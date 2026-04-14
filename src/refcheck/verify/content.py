from __future__ import annotations
from pathlib import Path
from refcheck.schema.models import Citation, VerifiedReference, Finding
from refcheck.llm.client import LLMClient
from refcheck.verify.content_schema import CONTENT_VERIFY_SCHEMA
from refcheck.verify.evidence_validator import quote_exists_in_source


_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "content_verify.md"


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

    system = _PROMPT_PATH.read_text(encoding="utf-8")
    user = (
        f"DRAFT CLAIM:\n{citation.surrounding_paragraph}\n\n"
        f"CITED REFERENCE:\n"
        f"{_ref_summary(verified_ref)}\n\n"
        f"SOURCE TEXT ({'FULL' if verified_ref.full_text else 'ABSTRACT ONLY'}):\n{source_text}"
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
        confidence = "low" if confidence == "medium" else confidence

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
