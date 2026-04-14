from pathlib import Path
import pytest
from refcheck.ingest.pdf_reader import read_pdf, PDFReadError


SAMPLE = Path(__file__).parent.parent / "fixtures" / "drafts" / "sample.pdf"


def test_reads_text_from_pdf():
    text = read_pdf(SAMPLE)
    assert "Gambling Disorder" in text
    assert "Potenza" in text


def test_raises_on_empty_or_missing_file(tmp_path):
    missing = tmp_path / "nonexistent.pdf"
    with pytest.raises(PDFReadError):
        read_pdf(missing)


def test_raises_on_image_only_pdf(tmp_path):
    # 빈 내용 (텍스트 추출 시 0자)
    from reportlab.pdfgen import canvas
    empty_pdf = tmp_path / "empty.pdf"
    c = canvas.Canvas(str(empty_pdf))
    c.showPage()  # 빈 페이지
    c.save()
    with pytest.raises(PDFReadError, match="텍스트 추출 실패"):
        read_pdf(empty_pdf)
