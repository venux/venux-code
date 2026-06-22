"""OpenAI provider backed by ``langchain-openai``."""

from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from venux_code.llm.providers.base import BaseLLMProvider, ModelInfo


class OpenAIProvider(BaseLLMProvider):
    """Provider wrapping ``ChatOpenAI``."""

    def _build_model(
        self, *, stream: bool = False, tools: Optional[list[BaseTool]] = None
    ) -> BaseChatModel:
        return ChatOpenAI(
            model=self.model_name,
            api_key=self.api_key,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            base_url=self.base_url,
            streaming=stream or tools is not None,
        )

    def model_info(self) -> ModelInfo:
        # Defaults – may be overridden per model name.
        info: dict[str, tuple[int, int, float, float]] = {
            "gpt-4o": (128_000, 16_384, 2.50, 10.00),
            "gpt-4o-mini": (128_000, 16_384, 0.15, 0.60),
            "gpt-4-turbo": (128_000, 4_096, 10.00, 30.00),
            "gpt-3.5-turbo": (16_385, 4_096, 0.50, 1.50),
            "o1": (200_000, 100_000, 15.00, 60.00),
            "o3-mini": (200_000, 100_000, 1.10, 4.40),
        }
        ctx, max_tok, cost_in, cost_out = info.get(
            self.model_name, (128_000, self.max_tokens, 0.0, 0.0)
        )
        return ModelInfo(
            name=self.model_name,
            provider="openai",
            context_window=ctx,
            max_tokens=max_tok,
            cost_per_1m_in=cost_in,
            cost_per_1m_out=cost_out,
        )
