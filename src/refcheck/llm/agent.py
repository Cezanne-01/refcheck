from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any, Protocol


class _Dispatcher(Protocol):
    async def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]: ...


class AgentTimeoutError(Exception):
    """Agent did not call submit_final within max_turns."""


@dataclass
class AgentResult:
    """Return value of an AgentRunner.run() call."""
    final_args: dict[str, Any]
    turns: int
    tool_call_trace: list[dict[str, Any]] = field(default_factory=list)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0


class AgentRunner:
    """Generic OpenAI function-calling loop.

    Loops until the agent calls the `submit_final` tool (successful termination)
    or max_turns is reached (raises AgentTimeoutError).
    """

    def __init__(self, openai_client, max_turns: int = 6):
        self._client = openai_client
        self._max_turns = max_turns

    async def run(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        dispatcher: _Dispatcher,
        temperature: float = 0.2,
    ) -> AgentResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        trace: list[dict[str, Any]] = []
        total_in = 0
        total_out = 0

        for turn in range(1, self._max_turns + 1):
            resp = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
            )
            msg = resp.choices[0].message
            usage = resp.usage
            if usage is not None:
                total_in += usage.prompt_tokens
                total_out += usage.completion_tokens

            if not msg.tool_calls:
                messages.append({"role": "assistant", "content": msg.content or ""})
                messages.append({
                    "role": "user",
                    "content": "You must call submit_final to return your verdict.",
                })
                continue

            messages.append(msg.model_dump())

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                trace.append({"turn": turn, "tool": fn_name, "args": args})

                if fn_name == "submit_final":
                    return AgentResult(
                        final_args=args,
                        turns=turn,
                        tool_call_trace=trace,
                        total_prompt_tokens=total_in,
                        total_completion_tokens=total_out,
                    )

                result = await dispatcher.dispatch(fn_name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

        raise AgentTimeoutError(
            f"Agent exceeded max_turns={self._max_turns} without calling submit_final"
        )
