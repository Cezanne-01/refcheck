from __future__ import annotations
import asyncio
from refcheck.schema.models import Reference, VerifiedReference
from refcheck.verify.matching import compare_metadata, title_similarity, authors_match
from refcheck.fetch.crossref import CrossrefClient
from refcheck.fetch.openalex import OpenAlexClient, OpenAlexResult
from refcheck.fetch.semantic_scholar import SemanticScholarClient, SemanticScholarResult
from refcheck.fetch.pubmed import PubMedClient, PubMedResult


TITLE_ACCEPT = 0.90
TITLE_MAYBE = 0.70


async def verify_all_references(
    references: list[Reference],
    *,
    crossref: CrossrefClient,
    openalex: OpenAlexClient,
    semantic_scholar: SemanticScholarClient,
    pubmed: PubMedClient,
    concurrency: int = 5,
) -> list[VerifiedReference]:
    sem = asyncio.Semaphore(concurrency)

    async def _worker(r: Reference) -> VerifiedReference:
        async with sem:
            return await _verify_single(r, crossref, openalex, semantic_scholar, pubmed)

    return list(await asyncio.gather(*(_worker(r) for r in references)))


async def _verify_single(
    ref: Reference,
    crossref: CrossrefClient,
    openalex: OpenAlexClient,
    semantic: SemanticScholarClient,
    pubmed: PubMedClient,
) -> VerifiedReference:
    checked: list[str] = []
    best_match: Reference | None = None

    # 1. DOI 있으면 Crossref DOI 조회
    if ref.doi:
        checked.append("crossref_doi")
        result = await _safe(crossref.lookup_doi(ref.doi))
        if result:
            return _build_verified(ref, result, checked)

    # 2. Crossref 검색
    checked.append("crossref")
    cr: Reference | None = await _safe(crossref.search(title=ref.title, authors=ref.authors, year=ref.year))
    if cr and _is_plausible_match(ref, cr):
        return _build_verified(ref, cr, checked)
    if cr:
        best_match = cr

    # 3. OpenAlex
    checked.append("openalex")
    oa: OpenAlexResult | None = await _safe(openalex.search(title=ref.title, authors=ref.authors, year=ref.year))
    if oa and _is_plausible_match(ref, oa.reference):
        return _build_verified(ref, oa.reference, checked, abstract=oa.abstract,
                               oa_url=oa.oa_url if oa.is_oa else None)
    if oa and not best_match:
        best_match = oa.reference

    # 4. Semantic Scholar
    checked.append("semantic_scholar")
    ss: SemanticScholarResult | None = await _safe(semantic.search(title=ref.title, authors=ref.authors, year=ref.year))
    if ss and _is_plausible_match(ref, ss.reference):
        return _build_verified(ref, ss.reference, checked, abstract=ss.abstract)
    if ss and not best_match:
        best_match = ss.reference

    # 5. PubMed
    checked.append("pubmed")
    pm: PubMedResult | None = await _safe(pubmed.search(title=ref.title, authors=ref.authors, year=ref.year))
    if pm and _is_plausible_match(ref, pm.reference):
        return _build_verified(ref, pm.reference, checked, abstract=pm.abstract)
    if pm and not best_match:
        best_match = pm.reference

    # 6. 판정: best_match가 있으면 unverifiable 또는 metadata_error, 없으면 hallucination
    if best_match is not None:
        sim = title_similarity(ref.title, best_match.title)
        if sim >= TITLE_MAYBE:
            # 제목이 꽤 비슷 → metadata_error 가능성
            return _build_verified(ref, best_match, checked)
        # 애매한 일치
        return VerifiedReference(
            reference=ref,
            status="unverifiable",
            canonical=best_match,
            access_level="not_found",
            sources_checked=checked,
        )

    return VerifiedReference(
        reference=ref,
        status="hallucination",
        canonical=None,
        access_level="not_found",
        sources_checked=checked,
    )


async def _safe(awaitable):
    try:
        return await awaitable
    except Exception:
        return None


def _is_plausible_match(ref: Reference, cand: Reference) -> bool:
    return title_similarity(ref.title, cand.title) >= TITLE_ACCEPT and authors_match(ref.authors, cand.authors)


def _build_verified(
    ref: Reference,
    canonical: Reference,
    sources: list[str],
    *,
    abstract: str | None = None,
    oa_url: str | None = None,
) -> VerifiedReference:
    match = compare_metadata(ref, canonical)
    access = "abstract_only" if abstract else "not_found"
    if oa_url:
        access = "full_text"  # 실제 다운로드는 Task 18에서
    return VerifiedReference(
        reference=ref,
        status=match.status,
        canonical=canonical,
        field_diffs=match.field_diffs,
        access_level=access,
        abstract=abstract,
        sources_checked=sources,
    )
