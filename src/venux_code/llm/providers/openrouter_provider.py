"""OpenRouter provider (OpenAI-compatible API)."""

from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from venux_code.llm.providers.base import BaseLLMProvider, ModelInfo

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(BaseLLMProvider):
    """Provider for models hosted on OpenRouter via the OpenAI-compatible API."""

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
            default_headers={
                "HTTP-Referer": "https://venux-code.dev",
                "X-Title": "Venux Code",
            },
        )

    def model_info(self) -> ModelInfo:
        # OpenRouter proxies many models; costs vary.  These are common ones.
        info: dict[str, tuple[int, int, float, float]] = {
            "anthropic/claude-sonnet-4": (200_000, 16_384, 3.00, 15.00),
            "openai/gpt-4o": (128_000, 16_384, 2.50, 10.00),
            "google/gemini-2.5-pro": (1_048_576, 65_536, 1.25, 10.00),
            "deepseek/deepseek-chat-v3": (64_000, 8_192, 0.14, 0.28),
            "meta-llama/llama-4-maverick": (1_048_576, 32_768, 0.20, 0.60),
        }
        ctx, max_tok, cost_in, cost_out = info.get(
            self.model_name, (128_000, self.max_tokens, 0.0, 0.0)
        )
        return ModelInfo(
            name=self.model_name,
            provider="openrouter",
            context_window=ctx,
            max_tokens=max_tok,
            cost_per_1m_in=cost_in,
            cost_per_1m_out=cost_out,
        )
