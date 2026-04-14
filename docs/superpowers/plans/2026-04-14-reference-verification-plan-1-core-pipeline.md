# Reference Verification Tool — Plan 1: Core Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LLM이 작성한 학술 문서 초안을 입력받아 참고문헌·인용을 검증하고 JSON/Markdown 리포트를 출력하는 CLI 엔진을 구현한다. (Streamlit UI는 Plan 2에서 추가)

**Architecture:** 6단계 단방향 파이프라인 — Ingestion → Extraction → Metadata Verify → Source Fetch → Content Verify → Report. 각 단계는 독립 모듈, Pydantic 모델로 단계 간 데이터 전달. LLM 호출은 `gpt-5.4-mini`(파싱) / `gpt-5.4 Thinking`(의미 판정).

**Tech Stack:** Python 3.11+, Pydantic v2, httpx (async HTTP), OpenAI Python SDK, pdfplumber + pypdf, tenacity, pytest + respx + responses.

**Spec 참조:** [docs/superpowers/specs/2026-04-14-reference-verification-tool-design.md](../specs/2026-04-14-reference-verification-tool-design.md)

---

## 파일 구조 (Plan 1 완료 시점)

```
refcheck/
├── pyproject.toml
├── .env.example
├── src/refcheck/
│   ├── __init__.py
│   ├── __main__.py              # CLI entry: python -m refcheck
│   ├── cli.py                   # argparse CLI
│   ├── pipeline.py              # 전체 파이프라인 오케스트레이터
│   ├── schema/
│   │   ├── __init__.py
│   │   └── models.py            # 모든 Pydantic 모델
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── pdf_reader.py
│   │   ├── text_normalizer.py
│   │   └── section_splitter.py
│   ├── extract/
│   │   ├── __init__.py
│   │   ├── reference_parser.py
│   │   ├── citation_extractor.py
│   │   └── linker.py
│   ├── verify/
│   │   ├── __init__.py
│   │   ├── matching.py
│   │   ├── metadata.py
│   │   └── content.py
│   ├── fetch/
│   │   ├── __init__.py
│   │   ├── crossref.py
│   │   ├── openalex.py
│   │   ├── semantic_scholar.py
│   │   ├── pubmed.py
│   │   ├── unpaywall.py
│   │   ├── source_fetcher.py
│   │   └── cache.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py            # OpenAI 래퍼
│   │   └── prompts/
│   │       ├── reference_parser.md
│   │       ├── citation_extractor.md
│   │       └── content_verify.md
│   └── report/
│       ├── __init__.py
│       ├── aggregator.py
│       ├── json_exporter.py
│       └── markdown_exporter.py
└── tests/
    ├── unit/
    ├── integration/
    ├── fixtures/
    └── e2e/
```

---

## Task 1: 프로젝트 스캐폴딩

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `src/refcheck/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: 디렉토리 생성**

```bash
mkdir -p src/refcheck/{schema,ingest,extract,verify,fetch,llm/prompts,report}
mkdir -p tests/{unit,integration,fixtures,e2e}
touch src/refcheck/{schema,ingest,extract,verify,fetch,llm,report}/__init__.py
touch src/refcheck/__init__.py tests/__init__.py
```

- [ ] **Step 2: `pyproject.toml` 작성**

```toml
[project]
name = "refcheck"
version = "0.1.0"
description = "LLM 학술 초안 참고문헌 검증 도구"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.6",
    "openai>=1.30",
    "httpx>=0.27",
    "pdfplumber>=0.11",
    "pypdf>=4.2",
    "tenacity>=8.2",
    "python-dotenv>=1.0",
    "rapidfuzz>=3.8",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.1",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
    "responses>=0.25",
    "pytest-cov>=5.0",
    "reportlab>=4.0",  # 테스트용 PDF 생성
]

[project.scripts]
refcheck = "refcheck.cli:main"

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "live: requires live API calls (costs money)",
]
```

- [ ] **Step 3: `.env.example` 작성**

```bash
OPENAI_API_KEY=sk-...
UNPAYWALL_EMAIL=your-email@example.com
SEMANTIC_SCHOLAR_API_KEY=     # optional
MAX_USD_PER_RUN=20.0
```

- [ ] **Step 4: `.gitignore` 작성**

```
__pycache__/
*.pyc
.pytest_cache/
.coverage
dist/
build/
*.egg-info/
.venv/
.env
.cache/
htmlcov/
```

- [ ] **Step 5: 설치 검증**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -c "import refcheck; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git init
git add .
git commit -m "chore: project scaffolding"
```

---

## Task 2: 데이터 스키마 (Pydantic 모델)

**Files:**
- Create: `src/refcheck/schema/models.py`
- Test: `tests/unit/test_schema.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/unit/test_schema.py`:

```python
from refcheck.schema.models import (
    Author, Reference, Citation, VerifiedReference,
    Finding, DraftReport, ReportMetadata
)


def test_reference_accepts_none_fields():
    ref = Reference(
        id="ref_001",
        authors=[Author(given="Marc", family="Potenza")],
        year=2013,
        title="Neurobiology of gambling",
        journal=None,
        volume=None,
        pages=None,
        doi=None,
        raw_text="Potenza, M. (2013). ...",
        style_detected="APA",
    )
    assert ref.id == "ref_001"
    assert ref.authors[0].family == "Potenza"


def test_finding_severity_range():
    import pytest
    with pytest.raises(ValueError):
        Finding(
            id="f_001",
            citation_id="cit_001",
            reference_id="ref_001",
            category="content_mismatch",
            error_type="주장 반전",
            severity=6,  # out of range
            confidence="high",
            draft_claim_quote="...",
            source_evidence_quote="...",
            explanation="...",
            suggestion=None,
        )


def test_draft_report_summary_counts():
    report = DraftReport(
        metadata=ReportMetadata(
            draft_title="Test",
            processing_seconds=10.0,
            total_usd_cost=0.5,
            verification_level="precise",
        ),
        summary_counts={"verified": 5, "hallucination": 1},
        findings=[],
        references=[],
        unverified_manual_review=[],
    )
    assert report.summary_counts["hallucination"] == 1
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/unit/test_schema.py -v
```

Expected: FAIL (`ModuleNotFoundError: refcheck.schema.models`)

- [ ] **Step 3: 모델 구현**

`src/refcheck/schema/models.py`:

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class Author(BaseModel):
    model_config = ConfigDict(extra="forbid")
    given: str | None = None
    family: str


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    authors: list[Author]
    year: int | None
    title: str
    journal: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    doi: str | None = None
    raw_text: str
    style_detected: Literal["APA", "Vancouver", "Nature", "Chicago", "IEEE", "unknown"]


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    surface: str
    ref_ids: list[str]
    char_offset: int
    containing_sentence: str
    surrounding_paragraph: str


class VerifiedReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: Reference
    status: Literal["verified", "hallucination", "metadata_error", "unverifiable"]
    canonical: Reference | None = None
    field_diffs: dict[str, tuple[str | None, str | None]] = Field(default_factory=dict)
    access_level: Literal["full_text", "abstract_only", "paywalled", "not_found"] = "not_found"
    abstract: str | None = None
    full_text: str | None = None
    sources_checked: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    citation_id: str
    reference_id: str
    category: Literal[
        "hallucination", "metadata", "content_mismatch", "weak_context",
        "partial_verified", "paywalled", "unverifiable", "citation_unmatched",
    ]
    error_type: str | None = None
    severity: int = Field(ge=1, le=5)
    confidence: Literal["high", "medium", "low"]
    draft_claim_quote: str
    source_evidence_quote: str | None = None
    explanation: str
    suggestion: str | None = None


class ReportMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft_title: str
    processing_seconds: float
    total_usd_cost: float
    verification_level: Literal["fast", "precise", "ultra"]


class DraftReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metadata: ReportMetadata
    summary_counts: dict[str, int]
    findings: list[Finding]
    references: list[VerifiedReference]
    unverified_manual_review: list[str]
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/unit/test_schema.py -v
```

Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/schema/ tests/unit/test_schema.py
git commit -m "feat(schema): add Pydantic data models"
```

---

## Task 3: OpenAI LLM 클라이언트 래퍼

**Files:**
- Create: `src/refcheck/llm/client.py`
- Test: `tests/unit/test_llm_client.py`

**주요 책임:**
- OpenAI API 호출, 재시도, 비용 추적
- 구조화 응답 파싱 (strict JSON schema)
- 모델별 비용 단가 계산

- [ ] **Step 1: 실패 테스트 작성**

`tests/unit/test_llm_client.py`:

```python
from unittest.mock import AsyncMock, MagicMock
import pytest
from refcheck.llm.client import LLMClient, LLMUsage, MODEL_PRICING


@pytest.mark.asyncio
async def test_client_tracks_cost():
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content='{"ok": true}'))]
    fake_response.usage = MagicMock(prompt_tokens=1000, completion_tokens=500)
    fake_response.model = "gpt-5.4-mini"

    mock_openai = MagicMock()
    mock_openai.chat.completions.create = AsyncMock(return_value=fake_response)

    client = LLMClient(openai_client=mock_openai)
    result, usage = await client.complete_json(
        model="gpt-5.4-mini",
        system="You are a parser.",
        user="Parse this.",
        response_schema={"type": "object"},
    )

    assert result == {"ok": True}
    assert usage.prompt_tokens == 1000
    assert usage.completion_tokens == 500
    # mini: $0.40/1M input, $1.60/1M output
    expected = (1000 * 0.40 + 500 * 1.60) / 1_000_000
    assert abs(usage.cost_usd - expected) < 1e-6


def test_pricing_table_has_expected_models():
    assert "gpt-5.4-mini" in MODEL_PRICING
    assert "gpt-5.4" in MODEL_PRICING
    assert "gpt-5.4-thinking" in MODEL_PRICING
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/unit/test_llm_client.py -v
```

Expected: FAIL (`ImportError`)

- [ ] **Step 3: 구현**

`src/refcheck/llm/client.py`:

```python
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


# USD per 1M tokens — 2026-04 기준, 실제 가격은 OpenAI 페이지 확인 후 업데이트
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-5.4-mini": (0.40, 1.60),
    "gpt-5.4": (2.50, 10.00),
    "gpt-5.4-thinking": (5.00, 20.00),
    "gpt-5.4-pro": (15.00, 60.00),
}


@dataclass
class LLMUsage:
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


def _cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_price, out_price = MODEL_PRICING.get(model, (0.0, 0.0))
    return (prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000


class LLMClient:
    """OpenAI client wrapper with retry, JSON schema enforcement, cost tracking."""

    def __init__(self, openai_client: AsyncOpenAI | None = None, api_key: str | None = None):
        self._client = openai_client or AsyncOpenAI(api_key=api_key)
        self.total_usage: list[LLMUsage] = []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def complete_json(
        self,
        *,
        model: str,
        system: str,
        user: str,
        response_schema: dict[str, Any],
        temperature: float = 0.2,
    ) -> tuple[dict[str, Any], LLMUsage]:
        response = await self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": response_schema,
                },
            },
            temperature=temperature,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        usage = LLMUsage(
            model=response.model,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            cost_usd=_cost(response.model, response.usage.prompt_tokens, response.usage.completion_tokens),
        )
        self.total_usage.append(usage)
        return parsed, usage

    @property
    def total_cost_usd(self) -> float:
        return sum(u.cost_usd for u in self.total_usage)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/unit/test_llm_client.py -v
```

Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/llm/ tests/unit/test_llm_client.py
git commit -m "feat(llm): add OpenAI client wrapper with cost tracking"
```

---

## Task 4: 텍스트 정규화 모듈

**Files:**
- Create: `src/refcheck/ingest/text_normalizer.py`
- Test: `tests/unit/test_text_normalizer.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/unit/test_text_normalizer.py`:

```python
from refcheck.ingest.text_normalizer import normalize_text


def test_removes_ligatures():
    assert normalize_text("eﬃcacy") == "efficacy"
    assert normalize_text("ﬁnal") == "final"


def test_collapses_whitespace():
    assert normalize_text("hello  \t  world") == "hello world"


def test_removes_soft_hyphen_breaks():
    # PDF 줄바꿈: "neurobio-\nlogical" → "neurobiological"
    assert normalize_text("neurobio-\nlogical") == "neurobiological"


def test_preserves_paragraph_breaks():
    text = "Para 1.\n\nPara 2."
    result = normalize_text(text)
    assert "\n\n" in result


def test_nfc_normalization():
    # NFD (결합 문자) → NFC
    nfd = "한" + chr(0x1100) + chr(0x1161) + chr(0x11AB)  # 간
    result = normalize_text(nfd)
    assert "한" in result
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/unit/test_text_normalizer.py -v
```

Expected: FAIL (`ImportError`)

- [ ] **Step 3: 구현**

`src/refcheck/ingest/text_normalizer.py`:

```python
from __future__ import annotations
import re
import unicodedata


LIGATURES = {
    "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
    "ﬆ": "st", "ﬅ": "ft",
}


def normalize_text(text: str) -> str:
    """NFC 정규화 + ligature 복원 + 하이픈 줄바꿈 제거 + 공백 압축."""
    # 1. NFC
    text = unicodedata.normalize("NFC", text)
    # 2. Ligatures
    for lig, rep in LIGATURES.items():
        text = text.replace(lig, rep)
    # 3. PDF 줄바꿈으로 깨진 단어: "word-\nword" → "wordword"
    text = re.sub(r"-\n(\w)", r"\1", text)
    # 4. 여러 줄바꿈은 단락 경계(\n\n)로만 보존
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 5. 단일 줄바꿈(단락 내부)은 공백으로
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    # 6. 연속 공백 압축
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/unit/test_text_normalizer.py -v
```

Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/ingest/text_normalizer.py tests/unit/test_text_normalizer.py
git commit -m "feat(ingest): add text normalizer"
```

---

## Task 5: PDF 리더

**Files:**
- Create: `src/refcheck/ingest/pdf_reader.py`
- Test: `tests/unit/test_pdf_reader.py`
- Test fixture: `tests/fixtures/drafts/sample.pdf`

- [ ] **Step 1: 테스트용 샘플 PDF 생성**

```bash
python - <<'PY'
from pathlib import Path
from reportlab.pdfgen import canvas
fp = Path("tests/fixtures/drafts/sample.pdf")
fp.parent.mkdir(parents=True, exist_ok=True)
c = canvas.Canvas(str(fp))
c.drawString(72, 750, "Introduction")
c.drawString(72, 720, "Gambling Disorder (GD) is characterized by (Potenza, 2013).")
c.drawString(72, 690, "References")
c.drawString(72, 660, "Potenza, M. N. (2013). Neurobiology of gambling. Journal X, 12(3), 45-60.")
c.save()
print(f"Created {fp}")
PY
```

(reportlab은 Task 1에서 dev 의존성으로 이미 설치됨)

- [ ] **Step 2: 실패 테스트 작성**

`tests/unit/test_pdf_reader.py`:

```python
from pathlib import Path
import pytest
from refcheck.ingest.pdf_reader import read_pdf, PDFReadError


SAMPLE = Path(__file__).parent.parent / "fixtures" / "drafts" / "sample.pdf"


def test_reads_text_from_pdf():
    text = read_pdf(SAMPLE)
    assert "Gambling Disorder" in text
    assert "Potenza" in text


def test_raises_on_empty_or_missing_file(tmp_path):
    missing = tmp_path / "nonexistent.pdf"
    with pytest.raises(PDFReadError):
        read_pdf(missing)


def test_raises_on_image_only_pdf(tmp_path):
    # 빈 내용 (텍스트 추출 시 0자)
    from reportlab.pdfgen import canvas
    empty_pdf = tmp_path / "empty.pdf"
    c = canvas.Canvas(str(empty_pdf))
    c.showPage()  # 빈 페이지
    c.save()
    with pytest.raises(PDFReadError, match="텍스트 추출 실패"):
        read_pdf(empty_pdf)
```

- [ ] **Step 3: 테스트 실패 확인**

```bash
pytest tests/unit/test_pdf_reader.py -v
```

Expected: FAIL (`ImportError`)

- [ ] **Step 4: 구현**

`src/refcheck/ingest/pdf_reader.py`:

```python
from __future__ import annotations
from pathlib import Path
import pdfplumber
from pypdf import PdfReader


class PDFReadError(Exception):
    pass


def read_pdf(path: Path) -> str:
    """PDF → raw text. pdfplumber 우선, 실패 시 pypdf fallback."""
    if not path.exists():
        raise PDFReadError(f"파일을 찾을 수 없습니다: {path}")

    text = _try_pdfplumber(path)
    if not text.strip():
        text = _try_pypdf(path)

    if not text.strip():
        raise PDFReadError(
            "텍스트 추출 실패. 스캔 PDF(이미지만)일 가능성. "
            "텍스트 레이어가 있는 PDF로 재업로드하거나 OCR 후 시도하세요."
        )
    return text


def _try_pdfplumber(path: Path) -> str:
    try:
        with pdfplumber.open(path) as pdf:
            parts = [page.extract_text() or "" for page in pdf.pages]
        return "\n\n".join(parts)
    except Exception:
        return ""


def _try_pypdf(path: Path) -> str:
    try:
        reader = PdfReader(path)
        parts = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(parts)
    except Exception:
        return ""
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/unit/test_pdf_reader.py -v
```

Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add src/refcheck/ingest/pdf_reader.py tests/unit/test_pdf_reader.py tests/fixtures/drafts/sample.pdf
git commit -m "feat(ingest): add PDF reader with pdfplumber+pypdf fallback"
```

---

## Task 6: 참고문헌 섹션 분리기

**Files:**
- Create: `src/refcheck/ingest/section_splitter.py`
- Test: `tests/unit/test_section_splitter.py`

**책임:** 본문 텍스트에서 `References` / `참고문헌` / `Bibliography` 헤딩 이후를 참고문헌 섹션으로 분리.

- [ ] **Step 1: 실패 테스트 작성**

`tests/unit/test_section_splitter.py`:

```python
import pytest
from refcheck.ingest.section_splitter import split_body_and_references, SectionSplitError


def test_splits_on_references_heading_english():
    text = """Introduction
Gambling is bad (Potenza, 2013).

References

Potenza, M. N. (2013). ...
Balodis, I. M. (2015). ..."""
    body, refs = split_body_and_references(text)
    assert "Gambling is bad" in body
    assert "Potenza, M. N. (2013)" in refs
    assert "References" not in body


def test_splits_on_korean_heading():
    text = """서론
도박장애는 심각하다 (Potenza, 2013).

참고문헌

Potenza, M. N. (2013). ..."""
    body, refs = split_body_and_references(text)
    assert "도박장애는 심각하다" in body
    assert "Potenza, M. N. (2013)" in refs


def test_splits_on_bibliography():
    text = "Body text.\n\nBibliography\n\nFoo (2020)."
    body, refs = split_body_and_references(text)
    assert refs.startswith("Foo")


def test_raises_when_no_heading_found():
    with pytest.raises(SectionSplitError, match="참고문헌 섹션"):
        split_body_and_references("Just some text with no references heading.")


def test_case_insensitive():
    text = "Body.\n\nREFERENCES\n\nFoo (2020)."
    body, refs = split_body_and_references(text)
    assert "Foo (2020)" in refs
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/unit/test_section_splitter.py -v
```

Expected: FAIL (`ImportError`)

- [ ] **Step 3: 구현**

`src/refcheck/ingest/section_splitter.py`:

```python
from __future__ import annotations
import re


HEADINGS = [
    "References", "REFERENCES",
    "Bibliography", "BIBLIOGRAPHY",
    "참고문헌", "참고 문헌", "인용문헌",
    "문헌", "Literature Cited",
]


class SectionSplitError(Exception):
    pass


def split_body_and_references(text: str) -> tuple[str, str]:
    """본문과 참고문헌 섹션을 분리. 헤딩은 양쪽 모두에서 제거."""
    # 헤딩을 단독 줄로 등장 (앞뒤 개행 또는 문서 시작/끝)
    pattern = r"(?m)^\s*(?:{})\s*:?\s*$".format("|".join(re.escape(h) for h in HEADINGS))
    matches = list(re.finditer(pattern, text, re.IGNORECASE))

    if not matches:
        raise SectionSplitError(
            "참고문헌 섹션 헤딩을 찾을 수 없습니다. "
            "'References', '참고문헌', 'Bibliography' 등이 단독 줄로 있는지 확인하세요."
        )

    # 보통 마지막 등장이 실제 참고문헌 섹션 (Introduction에서 언급된 'references' 같은 본문 단어와 구분)
    last = matches[-1]
    body = text[: last.start()].strip()
    refs = text[last.end():].strip()

    if not refs:
        raise SectionSplitError("참고문헌 섹션이 비어있습니다.")

    return body, refs
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/unit/test_section_splitter.py -v
```

Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/ingest/section_splitter.py tests/unit/test_section_splitter.py
git commit -m "feat(ingest): add references section splitter"
```

---

## Task 7: 참고문헌 파서 (LLM)

**Files:**
- Create: `src/refcheck/llm/prompts/reference_parser.md`
- Create: `src/refcheck/extract/reference_parser.py`
- Test: `tests/integration/test_reference_parser.py`

**책임:** 참고문헌 섹션 텍스트 → `list[Reference]`. LLM에게 스타일 자동 감지 + 구조화 출력.

- [ ] **Step 1: 프롬프트 템플릿 작성**

`src/refcheck/llm/prompts/reference_parser.md`:

```markdown
You are a bibliographic parser for academic documents.

Parse the given references section into a list of structured Reference objects.
Detect the citation style (APA, Vancouver, Nature, Chicago, IEEE) automatically.

Rules:
- Extract ALL references. Do not skip any.
- If a field is missing or uncertain, use null — NEVER guess.
- `raw_text` must be the EXACT original string for each reference.
- For authors, split into given (first name/initials) and family (surname).
- `year` is a 4-digit integer, or null.
- `style_detected` must be one of: APA, Vancouver, Nature, Chicago, IEEE, unknown.
- Preserve the order from the input.

Output strictly valid JSON matching the provided schema.
```

- [ ] **Step 2: 실패 테스트 작성**

`tests/integration/test_reference_parser.py`:

```python
from unittest.mock import AsyncMock, MagicMock
import pytest
from refcheck.extract.reference_parser import parse_references
from refcheck.llm.client import LLMClient, LLMUsage


@pytest.mark.asyncio
async def test_parses_apa_references():
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.complete_json = AsyncMock(return_value=(
        {
            "references": [
                {
                    "id": "ref_001",
                    "authors": [{"given": "M. N.", "family": "Potenza"}],
                    "year": 2013,
                    "title": "Neurobiology of gambling",
                    "journal": "Current Opinion in Neurobiology",
                    "volume": "23",
                    "issue": "4",
                    "pages": "660-667",
                    "doi": None,
                    "raw_text": "Potenza, M. N. (2013). Neurobiology of gambling. Current Opinion in Neurobiology, 23(4), 660-667.",
                    "style_detected": "APA"
                }
            ]
        },
        LLMUsage(model="gpt-5.4-mini", prompt_tokens=100, completion_tokens=50, cost_usd=0.001),
    ))

    raw = "Potenza, M. N. (2013). Neurobiology of gambling..."
    refs = await parse_references(raw, llm=mock_llm)

    assert len(refs) == 1
    assert refs[0].title == "Neurobiology of gambling"
    assert refs[0].authors[0].family == "Potenza"
    assert refs[0].year == 2013
    assert refs[0].style_detected == "APA"


@pytest.mark.asyncio
async def test_assigns_sequential_ids_when_missing():
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.complete_json = AsyncMock(return_value=(
        {
            "references": [
                {"id": "", "authors": [{"family": "A"}], "year": 2020, "title": "T1",
                 "journal": None, "volume": None, "issue": None, "pages": None, "doi": None,
                 "raw_text": "A (2020). T1.", "style_detected": "APA"},
                {"id": "", "authors": [{"family": "B"}], "year": 2021, "title": "T2",
                 "journal": None, "volume": None, "issue": None, "pages": None, "doi": None,
                 "raw_text": "B (2021). T2.", "style_detected": "APA"},
            ]
        },
        LLMUsage(model="gpt-5.4-mini", prompt_tokens=100, completion_tokens=50, cost_usd=0.001),
    ))

    refs = await parse_references("...", llm=mock_llm)
    assert refs[0].id == "ref_001"
    assert refs[1].id == "ref_002"
```

- [ ] **Step 3: 테스트 실패 확인**

```bash
pytest tests/integration/test_reference_parser.py -v
```

Expected: FAIL (`ImportError`)

- [ ] **Step 4: 구현**

`src/refcheck/extract/reference_parser.py`:

```python
from __future__ import annotations
from pathlib import Path
from refcheck.schema.models import Reference, Author
from refcheck.llm.client import LLMClient


_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "reference_parser.md"


REFERENCE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["references"],
    "properties": {
        "references": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id", "authors", "year", "title", "journal",
                    "volume", "issue", "pages", "doi", "raw_text", "style_detected"
                ],
                "properties": {
                    "id": {"type": "string"},
                    "authors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["given", "family"],
                            "properties": {
                                "given": {"type": ["string", "null"]},
                                "family": {"type": "string"},
                            },
                        },
                    },
                    "year": {"type": ["integer", "null"]},
                    "title": {"type": "string"},
                    "journal": {"type": ["string", "null"]},
                    "volume": {"type": ["string", "null"]},
                    "issue": {"type": ["string", "null"]},
                    "pages": {"type": ["string", "null"]},
                    "doi": {"type": ["string", "null"]},
                    "raw_text": {"type": "string"},
                    "style_detected": {
                        "type": "string",
                        "enum": ["APA", "Vancouver", "Nature", "Chicago", "IEEE", "unknown"],
                    },
                },
            },
        },
    },
}


async def parse_references(
    raw_refs_text: str,
    *,
    llm: LLMClient,
    model: str = "gpt-5.4-mini",
) -> list[Reference]:
    system = _PROMPT_PATH.read_text(encoding="utf-8")
    result, _ = await llm.complete_json(
        model=model,
        system=system,
        user=raw_refs_text,
        response_schema=REFERENCE_SCHEMA,
    )

    refs: list[Reference] = []
    for idx, item in enumerate(result["references"], start=1):
        item_id = item["id"] or f"ref_{idx:03d}"
        refs.append(Reference(
            id=item_id,
            authors=[Author(**a) for a in item["authors"]],
            year=item["year"],
            title=item["title"],
            journal=item["journal"],
            volume=item["volume"],
            issue=item["issue"],
            pages=item["pages"],
            doi=item["doi"],
            raw_text=item["raw_text"],
            style_detected=item["style_detected"],
        ))
    return refs
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/integration/test_reference_parser.py -v
```

Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add src/refcheck/extract/reference_parser.py src/refcheck/llm/prompts/reference_parser.md tests/integration/test_reference_parser.py
git commit -m "feat(extract): add LLM-based reference parser"
```

---

## Task 8: 인용(citation) 추출기 (LLM)

**Files:**
- Create: `src/refcheck/llm/prompts/citation_extractor.md`
- Create: `src/refcheck/extract/citation_extractor.py`
- Test: `tests/integration/test_citation_extractor.py`

**책임:** 본문 텍스트 → `list[Citation]`. 각 in-text citation의 위치, 원문, 문맥 추출.

- [ ] **Step 1: 프롬프트 작성**

`src/refcheck/llm/prompts/citation_extractor.md`:

```markdown
You are an in-text citation extractor for academic documents.

Given the body text and the list of parsed references (with their IDs), find every in-text citation in the body.

For each citation, extract:
- `surface`: the literal citation string as it appears, e.g. "(Potenza, 2013)" or "[12]".
- `ref_ids`: list of Reference IDs this citation points to. A citation like "(Smith, 2020; Jones, 2021)" maps to multiple.
- `char_offset`: 0-indexed character offset of the citation's first character in the body text.
- `containing_sentence`: the full sentence that contains this citation.
- `surrounding_paragraph`: the paragraph containing this citation.

Rules:
- Be exhaustive — extract every citation, including duplicates.
- If a citation doesn't match any reference, set ref_ids to [] (it will be flagged separately).
- For numbered citations like [1,2,3-5], expand the range and map each number to the corresponding reference by position in the reference list.

Output strictly valid JSON matching the provided schema.
```

- [ ] **Step 2: 실패 테스트**

`tests/integration/test_citation_extractor.py`:

```python
from unittest.mock import AsyncMock, MagicMock
import pytest
from refcheck.extract.citation_extractor import extract_citations
from refcheck.schema.models import Reference, Author
from refcheck.llm.client import LLMClient, LLMUsage


@pytest.mark.asyncio
async def test_extracts_single_citation():
    refs = [Reference(
        id="ref_001", authors=[Author(family="Potenza")], year=2013,
        title="X", raw_text="...", style_detected="APA",
    )]
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.complete_json = AsyncMock(return_value=(
        {"citations": [{
            "id": "cit_0001",
            "surface": "(Potenza, 2013)",
            "ref_ids": ["ref_001"],
            "char_offset": 28,
            "containing_sentence": "Gambling is harmful (Potenza, 2013).",
            "surrounding_paragraph": "Gambling is harmful (Potenza, 2013).",
        }]},
        LLMUsage(model="gpt-5.4-mini", prompt_tokens=100, completion_tokens=50, cost_usd=0.001),
    ))

    body = "Gambling is harmful (Potenza, 2013)."
    cits = await extract_citations(body, refs, llm=mock_llm)

    assert len(cits) == 1
    assert cits[0].surface == "(Potenza, 2013)"
    assert cits[0].ref_ids == ["ref_001"]
```

- [ ] **Step 3: 테스트 실패 확인**

```bash
pytest tests/integration/test_citation_extractor.py -v
```

Expected: FAIL

- [ ] **Step 4: 구현**

`src/refcheck/extract/citation_extractor.py`:

```python
from __future__ import annotations
import json
from pathlib import Path
from refcheck.schema.models import Citation, Reference
from refcheck.llm.client import LLMClient


_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "citation_extractor.md"


CITATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["citations"],
    "properties": {
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "surface", "ref_ids", "char_offset",
                             "containing_sentence", "surrounding_paragraph"],
                "properties": {
                    "id": {"type": "string"},
                    "surface": {"type": "string"},
                    "ref_ids": {"type": "array", "items": {"type": "string"}},
                    "char_offset": {"type": "integer"},
                    "containing_sentence": {"type": "string"},
                    "surrounding_paragraph": {"type": "string"},
                },
            },
        },
    },
}


def _refs_summary(refs: list[Reference]) -> str:
    """LLM에게 참고문헌 ID 매핑을 보여주기 위한 요약."""
    lines = []
    for r in refs:
        authors = ", ".join(a.family for a in r.authors)
        lines.append(f"{r.id}: {authors} ({r.year}) — {r.title[:80]}")
    return "\n".join(lines)


async def extract_citations(
    body_text: str,
    references: list[Reference],
    *,
    llm: LLMClient,
    model: str = "gpt-5.4-mini",
) -> list[Citation]:
    system = _PROMPT_PATH.read_text(encoding="utf-8")
    user = (
        "REFERENCES:\n"
        f"{_refs_summary(references)}\n\n"
        "BODY TEXT:\n"
        f"{body_text}"
    )
    result, _ = await llm.complete_json(
        model=model,
        system=system,
        user=user,
        response_schema=CITATION_SCHEMA,
    )

    cits: list[Citation] = []
    for idx, item in enumerate(result["citations"], start=1):
        cits.append(Citation(
            id=item["id"] or f"cit_{idx:04d}",
            surface=item["surface"],
            ref_ids=item["ref_ids"],
            char_offset=item["char_offset"],
            containing_sentence=item["containing_sentence"],
            surrounding_paragraph=item["surrounding_paragraph"],
        ))
    return cits
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/integration/test_citation_extractor.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/refcheck/extract/citation_extractor.py src/refcheck/llm/prompts/citation_extractor.md tests/integration/test_citation_extractor.py
git commit -m "feat(extract): add LLM-based citation extractor"
```

---

## Task 9: 인용-참고문헌 매칭 검사기

**Files:**
- Create: `src/refcheck/extract/linker.py`
- Test: `tests/unit/test_linker.py`

**책임:** 고아 citation (ref_ids=[]) / 고아 reference (본문에서 안 쓰임) 탐지.

- [ ] **Step 1: 실패 테스트**

`tests/unit/test_linker.py`:

```python
from refcheck.extract.linker import check_orphans
from refcheck.schema.models import Reference, Author, Citation


def test_detects_orphan_citation():
    refs = [Reference(id="ref_001", authors=[Author(family="A")], year=2020,
                      title="T", raw_text="...", style_detected="APA")]
    cits = [Citation(id="cit_001", surface="(Unknown, 2025)", ref_ids=[],
                     char_offset=0, containing_sentence="...", surrounding_paragraph="...")]
    orphan_cits, orphan_refs = check_orphans(cits, refs)
    assert "cit_001" in orphan_cits
    assert "ref_001" in orphan_refs


def test_detects_orphan_reference():
    refs = [
        Reference(id="ref_001", authors=[Author(family="A")], year=2020,
                  title="Used", raw_text="...", style_detected="APA"),
        Reference(id="ref_002", authors=[Author(family="B")], year=2021,
                  title="Unused", raw_text="...", style_detected="APA"),
    ]
    cits = [Citation(id="cit_001", surface="(A, 2020)", ref_ids=["ref_001"],
                     char_offset=0, containing_sentence="...", surrounding_paragraph="...")]
    orphan_cits, orphan_refs = check_orphans(cits, refs)
    assert orphan_cits == []
    assert orphan_refs == ["ref_002"]


def test_all_linked():
    refs = [Reference(id="ref_001", authors=[Author(family="A")], year=2020,
                      title="T", raw_text="...", style_detected="APA")]
    cits = [Citation(id="cit_001", surface="(A, 2020)", ref_ids=["ref_001"],
                     char_offset=0, containing_sentence="...", surrounding_paragraph="...")]
    orphan_cits, orphan_refs = check_orphans(cits, refs)
    assert orphan_cits == []
    assert orphan_refs == []
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/unit/test_linker.py -v
```

Expected: FAIL

- [ ] **Step 3: 구현**

`src/refcheck/extract/linker.py`:

```python
from __future__ import annotations
from refcheck.schema.models import Reference, Citation


def check_orphans(
    citations: list[Citation],
    references: list[Reference],
) -> tuple[list[str], list[str]]:
    """고아 citation과 고아 reference의 ID 리스트 반환."""
    orphan_citations = [c.id for c in citations if not c.ref_ids]

    used_ref_ids: set[str] = set()
    for c in citations:
        used_ref_ids.update(c.ref_ids)

    orphan_references = [r.id for r in references if r.id not in used_ref_ids]

    return orphan_citations, orphan_references
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/unit/test_linker.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/extract/linker.py tests/unit/test_linker.py
git commit -m "feat(extract): detect orphan citations and references"
```

---

## Task 10: 매칭 유틸리티 (제목/저자/연도)

**Files:**
- Create: `src/refcheck/verify/matching.py`
- Test: `tests/unit/test_matching.py`

**책임:** 제목 유사도, 저자 집합 비교, 연도 매칭. 메타데이터 검증의 기본 연산.

- [ ] **Step 1: 실패 테스트**

`tests/unit/test_matching.py`:

```python
from refcheck.verify.matching import (
    title_similarity, authors_match, compare_metadata,
    MatchResult,
)
from refcheck.schema.models import Reference, Author


def test_title_similarity_exact():
    assert title_similarity("The Neurobiology of Gambling",
                            "The Neurobiology of Gambling") >= 0.99


def test_title_similarity_near():
    s = title_similarity(
        "Anticipatory reward processing in addicted populations",
        "Anticipatory Reward Processing in Addicted Populations: A Focus on the Monetary Incentive Delay Task",
    )
    assert 0.60 <= s <= 0.90  # 부분 매칭


def test_title_similarity_different():
    assert title_similarity("Gambling neurobiology",
                            "Schizophrenia treatment") < 0.40


def test_authors_match_first_author_required():
    a1 = [Author(family="Potenza"), Author(family="Balodis")]
    a2 = [Author(family="Potenza"), Author(family="Kober"), Author(family="Balodis")]
    assert authors_match(a1, a2) is True  # 첫 저자 일치 + 부분집합


def test_authors_mismatch_different_first():
    a1 = [Author(family="Smith")]
    a2 = [Author(family="Jones")]
    assert authors_match(a1, a2) is False


def test_compare_metadata_all_match():
    ref = Reference(id="r1", authors=[Author(family="Potenza")], year=2013,
                    title="Neurobiology of gambling", journal="J Neuro",
                    raw_text="...", style_detected="APA")
    canonical = Reference(id="r1", authors=[Author(family="Potenza")], year=2013,
                          title="Neurobiology of gambling", journal="J Neuro",
                          raw_text="...", style_detected="APA")
    result = compare_metadata(ref, canonical)
    assert result.status == "verified"
    assert result.field_diffs == {}


def test_compare_metadata_year_mismatch():
    ref = Reference(id="r1", authors=[Author(family="Potenza")], year=2013,
                    title="Neurobiology of gambling", raw_text="...", style_detected="APA")
    canonical = Reference(id="r1", authors=[Author(family="Potenza")], year=2014,
                          title="Neurobiology of gambling", raw_text="...", style_detected="APA")
    result = compare_metadata(ref, canonical)
    assert result.status == "metadata_error"
    assert "year" in result.field_diffs


def test_compare_metadata_preprint_vs_published():
    # 저자·제목 일치, 연도 1년 차이 — 정보성 finding
    ref = Reference(id="r1", authors=[Author(family="Potenza")], year=2012,
                    title="Neurobiology of gambling", raw_text="...", style_detected="APA")
    canonical = Reference(id="r1", authors=[Author(family="Potenza")], year=2013,
                          title="Neurobiology of gambling", raw_text="...", style_detected="APA")
    result = compare_metadata(ref, canonical)
    assert result.status == "metadata_error"
    assert result.preprint_vs_published is True
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/unit/test_matching.py -v
```

Expected: FAIL

- [ ] **Step 3: 구현**

`src/refcheck/verify/matching.py`:

```python
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Literal
from rapidfuzz import fuzz
from refcheck.schema.models import Reference, Author


def _normalize_title(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def title_similarity(a: str, b: str) -> float:
    """0.0~1.0. token_set_ratio(부분 포함 허용)과 ratio(전체 일치)의 가중 평균."""
    a_n = _normalize_title(a)
    b_n = _normalize_title(b)
    set_score = fuzz.token_set_ratio(a_n, b_n) / 100
    full_score = fuzz.ratio(a_n, b_n) / 100
    return 0.5 * set_score + 0.5 * full_score


def _norm_surname(s: str) -> str:
    return re.sub(r"\s+", "", s.lower().strip())


def authors_match(a: list[Author], b: list[Author]) -> bool:
    """첫 저자 성 일치 + a의 저자 집합이 b의 부분집합 (et al. 허용)."""
    if not a or not b:
        return False
    if _norm_surname(a[0].family) != _norm_surname(b[0].family):
        return False
    set_a = {_norm_surname(x.family) for x in a}
    set_b = {_norm_surname(x.family) for x in b}
    return set_a.issubset(set_b) or set_b.issubset(set_a)


@dataclass
class MatchResult:
    status: Literal["verified", "metadata_error", "hallucination", "unverifiable"]
    field_diffs: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)
    title_sim: float = 0.0
    preprint_vs_published: bool = False


def compare_metadata(ref: Reference, canonical: Reference) -> MatchResult:
    diffs: dict[str, tuple[str | None, str | None]] = {}
    preprint_flag = False

    sim = title_similarity(ref.title, canonical.title)
    if sim < 0.90:
        diffs["title"] = (ref.title, canonical.title)

    if not authors_match(ref.authors, canonical.authors):
        diffs["authors"] = (
            ", ".join(a.family for a in ref.authors),
            ", ".join(a.family for a in canonical.authors),
        )

    if ref.year != canonical.year:
        diffs["year"] = (str(ref.year), str(canonical.year))
        if (
            ref.year is not None
            and canonical.year is not None
            and abs(ref.year - canonical.year) == 1
            and sim >= 0.90
            and authors_match(ref.authors, canonical.authors)
        ):
            preprint_flag = True

    if ref.journal and canonical.journal:
        if _normalize_title(ref.journal) != _normalize_title(canonical.journal):
            # 약어 vs 풀네임 동등 처리 (간단 heuristic: 한쪽이 다른쪽의 부분집합)
            sim_j = title_similarity(ref.journal, canonical.journal)
            if sim_j < 0.70:
                diffs["journal"] = (ref.journal, canonical.journal)

    if ref.doi and canonical.doi and ref.doi.lower() != canonical.doi.lower():
        diffs["doi"] = (ref.doi, canonical.doi)

    if ref.volume and canonical.volume and ref.volume != canonical.volume:
        diffs["volume"] = (ref.volume, canonical.volume)

    if ref.pages and canonical.pages and ref.pages != canonical.pages:
        diffs["pages"] = (ref.pages, canonical.pages)

    status: Literal["verified", "metadata_error"]
    status = "verified" if not diffs else "metadata_error"
    return MatchResult(status=status, field_diffs=diffs, title_sim=sim, preprint_vs_published=preprint_flag)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/unit/test_matching.py -v
```

Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/verify/matching.py tests/unit/test_matching.py
git commit -m "feat(verify): add title/author/metadata matching utilities"
```

---

## Task 11: Crossref 클라이언트

**Files:**
- Create: `src/refcheck/fetch/crossref.py`
- Test: `tests/integration/test_crossref.py`
- Fixture: `tests/fixtures/api_responses/crossref_potenza_2013.json`

- [ ] **Step 1: Fixture 작성**

`tests/fixtures/api_responses/crossref_potenza_2013.json`:

```json
{
  "status": "ok",
  "message": {
    "items": [{
      "DOI": "10.1016/j.conb.2013.01.020",
      "title": ["Neurobiology of gambling"],
      "author": [{"given": "Marc N.", "family": "Potenza"}],
      "published-print": {"date-parts": [[2013, 8]]},
      "container-title": ["Current Opinion in Neurobiology"],
      "volume": "23",
      "issue": "4",
      "page": "660-667"
    }]
  }
}
```

- [ ] **Step 2: 실패 테스트**

`tests/integration/test_crossref.py`:

```python
import json
from pathlib import Path
import pytest
import respx
from httpx import Response
from refcheck.fetch.crossref import CrossrefClient
from refcheck.schema.models import Reference, Author


FIXTURE = Path(__file__).parent.parent / "fixtures" / "api_responses" / "crossref_potenza_2013.json"


@pytest.mark.asyncio
@respx.mock
async def test_search_by_title_and_author():
    data = json.loads(FIXTURE.read_text())
    respx.get("https://api.crossref.org/works").mock(
        return_value=Response(200, json=data)
    )

    client = CrossrefClient()
    result = await client.search(
        title="Neurobiology of gambling",
        authors=[Author(family="Potenza")],
        year=2013,
    )
    assert result is not None
    assert result.title == "Neurobiology of gambling"
    assert result.doi == "10.1016/j.conb.2013.01.020"
    assert result.year == 2013
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_lookup_by_doi():
    data = {"status": "ok", "message": {
        "DOI": "10.1016/j.conb.2013.01.020",
        "title": ["Neurobiology of gambling"],
        "author": [{"given": "Marc N.", "family": "Potenza"}],
        "published-print": {"date-parts": [[2013, 8]]},
        "container-title": ["Current Opinion in Neurobiology"],
        "volume": "23", "issue": "4", "page": "660-667",
    }}
    respx.get("https://api.crossref.org/works/10.1016/j.conb.2013.01.020").mock(
        return_value=Response(200, json=data)
    )
    client = CrossrefClient()
    result = await client.lookup_doi("10.1016/j.conb.2013.01.020")
    assert result is not None
    assert result.year == 2013
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_returns_none_on_not_found():
    respx.get("https://api.crossref.org/works").mock(
        return_value=Response(200, json={"status": "ok", "message": {"items": []}})
    )
    client = CrossrefClient()
    result = await client.search(title="nonexistent paper", authors=[], year=2099)
    assert result is None
    await client.close()
```

- [ ] **Step 3: 테스트 실패 확인**

```bash
pytest tests/integration/test_crossref.py -v
```

Expected: FAIL

- [ ] **Step 4: 구현**

`src/refcheck/fetch/crossref.py`:

```python
from __future__ import annotations
from typing import Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from refcheck.schema.models import Reference, Author


BASE_URL = "https://api.crossref.org/works"


class CrossrefClient:
    def __init__(self, user_agent: str = "refcheck/0.1 (mailto:unknown)", timeout: float = 10.0):
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5), reraise=True)
    async def lookup_doi(self, doi: str) -> Reference | None:
        r = await self._client.get(f"{BASE_URL}/{doi}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        msg = r.json().get("message")
        return _to_reference(msg) if msg else None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5), reraise=True)
    async def search(
        self,
        *,
        title: str,
        authors: list[Author],
        year: int | None,
        rows: int = 5,
    ) -> Reference | None:
        params: dict[str, Any] = {"query.title": title, "rows": rows}
        if authors:
            params["query.author"] = " ".join(a.family for a in authors)
        if year:
            params["filter"] = f"from-pub-date:{year},until-pub-date:{year}"
        r = await self._client.get(BASE_URL, params=params)
        r.raise_for_status()
        items = r.json().get("message", {}).get("items", [])
        if not items:
            return None
        return _to_reference(items[0])


def _to_reference(msg: dict[str, Any]) -> Reference:
    title_list = msg.get("title") or []
    title = title_list[0] if title_list else ""
    authors = [
        Author(given=a.get("given"), family=a.get("family", ""))
        for a in msg.get("author", [])
        if a.get("family")
    ]
    year: int | None = None
    date_parts = (
        msg.get("published-print") or msg.get("published-online") or msg.get("issued") or {}
    ).get("date-parts") or []
    if date_parts and date_parts[0]:
        year = int(date_parts[0][0])
    journal_list = msg.get("container-title") or []
    return Reference(
        id="canonical",
        authors=authors,
        year=year,
        title=title,
        journal=journal_list[0] if journal_list else None,
        volume=msg.get("volume"),
        issue=msg.get("issue"),
        pages=msg.get("page"),
        doi=msg.get("DOI"),
        raw_text="",
        style_detected="unknown",
    )
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/integration/test_crossref.py -v
```

Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add src/refcheck/fetch/crossref.py tests/integration/test_crossref.py tests/fixtures/api_responses/crossref_potenza_2013.json
git commit -m "feat(fetch): add Crossref client"
```

---

## Task 12: OpenAlex 클라이언트

**Files:**
- Create: `src/refcheck/fetch/openalex.py`
- Test: `tests/integration/test_openalex.py`
- Fixture: `tests/fixtures/api_responses/openalex_potenza_2013.json`

- [ ] **Step 1: Fixture 작성**

`tests/fixtures/api_responses/openalex_potenza_2013.json`:

```json
{
  "results": [{
    "id": "https://openalex.org/W2005234567",
    "title": "Neurobiology of gambling",
    "doi": "https://doi.org/10.1016/j.conb.2013.01.020",
    "publication_year": 2013,
    "authorships": [{"author": {"display_name": "Marc N. Potenza"}}],
    "host_venue": {"display_name": "Current Opinion in Neurobiology"},
    "biblio": {"volume": "23", "issue": "4", "first_page": "660", "last_page": "667"},
    "abstract_inverted_index": {"Gambling": [0], "disorder": [1], "is": [2], "addictive": [3]},
    "open_access": {"is_oa": true, "oa_url": "https://example.com/paper.pdf"}
  }]
}
```

- [ ] **Step 2: 실패 테스트**

`tests/integration/test_openalex.py`:

```python
import json
from pathlib import Path
import pytest
import respx
from httpx import Response
from refcheck.fetch.openalex import OpenAlexClient
from refcheck.schema.models import Author


FIXTURE = Path(__file__).parent.parent / "fixtures" / "api_responses" / "openalex_potenza_2013.json"


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_reference_with_abstract_and_oa():
    data = json.loads(FIXTURE.read_text())
    respx.get("https://api.openalex.org/works").mock(
        return_value=Response(200, json=data)
    )
    client = OpenAlexClient()
    result = await client.search(
        title="Neurobiology of gambling",
        authors=[Author(family="Potenza")],
        year=2013,
    )
    assert result is not None
    assert result.reference.year == 2013
    assert result.abstract is not None and "Gambling" in result.abstract
    assert result.is_oa is True
    assert result.oa_url == "https://example.com/paper.pdf"
    await client.close()
```

- [ ] **Step 3: 테스트 실패 확인**

```bash
pytest tests/integration/test_openalex.py -v
```

Expected: FAIL

- [ ] **Step 4: 구현**

`src/refcheck/fetch/openalex.py`:

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from refcheck.schema.models import Reference, Author


BASE_URL = "https://api.openalex.org/works"


@dataclass
class OpenAlexResult:
    reference: Reference
    abstract: str | None
    is_oa: bool
    oa_url: str | None


class OpenAlexClient:
    def __init__(self, mailto: str | None = None, timeout: float = 10.0):
        params = f"?mailto={mailto}" if mailto else ""
        self._client = httpx.AsyncClient(
            headers={"User-Agent": f"refcheck/0.1{params}"},
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
    ) -> OpenAlexResult | None:
        query_parts = [title]
        if authors:
            query_parts.append(authors[0].family)
        params = {"search": " ".join(query_parts), "per-page": "5"}
        if year:
            params["filter"] = f"publication_year:{year}"
        r = await self._client.get(BASE_URL, params=params)
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return None
        return _to_result(results[0])


def _to_result(item: dict[str, Any]) -> OpenAlexResult:
    authorships = item.get("authorships") or []
    authors: list[Author] = []
    for a in authorships:
        name = (a.get("author") or {}).get("display_name", "")
        if name:
            parts = name.rsplit(" ", 1)
            if len(parts) == 2:
                authors.append(Author(given=parts[0], family=parts[1]))
            else:
                authors.append(Author(family=name))

    venue = item.get("host_venue") or {}
    biblio = item.get("biblio") or {}
    pages = None
    if biblio.get("first_page"):
        pages = biblio["first_page"]
        if biblio.get("last_page"):
            pages = f"{biblio['first_page']}-{biblio['last_page']}"

    doi = item.get("doi")
    if doi and doi.startswith("https://doi.org/"):
        doi = doi.removeprefix("https://doi.org/")

    ref = Reference(
        id="canonical",
        authors=authors,
        year=item.get("publication_year"),
        title=item.get("title", ""),
        journal=venue.get("display_name"),
        volume=biblio.get("volume"),
        issue=biblio.get("issue"),
        pages=pages,
        doi=doi,
        raw_text="",
        style_detected="unknown",
    )

    abstract = _decode_inverted_index(item.get("abstract_inverted_index"))
    oa = item.get("open_access") or {}
    return OpenAlexResult(
        reference=ref,
        abstract=abstract,
        is_oa=bool(oa.get("is_oa")),
        oa_url=oa.get("oa_url"),
    )


def _decode_inverted_index(idx: dict[str, list[int]] | None) -> str | None:
    if not idx:
        return None
    positions: list[tuple[int, str]] = []
    for word, poss in idx.items():
        for p in poss:
            positions.append((p, word))
    positions.sort()
    return " ".join(w for _, w in positions)
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/integration/test_openalex.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/refcheck/fetch/openalex.py tests/integration/test_openalex.py tests/fixtures/api_responses/openalex_potenza_2013.json
git commit -m "feat(fetch): add OpenAlex client with abstract decoding"
```

---

## Task 13: Semantic Scholar 클라이언트

**Files:**
- Create: `src/refcheck/fetch/semantic_scholar.py`
- Test: `tests/integration/test_semantic_scholar.py`

- [ ] **Step 1: 실패 테스트**

`tests/integration/test_semantic_scholar.py`:

```python
import pytest
import respx
from httpx import Response
from refcheck.fetch.semantic_scholar import SemanticScholarClient
from refcheck.schema.models import Author


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_reference():
    data = {
        "data": [{
            "paperId": "abc123",
            "title": "Neurobiology of gambling",
            "year": 2013,
            "authors": [{"name": "Marc N. Potenza"}],
            "venue": "Current Opinion in Neurobiology",
            "externalIds": {"DOI": "10.1016/j.conb.2013.01.020"},
            "abstract": "Gambling disorder is ...",
        }]
    }
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=Response(200, json=data)
    )
    client = SemanticScholarClient()
    result = await client.search(
        title="Neurobiology of gambling",
        authors=[Author(family="Potenza")],
        year=2013,
    )
    assert result is not None
    assert result.reference.doi == "10.1016/j.conb.2013.01.020"
    assert result.abstract is not None
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_returns_none_on_empty():
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=Response(200, json={"data": []})
    )
    client = SemanticScholarClient()
    result = await client.search(title="zzz", authors=[], year=2099)
    assert result is None
    await client.close()
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/integration/test_semantic_scholar.py -v
```

Expected: FAIL

- [ ] **Step 3: 구현**

`src/refcheck/fetch/semantic_scholar.py`:

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from refcheck.schema.models import Reference, Author


BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,year,authors,venue,externalIds,abstract"


@dataclass
class SemanticScholarResult:
    reference: Reference
    abstract: str | None


class SemanticScholarClient:
    def __init__(self, api_key: str | None = None, timeout: float = 10.0):
        headers = {"User-Agent": "refcheck/0.1"}
        if api_key:
            headers["x-api-key"] = api_key
        self._client = httpx.AsyncClient(headers=headers, timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5), reraise=True)
    async def search(
        self,
        *,
        title: str,
        authors: list[Author],
        year: int | None,
        limit: int = 5,
    ) -> SemanticScholarResult | None:
        query = title
        if authors:
            query = f"{title} {authors[0].family}"
        params: dict[str, Any] = {"query": query, "limit": limit, "fields": FIELDS}
        if year:
            params["year"] = str(year)
        r = await self._client.get(BASE_URL, params=params)
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return None
        return _to_result(data[0])


def _to_result(item: dict[str, Any]) -> SemanticScholarResult:
    authors_raw = item.get("authors") or []
    authors: list[Author] = []
    for a in authors_raw:
        name = a.get("name", "")
        parts = name.rsplit(" ", 1)
        if len(parts) == 2:
            authors.append(Author(given=parts[0], family=parts[1]))
        elif name:
            authors.append(Author(family=name))

    ext = item.get("externalIds") or {}
    ref = Reference(
        id="canonical",
        authors=authors,
        year=item.get("year"),
        title=item.get("title", ""),
        journal=item.get("venue"),
        doi=ext.get("DOI"),
        raw_text="",
        style_detected="unknown",
    )
    return SemanticScholarResult(reference=ref, abstract=item.get("abstract"))
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/integration/test_semantic_scholar.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/fetch/semantic_scholar.py tests/integration/test_semantic_scholar.py
git commit -m "feat(fetch): add Semantic Scholar client"
```

---

## Task 14: PubMed 클라이언트

**Files:**
- Create: `src/refcheck/fetch/pubmed.py`
- Test: `tests/integration/test_pubmed.py`

**참고:** PubMed E-utilities는 esearch(ID 검색) + efetch(상세) 2단계 호출.

- [ ] **Step 1: 실패 테스트**

`tests/integration/test_pubmed.py`:

```python
import pytest
import respx
from httpx import Response
from refcheck.fetch.pubmed import PubMedClient
from refcheck.schema.models import Author


ESEARCH_XML = """<?xml version="1.0"?>
<eSearchResult><IdList><Id>23500103</Id></IdList></eSearchResult>"""

EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle><MedlineCitation>
    <PMID>23500103</PMID>
    <Article>
      <Journal><Title>Current Opinion in Neurobiology</Title>
        <JournalIssue><Volume>23</Volume><Issue>4</Issue>
          <PubDate><Year>2013</Year></PubDate></JournalIssue></Journal>
      <ArticleTitle>Neurobiology of gambling</ArticleTitle>
      <Pagination><MedlinePgn>660-7</MedlinePgn></Pagination>
      <Abstract><AbstractText>Gambling disorder is...</AbstractText></Abstract>
      <AuthorList><Author>
        <LastName>Potenza</LastName><ForeName>Marc N</ForeName>
      </Author></AuthorList>
      <ELocationID EIdType="doi">10.1016/j.conb.2013.01.020</ELocationID>
    </Article>
  </MedlineCitation></PubmedArticle>
</PubmedArticleSet>"""


@pytest.mark.asyncio
@respx.mock
async def test_search_two_step():
    respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").mock(
        return_value=Response(200, text=ESEARCH_XML)
    )
    respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi").mock(
        return_value=Response(200, text=EFETCH_XML)
    )
    client = PubMedClient()
    result = await client.search(
        title="Neurobiology of gambling",
        authors=[Author(family="Potenza")],
        year=2013,
    )
    assert result is not None
    assert result.reference.year == 2013
    assert result.reference.doi == "10.1016/j.conb.2013.01.020"
    assert "Gambling disorder" in result.abstract
    await client.close()
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/integration/test_pubmed.py -v
```

Expected: FAIL

- [ ] **Step 3: 구현**

`src/refcheck/fetch/pubmed.py`:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/integration/test_pubmed.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/fetch/pubmed.py tests/integration/test_pubmed.py
git commit -m "feat(fetch): add PubMed client (esearch + efetch)"
```

---

## Task 15: 메타데이터 검증 오케스트레이터

**Files:**
- Create: `src/refcheck/verify/metadata.py`
- Test: `tests/integration/test_verify_metadata.py`

**책임:** 각 Reference에 대해 DOI → Crossref → OpenAlex → Semantic Scholar → PubMed 순차 조회. 최초 매칭 성공한 결과로 판정. 병렬 실행.

- [ ] **Step 1: 실패 테스트**

`tests/integration/test_verify_metadata.py`:

```python
from unittest.mock import AsyncMock, MagicMock
import pytest
from refcheck.schema.models import Reference, Author
from refcheck.verify.metadata import verify_all_references
from refcheck.fetch.openalex import OpenAlexResult
from refcheck.fetch.semantic_scholar import SemanticScholarResult


def _canonical(title="Neurobiology of gambling", year=2013):
    return Reference(
        id="canonical",
        authors=[Author(family="Potenza")],
        year=year,
        title=title,
        doi="10.1016/x",
        raw_text="",
        style_detected="unknown",
    )


@pytest.mark.asyncio
async def test_verified_when_crossref_matches():
    ref = Reference(id="ref_001", authors=[Author(family="Potenza")], year=2013,
                    title="Neurobiology of gambling", raw_text="...", style_detected="APA")

    crossref = MagicMock()
    crossref.lookup_doi = AsyncMock(return_value=None)
    crossref.search = AsyncMock(return_value=_canonical())
    openalex = MagicMock()
    openalex.search = AsyncMock(return_value=None)
    semantic = MagicMock()
    semantic.search = AsyncMock(return_value=None)
    pubmed = MagicMock()
    pubmed.search = AsyncMock(return_value=None)

    results = await verify_all_references(
        [ref], crossref=crossref, openalex=openalex,
        semantic_scholar=semantic, pubmed=pubmed, concurrency=1,
    )
    assert results[0].status == "verified"
    assert "crossref" in results[0].sources_checked


@pytest.mark.asyncio
async def test_hallucination_when_all_sources_empty():
    ref = Reference(id="ref_001", authors=[Author(family="FakeAuthor")], year=2099,
                    title="A Paper That Does Not Exist", raw_text="...", style_detected="APA")

    crossref = MagicMock()
    crossref.lookup_doi = AsyncMock(return_value=None)
    crossref.search = AsyncMock(return_value=None)
    openalex = MagicMock()
    openalex.search = AsyncMock(return_value=None)
    semantic = MagicMock()
    semantic.search = AsyncMock(return_value=None)
    pubmed = MagicMock()
    pubmed.search = AsyncMock(return_value=None)

    results = await verify_all_references(
        [ref], crossref=crossref, openalex=openalex,
        semantic_scholar=semantic, pubmed=pubmed, concurrency=1,
    )
    assert results[0].status == "hallucination"
    assert len(results[0].sources_checked) == 4


@pytest.mark.asyncio
async def test_metadata_error_when_year_differs():
    ref = Reference(id="ref_001", authors=[Author(family="Potenza")], year=2012,
                    title="Neurobiology of gambling", raw_text="...", style_detected="APA")
    crossref = MagicMock()
    crossref.lookup_doi = AsyncMock(return_value=None)
    crossref.search = AsyncMock(return_value=_canonical(year=2013))
    openalex = MagicMock()
    openalex.search = AsyncMock(return_value=None)
    semantic = MagicMock()
    semantic.search = AsyncMock(return_value=None)
    pubmed = MagicMock()
    pubmed.search = AsyncMock(return_value=None)

    results = await verify_all_references(
        [ref], crossref=crossref, openalex=openalex,
        semantic_scholar=semantic, pubmed=pubmed, concurrency=1,
    )
    assert results[0].status == "metadata_error"
    assert "year" in results[0].field_diffs
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/integration/test_verify_metadata.py -v
```

Expected: FAIL

- [ ] **Step 3: 구현**

`src/refcheck/verify/metadata.py`:

```python
from __future__ import annotations
import asyncio
from typing import Protocol
from refcheck.schema.models import Reference, VerifiedReference
from refcheck.verify.matching import compare_metadata, title_similarity, authors_match
from refcheck.fetch.crossref import CrossrefClient
from refcheck.fetch.openalex import OpenAlexClient, OpenAlexResult
from refcheck.fetch.semantic_scholar import SemanticScholarClient, SemanticScholarResult
from refcheck.fetch.pubmed import PubMedClient, PubMedResult


TITLE_ACCEPT = 0.90
TITLE_MAYBE = 0.70


async def verify_all_references(
    references: list[Reference],
    *,
    crossref: CrossrefClient,
    openalex: OpenAlexClient,
    semantic_scholar: SemanticScholarClient,
    pubmed: PubMedClient,
    concurrency: int = 5,
) -> list[VerifiedReference]:
    sem = asyncio.Semaphore(concurrency)

    async def _worker(r: Reference) -> VerifiedReference:
        async with sem:
            return await _verify_single(r, crossref, openalex, semantic_scholar, pubmed)

    return await asyncio.gather(*(_worker(r) for r in references))


async def _verify_single(
    ref: Reference,
    crossref: CrossrefClient,
    openalex: OpenAlexClient,
    semantic: SemanticScholarClient,
    pubmed: PubMedClient,
) -> VerifiedReference:
    checked: list[str] = []
    best_match: Reference | None = None

    # 1. DOI 있으면 Crossref DOI 조회
    if ref.doi:
        checked.append("crossref_doi")
        result = await _safe(crossref.lookup_doi(ref.doi))
        if result:
            return _build_verified(ref, result, checked)

    # 2. Crossref 검색
    checked.append("crossref")
    cr = await _safe(crossref.search(title=ref.title, authors=ref.authors, year=ref.year))
    if cr and _is_plausible_match(ref, cr):
        return _build_verified(ref, cr, checked)
    if cr:
        best_match = cr

    # 3. OpenAlex
    checked.append("openalex")
    oa: OpenAlexResult | None = await _safe(openalex.search(title=ref.title, authors=ref.authors, year=ref.year))
    if oa and _is_plausible_match(ref, oa.reference):
        return _build_verified(ref, oa.reference, checked, abstract=oa.abstract,
                               oa_url=oa.oa_url if oa.is_oa else None)
    if oa and not best_match:
        best_match = oa.reference

    # 4. Semantic Scholar
    checked.append("semantic_scholar")
    ss: SemanticScholarResult | None = await _safe(semantic.search(title=ref.title, authors=ref.authors, year=ref.year))
    if ss and _is_plausible_match(ref, ss.reference):
        return _build_verified(ref, ss.reference, checked, abstract=ss.abstract)
    if ss and not best_match:
        best_match = ss.reference

    # 5. PubMed
    checked.append("pubmed")
    pm: PubMedResult | None = await _safe(pubmed.search(title=ref.title, authors=ref.authors, year=ref.year))
    if pm and _is_plausible_match(ref, pm.reference):
        return _build_verified(ref, pm.reference, checked, abstract=pm.abstract)
    if pm and not best_match:
        best_match = pm.reference

    # 6. 판정: best_match가 있으면 ❓(unverifiable) 또는 🟠(metadata_error), 없으면 🔴(hallucination)
    if best_match is not None:
        sim = title_similarity(ref.title, best_match.title)
        if sim >= TITLE_MAYBE:
            # 제목이 꽤 비슷 → metadata_error 가능성
            return _build_verified(ref, best_match, checked)
        # 애매한 일치
        return VerifiedReference(
            reference=ref,
            status="unverifiable",
            canonical=best_match,
            access_level="not_found",
            sources_checked=checked,
        )

    return VerifiedReference(
        reference=ref,
        status="hallucination",
        canonical=None,
        access_level="not_found",
        sources_checked=checked,
    )


async def _safe(awaitable) -> any:
    try:
        return await awaitable
    except Exception:
        return None


def _is_plausible_match(ref: Reference, cand: Reference) -> bool:
    return title_similarity(ref.title, cand.title) >= TITLE_ACCEPT and authors_match(ref.authors, cand.authors)


def _build_verified(
    ref: Reference,
    canonical: Reference,
    sources: list[str],
    *,
    abstract: str | None = None,
    oa_url: str | None = None,
) -> VerifiedReference:
    match = compare_metadata(ref, canonical)
    access = "abstract_only" if abstract else "not_found"
    if oa_url:
        access = "full_text"  # 실제 다운로드는 Task 18에서
    return VerifiedReference(
        reference=ref,
        status=match.status,
        canonical=canonical,
        field_diffs=match.field_diffs,
        access_level=access,
        abstract=abstract,
        sources_checked=sources,
    )
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/integration/test_verify_metadata.py -v
```

Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/verify/metadata.py tests/integration/test_verify_metadata.py
git commit -m "feat(verify): add metadata verification orchestrator"
```

---

## Task 16: 디스크 캐시

**Files:**
- Create: `src/refcheck/fetch/cache.py`
- Test: `tests/unit/test_cache.py`

**책임:** DOI 해시로 JSON 캐시. API 재호출 방지.

- [ ] **Step 1: 실패 테스트**

`tests/unit/test_cache.py`:

```python
from refcheck.fetch.cache import DiskCache


def test_set_and_get(tmp_path):
    cache = DiskCache(tmp_path)
    cache.set("key1", {"a": 1})
    assert cache.get("key1") == {"a": 1}


def test_missing_returns_none(tmp_path):
    cache = DiskCache(tmp_path)
    assert cache.get("missing") is None


def test_keys_are_hashed_path_safe(tmp_path):
    cache = DiskCache(tmp_path)
    weird_key = "10.1016/some/slash?and&stuff"
    cache.set(weird_key, {"ok": True})
    assert cache.get(weird_key) == {"ok": True}


def test_survives_across_instances(tmp_path):
    c1 = DiskCache(tmp_path)
    c1.set("persist", {"v": 42})
    c2 = DiskCache(tmp_path)
    assert c2.get("persist") == {"v": 42}
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/unit/test_cache.py -v
```

Expected: FAIL

- [ ] **Step 3: 구현**

`src/refcheck/fetch/cache.py`:

```python
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any


class DiskCache:
    def __init__(self, base_dir: Path | str):
        self._dir = Path(base_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self._dir / f"{h}.json"

    def get(self, key: str) -> Any | None:
        p = self._path(key)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, key: str, value: Any) -> None:
        p = self._path(key)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        tmp.rename(p)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/unit/test_cache.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/fetch/cache.py tests/unit/test_cache.py
git commit -m "feat(fetch): add disk cache"
```

---

## Task 17: Unpaywall 클라이언트

**Files:**
- Create: `src/refcheck/fetch/unpaywall.py`
- Test: `tests/integration/test_unpaywall.py`

- [ ] **Step 1: 실패 테스트**

`tests/integration/test_unpaywall.py`:

```python
import pytest
import respx
from httpx import Response
from refcheck.fetch.unpaywall import UnpaywallClient


@pytest.mark.asyncio
@respx.mock
async def test_returns_oa_url():
    data = {
        "is_oa": True,
        "best_oa_location": {"url_for_pdf": "https://example.com/paper.pdf"},
    }
    respx.get("https://api.unpaywall.org/v2/10.1016/j.conb.2013.01.020").mock(
        return_value=Response(200, json=data)
    )
    client = UnpaywallClient(email="test@example.com")
    url = await client.oa_pdf_url("10.1016/j.conb.2013.01.020")
    assert url == "https://example.com/paper.pdf"
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_returns_none_when_not_oa():
    data = {"is_oa": False, "best_oa_location": None}
    respx.get("https://api.unpaywall.org/v2/10.1016/paywalled").mock(
        return_value=Response(200, json=data)
    )
    client = UnpaywallClient(email="test@example.com")
    url = await client.oa_pdf_url("10.1016/paywalled")
    assert url is None
    await client.close()
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/integration/test_unpaywall.py -v
```

Expected: FAIL

- [ ] **Step 3: 구현**

`src/refcheck/fetch/unpaywall.py`:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/integration/test_unpaywall.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/fetch/unpaywall.py tests/integration/test_unpaywall.py
git commit -m "feat(fetch): add Unpaywall client"
```

---

## Task 18: Source Fetcher 오케스트레이터

**Files:**
- Create: `src/refcheck/fetch/source_fetcher.py`
- Test: `tests/integration/test_source_fetcher.py`

**책임:** `VerifiedReference`에 전문 PDF 다운로드·텍스트 추출 결과 채우기. OA PDF 다운로드 실패 시 초록만(⚪) 또는 🔒 판정.

- [ ] **Step 1: 실패 테스트**

`tests/integration/test_source_fetcher.py`:

```python
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
import pytest
import respx
from httpx import Response
from refcheck.schema.models import VerifiedReference, Reference, Author
from refcheck.fetch.source_fetcher import fetch_sources


def _vref(doi="10.1016/x", abstract=None, access_level="not_found"):
    return VerifiedReference(
        reference=Reference(
            id="ref_001", authors=[Author(family="X")], year=2020,
            title="T", doi=doi, raw_text="...", style_detected="APA",
        ),
        status="verified",
        canonical=Reference(
            id="canonical", authors=[Author(family="X")], year=2020,
            title="T", doi=doi, raw_text="", style_detected="unknown",
        ),
        abstract=abstract,
        access_level=access_level,
    )


@pytest.mark.asyncio
async def test_paywalled_when_no_oa(tmp_path):
    vref = _vref(abstract="Short abstract", access_level="abstract_only")
    unpaywall = MagicMock()
    unpaywall.oa_pdf_url = AsyncMock(return_value=None)

    result = await fetch_sources([vref], unpaywall=unpaywall, cache_dir=tmp_path)
    assert result[0].access_level == "abstract_only"  # 초록은 있으므로 paywalled 아님


@pytest.mark.asyncio
async def test_marks_paywalled_when_no_abstract_no_oa(tmp_path):
    vref = _vref(abstract=None, access_level="not_found")
    unpaywall = MagicMock()
    unpaywall.oa_pdf_url = AsyncMock(return_value=None)
    result = await fetch_sources([vref], unpaywall=unpaywall, cache_dir=tmp_path)
    assert result[0].access_level == "paywalled"


@pytest.mark.asyncio
@respx.mock
async def test_downloads_full_text_when_oa(tmp_path):
    # 간단한 PDF 생성 (실제 PDF 바이트 필요)
    from reportlab.pdfgen import canvas
    pdf_path = tmp_path / "paper.pdf"
    c = canvas.Canvas(str(pdf_path))
    c.drawString(72, 750, "Full text content here")
    c.save()
    pdf_bytes = pdf_path.read_bytes()

    respx.get("https://example.com/paper.pdf").mock(
        return_value=Response(200, content=pdf_bytes, headers={"content-type": "application/pdf"})
    )

    vref = _vref(abstract="abs", access_level="abstract_only")
    unpaywall = MagicMock()
    unpaywall.oa_pdf_url = AsyncMock(return_value="https://example.com/paper.pdf")

    result = await fetch_sources([vref], unpaywall=unpaywall, cache_dir=tmp_path / "cache")
    assert result[0].access_level == "full_text"
    assert "Full text content" in (result[0].full_text or "")
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/integration/test_source_fetcher.py -v
```

Expected: FAIL

- [ ] **Step 3: 구현**

`src/refcheck/fetch/source_fetcher.py`:

```python
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
    # 이미 hallucination/unverifiable이면 스킵
    if vref.status in ("hallucination", "unverifiable"):
        return vref

    doi = (vref.canonical.doi if vref.canonical else None) or vref.reference.doi
    if not doi:
        # 초록만 있으면 abstract_only, 아니면 paywalled
        if vref.abstract:
            vref.access_level = "abstract_only"
        else:
            vref.access_level = "paywalled"
        return vref

    # 캐시 확인
    cache_key = f"fulltext:{doi}"
    cached = cache.get(cache_key)
    if cached:
        vref.full_text = cached.get("text")
        vref.access_level = "full_text"
        return vref

    # Unpaywall 조회
    try:
        url = await unpaywall.oa_pdf_url(doi)
    except Exception:
        url = None

    if not url:
        vref.access_level = "abstract_only" if vref.abstract else "paywalled"
        return vref

    # PDF 다운로드 + 텍스트 추출
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
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/integration/test_source_fetcher.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/fetch/source_fetcher.py tests/integration/test_source_fetcher.py
git commit -m "feat(fetch): add source fetcher for OA full text"
```

---

## Task 19: Content Verify 프롬프트 + 스키마

**Files:**
- Create: `src/refcheck/llm/prompts/content_verify.md`
- Create: `src/refcheck/verify/content_schema.py`

- [ ] **Step 1: 프롬프트 작성**

`src/refcheck/llm/prompts/content_verify.md`:

```markdown
You are a meticulous medical journal editor verifying citations in an academic draft.

Given:
- A claim in the draft that cites a specific reference
- The original paper's abstract (and sometimes full text)

Determine whether the citation is correct. Classify any issues using the taxonomy below.

# Error Taxonomy

## Content Mismatch (category: "content_mismatch")
- **claim_reversal**: Original paper says "no effect" but draft claims "effect exists" (or vice versa)
- **number_distortion**: Numbers/statistics (percentages, p-values, effect sizes) are wrong
- **causal_correlation_confusion**: Original shows correlation, draft claims causation
- **overgeneralization**: Original applies to specific population/condition, draft generalizes
- **strength_distortion**: Original says "suggests/may" but draft says "proves/established"
- **selective_citation**: Draft cites only positive results, ignoring limitations
- **complete_mismatch**: The cited paper does not discuss this topic at all

## Weak Context (category: "weak_context")
- **temporal_inadequate**: A later meta-analysis overturned this finding
- **population_inadequate**: Animal study cited for human clinical claim
- **methodology_inadequate**: Case report cited as evidence of treatment effect
- **weak_support**: Original mentions the topic but it's not the main conclusion
- **indirect_citation_chain**: The cited paper doesn't make the claim directly; it cites another paper for it. Suggest citing the primary source.

## No Issue
If the citation is accurate, return category "none".

# Rules

1. `source_evidence_quote` MUST be copied verbatim from the provided source text. If you cannot find direct evidence, use empty string "".
2. Never invent evidence. If the source text doesn't support a finding, use "none".
3. Severity: 5=critical (fabrication, claim reversal), 4=major (number distortion, causal confusion), 3=moderate (overgeneralization, strength distortion), 2=minor (weak_support, selective_citation), 1=informational (indirect_citation_chain).
4. Confidence: high=evidence clearly in abstract, medium=evidence in full text, low=partial/indirect evidence.
5. If you only have the abstract and cannot determine, return confidence "low" with category "none" — flag for manual review via low confidence.

Output strictly valid JSON matching the provided schema.
```

- [ ] **Step 2: 스키마 정의**

`src/refcheck/verify/content_schema.py`:

```python
CONTENT_VERIFY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "category", "error_type", "severity", "confidence",
        "source_evidence_quote", "explanation", "suggestion",
    ],
    "properties": {
        "category": {
            "type": "string",
            "enum": ["content_mismatch", "weak_context", "none"],
        },
        "error_type": {"type": ["string", "null"]},
        "severity": {"type": "integer", "minimum": 1, "maximum": 5},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "source_evidence_quote": {"type": "string"},
        "explanation": {"type": "string"},
        "suggestion": {"type": ["string", "null"]},
    },
}
```

- [ ] **Step 3: Commit**

```bash
git add src/refcheck/llm/prompts/content_verify.md src/refcheck/verify/content_schema.py
git commit -m "feat(verify): add content verify prompt and schema"
```

---

## Task 20: 증거 인용 검증기 (환각 방지)

**Files:**
- Create: `src/refcheck/verify/evidence_validator.py`
- Test: `tests/unit/test_evidence_validator.py`

**책임:** LLM이 제시한 `source_evidence_quote`가 원문에 실제로 존재하는지 확인. 없으면 재호출 필요 신호.

- [ ] **Step 1: 실패 테스트**

`tests/unit/test_evidence_validator.py`:

```python
from refcheck.verify.evidence_validator import quote_exists_in_source


def test_exact_quote_found():
    source = "Gambling disorder is characterized by persistent patterns."
    assert quote_exists_in_source("characterized by persistent patterns", source) is True


def test_quote_with_whitespace_differences_found():
    source = "Gambling disorder\n\nis   characterized by persistent."
    assert quote_exists_in_source("is characterized by persistent", source) is True


def test_quote_not_in_source():
    source = "Gambling disorder."
    assert quote_exists_in_source("schizophrenia treatment", source) is False


def test_empty_quote_returns_true():
    # 빈 문자열은 "증거 없음"이므로 True (검증 통과, low confidence로 처리)
    assert quote_exists_in_source("", "any source") is True


def test_empty_source_with_nonempty_quote_returns_false():
    assert quote_exists_in_source("something", "") is False
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/unit/test_evidence_validator.py -v
```

Expected: FAIL

- [ ] **Step 3: 구현**

`src/refcheck/verify/evidence_validator.py`:

```python
from __future__ import annotations
import re


def _normalize_for_match(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_exists_in_source(quote: str, source: str) -> bool:
    """공백·대소문자 차이를 허용하고 quote가 source에 포함되는지 확인."""
    if not quote.strip():
        return True
    if not source:
        return False
    q = _normalize_for_match(quote)
    s = _normalize_for_match(source)
    return q in s
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/unit/test_evidence_validator.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/verify/evidence_validator.py tests/unit/test_evidence_validator.py
git commit -m "feat(verify): add evidence quote existence validator"
```

---

## Task 21: Content Verify 엔진 (인용 1건)

**Files:**
- Create: `src/refcheck/verify/content.py`
- Test: `tests/integration/test_content_verify.py`

**책임:** (Citation + VerifiedReference) → LLM 호출 → Finding 또는 None. 증거 검증 실패 시 재호출 1회.

- [ ] **Step 1: 실패 테스트**

`tests/integration/test_content_verify.py`:

```python
from unittest.mock import AsyncMock, MagicMock
import pytest
from refcheck.schema.models import Citation, VerifiedReference, Reference, Author
from refcheck.verify.content import verify_citation
from refcheck.llm.client import LLMClient, LLMUsage


def _vref_with_abstract():
    ref = Reference(
        id="ref_001", authors=[Author(family="Potenza")], year=2013,
        title="T", doi="10.1016/x", raw_text="...", style_detected="APA",
    )
    return VerifiedReference(
        reference=ref,
        status="verified",
        canonical=ref,
        abstract="Gambling disorder affects 1% of adults. No significant effect of drug X was observed.",
        access_level="abstract_only",
    )


def _cit():
    return Citation(
        id="cit_001",
        surface="(Potenza, 2013)",
        ref_ids=["ref_001"],
        char_offset=0,
        containing_sentence="Drug X shows clear efficacy in gambling disorder (Potenza, 2013).",
        surrounding_paragraph="Drug X shows clear efficacy in gambling disorder (Potenza, 2013).",
    )


@pytest.mark.asyncio
async def test_detects_claim_reversal():
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.complete_json = AsyncMock(return_value=(
        {
            "category": "content_mismatch",
            "error_type": "claim_reversal",
            "severity": 5,
            "confidence": "high",
            "source_evidence_quote": "No significant effect of drug X was observed.",
            "explanation": "원문은 '효과 없음'인데 초안은 '명확한 효능'이라 주장.",
            "suggestion": "효능 주장 철회 또는 다른 논문 인용 필요.",
        },
        LLMUsage(model="gpt-5.4-thinking", prompt_tokens=500, completion_tokens=100, cost_usd=0.005),
    ))

    finding = await verify_citation(_cit(), _vref_with_abstract(), llm=mock_llm)
    assert finding is not None
    assert finding.category == "content_mismatch"
    assert finding.error_type == "claim_reversal"
    assert finding.severity == 5


@pytest.mark.asyncio
async def test_returns_none_when_category_none():
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.complete_json = AsyncMock(return_value=(
        {
            "category": "none",
            "error_type": None,
            "severity": 1,
            "confidence": "high",
            "source_evidence_quote": "",
            "explanation": "문제 없음.",
            "suggestion": None,
        },
        LLMUsage(model="gpt-5.4-thinking", prompt_tokens=500, completion_tokens=50, cost_usd=0.003),
    ))
    finding = await verify_citation(_cit(), _vref_with_abstract(), llm=mock_llm)
    assert finding is None


@pytest.mark.asyncio
async def test_retries_when_evidence_not_in_source():
    """LLM이 환각한 증거 인용을 걸러내고 재호출."""
    mock_llm = MagicMock(spec=LLMClient)
    # 1회차: 원문에 없는 인용
    # 2회차: 유효한 인용
    mock_llm.complete_json = AsyncMock(side_effect=[
        (
            {"category": "content_mismatch", "error_type": "claim_reversal",
             "severity": 5, "confidence": "high",
             "source_evidence_quote": "This text does not exist in the abstract.",
             "explanation": "...", "suggestion": None},
            LLMUsage(model="gpt-5.4-thinking", prompt_tokens=500, completion_tokens=100, cost_usd=0.005),
        ),
        (
            {"category": "content_mismatch", "error_type": "claim_reversal",
             "severity": 5, "confidence": "high",
             "source_evidence_quote": "No significant effect of drug X was observed.",
             "explanation": "...", "suggestion": None},
            LLMUsage(model="gpt-5.4-thinking", prompt_tokens=500, completion_tokens=100, cost_usd=0.005),
        ),
    ])
    finding = await verify_citation(_cit(), _vref_with_abstract(), llm=mock_llm)
    assert finding is not None
    assert finding.source_evidence_quote == "No significant effect of drug X was observed."
    assert mock_llm.complete_json.call_count == 2


@pytest.mark.asyncio
async def test_low_confidence_after_two_failed_evidence_validations():
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.complete_json = AsyncMock(return_value=(
        {"category": "content_mismatch", "error_type": "claim_reversal",
         "severity": 5, "confidence": "high",
         "source_evidence_quote": "Not in source at all.",
         "explanation": "...", "suggestion": None},
        LLMUsage(model="gpt-5.4-thinking", prompt_tokens=500, completion_tokens=100, cost_usd=0.005),
    ))
    finding = await verify_citation(_cit(), _vref_with_abstract(), llm=mock_llm)
    assert finding is not None
    assert finding.confidence == "low"
    assert finding.source_evidence_quote is None
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/integration/test_content_verify.py -v
```

Expected: FAIL

- [ ] **Step 3: 구현**

`src/refcheck/verify/content.py`:

```python
from __future__ import annotations
from pathlib import Path
from refcheck.schema.models import Citation, VerifiedReference, Finding
from refcheck.llm.client import LLMClient
from refcheck.verify.content_schema import CONTENT_VERIFY_SCHEMA
from refcheck.verify.evidence_validator import quote_exists_in_source


_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "content_verify.md"


async def verify_citation(
    citation: Citation,
    verified_ref: VerifiedReference,
    *,
    llm: LLMClient,
    model: str = "gpt-5.4-thinking",
    max_evidence_retries: int = 1,
) -> Finding | None:
    """단일 citation을 원문 대조하여 Finding 반환 (문제 없으면 None).

    verified_ref가 status='hallucination'/'unverifiable'이면 호출자가 이미
    Finding을 만들었을 것이므로 여기서는 verified/metadata_error인 경우만 처리.
    """
    if verified_ref.status in ("hallucination", "unverifiable"):
        return None

    source_text = verified_ref.full_text or verified_ref.abstract
    if not source_text:
        # 🔒 접근 불가
        return Finding(
            id=f"find_{citation.id}",
            citation_id=citation.id,
            reference_id=verified_ref.reference.id,
            category="paywalled",
            error_type=None,
            severity=1,
            confidence="low",
            draft_claim_quote=citation.containing_sentence,
            source_evidence_quote=None,
            explanation="원문 전문·초록 모두 접근 불가. 수동 확인 권장.",
            suggestion=None,
        )

    system = _PROMPT_PATH.read_text(encoding="utf-8")
    user = (
        f"DRAFT CLAIM:\n{citation.surrounding_paragraph}\n\n"
        f"CITED REFERENCE:\n"
        f"{_ref_summary(verified_ref)}\n\n"
        f"SOURCE TEXT ({'FULL' if verified_ref.full_text else 'ABSTRACT ONLY'}):\n{source_text}"
    )

    attempts = 0
    last_result: dict | None = None
    while attempts <= max_evidence_retries:
        result, _ = await llm.complete_json(
            model=model,
            system=system,
            user=user,
            response_schema=CONTENT_VERIFY_SCHEMA,
            temperature=0.2 if attempts == 0 else 0.0,
        )
        last_result = result
        quote = result.get("source_evidence_quote", "")
        if quote_exists_in_source(quote, source_text):
            break
        attempts += 1

    assert last_result is not None
    category = last_result["category"]
    if category == "none":
        return None

    # 증거 검증이 끝내 실패한 경우 → confidence low + quote 비움
    quote = last_result.get("source_evidence_quote", "")
    evidence_valid = quote_exists_in_source(quote, source_text)
    confidence = last_result["confidence"] if evidence_valid else "low"
    final_quote = quote if evidence_valid else None

    # access_level이 abstract_only면 partial_verified 태그로 강등
    base_category = category
    if verified_ref.access_level == "abstract_only" and base_category != "none":
        # 카테고리는 그대로 두되, confidence를 한 단계 낮춤
        confidence = "low" if confidence == "medium" else confidence

    return Finding(
        id=f"find_{citation.id}",
        citation_id=citation.id,
        reference_id=verified_ref.reference.id,
        category=base_category,
        error_type=last_result.get("error_type"),
        severity=int(last_result["severity"]),
        confidence=confidence,
        draft_claim_quote=citation.containing_sentence,
        source_evidence_quote=final_quote,
        explanation=last_result["explanation"],
        suggestion=last_result.get("suggestion"),
    )


def _ref_summary(vref: VerifiedReference) -> str:
    r = vref.canonical or vref.reference
    authors = ", ".join(a.family for a in r.authors)
    return f"{authors} ({r.year}). {r.title}. {r.journal or ''}"
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/integration/test_content_verify.py -v
```

Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/verify/content.py tests/integration/test_content_verify.py
git commit -m "feat(verify): add content verification with evidence validation"
```

---

## Task 22: Content Verify 오케스트레이터 (병렬)

**Files:**
- Modify: `src/refcheck/verify/content.py` (add `verify_all_content`)
- Test: `tests/integration/test_content_verify.py` (add tests)

- [ ] **Step 1: 실패 테스트 추가**

`tests/integration/test_content_verify.py`에 추가:

```python
@pytest.mark.asyncio
async def test_verify_all_content_parallel():
    from refcheck.verify.content import verify_all_content

    cit1 = _cit()
    cit2 = Citation(
        id="cit_002", surface="(X, 2020)", ref_ids=["ref_001"],
        char_offset=100, containing_sentence="Good citation.",
        surrounding_paragraph="Good citation.",
    )

    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.complete_json = AsyncMock(return_value=(
        {"category": "none", "error_type": None, "severity": 1,
         "confidence": "high", "source_evidence_quote": "",
         "explanation": "ok", "suggestion": None},
        LLMUsage(model="gpt-5.4-thinking", prompt_tokens=100, completion_tokens=20, cost_usd=0.001),
    ))

    findings = await verify_all_content(
        [cit1, cit2], [_vref_with_abstract()], llm=mock_llm, concurrency=2,
    )
    assert findings == []  # 둘 다 category=none
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/integration/test_content_verify.py::test_verify_all_content_parallel -v
```

Expected: FAIL

- [ ] **Step 3: 구현 추가**

`src/refcheck/verify/content.py` 하단에 추가:

```python
import asyncio


async def verify_all_content(
    citations: list[Citation],
    verified_refs: list[VerifiedReference],
    *,
    llm: LLMClient,
    model: str = "gpt-5.4-thinking",
    concurrency: int = 5,
) -> list[Finding]:
    """모든 citation을 병렬로 검증. 각 citation이 여러 ref를 가리키면 각 ref별로 finding 생성."""
    vref_by_id = {v.reference.id: v for v in verified_refs}
    sem = asyncio.Semaphore(concurrency)

    async def _worker(cit: Citation, ref_id: str) -> Finding | None:
        vref = vref_by_id.get(ref_id)
        if vref is None:
            return None
        async with sem:
            return await verify_citation(cit, vref, llm=llm, model=model)

    tasks = []
    for cit in citations:
        for ref_id in cit.ref_ids:
            tasks.append(_worker(cit, ref_id))

    results = await asyncio.gather(*tasks)
    return [f for f in results if f is not None]
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/integration/test_content_verify.py -v
```

Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/verify/content.py tests/integration/test_content_verify.py
git commit -m "feat(verify): add parallel content verification orchestrator"
```

---

## Task 23: Finding Aggregator (리포트 조립)

**Files:**
- Create: `src/refcheck/report/aggregator.py`
- Test: `tests/unit/test_aggregator.py`

**책임:** `VerifiedReference` + Content `Finding` + orphan 정보 → `DraftReport` 조립. 정렬, 개수 집계, 수동 확인 리스트.

- [ ] **Step 1: 실패 테스트**

`tests/unit/test_aggregator.py`:

```python
from refcheck.report.aggregator import build_draft_report
from refcheck.schema.models import (
    VerifiedReference, Reference, Author, Citation, Finding, ReportMetadata,
)


def _ref(id_, title="T"):
    return Reference(id=id_, authors=[Author(family="X")], year=2020,
                     title=title, raw_text="...", style_detected="APA")


def _vref(status, id_="r1", access="abstract_only"):
    r = _ref(id_)
    return VerifiedReference(
        reference=r,
        status=status,
        canonical=r if status != "hallucination" else None,
        access_level=access,
    )


def test_counts_by_status():
    vrefs = [_vref("verified", "r1"), _vref("hallucination", "r2"),
             _vref("metadata_error", "r3"), _vref("unverifiable", "r4")]
    report = build_draft_report(
        verified_refs=vrefs,
        content_findings=[],
        citations=[],
        orphan_citations=[],
        orphan_references=[],
        metadata=ReportMetadata(
            draft_title="t", processing_seconds=1.0, total_usd_cost=0.1,
            verification_level="precise",
        ),
    )
    assert report.summary_counts["verified"] == 1
    assert report.summary_counts["hallucination"] == 1
    assert report.summary_counts["metadata_error"] == 1
    assert report.summary_counts["unverifiable"] == 1


def test_hallucination_generates_finding():
    vref = _vref("hallucination", "r1")
    citations = [Citation(id="c1", surface="(X, 2020)", ref_ids=["r1"],
                          char_offset=0, containing_sentence="...", surrounding_paragraph="...")]
    report = build_draft_report(
        verified_refs=[vref], content_findings=[], citations=citations,
        orphan_citations=[], orphan_references=[],
        metadata=ReportMetadata(draft_title="t", processing_seconds=1.0,
                                total_usd_cost=0.1, verification_level="precise"),
    )
    hall = [f for f in report.findings if f.category == "hallucination"]
    assert len(hall) == 1
    assert hall[0].severity == 5
    assert hall[0].reference_id == "r1"


def test_sorts_by_severity_desc():
    f1 = Finding(id="f1", citation_id="c1", reference_id="r1", category="content_mismatch",
                 error_type="minor", severity=2, confidence="high",
                 draft_claim_quote="a", explanation="a", suggestion=None)
    f2 = Finding(id="f2", citation_id="c2", reference_id="r2", category="content_mismatch",
                 error_type="major", severity=5, confidence="high",
                 draft_claim_quote="b", explanation="b", suggestion=None)
    report = build_draft_report(
        verified_refs=[], content_findings=[f1, f2], citations=[],
        orphan_citations=[], orphan_references=[],
        metadata=ReportMetadata(draft_title="t", processing_seconds=1.0,
                                total_usd_cost=0.1, verification_level="precise"),
    )
    assert report.findings[0].severity == 5
    assert report.findings[1].severity == 2


def test_unverifiable_added_to_manual_review():
    vrefs = [_vref("unverifiable", "r1"), _vref("verified", "r2")]
    report = build_draft_report(
        verified_refs=vrefs, content_findings=[], citations=[],
        orphan_citations=[], orphan_references=[],
        metadata=ReportMetadata(draft_title="t", processing_seconds=1.0,
                                total_usd_cost=0.1, verification_level="precise"),
    )
    assert "r1" in report.unverified_manual_review
    assert "r2" not in report.unverified_manual_review
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/unit/test_aggregator.py -v
```

Expected: FAIL

- [ ] **Step 3: 구현**

`src/refcheck/report/aggregator.py`:

```python
from __future__ import annotations
from collections import Counter
from refcheck.schema.models import (
    VerifiedReference, Citation, Finding, DraftReport, ReportMetadata,
)


def build_draft_report(
    *,
    verified_refs: list[VerifiedReference],
    content_findings: list[Finding],
    citations: list[Citation],
    orphan_citations: list[str],
    orphan_references: list[str],
    metadata: ReportMetadata,
) -> DraftReport:
    findings: list[Finding] = []

    # 1. Hallucination / metadata_error / unverifiable → Finding
    vref_by_id = {v.reference.id: v for v in verified_refs}
    citations_by_ref: dict[str, list[Citation]] = {}
    for c in citations:
        for rid in c.ref_ids:
            citations_by_ref.setdefault(rid, []).append(c)

    for vref in verified_refs:
        rid = vref.reference.id
        related_cits = citations_by_ref.get(rid, [])
        if vref.status == "hallucination":
            for cit in related_cits or [_dummy_cit(rid)]:
                findings.append(Finding(
                    id=f"find_hall_{cit.id}",
                    citation_id=cit.id,
                    reference_id=rid,
                    category="hallucination",
                    error_type="fabricated_reference",
                    severity=5,
                    confidence="high",
                    draft_claim_quote=cit.containing_sentence,
                    source_evidence_quote=None,
                    explanation=(
                        f"참고문헌 '{vref.reference.raw_text[:80]}...'을 "
                        f"{len(vref.sources_checked)}개 DB에서 찾을 수 없습니다. 환각 의심."
                    ),
                    suggestion="해당 논문 존재 여부 직접 확인 후 삭제 또는 올바른 출처로 교체.",
                ))
        elif vref.status == "metadata_error":
            for cit in related_cits or [_dummy_cit(rid)]:
                diff_str = ", ".join(f"{k}: '{v[0]}' → '{v[1]}'" for k, v in vref.field_diffs.items())
                findings.append(Finding(
                    id=f"find_meta_{cit.id}",
                    citation_id=cit.id,
                    reference_id=rid,
                    category="metadata",
                    error_type="field_mismatch",
                    severity=3,
                    confidence="high",
                    draft_claim_quote=cit.containing_sentence,
                    source_evidence_quote=None,
                    explanation=f"메타데이터 불일치: {diff_str}",
                    suggestion="정확한 메타데이터로 교체.",
                ))

    # 2. Orphan citations (참고문헌 없음)
    for cit_id in orphan_citations:
        findings.append(Finding(
            id=f"find_orphan_cit_{cit_id}",
            citation_id=cit_id,
            reference_id="",
            category="citation_unmatched",
            error_type="orphan_citation",
            severity=3,
            confidence="high",
            draft_claim_quote="",
            source_evidence_quote=None,
            explanation="본문에서 인용되었으나 참고문헌 목록에 해당 항목 없음.",
            suggestion="참고문헌 추가 또는 인용 삭제.",
        ))

    # 3. Content findings (그대로 합침)
    findings.extend(content_findings)

    # 4. 정렬: severity DESC, confidence (high > medium > low)
    conf_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (-f.severity, conf_order.get(f.confidence, 3)))

    # 5. 요약 개수
    counts: Counter = Counter()
    for v in verified_refs:
        counts[v.status] += 1
    for v in verified_refs:
        counts[f"access_{v.access_level}"] += 1
    counts["orphan_citations"] = len(orphan_citations)
    counts["orphan_references"] = len(orphan_references)
    counts["findings_total"] = len(findings)

    # 6. 수동 확인 리스트
    manual = [
        v.reference.id for v in verified_refs
        if v.status == "unverifiable" or v.access_level == "paywalled"
    ]

    return DraftReport(
        metadata=metadata,
        summary_counts=dict(counts),
        findings=findings,
        references=verified_refs,
        unverified_manual_review=manual,
    )


def _dummy_cit(ref_id: str) -> Citation:
    return Citation(
        id=f"cit_unused_{ref_id}",
        surface="",
        ref_ids=[ref_id],
        char_offset=-1,
        containing_sentence="(참고문헌에만 존재, 본문 인용 없음)",
        surrounding_paragraph="",
    )
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/unit/test_aggregator.py -v
```

Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/report/aggregator.py tests/unit/test_aggregator.py
git commit -m "feat(report): add finding aggregator"
```

---

## Task 24: JSON Exporter

**Files:**
- Create: `src/refcheck/report/json_exporter.py`
- Test: `tests/unit/test_json_exporter.py`

- [ ] **Step 1: 실패 테스트**

`tests/unit/test_json_exporter.py`:

```python
import json
from refcheck.report.json_exporter import export_json
from refcheck.schema.models import DraftReport, ReportMetadata


def test_exports_valid_json():
    report = DraftReport(
        metadata=ReportMetadata(draft_title="t", processing_seconds=1.0,
                                total_usd_cost=0.1, verification_level="precise"),
        summary_counts={"verified": 5},
        findings=[],
        references=[],
        unverified_manual_review=[],
    )
    s = export_json(report)
    data = json.loads(s)
    assert data["metadata"]["draft_title"] == "t"
    assert data["summary_counts"]["verified"] == 5


def test_indented_and_utf8(tmp_path):
    from pathlib import Path
    report = DraftReport(
        metadata=ReportMetadata(draft_title="한글 제목", processing_seconds=1.0,
                                total_usd_cost=0.1, verification_level="precise"),
        summary_counts={}, findings=[], references=[], unverified_manual_review=[],
    )
    s = export_json(report)
    assert "한글 제목" in s  # ensure_ascii=False
    assert "\n" in s  # indented
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/unit/test_json_exporter.py -v
```

Expected: FAIL

- [ ] **Step 3: 구현**

`src/refcheck/report/json_exporter.py`:

```python
from __future__ import annotations
import json
from refcheck.schema.models import DraftReport


def export_json(report: DraftReport) -> str:
    return json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
    )
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/unit/test_json_exporter.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/report/json_exporter.py tests/unit/test_json_exporter.py
git commit -m "feat(report): add JSON exporter"
```

---

## Task 25: Markdown Exporter

**Files:**
- Create: `src/refcheck/report/markdown_exporter.py`
- Test: `tests/unit/test_markdown_exporter.py`

- [ ] **Step 1: 실패 테스트**

`tests/unit/test_markdown_exporter.py`:

```python
from refcheck.report.markdown_exporter import export_markdown
from refcheck.schema.models import (
    DraftReport, ReportMetadata, Finding, VerifiedReference, Reference, Author,
)


def _simple_report():
    finding = Finding(
        id="f1", citation_id="c1", reference_id="r1",
        category="hallucination", error_type="fabricated_reference",
        severity=5, confidence="high",
        draft_claim_quote="A claim (Fake, 2099).",
        source_evidence_quote=None,
        explanation="Not found in any DB.",
        suggestion="Remove.",
    )
    return DraftReport(
        metadata=ReportMetadata(draft_title="My Draft", processing_seconds=12.3,
                                total_usd_cost=1.23, verification_level="precise"),
        summary_counts={"verified": 5, "hallucination": 1, "findings_total": 1},
        findings=[finding],
        references=[],
        unverified_manual_review=[],
    )


def test_contains_header_and_summary():
    md = export_markdown(_simple_report())
    assert "# 참고문헌 검증 리포트" in md
    assert "My Draft" in md
    assert "verified" in md.lower() or "검증됨" in md


def test_includes_finding_details():
    md = export_markdown(_simple_report())
    assert "🔴" in md or "환각" in md
    assert "A claim (Fake, 2099)." in md
    assert "Severity" in md or "심각도" in md


def test_includes_limitation_banner():
    md = export_markdown(_simple_report())
    assert "보조 도구" in md
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/unit/test_markdown_exporter.py -v
```

Expected: FAIL

- [ ] **Step 3: 구현**

`src/refcheck/report/markdown_exporter.py`:

```python
from __future__ import annotations
from refcheck.schema.models import DraftReport, Finding


CATEGORY_ICONS = {
    "hallucination": "🔴 환각 의심",
    "metadata": "🟠 메타데이터 오류",
    "content_mismatch": "🟡 인용 내용 불일치",
    "weak_context": "🟢 맥락 약함",
    "partial_verified": "⚪ 부분 검증",
    "paywalled": "🔒 접근 불가",
    "unverifiable": "❓ 확인 불가",
    "citation_unmatched": "⚠️ 고아 인용",
}


def export_markdown(report: DraftReport) -> str:
    m = report.metadata
    lines: list[str] = []
    lines.append("# 참고문헌 검증 리포트\n")
    lines.append(f"- **문서**: {m.draft_title}")
    lines.append(f"- **처리 시간**: {m.processing_seconds:.1f}초")
    lines.append(f"- **비용**: ${m.total_usd_cost:.3f}")
    lines.append(f"- **검증 레벨**: {m.verification_level}\n")

    lines.append("## ⚠️ 이 리포트는 **보조 도구**입니다\n")
    lines.append(
        "모든 판정은 LLM·API 출력이며 오판 가능성이 있습니다. "
        "🟡/🟢/⚪/❓/🔒 항목은 사용자 최종 확인이 필수입니다.\n"
    )

    lines.append("## 요약\n")
    for k, v in report.summary_counts.items():
        lines.append(f"- `{k}`: {v}")
    lines.append("")

    if report.unverified_manual_review:
        lines.append("## 수동 확인 권장 참고문헌\n")
        for ref_id in report.unverified_manual_review:
            lines.append(f"- {ref_id}")
        lines.append("")

    lines.append("## 발견된 문제\n")
    if not report.findings:
        lines.append("문제 없음. ✅\n")
    else:
        for idx, f in enumerate(report.findings, start=1):
            lines.extend(_render_finding(idx, f))

    return "\n".join(lines)


def _render_finding(idx: int, f: Finding) -> list[str]:
    icon = CATEGORY_ICONS.get(f.category, f.category)
    out = [f"### Finding #{idx} — {icon}"]
    out.append(f"- **유형**: {f.error_type or '-'}")
    out.append(f"- **심각도**: {'●' * f.severity}{'○' * (5 - f.severity)}")
    out.append(f"- **신뢰도**: {f.confidence}")
    out.append(f"- **Citation ID**: {f.citation_id}")
    out.append(f"- **Reference ID**: {f.reference_id}")
    out.append("")
    out.append("**초안 인용 부분:**")
    out.append(f"> {f.draft_claim_quote}")
    out.append("")
    if f.source_evidence_quote:
        out.append("**원문 근거:**")
        out.append(f"> {f.source_evidence_quote}")
        out.append("")
    out.append(f"**설명:** {f.explanation}")
    if f.suggestion:
        out.append(f"**제안:** {f.suggestion}")
    out.append("")
    return out
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/unit/test_markdown_exporter.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/report/markdown_exporter.py tests/unit/test_markdown_exporter.py
git commit -m "feat(report): add Markdown exporter"
```

---

## Task 26: 파이프라인 오케스트레이터

**Files:**
- Create: `src/refcheck/pipeline.py`
- Test: `tests/integration/test_pipeline.py`

**책임:** 모든 단계를 하나로 연결. 사용자가 호출할 고수준 함수 제공.

- [ ] **Step 1: 실패 테스트 (단순 스모크 테스트)**

`tests/integration/test_pipeline.py`:

```python
from unittest.mock import AsyncMock, MagicMock
import pytest
from refcheck.pipeline import run_pipeline, PipelineConfig
from refcheck.llm.client import LLMClient, LLMUsage


@pytest.mark.asyncio
async def test_pipeline_returns_report_on_minimal_input(tmp_path, monkeypatch):
    # 입력 텍스트
    draft_text = (
        "Introduction\n\n"
        "Gambling disorder is serious (Potenza, 2013).\n\n"
        "References\n\n"
        "Potenza, M. N. (2013). Neurobiology of gambling. Journal X, 23(4), 660-667."
    )

    # LLM mock: reference_parser + citation_extractor + content_verify
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.total_cost_usd = 0.01
    mock_llm.complete_json = AsyncMock(side_effect=[
        # reference_parser
        ({"references": [{
            "id": "ref_001",
            "authors": [{"given": "M. N.", "family": "Potenza"}],
            "year": 2013, "title": "Neurobiology of gambling",
            "journal": "Journal X", "volume": "23", "issue": "4",
            "pages": "660-667", "doi": None,
            "raw_text": "Potenza, M. N. (2013). Neurobiology of gambling. Journal X, 23(4), 660-667.",
            "style_detected": "APA",
        }]}, LLMUsage("gpt-5.4-mini", 100, 50, 0.001)),
        # citation_extractor
        ({"citations": [{
            "id": "cit_0001", "surface": "(Potenza, 2013)", "ref_ids": ["ref_001"],
            "char_offset": 30,
            "containing_sentence": "Gambling disorder is serious (Potenza, 2013).",
            "surrounding_paragraph": "Gambling disorder is serious (Potenza, 2013).",
        }]}, LLMUsage("gpt-5.4-mini", 100, 50, 0.001)),
        # content_verify → no issue
        ({"category": "none", "error_type": None, "severity": 1,
          "confidence": "high", "source_evidence_quote": "",
          "explanation": "ok", "suggestion": None},
         LLMUsage("gpt-5.4-thinking", 100, 20, 0.001)),
    ])

    # API clients mock → verified
    from refcheck.schema.models import Reference, Author
    canonical = Reference(
        id="canonical", authors=[Author(given="M. N.", family="Potenza")],
        year=2013, title="Neurobiology of gambling",
        journal="Journal X", volume="23", issue="4", pages="660-667",
        doi="10.1016/x", raw_text="", style_detected="unknown",
    )
    crossref = MagicMock()
    crossref.lookup_doi = AsyncMock(return_value=None)
    crossref.search = AsyncMock(return_value=canonical)
    crossref.close = AsyncMock()

    openalex = MagicMock()
    openalex.search = AsyncMock(return_value=None)
    openalex.close = AsyncMock()

    semantic = MagicMock()
    semantic.search = AsyncMock(return_value=None)
    semantic.close = AsyncMock()

    pubmed = MagicMock()
    pubmed.search = AsyncMock(return_value=None)
    pubmed.close = AsyncMock()

    unpaywall = MagicMock()
    unpaywall.oa_pdf_url = AsyncMock(return_value=None)
    unpaywall.close = AsyncMock()

    config = PipelineConfig(
        cache_dir=tmp_path / "cache",
        verification_level="precise",
    )

    report = await run_pipeline(
        draft_text=draft_text,
        draft_title="test",
        config=config,
        llm=mock_llm,
        crossref=crossref,
        openalex=openalex,
        semantic_scholar=semantic,
        pubmed=pubmed,
        unpaywall=unpaywall,
    )

    assert report.metadata.draft_title == "test"
    assert report.summary_counts.get("verified", 0) >= 1 or report.summary_counts.get("metadata_error", 0) >= 1
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/integration/test_pipeline.py -v
```

Expected: FAIL

- [ ] **Step 3: 구현**

`src/refcheck/pipeline.py`:

```python
from __future__ import annotations
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from refcheck.schema.models import DraftReport, ReportMetadata
from refcheck.ingest.text_normalizer import normalize_text
from refcheck.ingest.section_splitter import split_body_and_references
from refcheck.extract.reference_parser import parse_references
from refcheck.extract.citation_extractor import extract_citations
from refcheck.extract.linker import check_orphans
from refcheck.verify.metadata import verify_all_references
from refcheck.fetch.source_fetcher import fetch_sources
from refcheck.verify.content import verify_all_content
from refcheck.report.aggregator import build_draft_report
from refcheck.llm.client import LLMClient
from refcheck.fetch.crossref import CrossrefClient
from refcheck.fetch.openalex import OpenAlexClient
from refcheck.fetch.semantic_scholar import SemanticScholarClient
from refcheck.fetch.pubmed import PubMedClient
from refcheck.fetch.unpaywall import UnpaywallClient


MODEL_MAP = {
    "fast":   {"extract": "gpt-5.4-mini", "content": "gpt-5.4"},
    "precise": {"extract": "gpt-5.4-mini", "content": "gpt-5.4-thinking"},
    "ultra":  {"extract": "gpt-5.4",      "content": "gpt-5.4-pro"},
}


@dataclass
class PipelineConfig:
    cache_dir: Path
    verification_level: Literal["fast", "precise", "ultra"] = "precise"
    concurrency: int = 5


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
) -> DraftReport:
    start = time.time()
    models = MODEL_MAP[config.verification_level]

    # 1. Normalize + split
    text = normalize_text(draft_text)
    body, refs_raw = split_body_and_references(text)

    # 2. Parse references + extract citations
    references = await parse_references(refs_raw, llm=llm, model=models["extract"])
    citations = await extract_citations(body, references, llm=llm, model=models["extract"])

    # 3. Check orphans
    orphan_cits, orphan_refs = check_orphans(citations, references)

    # 4. Metadata verify
    verified = await verify_all_references(
        references,
        crossref=crossref, openalex=openalex,
        semantic_scholar=semantic_scholar, pubmed=pubmed,
        concurrency=config.concurrency,
    )

    # 5. Source fetch (full text where possible)
    verified = await fetch_sources(
        verified, unpaywall=unpaywall,
        cache_dir=config.cache_dir,
        concurrency=config.concurrency,
    )

    # 6. Content verify (per citation, only for refs with status verified or metadata_error)
    findings = await verify_all_content(
        citations, verified, llm=llm,
        model=models["content"],
        concurrency=config.concurrency,
    )

    # 7. Aggregate report
    elapsed = time.time() - start
    metadata = ReportMetadata(
        draft_title=draft_title,
        processing_seconds=elapsed,
        total_usd_cost=llm.total_cost_usd,
        verification_level=config.verification_level,
    )
    return build_draft_report(
        verified_refs=verified,
        content_findings=findings,
        citations=citations,
        orphan_citations=orphan_cits,
        orphan_references=orphan_refs,
        metadata=metadata,
    )
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/integration/test_pipeline.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/pipeline.py tests/integration/test_pipeline.py
git commit -m "feat(pipeline): add end-to-end pipeline orchestrator"
```

---

## Task 27: CLI 진입점

**Files:**
- Create: `src/refcheck/cli.py`
- Create: `src/refcheck/__main__.py`
- Test: `tests/integration/test_cli.py`

- [ ] **Step 1: 실패 테스트**

`tests/integration/test_cli.py`:

```python
import subprocess
import sys
from pathlib import Path


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "refcheck", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "--input" in result.stdout or "input" in result.stdout.lower()


def test_cli_requires_input():
    result = subprocess.run(
        [sys.executable, "-m", "refcheck"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/integration/test_cli.py -v
```

Expected: FAIL

- [ ] **Step 3: `__main__.py` 작성**

`src/refcheck/__main__.py`:

```python
from refcheck.cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: CLI 구현**

`src/refcheck/cli.py`:

```python
from __future__ import annotations
import argparse
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from refcheck.pipeline import run_pipeline, PipelineConfig
from refcheck.ingest.pdf_reader import read_pdf
from refcheck.llm.client import LLMClient
from refcheck.fetch.crossref import CrossrefClient
from refcheck.fetch.openalex import OpenAlexClient
from refcheck.fetch.semantic_scholar import SemanticScholarClient
from refcheck.fetch.pubmed import PubMedClient
from refcheck.fetch.unpaywall import UnpaywallClient
from refcheck.report.json_exporter import export_json
from refcheck.report.markdown_exporter import export_markdown


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="refcheck", description="참고문헌 검증 도구")
    parser.add_argument("--input", "-i", required=True, type=Path, help="초안 PDF 또는 .txt 파일")
    parser.add_argument("--output", "-o", type=Path, default=Path("./refcheck_report"),
                        help="출력 기본 경로 (.json, .md 자동 생성)")
    parser.add_argument("--level", "-l", choices=["fast", "precise", "ultra"],
                        default="precise", help="검증 레벨")
    parser.add_argument("--cache-dir", type=Path, default=Path("./.cache"),
                        help="API 응답 캐시 디렉토리")
    args = parser.parse_args()

    # 1. Read input
    if args.input.suffix.lower() == ".pdf":
        draft_text = read_pdf(args.input)
    else:
        draft_text = args.input.read_text(encoding="utf-8")

    # 2. Env 체크
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY 환경변수가 필요합니다.", file=sys.stderr)
        sys.exit(2)

    unpaywall_email = os.getenv("UNPAYWALL_EMAIL")
    if not unpaywall_email:
        print("WARN: UNPAYWALL_EMAIL 미설정. OA PDF 자동 다운로드 스킵됨.", file=sys.stderr)
        unpaywall_email = "refcheck@example.com"

    # 3. Clients
    llm = LLMClient(api_key=api_key)
    crossref = CrossrefClient(user_agent=f"refcheck/0.1 (mailto:{unpaywall_email})")
    openalex = OpenAlexClient(mailto=unpaywall_email)
    semantic = SemanticScholarClient(api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY") or None)
    pubmed = PubMedClient()
    unpaywall = UnpaywallClient(email=unpaywall_email)

    # 4. Pipeline
    config = PipelineConfig(cache_dir=args.cache_dir, verification_level=args.level)

    async def _run():
        try:
            report = await run_pipeline(
                draft_text=draft_text,
                draft_title=args.input.name,
                config=config,
                llm=llm,
                crossref=crossref,
                openalex=openalex,
                semantic_scholar=semantic,
                pubmed=pubmed,
                unpaywall=unpaywall,
            )
        finally:
            await crossref.close()
            await openalex.close()
            await semantic.close()
            await pubmed.close()
            await unpaywall.close()
        return report

    report = asyncio.run(_run())

    # 5. Output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    json_path = args.output.with_suffix(".json")
    md_path = args.output.with_suffix(".md")
    json_path.write_text(export_json(report), encoding="utf-8")
    md_path.write_text(export_markdown(report), encoding="utf-8")

    print(f"✅ 리포트 생성 완료")
    print(f"  - JSON: {json_path}")
    print(f"  - Markdown: {md_path}")
    print(f"  - 처리 시간: {report.metadata.processing_seconds:.1f}초")
    print(f"  - 총 비용: ${report.metadata.total_usd_cost:.3f}")
    print(f"  - 발견된 문제: {report.summary_counts.get('findings_total', 0)}건")
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/integration/test_cli.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/refcheck/cli.py src/refcheck/__main__.py tests/integration/test_cli.py
git commit -m "feat(cli): add command-line entry point"
```

---

## Task 28: E2E 골든 테스트

**Files:**
- Create: `tests/e2e/test_e2e_injected_errors.py`
- Create: `tests/fixtures/drafts/injected_errors.txt`
- Create: `tests/fixtures/expected_reports/injected_errors_expected.json`

**책임:** 의도적으로 오류를 주입한 샘플 초안 → 파이프라인 실행 → 기대 finding들이 감지되는지 검증.

- [ ] **Step 1: 주입 오류 초안 작성**

`tests/fixtures/drafts/injected_errors.txt`:

```
Introduction

Gambling disorder (GD) is a behavioral addiction. Potenza et al. demonstrated that the ventral striatum shows hyperactivity in GD patients (Potenza, 2013). Additionally, a completely fabricated finding was reported by the fictional author (FakeAuthor, 2099) showing that bananas cure GD. Furthermore, the effect size for cognitive behavioral therapy was reported as d=0.8 (Smith, 2015).

References

Potenza, M. N. (2013). Neurobiology of gambling. Current Opinion in Neurobiology, 23(4), 660-667.
FakeAuthor, F. (2099). Bananas as a novel treatment for gambling disorder. Journal of Imaginary Medicine, 1(1), 1-1.
Smith, J. (2015). Cognitive behavioral therapy for gambling. Real Journal, 50(3), 200-210.
```

- [ ] **Step 2: 테스트 작성**

`tests/e2e/test_e2e_injected_errors.py`:

```python
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
import pytest
from refcheck.pipeline import run_pipeline, PipelineConfig
from refcheck.llm.client import LLMClient, LLMUsage
from refcheck.schema.models import Reference, Author


FIXTURE = Path(__file__).parent.parent / "fixtures" / "drafts" / "injected_errors.txt"


@pytest.mark.asyncio
async def test_detects_hallucination_and_content_mismatch(tmp_path):
    draft_text = FIXTURE.read_text(encoding="utf-8")

    # LLM scripted responses:
    # 1. Parse references (3 refs)
    # 2. Extract citations (3 citations)
    # 3. Content verify × 2 (only Potenza and Smith; FakeAuthor is hallucination, skipped)
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.total_cost_usd = 0.05

    ref_parsed = {"references": [
        {"id": "ref_001", "authors": [{"given": "M. N.", "family": "Potenza"}],
         "year": 2013, "title": "Neurobiology of gambling",
         "journal": "Current Opinion in Neurobiology", "volume": "23",
         "issue": "4", "pages": "660-667", "doi": None,
         "raw_text": "Potenza, M. N. (2013)...", "style_detected": "APA"},
        {"id": "ref_002", "authors": [{"given": "F.", "family": "FakeAuthor"}],
         "year": 2099, "title": "Bananas as a novel treatment for gambling disorder",
         "journal": "Journal of Imaginary Medicine", "volume": "1",
         "issue": "1", "pages": "1-1", "doi": None,
         "raw_text": "FakeAuthor, F. (2099)...", "style_detected": "APA"},
        {"id": "ref_003", "authors": [{"given": "J.", "family": "Smith"}],
         "year": 2015, "title": "Cognitive behavioral therapy for gambling",
         "journal": "Real Journal", "volume": "50",
         "issue": "3", "pages": "200-210", "doi": None,
         "raw_text": "Smith, J. (2015)...", "style_detected": "APA"},
    ]}

    cit_parsed = {"citations": [
        {"id": "cit_0001", "surface": "(Potenza, 2013)", "ref_ids": ["ref_001"],
         "char_offset": 150,
         "containing_sentence": "Potenza et al. demonstrated that the ventral striatum shows hyperactivity in GD patients (Potenza, 2013).",
         "surrounding_paragraph": "..."},
        {"id": "cit_0002", "surface": "(FakeAuthor, 2099)", "ref_ids": ["ref_002"],
         "char_offset": 300,
         "containing_sentence": "a completely fabricated finding was reported by the fictional author (FakeAuthor, 2099) showing that bananas cure GD.",
         "surrounding_paragraph": "..."},
        {"id": "cit_0003", "surface": "(Smith, 2015)", "ref_ids": ["ref_003"],
         "char_offset": 450,
         "containing_sentence": "the effect size for cognitive behavioral therapy was reported as d=0.8 (Smith, 2015).",
         "surrounding_paragraph": "..."},
    ]}

    # content verify: Potenza → no issue; Smith → number_distortion (d=0.5, not 0.8)
    content_potenza = {"category": "none", "error_type": None, "severity": 1,
                       "confidence": "high", "source_evidence_quote": "",
                       "explanation": "ok", "suggestion": None}
    content_smith = {"category": "content_mismatch", "error_type": "number_distortion",
                     "severity": 4, "confidence": "high",
                     "source_evidence_quote": "effect size d=0.5",
                     "explanation": "원문은 d=0.5, 초안은 d=0.8.",
                     "suggestion": "수치 교정."}

    mock_llm.complete_json = AsyncMock(side_effect=[
        (ref_parsed, LLMUsage("gpt-5.4-mini", 500, 200, 0.01)),
        (cit_parsed, LLMUsage("gpt-5.4-mini", 500, 200, 0.01)),
        (content_potenza, LLMUsage("gpt-5.4-thinking", 500, 50, 0.01)),
        (content_smith, LLMUsage("gpt-5.4-thinking", 500, 100, 0.01)),
    ])

    # API clients:
    #  - Potenza → found (verified)
    #  - FakeAuthor → all empty (hallucination)
    #  - Smith → found (verified)
    def _canonical_for(ref_id):
        if ref_id == "ref_001":
            return Reference(
                id="canonical", authors=[Author(family="Potenza")], year=2013,
                title="Neurobiology of gambling",
                journal="Current Opinion in Neurobiology",
                volume="23", issue="4", pages="660-667",
                doi="10.1016/x", raw_text="", style_detected="unknown",
            )
        if ref_id == "ref_003":
            return Reference(
                id="canonical", authors=[Author(family="Smith")], year=2015,
                title="Cognitive behavioral therapy for gambling",
                journal="Real Journal", volume="50", issue="3", pages="200-210",
                doi="10.1016/y", raw_text="", style_detected="unknown",
            )
        return None

    async def crossref_search(*, title, authors, year):
        if "Potenza" in (authors[0].family if authors else "") and year == 2013:
            return _canonical_for("ref_001")
        if "Smith" in (authors[0].family if authors else "") and year == 2015:
            return _canonical_for("ref_003")
        return None

    crossref = MagicMock()
    crossref.lookup_doi = AsyncMock(return_value=None)
    crossref.search = AsyncMock(side_effect=crossref_search)
    crossref.close = AsyncMock()

    from refcheck.fetch.openalex import OpenAlexResult
    async def openalex_search(*, title, authors, year):
        if "Potenza" in (authors[0].family if authors else ""):
            return OpenAlexResult(
                reference=_canonical_for("ref_001"),
                abstract="Gambling disorder shows ventral striatum hyperactivity.",
                is_oa=False, oa_url=None,
            )
        if "Smith" in (authors[0].family if authors else ""):
            return OpenAlexResult(
                reference=_canonical_for("ref_003"),
                abstract="effect size d=0.5 for CBT in gambling.",
                is_oa=False, oa_url=None,
            )
        return None

    openalex = MagicMock()
    openalex.search = AsyncMock(side_effect=openalex_search)
    openalex.close = AsyncMock()

    semantic = MagicMock()
    semantic.search = AsyncMock(return_value=None)
    semantic.close = AsyncMock()

    pubmed = MagicMock()
    pubmed.search = AsyncMock(return_value=None)
    pubmed.close = AsyncMock()

    unpaywall = MagicMock()
    unpaywall.oa_pdf_url = AsyncMock(return_value=None)
    unpaywall.close = AsyncMock()

    config = PipelineConfig(cache_dir=tmp_path / "cache", verification_level="precise")

    report = await run_pipeline(
        draft_text=draft_text,
        draft_title="injected_errors",
        config=config,
        llm=mock_llm,
        crossref=crossref,
        openalex=openalex,
        semantic_scholar=semantic,
        pubmed=pubmed,
        unpaywall=unpaywall,
    )

    # 검증
    # 1. FakeAuthor → hallucination finding
    halls = [f for f in report.findings if f.category == "hallucination"]
    assert len(halls) == 1
    assert halls[0].reference_id == "ref_002"

    # 2. Smith → content_mismatch finding (number_distortion)
    content = [f for f in report.findings if f.category == "content_mismatch"]
    assert len(content) == 1
    assert content[0].error_type == "number_distortion"

    # 3. Potenza → no finding
    potenza_findings = [f for f in report.findings if f.reference_id == "ref_001"]
    assert potenza_findings == []
```

- [ ] **Step 3: 테스트 실행**

```bash
pytest tests/e2e/test_e2e_injected_errors.py -v
```

Expected: PASS

- [ ] **Step 4: 전체 테스트 스윕**

```bash
pytest -m "not slow and not live"
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/test_e2e_injected_errors.py tests/fixtures/drafts/injected_errors.txt
git commit -m "test(e2e): add golden test for injected-errors draft"
```

---

## Task 29: 실제 사용 문서화 (README)

**Files:**
- Create: `README.md`

**책임:** 실제 사용자가 도구를 설치·실행·확장할 수 있도록 최소 README.

- [ ] **Step 1: README 작성**

```markdown
# refcheck — LLM 학술 초안 참고문헌 검증 도구

## 설치

```bash
git clone <repo>
cd refcheck
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# .env 편집: OPENAI_API_KEY, UNPAYWALL_EMAIL 설정
```

## 사용

```bash
# PDF 입력
refcheck --input draft.pdf --output ./report --level precise

# 텍스트 입력
refcheck --input draft.txt --output ./report --level fast
```

출력: `report.json` (구조화 데이터), `report.md` (사람 친화적 리포트)

## 검증 레벨

- `fast`: gpt-5.4-mini + gpt-5.4, 논문당 ~$1~2, 2~3분
- `precise` (기본): gpt-5.4-mini + gpt-5.4-thinking, ~$3~5, 5~8분
- `ultra`: gpt-5.4 + gpt-5.4-pro, ~$8~12, 10~15분

## 테스트

```bash
pytest                      # 전체 (빠른 것만)
pytest -m slow              # 실 API 호출 포함
```

## 한계

이 도구는 **보조 도구**입니다. 모든 판정은 LLM·API 출력이며 오판 가능성이 있습니다.
특히 🟡 (인용 내용 불일치), 🟢 (맥락 약함), ⚪ (초록 기반), ❓ (확인 불가), 🔒 (접근 불가)
항목은 최종 사용자 확인이 필수입니다.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with installation and usage"
```

---

## 최종 검증

- [ ] **전체 테스트 실행**

```bash
pytest -m "not slow and not live" -v
```

Expected: 모든 테스트 PASS

- [ ] **샘플 실제 실행 (OPENAI_API_KEY 설정 후)**

```bash
# 준비된 샘플 텍스트로 CLI 실행
refcheck --input tests/fixtures/drafts/injected_errors.txt --output /tmp/refcheck_smoke --level fast
cat /tmp/refcheck_smoke.md
```

Expected: 
- `/tmp/refcheck_smoke.md` 파일 생성
- FakeAuthor(2099)는 🔴 환각으로 분류
- 리포트 상단 "보조 도구" 배너 확인

---

## Plan 2 예고

Plan 2에서 추가할 것:
- Streamlit UI (`app.py`) — 업로드, 진행 바, 결과 탭, 다운로드 버튼
- HTML 렌더러 (Streamlit 표시용 — side-by-side 근거 패널)
- PDF exporter (weasyprint)
- 비용 감시 UI (MAX_USD_PER_RUN 실시간 게이지)
- 중간 단계 재개 기능 UI (캐시 활용)
