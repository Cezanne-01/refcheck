from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from refcheck.schema.models import Reference, Author
from refcheck._match import title_similarity, surname_overlap


BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,year,authors,venue,externalIds,abstract"

_MIN_SIMILARITY = 0.40


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
        """Search Semantic Scholar.

        Year is not used as a strict filter; ranking is by title similarity
        with author-overlap penalty and a small year-proximity bonus.
        """
        query = title
        if authors:
            query = f"{title} {authors[0].family}"
        params: dict[str, Any] = {"query": query, "limit": limit, "fields": FIELDS}
        r = await self._client.get(BASE_URL, params=params)
        r.raise_for_status()
        data = r.json().get("data", []) or []
        if not data:
            return None
        best = _best_match(
            data, query_title=title, query_authors=authors, query_year=year,
        )
        return _to_result(best) if best else None


def _best_match(
    items: list[dict[str, Any]],
    *,
    query_title: str,
    query_authors: list[Author],
    query_year: int | None,
) -> dict[str, Any] | None:
    query_surnames = [a.family for a in query_authors if a.family]
    scored = []
    for it in items:
        cand_title = it.get("title", "") or ""
        sim = title_similarity(query_title, cand_title)
        cand_surnames: list[str] = []
        for a in it.get("authors") or []:
            name = a.get("name", "") or ""
            if name:
                parts = name.rsplit(" ", 1)
                cand_surnames.append(parts[1] if len(parts) == 2 else name)
        author_ok = (
            not query_surnames
            or surname_overlap(query_surnames, cand_surnames)
        )
        if not author_ok:
            sim *= 0.5
        cand_year = it.get("year")
        year_bonus = 0.0
        if query_year and cand_year:
            diff = abs(query_year - cand_year)
            if diff == 0:
                year_bonus = 0.05
            elif diff == 1:
                year_bonus = 0.02
        scored.append((sim + year_bonus, it))
    scored.sort(key=lambda x: -x[0])
    if not scored or scored[0][0] < _MIN_SIMILARITY:
        return None
    return scored[0][1]


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
