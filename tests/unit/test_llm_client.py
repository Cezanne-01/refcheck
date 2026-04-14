from unittest.mock import AsyncMock, MagicMock
import pytest
from refcheck.llm.client import LLMClient, LLMUsage, MODEL_PRICING


@pytest.mark.asyncio
async def test_client_tracks_cost():
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content='{"ok": true}'))]
    fake_response.usage = MagicMock(prompt_tokens=1000, completion_tokens=500)
    fake_response.model = "gpt-5.4-mini"

    mock_openai = MagicMock()
    mock_openai.chat.completions.create = AsyncMock(return_value=fake_response)

    client = LLMClient(openai_client=mock_openai)
    result, usage = await client.complete_json(
        model="gpt-5.4-mini",
        system="You are a parser.",
        user="Parse this.",
        response_schema={"type": "object"},
    )

    assert result == {"ok": True}
    assert usage.prompt_tokens == 1000
    assert usage.completion_tokens == 500
    # mini: $0.40/1M input, $1.60/1M output
    expected = (1000 * 0.40 + 500 * 1.60) / 1_000_000
    assert abs(usage.cost_usd - expected) < 1e-6


def test_pricing_table_has_expected_models():
    assert "gpt-5.4-mini" in MODEL_PRICING
    assert "gpt-5.4" in MODEL_PRICING
    assert "gpt-5.4-thinking" in MODEL_PRICING
