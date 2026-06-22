"""Tests for CronService and CronJob models.

Note: CronService tests mock the CronScheduler to avoid APScheduler
version-specific issues. Model tests are pure and don't need mocking.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venux_code.cron.models import (
    CronJob,
    CronSchedule,
    DeliveryConfig,
    DeliveryMethod,
    RepeatPolicy,
    ScheduleType,
)
from venux_code.cron.runner import JobRunResult


# ── Model tests ─────────────────────────────────────────────────────────────


class TestCronSchedule:
    def test_cron_type(self):
        s = CronSchedule(type=ScheduleType.CRON, expression="0 9 * * 1-5")
        assert s.type == ScheduleType.CRON
        assert s.expression == "0 9 * * 1-5"

    def test_interval_type(self):
        s = CronSchedule(type=ScheduleType.INTERVAL, minutes=30)
        assert s.type == ScheduleType.INTERVAL
        assert s.minutes == 30

    def test_date_type(self):
        run_at = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
        s = CronSchedule(type=ScheduleType.DATE, run_at=run_at)
        assert s.type == ScheduleType.DATE
        assert s.run_at == run_at

    def test_defaults(self):
        s = CronSchedule(type=ScheduleType.INTERVAL)
        assert s.seconds == 0
        assert s.minutes == 0
        assert s.hours == 0
        assert s.timezone == "UTC"


class TestDeliveryConfig:
    def test_defaults(self):
        d = DeliveryConfig()
        assert d.method == DeliveryMethod.NONE
        assert d.target is None
        assert d.include_output is True

    def test_webhook(self):
        d = DeliveryConfig(method=DeliveryMethod.WEBHOOK, target="https://hook.example.com")
        assert d.method == DeliveryMethod.WEBHOOK
        assert d.target == "https://hook.example.com"


class TestCronJob:
    def test_create(self):
        job = CronJob(
            name="test-job",
            schedule=CronSchedule(type=ScheduleType.INTERVAL, minutes=5),
            prompt="Do something",
        )
        assert job.id is not None
        assert job.name == "test-job"
        assert job.enabled is True
        assert job.no_agent is False

    def test_to_storage_dict(self):
        job = CronJob(
            name="storage-test",
            schedule=CronSchedule(type=ScheduleType.CRON, expression="*/10 * * * *"),
            prompt="Check status",
        )
        d = job.to_storage_dict()
        assert d["name"] == "storage-test"
        assert d["schedule"]["type"] == "cron"
        assert d["prompt"] == "Check status"

    def test_from_storage_dict(self):
        data = {
            "name": "restored",
            "schedule": {"type": "interval", "minutes": 15},
            "prompt": "Run check",
            "enabled": True,
        }
        job = CronJob.from_storage_dict(data)
        assert job.name == "restored"
        assert job.schedule.type == ScheduleType.INTERVAL
        assert job.schedule.minutes == 15

    def test_roundtrip(self):
        original = CronJob(
            name="roundtrip",
            schedule=CronSchedule(type=ScheduleType.CRON, expression="0 0 * * *"),
            prompt="Daily report",
            skills=["reporting"],
            deliver=DeliveryConfig(method=DeliveryMethod.CHAT),
            repeat=RepeatPolicy.RESCHEDULE,
        )
        d = original.to_storage_dict()
        restored = CronJob.from_storage_dict(d)
        assert restored.name == original.name
        assert restored.schedule.expression == original.schedule.expression
        assert restored.skills == original.skills
        assert restored.deliver.method == DeliveryMethod.CHAT

    def test_script_job(self):
        job = CronJob(
            name="script-job",
            schedule=CronSchedule(type=ScheduleType.INTERVAL, hours=1),
            prompt="",
            script="echo hello",
            no_agent=True,
        )
        assert job.no_agent is True
        assert job.script == "echo hello"


# ── JobRunner tests ─────────────────────────────────────────────────────────


class TestJobRunner:
    async def test_run_agent_mode(self):
        from venux_code.cron.runner import JobRunner

        async def mock_factory(prompt: str, skills: list, session_id: str) -> str:
            return f"Result: {prompt}"

        runner = JobRunner(agent_factory=mock_factory)
        job = CronJob(
            name="agent-job",
            schedule=CronSchedule(type=ScheduleType.INTERVAL, minutes=60),
            prompt="Check status",
        )
        result = await runner.run(job)
        assert result.success is True
        assert "Check status" in result.output

    async def test_run_script_mode(self, tmp_path: Path):
        from venux_code.cron.runner import JobRunner

        script = tmp_path / "test.sh"
        script.write_text("#!/bin/bash\necho 'script output'\n")
        script.chmod(0o755)

        runner = JobRunner()
        job = CronJob(
            name="script-job",
            schedule=CronSchedule(type=ScheduleType.INTERVAL, minutes=60),
            prompt="",
            script=str(script),
            no_agent=True,
        )
        result = await runner.run(job)
        assert result.success is True
        assert "script output" in result.output

    async def test_run_script_failure(self):
        from venux_code.cron.runner import JobRunner

        runner = JobRunner()
        job = CronJob(
            name="fail-job",
            schedule=CronSchedule(type=ScheduleType.INTERVAL, minutes=60),
            prompt="",
            script="exit 1",
            no_agent=True,
        )
        result = await runner.run(job)
        assert result.success is False
        assert result.error is not None

    async def test_run_no_agent_no_script(self):
        from venux_code.cron.runner import JobRunner

        runner = JobRunner()
        job = CronJob(
            name="empty-job",
            schedule=CronSchedule(type=ScheduleType.INTERVAL, minutes=60),
            prompt="",
            no_agent=True,
            script=None,
        )
        result = await runner.run(job)
        assert result.success is False

    async def test_run_no_factory(self):
        from venux_code.cron.runner import JobRunner

        runner = JobRunner(agent_factory=None)
        job = CronJob(
            name="no-factory",
            schedule=CronSchedule(type=ScheduleType.INTERVAL, minutes=60),
            prompt="Hello",
        )
        result = await runner.run(job)
        assert result.success is False


# ── CronService tests with mocked scheduler ─────────────────────────────────


@pytest.fixture
def cron_storage(tmp_path: Path) -> Path:
    return tmp_path / "cron_jobs.json"


@pytest.fixture
def cron_service(cron_storage: Path):
    """Create a CronService with mocked scheduler and runner."""
    from venux_code.cron.service import CronService

    async def mock_agent_factory(prompt: str, skills: list, session_id: str) -> str:
        return f"Executed: {prompt}"

    service = CronService(storage_path=cron_storage, agent_factory=mock_agent_factory)

    # Mock the scheduler to avoid APScheduler issues
    mock_scheduler = MagicMock()
    mock_scheduler.add_job = MagicMock()
    mock_scheduler.remove_job = MagicMock()
    mock_scheduler.pause_job = MagicMock(return_value=True)
    mock_scheduler.resume_job = MagicMock(return_value=True)
    mock_scheduler.get_next_runs = MagicMock(return_value={})
    mock_scheduler.start = AsyncMock()
    mock_scheduler.shutdown = AsyncMock()
    service._scheduler = mock_scheduler

    return service


class TestCronServiceCRUD:
    async def test_add_job(self, cron_service):
        job = CronJob(
            name="new-job",
            schedule=CronSchedule(type=ScheduleType.INTERVAL, minutes=10),
            prompt="Check something",
        )
        result = await cron_service.add(job)
        assert result.id == job.id
        assert cron_service.get_job(job.id) is not None
        cron_service._scheduler.add_job.assert_called_once()

    async def test_remove_job(self, cron_service):
        job = CronJob(
            name="removable",
            schedule=CronSchedule(type=ScheduleType.INTERVAL, minutes=5),
            prompt="Remove me",
        )
        await cron_service.add(job)
        result = await cron_service.remove(job.id)
        assert result is True
        assert cron_service.get_job(job.id) is None

    async def test_remove_nonexistent(self, cron_service):
        result = await cron_service.remove("nonexistent")
        assert result is False

    async def test_list_jobs(self, cron_service):
        for i in range(3):
            job = CronJob(
                name=f"job-{i}",
                schedule=CronSchedule(type=ScheduleType.INTERVAL, minutes=5),
                prompt=f"Job {i}",
                enabled=i != 2,
            )
            await cron_service.add(job)

        all_jobs = cron_service.list_jobs()
        assert len(all_jobs) == 3

        enabled_jobs = cron_service.list_jobs(enabled_only=True)
        assert len(enabled_jobs) == 2

    async def test_update_job(self, cron_service):
        job = CronJob(
            name="updatable",
            schedule=CronSchedule(type=ScheduleType.INTERVAL, minutes=5),
            prompt="Original",
        )
        await cron_service.add(job)

        job.prompt = "Updated"
        result = await cron_service.update(job)
        assert result is True
        assert cron_service.get_job(job.id).prompt == "Updated"

    async def test_update_nonexistent(self, cron_service):
        job = CronJob(
            name="ghost",
            schedule=CronSchedule(type=ScheduleType.INTERVAL, minutes=5),
            prompt="Ghost",
        )
        result = await cron_service.update(job)
        assert result is False

    async def test_get_job(self, cron_service):
        job = CronJob(
            name="findable",
            schedule=CronSchedule(type=ScheduleType.INTERVAL, minutes=5),
            prompt="Find me",
        )
        await cron_service.add(job)
        found = cron_service.get_job(job.id)
        assert found is not None
        assert found.name == "findable"

    async def test_get_job_nonexistent(self, cron_service):
        found = cron_service.get_job("nonexistent")
        assert found is None


class TestCronServicePersistence:
    async def test_save_and_load(self, cron_service, cron_storage: Path):
        job = CronJob(
            name="persistent",
            schedule=CronSchedule(type=ScheduleType.CRON, expression="0 9 * * *"),
            prompt="Daily standup",
        )
        await cron_service.add(job)

        assert cron_storage.exists()
        data = json.loads(cron_storage.read_text())
        assert len(data) == 1
        assert data[0]["name"] == "persistent"

    async def test_run_now(self, cron_service):
        job = CronJob(
            name="run-now",
            schedule=CronSchedule(type=ScheduleType.INTERVAL, minutes=60),
            prompt="Test run",
        )
        await cron_service.add(job)

        result = await cron_service.run_now(job.id)
        assert result is not None
        assert result.success is True
        assert "Test run" in result.output

    async def test_run_now_nonexistent(self, cron_service):
        result = await cron_service.run_now("nonexistent")
        assert result is None
