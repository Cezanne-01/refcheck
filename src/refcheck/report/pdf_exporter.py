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
