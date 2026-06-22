"""Job runner – creates an agent session and executes a cron job's prompt.

Supports two modes:
  1. **Agent mode** (default): spawns a ``VenuxAgent`` with optional skills
     and runs the prompt to completion.
  2. **Script mode** (``no_agent=True``): executes the shell script directly.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .models import CronJob, DeliveryConfig, DeliveryMethod

logger = logging.getLogger(__name__)


# ── Run result ──────────────────────────────────────────────────────────────


@dataclass
class JobRunResult:
    """Outcome of a single cron job execution."""

    job_id: str
    success: bool
    output: str = ""
    error: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    duration_seconds: float = 0.0


# ── Runner ──────────────────────────────────────────────────────────────────


class JobRunner:
    """Executes cron jobs.

    Parameters
    ----------
    agent_factory:
        Async callable ``(prompt, skills, session_id) -> str`` that creates
        an agent, runs *prompt*, and returns the final text output.
        This decouples the runner from the concrete agent implementation.
    script_timeout:
        Max seconds for script execution.  Defaults to 300.
    """

    def __init__(
        self,
        agent_factory: Any | None = None,
        *,
        script_timeout: int = 300,
    ) -> None:
        self._agent_factory = agent_factory
        self._script_timeout = script_timeout

    # ── Public API ──────────────────────────────────────────────────────────

    async def run(self, job: CronJob) -> JobRunResult:
        """Execute a single ``CronJob`` and return the result.

        Dispatches to either the agent or script runner depending on
        ``job.no_agent``.
        """
        started = datetime.now(timezone.utc)
        logger.info("Running job %s (%s)", job.id, job.name)

        try:
            if job.no_agent:
                output = await self._run_script(job)
            else:
                output = await self._run_agent(job)

            finished = datetime.now(timezone.utc)
            result = JobRunResult(
                job_id=job.id,
                success=True,
                output=output,
                started_at=started,
                finished_at=finished,
                duration_seconds=(finished - started).total_seconds(),
            )
        except Exception as exc:
            finished = datetime.now(timezone.utc)
            result = JobRunResult(
                job_id=job.id,
                success=False,
                error=str(exc),
                started_at=started,
                finished_at=finished,
                duration_seconds=(finished - started).total_seconds(),
            )
            logger.exception("Job %s failed", job.id)

        # Deliver result
        await self._deliver(job.deliver, result)
        return result

    # ── Agent mode ──────────────────────────────────────────────────────────

    async def _run_agent(self, job: CronJob) -> str:
        """Spawn an agent session and run the prompt to completion."""
        if self._agent_factory is None:
            raise RuntimeError(
                "No agent_factory configured – cannot run in agent mode"
            )

        session_id = f"cron-{job.id}-{int(datetime.now(timezone.utc).timestamp())}"

        # The factory returns the full text response
        result: str = await self._agent_factory(
            prompt=job.prompt,
            skills=job.skills,
            session_id=session_id,
        )
        return result

    # ── Script mode ─────────────────────────────────────────────────────────

    async def _run_script(self, job: CronJob) -> str:
        """Run the job's shell script in a subprocess."""
        if not job.script:
            raise ValueError(f"Job {job.id} has no_agent=True but no script")

        logger.debug("Executing script for job %s", job.id)

        proc = await asyncio.create_subprocess_shell(
            job.script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self._script_timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(f"Script timed out after {self._script_timeout}s")

        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            raise RuntimeError(
                f"Script exited with code {proc.returncode}: {stderr}"
            )

        return stdout

    # ── Delivery ────────────────────────────────────────────────────────────

    async def _deliver(self, config: DeliveryConfig, result: JobRunResult) -> None:
        """Deliver the job result according to the delivery config."""
        if config.method == DeliveryMethod.NONE:
            return

        payload = self._format_delivery(result)

        if config.method == DeliveryMethod.CHAT:
            logger.info("Delivering result to chat for job %s", result.job_id)
            # Chat delivery is handled by the service layer which pushes
            # into the Feishu/Lark message stream.
            return

        if config.method == DeliveryMethod.WEBHOOK:
            await self._deliver_webhook(config.target, payload)
            return

        if config.method == DeliveryMethod.EMAIL:
            logger.info("Email delivery not yet implemented for job %s", result.job_id)
            return

    @staticmethod
    def _format_delivery(result: JobRunResult) -> str:
        """Format a result for delivery."""
        status = "✅ 成功" if result.success else "❌ 失败"
        lines = [
            f"**定时任务结果** – Job `{result.job_id[:8]}`",
            f"状态: {status}",
            f"耗时: {result.duration_seconds:.1f}s",
        ]
        if result.output:
            lines.append(f"\n```\n{result.output[:2000]}\n```")
        if result.error:
            lines.append(f"\n错误: {result.error[:1000]}")
        return "\n".join(lines)

    @staticmethod
    async def _deliver_webhook(url: str | None, payload: str) -> None:
        """POST the result to a webhook URL."""
        if not url:
            logger.warning("Webhook delivery requested but no URL configured")
            return

        try:
            import httpx

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url,
                    json={"text": payload},
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                logger.info("Webhook delivery to %s – %s", url, resp.status_code)
        except Exception:
            logger.exception("Webhook delivery to %s failed", url)
