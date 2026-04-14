from unittest.mock import AsyncMock, MagicMock
import json
import pytest
from refcheck.schema.models import Reference, Author
from refcheck.verify.agent_metadata import verify_reference_agent


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


@pytest.mark.asyncio
async def test_agent_verified_via_crossref(tmp_path):
    ref = Reference(
        id="ref_001", authors=[Author(family="Potenza")], year=2013,
        title="Neurobiology of gambling", raw_text="...", style_detected="APA",
    )

    final_args = {
        "status": "verified",
        "confidence": "high",
        "reasoning": "Crossref found exact match.",
        "canonical": {
            "title": "Neurobiology of gambling",
            "authors": [{"given": "M. N.", "family": "Potenza"}],
            "year": 2013, "doi": "10.1016/x",
            "journal": "Current Opinion in Neurobiology",
        },
        "field_diffs": {},
        "abstract": None,
        "oa_pdf_url": None,
        "preprint_vs_published": False,
    }
    openai = MagicMock()
    openai.chat.completions.create = AsyncMock(side_effect=[
        _resp(tool_calls=[_tc(tc_id="c1", name="search_crossref",
                              args_json=json.dumps({"title": "Neurobiology of gambling",
                                                    "authors": ["Potenza"], "year": 2013}))]),
        _resp(tool_calls=[_tc(tc_id="c2", name="submit_final",
                              args_json=json.dumps(final_args))]),
    ])

    crossref = MagicMock()
    crossref.search = AsyncMock(return_value=Reference(
        id="canonical", authors=[Author(family="Potenza")], year=2013,
        title="Neurobiology of gambling", doi="10.1016/x",
        raw_text="", style_detected="unknown",
    ))
    openalex = MagicMock()
    semantic = MagicMock()
    pubmed = MagicMock()

    vref = await verify_reference_agent(
        ref,
        openai_client=openai,
        crossref=crossref, openalex=openalex,
        semantic_scholar=semantic, pubmed=pubmed,
        model="gpt-5.4", max_turns=5,
    )

    assert vref.status == "verified"
    assert vref.canonical is not None
    assert vref.canonical.title == "Neurobiology of gambling"


@pytest.mark.asyncio
async def test_agent_hallucination_when_all_empty():
    ref = Reference(
        id="ref_001", authors=[Author(family="FakeAuthor")], year=2099,
        title="Bananas cure gambling", raw_text="...", style_detected="APA",
    )

    final_args = {
        "status": "hallucination",
        "confidence": "high",
        "reasoning": "Searched 4 DBs, no results.",
        "canonical": None,
        "field_diffs": {},
        "abstract": None,
        "oa_pdf_url": None,
        "preprint_vs_published": False,
    }
    openai = MagicMock()
    openai.chat.completions.create = AsyncMock(return_value=_resp(
        tool_calls=[_tc(tc_id="c1", name="submit_final",
                        args_json=json.dumps(final_args))]
    ))

    crossref = MagicMock(); openalex = MagicMock()
    semantic = MagicMock(); pubmed = MagicMock()

    vref = await verify_reference_agent(
        ref, openai_client=openai,
        crossref=crossref, openalex=openalex,
        semantic_scholar=semantic, pubmed=pubmed,
    )

    assert vref.status == "hallucination"
    assert vref.canonical is None
