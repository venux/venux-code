"""DeepSeek provider (OpenAI-compatible API)."""

from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from venux_code.llm.providers.base import BaseLLMProvider, ModelInfo

_DEFAULT_BASE_URL = "https://api.deepseek.com"


class DeepSeekProvider(BaseLLMProvider):
    """Provider for DeepSeek models via the OpenAI-compatible API."""

    def _build_model(
        self, *, stream: bool = False, tools: Optional[list[BaseTool]] = None
    ) -> BaseChatModel:
        return ChatOpenAI(
            model=self.model_name,
            api_key=self.api_key,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            base_url=self.base_url or _DEFAULT_BASE_URL,
            streaming=stream or tools is not None,
        )

    def model_info(self) -> ModelInfo:
        info: dict[str, tuple[int, int, float, float]] = {
            "deepseek-chat": (64_000, 8_192, 0.14, 0.28),
            "deepseek-reasoner": (64_000, 8_192, 0.55, 2.19),
        }
        ctx, max_tok, cost_in, cost_out = info.get(
            self.model_name, (64_000, self.max_tokens, 0.0, 0.0)
        )
        return ModelInfo(
            name=self.model_name,
            provider="deepseek",
            context_window=ctx,
            max_tokens=max_tok,
            cost_per_1m_in=cost_in,
            cost_per_1m_out=cost_out,
        )
