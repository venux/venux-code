"""Tests for MessageService."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from venux_code.db.models import SessionRow
from venux_code.message.models import Message, MessageRole, ToolCall, ToolCallFunction
from venux_code.message.service import MessageService


def _make_message(session_id: str, role: str = "user", content: str = "Hello") -> Message:
    return Message(session_id=session_id, role=MessageRole(role), content=content)


class TestMessageServiceCreate:
    async def test_create_user_message(self, db_session: AsyncSession, test_session: SessionRow):
        msg = _make_message(test_session.id, "user", "What is Python?")
        result = await MessageService.create(msg, session=db_session)
        assert result.id is not None
        assert result.content == "What is Python?"
        assert result.role == MessageRole.USER

    async def test_create_assistant_message(self, db_session: AsyncSession, test_session: SessionRow):
        msg = _make_message(test_session.id, "assistant", "Python is a language.")
        result = await MessageService.create(msg, session=db_session)
        assert result.role == MessageRole.ASSISTANT

    async def test_create_with_tool_calls(self, db_session: AsyncSession, test_session: SessionRow):
        msg = Message(
            session_id=test_session.id,
            role=MessageRole.ASSISTANT,
            content=None,
            tool_calls=[
                ToolCall(
                    function=ToolCallFunction(
                        name="bash",
                        arguments='{"command": "ls"}',
                    )
                )
            ],
        )
        result = await MessageService.create(msg, session=db_session)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].function.name == "bash"


class TestMessageServiceGet:
    async def test_get_existing(self, db_session: AsyncSession, test_session: SessionRow):
        msg = _make_message(test_session.id, "user", "Find me")
        created = await MessageService.create(msg, session=db_session)
        found = await MessageService.get(created.id, session=db_session)
        assert found is not None
        assert found.content == "Find me"

    async def test_get_nonexistent(self, db_session: AsyncSession):
        found = await MessageService.get("nonexistent", session=db_session)
        assert found is None


class TestMessageServiceListBySession:
    async def test_list_chronological(self, db_session: AsyncSession, test_session: SessionRow):
        for i in range(5):
            msg = _make_message(test_session.id, "user", f"Message {i}")
            await MessageService.create(msg, session=db_session)

        messages, total = await MessageService.list_by_session(
            test_session.id, session=db_session
        )
        assert total == 5
        assert len(messages) == 5
        # Should be chronological (ascending)
        for i in range(len(messages) - 1):
            assert messages[i].created_at <= messages[i + 1].created_at

    async def test_list_empty_session(self, db_session: AsyncSession, test_session: SessionRow):
        messages, total = await MessageService.list_by_session(
            test_session.id, session=db_session
        )
        assert total == 0
        assert messages == []

    async def test_list_with_pagination(self, db_session: AsyncSession, test_session: SessionRow):
        for i in range(10):
            msg = _make_message(test_session.id, "user", f"M{i}")
            await MessageService.create(msg, session=db_session)

        page, total = await MessageService.list_by_session(
            test_session.id, offset=2, limit=3, session=db_session
        )
        assert total == 10
        assert len(page) == 3


class TestMessageServiceUpdate:
    async def test_update_content(self, db_session: AsyncSession, test_session: SessionRow):
        msg = _make_message(test_session.id, "user", "Old content")
        created = await MessageService.create(msg, session=db_session)
        updated = await MessageService.update(
            created.id, content="New content", session=db_session
        )
        assert updated is not None
        assert updated.content == "New content"

    async def test_update_tokens(self, db_session: AsyncSession, test_session: SessionRow):
        msg = _make_message(test_session.id, "assistant", "Response")
        created = await MessageService.create(msg, session=db_session)
        updated = await MessageService.update(
            created.id, tokens_in=100, tokens_out=50, cost=0.01, session=db_session
        )
        assert updated is not None
        assert updated.tokens_in == 100
        assert updated.tokens_out == 50

    async def test_update_nonexistent(self, db_session: AsyncSession):
        result = await MessageService.update("fake-id", content="X", session=db_session)
        assert result is None


class TestMessageServiceDelete:
    async def test_delete_existing(self, db_session: AsyncSession, test_session: SessionRow):
        msg = _make_message(test_session.id, "user", "Delete me")
        created = await MessageService.create(msg, session=db_session)
        result = await MessageService.delete(created.id, session=db_session)
        assert result is True

        found = await MessageService.get(created.id, session=db_session)
        assert found is None

    async def test_delete_nonexistent(self, db_session: AsyncSession):
        result = await MessageService.delete("nonexistent", session=db_session)
        assert result is False

    async def test_delete_by_session(self, db_session: AsyncSession, test_session: SessionRow):
        for i in range(5):
            msg = _make_message(test_session.id, "user", f"Msg {i}")
            await MessageService.create(msg, session=db_session)

        count = await MessageService.delete_by_session(
            test_session.id, session=db_session
        )
        assert count == 5

        messages, total = await MessageService.list_by_session(
            test_session.id, session=db_session
        )
        assert total == 0
