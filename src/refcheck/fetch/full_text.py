from __future__ import annotations
import io
import re
from dataclasses import dataclass
from typing import Any
import httpx
from pypdf import PdfReader


_ARXIV_API = "http://export.arxiv.org/api/query"
_EPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
_EPMC_FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest/{src}/{pmcid}/fullTextXML"


@dataclass
class FullTextResult:
    text: str | None
    source: str  # "arxiv" | "europepmc" | "unpaywall" | "none"
    url: str | None = None


class FullTextFetcher:
    """Fallback chain: arXiv → Europe PMC → Unpaywall.

    Each tier failure is silent; if all fail, returns ``text=None``. Designed
    so the agent's content verifier can call this once per citation and either
    get full body or fall back to the abstract already in its prompt.
    """

    def __init__(self, *, unpaywall: Any | None, timeout: float = 30.0):
        self._unpaywall = unpaywall
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch(
        self,
        *,
        doi: str | None,
        title: str,
        year: int | None,
    ) -> FullTextResult:
        if title:
            text, url = await self._try_arxiv(title, year)
            if text:
                return FullTextResult(text=text, source="arxiv", url=url)

        if doi or title:
            text, url = await self._try_europepmc(doi=doi, title=title)
            if text:
                return FullTextResult(text=text, source="europepmc", url=url)

        if doi and self._unpaywall is not None:
            try:
                pdf_url = await self._unpaywall.oa_pdf_url(doi)
            except Exception:
                pdf_url = None
            if pdf_url:
                text = await self._download_pdf(pdf_url)
                if text:
                    return FullTextResult(text=text, source="unpaywall", url=pdf_url)

        return FullTextResult(text=None, source="none", url=None)

    async def _try_arxiv(
        self, title: str, year: int | None
    ) -> tuple[str | None, str | None]:
        try:
            params = {"search_query": f"ti:{title}", "max_results": "3"}
            r = await self._client.get(_ARXIV_API, params=params)
            if r.status_code != 200:
                return None, None
            xml = r.text
        except Exception:
            return None, None

        ids = re.findall(r"<id>(http://arxiv\.org/abs/[^<]+)</id>", xml)
        if not ids:
            return None, None
        abs_url = ids[0]
        pdf_url = abs_url.replace("/abs/", "/pdf/") + ".pdf"
        text = await self._download_pdf(pdf_url)
        return text, pdf_url

    async def _try_europepmc(
        self, *, doi: str | None, title: str
    ) -> tuple[str | None, str | None]:
        try:
            if doi:
                query = f'DOI:"{doi}"'
            else:
                query = f'TITLE:"{title}"'
            params = {
                "query": query,
                "format": "json",
                "pageSize": "3",
                "resultType": "lite",
            }
            r = await self._client.get(_EPMC_SEARCH, params=params)
            if r.status_code != 200:
                return None, None
            data = r.json()
        except Exception:
            return None, None

        results = (data.get("resultList", {}) or {}).get("result", []) or []
        for hit in results:
            pmcid = hit.get("pmcid")
            src = hit.get("source") or "MED"
            if not pmcid:
                continue
            try:
                url = _EPMC_FULLTEXT.format(src=src, pmcid=pmcid)
                rx = await self._client.get(url)
                if rx.status_code != 200:
                    continue
                text = re.sub(r"<[^>]+>", " ", rx.text)
                text = re.sub(r"\s+", " ", text).strip()
                if len(text) > 500:
                    return text, url
            except Exception:
                continue
        return None, None

    async def _download_pdf(self, url: str) -> str | None:
        try:
            r = await self._client.get(url)
            if r.status_code != 200:
                return None
            data = r.content
        except Exception:
            return None
        try:
            reader = PdfReader(io.BytesIO(data))
            parts = [p.extract_text() or "" for p in reader.pages]
            joined = "\n\n".join(parts).strip()
            return joined or None
        except Exception:
            return None
