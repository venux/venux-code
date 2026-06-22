"""Xiaomi MiMo provider (OpenAI-compatible API with custom base URL)."""

from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from venux_code.llm.providers.base import BaseLLMProvider, ModelInfo

_DEFAULT_BASE_URL = "https://api.mimo.xiaomi.com/v1"


class MiMoProvider(BaseLLMProvider):
    """Provider for Xiaomi MiMo models via the OpenAI-compatible API."""

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
            "mimo-7b": (32_000, 8_192, 0.0, 0.0),
            "mimo-13b": (32_000, 8_192, 0.0, 0.0),
            "mimo-72b": (128_000, 16_384, 0.0, 0.0),
        }
        ctx, max_tok, cost_in, cost_out = info.get(
            self.model_name, (32_000, self.max_tokens, 0.0, 0.0)
        )
        return ModelInfo(
            name=self.model_name,
            provider="mimo",
            context_window=ctx,
            max_tokens=max_tok,
            cost_per_1m_in=cost_in,
            cost_per_1m_out=cost_out,
        )
