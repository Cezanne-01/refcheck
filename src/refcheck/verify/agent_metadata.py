from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Any
from refcheck.schema.models import Reference, VerifiedReference, Author
from refcheck.llm.agent import AgentRunner, AgentTimeoutError
from refcheck.llm.tools import METADATA_TOOLS, MetadataToolDispatcher
from refcheck.fetch.crossref import CrossrefClient
from refcheck.fetch.openalex import OpenAlexClient
from refcheck.fetch.semantic_scholar import SemanticScholarClient
from refcheck.fetch.pubmed import PubMedClient
from refcheck.fetch.web_search import WebSearchClient
from refcheck.verify.matching import compare_metadata


_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "metadata_agent.md"


def _format_ref_prompt(ref: Reference) -> str:
    authors = ", ".join(f"{a.family}, {a.given or ''}" for a in ref.authors)
    return (
        f"Verify this reference:\n"
        f"- Title: {ref.title}\n"
        f"- Authors: {authors}\n"
        f"- Year: {ref.year}\n"
        f"- DOI: {ref.doi or '(none)'}\n"
        f"- Journal: {ref.journal or '(not provided)'}\n"
        f"- Raw text: {ref.raw_text[:200]}"
    )


def _canonical_from_dict(d: dict[str, Any] | None) -> Reference | None:
    if not d:
        return None
    authors = [
        Author(given=a.get("given"), family=a.get("family", ""))
        for a in (d.get("authors") or [])
        if a.get("family")
    ]
    return Reference(
        id="canonical",
        authors=authors,
        year=d.get("year"),
        title=d.get("title", ""),
        journal=d.get("journal"),
        volume=d.get("volume"),
        issue=d.get("issue"),
        pages=d.get("pages"),
        doi=d.get("doi"),
        raw_text="",
        style_detected="unknown",
    )


async def verify_reference_agent(
    ref: Reference,
    *,
    openai_client: Any,
    crossref: CrossrefClient,
    openalex: OpenAlexClient,
    semantic_scholar: SemanticScholarClient,
    pubmed: PubMedClient,
    web_search: WebSearchClient | None = None,
    model: str = "gpt-5.4",
    max_turns: int = 6,
) -> VerifiedReference:
    """Run the metadata-verification agent for a single Reference."""
    dispatcher = MetadataToolDispatcher(
        crossref=crossref, openalex=openalex,
        semantic_scholar=semantic_scholar, pubmed=pubmed,
        web_search=web_search,
    )
    runner = AgentRunner(openai_client=openai_client, max_turns=max_turns)
    system = _PROMPT_PATH.read_text(encoding="utf-8")

    try:
        result = await runner.run(
            model=model,
            system_prompt=system,
            user_prompt=_format_ref_prompt(ref),
            tools=METADATA_TOOLS,
            dispatcher=dispatcher,
        )
    except AgentTimeoutError:
        return VerifiedReference(
            reference=ref,
            status="unverifiable",
            canonical=None,
            access_level="not_found",
            sources_checked=["agent_timeout"],
        )

    args = result.final_args
    canonical = _canonical_from_dict(args.get("canonical"))

    sources = []
    for t in result.tool_call_trace:
        name = t["tool"]
        if name.startswith("search_") or name.startswith("lookup_"):
            if name not in sources:
                sources.append(name)

    # Field diffs are computed deterministically from (ref, canonical) using
    # compare_metadata so the report is independent of how the agent chose to
    # phrase its diffs. The agent's reported diffs are kept only as a fallback
    # if no canonical was returned.
    field_diffs: dict[str, tuple[str | None, str | None]] = {}
    diff_severities: dict[str, str] = {}
    preprint_flag = bool(args.get("preprint_vs_published", False))
    if canonical is not None:
        match_result = compare_metadata(ref, canonical)
        field_diffs = match_result.field_diffs
        diff_severities = dict(match_result.diff_severities)
        preprint_flag = preprint_flag or match_result.preprint_vs_published
    else:
        diffs_raw = args.get("field_diffs") or []
        if isinstance(diffs_raw, list):
            for item in diffs_raw:
                if isinstance(item, dict) and "field" in item:
                    field_diffs[item["field"]] = (
                        item.get("user_value"),
                        item.get("canonical_value"),
                    )

    abstract = args.get("abstract")
    access_level: str = "abstract_only" if abstract else "not_found"

    # If the agent claimed metadata_error but compare_metadata found nothing
    # worth flagging (only nuisance-level differences), downgrade to verified.
    status = args.get("status", "unverifiable")
    if status == "metadata_error" and canonical is not None and not field_diffs:
        status = "verified"

    return VerifiedReference(
        reference=ref,
        status=status,
        canonical=canonical,
        field_diffs=field_diffs,
        diff_severities=diff_severities,  # type: ignore[arg-type]
        access_level=access_level,  # type: ignore[arg-type]
        abstract=abstract,
        sources_checked=sources,
        preprint_vs_published=preprint_flag,
    )


async def verify_all_references_agent(
    references: list[Reference],
    *,
    openai_client: Any,
    crossref: CrossrefClient,
    openalex: OpenAlexClient,
    semantic_scholar: SemanticScholarClient,
    pubmed: PubMedClient,
    web_search: WebSearchClient | None = None,
    model: str = "gpt-5.4",
    max_turns: int = 6,
    concurrency: int = 3,
) -> list[VerifiedReference]:
    sem = asyncio.Semaphore(concurrency)

    async def _worker(r: Reference) -> VerifiedReference:
        async with sem:
            return await verify_reference_agent(
                r, openai_client=openai_client,
                crossref=crossref, openalex=openalex,
                semantic_scholar=semantic_scholar, pubmed=pubmed,
                web_search=web_search,
                model=model, max_turns=max_turns,
            )

    return list(await asyncio.gather(*(_worker(r) for r in references)))
