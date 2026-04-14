from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
import pytest
import respx
from httpx import Response
from refcheck.schema.models import VerifiedReference, Reference, Author
from refcheck.fetch.source_fetcher import fetch_sources


def _vref(doi="10.1016/x", abstract=None, access_level="not_found"):
    return VerifiedReference(
        reference=Reference(
            id="ref_001", authors=[Author(family="X")], year=2020,
            title="T", doi=doi, raw_text="...", style_detected="APA",
        ),
        status="verified",
        canonical=Reference(
            id="canonical", authors=[Author(family="X")], year=2020,
            title="T", doi=doi, raw_text="", style_detected="unknown",
        ),
        abstract=abstract,
        access_level=access_level,
    )


@pytest.mark.asyncio
async def test_paywalled_when_no_oa(tmp_path):
    vref = _vref(abstract="Short abstract", access_level="abstract_only")
    unpaywall = MagicMock()
    unpaywall.oa_pdf_url = AsyncMock(return_value=None)

    result = await fetch_sources([vref], unpaywall=unpaywall, cache_dir=tmp_path)
    assert result[0].access_level == "abstract_only"


@pytest.mark.asyncio
async def test_marks_paywalled_when_no_abstract_no_oa(tmp_path):
    vref = _vref(abstract=None, access_level="not_found")
    unpaywall = MagicMock()
    unpaywall.oa_pdf_url = AsyncMock(return_value=None)
    result = await fetch_sources([vref], unpaywall=unpaywall, cache_dir=tmp_path)
    assert result[0].access_level == "paywalled"


@pytest.mark.asyncio
@respx.mock
async def test_downloads_full_text_when_oa(tmp_path):
    from reportlab.pdfgen import canvas
    pdf_path = tmp_path / "paper.pdf"
    c = canvas.Canvas(str(pdf_path))
    c.drawString(72, 750, "Full text content here")
    c.save()
    pdf_bytes = pdf_path.read_bytes()

    respx.get("https://example.com/paper.pdf").mock(
        return_value=Response(200, content=pdf_bytes, headers={"content-type": "application/pdf"})
    )

    vref = _vref(abstract="abs", access_level="abstract_only")
    unpaywall = MagicMock()
    unpaywall.oa_pdf_url = AsyncMock(return_value="https://example.com/paper.pdf")

    result = await fetch_sources([vref], unpaywall=unpaywall, cache_dir=tmp_path / "cache")
    assert result[0].access_level == "full_text"
    assert "Full text content" in (result[0].full_text or "")
