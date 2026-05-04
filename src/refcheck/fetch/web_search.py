from __future__ import annotations
from dataclasses import dataclass
import httpx
from bs4 import BeautifulSoup


_DDG_URL = "https://html.duckduckgo.com/html/"
_UA = "Mozilla/5.0 (compatible; refcheck/0.1; +https://github.com/)"


@dataclass
class WebSearchHit:
    title: str
    url: str
    snippet: str


class WebSearchClient:
    """DuckDuckGo HTML search client. Free, no API key.

    Returns up to ``max_results`` hits. All errors are silently swallowed and
    return an empty list — this is a *backup* search and must never block
    the agent's primary academic-DB path.
    """

    def __init__(self, timeout: float = 10.0):
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": _UA},
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def search(self, query: str, max_results: int = 5) -> list[WebSearchHit]:
        try:
            r = await self._client.post(_DDG_URL, data={"q": query})
            if r.status_code != 200:
                return []
            html = r.text
        except Exception:
            return []

        soup = BeautifulSoup(html, "html.parser")
        hits: list[WebSearchHit] = []
        for div in soup.select("div.result"):
            a = div.select_one("a.result__a")
            if not a or not a.get("href"):
                continue
            snip = div.select_one(".result__snippet")
            hits.append(
                WebSearchHit(
                    title=a.get_text(strip=True),
                    url=a["href"],
                    snippet=snip.get_text(strip=True) if snip else "",
                )
            )
            if len(hits) >= max_results:
                break
        return hits
