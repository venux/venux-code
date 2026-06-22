"""APScheduler-based async scheduler.

Wraps ``AsyncIOScheduler`` from APScheduler 3.x (or ``APScheduler>=4.0``
if available) and translates ``CronSchedule`` models into triggers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .models import CronJob, CronSchedule, ScheduleType

logger = logging.getLogger(__name__)

# Type alias for the async callback invoked when a job fires.
JobCallback = Callable[[CronJob], Coroutine[Any, Any, None]]


def _build_trigger(schedule: CronSchedule) -> Any:
    """Convert a ``CronSchedule`` into an APScheduler trigger object."""
    tz = schedule.timezone

    if schedule.type == ScheduleType.CRON:
        if not schedule.expression:
            raise ValueError("Cron schedule requires 'expression'")
        # Parse "minute hour day month day_of_week" style
        parts = schedule.expression.strip().split()
        field_names = ["minute", "hour", "day", "month", "day_of_week"]
        kwargs: dict[str, str] = {}
        for i, val in enumerate(parts[:5]):
            kwargs[field_names[i]] = val
        return CronTrigger(timezone=tz, **kwargs)

    if schedule.type == ScheduleType.INTERVAL:
        return IntervalTrigger(
            weeks=schedule.weeks,
            days=schedule.days,
            hours=schedule.hours,
            minutes=schedule.minutes,
            seconds=schedule.seconds,
            timezone=tz,
        )

    if schedule.type == ScheduleType.DATE:
        run_at = schedule.run_at
        if run_at is None:
            raise ValueError("Date schedule requires 'run_at'")
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)
        return DateTrigger(run_date=run_at, timezone=tz)

    raise ValueError(f"Unknown schedule type: {schedule.type}")


class CronScheduler:
    """Async scheduler managing cron jobs via APScheduler.

    Parameters
    ----------
    callback:
        Async function invoked with the ``CronJob`` when a trigger fires.
        Typically this delegates to ``JobRunner.run``.
    """

    def __init__(self, callback: JobCallback) -> None:
        self._callback = callback
        self._scheduler = AsyncIOScheduler()
        self._jobs: dict[str, CronJob] = {}  # job_id → CronJob
        self._started = False

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the APScheduler event loop."""
        if not self._started:
            self._scheduler.start()
            self._started = True
            logger.info("CronScheduler started")

    async def shutdown(self, *, wait: bool = True) -> None:
        """Gracefully shut down the scheduler."""
        if self._started:
            self._scheduler.shutdown(wait=wait)
            self._started = False
            logger.info("CronScheduler shut down")

    # ── Job management ──────────────────────────────────────────────────────

    def add_job(self, job: CronJob) -> None:
        """Register a job with the scheduler.

        Does nothing if the job is disabled.
        """
        if not job.enabled:
            logger.debug("Skipping disabled job %s (%s)", job.id, job.name)
            return

        trigger = _build_trigger(job.schedule)

        self._scheduler.add_job(
            self._fire_job,
            trigger=trigger,
            id=job.id,
            name=job.name or job.id,
            replace_existing=True,
            kwargs={"job": job},
        )
        self._jobs[job.id] = job
        logger.info("Scheduled job %s (%s) – next run: %s", job.id, job.name, self._get_next_run(job.id))

    def remove_job(self, job_id: str) -> bool:
        """Remove a job. Returns ``True`` if the job existed."""
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass
        existed = job_id in self._jobs
        self._jobs.pop(job_id, None)
        return existed

    def pause_job(self, job_id: str) -> bool:
        """Pause a job. Returns ``True`` if the job existed."""
        try:
            self._scheduler.pause_job(job_id)
            if job_id in self._jobs:
                self._jobs[job_id].enabled = False
            return True
        except Exception:
            return False

    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job. Returns ``True`` if the job existed."""
        try:
            self._scheduler.resume_job(job_id)
            if job_id in self._jobs:
                self._jobs[job_id].enabled = True
            return True
        except Exception:
            return False

    def get_job(self, job_id: str) -> Optional[CronJob]:
        """Return the ``CronJob`` model for *job_id*, or ``None``."""
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[CronJob]:
        """Return all registered jobs."""
        return list(self._jobs.values())

    def get_next_run(self, job_id: str) -> Optional[datetime]:
        """Return the next fire time for *job_id*."""
        return self._get_next_run(job_id)

    def get_next_runs(self) -> dict[str, Optional[datetime]]:
        """Return ``{job_id: next_run_time}`` for all jobs."""
        return {jid: self._get_next_run(jid) for jid in self._jobs}

    # ── Internals ───────────────────────────────────────────────────────────

    def _get_next_run(self, job_id: str) -> Optional[datetime]:
        aps_job = self._scheduler.get_job(job_id)
        if aps_job and aps_job.next_run_time:
            return aps_job.next_run_time
        return None

    async def _fire_job(self, job: CronJob) -> None:
        """Wrapper called by APScheduler; delegates to the user callback."""
        logger.info("Firing cron job %s (%s)", job.id, job.name)
        job.last_run = datetime.now(timezone.utc)
        try:
            await self._callback(job)
        except Exception:
            logger.exception("Error running cron job %s", job.id)
