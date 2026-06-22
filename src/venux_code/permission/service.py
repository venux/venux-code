"""Async permission request / grant / deny service.

Permissions are keyed by the quadruple
``(session_id, tool, action, path)`` – meaning "may *session* invoke
*tool* with *action* on *path*?".

When the global ``auto_approve`` flag (or a per-tool allow-list) is
active, requests are granted immediately without user interaction.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from venux_code.db.engine import get_session_factory
from venux_code.db.models import PermissionRow


class PermissionDecision:
    """Result of a permission check."""

    def __init__(
        self,
        *,
        granted: bool,
        denied: bool,
        auto_approved: bool = False,
        permission_id: Optional[str] = None,
    ) -> None:
        self.granted = granted
        self.denied = denied
        self.auto_approved = auto_approved
        self.permission_id = permission_id

    @property
    def allowed(self) -> bool:
        return self.granted and not self.denied

    @property
    def pending(self) -> bool:
        return not self.granted and not self.denied

    def __repr__(self) -> str:
        if self.granted:
            tag = "auto-approved" if self.auto_approved else "granted"
        elif self.denied:
            tag = "denied"
        else:
            tag = "pending"
        return f"<PermissionDecision {tag}>"


class PermissionService:
    """Stateless async service for managing tool permissions."""

    # ── Request ────────────────────────────────────────────────────────────

    @staticmethod
    async def request(
        *,
        session_id: str,
        tool: str,
        action: str,
        path: Optional[str] = None,
        auto_approve: bool = False,
        auto_approve_tools: Optional[list[str]] = None,
        denied_tools: Optional[list[str]] = None,
        session: Optional[AsyncSession] = None,
    ) -> PermissionDecision:
        """Request permission for a tool invocation.

        If *auto_approve* is globally enabled **or** the tool is in
        *auto_approve_tools*, the permission is granted immediately.
        If the tool is in *denied_tools*, it is denied immediately.
        Otherwise a pending row is created and the caller must wait for
        :meth:`grant` or :meth:`deny`.
        """
        auto_approve_tools = auto_approve_tools or []
        denied_tools = denied_tools or []

        # ── Fast-path: auto-approve ────────────────────────────────────────
        if auto_approve or tool in auto_approve_tools:
            row = PermissionRow(
                session_id=session_id,
                tool=tool,
                action=action,
                path=path,
                granted=True,
                denied=False,
                auto_approved=True,
            )
            if session is not None:
                session.add(row)
                await session.flush()
            else:
                async with get_session_factory()() as db:
                    db.add(row)
                    await db.commit()
                    await db.refresh(row)
            return PermissionDecision(
                granted=True,
                denied=False,
                auto_approved=True,
                permission_id=row.id,
            )

        # ── Fast-path: explicitly denied ───────────────────────────────────
        if tool in denied_tools:
            row = PermissionRow(
                session_id=session_id,
                tool=tool,
                action=action,
                path=path,
                granted=False,
                denied=True,
                auto_approved=False,
            )
            if session is not None:
                session.add(row)
                await session.flush()
            else:
                async with get_session_factory()() as db:
                    db.add(row)
                    await db.commit()
                    await db.refresh(row)
            return PermissionDecision(
                granted=False,
                denied=True,
                permission_id=row.id,
            )

        # ── Create pending row ─────────────────────────────────────────────
        row = PermissionRow(
            session_id=session_id,
            tool=tool,
            action=action,
            path=path,
            granted=False,
            denied=False,
            auto_approved=False,
        )
        if session is not None:
            session.add(row)
            await session.flush()
        else:
            async with get_session_factory()() as db:
                db.add(row)
                await db.commit()
                await db.refresh(row)
        return PermissionDecision(
            granted=False,
            denied=False,
            permission_id=row.id,
        )

    # ── Grant ──────────────────────────────────────────────────────────────

    @staticmethod
    async def grant(
        permission_id: str, *, session: Optional[AsyncSession] = None
    ) -> Optional[PermissionDecision]:
        """Mark a pending permission as *granted*."""
        async def _run(db: AsyncSession) -> Optional[PermissionDecision]:
            row = (
                await db.execute(
                    select(PermissionRow).where(
                        PermissionRow.id == permission_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            row.granted = True
            row.denied = False
            await db.flush()
            return PermissionDecision(
                granted=True,
                denied=False,
                permission_id=row.id,
            )

        if session is not None:
            return await _run(session)

        async with get_session_factory()() as db:
            result = await _run(db)
            await db.commit()
            return result

    # ── Deny ───────────────────────────────────────────────────────────────

    @staticmethod
    async def deny(
        permission_id: str, *, session: Optional[AsyncSession] = None
    ) -> Optional[PermissionDecision]:
        """Mark a pending permission as *denied*."""
        async def _run(db: AsyncSession) -> Optional[PermissionDecision]:
            row = (
                await db.execute(
                    select(PermissionRow).where(
                        PermissionRow.id == permission_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            row.granted = False
            row.denied = True
            await db.flush()
            return PermissionDecision(
                granted=False,
                denied=True,
                permission_id=row.id,
            )

        if session is not None:
            return await _run(session)

        async with get_session_factory()() as db:
            result = await _run(db)
            await db.commit()
            return result

    # ── Query ──────────────────────────────────────────────────────────────

    @staticmethod
    async def check(
        *,
        session_id: str,
        tool: str,
        action: str,
        path: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> Optional[PermissionDecision]:
        """Look up an existing permission for the quadruple.

        Returns ``None`` when no record exists.
        """
        stmt = (
            select(PermissionRow)
            .where(PermissionRow.session_id == session_id)
            .where(PermissionRow.tool == tool)
            .where(PermissionRow.action == action)
            .where(PermissionRow.path == path)
            .order_by(PermissionRow.created_at.desc())
            .limit(1)
        )

        async def _run(db: AsyncSession) -> Optional[PermissionDecision]:
            row = (await db.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            return PermissionDecision(
                granted=row.granted,
                denied=row.denied,
                auto_approved=row.auto_approved,
                permission_id=row.id,
            )

        if session is not None:
            return await _run(session)

        async with get_session_factory()() as db:
            return await _run(db)

    @staticmethod
    async def list_by_session(
        session_id: str,
        *,
        session: Optional[AsyncSession] = None,
    ) -> list[PermissionDecision]:
        """Return all permission records for a session."""
        stmt = (
            select(PermissionRow)
            .where(PermissionRow.session_id == session_id)
            .order_by(PermissionRow.created_at.desc())
        )

        async def _run(db: AsyncSession) -> list[PermissionDecision]:
            rows = (await db.execute(stmt)).scalars().all()
            return [
                PermissionDecision(
                    granted=r.granted,
                    denied=r.denied,
                    auto_approved=r.auto_approved,
                    permission_id=r.id,
                )
                for r in rows
            ]

        if session is not None:
            return await _run(session)

        async with get_session_factory()() as db:
            return await _run(db)
