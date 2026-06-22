"""Anthropic provider backed by ``langchain-anthropic``."""

from __future__ import annotations

from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from venux_code.llm.providers.base import BaseLLMProvider, ModelInfo


class AnthropicProvider(BaseLLMProvider):
    """Provider wrapping ``ChatAnthropic``."""

    def _build_model(
        self, *, stream: bool = False, tools: Optional[list[BaseTool]] = None
    ) -> BaseChatModel:
        kwargs: dict = dict(
            model=self.model_name,
            api_key=self.api_key,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            streaming=stream or tools is not None,
        )
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return ChatAnthropic(**kwargs)

    def model_info(self) -> ModelInfo:
        info: dict[str, tuple[int, int, float, float]] = {
            "claude-sonnet-4-20250514": (200_000, 16_384, 3.00, 15.00),
            "claude-3-5-sonnet-20241022": (200_000, 8_192, 3.00, 15.00),
            "claude-3-5-haiku-20241022": (200_000, 8_192, 0.80, 4.00),
            "claude-3-opus-20240229": (200_000, 4_096, 15.00, 75.00),
        }
        ctx, max_tok, cost_in, cost_out = info.get(
            self.model_name, (200_000, self.max_tokens, 0.0, 0.0)
        )
        return ModelInfo(
            name=self.model_name,
            provider="anthropic",
            context_window=ctx,
            max_tokens=max_tok,
            cost_per_1m_in=cost_in,
            cost_per_1m_out=cost_out,
        )
