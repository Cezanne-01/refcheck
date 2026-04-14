# Reference Verification Tool — Plan 2: Streamlit UI + Exports

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Plan 1의 엔진 위에 Streamlit 로컬 웹 UI, HTML/PDF 리포트 출력, 실시간 진행 상황 표시를 추가한다.

**Architecture:** 엔진(Plan 1)은 순수 로직으로 두고, 그 위에 `refcheck.ui.*` 모듈로 Streamlit 앱을 구성. 파이프라인은 progress callback을 통해 UI와 소통. HTML/PDF는 markdown을 템플릿에 렌더해 생성.

**Tech Stack:** Streamlit 1.32+, weasyprint 62+ (HTML→PDF), Python markdown 3.6+. Plan 1의 기존 스택은 그대로 사용.

**Spec 참조:** [docs/superpowers/specs/2026-04-14-reference-verification-tool-design.md](../specs/2026-04-14-reference-verification-tool-design.md)
**Plan 1:** [2026-04-14-reference-verification-plan-1-core-pipeline.md](./2026-04-14-reference-verification-plan-1-core-pipeline.md)

---

## 파일 구조 (Plan 2 완료 시점)

```
refcheck/
├── pyproject.toml                 # +streamlit, +weasyprint, +markdown
├── src/refcheck/
│   ├── ...                        # Plan 1 모듈들 (수정: pipeline.py에 progress)
│   ├── report/
│   │   ├── html_exporter.py       # 신규: 스탠드얼론 HTML 리포트 (인쇄·공유용)
│   │   └── pdf_exporter.py        # 신규: HTML→PDF via weasyprint
│   └── ui/
│       ├── __init__.py
│       ├── app.py                 # 신규: Streamlit 엔트리
│       ├── progress.py            # 신규: ProgressEvent 프로토콜 + reporter
│       ├── widgets.py             # 신규: 업로드·설정 폼
│       ├── renderer.py            # 신규: DraftReport → Streamlit 위젯
│       └── templates/
│           └── report.html.j2     # 신규: PDF/HTML export용 템플릿
└── tests/
    ├── unit/
    │   ├── test_html_exporter.py
    │   ├── test_pdf_exporter.py
    │   ├── test_progress.py
    │   └── test_renderer.py
    ├── integration/
    │   └── test_streamlit_app.py
    └── fixtures/
        └── reports/
            └── sample_report.json  # 기존 DraftReport JSON 샘플
```

---

## Task 1: 의존성 추가 + Streamlit 스모크 테스트

**Files:**
- Modify: `pyproject.toml`
- Create: `src/refcheck/ui/__init__.py`
- Create: `src/refcheck/ui/app.py`
- Test: `tests/integration/test_streamlit_app.py`

- [ ] **Step 1: `pyproject.toml` 의존성 추가**

Edit `pyproject.toml` — `dependencies` 섹션에 추가:

```toml
dependencies = [
    # ... 기존 Plan 1 deps ...
    "streamlit>=1.32",
    "weasyprint>=62",
    "markdown>=3.6",
    "jinja2>=3.1",
]
```

`dev` 섹션은 변경 불필요 (pytest는 이미 있음).

- [ ] **Step 2: 의존성 설치 확인**

```bash
cd "/Users/park-yubin/Project/Reference check " && source .venv/bin/activate
pip install -e ".[dev]"
python -c "import streamlit, weasyprint, markdown, jinja2; print('OK')"
```

Expected: `OK`

**참고: macOS에서 weasyprint는 시스템 라이브러리 Cairo, Pango, GDK-PixBuf가 필요합니다:**

```bash
brew install cairo pango gdk-pixbuf libffi
```

설치가 안 되면 Step 2에서 import 에러 발생 — 사용자에게 brew 설치 안내.

- [ ] **Step 3: Streamlit 스모크 테스트 작성**

Create `src/refcheck/ui/app.py`:

```python
"""Streamlit entry point for refcheck.

Run: `streamlit run src/refcheck/ui/app.py`
"""
from __future__ import annotations
import streamlit as st


def main() -> None:
    st.set_page_config(page_title="refcheck", layout="wide")
    st.title("📚 refcheck — 참고문헌 검증")
    st.caption("LLM이 작성한 학술 문서 초안의 참고문헌·인용을 검증합니다.")
    st.info("초안을 업로드하고 '검증 시작' 버튼을 눌러주세요.")


if __name__ == "__main__":
    main()
```

Create `src/refcheck/ui/__init__.py`:

```python
```

(빈 파일)

Create `tests/integration/test_streamlit_app.py`:

```python
import pytest
from streamlit.testing.v1 import AppTest


def test_app_loads_without_error():
    at = AppTest.from_file("src/refcheck/ui/app.py", default_timeout=10)
    at.run()
    assert not at.exception


def test_app_shows_title():
    at = AppTest.from_file("src/refcheck/ui/app.py", default_timeout=10)
    at.run()
    assert any("refcheck" in str(t.value) for t in at.title)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/integration/test_streamlit_app.py -v
```

Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/refcheck/ui/ tests/integration/test_streamlit_app.py
git commit -m "feat(ui): add Streamlit app scaffolding"
```

---

## Task 2: Progress 이벤트 프로토콜

**Files:**
- Create: `src/refcheck/ui/progress.py`
- Test: `tests/unit/test_progress.py`

**책임:** 파이프라인 단계별 진행 상황을 UI로 전달하는 dataclass + 리스너 프로토콜. 엔진은 callback을 호출만 하고, UI는 callback을 구현해서 표시.

- [ ] **Step 1: 실패 테스트**

`tests/unit/test_progress.py`:

```python
from refcheck.ui.progress import ProgressEvent, ProgressReporter, Stage


def test_reporter_collects_events():
    events: list[ProgressEvent] = []
    reporter = ProgressReporter(callback=events.append)

    reporter.start(Stage.EXTRACT, total=10, message="참고문헌 파싱")
    reporter.update(Stage.EXTRACT, current=5)
    reporter.finish(Stage.EXTRACT)

    assert len(events) == 3
    assert events[0].stage == Stage.EXTRACT
    assert events[0].total == 10
    assert events[0].current == 0
    assert events[1].current == 5
    assert events[2].current == 10  # finish sets current=total


def test_reporter_noop_callback_does_not_raise():
    # None callback → reports are no-ops (safe for library code)
    reporter = ProgressReporter(callback=None)
    reporter.start(Stage.VERIFY_METADATA, total=5)
    reporter.update(Stage.VERIFY_METADATA, current=3)
    reporter.finish(Stage.VERIFY_METADATA)
    # no exceptions


def test_stage_labels_are_korean():
    assert "파싱" in Stage.EXTRACT.label or "추출" in Stage.EXTRACT.label
    assert "메타데이터" in Stage.VERIFY_METADATA.label
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd "/Users/park-yubin/Project/Reference check " && source .venv/bin/activate && pytest tests/unit/test_progress.py -v
```

Expected: FAIL (ImportError)

- [ ] **Step 3: 구현**

`src/refcheck/ui/progress.py`:

```python
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class Stage(Enum):
    """파이프라인 단계. 각 단계의 label은 UI 표시용 한국어."""
    INGEST = ("ingest", "문서 읽기")
    EXTRACT = ("extract", "참고문헌·인용 추출")
    VERIFY_METADATA = ("verify_metadata", "메타데이터 검증")
    FETCH_SOURCES = ("fetch_sources", "원문 확보")
    VERIFY_CONTENT = ("verify_content", "내용 검증")
    AGGREGATE = ("aggregate", "리포트 생성")

    def __init__(self, key: str, label: str):
        self.key = key
        self.label = label


@dataclass(frozen=True)
class ProgressEvent:
    stage: Stage
    current: int
    total: int
    message: str = ""


class ProgressReporter:
    """파이프라인이 호출하는 얇은 reporter. callback이 None이면 no-op."""

    def __init__(self, callback: Optional[Callable[[ProgressEvent], None]] = None):
        self._callback = callback
        self._current_totals: dict[Stage, int] = {}

    def _emit(self, event: ProgressEvent) -> None:
        if self._callback is not None:
            try:
                self._callback(event)
            except Exception:
                # UI 오류가 파이프라인을 중단시키지 않도록 swallow
                pass

    def start(self, stage: Stage, total: int, message: str = "") -> None:
        self._current_totals[stage] = total
        self._emit(ProgressEvent(stage=stage, current=0, total=total, message=message))

    def update(self, stage: Stage, current: int, message: str = "") -> None:
        total = self._current_totals.get(stage, 0)
        self._emit(ProgressEvent(stage=stage, current=current, total=total, message=message))

    def finish(self, stage: Stage, message: str = "") -> None:
        total = self._current_totals.get(stage, 0)
        self._emit(ProgressEvent(stage=stage, current=total, total=total, message=message))
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/unit/test_progress.py -v
```

Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/ui/progress.py tests/unit/test_progress.py
git commit -m "feat(ui): add progress event protocol"
```

---

## Task 3: Pipeline에 progress 계측

**Files:**
- Modify: `src/refcheck/pipeline.py`
- Test: `tests/integration/test_pipeline.py` (기존 파일에 새 테스트 추가)

**책임:** `run_pipeline`가 `progress` 인자를 받아 각 단계 시작/종료 시 이벤트 emit.

- [ ] **Step 1: 실패 테스트 추가**

Append to `tests/integration/test_pipeline.py`:

```python
@pytest.mark.asyncio
async def test_pipeline_emits_progress_events(tmp_path):
    from refcheck.ui.progress import ProgressReporter, ProgressEvent, Stage

    draft_text = (
        "Intro\n\nClaim (X, 2020).\n\n"
        "References\n\nX (2020). T. J, 1, 1-1."
    )

    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.total_cost_usd = 0.01
    mock_llm.complete_json = AsyncMock(side_effect=[
        ({"references": [{
            "id": "ref_001", "authors": [{"given": "X", "family": "X"}],
            "year": 2020, "title": "T", "journal": "J", "volume": "1",
            "issue": None, "pages": "1-1", "doi": None,
            "raw_text": "X (2020). T. J, 1, 1-1.", "style_detected": "APA",
        }]}, LLMUsage("gpt-5.4-mini", 100, 50, 0.001)),
        ({"citations": [{
            "id": "cit_0001", "surface": "(X, 2020)", "ref_ids": ["ref_001"],
            "char_offset": 6, "containing_sentence": "Claim (X, 2020).",
            "surrounding_paragraph": "Claim (X, 2020).",
        }]}, LLMUsage("gpt-5.4-mini", 100, 50, 0.001)),
        ({"category": "none", "error_type": None, "severity": 1,
          "confidence": "high", "source_evidence_quote": "",
          "explanation": "ok", "suggestion": None},
         LLMUsage("gpt-5.4-thinking", 100, 20, 0.001)),
    ])

    crossref = MagicMock()
    crossref.lookup_doi = AsyncMock(return_value=None)
    crossref.search = AsyncMock(return_value=None)
    crossref.close = AsyncMock()

    from refcheck.fetch.openalex import OpenAlexResult
    from refcheck.schema.models import Reference, Author
    openalex = MagicMock()
    openalex.search = AsyncMock(return_value=OpenAlexResult(
        reference=Reference(id="canonical", authors=[Author(family="X")], year=2020,
                            title="T", doi="10.1/y", raw_text="", style_detected="unknown"),
        abstract="abs", is_oa=False, oa_url=None,
    ))
    openalex.close = AsyncMock()
    semantic = MagicMock(); semantic.search = AsyncMock(return_value=None); semantic.close = AsyncMock()
    pubmed = MagicMock(); pubmed.search = AsyncMock(return_value=None); pubmed.close = AsyncMock()
    unpaywall = MagicMock(); unpaywall.oa_pdf_url = AsyncMock(return_value=None); unpaywall.close = AsyncMock()

    events: list[ProgressEvent] = []
    reporter = ProgressReporter(callback=events.append)
    config = PipelineConfig(cache_dir=tmp_path / "cache")

    await run_pipeline(
        draft_text=draft_text, draft_title="t", config=config,
        llm=mock_llm, crossref=crossref, openalex=openalex,
        semantic_scholar=semantic, pubmed=pubmed, unpaywall=unpaywall,
        progress=reporter,
    )

    # 각 단계가 최소 1회씩 start 이벤트를 emit해야 함
    stages_started = {e.stage for e in events if e.current == 0}
    assert Stage.EXTRACT in stages_started
    assert Stage.VERIFY_METADATA in stages_started
    assert Stage.VERIFY_CONTENT in stages_started
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/integration/test_pipeline.py::test_pipeline_emits_progress_events -v
```

Expected: FAIL (run_pipeline doesn't accept `progress` argument)

- [ ] **Step 3: 구현**

Modify `src/refcheck/pipeline.py` — add import, add `progress` param, instrument each stage.

Top of file, add import:

```python
from refcheck.ui.progress import ProgressReporter, Stage
```

Replace `run_pipeline` signature and body:

```python
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
    progress: ProgressReporter | None = None,
) -> DraftReport:
    start = time.time()
    models = MODEL_MAP[config.verification_level]
    reporter = progress or ProgressReporter()  # no-op if absent

    reporter.start(Stage.INGEST, total=1, message="본문 정규화")
    text = normalize_text(draft_text)
    body, refs_raw = split_body_and_references(text)
    reporter.finish(Stage.INGEST)

    reporter.start(Stage.EXTRACT, total=2, message="참고문헌·인용 추출")
    references = await parse_references(refs_raw, llm=llm, model=models["extract"])

    if len(references) == 0:
        raise ValueError(
            "참고문헌이 감지되지 않았습니다. 초안이 참고문헌 섹션을 포함하는지 확인하세요."
        )
    if len(references) > config.max_references:
        raise ValueError(
            f"참고문헌 수가 제한을 초과했습니다 ({len(references)} > {config.max_references}). "
            "초안을 분할하거나 --max-references 옵션으로 상한을 조정하세요."
        )
    if len(references) > config.warn_references:
        import warnings
        warnings.warn(
            f"참고문헌 수가 많습니다 ({len(references)} > {config.warn_references}). "
            "검증 시간·비용이 증가할 수 있습니다.",
            UserWarning,
            stacklevel=2,
        )

    reporter.update(Stage.EXTRACT, current=1, message=f"{len(references)}개 참고문헌 파싱됨")
    citations = await extract_citations(body, references, llm=llm, model=models["extract"])
    reporter.finish(Stage.EXTRACT, message=f"{len(citations)}개 인용 추출됨")

    orphan_cits, orphan_refs = check_orphans(citations, references)

    reporter.start(Stage.VERIFY_METADATA, total=len(references), message="4개 DB에서 메타데이터 검증")
    verified = await verify_all_references(
        references,
        crossref=crossref, openalex=openalex,
        semantic_scholar=semantic_scholar, pubmed=pubmed,
        concurrency=config.concurrency,
    )
    reporter.finish(Stage.VERIFY_METADATA)

    reporter.start(Stage.FETCH_SOURCES, total=len(verified), message="전문·초록 확보")
    verified = await fetch_sources(
        verified, unpaywall=unpaywall,
        cache_dir=config.cache_dir,
        concurrency=config.concurrency,
    )
    reporter.finish(Stage.FETCH_SOURCES)

    reporter.start(Stage.VERIFY_CONTENT, total=len(citations), message="LLM으로 인용 내용 검증")
    findings = await verify_all_content(
        citations, verified, llm=llm,
        model=models["content"],
        concurrency=config.concurrency,
    )
    reporter.finish(Stage.VERIFY_CONTENT, message=f"{len(findings)}개 발견사항")

    reporter.start(Stage.AGGREGATE, total=1)
    elapsed = time.time() - start
    metadata = ReportMetadata(
        draft_title=draft_title,
        processing_seconds=elapsed,
        total_usd_cost=llm.total_cost_usd,
        verification_level=config.verification_level,
    )
    report = build_draft_report(
        verified_refs=verified,
        content_findings=findings,
        citations=citations,
        orphan_citations=orphan_cits,
        orphan_references=orphan_refs,
        metadata=metadata,
    )
    reporter.finish(Stage.AGGREGATE)
    return report
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/integration/test_pipeline.py -v
pytest 2>&1 | tail -3
```

Expected: 모든 기존 + 새 테스트 PASS

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/pipeline.py tests/integration/test_pipeline.py
git commit -m "feat(pipeline): emit progress events through each stage"
```

---

## Task 4: HTML 템플릿 + HTML Exporter

**Files:**
- Create: `src/refcheck/ui/templates/report.html.j2`
- Create: `src/refcheck/report/html_exporter.py`
- Test: `tests/unit/test_html_exporter.py`

**책임:** `DraftReport` → 스탠드얼론 HTML 문자열. 인쇄·공유·PDF 변환 공통 입력.

- [ ] **Step 1: 실패 테스트**

`tests/unit/test_html_exporter.py`:

```python
from refcheck.report.html_exporter import export_html
from refcheck.schema.models import (
    DraftReport, ReportMetadata, Finding,
)


def _report_with_finding():
    f = Finding(
        id="f1", citation_id="c1", reference_id="r1",
        category="hallucination", error_type="fabricated_reference",
        severity=5, confidence="high",
        draft_claim_quote="Fake claim (Fake, 2099).",
        source_evidence_quote=None,
        explanation="환각 의심 — 어떤 DB에도 존재하지 않음.",
        suggestion="삭제 또는 교체.",
    )
    return DraftReport(
        metadata=ReportMetadata(
            draft_title="테스트 초안", processing_seconds=12.3,
            total_usd_cost=1.23, verification_level="precise",
        ),
        summary_counts={"verified": 5, "hallucination": 1, "findings_total": 1},
        findings=[f],
        references=[],
        unverified_manual_review=[],
    )


def test_html_is_valid_document():
    html = export_html(_report_with_finding())
    assert html.startswith("<!DOCTYPE html>") or html.startswith("<!doctype html>")
    assert "<html" in html
    assert "</html>" in html
    assert "테스트 초안" in html


def test_html_embeds_severity_icons():
    html = export_html(_report_with_finding())
    # 심각도별 시각적 아이콘이 포함되어야 함
    assert "●" in html or "critical" in html.lower() or "🔴" in html


def test_html_includes_limitation_banner():
    html = export_html(_report_with_finding())
    assert "보조 도구" in html


def test_html_escapes_user_content():
    f = Finding(
        id="f1", citation_id="c1", reference_id="r1",
        category="hallucination", error_type=None,
        severity=3, confidence="high",
        draft_claim_quote="<script>alert('xss')</script>",
        source_evidence_quote=None,
        explanation="test",
        suggestion=None,
    )
    report = DraftReport(
        metadata=ReportMetadata(
            draft_title="t", processing_seconds=1.0,
            total_usd_cost=0.1, verification_level="precise",
        ),
        summary_counts={}, findings=[f], references=[], unverified_manual_review=[],
    )
    html = export_html(report)
    # Raw script should be escaped
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html or "&#x27;" in html or "&lt;" in html
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd "/Users/park-yubin/Project/Reference check " && source .venv/bin/activate && pytest tests/unit/test_html_exporter.py -v
```

Expected: FAIL (ImportError)

- [ ] **Step 3: Jinja2 템플릿**

Create `src/refcheck/ui/templates/report.html.j2`:

```jinja2
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>참고문헌 검증 리포트 — {{ report.metadata.draft_title }}</title>
<style>
  body { font-family: -apple-system, "Apple SD Gothic Neo", sans-serif; max-width: 900px; margin: 2em auto; padding: 0 1em; color: #222; line-height: 1.5; }
  h1 { border-bottom: 2px solid #333; padding-bottom: 0.3em; }
  .banner { background: #fff3cd; border-left: 4px solid #ff9800; padding: 1em; margin: 1em 0; }
  .metadata { color: #666; font-size: 0.9em; margin-bottom: 1.5em; }
  .metadata span { margin-right: 1em; }
  .summary { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 0.8em; margin: 1em 0; }
  .summary-cell { border: 1px solid #ddd; border-radius: 4px; padding: 0.6em 0.8em; }
  .summary-cell .count { font-size: 1.6em; font-weight: 600; }
  .summary-cell .label { color: #777; font-size: 0.85em; }
  .finding { border: 1px solid #ddd; border-radius: 6px; margin: 1em 0; padding: 1em 1.2em; page-break-inside: avoid; }
  .finding-header { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid #eee; padding-bottom: 0.5em; margin-bottom: 0.6em; }
  .finding-header .category { font-weight: 600; font-size: 1.1em; }
  .finding-meta { color: #888; font-size: 0.85em; }
  .severity { letter-spacing: 2px; color: #c73e3e; }
  .confidence { color: #666; }
  blockquote { border-left: 3px solid #ccc; padding-left: 1em; margin: 0.5em 0; color: #444; }
  .evidence-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 1em; }
  @media (max-width: 700px) { .evidence-pair { grid-template-columns: 1fr; } }
  .evidence-pair h4 { margin: 0 0 0.3em; font-size: 0.9em; color: #555; text-transform: uppercase; letter-spacing: 0.05em; }
  .suggestion { background: #e8f5e9; padding: 0.6em 0.8em; border-radius: 4px; margin-top: 0.6em; }
  .cat-hallucination { border-left: 6px solid #c62828; }
  .cat-metadata { border-left: 6px solid #ef6c00; }
  .cat-content_mismatch { border-left: 6px solid #f9a825; }
  .cat-weak_context { border-left: 6px solid #558b2f; }
  .cat-partial_verified { border-left: 6px solid #9e9e9e; }
  .cat-paywalled { border-left: 6px solid #455a64; }
  .cat-unverifiable { border-left: 6px solid #6a1b9a; }
  .cat-citation_unmatched { border-left: 6px solid #0277bd; }
</style>
</head>
<body>
  <h1>참고문헌 검증 리포트</h1>
  <div class="metadata">
    <span><b>문서:</b> {{ report.metadata.draft_title }}</span>
    <span><b>처리 시간:</b> {{ "%.1f"|format(report.metadata.processing_seconds) }}초</span>
    <span><b>비용:</b> ${{ "%.3f"|format(report.metadata.total_usd_cost) }}</span>
    <span><b>검증 레벨:</b> {{ report.metadata.verification_level }}</span>
  </div>

  <div class="banner">
    <b>⚠️ 이 리포트는 보조 도구입니다.</b>
    모든 판정은 LLM·API 출력이며 오판 가능성이 있습니다.
    🟡/🟢/⚪/❓/🔒 항목은 최종 사용자 확인이 필수입니다.
  </div>

  <h2>요약</h2>
  <div class="summary">
    {% for k, v in report.summary_counts.items() %}
      <div class="summary-cell">
        <div class="count">{{ v }}</div>
        <div class="label">{{ k }}</div>
      </div>
    {% endfor %}
  </div>

  {% if report.unverified_manual_review %}
    <h2>수동 확인 권장</h2>
    <ul>
    {% for rid in report.unverified_manual_review %}
      <li>{{ rid }}</li>
    {% endfor %}
    </ul>
  {% endif %}

  <h2>발견된 문제 ({{ report.findings|length }}건)</h2>
  {% if not report.findings %}
    <p>문제 없음. ✅</p>
  {% endif %}
  {% for f in report.findings %}
    <div class="finding cat-{{ f.category }}">
      <div class="finding-header">
        <span class="category">{{ category_label(f.category) }}
          {% if f.error_type %} — {{ f.error_type }}{% endif %}
        </span>
        <span class="finding-meta">
          <span class="severity">{% for _ in range(f.severity) %}●{% endfor %}{% for _ in range(5 - f.severity) %}○{% endfor %}</span>
          <span class="confidence">신뢰도: {{ f.confidence }}</span>
        </span>
      </div>
      <div class="evidence-pair">
        <div>
          <h4>초안 인용</h4>
          <blockquote>{{ f.draft_claim_quote }}</blockquote>
        </div>
        {% if f.source_evidence_quote %}
        <div>
          <h4>원문 근거</h4>
          <blockquote>{{ f.source_evidence_quote }}</blockquote>
        </div>
        {% endif %}
      </div>
      <p>{{ f.explanation }}</p>
      {% if f.suggestion %}
        <div class="suggestion">💡 <b>제안:</b> {{ f.suggestion }}</div>
      {% endif %}
    </div>
  {% endfor %}
</body>
</html>
```

- [ ] **Step 4: 구현 (`src/refcheck/report/html_exporter.py`)**

```python
from __future__ import annotations
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from refcheck.schema.models import DraftReport


_TEMPLATE_DIR = Path(__file__).parent.parent / "ui" / "templates"


_CATEGORY_LABELS = {
    "hallucination": "🔴 환각 의심",
    "metadata": "🟠 메타데이터 오류",
    "content_mismatch": "🟡 인용 내용 불일치",
    "weak_context": "🟢 맥락 약함",
    "partial_verified": "⚪ 부분 검증",
    "paywalled": "🔒 접근 불가",
    "unverifiable": "❓ 확인 불가",
    "citation_unmatched": "⚠️ 고아 인용",
}


def _category_label(category: str) -> str:
    return _CATEGORY_LABELS.get(category, category)


def export_html(report: DraftReport) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "htm", "j2"]),
    )
    env.globals["category_label"] = _category_label
    template = env.get_template("report.html.j2")
    return template.render(report=report)
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/unit/test_html_exporter.py -v
```

Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add src/refcheck/report/html_exporter.py src/refcheck/ui/templates/ tests/unit/test_html_exporter.py
git commit -m "feat(report): add HTML exporter with Jinja2 template"
```

---

## Task 5: PDF Exporter (via weasyprint)

**Files:**
- Create: `src/refcheck/report/pdf_exporter.py`
- Test: `tests/unit/test_pdf_exporter.py`

**책임:** HTML 문자열 → PDF bytes. weasyprint가 시스템 폰트 탐지에 실패하면 graceful fallback.

- [ ] **Step 1: 실패 테스트**

`tests/unit/test_pdf_exporter.py`:

```python
import pytest
from refcheck.report.pdf_exporter import export_pdf, PDFExportError
from refcheck.schema.models import DraftReport, ReportMetadata


def _minimal_report():
    return DraftReport(
        metadata=ReportMetadata(draft_title="t", processing_seconds=1.0,
                                total_usd_cost=0.1, verification_level="precise"),
        summary_counts={}, findings=[], references=[], unverified_manual_review=[],
    )


def test_export_pdf_returns_bytes():
    pdf = export_pdf(_minimal_report())
    # PDF magic bytes
    assert pdf.startswith(b"%PDF-")


def test_export_pdf_is_readable():
    pdf = export_pdf(_minimal_report())
    assert len(pdf) > 1000  # at least a non-trivial PDF
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/unit/test_pdf_exporter.py -v
```

Expected: FAIL (ImportError)

- [ ] **Step 3: 구현 (`src/refcheck/report/pdf_exporter.py`)**

```python
from __future__ import annotations
from io import BytesIO
from refcheck.schema.models import DraftReport
from refcheck.report.html_exporter import export_html


class PDFExportError(Exception):
    pass


def export_pdf(report: DraftReport) -> bytes:
    """DraftReport → PDF bytes. weasyprint 필요 (cairo/pango 시스템 deps)."""
    try:
        from weasyprint import HTML
    except Exception as e:
        raise PDFExportError(
            f"weasyprint 로드 실패 ({e}). macOS: `brew install cairo pango gdk-pixbuf libffi`"
        ) from e

    html = export_html(report)
    try:
        buf = BytesIO()
        HTML(string=html).write_pdf(buf)
        return buf.getvalue()
    except Exception as e:
        raise PDFExportError(f"PDF 변환 실패: {e}") from e
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/unit/test_pdf_exporter.py -v
```

Expected: PASS (2 passed) — weasyprint 시스템 deps가 설치되지 않은 환경에서는 SKIP으로 처리하려면 pytest fixture로 조건부로 스킵. 일단 PASS 가정.

만약 `ModuleNotFoundError` 또는 libgobject 에러가 나면:

```bash
brew install cairo pango gdk-pixbuf libffi
pip install --force-reinstall weasyprint
```

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/report/pdf_exporter.py tests/unit/test_pdf_exporter.py
git commit -m "feat(report): add PDF exporter via weasyprint"
```

---

## Task 6: Streamlit Renderer (요약 + Finding 위젯)

**Files:**
- Create: `src/refcheck/ui/renderer.py`
- Test: `tests/unit/test_renderer.py`

**책임:** `DraftReport`를 Streamlit 네이티브 위젯(st.metric, st.expander, st.columns)으로 렌더.

- [ ] **Step 1: 실패 테스트**

`tests/unit/test_renderer.py`:

```python
from unittest.mock import MagicMock, call
from refcheck.ui.renderer import render_summary, render_findings, render_report
from refcheck.schema.models import (
    DraftReport, ReportMetadata, Finding,
)


def _sample_report():
    f = Finding(
        id="f1", citation_id="c1", reference_id="r1",
        category="hallucination", error_type="fabricated_reference",
        severity=5, confidence="high",
        draft_claim_quote="Fake (X, 2099).", source_evidence_quote=None,
        explanation="Not found.", suggestion="Remove.",
    )
    return DraftReport(
        metadata=ReportMetadata(
            draft_title="t", processing_seconds=5.0,
            total_usd_cost=1.5, verification_level="precise",
        ),
        summary_counts={"verified": 3, "hallucination": 1},
        findings=[f],
        references=[], unverified_manual_review=[],
    )


def test_render_summary_calls_st_metric():
    """Summary는 핵심 지표를 st.metric으로 표시."""
    st = MagicMock()
    # columns → list of col mocks
    st.columns.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
    render_summary(_sample_report(), st=st)
    # 최소 2회 이상의 metric 호출 (한 번은 col mock에서)
    all_metric_calls = sum(
        1 for c in st.columns.return_value if c.metric.called
    )
    assert all_metric_calls >= 2


def test_render_findings_groups_by_severity():
    """Findings는 심각도별로 그룹화되어 st.expander로 표시."""
    st = MagicMock()
    render_findings(_sample_report(), st=st)
    # st.expander가 한 번 이상 호출
    assert st.expander.called


def test_render_report_emits_title_and_banner():
    """전체 리포트 렌더러는 title + 경고 배너 emit."""
    st = MagicMock()
    st.columns.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
    render_report(_sample_report(), st=st)
    # title 호출
    assert st.title.called or st.header.called
    # 경고 배너 (warning/info/error 중 하나)
    assert st.warning.called or st.info.called or st.error.called
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/unit/test_renderer.py -v
```

Expected: FAIL (ImportError)

- [ ] **Step 3: 구현 (`src/refcheck/ui/renderer.py`)**

```python
from __future__ import annotations
from collections import defaultdict
from typing import Any
from refcheck.schema.models import DraftReport, Finding


CATEGORY_LABELS = {
    "hallucination": "🔴 환각 의심",
    "metadata": "🟠 메타데이터 오류",
    "content_mismatch": "🟡 인용 내용 불일치",
    "weak_context": "🟢 맥락 약함",
    "partial_verified": "⚪ 부분 검증",
    "paywalled": "🔒 접근 불가",
    "unverifiable": "❓ 확인 불가",
    "citation_unmatched": "⚠️ 고아 인용",
}

SEVERITY_LABEL = {5: "Critical", 4: "Major", 3: "Moderate", 2: "Minor", 1: "Info"}


def render_summary(report: DraftReport, *, st: Any) -> None:
    """상단 요약 대시보드 — 주요 지표 4개 + 카테고리별 카운트."""
    st.subheader("요약")

    cols = st.columns(4)
    cols[0].metric("처리 시간", f"{report.metadata.processing_seconds:.1f}초")
    cols[1].metric("총 비용", f"${report.metadata.total_usd_cost:.3f}")
    cols[2].metric("발견사항", report.summary_counts.get("findings_total", 0))
    cols[3].metric("검증 레벨", report.metadata.verification_level)

    st.markdown("**카테고리별 분포**")
    count_cols = st.columns(min(4, max(1, len(report.summary_counts))))
    for i, (k, v) in enumerate(report.summary_counts.items()):
        count_cols[i % len(count_cols)].metric(k, v)


def render_findings(report: DraftReport, *, st: Any) -> None:
    """Findings를 심각도별로 그룹화, expander로 표시."""
    st.subheader(f"발견된 문제 ({len(report.findings)}건)")

    if not report.findings:
        st.success("문제 없음. ✅")
        return

    grouped: dict[int, list[Finding]] = defaultdict(list)
    for f in report.findings:
        grouped[f.severity].append(f)

    for sev in sorted(grouped.keys(), reverse=True):
        st.markdown(f"### {SEVERITY_LABEL.get(sev, sev)} — {len(grouped[sev])}건")
        for idx, f in enumerate(grouped[sev], start=1):
            label = (
                f"{CATEGORY_LABELS.get(f.category, f.category)} — "
                f"{f.error_type or '-'} · 신뢰도: {f.confidence}"
            )
            with st.expander(label, expanded=(sev >= 4 and idx == 1)):
                _render_finding_body(f, st=st)


def _render_finding_body(f: Finding, *, st: Any) -> None:
    cols = st.columns(2)
    cols[0].markdown("**초안 인용**")
    cols[0].markdown(f"> {f.draft_claim_quote}")
    if f.source_evidence_quote:
        cols[1].markdown("**원문 근거**")
        cols[1].markdown(f"> {f.source_evidence_quote}")
    else:
        cols[1].markdown("**원문 근거**")
        cols[1].caption("_(제시된 근거 없음)_")

    st.markdown(f"**설명:** {f.explanation}")
    if f.suggestion:
        st.info(f"💡 **제안**: {f.suggestion}")

    st.caption(f"Citation: `{f.citation_id}` · Reference: `{f.reference_id}`")


def render_report(report: DraftReport, *, st: Any) -> None:
    """전체 리포트 렌더. UI 최상단에서 호출."""
    st.title("📚 검증 리포트")
    st.caption(f"**문서:** {report.metadata.draft_title}")

    st.warning(
        "⚠️ **이 리포트는 보조 도구입니다.** 모든 판정은 LLM·API 출력이며 오판 가능성이 있습니다. "
        "🟡/🟢/⚪/❓/🔒 항목은 최종 사용자 확인이 필수입니다."
    )

    render_summary(report, st=st)

    if report.unverified_manual_review:
        with st.expander(f"수동 확인 권장 참고문헌 ({len(report.unverified_manual_review)}개)"):
            for rid in report.unverified_manual_review:
                st.markdown(f"- `{rid}`")

    render_findings(report, st=st)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/unit/test_renderer.py -v
```

Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/ui/renderer.py tests/unit/test_renderer.py
git commit -m "feat(ui): add Streamlit report renderer"
```

---

## Task 7: Streamlit Upload + 설정 위젯

**Files:**
- Create: `src/refcheck/ui/widgets.py`

**책임:** 업로드·설정·환경변수 확인 UI 컴포넌트. 순수 UI이므로 단위 테스트는 하지 않고 Task 11에서 E2E 테스트.

- [ ] **Step 1: 구현 (`src/refcheck/ui/widgets.py`)**

```python
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class UploadResult:
    filename: str
    draft_text: str


@dataclass
class RunConfig:
    verification_level: str
    cache_dir: Path


def render_upload(st: Any) -> UploadResult | None:
    """파일 업로드 위젯. 반환값은 업로드 완료 시 UploadResult, 아니면 None."""
    uploaded = st.file_uploader(
        "초안 업로드 (PDF 또는 .txt)",
        type=["pdf", "txt"],
        help="LLM이 작성한 초안을 업로드하세요. 참고문헌 섹션이 포함되어야 합니다.",
    )
    if uploaded is None:
        return None

    try:
        if uploaded.name.lower().endswith(".pdf"):
            # PDF: 바이트 → 임시 파일 → pdf_reader
            from refcheck.ingest.pdf_reader import read_pdf, PDFReadError
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(uploaded.getvalue())
                tmp_path = Path(f.name)
            try:
                text = read_pdf(tmp_path)
            except PDFReadError as e:
                st.error(f"PDF 읽기 실패: {e}")
                return None
            finally:
                tmp_path.unlink(missing_ok=True)
        else:
            try:
                text = uploaded.getvalue().decode("utf-8")
            except UnicodeDecodeError:
                st.error("텍스트 파일은 UTF-8 인코딩이어야 합니다.")
                return None
    except Exception as e:
        st.error(f"파일 처리 중 오류: {e}")
        return None

    return UploadResult(filename=uploaded.name, draft_text=text)


def render_config(st: Any) -> RunConfig:
    """검증 레벨·캐시 디렉토리 선택."""
    st.subheader("⚙️ 검증 설정")
    col1, col2 = st.columns([2, 3])
    level = col1.selectbox(
        "검증 레벨",
        options=["fast", "precise", "ultra"],
        index=1,
        help=(
            "- **fast**: 빠른 검증 (비용 ~$1~2, 2~3분)\n"
            "- **precise**: 정밀 검증 (비용 ~$3~5, 5~8분) — 기본\n"
            "- **ultra**: 초정밀 (비용 ~$8~12, 10~15분)"
        ),
    )
    cache_dir_str = col2.text_input(
        "캐시 디렉토리",
        value="./.cache",
        help="API 응답·전문 PDF 캐시 위치. 재실행 시 속도 향상.",
    )
    return RunConfig(verification_level=level, cache_dir=Path(cache_dir_str))


def check_env_readiness(st: Any) -> bool:
    """OPENAI_API_KEY 등 필수 환경변수 체크. 부재 시 에러 표시 + False 반환."""
    missing: list[str] = []
    if not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    # UNPAYWALL_EMAIL은 optional (없으면 OA 다운로드만 스킵됨)

    if missing:
        st.error(
            f"환경변수 {', '.join(missing)}이(가) 설정되지 않았습니다. "
            "프로젝트 루트의 `.env` 파일을 확인하세요 (예시: `.env.example`)."
        )
        return False

    if not os.getenv("UNPAYWALL_EMAIL"):
        st.warning(
            "`UNPAYWALL_EMAIL`이 설정되지 않아 오픈 액세스 PDF 자동 다운로드는 스킵됩니다. "
            "메타데이터·초록 기반 검증은 정상 동작합니다."
        )
    return True
```

- [ ] **Step 2: Import 테스트**

```bash
cd "/Users/park-yubin/Project/Reference check " && source .venv/bin/activate
python -c "from refcheck.ui.widgets import render_upload, render_config, check_env_readiness; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/refcheck/ui/widgets.py
git commit -m "feat(ui): add upload/config/env widgets"
```

---

## Task 8: Streamlit App 메인 — Pipeline 실행 + Progress 표시

**Files:**
- Modify: `src/refcheck/ui/app.py`
- Test: `tests/integration/test_streamlit_app.py` (확장)

**책임:** 업로드 → 설정 → 실행 → 진행 바 → 리포트 표시. `st.status`를 사용해 단계별 진행 상황 표시.

- [ ] **Step 1: 실패 테스트 추가**

Append to `tests/integration/test_streamlit_app.py`:

```python
def test_app_shows_upload_widget():
    at = AppTest.from_file("src/refcheck/ui/app.py", default_timeout=10)
    at.run()
    # file_uploader가 한 개 있어야 함
    assert len(at.get("file_uploader") or []) >= 1


def test_app_shows_verification_level_selector():
    at = AppTest.from_file("src/refcheck/ui/app.py", default_timeout=10)
    at.run()
    # selectbox가 최소 1개 있어야 함 (verification level)
    assert len(at.selectbox) >= 1
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/integration/test_streamlit_app.py -v
```

Expected: 새 테스트 FAIL

- [ ] **Step 3: `app.py` 확장**

Replace `src/refcheck/ui/app.py`:

```python
"""Streamlit entry point for refcheck."""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from refcheck.pipeline import PipelineConfig, run_pipeline
from refcheck.llm.client import LLMClient
from refcheck.fetch.crossref import CrossrefClient
from refcheck.fetch.openalex import OpenAlexClient
from refcheck.fetch.semantic_scholar import SemanticScholarClient
from refcheck.fetch.pubmed import PubMedClient
from refcheck.fetch.unpaywall import UnpaywallClient
from refcheck.schema.models import DraftReport
from refcheck.ui.progress import ProgressReporter, ProgressEvent, Stage
from refcheck.ui.widgets import render_upload, render_config, check_env_readiness
from refcheck.ui.renderer import render_report


load_dotenv()


def main() -> None:
    st.set_page_config(page_title="refcheck", layout="wide", page_icon="📚")
    st.title("📚 refcheck — 참고문헌 검증")
    st.caption("LLM이 작성한 학술 문서 초안의 참고문헌·인용을 검증합니다.")

    # Session state
    if "report" not in st.session_state:
        st.session_state.report = None

    # 1. Env check
    if not check_env_readiness(st):
        return

    # 2. Upload + config
    col_up, col_cfg = st.columns([3, 2])
    with col_up:
        upload = render_upload(st)
    with col_cfg:
        config = render_config(st)

    # 3. Run button
    if upload is not None:
        st.success(f"✅ 업로드됨: **{upload.filename}** ({len(upload.draft_text):,}자)")
        if st.button("🚀 검증 시작", type="primary", use_container_width=True):
            _run_pipeline_with_progress(upload, config)

    # 4. Report display
    if st.session_state.report is not None:
        st.divider()
        render_report(st.session_state.report, st=st)


def _run_pipeline_with_progress(upload, config) -> None:
    """Pipeline을 동기적으로 실행하며 st.status로 진행 상황 표시."""
    with st.status("검증 중...", expanded=True) as status:
        stage_placeholders: dict[Stage, Any] = {}
        progress_bars: dict[Stage, Any] = {}

        def _on_event(event: ProgressEvent) -> None:
            key = event.stage.key
            if event.stage not in stage_placeholders:
                stage_placeholders[event.stage] = st.empty()
                progress_bars[event.stage] = st.progress(0, text=event.stage.label)
            ratio = (event.current / event.total) if event.total else 0.0
            label = f"**{event.stage.label}** — {event.current}/{event.total}"
            if event.message:
                label += f" · {event.message}"
            stage_placeholders[event.stage].markdown(label)
            progress_bars[event.stage].progress(ratio, text=event.stage.label)

        reporter = ProgressReporter(callback=_on_event)
        try:
            report = asyncio.run(_execute_pipeline(upload, config, reporter))
            st.session_state.report = report
            status.update(label="✅ 검증 완료", state="complete", expanded=False)
        except ValueError as e:
            status.update(label=f"❌ 검증 실패", state="error")
            st.error(str(e))
        except Exception as e:
            status.update(label=f"❌ 검증 실패", state="error")
            st.exception(e)


async def _execute_pipeline(upload, config, reporter: ProgressReporter) -> DraftReport:
    unpaywall_email = os.getenv("UNPAYWALL_EMAIL") or "refcheck@example.com"

    llm = LLMClient(api_key=os.getenv("OPENAI_API_KEY"))
    crossref = CrossrefClient(user_agent=f"refcheck/0.1 (mailto:{unpaywall_email})")
    openalex = OpenAlexClient(mailto=unpaywall_email)
    semantic = SemanticScholarClient(api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY") or None)
    pubmed = PubMedClient()
    unpaywall = UnpaywallClient(email=unpaywall_email)

    try:
        report = await run_pipeline(
            draft_text=upload.draft_text,
            draft_title=upload.filename,
            config=PipelineConfig(
                cache_dir=config.cache_dir,
                verification_level=config.verification_level,
            ),
            llm=llm,
            crossref=crossref,
            openalex=openalex,
            semantic_scholar=semantic,
            pubmed=pubmed,
            unpaywall=unpaywall,
            progress=reporter,
        )
    finally:
        await crossref.close()
        await openalex.close()
        await semantic.close()
        await pubmed.close()
        await unpaywall.close()
    return report


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 실행**

```bash
pytest tests/integration/test_streamlit_app.py -v
```

Expected: PASS (4 passed)

단, `test_app_shows_upload_widget`은 `check_env_readiness`가 `OPENAI_API_KEY` 없을 때 early return하기 때문에 실패할 수 있음. 해결책: 테스트에서 환경변수를 mock.

테스트가 실패하면 `tests/integration/test_streamlit_app.py` 상단에 fixture 추가:

```python
import pytest


@pytest.fixture(autouse=True)
def _fake_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")
    monkeypatch.setenv("UNPAYWALL_EMAIL", "test@example.com")
```

- [ ] **Step 5: Commit**

```bash
git add src/refcheck/ui/app.py tests/integration/test_streamlit_app.py
git commit -m "feat(ui): implement upload→run→progress→report flow"
```

---

## Task 9: 다운로드 버튼 (JSON / Markdown / HTML / PDF)

**Files:**
- Modify: `src/refcheck/ui/app.py`

**책임:** 리포트 하단에 4가지 포맷 다운로드 버튼 제공. 이미 존재하는 exporter들을 연결만.

- [ ] **Step 1: 버튼 추가**

Insert into `main()` — after `render_report(...)` call:

```python
    # 4. Report display
    if st.session_state.report is not None:
        st.divider()
        render_report(st.session_state.report, st=st)

        # 5. Download buttons
        _render_download_buttons(st.session_state.report)
```

Add helper function:

```python
def _render_download_buttons(report: DraftReport) -> None:
    from refcheck.report.json_exporter import export_json
    from refcheck.report.markdown_exporter import export_markdown
    from refcheck.report.html_exporter import export_html

    st.subheader("📥 리포트 다운로드")
    cols = st.columns(4)

    base = Path(report.metadata.draft_title).stem or "report"

    cols[0].download_button(
        "JSON",
        data=export_json(report),
        file_name=f"{base}.refcheck.json",
        mime="application/json",
        use_container_width=True,
    )
    cols[1].download_button(
        "Markdown",
        data=export_markdown(report),
        file_name=f"{base}.refcheck.md",
        mime="text/markdown",
        use_container_width=True,
    )
    cols[2].download_button(
        "HTML",
        data=export_html(report),
        file_name=f"{base}.refcheck.html",
        mime="text/html",
        use_container_width=True,
    )

    # PDF: weasyprint 시스템 deps가 없으면 에러 메시지 + disabled 버튼
    pdf_bytes = _try_export_pdf(report)
    if pdf_bytes is not None:
        cols[3].download_button(
            "PDF",
            data=pdf_bytes,
            file_name=f"{base}.refcheck.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    else:
        with cols[3]:
            st.button("PDF (사용 불가)", disabled=True, use_container_width=True,
                      help="weasyprint 시스템 deps 설치 필요: brew install cairo pango gdk-pixbuf libffi")


def _try_export_pdf(report: DraftReport) -> bytes | None:
    from refcheck.report.pdf_exporter import export_pdf, PDFExportError
    try:
        return export_pdf(report)
    except PDFExportError:
        return None
```

- [ ] **Step 2: 스모크 테스트**

```bash
cd "/Users/park-yubin/Project/Reference check " && source .venv/bin/activate
pytest tests/integration/test_streamlit_app.py -v
```

Expected: PASS (4 passed)

- [ ] **Step 3: Commit**

```bash
git add src/refcheck/ui/app.py
git commit -m "feat(ui): add JSON/Markdown/HTML/PDF download buttons"
```

---

## Task 10: README 업데이트 + 수동 E2E 체크리스트

**Files:**
- Modify: `README.md`
- Create: `docs/manual-test-checklist.md`

- [ ] **Step 1: README 업데이트**

Append to `README.md` (end of file):

```markdown

## Streamlit UI

CLI 외에도 웹 UI로 실행할 수 있습니다.

### 시스템 요구사항 (macOS)

PDF 다운로드에는 weasyprint가 필요하며, 다음 시스템 라이브러리를 먼저 설치해야 합니다:

``` bash
brew install cairo pango gdk-pixbuf libffi
```

### 실행

``` bash
streamlit run src/refcheck/ui/app.py
```

브라우저에서 http://localhost:8501 접속.

- 초안 PDF·TXT 업로드
- 검증 레벨 선택 (fast / precise / ultra)
- 실시간 단계별 진행 바
- 심각도별 접힌 Finding 목록 + side-by-side 근거 비교
- JSON / Markdown / HTML / PDF 리포트 다운로드
```

- [ ] **Step 2: 수동 E2E 체크리스트 작성**

Create `docs/manual-test-checklist.md`:

```markdown
# Manual E2E Test Checklist

Plan 1+2 전체 동작을 실제 API 호출로 검증합니다. 실행에 비용이 발생합니다 (테스트당 ~$1-3).

## 사전 준비

- [ ] `.env` 파일에 `OPENAI_API_KEY`, `UNPAYWALL_EMAIL` 설정
- [ ] `brew install cairo pango gdk-pixbuf libffi` 완료
- [ ] `pip install -e ".[dev]"` 완료
- [ ] `pytest` 통과 (단위·통합 테스트 모두 녹색)

## CLI 검증

- [ ] 빈 텍스트 파일 → 에러 메시지 명확 (섹션 분리 실패)
- [ ] 참고문헌 0개 → `ValueError("참고문헌이 감지되지 않았습니다")`
- [ ] 참고문헌 200개 초과 → `ValueError(제한 초과)`
- [ ] 정상 초안 (예: tests/fixtures/drafts/injected_errors.txt) → JSON + MD 생성 확인

## Streamlit UI 검증

- [ ] `streamlit run src/refcheck/ui/app.py` 서버 시작
- [ ] 홈에서 타이틀·배너 정상 표시
- [ ] OPENAI_API_KEY 없으면 에러 카드 표시 (+ `.env` 안내)
- [ ] .txt 업로드 → 업로드 성공 메시지 + 글자수 표시
- [ ] PDF 업로드 → 동일 동작 (스캔 PDF는 에러 메시지)
- [ ] 검증 레벨 드롭다운: fast / precise / ultra 선택 가능
- [ ] "검증 시작" 클릭 → st.status 열림
- [ ] 각 단계별 progress bar 업데이트 (ingest → extract → metadata → fetch → content → aggregate)
- [ ] 완료 후 요약 카드 + 심각도별 expander 표시
- [ ] 🔴 severity 5 expander는 기본 펼쳐짐
- [ ] 🟡 finding 클릭 시 side-by-side 근거 표시
- [ ] 수동 확인 권장 리스트가 있는 경우 접을 수 있음
- [ ] JSON 다운로드 → 파일 열어서 구조 확인
- [ ] Markdown 다운로드 → 한글 깨지지 않음
- [ ] HTML 다운로드 → 브라우저에서 스타일 정상
- [ ] PDF 다운로드 → Adobe/Preview에서 열림, 한글 정상 출력
- [ ] PDF 다운로드 (weasyprint 실패 환경): 버튼 disabled + 안내 메시지

## 오류 경로

- [ ] OpenAI API 키가 잘못됨 → 적절한 에러 메시지
- [ ] 네트워크 단절 중 실행 → retry 후 실패 메시지 (traceback 없이)
- [ ] 같은 초안 재실행 → 캐시 hit으로 API 호출 수 감소 (총 비용 표시로 확인)

## 품질 체크

- [ ] 실제 LLM 초안 (ChatGPT에게 의학 논문 초안 생성 요청) 1편 검증
  - 🔴 환각이 실제로 있으면 감지되는지
  - 🟡 인용 내용 불일치 사례가 잡히는지
  - 비용이 예상 범위 내인지
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/manual-test-checklist.md
git commit -m "docs: add Streamlit section and manual E2E checklist"
```

---

## 최종 검증

- [ ] **전체 테스트 실행**

```bash
cd "/Users/park-yubin/Project/Reference check " && source .venv/bin/activate
pytest -m "not slow and not live" 2>&1 | tail -3
```

Expected: 모든 테스트 PASS (Plan 1 86 + Plan 2 추가 약 12 = ~98개)

- [ ] **Streamlit 구동 확인**

```bash
streamlit run src/refcheck/ui/app.py
```

`http://localhost:8501`에서 앱이 정상 로드되고 업로드 UI가 보여야 함 (Ctrl+C로 종료).

- [ ] **수동 E2E 체크리스트 1회 실행**

`docs/manual-test-checklist.md`의 전체 항목을 실제 브라우저에서 통과 확인.

---

## Plan 2 완료 시 상태

- ✅ CLI (Plan 1) + Streamlit UI 모두 동작
- ✅ 실시간 progress UI (6단계 bar)
- ✅ JSON / Markdown / HTML / PDF 4가지 다운로드
- ✅ 심각도별 접이식 Finding + side-by-side 근거
- ✅ 모든 단위·통합 테스트 녹색
- ✅ 실제 API 호출 E2E 체크리스트로 수동 검증 완료
