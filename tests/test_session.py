"""Tests for SessionService."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from venux_code.db.models import SessionRow
from venux_code.session.service import SessionService


class TestSessionServiceCreate:
    async def test_create_with_session(self, db_session: AsyncSession):
        row = await SessionService.create(title="Hello", session=db_session)
        assert row.id is not None
        assert row.title == "Hello"
        assert row.created_at is not None

    async def test_create_no_title(self, db_session: AsyncSession):
        row = await SessionService.create(session=db_session)
        assert row.title is None

    async def test_create_with_parent(self, db_session: AsyncSession):
        parent = await SessionService.create(title="Parent", session=db_session)
        child = await SessionService.create(
            title="Child", parent_session_id=parent.id, session=db_session
        )
        assert child.parent_session_id == parent.id


class TestSessionServiceGet:
    async def test_get_existing(self, db_session: AsyncSession):
        created = await SessionService.create(title="Find Me", session=db_session)
        found = await SessionService.get(created.id, session=db_session)
        assert found is not None
        assert found.title == "Find Me"

    async def test_get_nonexistent(self, db_session: AsyncSession):
        found = await SessionService.get("nonexistent-id", session=db_session)
        assert found is None


class TestSessionServiceList:
    async def test_list_sessions(self, db_session: AsyncSession):
        for i in range(5):
            await SessionService.create(title=f"Session {i}", session=db_session)

        sessions, total = await SessionService.list_sessions(session=db_session)
        assert total == 5
        assert len(sessions) == 5

    async def test_list_with_pagination(self, db_session: AsyncSession):
        for i in range(10):
            await SessionService.create(title=f"S {i}", session=db_session)

        page1, total = await SessionService.list_sessions(
            offset=0, limit=3, session=db_session
        )
        assert total == 10
        assert len(page1) == 3

        page2, _ = await SessionService.list_sessions(
            offset=3, limit=3, session=db_session
        )
        assert len(page2) == 3

    async def test_list_filter_by_parent(self, db_session: AsyncSession):
        parent = await SessionService.create(title="Parent", session=db_session)
        await SessionService.create(
            title="Child 1", parent_session_id=parent.id, session=db_session
        )
        await SessionService.create(
            title="Child 2", parent_session_id=parent.id, session=db_session
        )
        await SessionService.create(title="Unrelated", session=db_session)

        children, total = await SessionService.list_sessions(
            parent_session_id=parent.id, session=db_session
        )
        assert total == 2
        assert all(c.parent_session_id == parent.id for c in children)


class TestSessionServiceUpdate:
    async def test_update_title(self, db_session: AsyncSession):
        row = await SessionService.create(title="Old", session=db_session)
        updated = await SessionService.update(
            row.id, title="New", session=db_session
        )
        assert updated is not None
        assert updated.title == "New"

    async def test_update_tokens(self, db_session: AsyncSession):
        row = await SessionService.create(session=db_session)
        updated = await SessionService.update(
            row.id,
            prompt_tokens=100,
            completion_tokens=50,
            cost=0.05,
            session=db_session,
        )
        assert updated is not None
        assert updated.prompt_tokens == 100
        assert updated.completion_tokens == 50
        assert updated.cost == 0.05

    async def test_update_nonexistent(self, db_session: AsyncSession):
        result = await SessionService.update(
            "nonexistent", title="X", session=db_session
        )
        assert result is None


class TestSessionServiceDelete:
    async def test_delete_existing(self, db_session: AsyncSession):
        row = await SessionService.create(title="Delete Me", session=db_session)
        result = await SessionService.delete(row.id, session=db_session)
        assert result is True

        # Verify it's gone
        found = await SessionService.get(row.id, session=db_session)
        assert found is None

    async def test_delete_nonexistent(self, db_session: AsyncSession):
        result = await SessionService.delete("nonexistent", session=db_session)
        assert result is False
