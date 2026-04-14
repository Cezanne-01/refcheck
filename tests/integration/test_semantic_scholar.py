import pytest
import respx
from httpx import Response
from refcheck.fetch.semantic_scholar import SemanticScholarClient
from refcheck.schema.models import Author


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_reference():
    data = {
        "data": [{
            "paperId": "abc123",
            "title": "Neurobiology of gambling",
            "year": 2013,
            "authors": [{"name": "Marc N. Potenza"}],
            "venue": "Current Opinion in Neurobiology",
            "externalIds": {"DOI": "10.1016/j.conb.2013.01.020"},
            "abstract": "Gambling disorder is ...",
        }]
    }
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=Response(200, json=data)
    )
    client = SemanticScholarClient()
    result = await client.search(
        title="Neurobiology of gambling",
        authors=[Author(family="Potenza")],
        year=2013,
    )
    assert result is not None
    assert result.reference.doi == "10.1016/j.conb.2013.01.020"
    assert result.abstract is not None
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_returns_none_on_empty():
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=Response(200, json={"data": []})
    )
    client = SemanticScholarClient()
    result = await client.search(title="zzz", authors=[], year=2099)
    assert result is None
    await client.close()
