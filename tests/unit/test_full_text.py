from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.mark.asyncio
async def test_fetch_returns_arxiv_when_found():
    from refcheck.fetch.full_text import FullTextFetcher

    f = FullTextFetcher(unpaywall=None)
    try:
        with patch.object(
            f, "_try_arxiv",
            new=AsyncMock(return_value=("ARXIV TEXT", "https://arxiv.org/pdf/x")),
        ):
            result = await f.fetch(doi=None, title="Foo bar", year=2024)
        assert result.text == "ARXIV TEXT"
        assert result.source == "arxiv"
        assert result.url == "https://arxiv.org/pdf/x"
    finally:
        await f.close()


@pytest.mark.asyncio
async def test_fetch_falls_through_to_europepmc():
    from refcheck.fetch.full_text import FullTextFetcher

    f = FullTextFetcher(unpaywall=None)
    try:
        with patch.object(f, "_try_arxiv", new=AsyncMock(return_value=(None, None))), \
             patch.object(
                 f, "_try_europepmc",
                 new=AsyncMock(return_value=("EPMC TEXT", "https://epmc/x")),
             ):
            result = await f.fetch(doi="10.1/x", title="t", year=None)
        assert result.text == "EPMC TEXT"
        assert result.source == "europepmc"
    finally:
        await f.close()


@pytest.mark.asyncio
async def test_fetch_falls_through_to_unpaywall():
    from refcheck.fetch.full_text import FullTextFetcher

    upw = MagicMock()
    upw.oa_pdf_url = AsyncMock(return_value="https://oa/x.pdf")
    f = FullTextFetcher(unpaywall=upw)
    try:
        with patch.object(f, "_try_arxiv", new=AsyncMock(return_value=(None, None))), \
             patch.object(f, "_try_europepmc", new=AsyncMock(return_value=(None, None))), \
             patch.object(f, "_download_pdf", new=AsyncMock(return_value="UPW TEXT")):
            result = await f.fetch(doi="10.1/x", title="t", year=None)
        assert result.text == "UPW TEXT"
        assert result.source == "unpaywall"
    finally:
        await f.close()


@pytest.mark.asyncio
async def test_fetch_returns_none_when_all_fail():
    from refcheck.fetch.full_text import FullTextFetcher

    f = FullTextFetcher(unpaywall=None)
    try:
        with patch.object(f, "_try_arxiv", new=AsyncMock(return_value=(None, None))), \
             patch.object(f, "_try_europepmc", new=AsyncMock(return_value=(None, None))):
            result = await f.fetch(doi="10.1/x", title="t", year=None)
        assert result.text is None
        assert result.source == "none"
    finally:
        await f.close()


@pytest.mark.asyncio
async def test_fetch_skips_arxiv_when_no_title_no_doi():
    from refcheck.fetch.full_text import FullTextFetcher

    f = FullTextFetcher(unpaywall=None)
    try:
        result = await f.fetch(doi=None, title="", year=None)
        assert result.text is None
        assert result.source == "none"
    finally:
        await f.close()


@pytest.mark.asyncio
async def test_fetch_unpaywall_skipped_when_no_doi():
    from refcheck.fetch.full_text import FullTextFetcher

    upw = MagicMock()
    upw.oa_pdf_url = AsyncMock(return_value="should-not-be-called")
    f = FullTextFetcher(unpaywall=upw)
    try:
        with patch.object(f, "_try_arxiv", new=AsyncMock(return_value=(None, None))), \
             patch.object(f, "_try_europepmc", new=AsyncMock(return_value=(None, None))):
            result = await f.fetch(doi=None, title="t", year=None)
        assert result.text is None
        upw.oa_pdf_url.assert_not_called()
    finally:
        await f.close()
