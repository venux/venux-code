"""Shared pytest fixtures for Venux Code test suite.

Provides:
- In-memory SQLite database with async session factory
- Mock LLM provider for agent tests
- Test session and message fixtures
- Temporary directory fixtures
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from venux_code.db.models import Base, SessionRow, MessageRow
from venux_code.message.models import Message, MessageRole, ToolCall, ToolCallFunction


# ── Database fixtures ───────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db_engine():
    """Create an in-memory SQLite async engine with tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession bound to the test engine."""
    factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def db_session_factory(db_engine) -> async_sessionmaker[AsyncSession]:
    """Return an async_sessionmaker bound to the test engine."""
    return async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )


# ── Mock LLM provider ──────────────────────────────────────────────────────


class MockChatModel:
    """A mock LangChain-compatible chat model for testing.

    Returns a configurable sequence of responses (AIMessages).
    """

    def __init__(
        self,
        responses: list[Any] | None = None,
        *,
        final_content: str = "Done.",
    ) -> None:
        self._responses = list(responses or [])
        self._final_content = final_content
        self._call_count = 0
        self._bound_tools: list[Any] = []

    def bind_tools(self, tools: list[Any]) -> MockChatModel:
        """Return a copy with tools bound (for testing bind_tools calls)."""
        new = MockChatModel(
            responses=self._responses,
            final_content=self._final_content,
        )
        new._bound_tools = list(tools)
        new._call_count = self._call_count
        return new

    async def ainvoke(self, messages: list[Any], **kwargs: Any) -> Any:
        """Return the next mock response."""
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
            self._call_count += 1
            return resp

        # Default: return a simple AIMessage with no tool calls
        from langchain_core.messages import AIMessage

        self._call_count += 1
        return AIMessage(content=self._final_content)

    async def astream(self, messages: list[Any], **kwargs: Any):
        """Yield a single chunk for streaming tests."""
        from langchain_core.messages import AIMessageChunk

        content = self._final_content
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
            self._call_count += 1
            if hasattr(resp, "content"):
                content = resp.content

        yield AIMessageChunk(content=content)


@pytest.fixture
def mock_model():
    """Return a fresh MockChatModel."""
    return MockChatModel()


@pytest.fixture
def mock_model_factory():
    """Factory for creating MockChatModel with custom responses."""

    def _factory(responses=None, final_content="Done."):
        return MockChatModel(responses=responses, final_content=final_content)

    return _factory


# ── Session / message fixtures ──────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_session(db_session: AsyncSession) -> SessionRow:
    """Create and return a test session row."""
    row = SessionRow(title="Test Session")
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture
async def test_message(db_session: AsyncSession, test_session: SessionRow) -> MessageRow:
    """Create and return a test message row."""
    row = MessageRow(
        session_id=test_session.id,
        role="user",
        content="Hello, world!",
    )
    db_session.add(row)
    await db_session.flush()
    return row


@pytest.fixture
def sample_message():
    """Return a sample Pydantic Message domain model."""

    def _factory(
        session_id: str = "test-session-id",
        role: MessageRole = MessageRole.USER,
        content: str = "Hello, world!",
    ) -> Message:
        return Message(
            session_id=session_id,
            role=role,
            content=content,
        )

    return _factory


# ── Temporary directory fixtures ────────────────────────────────────────────


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory with some sample files."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("print('hello')\n")
    (src / "utils.py").write_text("def helper():\n    return 42\n")
    (tmp_path / "README.md").write_text("# Test Project\n")
    (tmp_path / ".gitignore").write_text("__pycache__/\n")
    return tmp_path


# ── Settings override fixture ───────────────────────────────────────────────


@pytest.fixture(autouse=False)
def reset_settings():
    """Reset the global settings singleton before/after each test."""
    from venux_code.config.settings import reset_settings

    reset_settings()
    yield
    reset_settings()


# ── Database URL fixture for services ───────────────────────────────────────


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    """Return a SQLite URL pointing to a temporary file."""
    return f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
