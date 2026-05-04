from __future__ import annotations
from dataclasses import dataclass
from xml.etree import ElementTree as ET
from typing import Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from refcheck.schema.models import Reference, Author
from refcheck._match import title_similarity, surname_overlap


ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

_MIN_SIMILARITY = 0.40


@dataclass
class PubMedResult:
    reference: Reference
    abstract: str | None


class PubMedClient:
    def __init__(self, timeout: float = 10.0):
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "refcheck/0.1"},
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
    ) -> PubMedResult | None:
        """Search PubMed.

        Strategy: free-text search using title + first author surname (no
        strict ``[Title]`` quoted match, no ``AND year[PDAT]``). User
        metadata (year, exact title) is often wrong; we let PubMed rank by
        relevance and then validate top-N candidates by title similarity.
        """
        # Free-text query: title + first author + (optional) year as a soft hint
        query_parts = [title]
        if authors:
            query_parts.append(authors[0].family)
        if year:
            query_parts.append(str(year))
        term = " ".join(query_parts)
        params = {
            "db": "pubmed",
            "term": term,
            "retmax": "5",
            "retmode": "xml",
            "sort": "relevance",
        }
        r = await self._client.get(ESEARCH, params=params)
        r.raise_for_status()
        ids = [e.text for e in ET.fromstring(r.text).findall(".//Id") if e.text]
        if not ids:
            return None

        # Fetch the top candidates and rank locally by title similarity
        candidates = await self._fetch_many(ids)
        if not candidates:
            return None
        return _best_match(
            candidates, query_title=title, query_authors=authors, query_year=year,
        )

    async def _fetch_many(self, pmids: list[str]) -> list[PubMedResult]:
        if not pmids:
            return []
        r = await self._client.get(
            EFETCH,
            params={"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"},
        )
        r.raise_for_status()
        try:
            root = ET.fromstring(r.text)
        except ET.ParseError:
            return []
        results: list[PubMedResult] = []
        for article in root.findall(".//PubmedArticle"):
            results.append(_parse_article(article))
        return results


def _best_match(
    candidates: list[PubMedResult],
    *,
    query_title: str,
    query_authors: list[Author],
    query_year: int | None,
) -> PubMedResult | None:
    query_surnames = [a.family for a in query_authors if a.family]
    scored = []
    for c in candidates:
        sim = title_similarity(query_title, c.reference.title)
        cand_surnames = [a.family for a in c.reference.authors if a.family]
        author_ok = (
            not query_surnames or surname_overlap(query_surnames, cand_surnames)
        )
        if not author_ok:
            sim *= 0.5
        year_bonus = 0.0
        if query_year and c.reference.year:
            diff = abs(query_year - c.reference.year)
            if diff == 0:
                year_bonus = 0.05
            elif diff == 1:
                year_bonus = 0.02
        scored.append((sim + year_bonus, c))
    scored.sort(key=lambda x: -x[0])
    if not scored or scored[0][0] < _MIN_SIMILARITY:
        return None
    return scored[0][1]


def _text(el: ET.Element | None) -> str | None:
    if el is None:
        return None
    return el.text


def _parse_article(article: ET.Element) -> PubMedResult:
    title = _text(article.find(".//ArticleTitle")) or ""
    journal = _text(article.find(".//Journal/Title"))
    year_el = article.find(".//PubDate/Year")
    year = int(year_el.text) if year_el is not None and year_el.text else None
    volume = _text(article.find(".//JournalIssue/Volume"))
    issue = _text(article.find(".//JournalIssue/Issue"))
    pages = _text(article.find(".//Pagination/MedlinePgn"))
    abstract = _text(article.find(".//Abstract/AbstractText"))

    doi = None
    for eloc in article.findall(".//ELocationID"):
        if eloc.get("EIdType") == "doi":
            doi = eloc.text
            break

    authors: list[Author] = []
    for a in article.findall(".//AuthorList/Author"):
        family = _text(a.find("LastName"))
        given = _text(a.find("ForeName"))
        if family:
            authors.append(Author(given=given, family=family))

    ref = Reference(
        id="canonical",
        authors=authors,
        year=year,
        title=title,
        journal=journal,
        volume=volume,
        issue=issue,
        pages=pages,
        doi=doi,
        raw_text="",
        style_detected="unknown",
    )
    return PubMedResult(reference=ref, abstract=abstract)
