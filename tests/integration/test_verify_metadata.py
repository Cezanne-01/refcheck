from unittest.mock import AsyncMock, MagicMock
import pytest
from refcheck.schema.models import Reference, Author
from refcheck.verify.metadata import verify_all_references
from refcheck.fetch.openalex import OpenAlexResult
from refcheck.fetch.semantic_scholar import SemanticScholarResult


def _canonical(title="Neurobiology of gambling", year=2013):
    return Reference(
        id="canonical",
        authors=[Author(family="Potenza")],
        year=year,
        title=title,
        doi="10.1016/x",
        raw_text="",
        style_detected="unknown",
    )


@pytest.mark.asyncio
async def test_verified_when_crossref_matches():
    ref = Reference(id="ref_001", authors=[Author(family="Potenza")], year=2013,
                    title="Neurobiology of gambling", raw_text="...", style_detected="APA")

    crossref = MagicMock()
    crossref.lookup_doi = AsyncMock(return_value=None)
    crossref.search = AsyncMock(return_value=_canonical())
    openalex = MagicMock()
    openalex.search = AsyncMock(return_value=None)
    semantic = MagicMock()
    semantic.search = AsyncMock(return_value=None)
    pubmed = MagicMock()
    pubmed.search = AsyncMock(return_value=None)

    results = await verify_all_references(
        [ref], crossref=crossref, openalex=openalex,
        semantic_scholar=semantic, pubmed=pubmed, concurrency=1,
    )
    assert results[0].status == "verified"
    assert "crossref" in results[0].sources_checked


@pytest.mark.asyncio
async def test_hallucination_when_all_sources_empty():
    ref = Reference(id="ref_001", authors=[Author(family="FakeAuthor")], year=2099,
                    title="A Paper That Does Not Exist", raw_text="...", style_detected="APA")

    crossref = MagicMock()
    crossref.lookup_doi = AsyncMock(return_value=None)
    crossref.search = AsyncMock(return_value=None)
    openalex = MagicMock()
    openalex.search = AsyncMock(return_value=None)
    semantic = MagicMock()
    semantic.search = AsyncMock(return_value=None)
    pubmed = MagicMock()
    pubmed.search = AsyncMock(return_value=None)

    results = await verify_all_references(
        [ref], crossref=crossref, openalex=openalex,
        semantic_scholar=semantic, pubmed=pubmed, concurrency=1,
    )
    assert results[0].status == "hallucination"
    assert len(results[0].sources_checked) == 4


@pytest.mark.asyncio
async def test_metadata_error_when_year_differs():
    ref = Reference(id="ref_001", authors=[Author(family="Potenza")], year=2012,
                    title="Neurobiology of gambling", raw_text="...", style_detected="APA")
    crossref = MagicMock()
    crossref.lookup_doi = AsyncMock(return_value=None)
    crossref.search = AsyncMock(return_value=_canonical(year=2013))
    openalex = MagicMock()
    openalex.search = AsyncMock(return_value=None)
    semantic = MagicMock()
    semantic.search = AsyncMock(return_value=None)
    pubmed = MagicMock()
    pubmed.search = AsyncMock(return_value=None)

    results = await verify_all_references(
        [ref], crossref=crossref, openalex=openalex,
        semantic_scholar=semantic, pubmed=pubmed, concurrency=1,
    )
    assert results[0].status == "metadata_error"
    assert "year" in results[0].field_diffs
