"""Abstract base class for all LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional, Union

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.tools import BaseTool


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """Static metadata about a model."""

    name: str
    provider: str
    context_window: int = 128_000
    max_tokens: int = 4_096
    cost_per_1m_in: float = 0.0  # USD per 1M input tokens
    cost_per_1m_out: float = 0.0  # USD per 1M output tokens


@dataclass
class ChatResponse:
    """Normalised response returned by :meth:`BaseLLMProvider.chat`."""

    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    raw: Any = None  # the original LangChain AIMessage


class BaseLLMProvider(ABC):
    """Contract every LLM provider must fulfil."""

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        base_url: Optional[str] = None,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.base_url = base_url

    # ── abstract ---------------------------------------------------------------

    @abstractmethod
    def _build_model(
        self, *, stream: bool = False, tools: Optional[list[BaseTool]] = None
    ) -> BaseChatModel:
        """Return a configured LangChain ``BaseChatModel`` instance."""
        ...

    @abstractmethod
    def model_info(self) -> ModelInfo:
        """Return static metadata about this model."""
        ...

    # ── concrete ---------------------------------------------------------------

    async def chat(
        self,
        messages: list[BaseMessage],
        *,
        tools: Optional[list[BaseTool]] = None,
        stream: bool = False,
    ) -> ChatResponse:
        """Send *messages* to the model and return a normalised response.

        When *stream* is ``True`` the full streamed content is collected and
        returned as a single :class:`ChatResponse` (use :meth:`stream_chat`
        for true async streaming).
        """
        if stream:
            collected_content = ""
            async for chunk in self.stream_chat(messages, tools=tools):
                collected_content += chunk
            # Build a minimal response – callers needing per-chunk access
            # should call ``stream_chat`` directly.
            return ChatResponse(content=collected_content)

        model = self._build_model(stream=False, tools=tools)
        result = await model.ainvoke(messages)

        tool_calls: list[dict[str, Any]] = []
        if hasattr(result, "tool_calls"):
            tool_calls = result.tool_calls  # type: ignore[assignment]

        usage: dict[str, int] = {}
        if hasattr(result, "usage_metadata") and result.usage_metadata:
            usage = {
                "input_tokens": result.usage_metadata.get("input_tokens", 0),
                "output_tokens": result.usage_metadata.get("output_tokens", 0),
                "total_tokens": result.usage_metadata.get("total_tokens", 0),
            }

        return ChatResponse(
            content=result.content if isinstance(result.content, str) else str(result.content),
            tool_calls=tool_calls,
            usage=usage,
            raw=result,
        )

    async def stream_chat(
        self,
        messages: list[BaseMessage],
        *,
        tools: Optional[list[BaseTool]] = None,
    ) -> AsyncIterator[str]:
        """Yield incremental text chunks as they arrive from the model."""
        model = self._build_model(stream=True, tools=tools)
        async for chunk in model.astream(messages):
            chunk: AIMessageChunk  # type: ignore[no-redef]
            if chunk.content:
                if isinstance(chunk.content, str):
                    yield chunk.content
                else:
                    # Some models return list-of-parts; concatenate text parts.
                    yield "".join(
                        part.get("text", "") if isinstance(part, dict) else str(part)
                        for part in chunk.content
                    )
