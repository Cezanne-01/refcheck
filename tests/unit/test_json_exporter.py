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


def test_indented_and_utf8():
    report = DraftReport(
        metadata=ReportMetadata(draft_title="한글 제목", processing_seconds=1.0,
                                total_usd_cost=0.1, verification_level="precise"),
        summary_counts={}, findings=[], references=[], unverified_manual_review=[],
    )
    s = export_json(report)
    assert "한글 제목" in s  # ensure_ascii=False
    assert "\n" in s  # indented
