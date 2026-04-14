from refcheck.report.markdown_exporter import export_markdown
from refcheck.schema.models import (
    DraftReport, ReportMetadata, Finding,
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


def test_includes_finding_details():
    md = export_markdown(_simple_report())
    assert "A claim (Fake, 2099)." in md


def test_includes_limitation_banner():
    md = export_markdown(_simple_report())
    assert "보조 도구" in md
