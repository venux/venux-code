"""CronService – high-level API for managing scheduled jobs.

Provides add / remove / pause / resume / run_now / list / get_next_runs.
Persists jobs to a JSON file and delegates scheduling to ``CronScheduler``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

from venux_code.config.settings import get_settings

from .models import CronJob, CronSchedule
from .runner import JobRunner, JobRunResult
from .scheduler import CronScheduler

logger = logging.getLogger(__name__)

# Type alias
JobCallback = Callable[[CronJob], Coroutine[Any, Any, None]]


class CronService:
    """High-level service for managing Venux Code cron jobs.

    Parameters
    ----------
    storage_path:
        Path to the JSON file used for persistence.  Defaults to
        ``<data_dir>/cron_jobs.json``.
    agent_factory:
        Async callable passed to ``JobRunner`` for agent-mode execution.
    """

    def __init__(
        self,
        *,
        storage_path: Path | None = None,
        agent_factory: Any | None = None,
    ) -> None:
        settings = get_settings()
        self._storage_path = storage_path or (settings.data_dir / "cron_jobs.json")
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

        self._runner = JobRunner(agent_factory=agent_factory)
        self._scheduler = CronScheduler(callback=self._on_trigger)
        self._jobs: dict[str, CronJob] = {}
        self._started = False

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Load persisted jobs and start the scheduler."""
        self._load_jobs()
        for job in self._jobs.values():
            self._scheduler.add_job(job)
        await self._scheduler.start()
        self._started = True
        logger.info("CronService started with %d jobs", len(self._jobs))

    async def shutdown(self) -> None:
        """Stop the scheduler and persist jobs."""
        await self._scheduler.shutdown()
        self._save_jobs()
        self._started = False
        logger.info("CronService shut down")

    # ── CRUD ────────────────────────────────────────────────────────────────

    async def add(self, job: CronJob) -> CronJob:
        """Add a new job and persist.

        Returns the job (with generated ``id``).
        """
        self._jobs[job.id] = job
        self._scheduler.add_job(job)
        self._save_jobs()
        logger.info("Added job %s (%s)", job.id, job.name)
        return job

    async def remove(self, job_id: str) -> bool:
        """Remove a job by id.  Returns ``True`` if it existed."""
        self._scheduler.remove_job(job_id)
        existed = job_id in self._jobs
        self._jobs.pop(job_id, None)
        if existed:
            self._save_jobs()
            logger.info("Removed job %s", job_id)
        return existed

    async def pause(self, job_id: str) -> bool:
        """Pause a job.  Returns ``True`` if found."""
        ok = self._scheduler.pause_job(job_id)
        if ok and job_id in self._jobs:
            self._jobs[job_id].enabled = False
            self._save_jobs()
        return ok

    async def resume(self, job_id: str) -> bool:
        """Resume a paused job.  Returns ``True`` if found."""
        ok = self._scheduler.resume_job(job_id)
        if ok and job_id in self._jobs:
            self._jobs[job_id].enabled = True
            self._save_jobs()
        return ok

    async def run_now(self, job_id: str) -> Optional[JobRunResult]:
        """Trigger immediate execution of a job.

        Returns ``None`` if the job was not found.
        """
        job = self._jobs.get(job_id)
        if job is None:
            logger.warning("run_now: job %s not found", job_id)
            return None
        logger.info("Running job %s immediately", job_id)
        result = await self._runner.run(job)
        job.last_run = datetime.now(timezone.utc)
        self._save_jobs()
        return result

    async def update(self, job: CronJob) -> bool:
        """Update an existing job.  Returns ``True`` if found."""
        if job.id not in self._jobs:
            return False
        self._jobs[job.id] = job
        self._scheduler.remove_job(job.id)
        self._scheduler.add_job(job)
        self._save_jobs()
        return True

    # ── Queries ─────────────────────────────────────────────────────────────

    def list_jobs(self, *, enabled_only: bool = False) -> list[CronJob]:
        """Return all jobs, optionally filtered to enabled ones."""
        jobs = list(self._jobs.values())
        if enabled_only:
            jobs = [j for j in jobs if j.enabled]
        return jobs

    def get_job(self, job_id: str) -> Optional[CronJob]:
        """Return a single job by id."""
        return self._jobs.get(job_id)

    def get_next_runs(self) -> dict[str, Optional[datetime]]:
        """Return ``{job_id: next_run_time}`` for all scheduled jobs."""
        return self._scheduler.get_next_runs()

    # ── Trigger callback ────────────────────────────────────────────────────

    async def _on_trigger(self, job: CronJob) -> None:
        """Called by the scheduler when a job fires."""
        result = await self._runner.run(job)
        job.last_run = datetime.now(timezone.utc)

        if not result.success:
            logger.error("Job %s failed: %s", job.id, result.error)

        self._save_jobs()

    # ── Persistence ─────────────────────────────────────────────────────────

    def _save_jobs(self) -> None:
        """Persist all jobs to the JSON storage file."""
        data = [job.to_storage_dict() for job in self._jobs.values()]
        try:
            self._storage_path.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("Failed to save cron jobs to %s", self._storage_path)

    def _load_jobs(self) -> None:
        """Load jobs from the JSON storage file."""
        if not self._storage_path.is_file():
            return
        try:
            data = json.loads(self._storage_path.read_text(encoding="utf-8"))
            for item in data:
                job = CronJob.from_storage_dict(item)
                self._jobs[job.id] = job
            logger.info("Loaded %d cron jobs from %s", len(self._jobs), self._storage_path)
        except Exception:
            logger.exception("Failed to load cron jobs from %s", self._storage_path)
