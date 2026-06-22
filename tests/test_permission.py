"""Tests for PermissionService."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from venux_code.db.models import SessionRow
from venux_code.permission.service import PermissionService, PermissionDecision


class TestPermissionDecision:
    def test_allowed(self):
        d = PermissionDecision(granted=True, denied=False)
        assert d.allowed is True
        assert d.pending is False

    def test_denied(self):
        d = PermissionDecision(granted=False, denied=True)
        assert d.allowed is False
        assert d.pending is False

    def test_pending(self):
        d = PermissionDecision(granted=False, denied=False)
        assert d.allowed is False
        assert d.pending is True

    def test_auto_approved(self):
        d = PermissionDecision(granted=True, denied=False, auto_approved=True)
        assert d.allowed is True
        assert d.auto_approved is True

    def test_repr_granted(self):
        d = PermissionDecision(granted=True, denied=False)
        assert "granted" in repr(d)

    def test_repr_auto_approved(self):
        d = PermissionDecision(granted=True, denied=False, auto_approved=True)
        assert "auto-approved" in repr(d)

    def test_repr_denied(self):
        d = PermissionDecision(granted=False, denied=True)
        assert "denied" in repr(d)

    def test_repr_pending(self):
        d = PermissionDecision(granted=False, denied=False)
        assert "pending" in repr(d)


class TestPermissionServiceRequest:
    async def test_request_pending(self, db_session: AsyncSession, test_session: SessionRow):
        decision = await PermissionService.request(
            session_id=test_session.id,
            tool="bash",
            action="execute",
            path="/tmp/test.sh",
            session=db_session,
        )
        assert decision.pending is True
        assert decision.permission_id is not None

    async def test_request_auto_approve_global(self, db_session: AsyncSession, test_session: SessionRow):
        decision = await PermissionService.request(
            session_id=test_session.id,
            tool="bash",
            action="execute",
            auto_approve=True,
            session=db_session,
        )
        assert decision.allowed is True
        assert decision.auto_approved is True

    async def test_request_auto_approve_tool(self, db_session: AsyncSession, test_session: SessionRow):
        decision = await PermissionService.request(
            session_id=test_session.id,
            tool="bash",
            action="execute",
            auto_approve_tools=["bash", "write"],
            session=db_session,
        )
        assert decision.allowed is True
        assert decision.auto_approved is True

    async def test_request_denied_tool(self, db_session: AsyncSession, test_session: SessionRow):
        decision = await PermissionService.request(
            session_id=test_session.id,
            tool="rm",
            action="delete",
            denied_tools=["rm"],
            session=db_session,
        )
        assert decision.allowed is False
        assert decision.denied is True

    async def test_request_tool_not_in_lists(self, db_session: AsyncSession, test_session: SessionRow):
        decision = await PermissionService.request(
            session_id=test_session.id,
            tool="view",
            action="read",
            auto_approve_tools=["bash"],
            denied_tools=["rm"],
            session=db_session,
        )
        assert decision.pending is True


class TestPermissionServiceGrantDeny:
    async def test_grant(self, db_session: AsyncSession, test_session: SessionRow):
        decision = await PermissionService.request(
            session_id=test_session.id,
            tool="bash",
            action="execute",
            session=db_session,
        )
        assert decision.pending is True

        granted = await PermissionService.grant(
            decision.permission_id, session=db_session
        )
        assert granted is not None
        assert granted.allowed is True

    async def test_deny(self, db_session: AsyncSession, test_session: SessionRow):
        decision = await PermissionService.request(
            session_id=test_session.id,
            tool="bash",
            action="execute",
            session=db_session,
        )
        denied = await PermissionService.deny(
            decision.permission_id, session=db_session
        )
        assert denied is not None
        assert denied.denied is True

    async def test_grant_nonexistent(self, db_session: AsyncSession):
        result = await PermissionService.grant("nonexistent", session=db_session)
        assert result is None

    async def test_deny_nonexistent(self, db_session: AsyncSession):
        result = await PermissionService.deny("nonexistent", session=db_session)
        assert result is None


class TestPermissionServiceCheck:
    async def test_check_existing(self, db_session: AsyncSession, test_session: SessionRow):
        await PermissionService.request(
            session_id=test_session.id,
            tool="bash",
            action="execute",
            path="/tmp/test.sh",
            auto_approve=True,
            session=db_session,
        )

        result = await PermissionService.check(
            session_id=test_session.id,
            tool="bash",
            action="execute",
            path="/tmp/test.sh",
            session=db_session,
        )
        assert result is not None
        assert result.allowed is True

    async def test_check_no_record(self, db_session: AsyncSession, test_session: SessionRow):
        result = await PermissionService.check(
            session_id=test_session.id,
            tool="nonexistent",
            action="noop",
            session=db_session,
        )
        assert result is None


class TestPermissionServiceListBySession:
    async def test_list_permissions(self, db_session: AsyncSession, test_session: SessionRow):
        # Create multiple permissions
        await PermissionService.request(
            session_id=test_session.id,
            tool="bash",
            action="execute",
            auto_approve=True,
            session=db_session,
        )
        await PermissionService.request(
            session_id=test_session.id,
            tool="write",
            action="create",
            auto_approve=True,
            session=db_session,
        )

        perms = await PermissionService.list_by_session(
            test_session.id, session=db_session
        )
        assert len(perms) == 2

    async def test_list_empty(self, db_session: AsyncSession, test_session: SessionRow):
        perms = await PermissionService.list_by_session(
            test_session.id, session=db_session
        )
        assert len(perms) == 0
