"""Google Gemini provider backed by ``langchain-google-genai``."""

from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI

from venux_code.llm.providers.base import BaseLLMProvider, ModelInfo


class GoogleProvider(BaseLLMProvider):
    """Provider wrapping ``ChatGoogleGenerativeAI``."""

    def _build_model(
        self, *, stream: bool = False, tools: Optional[list[BaseTool]] = None
    ) -> BaseChatModel:
        return ChatGoogleGenerativeAI(
            model=self.model_name,
            google_api_key=self.api_key,
            max_output_tokens=self.max_tokens,
            temperature=self.temperature,
            streaming=stream or tools is not None,
        )

    def model_info(self) -> ModelInfo:
        info: dict[str, tuple[int, int, float, float]] = {
            "gemini-2.5-pro": (1_048_576, 65_536, 1.25, 10.00),
            "gemini-2.5-flash": (1_048_576, 65_536, 0.15, 0.60),
            "gemini-2.0-flash": (1_048_576, 8_192, 0.10, 0.40),
            "gemini-1.5-pro": (2_097_152, 8_192, 1.25, 5.00),
            "gemini-1.5-flash": (1_048_576, 8_192, 0.075, 0.30),
        }
        ctx, max_tok, cost_in, cost_out = info.get(
            self.model_name, (1_048_576, self.max_tokens, 0.0, 0.0)
        )
        return ModelInfo(
            name=self.model_name,
            provider="google",
            context_window=ctx,
            max_tokens=max_tok,
            cost_per_1m_in=cost_in,
            cost_per_1m_out=cost_out,
        )
