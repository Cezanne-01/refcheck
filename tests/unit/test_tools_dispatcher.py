from unittest.mock import AsyncMock, MagicMock
import pytest
from refcheck.llm.tools import (
    METADATA_TOOLS,
    CONTENT_TOOLS,
    SUBMIT_METADATA_FINAL,
    SUBMIT_CONTENT_FINAL,
    MetadataToolDispatcher,
    ContentToolDispatcher,
)
from refcheck.schema.models import Reference, Author


def test_metadata_tools_include_all_search_apis():
    names = {t["function"]["name"] for t in METADATA_TOOLS}
    assert "search_crossref" in names
    assert "search_openalex" in names
    assert "search_semantic_scholar" in names
    assert "search_pubmed" in names
    assert "lookup_doi_crossref" in names
    assert "submit_final" in names


def test_content_tools_include_passage_search():
    names = {t["function"]["name"] for t in CONTENT_TOOLS}
    assert "find_passage" in names
    assert "fetch_full_text" in names
    assert "submit_final" in names
    # fetch_abstract was a stub — removed; content agent uses abstract from prompt
    assert "fetch_abstract" not in names


def test_metadata_tools_include_web_search():
    names = {t["function"]["name"] for t in METADATA_TOOLS}
    assert "web_search" in names


def test_final_tools_have_strict_schemas():
    assert SUBMIT_METADATA_FINAL["function"]["strict"] is True
    assert "status" in SUBMIT_METADATA_FINAL["function"]["parameters"]["properties"]
    assert SUBMIT_CONTENT_FINAL["function"]["strict"] is True
    assert "category" in SUBMIT_CONTENT_FINAL["function"]["parameters"]["properties"]


def _canonical():
    return Reference(
        id="canonical", authors=[Author(family="Potenza")], year=2013,
        title="Neurobiology of gambling", doi="10.1016/x",
        raw_text="", style_detected="unknown",
    )


@pytest.mark.asyncio
async def test_metadata_dispatcher_routes_crossref():
    crossref = MagicMock()
    crossref.search = AsyncMock(return_value=_canonical())
    openalex = MagicMock()
    semantic = MagicMock()
    pubmed = MagicMock()

    dispatcher = MetadataToolDispatcher(
        crossref=crossref, openalex=openalex,
        semantic_scholar=semantic, pubmed=pubmed,
    )

    result = await dispatcher.dispatch(
        "search_crossref",
        {"title": "Neurobiology of gambling", "authors": ["Potenza"], "year": 2013},
    )
    assert "title" in result
    assert result["title"] == "Neurobiology of gambling"
    crossref.search.assert_called_once()


@pytest.mark.asyncio
async def test_metadata_dispatcher_returns_empty_on_miss():
    crossref = MagicMock()
    crossref.search = AsyncMock(return_value=None)
    openalex = MagicMock()
    semantic = MagicMock()
    pubmed = MagicMock()

    dispatcher = MetadataToolDispatcher(
        crossref=crossref, openalex=openalex,
        semantic_scholar=semantic, pubmed=pubmed,
    )

    result = await dispatcher.dispatch(
        "search_crossref",
        {"title": "nonexistent", "authors": [], "year": 2099},
    )
    assert result == {"found": False}


@pytest.mark.asyncio
async def test_metadata_dispatcher_web_search():
    from refcheck.fetch.web_search import WebSearchHit
    ws = MagicMock()
    ws.search = AsyncMock(return_value=[
        WebSearchHit(title="T", url="https://x", snippet="DOI 10.1/x"),
        WebSearchHit(title="T2", url="https://y", snippet="more"),
    ])
    dispatcher = MetadataToolDispatcher(
        crossref=MagicMock(), openalex=MagicMock(),
        semantic_scholar=MagicMock(), pubmed=MagicMock(),
        web_search=ws,
    )
    out = await dispatcher.dispatch("web_search", {"query": "foo"})
    assert "hits" in out
    assert len(out["hits"]) == 2
    assert out["hits"][0]["url"] == "https://x"
    assert out["hits"][0]["snippet"] == "DOI 10.1/x"


@pytest.mark.asyncio
async def test_metadata_dispatcher_web_search_no_client():
    """If web_search client not configured, returns empty hits with note."""
    dispatcher = MetadataToolDispatcher(
        crossref=MagicMock(), openalex=MagicMock(),
        semantic_scholar=MagicMock(), pubmed=MagicMock(),
        web_search=None,
    )
    out = await dispatcher.dispatch("web_search", {"query": "foo"})
    assert out["hits"] == []
    assert "not configured" in out.get("note", "")


@pytest.mark.asyncio
async def test_content_dispatcher_fetch_full_text_updates_source():
    from refcheck.fetch.full_text import FullTextResult
    fetcher = MagicMock()
    fetcher.fetch = AsyncMock(return_value=FullTextResult(
        text="HELLO BODY about dopamine",
        source="arxiv",
        url="https://arxiv.org/x",
    ))
    dispatcher = ContentToolDispatcher(
        source_text="abstract only",
        full_text_fetcher=fetcher,
    )
    out = await dispatcher.dispatch(
        "fetch_full_text", {"doi": "10.1/x", "title": "t"}
    )
    assert out["full_text"] == "HELLO BODY about dopamine"
    assert out["source"] == "arxiv"
    # source_text should be updated for next find_passage
    assert dispatcher.source_text == "HELLO BODY about dopamine"


@pytest.mark.asyncio
async def test_content_dispatcher_fetch_full_text_no_fetcher():
    dispatcher = ContentToolDispatcher(
        source_text="abstract only",
        full_text_fetcher=None,
    )
    out = await dispatcher.dispatch(
        "fetch_full_text", {"doi": "10.1/x", "title": "t"}
    )
    assert out["full_text"] is None
    assert "not configured" in out.get("note", "")


@pytest.mark.asyncio
async def test_content_dispatcher_fetch_full_text_failure():
    from refcheck.fetch.full_text import FullTextResult
    fetcher = MagicMock()
    fetcher.fetch = AsyncMock(return_value=FullTextResult(
        text=None, source="none",
    ))
    dispatcher = ContentToolDispatcher(
        source_text="abstract only",
        full_text_fetcher=fetcher,
    )
    out = await dispatcher.dispatch(
        "fetch_full_text", {"doi": "10.1/x", "title": "t"}
    )
    assert out["full_text"] is None
    # source_text untouched
    assert dispatcher.source_text == "abstract only"


@pytest.mark.asyncio
async def test_content_dispatcher_find_passage():
    source_text = (
        "Para 1 about dopamine.\n\n"
        "Para 2 about gambling disorder shows hyperactivity.\n\n"
        "Para 3 about something else."
    )
    dispatcher = ContentToolDispatcher(source_text=source_text)
    result = await dispatcher.dispatch(
        "find_passage", {"query": "gambling hyperactivity"}
    )
    assert "passages" in result
    assert len(result["passages"]) >= 1
    assert "gambling" in result["passages"][0].lower()
