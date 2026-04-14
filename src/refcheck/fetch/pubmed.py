from __future__ import annotations
from dataclasses import dataclass
from xml.etree import ElementTree as ET
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from refcheck.schema.models import Reference, Author


ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


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
        query_parts = [f'"{title}"[Title]']
        if authors:
            query_parts.append(f"{authors[0].family}[Author]")
        if year:
            query_parts.append(f"{year}[PDAT]")
        params = {"db": "pubmed", "term": " AND ".join(query_parts), "retmax": "1", "retmode": "xml"}
        r = await self._client.get(ESEARCH, params=params)
        r.raise_for_status()
        ids = [e.text for e in ET.fromstring(r.text).findall(".//Id") if e.text]
        if not ids:
            return None
        return await self._fetch(ids[0])

    async def _fetch(self, pmid: str) -> PubMedResult | None:
        r = await self._client.get(
            EFETCH,
            params={"db": "pubmed", "id": pmid, "retmode": "xml"},
        )
        r.raise_for_status()
        root = ET.fromstring(r.text)
        article = root.find(".//PubmedArticle")
        if article is None:
            return None
        return _parse_article(article)


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
