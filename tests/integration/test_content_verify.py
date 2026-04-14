from unittest.mock import AsyncMock, MagicMock
import pytest
from refcheck.schema.models import Citation, VerifiedReference, Reference, Author
from refcheck.verify.content import verify_citation
from refcheck.llm.client import LLMClient, LLMUsage


def _vref_with_abstract():
    ref = Reference(
        id="ref_001", authors=[Author(family="Potenza")], year=2013,
        title="T", doi="10.1016/x", raw_text="...", style_detected="APA",
    )
    return VerifiedReference(
        reference=ref,
        status="verified",
        canonical=ref,
        abstract="Gambling disorder affects 1% of adults. No significant effect of drug X was observed.",
        access_level="abstract_only",
    )


def _cit():
    return Citation(
        id="cit_001",
        surface="(Potenza, 2013)",
        ref_ids=["ref_001"],
        char_offset=0,
        containing_sentence="Drug X shows clear efficacy in gambling disorder (Potenza, 2013).",
        surrounding_paragraph="Drug X shows clear efficacy in gambling disorder (Potenza, 2013).",
    )


@pytest.mark.asyncio
async def test_detects_claim_reversal():
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.complete_json = AsyncMock(return_value=(
        {
            "category": "content_mismatch",
            "error_type": "claim_reversal",
            "severity": 5,
            "confidence": "high",
            "source_evidence_quote": "No significant effect of drug X was observed.",
            "explanation": "원문은 '효과 없음'인데 초안은 '명확한 효능'이라 주장.",
            "suggestion": "효능 주장 철회 또는 다른 논문 인용 필요.",
        },
        LLMUsage(model="gpt-5.4-thinking", prompt_tokens=500, completion_tokens=100, cost_usd=0.005),
    ))

    finding = await verify_citation(_cit(), _vref_with_abstract(), llm=mock_llm)
    assert finding is not None
    assert finding.category == "content_mismatch"
    assert finding.error_type == "claim_reversal"
    assert finding.severity == 5


@pytest.mark.asyncio
async def test_returns_none_when_category_none():
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.complete_json = AsyncMock(return_value=(
        {
            "category": "none",
            "error_type": None,
            "severity": 1,
            "confidence": "high",
            "source_evidence_quote": "",
            "explanation": "문제 없음.",
            "suggestion": None,
        },
        LLMUsage(model="gpt-5.4-thinking", prompt_tokens=500, completion_tokens=50, cost_usd=0.003),
    ))
    finding = await verify_citation(_cit(), _vref_with_abstract(), llm=mock_llm)
    assert finding is None


@pytest.mark.asyncio
async def test_retries_when_evidence_not_in_source():
    """LLM이 환각한 증거 인용을 걸러내고 재호출."""
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.complete_json = AsyncMock(side_effect=[
        (
            {"category": "content_mismatch", "error_type": "claim_reversal",
             "severity": 5, "confidence": "high",
             "source_evidence_quote": "This text does not exist in the abstract.",
             "explanation": "...", "suggestion": None},
            LLMUsage(model="gpt-5.4-thinking", prompt_tokens=500, completion_tokens=100, cost_usd=0.005),
        ),
        (
            {"category": "content_mismatch", "error_type": "claim_reversal",
             "severity": 5, "confidence": "high",
             "source_evidence_quote": "No significant effect of drug X was observed.",
             "explanation": "...", "suggestion": None},
            LLMUsage(model="gpt-5.4-thinking", prompt_tokens=500, completion_tokens=100, cost_usd=0.005),
        ),
    ])
    finding = await verify_citation(_cit(), _vref_with_abstract(), llm=mock_llm)
    assert finding is not None
    assert finding.source_evidence_quote == "No significant effect of drug X was observed."
    assert mock_llm.complete_json.call_count == 2


@pytest.mark.asyncio
async def test_low_confidence_after_two_failed_evidence_validations():
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.complete_json = AsyncMock(return_value=(
        {"category": "content_mismatch", "error_type": "claim_reversal",
         "severity": 5, "confidence": "high",
         "source_evidence_quote": "Not in source at all.",
         "explanation": "...", "suggestion": None},
        LLMUsage(model="gpt-5.4-thinking", prompt_tokens=500, completion_tokens=100, cost_usd=0.005),
    ))
    finding = await verify_citation(_cit(), _vref_with_abstract(), llm=mock_llm)
    assert finding is not None
    assert finding.confidence == "low"
    assert finding.source_evidence_quote is None
