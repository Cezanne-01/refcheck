from unittest.mock import MagicMock
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
    st.columns.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
    render_summary(_sample_report(), st=st)
    all_metric_calls = sum(
        1 for c in st.columns.return_value if c.metric.called
    )
    assert all_metric_calls >= 2


def test_render_findings_groups_by_severity():
    """Findings는 심각도별로 그룹화되어 st.expander로 표시."""
    st = MagicMock()
    render_findings(_sample_report(), st=st)
    assert st.expander.called


def test_render_report_emits_title_and_banner():
    """전체 리포트 렌더러는 title + 경고 배너 emit."""
    st = MagicMock()
    st.columns.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
    render_report(_sample_report(), st=st)
    assert st.title.called or st.header.called
    assert st.warning.called or st.info.called or st.error.called
