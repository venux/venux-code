"""Tests for DeepAgent phases and FilesystemMiddleware."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from venux_code.llm.agent.deep_agent import (
    DeepAgent,
    DeepAgentEvent,
    DeepAgentPhase,
    ExecutionPhase,
    ExecutionPlan,
    FilesystemMiddleware,
    PlanStep,
    PlanStepStatus,
    PlanningPhase,
    ReviewPhase,
)
from tests.conftest import MockChatModel


# ── PlanStep / ExecutionPlan models ───────────────────────────────────────


class TestPlanModels:
    def test_plan_step_defaults(self):
        step = PlanStep(id=1, description="Do something")
        assert step.status == PlanStepStatus.PENDING
        assert step.tools_hint == []
        assert step.depends_on == []
        assert step.result == ""
        assert step.error is None
        assert step.retries == 0

    def test_plan_step_status_values(self):
        assert PlanStepStatus.PENDING == "pending"
        assert PlanStepStatus.RUNNING == "running"
        assert PlanStepStatus.SUCCESS == "success"
        assert PlanStepStatus.FAILED == "failed"
        assert PlanStepStatus.SKIPPED == "skipped"

    def test_execution_plan_defaults(self):
        plan = ExecutionPlan(goal="test goal")
        assert plan.goal == "test goal"
        assert plan.steps == []
        assert plan.reasoning == ""
        assert plan.estimated_complexity == "medium"

    def test_execution_plan_with_steps(self):
        plan = ExecutionPlan(
            goal="build API",
            steps=[
                PlanStep(id=1, description="Create models"),
                PlanStep(id=2, description="Create routes", depends_on=[1]),
            ],
            reasoning="Bottom-up approach",
            estimated_complexity="high",
        )
        assert len(plan.steps) == 2
        assert plan.steps[1].depends_on == [1]


# ── DeepAgentEvent ────────────────────────────────────────────────────────


class TestDeepAgentEvent:
    def test_creation(self):
        event = DeepAgentEvent(
            DeepAgentPhase.PLANNING, "start", {"goal": "test"}
        )
        assert event.phase == DeepAgentPhase.PLANNING
        assert event.event_type == "start"
        assert event.data == {"goal": "test"}
        assert event.timestamp is not None

    def test_repr(self):
        event = DeepAgentEvent(DeepAgentPhase.EXECUTION, "step_done")
        assert "execution" in repr(event)
        assert "step_done" in repr(event)

    def test_default_data(self):
        event = DeepAgentEvent(DeepAgentPhase.DONE, "success")
        assert event.data == {}


# ── FilesystemMiddleware ──────────────────────────────────────────────────


class TestFilesystemMiddleware:
    def test_creates_directory(self, tmp_path: Path):
        middleware = FilesystemMiddleware(base_dir=tmp_path, session_id="test-123")
        assert middleware.working_dir.exists()
        assert middleware.working_dir == tmp_path / "test-123"

    def test_save_and_load_plan(self, tmp_path: Path):
        middleware = FilesystemMiddleware(base_dir=tmp_path, session_id="s1")
        plan = ExecutionPlan(
            goal="test",
            steps=[PlanStep(id=1, description="step one")],
            reasoning="because",
        )
        middleware.save_plan(plan)

        loaded = middleware.load_plan()
        assert loaded is not None
        assert loaded.goal == "test"
        assert len(loaded.steps) == 1
        assert loaded.steps[0].description == "step one"

    def test_load_plan_none_when_missing(self, tmp_path: Path):
        middleware = FilesystemMiddleware(base_dir=tmp_path, session_id="empty")
        assert middleware.load_plan() is None

    def test_save_step_result(self, tmp_path: Path):
        middleware = FilesystemMiddleware(base_dir=tmp_path, session_id="s2")
        step = PlanStep(id=1, description="test", status=PlanStepStatus.SUCCESS, result="done")
        middleware.save_step_result(step)

        step_file = middleware.working_dir / "step_1.json"
        assert step_file.exists()
        data = json.loads(step_file.read_text())
        assert data["status"] == "success"
        assert data["result"] == "done"

    def test_save_review(self, tmp_path: Path):
        middleware = FilesystemMiddleware(base_dir=tmp_path, session_id="s3")
        review = {"goal_achieved": True, "confidence": 0.9, "summary": "All good"}
        middleware.save_review(review)

        review_file = middleware.working_dir / "review.json"
        assert review_file.exists()
        data = json.loads(review_file.read_text())
        assert data["goal_achieved"] is True


# ── PlanningPhase ─────────────────────────────────────────────────────────


class TestPlanningPhase:
    @pytest.mark.asyncio
    async def test_valid_json_plan(self):
        plan_json = json.dumps({
            "reasoning": "Step by step approach",
            "estimated_complexity": "medium",
            "steps": [
                {"id": 1, "description": "Analyze code", "tools_hint": ["view"], "depends_on": []},
                {"id": 2, "description": "Make changes", "tools_hint": ["edit"], "depends_on": [1]},
            ],
        })

        mock_response = AIMessage(content=plan_json)
        model = MockChatModel(responses=[mock_response])

        phase = PlanningPhase(model)
        plan = await phase.execute("Refactor the auth module")

        assert plan.goal == "Refactor the auth module"
        assert len(plan.steps) == 2
        assert plan.steps[0].description == "Analyze code"
        assert plan.reasoning == "Step by step approach"

    @pytest.mark.asyncio
    async def test_json_in_markdown_block(self):
        plan_json = json.dumps({
            "reasoning": "test",
            "estimated_complexity": "low",
            "steps": [{"id": 1, "description": "Do it", "tools_hint": [], "depends_on": []}],
        })
        content = f"Here is the plan:\n```json\n{plan_json}\n```"
        mock_response = AIMessage(content=content)
        model = MockChatModel(responses=[mock_response])

        phase = PlanningPhase(model)
        plan = await phase.execute("test goal")
        assert len(plan.steps) == 1

    @pytest.mark.asyncio
    async def test_invalid_json_fallback(self):
        mock_response = AIMessage(content="I'm not sure how to plan this.")
        model = MockChatModel(responses=[mock_response])

        phase = PlanningPhase(model)
        plan = await phase.execute("unclear goal")

        assert plan.goal == "unclear goal"
        assert len(plan.steps) == 1
        assert "Fallback" in plan.reasoning

    def test_extract_json_direct(self):
        result = PlanningPhase._extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_extract_json_in_markdown(self):
        text = 'Some text\n```json\n{"key": "value"}\n```\nMore text'
        result = PlanningPhase._extract_json(text)
        assert result == {"key": "value"}

    def test_extract_json_none(self):
        result = PlanningPhase._extract_json("no json here")
        assert result is None


# ── ExecutionPhase ────────────────────────────────────────────────────────


class TestExecutionPhase:
    @pytest.mark.asyncio
    async def test_execute_single_step(self):
        model = MockChatModel(final_content="Step completed successfully.")
        phase = ExecutionPhase(model, tools=[], max_iterations_per_step=5)

        plan = ExecutionPlan(
            goal="test",
            steps=[PlanStep(id=1, description="Do something")],
        )
        result = await phase.execute(plan)

        assert result.steps[0].status == PlanStepStatus.SUCCESS
        assert "completed" in result.steps[0].result.lower()

    @pytest.mark.asyncio
    async def test_execute_skips_unmet_deps(self):
        model = MockChatModel(final_content="done")
        phase = ExecutionPhase(model, tools=[], max_iterations_per_step=3)

        plan = ExecutionPlan(
            goal="test",
            steps=[
                PlanStep(id=1, description="first", status=PlanStepStatus.FAILED),
                PlanStep(id=2, description="second", depends_on=[1]),
            ],
        )
        result = await phase.execute(plan)
        assert result.steps[1].status == PlanStepStatus.SKIPPED
        assert result.steps[1].error is not None and "Dependencies" in result.steps[1].error

    @pytest.mark.asyncio
    async def test_callbacks_called(self):
        model = MockChatModel(final_content="done")
        phase = ExecutionPhase(model, tools=[], max_iterations_per_step=3)

        start_called = []
        done_called = []

        async def on_start(step):
            start_called.append(step.id)

        async def on_done(step):
            done_called.append(step.id)

        plan = ExecutionPlan(
            goal="test",
            steps=[PlanStep(id=1, description="step")],
        )
        await phase.execute(plan, on_step_start=on_start, on_step_done=on_done)

        assert 1 in start_called
        assert 1 in done_called

    def test_build_previous_context_empty(self):
        plan = ExecutionPlan(goal="test", steps=[])
        result = ExecutionPhase._build_previous_context(plan, 1)
        assert "no previous steps" in result.lower()

    def test_build_previous_context_with_results(self):
        plan = ExecutionPlan(
            goal="test",
            steps=[
                PlanStep(id=1, description="step 1", status=PlanStepStatus.SUCCESS, result="done"),
                PlanStep(id=2, description="step 2", status=PlanStepStatus.FAILED, error="oops"),
            ],
        )
        result = ExecutionPhase._build_previous_context(plan, 3)
        assert "step 1" in result
        assert "done" in result
        assert "step 2" in result
        assert "oops" in result


# ── ReviewPhase ───────────────────────────────────────────────────────────


class TestReviewPhase:
    @pytest.mark.asyncio
    async def test_review_goal_achieved(self):
        review_json = json.dumps({
            "goal_achieved": True,
            "confidence": 0.95,
            "issues": [],
            "retry_steps": [],
            "summary": "All steps completed successfully.",
        })
        model = MockChatModel(responses=[AIMessage(content=review_json)])
        phase = ReviewPhase(model, max_retries=2)

        plan = ExecutionPlan(
            goal="test",
            steps=[PlanStep(id=1, description="step", status=PlanStepStatus.SUCCESS, result="done")],
        )
        review = await phase.execute(plan)

        assert review["goal_achieved"] is True
        assert review["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_review_with_retry(self):
        review_json = json.dumps({
            "goal_achieved": False,
            "confidence": 0.3,
            "issues": ["Step 1 failed"],
            "retry_steps": [1],
            "summary": "Needs retry.",
        })
        model = MockChatModel(responses=[AIMessage(content=review_json)])
        phase = ReviewPhase(model, max_retries=2)

        plan = ExecutionPlan(
            goal="test",
            steps=[PlanStep(id=1, description="step", status=PlanStepStatus.FAILED, error="err")],
        )
        review = await phase.execute(plan)

        assert review["goal_achieved"] is False
        assert 1 in review["retry_steps"]
        assert plan.steps[0].retries == 1

    @pytest.mark.asyncio
    async def test_review_invalid_json_fallback(self):
        model = MockChatModel(responses=[AIMessage(content="not json")])
        phase = ReviewPhase(model, max_retries=2)

        plan = ExecutionPlan(
            goal="test",
            steps=[PlanStep(id=1, description="step", status=PlanStepStatus.FAILED, error="err")],
        )
        review = await phase.execute(plan)

        assert review["goal_achieved"] is False
        assert len(review["issues"]) > 0

    @pytest.mark.asyncio
    async def test_review_retry_limit_enforced(self):
        review_json = json.dumps({
            "goal_achieved": False,
            "retry_steps": [1],
            "summary": "retry",
        })
        model = MockChatModel(responses=[AIMessage(content=review_json)])
        phase = ReviewPhase(model, max_retries=1)

        plan = ExecutionPlan(
            goal="test",
            steps=[PlanStep(id=1, description="step", status=PlanStepStatus.FAILED, retries=1)],
        )
        review = await phase.execute(plan)

        # retries=1 already equals max_retries=1, so should not be in retry_steps
        assert 1 not in review["retry_steps"]

    def test_format_plan(self):
        plan = ExecutionPlan(
            goal="test",
            steps=[
                PlanStep(id=1, description="step 1", status=PlanStepStatus.SUCCESS, result="ok"),
                PlanStep(id=2, description="step 2", status=PlanStepStatus.FAILED, error="fail"),
            ],
        )
        formatted = ReviewPhase._format_plan(plan)
        assert "Step 1 [success]" in formatted
        assert "Step 2 [failed]" in formatted
        assert "ok" in formatted
        assert "fail" in formatted


# ── DeepAgent (integration) ───────────────────────────────────────────────


class TestDeepAgent:
    @pytest.mark.asyncio
    async def test_run_success_flow(self, tmp_path: Path):
        """Test the full planning → execution → review → done flow."""
        plan_json = json.dumps({
            "reasoning": "Simple approach",
            "estimated_complexity": "low",
            "steps": [{"id": 1, "description": "Do the thing", "tools_hint": [], "depends_on": []}],
        })
        review_json = json.dumps({
            "goal_achieved": True,
            "confidence": 0.9,
            "issues": [],
            "retry_steps": [],
            "summary": "Success!",
        })

        model = MockChatModel(
            responses=[
                AIMessage(content=plan_json),      # planning
                AIMessage(content="Done."),         # execution step 1
                AIMessage(content=review_json),     # review
            ]
        )

        agent = DeepAgent(
            model=model,
            tools=[],
            save_intermediate=True,
            session_id="test-run",
        )
        # Override middleware to use tmp_path
        agent._middleware = FilesystemMiddleware(base_dir=tmp_path, session_id="test-run")

        events = []
        async for event in agent.run("Test goal"):
            events.append(event)

        event_types = [(e.phase.value, e.event_type) for e in events]
        assert ("planning", "start") in event_types
        assert ("planning", "plan_created") in event_types
        assert ("execution", "execution_start") in event_types
        assert ("execution", "step_done") in event_types
        assert ("execution", "execution_done") in event_types
        assert ("review", "review_start") in event_types
        assert ("review", "review_done") in event_types
        assert ("done", "success") in event_types

    @pytest.mark.asyncio
    async def test_run_planning_failure(self):
        """If planning raises, agent emits error and done/failed."""
        model = MagicMock()
        model.ainvoke = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

        agent = DeepAgent(model=model, tools=[], save_intermediate=False)

        events = []
        async for event in agent.run("test"):
            events.append(event)

        event_types = [(e.phase.value, e.event_type) for e in events]
        assert ("planning", "error") in event_types
        assert ("done", "failed") in event_types

    @pytest.mark.asyncio
    async def test_run_partial_success(self, tmp_path: Path):
        """When review says not achieved and no retries left."""
        plan_json = json.dumps({
            "reasoning": "try",
            "estimated_complexity": "low",
            "steps": [{"id": 1, "description": "step", "tools_hint": [], "depends_on": []}],
        })
        review_json = json.dumps({
            "goal_achieved": False,
            "confidence": 0.2,
            "issues": ["Not good enough"],
            "retry_steps": [],
            "summary": "Partial.",
        })

        model = MockChatModel(
            responses=[
                AIMessage(content=plan_json),
                AIMessage(content="attempted"),
                AIMessage(content=review_json),
            ]
        )

        agent = DeepAgent(
            model=model, tools=[], max_retries=0, save_intermediate=False
        )

        events = []
        async for event in agent.run("test"):
            events.append(event)

        event_types = [(e.phase.value, e.event_type) for e in events]
        assert ("done", "partial_success") in event_types
