"""Async CRUD service for conversation sessions."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from venux_code.db.engine import get_session_factory
from venux_code.db.models import SessionRow


class SessionService:
    """Stateless async service – every method accepts or creates its own
    ``AsyncSession`` so callers retain full control over transaction
    boundaries.
    """

    # ── Create ─────────────────────────────────────────────────────────────

    @staticmethod
    async def create(
        *,
        title: Optional[str] = None,
        parent_session_id: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> SessionRow:
        """Create a new session row and return it."""
        row = SessionRow(title=title, parent_session_id=parent_session_id)

        if session is not None:
            session.add(row)
            await session.flush()
            return row

        async with get_session_factory()() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return row

    # ── Read ───────────────────────────────────────────────────────────────

    @staticmethod
    async def get(
        session_id: str, *, session: Optional[AsyncSession] = None
    ) -> Optional[SessionRow]:
        """Fetch a single session by *id*, or ``None``."""
        stmt = select(SessionRow).where(SessionRow.id == session_id)

        if session is not None:
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

        async with get_session_factory()() as db:
            result = await db.execute(stmt)
            return result.scalar_one_or_none()

    @staticmethod
    async def list_sessions(
        *,
        offset: int = 0,
        limit: int = 50,
        parent_session_id: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> tuple[list[SessionRow], int]:
        """Return ``(sessions, total_count)`` with optional pagination."""
        base = select(SessionRow)
        if parent_session_id is not None:
            base = base.where(SessionRow.parent_session_id == parent_session_id)
        base = base.order_by(SessionRow.created_at.desc())

        count_stmt = select(func.count()).select_from(base.subquery())
        page_stmt = base.offset(offset).limit(limit)

        async def _run(db: AsyncSession) -> tuple[list[SessionRow], int]:
            total = (await db.execute(count_stmt)).scalar() or 0
            rows = (await db.execute(page_stmt)).scalars().all()
            return list(rows), total

        if session is not None:
            return await _run(session)

        async with get_session_factory()() as db:
            return await _run(db)

    # ── Update ─────────────────────────────────────────────────────────────

    @staticmethod
    async def update(
        session_id: str,
        *,
        title: Optional[str] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        cost: Optional[float] = None,
        session: Optional[AsyncSession] = None,
    ) -> Optional[SessionRow]:
        """Patch mutable fields on an existing session."""
        async def _run(db: AsyncSession) -> Optional[SessionRow]:
            row = (
                await db.execute(
                    select(SessionRow).where(SessionRow.id == session_id)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            if title is not None:
                row.title = title
            if prompt_tokens is not None:
                row.prompt_tokens = prompt_tokens
            if completion_tokens is not None:
                row.completion_tokens = completion_tokens
            if cost is not None:
                row.cost = cost
            await db.flush()
            return row

        if session is not None:
            return await _run(session)

        async with get_session_factory()() as db:
            result = await _run(db)
            await db.commit()
            return result

    # ── Delete ─────────────────────────────────────────────────────────────

    @staticmethod
    async def delete(
        session_id: str, *, session: Optional[AsyncSession] = None
    ) -> bool:
        """Delete a session by id. Returns *True* if a row was removed."""
        async def _run(db: AsyncSession) -> bool:
            row = (
                await db.execute(
                    select(SessionRow).where(SessionRow.id == session_id)
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            await db.delete(row)
            return True

        if session is not None:
            return await _run(session)

        async with get_session_factory()() as db:
            deleted = await _run(db)
            await db.commit()
            return deleted
