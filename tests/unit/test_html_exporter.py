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
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html or "&#x27;" in html or "&lt;" in html
