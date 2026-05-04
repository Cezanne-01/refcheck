from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any
import httpx
from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError, APIConnectionError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


# USD per 1M tokens — 2026-04 기준, 실제 가격은 OpenAI 페이지 확인 후 업데이트
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-5.4-mini": (0.40, 1.60),
    "gpt-5.4": (2.50, 10.00),
    "gpt-5.4-thinking": (5.00, 20.00),
    "gpt-5.4-pro": (15.00, 60.00),
}


@dataclass
class LLMUsage:
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


def _cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_price, out_price = MODEL_PRICING.get(model, (0.0, 0.0))
    return (prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000


class LLMClient:
    """OpenAI client wrapper with retry, JSON schema enforcement, cost tracking."""

    def __init__(self, openai_client: AsyncOpenAI | None = None, api_key: str | None = None):
        # SDK 기본 timeout이 600초라 호출 한 번이 죽지 않고 10분간 매달릴 수 있다.
        # 단일 호출 상한을 120초로 좁히고 retry는 위 데코레이터에서 처리.
        self._client = openai_client or AsyncOpenAI(api_key=api_key, timeout=120.0)
        self.total_usage: list[LLMUsage] = []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((
            RateLimitError,
            APITimeoutError,
            APIConnectionError,
            httpx.TimeoutException,
            httpx.NetworkError,
            json.JSONDecodeError,
        )),
        reraise=True,
    )
    async def complete_json(
        self,
        *,
        model: str,
        system: str,
        user: str,
        response_schema: dict[str, Any],
        temperature: float = 0.2,
    ) -> tuple[dict[str, Any], LLMUsage]:
        response = await self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": response_schema,
                },
            },
            temperature=temperature,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        usage = LLMUsage(
            model=response.model,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            cost_usd=_cost(response.model, response.usage.prompt_tokens, response.usage.completion_tokens),
        )
        self.total_usage.append(usage)
        return parsed, usage

    @property
    def total_cost_usd(self) -> float:
        return sum(u.cost_usd for u in self.total_usage)
