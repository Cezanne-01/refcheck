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


@pytest.mark.asyncio
async def test_verify_all_content_parallel():
    from refcheck.verify.content import verify_all_content

    cit1 = _cit()
    cit2 = Citation(
        id="cit_002", surface="(X, 2020)", ref_ids=["ref_001"],
        char_offset=100, containing_sentence="Good citation.",
        surrounding_paragraph="Good citation.",
    )

    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.complete_json = AsyncMock(return_value=(
        {"category": "none", "error_type": None, "severity": 1,
         "confidence": "high", "source_evidence_quote": "",
         "explanation": "ok", "suggestion": None},
        LLMUsage(model="gpt-5.4-thinking", prompt_tokens=100, completion_tokens=20, cost_usd=0.001),
    ))

    findings = await verify_all_content(
        [cit1, cit2], [_vref_with_abstract()], llm=mock_llm, concurrency=2,
    )
    assert findings == []  # 둘 다 category=none


@pytest.mark.asyncio
async def test_full_text_path_preserves_high_confidence():
    """access_level='full_text'면 confidence downgrade 없음."""
    ref = Reference(
        id="ref_001", authors=[Author(family="Potenza")], year=2013,
        title="T", doi="10.1016/x", raw_text="...", style_detected="APA",
    )
    vref = VerifiedReference(
        reference=ref, status="verified", canonical=ref,
        full_text="The ventral striatum shows hyperactivity in gambling disorder.",
        access_level="full_text",
    )
    cit = Citation(
        id="cit_001", surface="(X)", ref_ids=["ref_001"], char_offset=0,
        containing_sentence="Ventral striatum hyperactive.",
        surrounding_paragraph="Ventral striatum hyperactive.",
    )

    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.complete_json = AsyncMock(return_value=(
        {"category": "content_mismatch", "error_type": "strength_distortion",
         "severity": 3, "confidence": "high",
         "source_evidence_quote": "The ventral striatum shows hyperactivity",
         "explanation": "...", "suggestion": None},
        LLMUsage("gpt-5.4-thinking", 500, 100, 0.005),
    ))

    finding = await verify_citation(cit, vref, llm=mock_llm)
    assert finding is not None
    # full_text: no downgrade
    assert finding.confidence == "high"


@pytest.mark.asyncio
async def test_abstract_only_downgrades_high_to_medium():
    """abstract_only + high confidence → medium (한 단계 내림)."""
    ref = Reference(
        id="ref_001", authors=[Author(family="Potenza")], year=2013,
        title="T", doi="10.1016/x", raw_text="...", style_detected="APA",
    )
    vref = VerifiedReference(
        reference=ref, status="verified", canonical=ref,
        abstract="No significant effect observed.",
        access_level="abstract_only",
    )
    cit = Citation(
        id="cit_001", surface="(X)", ref_ids=["ref_001"], char_offset=0,
        containing_sentence="Drug X effective.",
        surrounding_paragraph="Drug X effective.",
    )

    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.complete_json = AsyncMock(return_value=(
        {"category": "content_mismatch", "error_type": "claim_reversal",
         "severity": 5, "confidence": "high",
         "source_evidence_quote": "No significant effect observed.",
         "explanation": "...", "suggestion": None},
        LLMUsage("gpt-5.4-thinking", 500, 100, 0.005),
    ))

    finding = await verify_citation(cit, vref, llm=mock_llm)
    assert finding is not None
    # abstract_only: high → medium (한 단계 내림)
    assert finding.confidence == "medium"


@pytest.mark.asyncio
async def test_multiple_ref_ids_in_single_citation():
    """인용이 여러 참고문헌을 동시에 가리키는 경우 각 ref별로 finding 생성."""
    from refcheck.verify.content import verify_all_content

    refs_data = [("ref_001", "Ok finding"), ("ref_002", "Problem finding")]
    vrefs = []
    for rid, _ in refs_data:
        r = Reference(id=rid, authors=[Author(family="X")], year=2020,
                      title="T", raw_text="...", style_detected="APA")
        vrefs.append(VerifiedReference(
            reference=r, status="verified", canonical=r,
            abstract="Abstract content here.", access_level="abstract_only",
        ))

    cit = Citation(
        id="cit_001", surface="(X, 2020; Y, 2020)", ref_ids=["ref_001", "ref_002"],
        char_offset=0, containing_sentence="Combined claim.",
        surrounding_paragraph="Combined claim.",
    )

    mock_llm = MagicMock(spec=LLMClient)
    # First call: ref_001 → no issue; Second: ref_002 → mismatch
    mock_llm.complete_json = AsyncMock(side_effect=[
        ({"category": "none", "error_type": None, "severity": 1,
          "confidence": "high", "source_evidence_quote": "",
          "explanation": "ok", "suggestion": None},
         LLMUsage("gpt-5.4-thinking", 100, 20, 0.001)),
        ({"category": "content_mismatch", "error_type": "claim_reversal",
          "severity": 5, "confidence": "high",
          "source_evidence_quote": "Abstract content here.",
          "explanation": "mismatch", "suggestion": None},
         LLMUsage("gpt-5.4-thinking", 100, 20, 0.001)),
    ])

    findings = await verify_all_content([cit], vrefs, llm=mock_llm, concurrency=2)
    # Only the second ref produces a finding
    assert len(findings) == 1
    assert findings[0].reference_id == "ref_002"


def test_mini_retrieval_extracts_relevant_passages():
    """긴 full_text에서 claim keyword와 겹치는 단락을 선별."""
    from refcheck.verify.content import _extract_relevant_passages

    claim = "ventral striatum hyperactivity gambling disorder"
    # 3 paragraphs, only middle is relevant
    para1 = "Introduction to cardiovascular disease. " * 500
    para2 = "The ventral striatum shows hyperactivity in gambling disorder patients. " * 50
    para3 = "Diabetes epidemiology spans decades. " * 500
    source = f"{para1}\n\n{para2}\n\n{para3}"
    assert len(source) > 30000  # exceeds limit

    result = _extract_relevant_passages(claim, source, max_chars=5000)
    # The relevant paragraph should be included
    assert "ventral striatum" in result
    # Total length should respect budget
    assert len(result) <= 5500  # small overhead tolerance
