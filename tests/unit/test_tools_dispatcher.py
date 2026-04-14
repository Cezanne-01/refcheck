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
    assert "fetch_abstract" in names
    assert "submit_final" in names


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
