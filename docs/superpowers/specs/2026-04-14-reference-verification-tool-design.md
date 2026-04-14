# Reference Verification Tool — 설계 문서

- **작성일**: 2026-04-14
- **대상**: LLM이 작성한 학술 문서 초안의 참고문헌·인용 검증
- **구현 플랫폼**: Python + Streamlit
- **주 사용 도메인**: 의학 논문 (범용 학술 문서 지원)

---

## 1. 목적 및 배경

LLM(예: ChatGPT, Claude)으로 학술 문서 초안을 작성할 때 다음 유형의 오류가 반복적으로 발생한다.

1. **참고문헌 환각** — 존재하지 않는 가짜 논문 생성
2. **메타데이터 오류** — 실제 논문이지만 연도/저널/저자/권·페이지가 잘못됨
3. **인용 내용 불일치** — 인용한 논문의 실제 내용과 본문의 주장이 다름 (출처 뒤바꿈, 수치 왜곡 등)
4. **맥락 부적절** — 원문이 해당 주장을 지지하지만 맥락(시점·집단·방법론)이 부적절

본 도구는 위 4가지를 자동 검증하고, 심각도별·근거 기반 리포트를 생성한다.

### 비목표 (Non-goals)

- 초안 자동 수정 (제안만 제공, 수정은 사용자 몫)
- 표절 검사 (의도적 표절은 범위 밖)
- 스캔 PDF의 OCR (MVP에서는 텍스트 레이어 있는 PDF만)
- 한국어 원문 논문 검증 (주 타깃은 영문 국제 논문 DB 기반)

---

## 2. 전체 아키텍처

단방향 파이프라인, 각 단계는 독립 단위로 테스트 가능.

```
[Streamlit UI]
      │
      ▼
[1. Ingestion]         PDF/텍스트 → 정규화된 본문 + 참고문헌 섹션
      │
      ▼
[2. Extraction]        LLM(gpt-5.4-mini): references[], citations[]
      │
      ▼
[3. Metadata Verify]   Crossref/OpenAlex/Semantic Scholar/PubMed
      │                → 🔴 환각 / 🟠 메타데이터 오류 / ❓ 불명 판정
      ▼
[4. Source Fetch]      Unpaywall + OpenAlex → 초록·전문 확보
      │                → 🔒 접근불가 / ⚪ 부분검증 판정
      ▼
[5. Content Verify]    LLM(gpt-5.4 Thinking): 주장 vs 원문 대조
      │                → 🟡 내용 불일치 / 🟢 맥락 약함 / ✅ 검증 판정
      ▼
[6. Report]            심각도별 리포트 + MD/PDF/JSON 다운로드
```

### 핵심 설계 원칙

- **단계별 결과 캐싱** — 중간에 끊겨도 이어서 재개 가능. 재검증 시 변한 단계부터만 재실행.
- **LLM 호출 최소화** — 파싱은 저렴한 모델(`gpt-5.4-mini`), 의미 판정만 추론 모델(`gpt-5.4 Thinking`).
- **순수 함수 지향** — 각 단계는 입력→출력 명확, 독립 단위 테스트 가능.
- **비동기 병렬 처리** — 외부 API 호출·LLM 호출은 asyncio + Semaphore로 동시성 제어.
- **근거 기반 판정** — LLM 판정 시 원문 발췌(`source_evidence_quote`)를 강제, 원문에 실제 존재하는지 코드로 검증.

---

## 3. 검증 결과 분류 체계

### 상태 카테고리

| 아이콘 | 상태 | 의미 |
|---|---|---|
| ✅ | 검증됨 | 메타데이터 일치 + 초록/전문으로 인용 내용·맥락 확인 완료 |
| 🔴 | 환각 의심 | 어떤 DB에도 해당 논문 없음 |
| 🟠 | 메타데이터 오류 | 논문은 존재하나 연도/저널/저자/페이지 등 불일치 |
| 🟡 | 인용 내용 불일치 | 본문 주장과 원문 내용이 맞지 않음 |
| 🟢 | 맥락 약함 | 주장이 완전히 틀리진 않지만 맥락이 부정확 |
| ⚪ | 부분 검증 | 초록 기반으로만 판정, 전문 확인 불가 |
| 🔒 | 접근 불가 | 논문 존재·메타데이터 확인됨, 전문은 paywall |
| ❓ | 확인 불가 | 일부 매칭은 있으나 확정 불가 (수동 확인 권장) |

### 🟡 인용 내용 불일치 세부 유형

| 유형 | 예시 |
|---|---|
| 완전 뒤바뀜 | 인용 논문이 해당 주제를 아예 다루지 않음 |
| 주장 반전 | 원문 "효과 없음" → 초안 "효과 있음" |
| 수치 왜곡 | p<.001 → p<.01, 37% → 27% |
| 인과/상관 혼동 | 원문 "연관성 관찰" → 초안 "A가 B를 유발" |
| 과일반화 | 원문 "특정 집단" → 초안 조건 삭제 일반화 |
| 강도 왜곡 | 원문 "시사/가능성" → 초안 "입증/확립" |
| 선택적 인용 | 긍정 결과만 인용, 한계·반대 증거 생략 |

### 🟢 맥락 약함 세부 유형

| 유형 | 예시 |
|---|---|
| 시점 부적절 | 메타분석이 뒤집었는데 옛 primary study만 인용 |
| 집단 부적절 | 동물 연구를 인간 임상 주장 근거로 |
| 방법론 부적절 | case report를 치료 효과 근거로 |
| 약한 지지 | 원문이 언급은 하지만 주 결론이 아님 |
| **재인용 체인 (indirect citation)** | 본문이 논문 A를 인용했으나, A는 해당 주장을 직접 하지 않고 논문 C를 재인용한 경우. primary source 누락 |

### Finding 구조

각 문제는 근거 중심으로 다음 필드 포함:

- `citation_id`, `reference_id`
- `category`, `error_type`
- `severity` (1~5), `confidence` (high/medium/low)
- `draft_claim_quote` — 초안에서 문제가 된 문장
- `source_evidence_quote` — 원문에서 글자 그대로 발췌 (코드로 존재 검증)
- `explanation` — 왜 문제인지 서술
- `suggestion` — 수정 제안 (선택)

---

## 4. 컴포넌트 상세

### 4-1. Ingestion (`ingest/`)

- `pdf_reader.py` — pdfplumber 우선, 실패 시 pypdf fallback. 2단·각주·footer 제거.
- `text_normalizer.py` — 유니코드 NFC, 공백/개행 정리, ligature(ﬁ→fi) 복원.
- **출력**: `{"body_text": str, "raw_refs_section": str}` — 참고문헌 섹션 1차 분리.

### 4-2. Extraction (`extract/`) — **LLM: gpt-5.4-mini**

- `reference_parser.py` — 참고문헌 섹션을 구조화 JSON으로. 스타일 자동 감지 (APA/Vancouver/Nature/Chicago/IEEE).
- `citation_extractor.py` — 본문에서 in-text citation 위치·원문·문맥 추출.
- **핵심 프롬프트 원칙**:
  - `response_format=json_schema` 강제
  - "확신 없으면 null" 명시
  - 구조화 출력 실패 시 최대 3회 재시도

### 4-3. Metadata Verify (`verify/metadata.py`) — API only

- **조회 순서**: DOI 있으면 Crossref → 없으면 제목+저자+연도로 Crossref → OpenAlex → Semantic Scholar → PubMed.
- **필드별 매칭 기준**:

| 필드 | 매칭 기준 | 불일치 시 |
|---|---|---|
| 연도 | 정확 일치 | 🟠 (preprint/published 케이스는 정보성 finding) |
| DOI | 정확 일치 (있는 경우) | 🟠 |
| 제목 | 정규화 후 유사도 ≥ 0.90 (Jaccard + Levenshtein) | 0.70~0.90 → ❓, <0.70 → 🔴/❓ |
| 저자 | 성(surname) 집합 일치, 첫 저자 필수 | 🟠 |
| 저널 | 정규화 후 일치 (약어/풀네임 동등 매핑) | 🟠 |
| 권·페이지 | 정확 일치 | 🟠 (낮은 심각도) |

- **preprint/published 특수 케이스**: 저자·제목 일치 + 연도만 1년 차이 → `error_type: "preprint_vs_published"`, severity 1 (정보성).

### 4-4. Source Fetch (`fetch/`)

- **초록**: OpenAlex / Semantic Scholar / PubMed abstract.
- **전문**: Unpaywall로 OA 판정 → OA면 PDF URL 다운로드 → 텍스트 추출.
- **Paywall 처리**: 초록만 있으면 `access_level: "abstract_only"` + ⚪. 초록도 없으면 🔒.
- **로컬 캐시**: DOI 해시로 디스크 저장. `.cache/papers/<doi_hash>.json`.

### 4-5. Content Verify (`verify/content.py`) — **LLM: gpt-5.4 Thinking**

- **인용당 1회 호출** (초정밀 모드는 2회 self-consistency).
- **프롬프트 구성**:
  - System: 의학 논문 편집자 페르소나 + 오류 유형 rubric + 심각도 rubric.
  - User: 인용 문장 + 주변 단락 + 원문 초록/전문(있는 만큼).
  - Output: strict JSON (`error_type`, `severity`, `confidence`, `source_evidence_quote`, `draft_claim_quote`, `explanation`, `suggestion`).
- **환각 방지**: `source_evidence_quote`는 원문에서 글자 그대로 복사. 코드로 원문 존재 확인 → 없으면 재호출 (temperature 낮춤). 2회 실패 시 `confidence: "low"` + "증거 검증 실패" 표시.
- **원문 부재 시**: 초록만 있으면 `confidence: "low"` + ⚪. 접근 불가면 content verify 스킵하고 🔒만 기록.
- **긴 전문 처리**: 인용 키워드로 원문에서 관련 단락만 추출해 전달 (미니 retrieval 단계).
- **재인용 체인 감지**: 프롬프트에 별도 지시 — "원문 A가 해당 주장을 직접 하지 않고 다른 논문 C를 인용해 주장하는 경우, `error_type: "indirect_citation_chain"`으로 분류하고 `source_evidence_quote`에 A가 C를 인용한 부분을 복사, `suggestion`에 'primary source(C) 직접 인용 권장' 기록." 전문이 있을 때만 검출 가능(초록만으론 판정 불가 → ⚪ 유지).

### 4-6. Report (`report/`)

- `html_renderer.py` — Streamlit 표시 (심각도별 expander, 근거 side-by-side, 제안).
- `markdown_exporter.py` — 공유용 .md (GitHub/Notion 호환).
- `pdf_exporter.py` — weasyprint 또는 pandoc.
- `json_exporter.py` — 전체 finding 구조 그대로.
- **요약 대시보드**: 상단에 상태별 개수 + 수동 확인 권장 리스트.
- **고정 한계 배너**: "이 도구는 보조용. 최종 판단은 사용자 책임" 명시.

---

## 5. 데이터 모델

```python
class Reference(BaseModel):
    id: str
    authors: list[Author]
    year: int | None
    title: str
    journal: str | None
    volume: str | None
    pages: str | None
    doi: str | None
    raw_text: str
    style_detected: Literal["APA", "Vancouver", "Nature", "Chicago", "IEEE", "unknown"]

class Citation(BaseModel):
    id: str
    surface: str
    ref_ids: list[str]
    char_offset: int
    containing_sentence: str
    surrounding_paragraph: str

class VerifiedReference(BaseModel):
    reference: Reference
    status: Literal["verified", "hallucination", "metadata_error", "unverifiable"]
    canonical: Reference | None
    field_diffs: dict[str, tuple[str, str]]
    access_level: Literal["full_text", "abstract_only", "paywalled", "not_found"]
    abstract: str | None
    full_text: str | None
    sources_checked: list[str]

class Finding(BaseModel):
    id: str
    citation_id: str
    reference_id: str
    category: Literal["hallucination", "metadata", "content_mismatch", "weak_context",
                      "partial_verified", "paywalled", "unverifiable"]
    error_type: str | None
    severity: int  # 1~5
    confidence: Literal["high", "medium", "low"]
    draft_claim_quote: str
    source_evidence_quote: str | None
    explanation: str
    suggestion: str | None

class DraftReport(BaseModel):
    metadata: ReportMetadata
    summary_counts: dict[str, int]
    findings: list[Finding]  # severity DESC, confidence DESC 정렬
    references: list[VerifiedReference]
    unverified_manual_review: list[str]
```

---

## 6. 파일 구조

```
src/
├── app.py                    # Streamlit entry
├── ingest/
│   ├── pdf_reader.py
│   └── text_normalizer.py
├── extract/
│   ├── reference_parser.py
│   └── citation_extractor.py
├── verify/
│   ├── metadata.py
│   └── content.py
├── fetch/
│   ├── openalex.py
│   ├── crossref.py
│   ├── pubmed.py
│   ├── semantic_scholar.py
│   ├── unpaywall.py
│   └── cache.py
├── report/
│   ├── html_renderer.py
│   ├── markdown_exporter.py
│   ├── pdf_exporter.py
│   └── json_exporter.py
├── llm/
│   ├── client.py             # OpenAI 래퍼, 재시도, 캐싱
│   └── prompts/              # 프롬프트 템플릿 (버전 관리)
└── schema/
    └── models.py
tests/
├── unit/
├── integration/
├── fixtures/
│   ├── drafts/
│   ├── api_responses/
│   ├── papers/
│   └── expected_reports/
└── e2e/
docs/superpowers/specs/
```

---

## 7. 검증 레벨 (사용자 선택)

Streamlit UI에서 "검증 수준" 드롭다운 제공.

| 레벨 | Extraction | Content Verify | 예상 비용/논문 | 예상 시간 |
|---|---|---|---|---|
| 빠른 | gpt-5.4-mini | gpt-5.4 Standard | ~$1~2 | 2~3분 |
| **정밀 (기본)** | gpt-5.4-mini | gpt-5.4 Thinking | ~$3~5 | 5~8분 |
| 초정밀 | gpt-5.4 Standard | gpt-5.4 Pro + self-consistency (2회) | ~$8~12 | 10~15분 |

비용 추적: 호출마다 input/output 토큰 기록 → 리포트 하단에 총 비용 표시.

---

## 8. 오류 처리 · 엣지 케이스

### 입력
- 스캔 PDF: 텍스트 추출 0자 감지 → "OCR 필요" 에러. MVP 미지원.
- 참고문헌 섹션 분리 실패 → 사용자가 수동 섹션 표시.
- 참고문헌 0개 → 조기 종료.
- 참고문헌 100~200 → 경고. 200+ → 거부.

### Extraction
- JSON 파싱 실패 → 재시도 3회 → 실패 시 `raw_text`로 남기고 "파싱 실패" 태그.
- 필드 누락 (저자만, 연도 없음) → `None` 허용, 가능한 필드로만 조회.
- 번호식 인용 `[1,2,3-5]` → `ref_ids` 다중 매핑.
- 고아 citation / 고아 reference → 별도 finding 기록.

### Metadata Verify
- API 타임아웃/rate limit → exponential backoff, 3회 재시도 후 다음 DB.
- 모든 API 장애 → 사용자에게 재실행 제안, 캐시 유지.
- DOI는 있으나 Crossref 없음 → OpenAlex DOI 조회 → 🔴.
- 제목 유사도 0.7~0.90 애매 → ❓ + 후보 표시.
- preprint/published 양쪽 존재 → published 우선, preprint 보조 정보.

### Source Fetch
- OA PDF 다운로드 실패 → 초록 fallback → ⚪.
- PDF 텍스트 추출 실패 → 초록 fallback → ⚪.
- 초록도 없음 → 🔒 + content verify 스킵.
- Unpaywall API 키 없음 → OpenAlex `open_access` 필드 대체.

### Content Verify
- `source_evidence_quote`가 원문에 없음 → 재호출 (temperature 낮춤). 2회 실패 시 `confidence: "low"`.
- 원문이 context 초과 → 인용 키워드 기반 단락 retrieval.
- 한영 혼용 (한국어 claim ↔ 영문 원문) → gpt-5.4 직접 처리, 번역 불일치는 "의역 의심" 주석.

### 비용·시간 보호
- `MAX_USD_PER_RUN` 초과 → 진행 중단, 부분 리포트 + 배너.
- 사용자 중지 → 중간 상태 보존, 다음 실행 시 "이어서?" 제안.
- OpenAI 장애 → content verify 스킵, metadata 결과만으로 리포트.

### 결과 신뢰성 배너 (고정)

> ⚠️ 이 리포트는 **보조 도구**입니다. 모든 판정은 LLM·API 출력이며 오판 가능성이 있습니다.
> 특히 다음은 최종 사용자 확인이 필수:
> - 🟡 인용 내용 불일치 / 🟢 맥락 약함 (LLM 의미 판정 기반)
> - ⚪ 부분 검증 (초록만으로 판정)
> - ❓ 확인 불가 (수동 검색 권장)
> - 🔒 접근 불가 (원문 직접 확인 필요)

---

## 9. 테스트 전략

### 계층

```
tests/
├── unit/          # 순수 함수, 외부 의존 없음
├── integration/   # 외부 API 또는 LLM 실제 호출
├── fixtures/      # 골든 데이터
└── e2e/           # 샘플 초안 → 최종 리포트
```

### 주요 케이스

**Unit** — LLM/API 없이 빠름
- 제목 유사도, 저자 매칭, 연도 매칭 (정확 일치).
- 동일 저자 같은 해 중복 → 수동 확인 finding.

**Integration — API**
- Crossref/OpenAlex 응답 `fixtures/api_responses/*.json` 저장, `responses` 라이브러리로 재생.
- 실 API는 `@pytest.mark.slow`로 주 1회.

**Integration — LLM**
- 파싱: 10개 참고문헌(스타일 혼재) → 필드 추출 정확도 ≥ 95%.
- content verify: 주입 오류 15개 케이스 → 유형 분류 정확도 ≥ 80% (3회 평균).
- 환각 방지: `source_evidence_quote`의 원문 존재성 자동 검증.

**E2E** — 골든 드래프트 3개
1. 깨끗한 초안 → ✅만.
2. 의도된 오류 주입 초안 → 해당 finding 모두 감지.
3. 실제 LLM 생성 초안 → 회귀 스냅샷.

### 골든 데이터 비교 전략

LLM 출력 비결정성 → 구조적 비교:
- 카테고리별 개수 ±1 범위.
- critical finding 유형이 top-2에 포함.
- 🔴 환각은 반드시 감지 (false negative 제로).

### 수동 평가

월 1회: 실제 투고 초안 5개 돌려 false positive / false negative 카운트. 프롬프트 수정 시 회귀 테스트 세트로 재확인.

### 개발 워크플로

- `pytest tests/unit` — 매 저장 (pre-commit hook).
- `pytest tests/integration -m "not slow"` — PR 전.
- `pytest tests/e2e` — 릴리스 전.
- `pytest -m slow` — 주 1회.

---

## 10. 범위 결정 (Scope)

**MVP 범위에 포함**
- 로컬 개인 사용 전용 (Streamlit 로컬 실행, 인증·동시성 불필요)
- 본문 언어: 한국어/영어 (gpt-5.4 기본 지원 범위)
- 재인용 체인 감지 (🟢 맥락 약함 > indirect_citation_chain, Section 4-5 참조)

**범위 외 (Out of scope)**
- 다중 사용자·공유 배포
- 한/영 외 다국어 (일본어·중국어 등)
- 회색 문헌 (정부 보고서·학위논문·preprint-only)
- 스캔 PDF의 OCR
