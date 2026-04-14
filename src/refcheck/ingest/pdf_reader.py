from __future__ import annotations
from pathlib import Path
import pdfplumber
from pypdf import PdfReader


class PDFReadError(Exception):
    pass


def read_pdf(path: Path) -> str:
    """PDF → raw text. pdfplumber 우선, 실패 시 pypdf fallback."""
    if not path.exists():
        raise PDFReadError(f"파일을 찾을 수 없습니다: {path}")

    text = _try_pdfplumber(path)
    if not text.strip():
        text = _try_pypdf(path)

    if not text.strip():
        raise PDFReadError(
            "텍스트 추출 실패. 스캔 PDF(이미지만)일 가능성. "
            "텍스트 레이어가 있는 PDF로 재업로드하거나 OCR 후 시도하세요."
        )
    return text


def _try_pdfplumber(path: Path) -> str:
    try:
        with pdfplumber.open(path) as pdf:
            parts = [page.extract_text() or "" for page in pdf.pages]
        return "\n\n".join(parts)
    except Exception:
        return ""


def _try_pypdf(path: Path) -> str:
    try:
        reader = PdfReader(path)
        parts = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(parts)
    except Exception:
        return ""
