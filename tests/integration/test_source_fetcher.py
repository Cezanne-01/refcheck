from unittest.mock import AsyncMock, MagicMock
import pytest
from refcheck.schema.models import VerifiedReference, Reference, Author
from refcheck.fetch.source_fetcher import fetch_sources
from refcheck.fetch.full_text import FullTextResult


def _vref(doi="10.1016/x", abstract=None, access_level="not_found"):
    return VerifiedReference(
        reference=Reference(
            id="ref_001", authors=[Author(family="X")], year=2020,
            title="T", doi=doi, raw_text="...", style_detected="APA",
        ),
        status="verified",
        canonical=Reference(
            id="canonical", authors=[Author(family="X")], year=2020,
            title="T", doi=doi, raw_text="", style_detected="unknown",
        ),
        abstract=abstract,
        access_level=access_level,
    )


@pytest.mark.asyncio
async def test_paywalled_when_no_oa(tmp_path):
    vref = _vref(abstract="Short abstract", access_level="abstract_only")
    fetcher = MagicMock()
    fetcher.fetch = AsyncMock(return_value=FullTextResult(text=None, source="none"))

    result = await fetch_sources(
        [vref], full_text_fetcher=fetcher, cache_dir=tmp_path,
    )
    assert result[0].access_level == "abstract_only"


@pytest.mark.asyncio
async def test_marks_paywalled_when_no_abstract_no_oa(tmp_path):
    vref = _vref(abstract=None, access_level="not_found")
    fetcher = MagicMock()
    fetcher.fetch = AsyncMock(return_value=FullTextResult(text=None, source="none"))

    result = await fetch_sources(
        [vref], full_text_fetcher=fetcher, cache_dir=tmp_path,
    )
    assert result[0].access_level == "paywalled"


@pytest.mark.asyncio
async def test_downloads_full_text_when_available(tmp_path):
    vref = _vref(abstract="abs", access_level="abstract_only")
    fetcher = MagicMock()
    fetcher.fetch = AsyncMock(return_value=FullTextResult(
        text="Full text content here covering many topics.",
        source="arxiv",
        url="https://arxiv.org/x",
    ))

    result = await fetch_sources(
        [vref], full_text_fetcher=fetcher,
        cache_dir=tmp_path / "cache",
    )
    assert result[0].access_level == "full_text"
    assert "Full text content" in (result[0].full_text or "")


@pytest.mark.asyncio
async def test_skips_hallucination(tmp_path):
    vref = _vref(abstract=None, access_level="not_found")
    vref.status = "hallucination"
    fetcher = MagicMock()
    fetcher.fetch = AsyncMock()

    result = await fetch_sources(
        [vref], full_text_fetcher=fetcher, cache_dir=tmp_path,
    )
    fetcher.fetch.assert_not_called()
    assert result[0].status == "hallucination"


@pytest.mark.asyncio
async def test_uses_cache_on_second_call(tmp_path):
    vref1 = _vref(doi="10.1/cache_test", access_level="abstract_only")
    vref2 = _vref(doi="10.1/cache_test", access_level="abstract_only")
    fetcher = MagicMock()
    fetcher.fetch = AsyncMock(return_value=FullTextResult(
        text="cached body text long enough",
        source="europepmc",
    ))

    await fetch_sources([vref1], full_text_fetcher=fetcher, cache_dir=tmp_path)
    assert fetcher.fetch.call_count == 1

    await fetch_sources([vref2], full_text_fetcher=fetcher, cache_dir=tmp_path)
    # Second call hits cache, fetcher not called again
    assert fetcher.fetch.call_count == 1
    assert vref2.full_text is not None
    assert vref2.access_level == "full_text"
