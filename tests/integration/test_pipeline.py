from unittest.mock import AsyncMock, MagicMock
import pytest
from refcheck.pipeline import run_pipeline, PipelineConfig
from refcheck.llm.client import LLMClient, LLMUsage


@pytest.mark.asyncio
async def test_pipeline_returns_report_on_minimal_input(tmp_path):
    draft_text = (
        "Introduction\n\n"
        "Gambling disorder is serious (Potenza, 2013).\n\n"
        "References\n\n"
        "Potenza, M. N. (2013). Neurobiology of gambling. Journal X, 23(4), 660-667."
    )

    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.total_cost_usd = 0.01
    mock_llm.complete_json = AsyncMock(side_effect=[
        # reference_parser
        ({"references": [{
            "id": "ref_001",
            "authors": [{"given": "M. N.", "family": "Potenza"}],
            "year": 2013, "title": "Neurobiology of gambling",
            "journal": "Journal X", "volume": "23", "issue": "4",
            "pages": "660-667", "doi": None,
            "raw_text": "Potenza, M. N. (2013). Neurobiology of gambling. Journal X, 23(4), 660-667.",
            "style_detected": "APA",
        }]}, LLMUsage("gpt-5.4-mini", 100, 50, 0.001)),
        # citation_extractor
        ({"citations": [{
            "id": "cit_0001", "surface": "(Potenza, 2013)", "ref_ids": ["ref_001"],
            "char_offset": 30,
            "containing_sentence": "Gambling disorder is serious (Potenza, 2013).",
            "surrounding_paragraph": "Gambling disorder is serious (Potenza, 2013).",
        }]}, LLMUsage("gpt-5.4-mini", 100, 50, 0.001)),
        # content_verify → no issue
        ({"category": "none", "error_type": None, "severity": 1,
          "confidence": "high", "source_evidence_quote": "",
          "explanation": "ok", "suggestion": None},
         LLMUsage("gpt-5.4-thinking", 100, 20, 0.001)),
    ])

    from refcheck.schema.models import Reference, Author
    canonical = Reference(
        id="canonical", authors=[Author(given="M. N.", family="Potenza")],
        year=2013, title="Neurobiology of gambling",
        journal="Journal X", volume="23", issue="4", pages="660-667",
        doi="10.1016/x", raw_text="", style_detected="unknown",
    )
    crossref = MagicMock()
    crossref.lookup_doi = AsyncMock(return_value=None)
    crossref.search = AsyncMock(return_value=canonical)
    crossref.close = AsyncMock()

    openalex = MagicMock()
    openalex.search = AsyncMock(return_value=None)
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

    config = PipelineConfig(
        cache_dir=tmp_path / "cache",
        verification_level="precise",
    )

    report = await run_pipeline(
        draft_text=draft_text,
        draft_title="test",
        config=config,
        llm=mock_llm,
        crossref=crossref,
        openalex=openalex,
        semantic_scholar=semantic,
        pubmed=pubmed,
        unpaywall=unpaywall,
    )

    assert report.metadata.draft_title == "test"
    # Either verified (title matches) or metadata_error — both indicate pipeline reached verify stage
    assert (
        report.summary_counts.get("verified", 0) >= 1
        or report.summary_counts.get("metadata_error", 0) >= 1
    )


@pytest.mark.asyncio
async def test_pipeline_emits_progress_events(tmp_path):
    from refcheck.ui.progress import ProgressReporter, ProgressEvent, Stage

    draft_text = (
        "Intro\n\nClaim (X, 2020).\n\n"
        "References\n\nX (2020). T. J, 1, 1-1."
    )

    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.total_cost_usd = 0.01
    mock_llm.complete_json = AsyncMock(side_effect=[
        ({"references": [{
            "id": "ref_001", "authors": [{"given": "X", "family": "X"}],
            "year": 2020, "title": "T", "journal": "J", "volume": "1",
            "issue": None, "pages": "1-1", "doi": None,
            "raw_text": "X (2020). T. J, 1, 1-1.", "style_detected": "APA",
        }]}, LLMUsage("gpt-5.4-mini", 100, 50, 0.001)),
        ({"citations": [{
            "id": "cit_0001", "surface": "(X, 2020)", "ref_ids": ["ref_001"],
            "char_offset": 6, "containing_sentence": "Claim (X, 2020).",
            "surrounding_paragraph": "Claim (X, 2020).",
        }]}, LLMUsage("gpt-5.4-mini", 100, 50, 0.001)),
        ({"category": "none", "error_type": None, "severity": 1,
          "confidence": "high", "source_evidence_quote": "",
          "explanation": "ok", "suggestion": None},
         LLMUsage("gpt-5.4-thinking", 100, 20, 0.001)),
    ])

    crossref = MagicMock()
    crossref.lookup_doi = AsyncMock(return_value=None)
    crossref.search = AsyncMock(return_value=None)
    crossref.close = AsyncMock()

    from refcheck.fetch.openalex import OpenAlexResult
    from refcheck.schema.models import Reference, Author
    openalex = MagicMock()
    openalex.search = AsyncMock(return_value=OpenAlexResult(
        reference=Reference(id="canonical", authors=[Author(family="X")], year=2020,
                            title="T", doi="10.1/y", raw_text="", style_detected="unknown"),
        abstract="abs", is_oa=False, oa_url=None,
    ))
    openalex.close = AsyncMock()
    semantic = MagicMock(); semantic.search = AsyncMock(return_value=None); semantic.close = AsyncMock()
    pubmed = MagicMock(); pubmed.search = AsyncMock(return_value=None); pubmed.close = AsyncMock()
    unpaywall = MagicMock(); unpaywall.oa_pdf_url = AsyncMock(return_value=None); unpaywall.close = AsyncMock()

    events: list[ProgressEvent] = []
    reporter = ProgressReporter(callback=events.append)
    config = PipelineConfig(cache_dir=tmp_path / "cache")

    await run_pipeline(
        draft_text=draft_text, draft_title="t", config=config,
        llm=mock_llm, crossref=crossref, openalex=openalex,
        semantic_scholar=semantic, pubmed=pubmed, unpaywall=unpaywall,
        progress=reporter,
    )

    # 각 단계가 최소 1회씩 start 이벤트를 emit해야 함
    stages_started = {e.stage for e in events if e.current == 0}
    assert Stage.EXTRACT in stages_started
    assert Stage.VERIFY_METADATA in stages_started
    assert Stage.VERIFY_CONTENT in stages_started


@pytest.mark.asyncio
async def test_pipeline_uses_agents_when_flag_set(tmp_path):
    """use_agents=True → agent_metadata + agent_content 사용, 기존 함수는 호출 안 됨."""
    from unittest.mock import patch, AsyncMock

    draft_text = (
        "Intro.\n\nClaim (X, 2020).\n\n"
        "References\n\nX (2020). T. J, 1, 1-1."
    )

    from refcheck.schema.models import (
        Reference, Author, VerifiedReference, Finding,
    )
    canonical = Reference(
        id="canonical", authors=[Author(family="X")], year=2020,
        title="T", doi="10.1/x", raw_text="", style_detected="unknown",
    )
    stub_vref = VerifiedReference(
        reference=Reference(
            id="ref_001", authors=[Author(family="X")], year=2020,
            title="T", raw_text="...", style_detected="APA",
        ),
        status="verified", canonical=canonical,
        abstract="abs", access_level="abstract_only",
    )

    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.total_cost_usd = 0.01
    mock_llm._client = MagicMock()
    mock_llm.complete_json = AsyncMock(side_effect=[
        ({"references": [{
            "id": "ref_001", "authors": [{"given": "X", "family": "X"}],
            "year": 2020, "title": "T", "journal": "J", "volume": "1",
            "issue": None, "pages": "1-1", "doi": None,
            "raw_text": "X (2020). T. J, 1, 1-1.", "style_detected": "APA",
        }]}, LLMUsage("gpt-5.4-mini", 100, 50, 0.001)),
        ({"citations": [{
            "id": "cit_0001", "surface": "(X, 2020)", "ref_ids": ["ref_001"],
            "char_offset": 6, "containing_sentence": "Claim (X, 2020).",
            "surrounding_paragraph": "Claim (X, 2020).",
        }]}, LLMUsage("gpt-5.4-mini", 100, 50, 0.001)),
    ])

    crossref = MagicMock(); crossref.close = AsyncMock()
    openalex = MagicMock(); openalex.close = AsyncMock()
    semantic = MagicMock(); semantic.close = AsyncMock()
    pubmed = MagicMock(); pubmed.close = AsyncMock()
    unpaywall = MagicMock(); unpaywall.close = AsyncMock()

    async def _stub_metadata(refs, **kwargs):
        return [stub_vref]
    async def _stub_content(cits, vrefs, **kwargs):
        return []

    with patch("refcheck.pipeline.verify_all_references_agent", side_effect=_stub_metadata), \
         patch("refcheck.pipeline.verify_all_content_agent", side_effect=_stub_content):
        config = PipelineConfig(
            cache_dir=tmp_path / "cache",
            verification_level="precise",
            use_agents=True,
        )
        report = await run_pipeline(
            draft_text=draft_text, draft_title="t", config=config,
            llm=mock_llm, crossref=crossref, openalex=openalex,
            semantic_scholar=semantic, pubmed=pubmed, unpaywall=unpaywall,
        )

    assert report.summary_counts.get("verified", 0) == 1
