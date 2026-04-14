import json
from pathlib import Path
import pytest
import respx
from httpx import Response
from refcheck.fetch.crossref import CrossrefClient
from refcheck.schema.models import Reference, Author


FIXTURE = Path(__file__).parent.parent / "fixtures" / "api_responses" / "crossref_potenza_2013.json"


@pytest.mark.asyncio
@respx.mock
async def test_search_by_title_and_author():
    data = json.loads(FIXTURE.read_text())
    respx.get("https://api.crossref.org/works").mock(
        return_value=Response(200, json=data)
    )

    client = CrossrefClient()
    result = await client.search(
        title="Neurobiology of gambling",
        authors=[Author(family="Potenza")],
        year=2013,
    )
    assert result is not None
    assert result.title == "Neurobiology of gambling"
    assert result.doi == "10.1016/j.conb.2013.01.020"
    assert result.year == 2013
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_lookup_by_doi():
    data = {"status": "ok", "message": {
        "DOI": "10.1016/j.conb.2013.01.020",
        "title": ["Neurobiology of gambling"],
        "author": [{"given": "Marc N.", "family": "Potenza"}],
        "published-print": {"date-parts": [[2013, 8]]},
        "container-title": ["Current Opinion in Neurobiology"],
        "volume": "23", "issue": "4", "page": "660-667",
    }}
    respx.get("https://api.crossref.org/works/10.1016/j.conb.2013.01.020").mock(
        return_value=Response(200, json=data)
    )
    client = CrossrefClient()
    result = await client.lookup_doi("10.1016/j.conb.2013.01.020")
    assert result is not None
    assert result.year == 2013
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_returns_none_on_not_found():
    respx.get("https://api.crossref.org/works").mock(
        return_value=Response(200, json={"status": "ok", "message": {"items": []}})
    )
    client = CrossrefClient()
    result = await client.search(title="nonexistent paper", authors=[], year=2099)
    assert result is None
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_lookup_doi_strips_url_prefix():
    """DOI가 'https://doi.org/10.xxx' 형태여도 정상 조회."""
    data = {"status": "ok", "message": {
        "DOI": "10.1016/j.conb.2013.01.020",
        "title": ["Neurobiology of gambling"],
        "author": [{"given": "Marc N.", "family": "Potenza"}],
        "published-print": {"date-parts": [[2013, 8]]},
        "container-title": ["Current Opinion in Neurobiology"],
    }}
    respx.get("https://api.crossref.org/works/10.1016/j.conb.2013.01.020").mock(
        return_value=Response(200, json=data)
    )
    client = CrossrefClient()

    # With URL prefix
    result1 = await client.lookup_doi("https://doi.org/10.1016/j.conb.2013.01.020")
    assert result1 is not None
    assert result1.year == 2013

    # With doi: prefix
    result2 = await client.lookup_doi("doi:10.1016/j.conb.2013.01.020")
    assert result2 is not None
    assert result2.year == 2013

    await client.close()
