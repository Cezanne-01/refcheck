from __future__ import annotations
import asyncio
import re
from pathlib import Path
from refcheck.schema.models import Citation, VerifiedReference, Finding
from refcheck.llm.client import LLMClient
from refcheck.verify.content_schema import CONTENT_VERIFY_SCHEMA
from refcheck.verify.evidence_validator import quote_exists_in_source


_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "content_verify.md"

# Max characters of source_text sent to LLM. Above this, run mini-retrieval.
# ~30k chars ≈ 7-10k tokens — comfortable for all supported models.
_FULL_TEXT_LIMIT = 30000


def _extract_relevant_passages(claim: str, source: str, max_chars: int = _FULL_TEXT_LIMIT) -> str:
    """Keyword-based passage retrieval when full text exceeds size budget.

    Splits source into paragraphs, scores each by overlap with claim keywords,
    returns top-scoring paragraphs in document order until reaching max_chars.
    """
    if len(source) <= max_chars:
        return source

    # Tokenize claim into meaningful keywords (drop stopwords + short tokens)
    tokens = re.findall(r"[A-Za-z가-힣0-9]{4,}", claim.lower())
    stopwords = {"that", "this", "with", "from", "which", "they", "their", "have",
                 "been", "were", "also", "what", "when", "where", "these", "those",
                 "하여", "이러한", "그러나", "따라서", "대한", "위한", "있다", "없다"}
    keywords = {t for t in tokens if t not in stopwords}

    if not keywords:
        # No usable keywords — just take head + tail of source
        half = max_chars // 2
        return source[:half] + "\n\n[... 중간 생략 ...]\n\n" + source[-half:]

    # Score each paragraph
    paragraphs = re.split(r"\n{2,}", source)
    scored: list[tuple[int, int, str]] = []  # (-score, idx, paragraph)
    for idx, para in enumerate(paragraphs):
        para_lower = para.lower()
        score = sum(1 for kw in keywords if kw in para_lower)
        if score > 0:
            scored.append((-score, idx, para))

    if not scored:
        half = max_chars // 2
        return source[:half] + "\n\n[... 중간 생략 ...]\n\n" + source[-half:]

    # Pick top paragraphs, restore document order, truncate to budget
    scored.sort()
    picked_indices: set[int] = set()
    total = 0
    for _, idx, para in scored:
        if total + len(para) > max_chars:
            break
        picked_indices.add(idx)
        total += len(para)

    out_parts = [paragraphs[i] for i in sorted(picked_indices)]
    return "\n\n".join(out_parts)


def _downgrade_confidence(c: str) -> str:
    """high→medium, medium→low, low→low (한 단계 내림)."""
    return {"high": "medium", "medium": "low", "low": "low"}.get(c, c)


async def verify_citation(
    citation: Citation,
    verified_ref: VerifiedReference,
    *,
    llm: LLMClient,
    model: str = "gpt-5.4-thinking",
    max_evidence_retries: int = 1,
) -> Finding | None:
    """단일 citation을 원문 대조하여 Finding 반환 (문제 없으면 None)."""
    if verified_ref.status in ("hallucination", "unverifiable"):
        return None

    source_text = verified_ref.full_text or verified_ref.abstract
    if not source_text:
        return Finding(
            id=f"find_{citation.id}",
            citation_id=citation.id,
            reference_id=verified_ref.reference.id,
            category="paywalled",
            error_type=None,
            severity=1,
            confidence="low",
            draft_claim_quote=citation.containing_sentence,
            source_evidence_quote=None,
            explanation="원문 전문·초록 모두 접근 불가. 수동 확인 권장.",
            suggestion=None,
        )

    # Mini-retrieval: if source is too long, extract relevant passages by keyword overlap
    if verified_ref.full_text and len(source_text) > _FULL_TEXT_LIMIT:
        source_label = "FULL (relevant passages only)"
        source_text = _extract_relevant_passages(
            citation.surrounding_paragraph, source_text, max_chars=_FULL_TEXT_LIMIT
        )
    elif verified_ref.full_text:
        source_label = "FULL"
    else:
        source_label = "ABSTRACT ONLY"

    system = _PROMPT_PATH.read_text(encoding="utf-8")
    user = (
        f"DRAFT CLAIM:\n{citation.surrounding_paragraph}\n\n"
        f"CITED REFERENCE:\n"
        f"{_ref_summary(verified_ref)}\n\n"
        f"SOURCE TEXT ({source_label}):\n{source_text}"
    )

    attempts = 0
    last_result: dict | None = None
    while attempts <= max_evidence_retries:
        result, _ = await llm.complete_json(
            model=model,
            system=system,
            user=user,
            response_schema=CONTENT_VERIFY_SCHEMA,
            temperature=0.2 if attempts == 0 else 0.0,
        )
        last_result = result
        quote = result.get("source_evidence_quote", "")
        if quote_exists_in_source(quote, source_text):
            break
        attempts += 1

    assert last_result is not None
    category = last_result["category"]
    if category == "none":
        return None

    quote = last_result.get("source_evidence_quote", "")
    evidence_valid = quote_exists_in_source(quote, source_text)
    confidence = last_result["confidence"] if evidence_valid else "low"
    final_quote = quote if evidence_valid else None

    # access_level이 abstract_only면 confidence 한 단계 낮춤
    if verified_ref.access_level == "abstract_only" and category != "none":
        confidence = _downgrade_confidence(confidence)

    return Finding(
        id=f"find_{citation.id}",
        citation_id=citation.id,
        reference_id=verified_ref.reference.id,
        category=category,
        error_type=last_result.get("error_type"),
        severity=int(last_result["severity"]),
        confidence=confidence,
        draft_claim_quote=citation.containing_sentence,
        source_evidence_quote=final_quote,
        explanation=last_result["explanation"],
        suggestion=last_result.get("suggestion"),
    )


def _ref_summary(vref: VerifiedReference) -> str:
    r = vref.canonical or vref.reference
    authors = ", ".join(a.family for a in r.authors)
    return f"{authors} ({r.year}). {r.title}. {r.journal or ''}"


async def verify_all_content(
    citations: list[Citation],
    verified_refs: list[VerifiedReference],
    *,
    llm: LLMClient,
    model: str = "gpt-5.4-thinking",
    concurrency: int = 5,
) -> list[Finding]:
    """모든 citation을 병렬로 검증. 각 citation이 여러 ref를 가리키면 각 ref별로 finding 생성."""
    vref_by_id = {v.reference.id: v for v in verified_refs}
    sem = asyncio.Semaphore(concurrency)

    async def _worker(cit: Citation, ref_id: str) -> Finding | None:
        vref = vref_by_id.get(ref_id)
        if vref is None:
            return None
        async with sem:
            return await verify_citation(cit, vref, llm=llm, model=model)

    tasks = []
    for cit in citations:
        for ref_id in cit.ref_ids:
            tasks.append(_worker(cit, ref_id))

    results = await asyncio.gather(*tasks)
    return [f for f in results if f is not None]
