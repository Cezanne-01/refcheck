from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from refcheck.schema.models import Reference, Author


BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,year,authors,venue,externalIds,abstract"


@dataclass
class SemanticScholarResult:
    reference: Reference
    abstract: str | None


class SemanticScholarClient:
    def __init__(self, api_key: str | None = None, timeout: float = 10.0):
        headers = {"User-Agent": "refcheck/0.1"}
        if api_key:
            headers["x-api-key"] = api_key
        self._client = httpx.AsyncClient(headers=headers, timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5), reraise=True)
    async def search(
        self,
        *,
        title: str,
        authors: list[Author],
        year: int | None,
        limit: int = 5,
    ) -> SemanticScholarResult | None:
        query = title
        if authors:
            query = f"{title} {authors[0].family}"
        params: dict[str, Any] = {"query": query, "limit": limit, "fields": FIELDS}
        if year:
            params["year"] = str(year)
        r = await self._client.get(BASE_URL, params=params)
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return None
        return _to_result(data[0])


def _to_result(item: dict[str, Any]) -> SemanticScholarResult:
    authors_raw = item.get("authors") or []
    authors: list[Author] = []
    for a in authors_raw:
        name = a.get("name", "")
        parts = name.rsplit(" ", 1)
        if len(parts) == 2:
            authors.append(Author(given=parts[0], family=parts[1]))
        elif name:
            authors.append(Author(family=name))

    ext = item.get("externalIds") or {}
    ref = Reference(
        id="canonical",
        authors=authors,
        year=item.get("year"),
        title=item.get("title", ""),
        journal=item.get("venue"),
        doi=ext.get("DOI"),
        raw_text="",
        style_detected="unknown",
    )
    return SemanticScholarResult(reference=ref, abstract=item.get("abstract"))
