from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from refcheck.schema.models import Reference, Author
from refcheck._match import title_similarity, surname_overlap


BASE_URL = "https://api.openalex.org/works"

_MIN_SIMILARITY = 0.40


@dataclass
class OpenAlexResult:
    reference: Reference
    abstract: str | None
    is_oa: bool
    oa_url: str | None


class OpenAlexClient:
    def __init__(self, mailto: str | None = None, timeout: float = 10.0):
        params = f"?mailto={mailto}" if mailto else ""
        self._client = httpx.AsyncClient(
            headers={"User-Agent": f"refcheck/0.1{params}"},
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5), reraise=True)
    async def search(
        self,
        *,
        title: str,
        authors: list[Author],
        year: int | None,
    ) -> OpenAlexResult | None:
        """Search OpenAlex by title + first author.

        ``year`` is no longer used as a strict filter; we pass title+author
        as a free-text search and rank candidates by title similarity.
        """
        query_parts = [title]
        if authors:
            query_parts.append(authors[0].family)
        params = {"search": " ".join(query_parts), "per-page": "5"}
        r = await self._client.get(BASE_URL, params=params)
        r.raise_for_status()
        results = r.json().get("results", []) or []
        if not results:
            return None
        best = _best_match(
            results, query_title=title, query_authors=authors, query_year=year,
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
        cand_title = it.get("title") or ""
        sim = title_similarity(query_title, cand_title)
        cand_surnames: list[str] = []
        for ah in it.get("authorships") or []:
            name = (ah.get("author") or {}).get("display_name", "")
            if name:
                parts = name.rsplit(" ", 1)
                cand_surnames.append(parts[1] if len(parts) == 2 else name)
        author_ok = (
            not query_surnames
            or surname_overlap(query_surnames, cand_surnames)
        )
        if not author_ok:
            sim *= 0.5
        cand_year = it.get("publication_year")
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


def _to_result(item: dict[str, Any]) -> OpenAlexResult:
    authorships = item.get("authorships") or []
    authors: list[Author] = []
    for a in authorships:
        name = (a.get("author") or {}).get("display_name", "")
        if name:
            parts = name.rsplit(" ", 1)
            if len(parts) == 2:
                authors.append(Author(given=parts[0], family=parts[1]))
            else:
                authors.append(Author(family=name))

    primary_location = item.get("primary_location") or {}
    venue = primary_location.get("source") or item.get("host_venue") or {}
    biblio = item.get("biblio") or {}
    pages = None
    if biblio.get("first_page"):
        pages = biblio["first_page"]
        if biblio.get("last_page"):
            pages = f"{biblio['first_page']}-{biblio['last_page']}"

    doi = item.get("doi")
    if doi and doi.startswith("https://doi.org/"):
        doi = doi.removeprefix("https://doi.org/")

    ref = Reference(
        id="canonical",
        authors=authors,
        year=item.get("publication_year"),
        title=item.get("title", ""),
        journal=venue.get("display_name"),
        volume=biblio.get("volume"),
        issue=biblio.get("issue"),
        pages=pages,
        doi=doi,
        raw_text="",
        style_detected="unknown",
    )

    abstract = _decode_inverted_index(item.get("abstract_inverted_index"))
    oa = item.get("open_access") or {}
    return OpenAlexResult(
        reference=ref,
        abstract=abstract,
        is_oa=bool(oa.get("is_oa")),
        oa_url=oa.get("oa_url"),
    )


def _decode_inverted_index(idx: dict[str, list[int]] | None) -> str | None:
    if not idx:
        return None
    positions: list[tuple[int, str]] = []
    for word, poss in idx.items():
        for p in poss:
            positions.append((p, word))
    positions.sort()
    return " ".join(w for _, w in positions)
