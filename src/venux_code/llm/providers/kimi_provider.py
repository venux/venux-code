"""Kimi / Moonshot provider (OpenAI-compatible API)."""

from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from venux_code.llm.providers.base import BaseLLMProvider, ModelInfo

_DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"


class KimiProvider(BaseLLMProvider):
    """Provider for Moonshot / Kimi models via the OpenAI-compatible API."""

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
            "moonshot-v1-8k": (8_192, 4_096, 1.00, 1.00),
            "moonshot-v1-32k": (32_768, 4_096, 2.00, 2.00),
            "moonshot-v1-128k": (131_072, 4_096, 6.00, 6.00),
            "kimi-k2": (131_072, 16_384, 0.60, 3.00),
        }
        ctx, max_tok, cost_in, cost_out = info.get(
            self.model_name, (32_768, self.max_tokens, 0.0, 0.0)
        )
        return ModelInfo(
            name=self.model_name,
            provider="kimi",
            context_window=ctx,
            max_tokens=max_tok,
            cost_per_1m_in=cost_in,
            cost_per_1m_out=cost_out,
        )
