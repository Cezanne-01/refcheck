from __future__ import annotations
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


BASE_URL = "https://api.unpaywall.org/v2"


class UnpaywallClient:
    def __init__(self, email: str, timeout: float = 10.0):
        self._email = email
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5), reraise=True)
    async def oa_pdf_url(self, doi: str) -> str | None:
        r = await self._client.get(f"{BASE_URL}/{doi}", params={"email": self._email})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        if not data.get("is_oa"):
            return None
        loc = data.get("best_oa_location") or {}
        return loc.get("url_for_pdf") or loc.get("url")
