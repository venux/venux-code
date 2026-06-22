"""Tests for database models and engine."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from venux_code.db.models import (
    Base,
    SessionRow,
    MessageRow,
    FileRow,
    MemoryRow,
    SkillRow,
    CronJobRow,
    PermissionRow,
)


class TestSessionRow:
    async def test_create(self, db_session: AsyncSession):
        row = SessionRow(title="Test")
        db_session.add(row)
        await db_session.flush()

        assert row.id is not None
        assert len(row.id) == 36  # UUID
        assert row.title == "Test"
        assert row.prompt_tokens == 0
        assert row.completion_tokens == 0
        assert row.cost == 0.0
        assert row.created_at is not None
        assert row.updated_at is not None

    async def test_read(self, db_session: AsyncSession):
        row = SessionRow(title="Readable")
        db_session.add(row)
        await db_session.flush()

        result = await db_session.execute(
            select(SessionRow).where(SessionRow.id == row.id)
        )
        fetched = result.scalar_one()
        assert fetched.title == "Readable"

    async def test_repr(self, db_session: AsyncSession):
        row = SessionRow(title="Repr Test")
        db_session.add(row)
        await db_session.flush()
        r = repr(row)
        assert "Session" in r
        assert "Repr Test" in r

    async def test_parent_session(self, db_session: AsyncSession):
        parent = SessionRow(title="Parent")
        db_session.add(parent)
        await db_session.flush()

        child = SessionRow(title="Child", parent_session_id=parent.id)
        db_session.add(child)
        await db_session.flush()

        assert child.parent_session_id == parent.id


class TestMessageRow:
    async def test_create(self, db_session: AsyncSession):
        session = SessionRow(title="Msg Test")
        db_session.add(session)
        await db_session.flush()

        msg = MessageRow(
            session_id=session.id,
            role="user",
            content="Hello!",
        )
        db_session.add(msg)
        await db_session.flush()

        assert msg.id is not None
        assert msg.role == "user"
        assert msg.content == "Hello!"
        assert msg.tokens_in == 0
        assert msg.tokens_out == 0

    async def test_relationship(self, db_session: AsyncSession):
        session = SessionRow(title="Rel Test")
        db_session.add(session)
        await db_session.flush()

        msg = MessageRow(session_id=session.id, role="assistant", content="Hi!")
        db_session.add(msg)
        await db_session.flush()

        assert msg.session.title == "Rel Test"


class TestFileRow:
    async def test_create(self, db_session: AsyncSession):
        session = SessionRow(title="File Test")
        db_session.add(session)
        await db_session.flush()

        f = FileRow(
            session_id=session.id,
            path="/tmp/test.py",
            action="write",
            diff="-old\n+new",
        )
        db_session.add(f)
        await db_session.flush()

        assert f.id is not None
        assert f.path == "/tmp/test.py"
        assert f.action == "write"


class TestMemoryRow:
    async def test_create(self, db_session: AsyncSession):
        row = MemoryRow(
            scope="global",
            key="user_pref",
            value="likes dark mode",
        )
        db_session.add(row)
        await db_session.flush()

        assert row.id is not None
        assert row.scope == "global"
        assert row.key == "user_pref"


class TestSkillRow:
    async def test_create(self, db_session: AsyncSession):
        row = SkillRow(
            name="test-skill",
            description="A test skill",
            content="# Instructions\nDo stuff.",
            enabled=True,
        )
        db_session.add(row)
        await db_session.flush()

        assert row.id is not None
        assert row.name == "test-skill"
        assert row.enabled is True


class TestCronJobRow:
    async def test_create(self, db_session: AsyncSession):
        row = CronJobRow(
            name="daily-check",
            schedule="0 9 * * *",
            prompt="Run the daily check",
            enabled=True,
        )
        db_session.add(row)
        await db_session.flush()

        assert row.id is not None
        assert row.name == "daily-check"
        assert row.last_run_at is None


class TestPermissionRow:
    async def test_create(self, db_session: AsyncSession):
        session = SessionRow(title="Perm Test")
        db_session.add(session)
        await db_session.flush()

        row = PermissionRow(
            session_id=session.id,
            tool="bash",
            action="execute",
            path="/tmp/test.sh",
            granted=True,
            denied=False,
            auto_approved=False,
        )
        db_session.add(row)
        await db_session.flush()

        assert row.id is not None
        assert row.granted is True
        assert row.denied is False

    async def test_repr_granted(self, db_session: AsyncSession):
        session = SessionRow(title="Repr Perm")
        db_session.add(session)
        await db_session.flush()

        row = PermissionRow(
            session_id=session.id,
            tool="bash",
            action="run",
            granted=True,
        )
        db_session.add(row)
        await db_session.flush()
        r = repr(row)
        assert "granted" in r
