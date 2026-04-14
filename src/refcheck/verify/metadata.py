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

    # 1. DOI 있으면 Crossref DOI 조회 (authoritative metadata but no abstract)
    if ref.doi:
        checked.append("crossref_doi")
        result = await _safe(crossref.lookup_doi(ref.doi))
        if result:
            vref = _build_verified(ref, result, checked)
            return await _enrich_abstract(vref, ref, openalex, semantic, pubmed, checked)

    # 2. Crossref 검색 (no abstract)
    checked.append("crossref")
    cr: Reference | None = await _safe(crossref.search(title=ref.title, authors=ref.authors, year=ref.year))
    if cr and _is_plausible_match(ref, cr):
        vref = _build_verified(ref, cr, checked)
        return await _enrich_abstract(vref, ref, openalex, semantic, pubmed, checked)
    if cr:
        best_match = cr

    # 3. OpenAlex (has abstract)
    checked.append("openalex")
    oa: OpenAlexResult | None = await _safe(openalex.search(title=ref.title, authors=ref.authors, year=ref.year))
    if oa and _is_plausible_match(ref, oa.reference):
        return _build_verified(
            ref, oa.reference, checked,
            abstract=oa.abstract,
            oa_url=oa.oa_url if oa.is_oa else None,
        )
    if oa and not best_match:
        best_match = oa.reference

    # 4. Semantic Scholar (has abstract)
    checked.append("semantic_scholar")
    ss: SemanticScholarResult | None = await _safe(semantic.search(title=ref.title, authors=ref.authors, year=ref.year))
    if ss and _is_plausible_match(ref, ss.reference):
        return _build_verified(ref, ss.reference, checked, abstract=ss.abstract)
    if ss and not best_match:
        best_match = ss.reference

    # 5. PubMed (has abstract)
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
            return _build_verified(ref, best_match, checked)
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


async def _enrich_abstract(
    vref: VerifiedReference,
    ref: Reference,
    openalex: OpenAlexClient,
    semantic: SemanticScholarClient,
    pubmed: PubMedClient,
    checked: list[str],
) -> VerifiedReference:
    """Crossref 검증 성공 후 OpenAlex/SS/PubMed에서 abstract·OA URL 보충."""
    if vref.abstract:
        return vref

    if "openalex" not in checked:
        checked.append("openalex_abstract")
    oa: OpenAlexResult | None = await _safe(
        openalex.search(title=ref.title, authors=ref.authors, year=ref.year)
    )
    if oa and oa.abstract:
        vref.abstract = oa.abstract
        vref.access_level = "abstract_only"
        if oa.is_oa and oa.oa_url:
            # source_fetcher에 OA 힌트 전달 — 실제 다운로드는 source_fetcher에서
            pass
        return vref

    if "semantic_scholar" not in checked:
        checked.append("semantic_scholar_abstract")
    ss: SemanticScholarResult | None = await _safe(
        semantic.search(title=ref.title, authors=ref.authors, year=ref.year)
    )
    if ss and ss.abstract:
        vref.abstract = ss.abstract
        vref.access_level = "abstract_only"
        return vref

    if "pubmed" not in checked:
        checked.append("pubmed_abstract")
    pm: PubMedResult | None = await _safe(
        pubmed.search(title=ref.title, authors=ref.authors, year=ref.year)
    )
    if pm and pm.abstract:
        vref.abstract = pm.abstract
        vref.access_level = "abstract_only"
        return vref

    return vref


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
    # access_level 초기값: abstract 있으면 abstract_only, 없으면 not_found
    # oa_url이 있어도 실제 다운로드는 source_fetcher에서 하므로 full_text로 미리 설정하지 않음
    access: str = "abstract_only" if abstract else "not_found"
    return VerifiedReference(
        reference=ref,
        status=match.status,
        canonical=canonical,
        field_diffs=match.field_diffs,
        access_level=access,  # type: ignore[arg-type]
        abstract=abstract,
        sources_checked=sources,
        preprint_vs_published=match.preprint_vs_published,
    )
