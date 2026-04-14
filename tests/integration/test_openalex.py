import json
from pathlib import Path
import pytest
import respx
from httpx import Response
from refcheck.fetch.openalex import OpenAlexClient
from refcheck.schema.models import Author


FIXTURE = Path(__file__).parent.parent / "fixtures" / "api_responses" / "openalex_potenza_2013.json"


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_reference_with_abstract_and_oa():
    data = json.loads(FIXTURE.read_text())
    respx.get("https://api.openalex.org/works").mock(
        return_value=Response(200, json=data)
    )
    client = OpenAlexClient()
    result = await client.search(
        title="Neurobiology of gambling",
        authors=[Author(family="Potenza")],
        year=2013,
    )
    assert result is not None
    assert result.reference.year == 2013
    assert result.abstract is not None and "Gambling" in result.abstract
    assert result.is_oa is True
    assert result.oa_url == "https://example.com/paper.pdf"
    await client.close()
