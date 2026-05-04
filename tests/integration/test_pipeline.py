from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from refcheck.pipeline import run_pipeline, PipelineConfig
from refcheck.llm.client import LLMClient, LLMUsage
from refcheck.fetch.full_text import FullTextResult


def _llm_two_extract_steps():
    """Mock LLMClient that returns reference + citation parses (no content_verify
    because the agent path stubs content verification entirely)."""
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
    return mock_llm


def _stub_clients():
    crossref = MagicMock(); crossref.close = AsyncMock()
    openalex = MagicMock(); openalex.close = AsyncMock()
    semantic = MagicMock(); semantic.close = AsyncMock()
    pubmed = MagicMock(); pubmed.close = AsyncMock()
    web_search = MagicMock(); web_search.close = AsyncMock()
    full_text = MagicMock()
    full_text.close = AsyncMock()
    full_text.fetch = AsyncMock(return_value=FullTextResult(text=None, source="none"))
    return crossref, openalex, semantic, pubmed, web_search, full_text


@pytest.mark.asyncio
async def test_pipeline_runs_agents_end_to_end(tmp_path):
    """전체 파이프라인이 에이전트 메타데이터·컨텐츠 검증을 호출하는지 확인."""
    draft_text = (
        "Intro.\n\nClaim (X, 2020).\n\n"
        "References\n\nX (2020). T. J, 1, 1-1."
    )

    from refcheck.schema.models import (
        Reference, Author, VerifiedReference,
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

    mock_llm = _llm_two_extract_steps()
    crossref, openalex, semantic, pubmed, web_search, full_text = _stub_clients()

    async def _stub_metadata(refs, **kwargs):
        return [stub_vref]

    async def _stub_content(cits, vrefs, **kwargs):
        return []

    with patch("refcheck.pipeline.verify_all_references_agent", side_effect=_stub_metadata), \
         patch("refcheck.pipeline.verify_all_content_agent", side_effect=_stub_content):
        config = PipelineConfig(
            cache_dir=tmp_path / "cache",
            verification_level="precise",
        )
        report = await run_pipeline(
            draft_text=draft_text, draft_title="t", config=config,
            llm=mock_llm, crossref=crossref, openalex=openalex,
            semantic_scholar=semantic, pubmed=pubmed,
            web_search=web_search, full_text_fetcher=full_text,
        )

    assert report.summary_counts.get("verified", 0) == 1


@pytest.mark.asyncio
async def test_pipeline_emits_progress_events(tmp_path):
    from refcheck.ui.progress import ProgressReporter, ProgressEvent, Stage
    from refcheck.schema.models import (
        Reference, Author, VerifiedReference,
    )

    draft_text = (
        "Intro\n\nClaim (X, 2020).\n\n"
        "References\n\nX (2020). T. J, 1, 1-1."
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

    mock_llm = _llm_two_extract_steps()
    crossref, openalex, semantic, pubmed, web_search, full_text = _stub_clients()

    async def _stub_metadata(refs, **kwargs):
        return [stub_vref]

    async def _stub_content(cits, vrefs, **kwargs):
        return []

    events: list[ProgressEvent] = []
    reporter = ProgressReporter(callback=events.append)

    with patch("refcheck.pipeline.verify_all_references_agent", side_effect=_stub_metadata), \
         patch("refcheck.pipeline.verify_all_content_agent", side_effect=_stub_content):
        config = PipelineConfig(cache_dir=tmp_path / "cache")
        await run_pipeline(
            draft_text=draft_text, draft_title="t", config=config,
            llm=mock_llm, crossref=crossref, openalex=openalex,
            semantic_scholar=semantic, pubmed=pubmed,
            web_search=web_search, full_text_fetcher=full_text,
            progress=reporter,
        )

    stages_started = {e.stage for e in events if e.current == 0}
    assert Stage.EXTRACT in stages_started
    assert Stage.VERIFY_METADATA in stages_started
    assert Stage.VERIFY_CONTENT in stages_started
