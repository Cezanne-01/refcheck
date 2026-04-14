import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture(autouse=True)
def _fake_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")
    monkeypatch.setenv("UNPAYWALL_EMAIL", "test@example.com")


def test_app_loads_without_error():
    at = AppTest.from_file("src/refcheck/ui/app.py", default_timeout=10)
    at.run()
    assert not at.exception


def test_app_shows_title():
    at = AppTest.from_file("src/refcheck/ui/app.py", default_timeout=10)
    at.run()
    assert any("refcheck" in str(t.value) for t in at.title)


def test_app_shows_upload_widget():
    at = AppTest.from_file("src/refcheck/ui/app.py", default_timeout=10)
    at.run()
    # file_uploader가 한 개 이상 있어야 함
    uploaders = getattr(at, "file_uploader", None) or []
    assert len(uploaders) >= 1


def test_app_shows_verification_level_selector():
    at = AppTest.from_file("src/refcheck/ui/app.py", default_timeout=10)
    at.run()
    # selectbox가 최소 1개 있어야 함 (verification level)
    assert len(at.selectbox) >= 1


def test_try_export_pdf_returns_none_when_exporter_fails(monkeypatch):
    """weasyprint 미설치 등으로 export_pdf가 PDFExportError를 raise하면 None 반환 — UI graceful degradation."""
    from refcheck.report.pdf_exporter import PDFExportError
    from refcheck.ui import app as app_module

    def _boom(_report):
        raise PDFExportError("weasyprint not available")

    monkeypatch.setattr("refcheck.report.pdf_exporter.export_pdf", _boom)

    from refcheck.schema.models import DraftReport, ReportMetadata
    report = DraftReport(
        metadata=ReportMetadata(draft_title="t", processing_seconds=1.0,
                                total_usd_cost=0.1, verification_level="precise"),
        summary_counts={}, findings=[], references=[], unverified_manual_review=[],
    )
    result = app_module._try_export_pdf(report)
    assert result is None
