from __future__ import annotations
from pathlib import Path


class PDFReadError(Exception):
    pass


def read_pdf(path: Path) -> str:
    """PDF → raw text.

    추출기 우선순위: pymupdf → pdfplumber → pypdf.
    pymupdf(fitz)가 레이아웃·읽기순서·폰트 ToUnicode 매핑(괄호/하이픈)에서 가장 안정적이라
    먼저 시도한다. 실패 시 pdfplumber, pypdf 순으로 fallback.
    """
    if not path.exists():
        raise PDFReadError(f"파일을 찾을 수 없습니다: {path}")

    for extractor in (_try_pymupdf, _try_pdfplumber, _try_pypdf):
        text = extractor(path)
        if text.strip():
            return text

    raise PDFReadError(
        "텍스트 추출 실패. 스캔 PDF(이미지만)일 가능성. "
        "텍스트 레이어가 있는 PDF로 재업로드하거나 OCR 후 시도하세요."
    )


def _try_pymupdf(path: Path) -> str:
    try:
        import fitz  # pymupdf
        with fitz.open(path) as doc:
            parts = [page.get_text() for page in doc]
        return "\n\n".join(parts)
    except Exception:
        return ""


def _try_pdfplumber(path: Path) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            parts = [page.extract_text() or "" for page in pdf.pages]
        return "\n\n".join(parts)
    except Exception:
        return ""


def _try_pypdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        parts = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(parts)
    except Exception:
        return ""
