from __future__ import annotations
import io
import re
from dataclasses import dataclass
from typing import Any
import httpx
from pypdf import PdfReader
from refcheck._match import title_similarity


_ARXIV_API = "http://export.arxiv.org/api/query"
_EPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
_EPMC_FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest/{src}/{pmcid}/fullTextXML"

# arXiv frequently returns wildly unrelated top hits when nothing actually
# matches (e.g. medical papers searched on arXiv land on whatever popular
# physics/CS preprint shares a few keywords). Reject anything below this
# title similarity to the queried title.
_ARXIV_MIN_TITLE_SIMILARITY = 0.55

# Europe PMC full-text XML must contain at least this many characters of
# stripped text to count as a real body (filters cases where only metadata
# stub XML comes back).
_EPMC_MIN_FULLTEXT_CHARS = 500


@dataclass
class FullTextResult:
    text: str | None
    source: str  # "arxiv" | "europepmc" | "unpaywall" | "none"
    url: str | None = None


class FullTextFetcher:
    """Fallback chain for full text.

    Routing is content-aware:
      - When a DOI is present (i.e. the paper is formally published) we try
        Europe PMC and Unpaywall first; arXiv preprints rarely match a DOI
        and are checked last only if both fail.
      - Without a DOI we still try Europe PMC first, then arXiv (the cited
        item may be a preprint).
      - Every retrieval is validated by title similarity. arXiv is the
        biggest historical source of false positives so the threshold there
        is the highest.
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
        # Tier 1: Europe PMC (DOI lookup is precise; without DOI uses title)
        if doi or title:
            text, url = await self._try_europepmc(doi=doi, title=title)
            if text:
                return FullTextResult(text=text, source="europepmc", url=url)

        # Tier 2: Unpaywall (only when DOI provided — gives an OA PDF URL)
        if doi and self._unpaywall is not None:
            try:
                pdf_url = await self._unpaywall.oa_pdf_url(doi)
            except Exception:
                pdf_url = None
            if pdf_url:
                text = await self._download_pdf(pdf_url)
                if text:
                    return FullTextResult(text=text, source="unpaywall", url=pdf_url)

        # Tier 3: arXiv — only if no DOI (DOI ⇒ formally published, not arXiv)
        # AND title is plausible. We always validate the retrieved title
        # against the queried title to avoid the historical bug of pulling
        # an unrelated popular preprint.
        if title and not doi:
            text, url = await self._try_arxiv(title)
            if text:
                return FullTextResult(text=text, source="arxiv", url=url)

        return FullTextResult(text=None, source="none", url=None)

    async def _try_arxiv(self, title: str) -> tuple[str | None, str | None]:
        """Search arXiv by title, validate match, then download PDF.

        Returns (text, url) only if the retrieved arXiv entry's title is
        sufficiently similar to the query title. Otherwise (None, None).
        """
        try:
            params = {"search_query": f"ti:{title}", "max_results": "5"}
            r = await self._client.get(_ARXIV_API, params=params)
            if r.status_code != 200:
                return None, None
            xml = r.text
        except Exception:
            return None, None

        # Pair up <id> and <title> entries from the Atom feed.
        entries = re.findall(
            r"<entry>(.*?)</entry>", xml, flags=re.DOTALL,
        )
        best_sim = 0.0
        best_id: str | None = None
        for entry in entries:
            id_m = re.search(r"<id>(http://arxiv\.org/abs/[^<]+)</id>", entry)
            title_m = re.search(r"<title>(.*?)</title>", entry, flags=re.DOTALL)
            if not id_m or not title_m:
                continue
            cand_title = re.sub(r"\s+", " ", title_m.group(1)).strip()
            sim = title_similarity(title, cand_title)
            if sim > best_sim:
                best_sim = sim
                best_id = id_m.group(1)

        if best_id is None or best_sim < _ARXIV_MIN_TITLE_SIMILARITY:
            return None, None

        pdf_url = best_id.replace("/abs/", "/pdf/") + ".pdf"
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
            # If we matched by title (no DOI), make sure the hit's title is
            # actually similar — Europe PMC also fuzzy-matches loosely.
            if not doi:
                hit_title = hit.get("title") or ""
                if title_similarity(title, hit_title) < 0.55:
                    continue

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
                if len(text) > _EPMC_MIN_FULLTEXT_CHARS:
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

        # Validate by both Content-Type and the PDF magic header (%PDF-).
        # Many "OA PDF" links return HTML landing pages or login walls; pypdf
        # would log "invalid pdf header" and produce garbage if we let it
        # parse those bytes. Reject early when the content clearly isn't PDF.
        ct = r.headers.get("content-type", "").lower()
        if ct and "pdf" not in ct and "octet-stream" not in ct:
            return None
        if not data.lstrip().startswith(b"%PDF-"):
            return None

        try:
            reader = PdfReader(io.BytesIO(data))
            parts = [p.extract_text() or "" for p in reader.pages]
            joined = "\n\n".join(parts).strip()
            return joined or None
        except Exception:
            return None
