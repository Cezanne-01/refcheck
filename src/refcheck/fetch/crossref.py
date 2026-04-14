from __future__ import annotations
from typing import Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from refcheck.schema.models import Reference, Author


BASE_URL = "https://api.crossref.org/works"


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
        # Strip URL prefix if user provided full URL DOI
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
        params: dict[str, Any] = {"query.title": title, "rows": rows}
        if authors:
            params["query.author"] = " ".join(a.family for a in authors)
        if year:
            params["filter"] = f"from-pub-date:{year},until-pub-date:{year}"
        r = await self._client.get(BASE_URL, params=params)
        r.raise_for_status()
        items = r.json().get("message", {}).get("items", [])
        if not items:
            return None
        return _to_reference(items[0])


def _to_reference(msg: dict[str, Any]) -> Reference:
    title_list = msg.get("title") or []
    title = title_list[0] if title_list else ""
    authors = [
        Author(given=a.get("given"), family=a.get("family", ""))
        for a in msg.get("author", [])
        if a.get("family")
    ]
    year: int | None = None
    date_parts = (
        msg.get("published-print") or msg.get("published-online") or msg.get("issued") or {}
    ).get("date-parts") or []
    if date_parts and date_parts[0]:
        year = int(date_parts[0][0])
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
