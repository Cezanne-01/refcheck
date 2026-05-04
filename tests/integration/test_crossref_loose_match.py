"""Tests for the looser Crossref behavior: returns matches even when the
user-supplied year is wrong, but rejects results whose title is wildly
unrelated (similarity below threshold)."""
import json
from pathlib import Path
import pytest
import respx
from httpx import Response
from refcheck.fetch.crossref import CrossrefClient
from refcheck.schema.models import Author


FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures" / "api_responses" / "crossref_potenza_2013.json"
)


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_match_even_when_user_year_is_wrong():
    """User cited 2015 but the actual paper is 2013 — search should still
    return the paper now that we no longer use a strict year filter."""
    data = json.loads(FIXTURE.read_text())
    respx.get("https://api.crossref.org/works").mock(
        return_value=Response(200, json=data)
    )
    client = CrossrefClient()
    try:
        result = await client.search(
            title="Neurobiology of gambling",
            authors=[Author(family="Potenza")],
            year=2015,  # WRONG — actual paper is 2013
        )
        assert result is not None
        assert result.year == 2013  # canonical year, not user's year
        assert result.doi == "10.1016/j.conb.2013.01.020"
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_search_rejects_completely_unrelated_top_hit():
    """If Crossref's top hit has a title totally unrelated to the query,
    return None instead of pretending the unrelated paper matches."""
    bad_data = {
        "status": "ok",
        "message": {
            "items": [{
                "DOI": "10.1234/unrelated",
                "title": ["A study of mating habits in penguins"],
                "author": [{"family": "Smith"}],
                "published-print": {"date-parts": [[2020]]},
                "container-title": ["Bird Quarterly"],
            }]
        }
    }
    respx.get("https://api.crossref.org/works").mock(
        return_value=Response(200, json=bad_data)
    )
    client = CrossrefClient()
    try:
        result = await client.search(
            title="Neurobiology of gambling behaviors",
            authors=[Author(family="Potenza")],
            year=2013,
        )
        assert result is None
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_search_picks_best_title_match_among_candidates():
    """If Crossref returns multiple candidates, the one with highest title
    similarity wins (not necessarily Crossref's own ranking)."""
    data = {
        "status": "ok",
        "message": {
            "items": [
                {
                    "DOI": "10.0001/wrong",
                    "title": ["Penguin migration patterns"],
                    "author": [{"family": "Smith"}],
                    "published-print": {"date-parts": [[2020]]},
                },
                {
                    "DOI": "10.0002/right",
                    "title": ["Neurobiology of gambling behaviors"],
                    "author": [{"family": "Potenza"}],
                    "published-print": {"date-parts": [[2013]]},
                },
            ]
        }
    }
    respx.get("https://api.crossref.org/works").mock(
        return_value=Response(200, json=data)
    )
    client = CrossrefClient()
    try:
        result = await client.search(
            title="Neurobiology of gambling behaviors",
            authors=[Author(family="Potenza")],
            year=2013,
        )
        assert result is not None
        assert result.doi == "10.0002/right"
    finally:
        await client.close()
