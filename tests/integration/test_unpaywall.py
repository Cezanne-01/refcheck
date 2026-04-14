import pytest
import respx
from httpx import Response
from refcheck.fetch.unpaywall import UnpaywallClient


@pytest.mark.asyncio
@respx.mock
async def test_returns_oa_url():
    data = {
        "is_oa": True,
        "best_oa_location": {"url_for_pdf": "https://example.com/paper.pdf"},
    }
    respx.get("https://api.unpaywall.org/v2/10.1016/j.conb.2013.01.020").mock(
        return_value=Response(200, json=data)
    )
    client = UnpaywallClient(email="test@example.com")
    url = await client.oa_pdf_url("10.1016/j.conb.2013.01.020")
    assert url == "https://example.com/paper.pdf"
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_returns_none_when_not_oa():
    data = {"is_oa": False, "best_oa_location": None}
    respx.get("https://api.unpaywall.org/v2/10.1016/paywalled").mock(
        return_value=Response(200, json=data)
    )
    client = UnpaywallClient(email="test@example.com")
    url = await client.oa_pdf_url("10.1016/paywalled")
    assert url is None
    await client.close()
