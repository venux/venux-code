"""Pydantic models for messages, tool calls, and attachments.

These are the *domain* / *API* models, distinct from the SQLAlchemy row
models in :mod:`venux_code.db.models`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────


class MessageRole(str, Enum):
    """Allowed message roles."""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SYSTEM = "system"


# ── Tool Call ──────────────────────────────────────────────────────────────


class ToolCallFunction(BaseModel):
    """The function invocation inside a tool call."""

    name: str
    arguments: str  # JSON-encoded string


class ToolCall(BaseModel):
    """Represents a single tool/function call requested by the model."""

    id: str = Field(default_factory=lambda: f"call_{uuid4().hex[:24]}")
    type: str = "function"
    function: ToolCallFunction


# ── Attachment ─────────────────────────────────────────────────────────────


class Attachment(BaseModel):
    """A file or binary attachment included with a message."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    filename: Optional[str] = None
    mime_type: str = "application/octet-stream"
    size_bytes: int = 0
    url: Optional[str] = None  # local path or remote URL
    data: Optional[str] = None  # base64-encoded inline data


# ── Message ────────────────────────────────────────────────────────────────


class Message(BaseModel):
    """Domain model for a single chat message."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    role: MessageRole
    content: Optional[str] = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: Optional[str] = None  # for role=tool responses
    model: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    attachments: list[Attachment] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # ── helpers ────────────────────────────────────────────────────────────

    @property
    def is_user(self) -> bool:
        return self.role == MessageRole.USER

    @property
    def is_assistant(self) -> bool:
        return self.role == MessageRole.ASSISTANT

    @property
    def is_tool(self) -> bool:
        return self.role == MessageRole.TOOL

    @property
    def is_system(self) -> bool:
        return self.role == MessageRole.SYSTEM

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    def to_api_dict(self) -> dict[str, Any]:
        """Serialize to the dict format expected by most LLM APIs."""
        d: dict[str, Any] = {"role": self.role.value}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_calls:
            d["tool_calls"] = [tc.model_dump() for tc in self.tool_calls]
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


# ── Pagination helper ─────────────────────────────────────────────────────


class MessagePage(BaseModel):
    """Paginated list of messages."""

    items: list[Message] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 50
