"""Async CRUD service for chat messages."""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from venux_code.db.engine import get_session_factory
from venux_code.db.models import MessageRow
from venux_code.message.models import Message, MessageRole, ToolCall


# ── Conversion helpers ─────────────────────────────────────────────────────


def _row_to_domain(row: MessageRow) -> Message:
    """Map a DB row to the Pydantic ``Message`` domain model."""
    tool_calls_raw = json.loads(row.tool_calls) if row.tool_calls else []
    return Message(
        id=row.id,
        session_id=row.session_id,
        role=MessageRole(row.role),
        content=row.content,
        tool_calls=[ToolCall(**tc) for tc in tool_calls_raw],
        model=row.model,
        tokens_in=row.tokens_in,
        tokens_out=row.tokens_out,
        cost=row.cost,
        created_at=row.created_at,
    )


def _domain_to_row(msg: Message) -> MessageRow:
    """Map the Pydantic ``Message`` domain model to a DB row."""
    tc_json = (
        json.dumps([tc.model_dump() for tc in msg.tool_calls])
        if msg.tool_calls
        else None
    )
    return MessageRow(
        id=msg.id,
        session_id=msg.session_id,
        role=msg.role.value,
        content=msg.content,
        tool_calls=tc_json,
        model=msg.model,
        tokens_in=msg.tokens_in,
        tokens_out=msg.tokens_out,
        cost=msg.cost,
        created_at=msg.created_at,
    )


class MessageService:
    """Stateless async CRUD service for messages."""

    # ── Create ─────────────────────────────────────────────────────────────

    @staticmethod
    async def create(
        msg: Message, *, session: Optional[AsyncSession] = None
    ) -> Message:
        """Persist a new message and return the domain model."""
        row = _domain_to_row(msg)

        if session is not None:
            session.add(row)
            await session.flush()
            return _row_to_domain(row)

        async with get_session_factory()() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return _row_to_domain(row)

    # ── Read ───────────────────────────────────────────────────────────────

    @staticmethod
    async def get(
        message_id: str, *, session: Optional[AsyncSession] = None
    ) -> Optional[Message]:
        """Fetch a single message by id."""
        stmt = select(MessageRow).where(MessageRow.id == message_id)

        if session is not None:
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _row_to_domain(row) if row else None

        async with get_session_factory()() as db:
            row = (await db.execute(stmt)).scalar_one_or_none()
            return _row_to_domain(row) if row else None

    @staticmethod
    async def list_by_session(
        session_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        session: Optional[AsyncSession] = None,
    ) -> tuple[list[Message], int]:
        """Return ``(messages, total_count)`` for a given session, ordered
        chronologically.
        """
        base = (
            select(MessageRow)
            .where(MessageRow.session_id == session_id)
            .order_by(MessageRow.created_at.asc())
        )
        count_stmt = select(func.count()).select_from(base.subquery())
        page_stmt = base.offset(offset).limit(limit)

        async def _run(db: AsyncSession) -> tuple[list[Message], int]:
            total = (await db.execute(count_stmt)).scalar() or 0
            rows = (await db.execute(page_stmt)).scalars().all()
            return [_row_to_domain(r) for r in rows], total

        if session is not None:
            return await _run(session)

        async with get_session_factory()() as db:
            return await _run(db)

    # ── Update ─────────────────────────────────────────────────────────────

    @staticmethod
    async def update(
        message_id: str,
        *,
        content: Optional[str] = None,
        tool_calls: Optional[list[ToolCall]] = None,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        cost: Optional[float] = None,
        session: Optional[AsyncSession] = None,
    ) -> Optional[Message]:
        """Patch mutable fields on an existing message."""
        async def _run(db: AsyncSession) -> Optional[Message]:
            row = (
                await db.execute(
                    select(MessageRow).where(MessageRow.id == message_id)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            if content is not None:
                row.content = content
            if tool_calls is not None:
                row.tool_calls = json.dumps(
                    [tc.model_dump() for tc in tool_calls]
                )
            if tokens_in is not None:
                row.tokens_in = tokens_in
            if tokens_out is not None:
                row.tokens_out = tokens_out
            if cost is not None:
                row.cost = cost
            await db.flush()
            return _row_to_domain(row)

        if session is not None:
            return await _run(session)

        async with get_session_factory()() as db:
            result = await _run(db)
            await db.commit()
            return result

    # ── Delete ─────────────────────────────────────────────────────────────

    @staticmethod
    async def delete(
        message_id: str, *, session: Optional[AsyncSession] = None
    ) -> bool:
        """Delete a message.  Returns *True* if a row was removed."""
        async def _run(db: AsyncSession) -> bool:
            row = (
                await db.execute(
                    select(MessageRow).where(MessageRow.id == message_id)
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

    # ── Bulk helpers ───────────────────────────────────────────────────────

    @staticmethod
    async def delete_by_session(
        session_id: str, *, session: Optional[AsyncSession] = None
    ) -> int:
        """Delete *all* messages in a session.  Returns count removed."""
        from sqlalchemy import delete as sa_delete

        stmt = sa_delete(MessageRow).where(MessageRow.session_id == session_id)

        async def _run(db: AsyncSession) -> int:
            result = await db.execute(stmt)
            return result.rowcount  # type: ignore[return-value]

        if session is not None:
            return await _run(session)

        async with get_session_factory()() as db:
            count = await _run(db)
            await db.commit()
            return count
