from unittest.mock import AsyncMock, MagicMock
import json
import pytest
from refcheck.schema.models import Citation, VerifiedReference, Reference, Author
from refcheck.verify.agent_content import verify_citation_agent


def _tc(*, tc_id, name, args_json):
    tc = MagicMock()
    tc.id = tc_id
    tc.type = "function"
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = args_json
    tc._raw = {"id": tc_id, "type": "function",
               "function": {"name": name, "arguments": args_json}}
    return tc


def _resp(*, tool_calls):
    msg = MagicMock()
    msg.content = None
    msg.tool_calls = tool_calls
    msg.model_dump = lambda: {"role": "assistant",
                              "tool_calls": [tc._raw for tc in tool_calls]}
    choice = MagicMock()
    choice.message = msg
    r = MagicMock()
    r.choices = [choice]
    r.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
    r.model = "gpt-5.4"
    return r


def _cit_and_vref():
    ref = Reference(
        id="ref_001", authors=[Author(family="Potenza")], year=2013,
        title="T", raw_text="...", style_detected="APA",
    )
    vref = VerifiedReference(
        reference=ref, status="verified", canonical=ref,
        abstract="Gambling disorder shows ventral striatum hyperactivity.",
        access_level="abstract_only",
    )
    cit = Citation(
        id="cit_001", surface="(Potenza, 2013)", ref_ids=["ref_001"],
        char_offset=0,
        containing_sentence="Ventral striatum shows hyperactivity (Potenza, 2013).",
        surrounding_paragraph="...",
    )
    return cit, vref


@pytest.mark.asyncio
async def test_agent_returns_none_when_claim_supported():
    cit, vref = _cit_and_vref()
    final_args = {
        "category": "none",
        "error_type": None,
        "severity": 1,
        "confidence": "high",
        "source_evidence_quote": "ventral striatum hyperactivity",
        "explanation": "Claim matches abstract.",
        "suggestion": None,
    }
    openai = MagicMock()
    openai.chat.completions.create = AsyncMock(return_value=_resp(
        tool_calls=[_tc(tc_id="c1", name="submit_final",
                        args_json=json.dumps(final_args))]
    ))

    finding = await verify_citation_agent(
        cit, vref,
        openai_client=openai,
        unpaywall=MagicMock(), openalex=MagicMock(),
    )
    assert finding is None


@pytest.mark.asyncio
async def test_agent_abstract_insufficient_over_complete_mismatch():
    """LLM이 abstract_insufficient 카테고리로 반환 → Finding 생성, severity 1."""
    cit, vref = _cit_and_vref()
    final_args = {
        "category": "abstract_insufficient",
        "error_type": "abstract_only_no_evidence",
        "severity": 1,
        "confidence": "low",
        "source_evidence_quote": "",
        "explanation": "Abstract doesn't discuss DSM-5 classification; full text needed.",
        "suggestion": "Fetch full text to confirm.",
    }
    openai = MagicMock()
    openai.chat.completions.create = AsyncMock(return_value=_resp(
        tool_calls=[_tc(tc_id="c1", name="submit_final",
                        args_json=json.dumps(final_args))]
    ))

    finding = await verify_citation_agent(
        cit, vref,
        openai_client=openai,
        unpaywall=MagicMock(), openalex=MagicMock(),
    )
    assert finding is not None
    assert finding.category == "partial_verified"
    assert finding.error_type == "abstract_only_no_evidence"
    assert finding.severity == 1
