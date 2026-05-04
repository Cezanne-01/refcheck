from __future__ import annotations
import asyncio
from pathlib import Path
from refcheck.schema.models import VerifiedReference
from refcheck.fetch.cache import DiskCache
from refcheck.fetch.full_text import FullTextFetcher
from refcheck.ingest.text_normalizer import normalize_text


async def fetch_sources(
    verified: list[VerifiedReference],
    *,
    full_text_fetcher: FullTextFetcher,
    cache_dir: Path,
    concurrency: int = 5,
) -> list[VerifiedReference]:
    cache = DiskCache(cache_dir)
    sem = asyncio.Semaphore(concurrency)

    async def _worker(vref: VerifiedReference) -> VerifiedReference:
        async with sem:
            return await _fetch_one(vref, full_text_fetcher, cache)

    return list(await asyncio.gather(*(_worker(v) for v in verified)))


async def _fetch_one(
    vref: VerifiedReference,
    fetcher: FullTextFetcher,
    cache: DiskCache,
) -> VerifiedReference:
    if vref.status in ("hallucination", "unverifiable"):
        return vref

    canon = vref.canonical or vref.reference
    doi = canon.doi or vref.reference.doi
    title = canon.title or vref.reference.title or ""
    year = canon.year or vref.reference.year

    cache_key = f"fulltext:{doi or title}"
    cached = cache.get(cache_key)
    if cached and cached.get("text"):
        vref.full_text = cached["text"]
        vref.access_level = "full_text"
        return vref

    result = await fetcher.fetch(doi=doi, title=title, year=year)
    if not result.text:
        vref.access_level = "abstract_only" if vref.abstract else "paywalled"
        return vref

    normalized = normalize_text(result.text)
    cache.set(cache_key, {"text": normalized})
    vref.full_text = normalized
    vref.access_level = "full_text"
    return vref
