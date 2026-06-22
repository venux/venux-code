"""SQLAlchemy ORM models for Venux Code.

Tables:
  - sessions      – conversation sessions
  - messages      – individual chat messages
  - files         – files touched during a session
  - memories      – persistent agent memories / notes
  - skills        – reusable skill definitions
  - cron_jobs     – scheduled / recurring tasks
  - permissions   – tool permission grants
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Declarative base shared by all models."""

    pass


# ── Session ────────────────────────────────────────────────────────────────


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    parent_session_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("sessions.id"), nullable=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # relationships
    messages: Mapped[list[MessageRow]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    files: Mapped[list[FileRow]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Session {self.id[:8]}… title={self.title!r}>"


# ── Message ────────────────────────────────────────────────────────────────


class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user|assistant|tool|system
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # relationships
    session: Mapped[SessionRow] = relationship(back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message {self.id[:8]}… role={self.role}>"


# ── File ───────────────────────────────────────────────────────────────────


class FileRow(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id"), index=True
    )
    path: Mapped[str] = mapped_column(String(1024))
    action: Mapped[str] = mapped_column(String(16))  # read|write|delete
    diff: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # relationships
    session: Mapped[SessionRow] = relationship(back_populates="files")

    def __repr__(self) -> str:
        return f"<File {self.id[:8]}… action={self.action} path={self.path!r}>"


# ── Memory ─────────────────────────────────────────────────────────────────


class MemoryRow(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    scope: Mapped[str] = mapped_column(String(64), default="global")  # global|project|session
    key: Mapped[str] = mapped_column(String(256), index=True)
    value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:
        return f"<Memory {self.id[:8]}… key={self.key!r}>"


# ── Skill ──────────────────────────────────────────────────────────────────


class SkillRow(Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text)  # skill body / instructions
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:
        return f"<Skill {self.name!r}>"


# ── CronJob ────────────────────────────────────────────────────────────────


class CronJobRow(Base):
    __tablename__ = "cron_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(128), index=True)
    schedule: Mapped[str] = mapped_column(String(256))  # cron expression / interval
    prompt: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:
        return f"<CronJob {self.name!r} schedule={self.schedule!r}>"


# ── Permission ─────────────────────────────────────────────────────────────


class PermissionRow(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id"), index=True
    )
    tool: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64))
    path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    granted: Mapped[bool] = mapped_column(Boolean, default=False)
    denied: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    def __repr__(self) -> str:
        status = "granted" if self.granted else "denied" if self.denied else "pending"
        return f"<Permission {self.id[:8]}… {self.tool}/{self.action} [{status}]>"
