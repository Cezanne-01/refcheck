from unittest.mock import AsyncMock, MagicMock
import pytest
from refcheck.extract.citation_extractor import extract_citations
from refcheck.schema.models import Reference, Author
from refcheck.llm.client import LLMClient, LLMUsage


@pytest.mark.asyncio
async def test_extracts_single_citation():
    refs = [Reference(
        id="ref_001", authors=[Author(family="Potenza")], year=2013,
        title="X", raw_text="...", style_detected="APA",
    )]
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.complete_json = AsyncMock(return_value=(
        {"citations": [{
            "id": "cit_0001",
            "surface": "(Potenza, 2013)",
            "ref_ids": ["ref_001"],
            "char_offset": 28,
            "containing_sentence": "Gambling is harmful (Potenza, 2013).",
            "surrounding_paragraph": "Gambling is harmful (Potenza, 2013).",
        }]},
        LLMUsage(model="gpt-5.4-mini", prompt_tokens=100, completion_tokens=50, cost_usd=0.001),
    ))

    body = "Gambling is harmful (Potenza, 2013)."
    cits = await extract_citations(body, refs, llm=mock_llm)

    assert len(cits) == 1
    assert cits[0].surface == "(Potenza, 2013)"
    assert cits[0].ref_ids == ["ref_001"]
