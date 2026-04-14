from unittest.mock import AsyncMock, MagicMock
import pytest
from refcheck.extract.reference_parser import parse_references
from refcheck.llm.client import LLMClient, LLMUsage


@pytest.mark.asyncio
async def test_parses_apa_references():
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.complete_json = AsyncMock(return_value=(
        {
            "references": [
                {
                    "id": "ref_001",
                    "authors": [{"given": "M. N.", "family": "Potenza"}],
                    "year": 2013,
                    "title": "Neurobiology of gambling",
                    "journal": "Current Opinion in Neurobiology",
                    "volume": "23",
                    "issue": "4",
                    "pages": "660-667",
                    "doi": None,
                    "raw_text": "Potenza, M. N. (2013). Neurobiology of gambling. Current Opinion in Neurobiology, 23(4), 660-667.",
                    "style_detected": "APA"
                }
            ]
        },
        LLMUsage(model="gpt-5.4-mini", prompt_tokens=100, completion_tokens=50, cost_usd=0.001),
    ))

    raw = "Potenza, M. N. (2013). Neurobiology of gambling..."
    refs = await parse_references(raw, llm=mock_llm)

    assert len(refs) == 1
    assert refs[0].title == "Neurobiology of gambling"
    assert refs[0].authors[0].family == "Potenza"
    assert refs[0].year == 2013
    assert refs[0].style_detected == "APA"


@pytest.mark.asyncio
async def test_assigns_sequential_ids_when_missing():
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.complete_json = AsyncMock(return_value=(
        {
            "references": [
                {"id": "", "authors": [{"given": None, "family": "A"}], "year": 2020, "title": "T1",
                 "journal": None, "volume": None, "issue": None, "pages": None, "doi": None,
                 "raw_text": "A (2020). T1.", "style_detected": "APA"},
                {"id": "", "authors": [{"given": None, "family": "B"}], "year": 2021, "title": "T2",
                 "journal": None, "volume": None, "issue": None, "pages": None, "doi": None,
                 "raw_text": "B (2021). T2.", "style_detected": "APA"},
            ]
        },
        LLMUsage(model="gpt-5.4-mini", prompt_tokens=100, completion_tokens=50, cost_usd=0.001),
    ))

    refs = await parse_references("...", llm=mock_llm)
    assert refs[0].id == "ref_001"
    assert refs[1].id == "ref_002"
