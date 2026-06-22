"""Pydantic models for the Skills system."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SkillSource(str, Enum):
    """Where a skill originated from."""

    LOCAL = "local"      # User-created in ~/.venux-code/skills/
    PROJECT = "project"  # Project-level .venux-code/skills/
    HUB = "hub"          # Installed from remote hub / URL
    AUTO = "auto"        # Auto-generated from conversation


class Skill(BaseModel):
    """A reusable procedure / instruction set the agent can load."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    content: str  # Markdown body / instructions
    category: str = "general"
    tags: list[str] = Field(default_factory=list)
    version: str = "1.0.0"
    source: SkillSource = SkillSource.LOCAL
    enabled: bool = True
    file_path: Optional[str] = None  # Path to SKILL.md if loaded from disk
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        """Update the ``updated_at`` timestamp to now."""
        self.updated_at = datetime.now(timezone.utc)

    @property
    def slug(self) -> str:
        """URL/filesystem-safe version of the name."""
        return self.name.lower().replace(" ", "-").replace("_", "-")
