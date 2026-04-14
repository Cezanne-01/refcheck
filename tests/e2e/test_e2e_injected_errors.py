from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
import pytest
from refcheck.pipeline import run_pipeline, PipelineConfig
from refcheck.llm.client import LLMClient, LLMUsage
from refcheck.schema.models import Reference, Author


FIXTURE = Path(__file__).parent.parent / "fixtures" / "drafts" / "injected_errors.txt"


@pytest.mark.asyncio
async def test_detects_hallucination_and_content_mismatch(tmp_path):
    draft_text = FIXTURE.read_text(encoding="utf-8")

    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.total_cost_usd = 0.05

    ref_parsed = {"references": [
        {"id": "ref_001", "authors": [{"given": "M. N.", "family": "Potenza"}],
         "year": 2013, "title": "Neurobiology of gambling",
         "journal": "Current Opinion in Neurobiology", "volume": "23",
         "issue": "4", "pages": "660-667", "doi": None,
         "raw_text": "Potenza, M. N. (2013)...", "style_detected": "APA"},
        {"id": "ref_002", "authors": [{"given": "F.", "family": "FakeAuthor"}],
         "year": 2099, "title": "Bananas as a novel treatment for gambling disorder",
         "journal": "Journal of Imaginary Medicine", "volume": "1",
         "issue": "1", "pages": "1-1", "doi": None,
         "raw_text": "FakeAuthor, F. (2099)...", "style_detected": "APA"},
        {"id": "ref_003", "authors": [{"given": "J.", "family": "Smith"}],
         "year": 2015, "title": "Cognitive behavioral therapy for gambling",
         "journal": "Real Journal", "volume": "50",
         "issue": "3", "pages": "200-210", "doi": None,
         "raw_text": "Smith, J. (2015)...", "style_detected": "APA"},
    ]}

    cit_parsed = {"citations": [
        {"id": "cit_0001", "surface": "(Potenza, 2013)", "ref_ids": ["ref_001"],
         "char_offset": 150,
         "containing_sentence": "Potenza et al. demonstrated that the ventral striatum shows hyperactivity in GD patients (Potenza, 2013).",
         "surrounding_paragraph": "..."},
        {"id": "cit_0002", "surface": "(FakeAuthor, 2099)", "ref_ids": ["ref_002"],
         "char_offset": 300,
         "containing_sentence": "a completely fabricated finding was reported by the fictional author (FakeAuthor, 2099) showing that bananas cure GD.",
         "surrounding_paragraph": "..."},
        {"id": "cit_0003", "surface": "(Smith, 2015)", "ref_ids": ["ref_003"],
         "char_offset": 450,
         "containing_sentence": "the effect size for cognitive behavioral therapy was reported as d=0.8 (Smith, 2015).",
         "surrounding_paragraph": "..."},
    ]}

    content_potenza = {"category": "none", "error_type": None, "severity": 1,
                       "confidence": "high", "source_evidence_quote": "",
                       "explanation": "ok", "suggestion": None}
    content_smith = {"category": "content_mismatch", "error_type": "number_distortion",
                     "severity": 4, "confidence": "high",
                     "source_evidence_quote": "effect size d=0.5",
                     "explanation": "원문은 d=0.5, 초안은 d=0.8.",
                     "suggestion": "수치 교정."}

    mock_llm.complete_json = AsyncMock(side_effect=[
        (ref_parsed, LLMUsage("gpt-5.4-mini", 500, 200, 0.01)),
        (cit_parsed, LLMUsage("gpt-5.4-mini", 500, 200, 0.01)),
        (content_potenza, LLMUsage("gpt-5.4-thinking", 500, 50, 0.01)),
        (content_smith, LLMUsage("gpt-5.4-thinking", 500, 100, 0.01)),
    ])

    def _canonical_for(ref_id):
        if ref_id == "ref_001":
            return Reference(
                id="canonical", authors=[Author(family="Potenza")], year=2013,
                title="Neurobiology of gambling",
                journal="Current Opinion in Neurobiology",
                volume="23", issue="4", pages="660-667",
                doi="10.1016/x", raw_text="", style_detected="unknown",
            )
        if ref_id == "ref_003":
            return Reference(
                id="canonical", authors=[Author(family="Smith")], year=2015,
                title="Cognitive behavioral therapy for gambling",
                journal="Real Journal", volume="50", issue="3", pages="200-210",
                doi="10.1016/y", raw_text="", style_detected="unknown",
            )
        return None

    crossref = MagicMock()
    crossref.lookup_doi = AsyncMock(return_value=None)
    crossref.search = AsyncMock(return_value=None)
    crossref.close = AsyncMock()

    from refcheck.fetch.openalex import OpenAlexResult
    async def openalex_search(*, title, authors, year):
        if authors and "Potenza" in authors[0].family:
            return OpenAlexResult(
                reference=_canonical_for("ref_001"),
                abstract="Gambling disorder shows ventral striatum hyperactivity.",
                is_oa=False, oa_url=None,
            )
        if authors and "Smith" in authors[0].family:
            return OpenAlexResult(
                reference=_canonical_for("ref_003"),
                abstract="effect size d=0.5 for CBT in gambling.",
                is_oa=False, oa_url=None,
            )
        return None

    openalex = MagicMock()
    openalex.search = AsyncMock(side_effect=openalex_search)
    openalex.close = AsyncMock()

    semantic = MagicMock()
    semantic.search = AsyncMock(return_value=None)
    semantic.close = AsyncMock()

    pubmed = MagicMock()
    pubmed.search = AsyncMock(return_value=None)
    pubmed.close = AsyncMock()

    unpaywall = MagicMock()
    unpaywall.oa_pdf_url = AsyncMock(return_value=None)
    unpaywall.close = AsyncMock()

    config = PipelineConfig(cache_dir=tmp_path / "cache", verification_level="precise")

    report = await run_pipeline(
        draft_text=draft_text,
        draft_title="injected_errors",
        config=config,
        llm=mock_llm,
        crossref=crossref,
        openalex=openalex,
        semantic_scholar=semantic,
        pubmed=pubmed,
        unpaywall=unpaywall,
    )

    # 1. FakeAuthor → hallucination finding
    halls = [f for f in report.findings if f.category == "hallucination"]
    assert len(halls) == 1, f"Expected 1 hallucination, got {len(halls)}"
    assert halls[0].reference_id == "ref_002"

    # 2. Smith → content_mismatch (number_distortion)
    content = [f for f in report.findings if f.category == "content_mismatch"]
    assert len(content) == 1, f"Expected 1 content_mismatch, got {len(content)}"
    assert content[0].error_type == "number_distortion"

    # 3. Potenza → no finding
    potenza_findings = [f for f in report.findings if f.reference_id == "ref_001"]
    assert potenza_findings == [], f"Expected no Potenza findings, got {potenza_findings}"
