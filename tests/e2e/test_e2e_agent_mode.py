from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import json
import pytest
from refcheck.pipeline import run_pipeline, PipelineConfig
from refcheck.llm.client import LLMClient, LLMUsage
from refcheck.schema.models import (
    Reference, Author, VerifiedReference, Finding,
)


FIXTURE = Path(__file__).parent.parent / "fixtures" / "drafts" / "injected_errors.txt"


@pytest.mark.asyncio
async def test_agent_mode_detects_hallucination_and_mismatch(tmp_path):
    draft_text = FIXTURE.read_text(encoding="utf-8")

    # Stub the agentic verify functions to simulate agent output
    ref_potenza = Reference(
        id="ref_001", authors=[Author(given="M. N.", family="Potenza")], year=2013,
        title="Neurobiology of gambling", journal="Current Opinion in Neurobiology",
        doi="10.1016/j.conb.2013.01.020", raw_text="...", style_detected="APA",
    )
    ref_fake = Reference(
        id="ref_002", authors=[Author(given="F.", family="FakeAuthor")], year=2099,
        title="Bananas", raw_text="...", style_detected="APA",
    )
    ref_smith = Reference(
        id="ref_003", authors=[Author(given="J.", family="Smith")], year=2015,
        title="CBT for gambling", journal="Real Journal",
        doi="10.1016/x", raw_text="...", style_detected="APA",
    )

    async def _stub_metadata(refs, **kwargs):
        return [
            VerifiedReference(
                reference=ref_potenza, status="verified", canonical=ref_potenza,
                abstract="Ventral striatum hyperactive in gambling.", access_level="abstract_only",
            ),
            VerifiedReference(
                reference=ref_fake, status="hallucination", canonical=None,
                access_level="not_found", sources_checked=["agent"],
            ),
            VerifiedReference(
                reference=ref_smith, status="verified", canonical=ref_smith,
                abstract="Effect size d=0.5 for CBT.", access_level="abstract_only",
            ),
        ]

    async def _stub_content(cits, vrefs, **kwargs):
        return [
            Finding(
                id="find_cit0003", citation_id="cit_0003", reference_id="ref_003",
                category="content_mismatch", error_type="number_distortion",
                severity=4, confidence="high",
                draft_claim_quote="effect size d=0.8",
                source_evidence_quote="Effect size d=0.5",
                explanation="원문은 d=0.5, 초안은 d=0.8",
                suggestion="수치 교정",
            ),
        ]

    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.total_cost_usd = 0.25
    mock_llm.total_prompt_tokens = 1000
    mock_llm.total_completion_tokens = 500
    mock_llm.model_breakdown = {
        "gpt-5.4": {
            "prompt_tokens": 1000, "completion_tokens": 500,
            "cost_usd": 0.25, "calls": 5,
        },
    }
    mock_llm._client = MagicMock()
    mock_llm.complete_json = AsyncMock(side_effect=[
        # parse_references
        ({"references": [
            {"id": "ref_001", "authors": [{"given": "M. N.", "family": "Potenza"}],
             "year": 2013, "title": "Neurobiology of gambling",
             "journal": "Current Opinion in Neurobiology", "volume": "23",
             "issue": "4", "pages": "660-667", "doi": None,
             "raw_text": "Potenza, M. N. (2013)...", "style_detected": "APA"},
            {"id": "ref_002", "authors": [{"given": "F.", "family": "FakeAuthor"}],
             "year": 2099, "title": "Bananas",
             "journal": None, "volume": None,
             "issue": None, "pages": None, "doi": None,
             "raw_text": "FakeAuthor, F. (2099)...", "style_detected": "APA"},
            {"id": "ref_003", "authors": [{"given": "J.", "family": "Smith"}],
             "year": 2015, "title": "CBT for gambling",
             "journal": "Real Journal", "volume": "50",
             "issue": "3", "pages": "200-210", "doi": None,
             "raw_text": "Smith, J. (2015)...", "style_detected": "APA"},
        ]}, LLMUsage("gpt-5.4-mini", 500, 200, 0.01)),
        # extract_citations
        ({"citations": [
            {"id": "cit_0001", "surface": "(Potenza, 2013)", "ref_ids": ["ref_001"],
             "char_offset": 150,
             "containing_sentence": "hyperactivity (Potenza, 2013).",
             "surrounding_paragraph": "hyperactivity (Potenza, 2013)."},
            {"id": "cit_0002", "surface": "(FakeAuthor, 2099)", "ref_ids": ["ref_002"],
             "char_offset": 300,
             "containing_sentence": "bananas (FakeAuthor, 2099)",
             "surrounding_paragraph": "bananas (FakeAuthor, 2099)."},
            {"id": "cit_0003", "surface": "(Smith, 2015)", "ref_ids": ["ref_003"],
             "char_offset": 450,
             "containing_sentence": "d=0.8 (Smith, 2015).",
             "surrounding_paragraph": "d=0.8 (Smith, 2015)."},
        ]}, LLMUsage("gpt-5.4-mini", 500, 200, 0.01)),
    ])

    from refcheck.fetch.full_text import FullTextResult
    crossref = MagicMock(); crossref.close = AsyncMock()
    openalex = MagicMock(); openalex.close = AsyncMock()
    semantic = MagicMock(); semantic.close = AsyncMock()
    pubmed = MagicMock(); pubmed.close = AsyncMock()
    web_search = MagicMock(); web_search.close = AsyncMock()
    full_text = MagicMock(); full_text.close = AsyncMock()
    full_text.fetch = AsyncMock(return_value=FullTextResult(text=None, source="none"))

    with patch("refcheck.pipeline.verify_all_references_agent", side_effect=_stub_metadata), \
         patch("refcheck.pipeline.verify_all_content_agent", side_effect=_stub_content):
        config = PipelineConfig(
            cache_dir=tmp_path / "cache",
            verification_level="precise",
        )
        report = await run_pipeline(
            draft_text=draft_text, draft_title="test", config=config,
            llm=mock_llm, crossref=crossref, openalex=openalex,
            semantic_scholar=semantic, pubmed=pubmed,
            web_search=web_search, full_text_fetcher=full_text,
        )

    # FakeAuthor hallucination finding must exist
    halls = [f for f in report.findings if f.category == "hallucination"]
    assert len(halls) == 1
    assert halls[0].reference_id == "ref_002"

    # Smith content_mismatch finding must exist
    content = [f for f in report.findings if f.category == "content_mismatch"]
    assert len(content) == 1
    assert content[0].error_type == "number_distortion"
