"""Cron job data models.

Defines ``CronJob``, ``CronSchedule``, and ``DeliveryConfig`` used by the
scheduler and service layers.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Schedule types ──────────────────────────────────────────────────────────


class ScheduleType(str, Enum):
    """Supported trigger types."""

    CRON = "cron"        # e.g. "*/5 * * * *"
    INTERVAL = "interval"  # e.g. every 30 minutes
    DATE = "date"        # one-shot at a specific datetime


class CronSchedule(BaseModel):
    """Describes *when* a job should run.

    Examples
    --------
    - ``CronSchedule(type="cron", expression="0 9 * * 1-5")``  → weekdays 09:00
    - ``CronSchedule(type="interval", minutes=30)``             → every 30 min
    - ``CronSchedule(type="date", run_at=datetime(...))``       → one-shot
    """

    type: ScheduleType
    expression: Optional[str] = None      # cron expression (for type=cron)
    seconds: int = 0
    minutes: int = 0
    hours: int = 0
    days: int = 0
    weeks: int = 0
    run_at: Optional[datetime] = None     # for type=date
    timezone: str = "UTC"


# ── Delivery configuration ─────────────────────────────────────────────────


class DeliveryMethod(str, Enum):
    """How the job result should be delivered."""

    NONE = "none"
    CHAT = "chat"        # push to the current Feishu / chat session
    WEBHOOK = "webhook"  # POST to a URL
    EMAIL = "email"


class DeliveryConfig(BaseModel):
    """Delivery settings for a cron job result."""

    method: DeliveryMethod = DeliveryMethod.NONE
    target: Optional[str] = None        # URL for webhook, address for email
    include_output: bool = True


# ── Repeat policy ───────────────────────────────────────────────────────────


class RepeatPolicy(str, Enum):
    """What to do after a one-shot (date) job finishes."""

    NONE = "none"          # run once
    RESCHEDULE = "reschedule"  # re-add with same schedule (interval/cron)


# ── CronJob model ───────────────────────────────────────────────────────────


class CronJob(BaseModel):
    """A single scheduled job.

    Attributes
    ----------
    id:
        UUID assigned on creation.
    name:
        Human-readable label.
    schedule:
        When to run.
    prompt:
        The prompt sent to the agent when the job fires.
    skills:
        Skill names to load for this job's agent session.
    script:
        Optional shell script to run instead of (or before) the prompt.
    no_agent:
        If ``True``, only run the *script* without spawning an agent.
    deliver:
        How to deliver the result.
    repeat:
        Repeat policy after completion.
    enabled:
        Whether the scheduler should consider this job.
    last_run:
        Timestamp of the most recent execution.
    next_run:
        Timestamp of the next scheduled execution (computed by APScheduler).
    metadata:
        Arbitrary key-value data attached to the job.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str = ""
    schedule: CronSchedule
    prompt: str = ""
    skills: list[str] = Field(default_factory=list)
    script: Optional[str] = None
    no_agent: bool = False
    deliver: DeliveryConfig = Field(default_factory=DeliveryConfig)
    repeat: RepeatPolicy = RepeatPolicy.NONE
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    # ── Serialisation helpers ───────────────────────────────────────────────

    def to_storage_dict(self) -> dict[str, Any]:
        """Export for JSON/YAML persistence."""
        return self.model_dump(mode="json")

    @classmethod
    def from_storage_dict(cls, data: dict[str, Any]) -> CronJob:
        """Reconstruct from persisted dict."""
        return cls.model_validate(data)
