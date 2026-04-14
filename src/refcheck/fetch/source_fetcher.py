from __future__ import annotations
import asyncio
import tempfile
from pathlib import Path
import httpx
from pypdf import PdfReader
from refcheck.schema.models import VerifiedReference
from refcheck.fetch.cache import DiskCache
from refcheck.fetch.unpaywall import UnpaywallClient
from refcheck.ingest.text_normalizer import normalize_text


async def fetch_sources(
    verified: list[VerifiedReference],
    *,
    unpaywall: UnpaywallClient,
    cache_dir: Path,
    concurrency: int = 5,
) -> list[VerifiedReference]:
    cache = DiskCache(cache_dir)
    sem = asyncio.Semaphore(concurrency)

    async def _worker(vref: VerifiedReference) -> VerifiedReference:
        async with sem:
            return await _fetch_one(vref, unpaywall, cache)

    return await asyncio.gather(*(_worker(v) for v in verified))


async def _fetch_one(
    vref: VerifiedReference,
    unpaywall: UnpaywallClient,
    cache: DiskCache,
) -> VerifiedReference:
    if vref.status in ("hallucination", "unverifiable"):
        return vref

    doi = (vref.canonical.doi if vref.canonical else None) or vref.reference.doi
    if not doi:
        # DOI가 없으면 Unpaywall 조회 불가. 초록 여부로 access_level 확정.
        # paywalled는 "DOI는 있지만 돈 내야 전문 열람" 상태이므로 DOI 부재는 not_found가 정확.
        vref.access_level = "abstract_only" if vref.abstract else "not_found"
        return vref

    cache_key = f"fulltext:{doi}"
    cached = cache.get(cache_key)
    if cached:
        vref.full_text = cached.get("text")
        vref.access_level = "full_text"
        return vref

    try:
        url = await unpaywall.oa_pdf_url(doi)
    except Exception:
        url = None

    if not url:
        vref.access_level = "abstract_only" if vref.abstract else "paywalled"
        return vref

    text = await _download_and_extract(url)
    if not text:
        vref.access_level = "abstract_only" if vref.abstract else "paywalled"
        return vref

    normalized = normalize_text(text)
    cache.set(cache_key, {"text": normalized})
    vref.full_text = normalized
    vref.access_level = "full_text"
    return vref


async def _download_and_extract(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            content = r.content
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as f:
            f.write(content)
            f.flush()
            reader = PdfReader(f.name)
            parts = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(parts) or None
    except Exception:
        return None
