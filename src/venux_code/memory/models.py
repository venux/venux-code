"""Pydantic models for the Memory system."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class MemoryCategory(str, Enum):
    """Categories for memory entries."""

    USER_PREF = "user_pref"
    PROJECT = "project"
    TOOL = "tool"
    GENERAL = "general"


class MemoryEntry(BaseModel):
    """A single memory entry stored by the agent."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    category: MemoryCategory = MemoryCategory.GENERAL
    tags: list[str] = Field(default_factory=list)
    trust_score: float = Field(default=0.5, ge=0.0, le=1.0)
    embedding: Optional[list[float]] = None
    source_session_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        """Update the ``updated_at`` timestamp to now."""
        self.updated_at = datetime.now(timezone.utc)


class UserProfile(BaseModel):
    """Persistent user profile for personalisation."""

    name: str = ""
    role: str = ""
    preferences: dict[str, Any] = Field(default_factory=dict)
    environment: dict[str, Any] = Field(default_factory=dict)
    corrections: list[str] = Field(default_factory=list)

    def merge(self, other: UserProfile) -> UserProfile:
        """Return a new profile merging *other* into *self* (other wins on conflicts)."""
        return UserProfile(
            name=other.name or self.name,
            role=other.role or self.role,
            preferences={**self.preferences, **other.preferences},
            environment={**self.environment, **other.environment},
            corrections=list({*self.corrections, *other.corrections}),
        )
