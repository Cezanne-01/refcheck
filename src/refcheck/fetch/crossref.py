from __future__ import annotations
from typing import Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from refcheck.schema.models import Reference, Author
from refcheck._match import title_similarity, surname_overlap


BASE_URL = "https://api.crossref.org/works"

# Below this similarity, we treat the result as not the cited paper.
# Set low to allow heavy typos (e.g. wrong subtitle) but avoid completely unrelated hits.
_MIN_SIMILARITY = 0.40


class CrossrefClient:
    def __init__(self, user_agent: str = "refcheck/0.1 (mailto:unknown)", timeout: float = 10.0):
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5), reraise=True)
    async def lookup_doi(self, doi: str) -> Reference | None:
        normalized = (
            doi.removeprefix("https://doi.org/")
            .removeprefix("http://doi.org/")
            .removeprefix("doi:")
        )
        r = await self._client.get(f"{BASE_URL}/{normalized}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        msg = r.json().get("message")
        return _to_reference(msg) if msg else None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5), reraise=True)
    async def search(
        self,
        *,
        title: str,
        authors: list[Author],
        year: int | None,
        rows: int = 5,
    ) -> Reference | None:
        """Search Crossref by title + authors, optionally year.

        Strategy: do NOT filter strictly by year up front — user-cited years
        are often wrong (off by 1, or wholesale incorrect). Year is used to
        rank candidates after the fact. Picks the best title-similarity
        candidate (also requiring ≥1 author surname overlap when authors
        are provided), returns ``None`` if even the best is below
        ``_MIN_SIMILARITY``.
        """
        items = await self._search_request(title=title, authors=authors, rows=rows)
        if not items:
            return None
        best = _best_match(
            items, query_title=title, query_authors=authors, query_year=year,
        )
        return _to_reference(best) if best else None

    async def _search_request(
        self, *, title: str, authors: list[Author], rows: int,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"query.title": title, "rows": rows}
        if authors:
            params["query.author"] = " ".join(a.family for a in authors if a.family)
        r = await self._client.get(BASE_URL, params=params)
        r.raise_for_status()
        return r.json().get("message", {}).get("items", []) or []


def _best_match(
    items: list[dict[str, Any]],
    *,
    query_title: str,
    query_authors: list[Author],
    query_year: int | None,
) -> dict[str, Any] | None:
    """Pick the candidate with highest title similarity, breaking ties by year."""
    query_surnames = [a.family for a in query_authors if a.family]
    scored = []
    for it in items:
        cand_title = (it.get("title") or [""])[0]
        sim = title_similarity(query_title, cand_title)
        cand_surnames = [a.get("family", "") for a in (it.get("author") or [])]
        author_ok = (
            not query_surnames
            or surname_overlap(query_surnames, cand_surnames)
        )
        if not author_ok:
            sim *= 0.5  # heavy penalty if no author overlap
        # Year proximity bonus (small)
        cand_year = _extract_year(it)
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


def _extract_year(msg: dict[str, Any]) -> int | None:
    date_parts = (
        msg.get("published-print") or msg.get("published-online") or msg.get("issued") or {}
    ).get("date-parts") or []
    if date_parts and date_parts[0]:
        try:
            return int(date_parts[0][0])
        except (ValueError, TypeError):
            return None
    return None


def _to_reference(msg: dict[str, Any]) -> Reference:
    title_list = msg.get("title") or []
    title = title_list[0] if title_list else ""
    authors = [
        Author(given=a.get("given"), family=a.get("family", ""))
        for a in msg.get("author", [])
        if a.get("family")
    ]
    year = _extract_year(msg)
    journal_list = msg.get("container-title") or []
    return Reference(
        id="canonical",
        authors=authors,
        year=year,
        title=title,
        journal=journal_list[0] if journal_list else None,
        volume=msg.get("volume"),
        issue=msg.get("issue"),
        pages=msg.get("page"),
        doi=msg.get("DOI"),
        raw_text="",
        style_detected="unknown",
    )
