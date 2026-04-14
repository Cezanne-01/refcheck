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
    assert pdf.startswith(b"%PDF-")


def test_export_pdf_is_readable():
    pdf = export_pdf(_minimal_report())
    assert len(pdf) > 1000
