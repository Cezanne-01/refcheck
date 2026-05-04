"""Tests for the title-similarity validation and re-ordered fallback chain
introduced to fix the bug where arXiv returned arbitrary unrelated papers
when given a medical/psych paper title (which arXiv does not index)."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.mark.asyncio
async def test_arxiv_skipped_when_doi_present():
    """If a DOI is given, the paper is formally published — arXiv should NOT
    be consulted (arXiv is preprint-only and was the source of the bug)."""
    from refcheck.fetch.full_text import FullTextFetcher

    f = FullTextFetcher(unpaywall=None)
    arxiv_mock = AsyncMock(return_value=("SHOULD NOT APPEAR", "url"))
    try:
        with patch.object(f, "_try_arxiv", new=arxiv_mock), \
             patch.object(f, "_try_europepmc", new=AsyncMock(return_value=(None, None))):
            result = await f.fetch(
                doi="10.1234/foo", title="Some title", year=None,
            )
        assert result.text is None
        arxiv_mock.assert_not_called()
    finally:
        await f.close()


@pytest.mark.asyncio
async def test_europepmc_tried_before_arxiv():
    """EuropePMC is tier-1 now; arXiv is tier-3. When EPMC returns text,
    arXiv should not be called even when there is no DOI."""
    from refcheck.fetch.full_text import FullTextFetcher

    f = FullTextFetcher(unpaywall=None)
    arxiv_mock = AsyncMock(return_value=("ARXIV", "u"))
    try:
        with patch.object(
            f, "_try_europepmc",
            new=AsyncMock(return_value=("EPMC TEXT", "epmc-url")),
        ), patch.object(f, "_try_arxiv", new=arxiv_mock):
            result = await f.fetch(doi=None, title="Some title", year=None)
        assert result.source == "europepmc"
        assert result.text == "EPMC TEXT"
        arxiv_mock.assert_not_called()
    finally:
        await f.close()


@pytest.mark.asyncio
async def test_arxiv_validates_title_similarity_rejects_unrelated():
    """Real arXiv API mock: it returns a wildly unrelated paper, and the
    fetcher must reject it on the title-similarity check."""
    from refcheck.fetch.full_text import FullTextFetcher

    # arXiv Atom feed with a single result whose title is nothing like the
    # query — this is the historical bug scenario.
    fake_xml = """
    <feed>
      <entry>
        <id>http://arxiv.org/abs/1234.5678</id>
        <title>Observation of B-meson decay at CMS LHCb</title>
      </entry>
    </feed>
    """
    f = FullTextFetcher(unpaywall=None)
    try:
        # Mock the HTTP layer so _try_arxiv parses the fake XML.
        mock_get = AsyncMock(return_value=MagicMock(status_code=200, text=fake_xml))
        with patch.object(f._client, "get", new=mock_get), \
             patch.object(
                 f, "_download_pdf",
                 new=AsyncMock(return_value="SHOULD-NOT-BE-DOWNLOADED"),
             ):
            text, url = await f._try_arxiv("Neurobiology of gambling behaviors")
        assert text is None
        assert url is None
    finally:
        await f.close()


@pytest.mark.asyncio
async def test_arxiv_accepts_high_similarity_match():
    """When arXiv returns a title very close to the query, accept it."""
    from refcheck.fetch.full_text import FullTextFetcher

    fake_xml = """
    <feed>
      <entry>
        <id>http://arxiv.org/abs/1234.5678</id>
        <title>Neurobiology of gambling behavior</title>
      </entry>
    </feed>
    """
    f = FullTextFetcher(unpaywall=None)
    try:
        mock_get = AsyncMock(return_value=MagicMock(status_code=200, text=fake_xml))
        with patch.object(f._client, "get", new=mock_get), \
             patch.object(
                 f, "_download_pdf",
                 new=AsyncMock(return_value="REAL PAPER TEXT"),
             ):
            text, url = await f._try_arxiv("Neurobiology of gambling behaviors")
        assert text == "REAL PAPER TEXT"
        assert url and url.startswith("http://arxiv.org/pdf/1234.5678")
    finally:
        await f.close()


@pytest.mark.asyncio
async def test_arxiv_picks_best_match_among_multiple_candidates():
    """If arXiv returns several entries, pick the one with highest title
    similarity rather than just the first."""
    from refcheck.fetch.full_text import FullTextFetcher

    fake_xml = """
    <feed>
      <entry>
        <id>http://arxiv.org/abs/9999.9999</id>
        <title>Some unrelated paper about quantum chromodynamics</title>
      </entry>
      <entry>
        <id>http://arxiv.org/abs/1234.5678</id>
        <title>Neurobiology of gambling behavior</title>
      </entry>
    </feed>
    """
    f = FullTextFetcher(unpaywall=None)
    try:
        mock_get = AsyncMock(return_value=MagicMock(status_code=200, text=fake_xml))
        with patch.object(f._client, "get", new=mock_get), \
             patch.object(
                 f, "_download_pdf",
                 new=AsyncMock(return_value="MATCHED TEXT"),
             ):
            text, url = await f._try_arxiv("Neurobiology of gambling behaviors")
        assert text == "MATCHED TEXT"
        assert "1234.5678" in (url or "")
    finally:
        await f.close()
