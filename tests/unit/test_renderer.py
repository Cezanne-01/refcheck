"""Tests for the redesigned per-reference card renderer."""
from unittest.mock import MagicMock
from contextlib import contextmanager
from refcheck.ui.renderer import render_report
from refcheck.schema.models import (
    DraftReport, ReportMetadata, Finding,
    VerifiedReference, Reference, Author,
)


def _ref(rid: str, title: str, year: int, raw: str = "raw"):
    return Reference(
        id=rid, authors=[Author(family=f"A{rid}")], year=year,
        title=title, raw_text=raw, style_detected="APA",
    )


def _vref(*, reference, status, canonical=None, field_diffs=None, diff_severities=None, access_level="abstract_only"):
    return VerifiedReference(
        reference=reference,
        status=status,
        canonical=canonical or (reference if status != "hallucination" else None),
        field_diffs=field_diffs or {},
        diff_severities=diff_severities or {},
        access_level=access_level,
    )


def _meta():
    return ReportMetadata(
        draft_title="t", processing_seconds=5.0, total_usd_cost=1.5,
        verification_level="precise",
    )


def _make_st():
    """Build a MagicMock that handles st.columns + st.expander as context managers."""
    st = MagicMock()

    def _make_col():
        col = MagicMock()
        col.__enter__ = MagicMock(return_value=col)
        col.__exit__ = MagicMock(return_value=False)
        return col

    def _columns(n_or_spec):
        n = n_or_spec if isinstance(n_or_spec, int) else len(n_or_spec)
        return [_make_col() for _ in range(n)]

    st.columns.side_effect = _columns

    @contextmanager
    def _expander(label, expanded=False):
        yield st
    st.expander = MagicMock(side_effect=_expander)
    return st


def test_render_report_emits_title_and_banner():
    st = _make_st()
    report = DraftReport(
        metadata=_meta(), summary_counts={},
        findings=[], references=[], unverified_manual_review=[],
    )
    render_report(report, st=st)
    assert st.title.called
    assert st.warning.called


def test_render_report_renders_one_card_per_reference():
    st = _make_st()
    refs = [
        _vref(reference=_ref("r1", "Paper One", 2020), status="metadata_error",
              field_diffs={"year": ("2020", "2021")},
              diff_severities={"year": "info"}),
        _vref(reference=_ref("r2", "Paper Two", 2021), status="hallucination"),
    ]
    report = DraftReport(
        metadata=_meta(), summary_counts={}, findings=[], references=refs,
        unverified_manual_review=[],
    )
    render_report(report, st=st)

    md_text = " ".join(str(c) for c in st.markdown.call_args_list)
    assert "Paper One" in md_text
    assert "Paper Two" in md_text


def test_diff_table_shows_severity_color_for_critical_field():
    st = _make_st()
    ref = _ref("r1", "T", 2020)
    canon = Reference(
        id="canonical", authors=[Author(family="Other")], year=2020,
        title="T", raw_text="", style_detected="unknown",
    )
    refs = [
        _vref(
            reference=ref, status="metadata_error", canonical=canon,
            field_diffs={"authors": ("Smith", "Other")},
            diff_severities={"authors": "critical"},
        ),
    ]
    report = DraftReport(
        metadata=_meta(), summary_counts={}, findings=[], references=refs,
        unverified_manual_review=[],
    )
    render_report(report, st=st)

    md_text = " ".join(str(c) for c in st.markdown.call_args_list)
    # The critical-severity color (#c62828) is used for the row.
    assert "#c62828" in md_text


def test_content_findings_shown_with_extra_count():
    """When there are >2 content findings, '+N more' note is shown."""
    st = _make_st()
    ref = _ref("r1", "Paper", 2020)
    refs = [_vref(reference=ref, status="verified")]

    findings = [
        Finding(
            id=f"f{i}", citation_id=f"c{i}", reference_id="r1",
            category="content_mismatch", error_type="wrong_paper",
            severity=4, confidence="high",
            draft_claim_quote=f"draft {i}",
            source_evidence_quote=f"source {i}",
            explanation="explained",
            suggestion="fix it",
        )
        for i in range(4)
    ]

    report = DraftReport(
        metadata=_meta(), summary_counts={},
        findings=findings, references=refs, unverified_manual_review=[],
    )
    render_report(report, st=st)

    caption_text = " ".join(str(c) for c in st.caption.call_args_list)
    assert "추가" in caption_text or "JSON" in caption_text


def test_hallucination_card_shows_explainer():
    st = _make_st()
    ref = _ref("r1", "Fake Paper", 2099)
    refs = [_vref(reference=ref, status="hallucination", canonical=None,
                  access_level="not_found")]
    report = DraftReport(
        metadata=_meta(), summary_counts={}, findings=[], references=refs,
        unverified_manual_review=[],
    )
    render_report(report, st=st)
    assert st.error.called


def test_orphan_findings_rendered_separately():
    """Findings without a matching reference go in the orphan section."""
    st = _make_st()
    findings = [
        Finding(
            id="f1", citation_id="c1", reference_id="",
            category="citation_unmatched", error_type="orphan_citation",
            severity=3, confidence="high",
            draft_claim_quote="text", source_evidence_quote=None,
            explanation="orphan", suggestion="add ref",
        ),
    ]
    report = DraftReport(
        metadata=_meta(), summary_counts={},
        findings=findings, references=[], unverified_manual_review=[],
    )
    render_report(report, st=st)

    md_text = " ".join(str(c) for c in st.markdown.call_args_list)
    assert "고아" in md_text or "매칭" in md_text or "orphan" in md_text.lower()
