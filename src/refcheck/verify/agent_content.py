from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Any
from refcheck.schema.models import Citation, VerifiedReference, Finding
from refcheck.llm.agent import AgentRunner, AgentTimeoutError
from refcheck.llm.tools import CONTENT_TOOLS, ContentToolDispatcher
from refcheck.fetch.full_text import FullTextFetcher


_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "content_agent.md"


def _format_user_prompt(cit: Citation, vref: VerifiedReference) -> str:
    r = vref.canonical or vref.reference
    authors = ", ".join(a.family for a in r.authors[:3])
    return (
        f"DRAFT CLAIM (in surrounding paragraph):\n"
        f"{cit.surrounding_paragraph}\n\n"
        f"CITED REFERENCE:\n"
        f"{authors} ({r.year}). {r.title}. {r.journal or ''}\n"
        f"DOI: {r.doi or '(none)'}\n\n"
        f"SOURCE TEXT ({'FULL' if vref.full_text else 'ABSTRACT ONLY'}):\n"
        f"{vref.full_text or vref.abstract or '(no text available)'}"
    )


_CATEGORY_MAP = {
    "content_mismatch": "content_mismatch",
    "weak_context": "weak_context",
    "none": None,
    "abstract_insufficient": "partial_verified",
}


async def verify_citation_agent(
    citation: Citation,
    verified_ref: VerifiedReference,
    *,
    openai_client: Any,
    full_text_fetcher: FullTextFetcher | None = None,
    model: str = "gpt-5.4",
    max_turns: int = 5,
    llm_client: Any | None = None,
) -> Finding | None:
    """Run the content-verification agent for a single citation.

    If ``llm_client`` is provided, agent token usage is recorded there.
    """
    if verified_ref.status in ("hallucination", "unverifiable"):
        return None

    source_text = verified_ref.full_text or verified_ref.abstract or ""
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
            explanation="원문 전문·초록 모두 접근 불가.",
            suggestion=None,
        )

    dispatcher = ContentToolDispatcher(
        source_text=source_text,
        full_text_fetcher=full_text_fetcher,
    )
    runner = AgentRunner(openai_client=openai_client, max_turns=max_turns)
    system = _PROMPT_PATH.read_text(encoding="utf-8")

    try:
        result = await runner.run(
            model=model,
            system_prompt=system,
            user_prompt=_format_user_prompt(citation, verified_ref),
            tools=CONTENT_TOOLS,
            dispatcher=dispatcher,
        )
        if llm_client is not None:
            llm_client.record_external_usage(
                model=model,
                prompt_tokens=result.total_prompt_tokens,
                completion_tokens=result.total_completion_tokens,
            )
    except AgentTimeoutError:
        return Finding(
            id=f"find_{citation.id}",
            citation_id=citation.id,
            reference_id=verified_ref.reference.id,
            category="partial_verified",
            error_type="agent_timeout",
            severity=1,
            confidence="low",
            draft_claim_quote=citation.containing_sentence,
            source_evidence_quote=None,
            explanation="에이전트가 판단을 마치지 못해 타임아웃. 수동 확인 필요.",
            suggestion=None,
        )

    args = result.final_args
    raw_category = args.get("category", "none")
    mapped = _CATEGORY_MAP.get(raw_category)
    if mapped is None:
        return None

    return Finding(
        id=f"find_{citation.id}",
        citation_id=citation.id,
        reference_id=verified_ref.reference.id,
        category=mapped,  # type: ignore[arg-type]
        error_type=args.get("error_type"),
        severity=int(args.get("severity", 1)),
        confidence=args.get("confidence", "low"),
        draft_claim_quote=citation.containing_sentence,
        source_evidence_quote=args.get("source_evidence_quote") or None,
        explanation=args.get("explanation", ""),
        suggestion=args.get("suggestion"),
    )


async def verify_all_content_agent(
    citations: list[Citation],
    verified_refs: list[VerifiedReference],
    *,
    openai_client: Any,
    full_text_fetcher: FullTextFetcher | None = None,
    model: str = "gpt-5.4",
    max_turns: int = 5,
    concurrency: int = 3,
    llm_client: Any | None = None,
) -> list[Finding]:
    vref_by_id = {v.reference.id: v for v in verified_refs}
    sem = asyncio.Semaphore(concurrency)

    async def _worker(cit: Citation, ref_id: str) -> Finding | None:
        vref = vref_by_id.get(ref_id)
        if vref is None:
            return None
        async with sem:
            return await verify_citation_agent(
                cit, vref,
                openai_client=openai_client,
                full_text_fetcher=full_text_fetcher,
                model=model, max_turns=max_turns,
                llm_client=llm_client,
            )

    tasks = []
    for cit in citations:
        for ref_id in cit.ref_ids:
            tasks.append(_worker(cit, ref_id))
    results = await asyncio.gather(*tasks)
    return [f for f in results if f is not None]
