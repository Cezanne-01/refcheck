from unittest.mock import AsyncMock, MagicMock, patch
import pytest


SAMPLE_HTML = """
<html><body>
<div class="result">
  <a class="result__a" href="https://example.com/paper1">Title One</a>
  <a class="result__snippet">Snippet text one with DOI 10.1000/abc</a>
</div>
<div class="result">
  <a class="result__a" href="https://arxiv.org/abs/2401.12345">arXiv:2401.12345 Title Two</a>
  <a class="result__snippet">Preprint abstract</a>
</div>
</body></html>
"""


@pytest.mark.asyncio
async def test_search_parses_results():
    from refcheck.fetch.web_search import WebSearchClient

    client = WebSearchClient()
    mock_resp = MagicMock(status_code=200, text=SAMPLE_HTML)
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "post", new=AsyncMock(return_value=mock_resp)):
        hits = await client.search("foo bar")
    try:
        assert len(hits) == 2
        assert hits[0].title == "Title One"
        assert hits[0].url == "https://example.com/paper1"
        assert "10.1000/abc" in hits[0].snippet
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_search_returns_empty_on_http_error():
    from refcheck.fetch.web_search import WebSearchClient

    client = WebSearchClient()
    mock_resp = MagicMock(status_code=503)
    with patch.object(client._client, "post", new=AsyncMock(return_value=mock_resp)):
        hits = await client.search("foo")
    try:
        assert hits == []
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_search_returns_empty_on_exception():
    from refcheck.fetch.web_search import WebSearchClient

    client = WebSearchClient()
    with patch.object(client._client, "post", new=AsyncMock(side_effect=RuntimeError("boom"))):
        hits = await client.search("foo")
    try:
        assert hits == []
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_search_max_results_limit():
    from refcheck.fetch.web_search import WebSearchClient

    client = WebSearchClient()
    blocks = "".join(
        f'<div class="result"><a class="result__a" href="https://x/{i}">T{i}</a>'
        f'<a class="result__snippet">S{i}</a></div>'
        for i in range(10)
    )
    html = f"<html><body>{blocks}</body></html>"
    mock_resp = MagicMock(status_code=200, text=html)
    with patch.object(client._client, "post", new=AsyncMock(return_value=mock_resp)):
        hits = await client.search("q", max_results=3)
    try:
        assert len(hits) == 3
        assert hits[0].title == "T0"
    finally:
        await client.close()
