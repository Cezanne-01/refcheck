# Agent-Only Verification + WebSearch Backup + Real Full-Text Fetch

날짜: 2026-05-03
저자: refcheck team

## 문제

기존 파이프라인은 두 가지 큰 사용성 문제가 있다:

1. **비-에이전트(파이프라인) 모드의 false positive**
   - `_is_plausible_match`가 제목 유사도 ≥ 0.90 + 첫 저자 성 완전일치를 요구
   - 4개 학술 DB 모두 통과 못 하면 `best_match`가 비고, 곧바로 `hallucination` 판정
   - 제목 한 글자/띄어쓰기 차이만으로 실제 존재하는 논문이 "할루시네이션"으로 분류
   - 같은 워크로드를 에이전트 모드와 비-에이전트 모드 두 갈래로 유지하느라 코드 부담만 큼

2. **인용 내용 검증이 본문 없이 초록만 봄**
   - `source_fetcher`는 Unpaywall OA URL이 있을 때만 PDF를 받음
   - paywalled / OA 미등록 논문은 그대로 abstract-only
   - 에이전트의 `fetch_full_text` tool은 OA URL만 리턴, 실제 본문 다운로드를 안 함
   - 결과적으로 대부분의 인용이 `abstract_insufficient`로 떨어져 결론을 못 냄

DB miss 시 학술 DB 외 일반 웹 검색 백업도 없어서 최근 논문(2024+)·컨퍼런스 페이퍼는 놓친다.

## 목표

- **에이전트 단일 경로**로 통일하여 사용자가 LLM의 융통성 있는 판단을 항상 받게 한다
- **WebSearch 백업**(DuckDuckGo HTML, 무료, 키 불필요)으로 4개 DB miss 시에도 식별 시도
- **실제 본문 다운로드**(arXiv → Europe PMC → Unpaywall OA fallback chain)로 본문 기반 인용 검증
- 매칭 임계치 완화 + 유니코드 정규화 보강

## 비-목표

- 별도 유료 검색 API(Tavily/Serper) 통합 — 향후 옵셔널로 추가 가능하지만 이번 범위 X
- Sci-Hub 등 paywall 우회 — 법적·정책적 이유로 안 함
- Google Scholar 직접 스크래핑 — 차단 위험, DDG로 충분
- 새 UI 옵션 추가 — `use_agents` 토글 자체를 제거하므로

## 설계

### A. 비-에이전트 모드 제거

삭제 대상:
- `src/refcheck/verify/metadata.py`의 `verify_all_references` 및 헬퍼 (`_verify_single`, `_enrich_abstract`, `_is_plausible_match`, `_build_verified`, `_safe`, `TITLE_ACCEPT`, `TITLE_MAYBE`)
- `src/refcheck/verify/content.py` 전체 (비-에이전트 내용 검증)
- `src/refcheck/pipeline.py`의 `if config.use_agents:` 분기 — 항상 에이전트 호출
- `PipelineConfig.use_agents` 필드 (또는 default를 True로 두고 deprecation 유지 — **삭제 선택**)
- Streamlit UI의 "에이전트 모드" 체크박스
- CLI의 관련 옵션 (있다면)
- 비-에이전트 경로 단위 테스트 (`tests/unit/test_matching.py`는 매칭 헬퍼만 검증하므로 유지, `verify_all_references`/`verify_all_content` 자체를 모킹하는 테스트는 제거)

`verify/matching.py`는 에이전트가 자체 판단할 때도 참고 도구로 쓸 수 있어 유지.

### B. WebSearch 백업 클라이언트

새 모듈: `src/refcheck/fetch/web_search.py`

```python
class WebSearchClient:
    async def search(self, query: str, max_results: int = 5) -> list[WebSearchHit]
```

- 백엔드: DuckDuckGo HTML endpoint (`https://html.duckduckgo.com/html/`)
- HTTP only, 키 불필요, polite UA + rate limit
- 결과: title, url, snippet
- 에러 시 빈 리스트 반환 (raise 안 함 — 백업 검색이라 핵심 경로 막으면 안 됨)

메타데이터 에이전트에 새 tool `web_search` 추가:
```python
{
  "name": "web_search",
  "description": "Fallback general web search when academic DBs return nothing. "
                 "Use ONLY after trying at least 2 DBs. Returns up to 5 hits "
                 "with title/url/snippet — extract DOI/arXiv ID from results.",
  "parameters": {"query": str}
}
```

프롬프트 업데이트: DB 2개 이상 시도 후 miss면 `web_search` 호출 → DOI/arXiv ID를 발견하면 `lookup_doi_crossref` 또는 `search_*` 재시도. 그래도 못 찾으면 hallucination.

### C. 실제 Full-Text 가져오기

새 모듈: `src/refcheck/fetch/full_text.py`

```python
class FullTextFetcher:
    async def fetch(self, *, doi: str | None, title: str, year: int | None) -> FullTextResult
```

`FullTextResult`: `text: str | None`, `source: str` (e.g. "europepmc", "arxiv", "unpaywall"), `url: str | None`

Fallback 체인:
1. **arXiv**: arXiv API (`http://export.arxiv.org/api/query`)로 title 검색 → PDF URL → 다운로드 + pypdf 추출
2. **Europe PMC**: REST API (`https://www.ebi.ac.uk/europepmc/webservices/rest/search`) → fullTextIdList → fullText XML 또는 PDF
3. **Unpaywall**: 기존 `UnpaywallClient.oa_pdf_url(doi)` → PDF 다운로드 + 추출

각 단계 실패는 silent — 다음 단계로. 모두 실패면 `text=None`.

캐싱: `DiskCache`에 `fulltext:{doi or title-hash}` 키로 저장 (현재 `source_fetcher.py` 패턴 그대로).

`source_fetcher.py`가 `FullTextFetcher`를 사용하도록 리팩토링.

에이전트 tool `fetch_full_text` 실제 구현:
- `doi`로 `FullTextFetcher.fetch` 호출
- 결과 본문이 있으면 dispatcher가 자체 `source_text`도 갱신 (다음 `find_passage`에서 즉시 활용)
- 리턴: `{"full_text": str | None, "source": str, "note": str}`

`fetch_abstract` stub 제거 — 더 이상 노출하지 않음 (초록은 user prompt에 이미 들어감).

### D. 매칭 관용도 향상

`verify/matching.py`:
- `_normalize_title`에 유니코드 정규화 추가:
  - smart quotes (`'` `'` `"` `"`) → ASCII (`'` `"`)
  - en/em dash (`–` `—`) → hyphen (`-`)
  - NFKD 정규화로 액센트 분리
- `authors_match` 변경: 첫 저자 성 일치 강제 → **첫 저자 성 일치 OR 저자 집합 교집합 ≥ 1**
  - 사람이 인용에서 저자 순서를 바꾸거나, 첫 저자만 잘못 적은 케이스를 살림

에이전트가 핵심 판단을 하므로 임계치는 도구 정도로 낮춰도 안전.

### E. UI/CLI 정리

- `Streamlit` UI: "에이전트 모드" 체크박스 제거. 검증 레벨 셀렉트만 유지.
- README의 "에이전트 모드" 섹션 → "검증 동작 원리"로 통합 (간단히)

## 데이터 흐름

```
draft → ingest → extract refs/citations
                    ↓
          [METADATA AGENT per ref]
              tools: search_crossref/openalex/ss/pubmed,
                     lookup_doi_crossref, web_search (NEW), submit_final
                    ↓
          [SOURCE FETCHER per verified ref]
              FullTextFetcher: arXiv → Europe PMC → Unpaywall
                    ↓
          [CONTENT AGENT per citation]
              tools: find_passage, fetch_full_text (real), submit_final
                    ↓
                aggregate → report
```

## 테스트 전략

- 단위:
  - `WebSearchClient.search` — DDG HTML mock으로 파싱 검증
  - `FullTextFetcher` — 각 단계 mock으로 fallback 순서 검증
  - 매칭 정규화 — 유니코드 따옴표/대시 케이스
- 통합:
  - `tests/integration/test_web_search.py` — 실제 DDG 호출 (`@pytest.mark.slow`)
  - `tests/integration/test_full_text.py` — arXiv/EuropePMC 실제 호출 (`@pytest.mark.slow`)
- 회귀:
  - 기존 통합 테스트(`test_agent_metadata.py`, `test_content_verify.py`)는 그대로 통과해야 함
  - 비-에이전트 통합 테스트는 제거

## 위험·트레이드오프

- DDG 차단/레이아웃 변경 → 백업이라 핵심 경로 영향 X. 향후 SerpAPI 등 추가 가능
- arXiv/EuropePMC 다운로드 시간 증가 → concurrency semaphore 유지, 캐싱
- `use_agents` 옵션 제거 = breaking change → 별도 마이그레이션 노트 README에 명시
- 비용: 모든 검증이 에이전트 통과 → 토큰 비용 증가. 사용자가 이미 받아들인 트레이드오프
