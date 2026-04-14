from unittest.mock import AsyncMock, MagicMock
import json
import pytest
from refcheck.llm.agent import AgentRunner, AgentTimeoutError, AgentResult


def _canned_response(*, content=None, tool_calls=None, model="gpt-5.4"):
    """Build a fake OpenAI ChatCompletion response object."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    msg.model_dump = lambda: {"role": "assistant",
                              "content": content,
                              "tool_calls": [tc._raw for tc in (tool_calls or [])]}
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    resp.model = model
    resp.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
    return resp


def _tool_call(*, tc_id, name, args_json):
    tc = MagicMock()
    tc.id = tc_id
    tc.type = "function"
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = args_json
    tc._raw = {"id": tc_id, "type": "function",
               "function": {"name": name, "arguments": args_json}}
    return tc


@pytest.mark.asyncio
async def test_agent_terminates_on_submit_final():
    """단일 턴에서 submit_final 호출 -> 즉시 종결."""
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(return_value=_canned_response(
        tool_calls=[_tool_call(
            tc_id="call_1", name="submit_final",
            args_json=json.dumps({"status": "verified", "reasoning": "ok"}),
        )],
    ))

    dispatcher = MagicMock()
    dispatcher.dispatch = AsyncMock()

    runner = AgentRunner(openai_client=openai_client, max_turns=3)
    result = await runner.run(
        model="gpt-5.4",
        system_prompt="You are a verifier.",
        user_prompt="Verify this.",
        tools=[{"type": "function", "function": {"name": "submit_final"}}],
        dispatcher=dispatcher,
    )

    assert isinstance(result, AgentResult)
    assert result.final_args == {"status": "verified", "reasoning": "ok"}
    assert result.turns == 1
    assert dispatcher.dispatch.call_count == 0


@pytest.mark.asyncio
async def test_agent_executes_tool_then_finalizes():
    """첫 턴: search_crossref 호출 -> dispatcher 결과 전달 -> 두 번째 턴: submit_final."""
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(side_effect=[
        _canned_response(tool_calls=[
            _tool_call(tc_id="call_1", name="search_crossref",
                       args_json=json.dumps({"title": "X", "authors": ["Y"], "year": 2020})),
        ]),
        _canned_response(tool_calls=[
            _tool_call(tc_id="call_2", name="submit_final",
                       args_json=json.dumps({"status": "verified"})),
        ]),
    ])

    dispatcher = MagicMock()
    dispatcher.dispatch = AsyncMock(return_value={"found": True, "title": "X"})

    runner = AgentRunner(openai_client=openai_client, max_turns=5)
    result = await runner.run(
        model="gpt-5.4", system_prompt="", user_prompt="",
        tools=[], dispatcher=dispatcher,
    )

    assert result.turns == 2
    assert result.final_args == {"status": "verified"}
    dispatcher.dispatch.assert_called_once_with(
        "search_crossref",
        {"title": "X", "authors": ["Y"], "year": 2020},
    )


@pytest.mark.asyncio
async def test_agent_raises_on_max_turns_without_final():
    """submit_final 호출 없이 max_turns 초과 -> AgentTimeoutError."""
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(return_value=_canned_response(
        tool_calls=[_tool_call(tc_id="call_x", name="search_crossref",
                               args_json=json.dumps({"title": "X", "authors": [], "year": 2020}))],
    ))
    dispatcher = MagicMock()
    dispatcher.dispatch = AsyncMock(return_value={"found": False})

    runner = AgentRunner(openai_client=openai_client, max_turns=2)
    with pytest.raises(AgentTimeoutError):
        await runner.run(
            model="gpt-5.4", system_prompt="", user_prompt="",
            tools=[], dispatcher=dispatcher,
        )
