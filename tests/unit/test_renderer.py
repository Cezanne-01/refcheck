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


def test_render_findings_groups_by_reference():
    """Findings는 심각도별이 아닌 reference_id별로 그룹화되어야 한다."""
    from refcheck.schema.models import VerifiedReference, Reference, Author

    def _ref(rid, title, year):
        return Reference(id=rid, authors=[Author(family=f"A{rid}")], year=year,
                         title=title, raw_text="...", style_detected="APA")

    ref1 = _ref("r1", "Paper One", 2020)
    ref2 = _ref("r2", "Paper Two", 2021)
    vref1 = VerifiedReference(reference=ref1, status="verified", canonical=ref1,
                              access_level="abstract_only")
    vref2 = VerifiedReference(reference=ref2, status="metadata_error", canonical=ref2,
                              access_level="not_found")

    # 각 레퍼런스에 2건씩 총 4건 (여러 심각도)
    findings = [
        Finding(id="f1", citation_id="c1", reference_id="r1", category="content_mismatch",
                error_type="x", severity=5, confidence="high",
                draft_claim_quote="a", explanation="a", suggestion=None),
        Finding(id="f2", citation_id="c2", reference_id="r1", category="partial_verified",
                error_type="y", severity=1, confidence="low",
                draft_claim_quote="b", explanation="b", suggestion=None),
        Finding(id="f3", citation_id="c3", reference_id="r2", category="hallucination",
                error_type="z", severity=5, confidence="high",
                draft_claim_quote="c", explanation="c", suggestion=None),
        Finding(id="f4", citation_id="c4", reference_id="r2", category="metadata",
                error_type="w", severity=3, confidence="high",
                draft_claim_quote="d", explanation="d", suggestion=None),
    ]

    report = DraftReport(
        metadata=ReportMetadata(draft_title="t", processing_seconds=1.0,
                                total_usd_cost=0.1, verification_level="precise"),
        summary_counts={},
        findings=findings,
        references=[vref1, vref2],
        unverified_manual_review=[],
    )

    from unittest.mock import MagicMock
    st = MagicMock()
    render_findings(report, st=st)

    # 4 findings → 4 expander calls (not 4 severity groups).
    # More importantly, the markdown calls should include the paper titles.
    markdown_texts = " ".join(str(c) for c in st.markdown.call_args_list)
    assert "Paper One" in markdown_texts
    assert "Paper Two" in markdown_texts
    # Author names appear in header
    assert "Ar1" in markdown_texts or "Ar2" in markdown_texts
