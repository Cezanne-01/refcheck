from __future__ import annotations
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


BASE_URL = "https://api.unpaywall.org/v2"


class UnpaywallClient:
    """Unpaywall API 클라이언트.

    `email=None`이면 API를 호출하지 않고 모든 조회가 None을 반환한다
    (Unpaywall은 식별용 이메일을 ToS로 요구하므로 가짜 이메일 사용 금지).
    """

    def __init__(self, email: str | None, timeout: float = 10.0):
        self._email = email
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5), reraise=True)
    async def oa_pdf_url(self, doi: str) -> str | None:
        if not self._email:
            # email 없으면 OA 조회 스킵 (ToS 준수)
            return None
        r = await self._client.get(f"{BASE_URL}/{doi}", params={"email": self._email})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        if not data.get("is_oa"):
            return None
        loc = data.get("best_oa_location") or {}
        return loc.get("url_for_pdf") or loc.get("url")
