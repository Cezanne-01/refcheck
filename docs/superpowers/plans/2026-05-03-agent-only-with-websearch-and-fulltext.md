# Agent-Only + WebSearch + Real Full-Text Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 비-에이전트 검증 경로 제거하고, DuckDuckGo 웹 검색을 메타데이터 백업으로 추가, OA 본문(arXiv/Europe PMC/Unpaywall) 실제 다운로드를 구현하여 LLM이 본문 기반으로 인용 검증을 수행하도록 한다.

**Architecture:** 에이전트 단일 경로. `WebSearchClient`(DDG HTML)와 `FullTextFetcher`(3-tier fallback)를 새 모듈로 추가. 메타데이터 에이전트는 `web_search` tool, 컨텐츠 에이전트는 진짜로 본문 받아오는 `fetch_full_text` tool을 사용. `source_fetcher`도 `FullTextFetcher`를 쓰도록 리팩토링.

**Tech Stack:** Python 3.11+, httpx, BeautifulSoup4 (DDG HTML 파싱), pypdf, pytest-asyncio, tenacity, OpenAI Python SDK.

---

## File Structure

**Create:**
- `src/refcheck/fetch/web_search.py` — DDG HTML 검색 클라이언트
- `src/refcheck/fetch/full_text.py` — arXiv→EuropePMC→Unpaywall fallback fetcher
- `tests/unit/test_web_search.py`
- `tests/unit/test_full_text.py`
- `tests/integration/test_web_search_live.py` (slow)
- `tests/integration/test_full_text_live.py` (slow)

**Modify:**
- `src/refcheck/llm/tools.py` — `web_search` tool 추가, `fetch_full_text` 실제 구현, `fetch_abstract` stub 삭제
- `src/refcheck/llm/agent.py` — (변경 불필요, 그대로 동작)
- `src/refcheck/llm/prompts/metadata_agent.md` — `web_search` 사용 가이드 추가
- `src/refcheck/llm/prompts/content_agent.md` — `fetch_full_text` 진짜 동작함을 반영
- `src/refcheck/verify/agent_metadata.py` — dispatcher에 web_search 주입
- `src/refcheck/verify/agent_content.py` — dispatcher에 full_text fetcher 주입, `set_source_text` 후 후속 find_passage 활용
- `src/refcheck/verify/matching.py` — 유니코드 정규화 추가, `authors_match` 완화
- `src/refcheck/fetch/source_fetcher.py` — `FullTextFetcher` 사용
- `src/refcheck/pipeline.py` — `use_agents` 분기 제거, web_search/full_text 클라이언트 주입
- `src/refcheck/cli.py` — web_search/full_text 클라이언트 인스턴스화 + close
- `src/refcheck/ui/widgets.py` — `use_agents` 체크박스 제거, `RunConfig.use_agents` 필드 제거
- `src/refcheck/ui/app.py` — `use_agents` 전달부 제거
- `README.md` — 에이전트 모드 토글 섹션 → 동작원리 설명으로 통합

**Delete:**
- `src/refcheck/verify/metadata.py` (전체)
- `src/refcheck/verify/content.py` (전체)
- `tests/integration/test_verify_metadata.py`
- `tests/integration/test_content_verify.py` 의 비-에이전트 부분 (또는 파일 삭제)
- `tests/integration/test_pipeline.py` 의 비-에이전트 시나리오 테스트 (use_agents=False)

---

## Task 1: WebSearchClient (DuckDuckGo HTML)

**Files:**
- Create: `src/refcheck/fetch/web_search.py`
- Create: `tests/unit/test_web_search.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_web_search.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from refcheck.fetch.web_search import WebSearchClient, WebSearchHit


SAMPLE_HTML = """
<html><body>
<div class="result">
  <a class="result__a" href="https://example.com/paper1">Title One</a>
  <a class="result__snippet">Snippet text one with DOI 10.1000/abc</a>
</div>
<div class="result">
  <a class="result__a" href="https://arxiv.org/abs/2401.12345">arXiv:2401.12345 Title Two</a>
  <a class="result__snippet">Preprint abstract</a>
</div>
</body></html>
"""


@pytest.mark.asyncio
async def test_search_parses_results():
    client = WebSearchClient()
    mock_resp = MagicMock(status_code=200, text=SAMPLE_HTML)
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "get", new=AsyncMock(return_value=mock_resp)):
        hits = await client.search("foo bar")
    assert len(hits) == 2
    assert hits[0].title == "Title One"
    assert hits[0].url == "https://example.com/paper1"
    assert "10.1000/abc" in hits[0].snippet
    await client.close()


@pytest.mark.asyncio
async def test_search_returns_empty_on_http_error():
    client = WebSearchClient()
    mock_resp = MagicMock(status_code=503)
    mock_resp.raise_for_status = MagicMock(side_effect=Exception("503"))
    with patch.object(client._client, "get", new=AsyncMock(return_value=mock_resp)):
        hits = await client.search("foo")
    assert hits == []
    await client.close()


@pytest.mark.asyncio
async def test_search_max_results_limit():
    client = WebSearchClient()
    many = "<html><body>" + (
        '<div class="result"><a class="result__a" href="https://x/{i}">T{i}</a>'
        '<a class="result__snippet">S{i}</a></div>'
    ) * 10 + "</body></html>"
    mock_resp = MagicMock(status_code=200, text=many.replace("{i}", "x"))
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "get", new=AsyncMock(return_value=mock_resp)):
        hits = await client.search("q", max_results=3)
    assert len(hits) == 3
    await client.close()
```

- [ ] **Step 2: Run tests (expect ImportError)**

Run: `pytest tests/unit/test_web_search.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement client**

```python
# src/refcheck/fetch/web_search.py
from __future__ import annotations
from dataclasses import dataclass
import httpx
from bs4 import BeautifulSoup


_DDG_URL = "https://html.duckduckgo.com/html/"
_UA = "Mozilla/5.0 (compatible; refcheck/0.1; +https://github.com/)"


@dataclass
class WebSearchHit:
    title: str
    url: str
    snippet: str


class WebSearchClient:
    """DuckDuckGo HTML search client. Free, no API key.

    Returns up to `max_results` hits. Errors silently → empty list (백업 검색이라
    에이전트 핵심 경로를 막지 않는다).
    """

    def __init__(self, timeout: float = 10.0):
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": _UA},
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def search(self, query: str, max_results: int = 5) -> list[WebSearchHit]:
        try:
            r = await self._client.post(_DDG_URL, data={"q": query})
            if r.status_code != 200:
                return []
            html = r.text
        except Exception:
            return []

        soup = BeautifulSoup(html, "html.parser")
        hits: list[WebSearchHit] = []
        for div in soup.select("div.result"):
            a = div.select_one("a.result__a")
            snip = div.select_one(".result__snippet")
            if not a or not a.get("href"):
                continue
            hits.append(WebSearchHit(
                title=a.get_text(strip=True),
                url=a["href"],
                snippet=snip.get_text(strip=True) if snip else "",
            ))
            if len(hits) >= max_results:
                break
        return hits
```

- [ ] **Step 4: Run tests (expect PASS)**

Run: `pytest tests/unit/test_web_search.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Add beautifulsoup4 to pyproject if missing**

Check `pyproject.toml` for `beautifulsoup4`. If absent, add it under `[project.dependencies]`.

- [ ] **Step 6: Commit**

```bash
git add src/refcheck/fetch/web_search.py tests/unit/test_web_search.py pyproject.toml
git commit -m "feat(fetch): add DuckDuckGo WebSearchClient backup search"
```

---

## Task 2: FullTextFetcher (arXiv → Europe PMC → Unpaywall)

**Files:**
- Create: `src/refcheck/fetch/full_text.py`
- Create: `tests/unit/test_full_text.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_full_text.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from refcheck.fetch.full_text import FullTextFetcher, FullTextResult


@pytest.mark.asyncio
async def test_fetch_returns_arxiv_when_found():
    f = FullTextFetcher(unpaywall=None)
    with patch.object(f, "_try_arxiv", new=AsyncMock(return_value=("ARXIV TEXT", "https://arxiv.org/pdf/x"))):
        result = await f.fetch(doi=None, title="Foo bar", year=2024)
    assert result.text == "ARXIV TEXT"
    assert result.source == "arxiv"


@pytest.mark.asyncio
async def test_fetch_falls_through_to_europepmc():
    f = FullTextFetcher(unpaywall=None)
    with patch.object(f, "_try_arxiv", new=AsyncMock(return_value=(None, None))), \
         patch.object(f, "_try_europepmc", new=AsyncMock(return_value=("EPMC TEXT", "https://epmc/x"))):
        result = await f.fetch(doi="10.1/x", title="t", year=None)
    assert result.text == "EPMC TEXT"
    assert result.source == "europepmc"


@pytest.mark.asyncio
async def test_fetch_falls_through_to_unpaywall():
    upw = MagicMock()
    upw.oa_pdf_url = AsyncMock(return_value="https://oa/x.pdf")
    f = FullTextFetcher(unpaywall=upw)
    with patch.object(f, "_try_arxiv", new=AsyncMock(return_value=(None, None))), \
         patch.object(f, "_try_europepmc", new=AsyncMock(return_value=(None, None))), \
         patch.object(f, "_download_pdf", new=AsyncMock(return_value="UPW TEXT")):
        result = await f.fetch(doi="10.1/x", title="t", year=None)
    assert result.text == "UPW TEXT"
    assert result.source == "unpaywall"


@pytest.mark.asyncio
async def test_fetch_returns_none_when_all_fail():
    f = FullTextFetcher(unpaywall=None)
    with patch.object(f, "_try_arxiv", new=AsyncMock(return_value=(None, None))), \
         patch.object(f, "_try_europepmc", new=AsyncMock(return_value=(None, None))):
        result = await f.fetch(doi="10.1/x", title="t", year=None)
    assert result.text is None
    assert result.source == "none"


@pytest.mark.asyncio
async def test_fetch_skips_arxiv_when_no_title_no_doi():
    f = FullTextFetcher(unpaywall=None)
    result = await f.fetch(doi=None, title="", year=None)
    assert result.text is None
```

- [ ] **Step 2: Run tests (expect FAIL — module missing)**

Run: `pytest tests/unit/test_full_text.py -v`
Expected: FAIL ImportError

- [ ] **Step 3: Implement fetcher**

```python
# src/refcheck/fetch/full_text.py
from __future__ import annotations
import io
import re
import tempfile
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

    각 단계 실패는 silent. 모두 실패하면 text=None.
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
        # 1. arXiv (title 검색)
        if title:
            text, url = await self._try_arxiv(title, year)
            if text:
                return FullTextResult(text=text, source="arxiv", url=url)

        # 2. Europe PMC
        if doi or title:
            text, url = await self._try_europepmc(doi=doi, title=title)
            if text:
                return FullTextResult(text=text, source="europepmc", url=url)

        # 3. Unpaywall
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

    async def _try_arxiv(self, title: str, year: int | None) -> tuple[str | None, str | None]:
        try:
            params = {"search_query": f"ti:{title}", "max_results": 3}
            r = await self._client.get(_ARXIV_API, params=params)
            if r.status_code != 200:
                return None, None
            xml = r.text
        except Exception:
            return None, None

        # 단순 정규식 파싱 (Atom feed)
        ids = re.findall(r"<id>(http://arxiv\.org/abs/[^<]+)</id>", xml)
        ids = [i for i in ids if "abs/" in i and "feed" not in i]
        if not ids:
            return None, None
        # 첫 결과의 PDF
        abs_url = ids[0]
        pdf_url = abs_url.replace("/abs/", "/pdf/") + ".pdf"
        text = await self._download_pdf(pdf_url)
        return text, pdf_url

    async def _try_europepmc(self, *, doi: str | None, title: str) -> tuple[str | None, str | None]:
        try:
            if doi:
                query = f'DOI:"{doi}"'
            else:
                query = f'TITLE:"{title}"'
            params = {"query": query, "format": "json", "pageSize": 3, "resultType": "lite"}
            r = await self._client.get(_EPMC_SEARCH, params=params)
            if r.status_code != 200:
                return None, None
            data = r.json()
        except Exception:
            return None, None

        for hit in (data.get("resultList", {}) or {}).get("result", []) or []:
            pmcid = hit.get("pmcid")
            src = hit.get("source") or "MED"
            if not pmcid:
                continue
            try:
                url = _EPMC_FULLTEXT.format(src=src, pmcid=pmcid)
                rx = await self._client.get(url)
                if rx.status_code != 200:
                    continue
                # XML — strip tags 단순 텍스트 추출
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
```

- [ ] **Step 4: Run tests (expect PASS)**

Run: `pytest tests/unit/test_full_text.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/fetch/full_text.py tests/unit/test_full_text.py
git commit -m "feat(fetch): add FullTextFetcher with arXiv/EuropePMC/Unpaywall fallback"
```

---

## Task 3: Update agent tools (web_search + real fetch_full_text)

**Files:**
- Modify: `src/refcheck/llm/tools.py`
- Modify: `tests/unit/test_tools_dispatcher.py` (and maybe add new tests)

- [ ] **Step 1: Add `web_search` tool to METADATA_TOOLS**

In `tools.py`, add before `SUBMIT_METADATA_FINAL`:

```python
{
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Fallback general web search (DuckDuckGo). Use ONLY after at least 2 "
            "academic DBs have returned no match. Returns up to 5 hits with "
            "title/url/snippet — extract DOI or arXiv ID from results, then "
            "call lookup_doi_crossref or search_* with the recovered identifier."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
        },
    },
},
```

- [ ] **Step 2: Wire `web_search` in MetadataToolDispatcher**

Add `web_search` to `__init__`:

```python
def __init__(
    self, *, crossref, openalex, semantic_scholar, pubmed, web_search=None,
):
    self._crossref = crossref
    self._openalex = openalex
    self._semantic = semantic_scholar
    self._pubmed = pubmed
    self._web_search = web_search
```

Add branch in `dispatch`:

```python
if name == "web_search":
    if self._web_search is None:
        return {"hits": [], "note": "web_search not configured"}
    hits = await self._web_search.search(args["query"])
    return {
        "hits": [
            {"title": h.title, "url": h.url, "snippet": h.snippet}
            for h in hits
        ],
    }
```

- [ ] **Step 3: Replace fetch_full_text stub with real implementation**

Replace `ContentToolDispatcher`:

```python
class ContentToolDispatcher:
    def __init__(
        self,
        *,
        source_text: str = "",
        full_text_fetcher=None,  # FullTextFetcher | None
    ):
        self._source_text = source_text
        self._fetcher = full_text_fetcher

    @property
    def source_text(self) -> str:
        return self._source_text

    def set_source_text(self, text: str) -> None:
        self._source_text = text

    async def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "find_passage":
            return self._find_passage(args["query"])
        if name == "fetch_full_text":
            return await self._fetch_full_text(args.get("doi"), args.get("title", ""))
        return {"error": f"unknown tool: {name}"}

    def _find_passage(self, query: str) -> dict[str, Any]:
        # 기존 그대로
        ...

    async def _fetch_full_text(self, doi: str | None, title: str) -> dict[str, Any]:
        if self._fetcher is None:
            return {"full_text": None, "note": "fetcher not configured"}
        result = await self._fetcher.fetch(doi=doi, title=title, year=None)
        if result.text:
            # 자체 source_text 갱신 — 후속 find_passage에서 즉시 활용
            self._source_text = result.text
            return {
                "full_text": result.text[:8000],  # 토큰 절약 — 앞부분만 noise 줄여서 리턴
                "source": result.source,
                "url": result.url,
                "note": "source_text 갱신됨. 이제 find_passage가 본문을 검색합니다.",
            }
        return {"full_text": None, "source": "none", "note": "본문 확보 실패"}
```

- [ ] **Step 4: Update CONTENT_TOOLS — fetch_full_text schema**

Update tool param to include `title`:

```python
{
    "type": "function",
    "function": {
        "name": "fetch_full_text",
        "description": (
            "Try to download full text via arXiv → Europe PMC → Unpaywall. "
            "Updates source_text on success so subsequent find_passage works on "
            "the full body. Returns first ~8000 chars + source identifier."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["doi", "title"],
            "properties": {
                "doi": {"type": ["string", "null"]},
                "title": {"type": "string"},
            },
        },
    },
},
```

- [ ] **Step 5: Remove `fetch_abstract` tool entirely**

Delete the tool entry from `CONTENT_TOOLS` and the dispatcher branch.

- [ ] **Step 6: Add unit tests for new tool dispatching**

Add to `tests/unit/test_tools_dispatcher.py`:

```python
@pytest.mark.asyncio
async def test_metadata_dispatcher_web_search():
    from refcheck.llm.tools import MetadataToolDispatcher
    from refcheck.fetch.web_search import WebSearchHit
    ws = MagicMock()
    ws.search = AsyncMock(return_value=[
        WebSearchHit(title="T", url="https://x", snippet="DOI 10.1/x"),
    ])
    d = MetadataToolDispatcher(
        crossref=MagicMock(), openalex=MagicMock(),
        semantic_scholar=MagicMock(), pubmed=MagicMock(),
        web_search=ws,
    )
    out = await d.dispatch("web_search", {"query": "foo"})
    assert out["hits"][0]["url"] == "https://x"


@pytest.mark.asyncio
async def test_content_dispatcher_fetch_full_text_updates_source():
    from refcheck.llm.tools import ContentToolDispatcher
    from refcheck.fetch.full_text import FullTextResult
    f = MagicMock()
    f.fetch = AsyncMock(return_value=FullTextResult(text="HELLO BODY", source="arxiv"))
    d = ContentToolDispatcher(source_text="abstract only", full_text_fetcher=f)
    out = await d.dispatch("fetch_full_text", {"doi": "10.1/x", "title": "t"})
    assert out["full_text"] == "HELLO BODY"
    assert d.source_text == "HELLO BODY"
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/unit/test_tools_dispatcher.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/refcheck/llm/tools.py tests/unit/test_tools_dispatcher.py
git commit -m "feat(llm): add web_search tool and real fetch_full_text"
```

---

## Task 4: Update agent_metadata.py and agent_content.py

**Files:**
- Modify: `src/refcheck/verify/agent_metadata.py`
- Modify: `src/refcheck/verify/agent_content.py`

- [ ] **Step 1: Inject web_search into metadata dispatcher**

In `agent_metadata.py`:

```python
from refcheck.fetch.web_search import WebSearchClient

async def verify_reference_agent(
    ref: Reference,
    *,
    openai_client: Any,
    crossref: CrossrefClient,
    openalex: OpenAlexClient,
    semantic_scholar: SemanticScholarClient,
    pubmed: PubMedClient,
    web_search: WebSearchClient | None = None,
    model: str = "gpt-5.4",
    max_turns: int = 6,
) -> VerifiedReference:
    dispatcher = MetadataToolDispatcher(
        crossref=crossref, openalex=openalex,
        semantic_scholar=semantic_scholar, pubmed=pubmed,
        web_search=web_search,
    )
    ...

# verify_all_references_agent에도 같은 파라미터 추가하여 worker에 전달
```

- [ ] **Step 2: Inject FullTextFetcher into content dispatcher**

In `agent_content.py`:

```python
from refcheck.fetch.full_text import FullTextFetcher

async def verify_citation_agent(
    citation: Citation,
    verified_ref: VerifiedReference,
    *,
    openai_client: Any,
    full_text_fetcher: FullTextFetcher | None = None,
    model: str = "gpt-5.4",
    max_turns: int = 5,
) -> Finding | None:
    ...
    dispatcher = ContentToolDispatcher(
        source_text=source_text,
        full_text_fetcher=full_text_fetcher,
    )
    ...

# verify_all_content_agent도 동일 파라미터, 더 이상 unpaywall/openalex를 직접 안 받음
```

기존 `unpaywall`/`openalex` 파라미터 제거 (FullTextFetcher 안에 unpaywall이 캡슐화됨).

- [ ] **Step 3: Update prompts**

`metadata_agent.md`에 추가 (기존 4단계 뒤에):

```
8. If all 4 DBs return nothing → call `web_search(query)` ONCE with title+first author+year.
   If results contain a DOI or arXiv ID → call lookup_doi_crossref or search_* with it.
   If web_search also returns nothing relevant → declare hallucination.
```

`content_agent.md` 수정 (Strategy 3번):

```
3. If source is abstract-only and the abstract doesn't clearly support/contradict the claim,
   call `fetch_full_text(doi, title)` to download the actual paper. After it succeeds,
   the source_text is replaced with the full body — call `find_passage` again to search the body.
```

- [ ] **Step 4: Commit**

```bash
git add src/refcheck/verify/agent_metadata.py src/refcheck/verify/agent_content.py src/refcheck/llm/prompts/
git commit -m "feat(agents): inject web_search and full-text fetcher into agents"
```

---

## Task 5: Loosen matching (unicode normalization + author leniency)

**Files:**
- Modify: `src/refcheck/verify/matching.py`
- Modify: `tests/unit/test_matching.py`

- [ ] **Step 1: Write failing tests for unicode normalization**

```python
# Add to tests/unit/test_matching.py
def test_title_similarity_ignores_smart_quotes():
    a = "Children's outcomes — a study"
    b = "Children's outcomes - a study"
    assert title_similarity(a, b) >= 0.95


def test_authors_match_first_author_swap():
    from refcheck.schema.models import Author
    a = [Author(family="Kim"), Author(family="Lee")]
    b = [Author(family="Lee"), Author(family="Kim")]
    # 같은 그룹이지만 첫 저자 다름 → 너그러운 매칭에서는 통과
    assert authors_match(a, b) is True
```

- [ ] **Step 2: Run tests (expect FAIL)**

Run: `pytest tests/unit/test_matching.py -v`
Expected: FAIL (smart quote test, swap test)

- [ ] **Step 3: Implement**

In `matching.py`, replace `_normalize_title`:

```python
import unicodedata

_SMART_TO_ASCII = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "−": "-",
    " ": " ", " ": " ", "​": "",
})


def _normalize_title(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(_SMART_TO_ASCII)
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s
```

Replace `authors_match`:

```python
def authors_match(a: list[Author], b: list[Author]) -> bool:
    """Lenient: author surname sets must overlap (≥1 common surname).

    이전: 첫 저자 성 일치 강제 → 인용에서 저자 순서가 바뀌거나 첫 저자가
    살짝 틀린 경우 false negative. 이제는 한 명이라도 겹치면 통과.
    최종 판단은 LLM 에이전트가 함.
    """
    if not a or not b:
        return False
    set_a = {_norm_surname(x.family) for x in a if x.family}
    set_b = {_norm_surname(x.family) for x in b if x.family}
    return bool(set_a & set_b)
```

- [ ] **Step 4: Run tests (expect PASS)**

Run: `pytest tests/unit/test_matching.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/verify/matching.py tests/unit/test_matching.py
git commit -m "fix(verify): loosen matching with unicode normalization and lenient authors"
```

---

## Task 6: Refactor source_fetcher to use FullTextFetcher

**Files:**
- Modify: `src/refcheck/fetch/source_fetcher.py`

- [ ] **Step 1: Replace internals**

```python
# src/refcheck/fetch/source_fetcher.py
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

    return await asyncio.gather(*(_worker(v) for v in verified))


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
    if cached:
        vref.full_text = cached.get("text")
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
```

- [ ] **Step 2: Update integration test if it directly mocks unpaywall**

Run existing tests:

```bash
pytest tests/integration/test_source_fetcher.py -v
```

Update mocks to use FullTextFetcher mock if necessary.

- [ ] **Step 3: Commit**

```bash
git add src/refcheck/fetch/source_fetcher.py tests/integration/test_source_fetcher.py
git commit -m "refactor(fetch): source_fetcher uses FullTextFetcher chain"
```

---

## Task 7: Pipeline + CLI + UI cleanup (remove use_agents)

**Files:**
- Modify: `src/refcheck/pipeline.py`
- Modify: `src/refcheck/cli.py`
- Modify: `src/refcheck/ui/widgets.py`
- Modify: `src/refcheck/ui/app.py`
- Delete: `src/refcheck/verify/metadata.py`
- Delete: `src/refcheck/verify/content.py`

- [ ] **Step 1: Update pipeline.py**

```python
# 추가/수정 부분만 발췌
from refcheck.fetch.web_search import WebSearchClient
from refcheck.fetch.full_text import FullTextFetcher
from refcheck.fetch.source_fetcher import fetch_sources
from refcheck.verify.agent_metadata import verify_all_references_agent
from refcheck.verify.agent_content import verify_all_content_agent
# verify.metadata, verify.content import 제거


@dataclass
class PipelineConfig:
    cache_dir: Path
    verification_level: Literal["fast", "precise", "ultra"] = "precise"
    concurrency: int = 5
    max_references: int = 200
    warn_references: int = 100
    agent_max_turns: int = 6
    # use_agents 필드 제거


async def run_pipeline(
    *,
    draft_text: str,
    draft_title: str,
    config: PipelineConfig,
    llm: LLMClient,
    crossref: CrossrefClient,
    openalex: OpenAlexClient,
    semantic_scholar: SemanticScholarClient,
    pubmed: PubMedClient,
    unpaywall: UnpaywallClient,
    web_search: WebSearchClient,
    full_text_fetcher: FullTextFetcher,
    progress: ProgressReporter | None = None,
) -> DraftReport:
    ...
    reporter.start(Stage.VERIFY_METADATA, total=len(references), message="에이전트로 메타데이터 검증")
    openai_raw = llm._client  # type: ignore[attr-defined]
    verified = await verify_all_references_agent(
        references,
        openai_client=openai_raw,
        crossref=crossref, openalex=openalex,
        semantic_scholar=semantic_scholar, pubmed=pubmed,
        web_search=web_search,
        model=models["content"],
        max_turns=config.agent_max_turns,
        concurrency=min(3, config.concurrency),
    )
    reporter.finish(Stage.VERIFY_METADATA)

    reporter.start(Stage.FETCH_SOURCES, total=len(verified), message="전문·초록 확보")
    verified = await fetch_sources(
        verified,
        full_text_fetcher=full_text_fetcher,
        cache_dir=config.cache_dir,
        concurrency=config.concurrency,
    )
    reporter.finish(Stage.FETCH_SOURCES)

    reporter.start(Stage.VERIFY_CONTENT, total=len(citations), message="에이전트로 인용 내용 검증")
    findings = await verify_all_content_agent(
        citations, verified,
        openai_client=openai_raw,
        full_text_fetcher=full_text_fetcher,
        model=models["content"],
        max_turns=config.agent_max_turns,
        concurrency=min(3, config.concurrency),
    )
    reporter.finish(Stage.VERIFY_CONTENT, message=f"{len(findings)}개 발견사항")
    ...
```

- [ ] **Step 2: Update CLI to instantiate new clients**

```python
# cli.py 추가
from refcheck.fetch.web_search import WebSearchClient
from refcheck.fetch.full_text import FullTextFetcher

# main() 안에서
web_search = WebSearchClient()
full_text_fetcher = FullTextFetcher(unpaywall=unpaywall)

# run_pipeline 호출에 web_search, full_text_fetcher 전달
# finally 절에 close 추가
await web_search.close()
await full_text_fetcher.close()
```

- [ ] **Step 3: Strip use_agents from UI**

`widgets.py` `RunConfig`:

```python
@dataclass
class RunConfig:
    verification_level: str
    cache_dir: Path
    # use_agents 필드 제거
```

`render_config` 함수에서 `st.checkbox` 호출 제거.

`app.py` line 118: `use_agents=config.use_agents` 라인 제거.

- [ ] **Step 4: Delete legacy modules**

```bash
rm src/refcheck/verify/metadata.py src/refcheck/verify/content.py
```

또한 `verify/__init__.py`에서 export 제거 (있으면).

- [ ] **Step 5: Delete legacy tests**

```bash
rm tests/integration/test_verify_metadata.py
rm tests/integration/test_content_verify.py
```

`tests/integration/test_pipeline.py`의 `use_agents=True`는 이제 기본 동작이므로 토큰만 제거. `use_agents=False` 시나리오 테스트가 있으면 삭제.

- [ ] **Step 6: Run full test suite**

```bash
pytest -x --ignore=tests/e2e
```

수정 필요한 테스트 (mocks 등) 인라인 수정.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: remove non-agent path, wire web_search and full-text into pipeline"
```

---

## Task 8: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace "에이전트 모드" 섹션**

기존 "## 🤖 에이전트 모드 (정밀 검증)" 섹션 (74~96줄)을 다음으로 교체:

```markdown
## 검증 동작 방식

이 도구는 **항상 LLM 에이전트 기반**으로 동작합니다. 파이프라인은 다음 단계를 거칩니다:

1. **메타데이터 에이전트** — 각 참고문헌마다 4개 학술 DB(Crossref, OpenAlex, Semantic Scholar, PubMed)를 순차 조회. 모두 miss 시 **DuckDuckGo 백업 검색**으로 DOI/arXiv ID를 추출 후 재조회. 그래도 못 찾으면 hallucination.
2. **본문 확보** — DOI/제목으로 **arXiv → Europe PMC → Unpaywall** 순으로 OA 본문 다운로드. 실패 시 초록만으로 진행.
3. **컨텐츠 에이전트** — 본문(없으면 초록)을 검색하여 인용이 실제로 뒷받침되는지 판정. 초록만으로 부족하면 에이전트가 직접 `fetch_full_text`를 호출해 본문을 받아옵니다.

비용·시간 (45개 참고문헌 기준):
- fast: ~$8~12, 5~8분
- precise: ~$15~25, 8~15분 — 기본
- ultra: ~$30~50, 15~25분
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README to reflect agent-only flow"
```

---

## Task 9: Verification + final tests

- [ ] **Step 1: Full test run**

```bash
pytest -x --ignore=tests/e2e -v
```

Expected: all green

- [ ] **Step 2: Smoke test imports**

```bash
python -c "from refcheck.pipeline import run_pipeline, PipelineConfig; print('ok')"
python -c "from refcheck.fetch.web_search import WebSearchClient; print('ok')"
python -c "from refcheck.fetch.full_text import FullTextFetcher; print('ok')"
```

- [ ] **Step 3: Verify no dead imports**

```bash
grep -rn "verify_all_references\b\|verify_all_content\b\|use_agents" src/ tests/ --include="*.py" | grep -v "_agent"
```

Expected: empty (or only inside docstrings/comments)

- [ ] **Step 4: Final commit if any cleanup**

```bash
git status
git add -A && git commit -m "chore: cleanup post-refactor" || echo "nothing to commit"
```
