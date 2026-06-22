"""Deep Agent implementation – multi-phase goal-solving agent.

The Deep Agent breaks complex goals into three phases:

1. **PlanningPhase**: Analyse the goal and produce a structured plan.
2. **ExecutionPhase**: Execute each plan step using available tools.
3. **ReviewPhase**: Validate results, detect failures, and optionally retry.

Each phase is implemented as a LangGraph subgraph, and they are composed
into a top-level graph that manages the full lifecycle.

Usage
-----
```python
agent = DeepAgent(model=model, tools=tools, system_prompt="...")
async for event in agent.run("Refactor the auth module"):
    handle(event)
```
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Optional, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ── Data models ─────────────────────────────────────────────────────────────


class PlanStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanStep(BaseModel):
    """A single step in the execution plan."""

    id: int
    description: str
    tools_hint: list[str] = []
    depends_on: list[int] = []
    status: PlanStepStatus = PlanStepStatus.PENDING
    result: str = ""
    error: str | None = None
    retries: int = 0


class ExecutionPlan(BaseModel):
    """The full plan produced by the PlanningPhase."""

    goal: str
    steps: list[PlanStep] = []
    reasoning: str = ""
    estimated_complexity: str = "medium"  # low, medium, high


class DeepAgentPhase(str, Enum):
    """Phases of the Deep Agent."""

    PLANNING = "planning"
    EXECUTION = "execution"
    REVIEW = "review"
    DONE = "done"


class DeepAgentEvent:
    """Event emitted by the Deep Agent."""

    def __init__(
        self,
        phase: DeepAgentPhase,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        self.phase = phase
        self.event_type = event_type
        self.data = data or {}
        self.timestamp = datetime.now(timezone.utc)

    def __repr__(self) -> str:
        return f"<DeepAgentEvent {self.phase.value}/{self.event_type}>"


# ── Filesystem middleware ───────────────────────────────────────────────────


class FilesystemMiddleware:
    """Saves intermediate results to disk for debugging and resumption.

    Creates a working directory under ``<project>/.venux/deep/<session_id>/``
    and writes plan, step results, and review notes.
    """

    def __init__(self, base_dir: Path | None = None, session_id: str = "") -> None:
        self._base = (base_dir or Path.cwd() / ".venux" / "deep") / session_id
        self._base.mkdir(parents=True, exist_ok=True)

    def save_plan(self, plan: ExecutionPlan) -> None:
        """Persist the execution plan to disk."""
        path = self._base / "plan.json"
        path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        logger.debug("Saved plan to %s", path)

    def save_step_result(self, step: PlanStep) -> None:
        """Persist a step result."""
        path = self._base / f"step_{step.id}.json"
        path.write_text(step.model_dump_json(indent=2), encoding="utf-8")

    def save_review(self, review: dict[str, Any]) -> None:
        """Persist the review phase output."""
        path = self._base / "review.json"
        path.write_text(json.dumps(review, indent=2, default=str), encoding="utf-8")

    def load_plan(self) -> ExecutionPlan | None:
        """Load a previously saved plan (for resumption)."""
        path = self._base / "plan.json"
        if path.is_file():
            return ExecutionPlan.model_validate_json(path.read_text(encoding="utf-8"))
        return None

    @property
    def working_dir(self) -> Path:
        return self._base


# ── Planning phase ──────────────────────────────────────────────────────────


class PlanningPhase:
    """Analyse the goal and produce a structured execution plan.

    Sends the goal to the LLM with instructions to produce a JSON plan,
    then parses the response into an ``ExecutionPlan``.
    """

    PLAN_SYSTEM_PROMPT = """\
You are a planning assistant. Given a goal, produce a structured execution plan.

Output **only** valid JSON with this structure:
{
  "reasoning": "Brief explanation of your approach",
  "estimated_complexity": "low|medium|high",
  "steps": [
    {
      "id": 1,
      "description": "What this step does",
      "tools_hint": ["tool1", "tool2"],
      "depends_on": []
    }
  ]
}

Guidelines:
- Break the goal into 3-10 concrete, actionable steps
- Each step should be independently verifiable
- Use tools_hint to suggest which tools are best for each step
- Use depends_on for ordering constraints
- Keep steps atomic – one clear action per step"""

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    async def execute(self, goal: str) -> ExecutionPlan:
        """Produce an execution plan for *goal*."""
        messages = [
            SystemMessage(content=self.PLAN_SYSTEM_PROMPT),
            HumanMessage(content=f"## Goal\n\n{goal}"),
        ]

        response: AIMessage = await self._model.ainvoke(messages)
        content = response.content if isinstance(response.content, str) else str(response.content)

        # Parse JSON from response
        plan_dict = self._extract_json(content)
        if plan_dict:
            plan_dict["goal"] = goal
            try:
                return ExecutionPlan.model_validate(plan_dict)
            except Exception:
                logger.warning("Failed to parse plan JSON, creating fallback")

        # Fallback: single-step plan
        return ExecutionPlan(
            goal=goal,
            reasoning="Fallback: LLM did not produce valid JSON plan",
            steps=[
                PlanStep(
                    id=1,
                    description=f"Accomplish: {goal}",
                    status=PlanStepStatus.PENDING,
                )
            ],
        )

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        """Try to extract a JSON object from LLM output."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try finding JSON block in markdown
        import re
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding first { ... } block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None


# ── Execution phase ─────────────────────────────────────────────────────────


class ExecutionPhase:
    """Execute each step in the plan using available tools.

    Creates a focused agent session for each step, passing relevant context
    from previous steps.
    """

    EXEC_STEP_PROMPT = """\
You are executing step {step_id} of {total_steps} in a plan.

## Current Step
{description}

## Previous Results
{previous_results}

Execute this step using the available tools. Be focused and efficient.
When done, provide a brief summary of what you accomplished."""

    def __init__(
        self,
        model: BaseChatModel,
        tools: Sequence[Any],
        *,
        max_iterations_per_step: int = 15,
    ) -> None:
        self._model = model
        self._tools = list(tools)
        self._max_iterations = max_iterations_per_step

    async def execute(
        self,
        plan: ExecutionPlan,
        *,
        on_step_start: Any = None,
        on_step_done: Any = None,
    ) -> ExecutionPlan:
        """Execute all steps in the plan sequentially.

        Modifies *plan.steps* in-place, updating status and results.
        """
        from langgraph.prebuilt import ToolNode

        total = len(plan.steps)

        for step in plan.steps:
            # Check dependencies
            deps_met = all(
                plan.steps[d - 1].status == PlanStepStatus.SUCCESS
                for d in step.depends_on
                if 0 < d <= len(plan.steps)
            )
            if not deps_met:
                step.status = PlanStepStatus.SKIPPED
                step.error = "Dependencies not met"
                continue

            step.status = PlanStepStatus.RUNNING
            if on_step_start:
                await on_step_start(step)

            # Build context from previous results
            previous = self._build_previous_context(plan, step.id)

            prompt = self.EXEC_STEP_PROMPT.format(
                step_id=step.id,
                total_steps=total,
                description=step.description,
                previous_results=previous,
            )

            try:
                result = await self._execute_with_tools(prompt)
                step.status = PlanStepStatus.SUCCESS
                step.result = result
            except Exception as exc:
                step.status = PlanStepStatus.FAILED
                step.error = str(exc)
                logger.error("Step %d failed: %s", step.id, exc)

            if on_step_done:
                await on_step_done(step)

        return plan

    async def _execute_with_tools(self, prompt: str) -> str:
        """Run a single step with tools using a mini agent loop."""
        messages: list[BaseMessage] = [
            SystemMessage(content="You are an execution agent. Use tools to accomplish the task."),
            HumanMessage(content=prompt),
        ]

        model_with_tools = self._model.bind_tools(self._tools) if self._tools else self._model
        tool_node = ToolNode(self._tools) if self._tools else None

        for _ in range(self._max_iterations):
            response: AIMessage = await model_with_tools.ainvoke(messages)
            messages.append(response)

            if not response.tool_calls:
                # Done – extract final content
                return response.content if isinstance(response.content, str) else str(response.content)

            if tool_node:
                tool_results = await tool_node.ainvoke({"messages": messages})
                # Append tool results
                if isinstance(tool_results, dict) and "messages" in tool_results:
                    messages.extend(tool_results["messages"])
                else:
                    messages.extend(tool_results if isinstance(tool_results, list) else [])

        # Max iterations reached
        last = messages[-1]
        return last.content if isinstance(last.content, str) else str(last.content)

    @staticmethod
    def _build_previous_context(plan: ExecutionPlan, current_id: int) -> str:
        """Build a summary of results from previous steps."""
        parts: list[str] = []
        for step in plan.steps:
            if step.id >= current_id:
                break
            status_icon = {"success": "✅", "failed": "❌", "skipped": "⏭️"}.get(
                step.status.value, "⏳"
            )
            parts.append(f"Step {step.id} {status_icon}: {step.description}")
            if step.result:
                # Truncate long results
                result = step.result[:500]
                if len(step.result) > 500:
                    result += "..."
                parts.append(f"  Result: {result}")
            if step.error:
                parts.append(f"  Error: {step.error}")
        return "\n".join(parts) if parts else "(no previous steps)"


# ── Review phase ────────────────────────────────────────────────────────────


class ReviewPhase:
    """Validate execution results and decide whether to retry failed steps.

    Sends the plan and results to the LLM for assessment.
    """

    REVIEW_PROMPT = """\
Review the execution results of a plan and determine if the goal was achieved.

## Original Goal
{goal}

## Execution Plan & Results
{plan_summary}

## Instructions
Assess whether:
1. The goal was achieved
2. Any steps need to be retried
3. The results are correct and complete

Respond with JSON:
{{
  "goal_achieved": true/false,
  "confidence": 0.0-1.0,
  "issues": ["list of issues found"],
  "retry_steps": [list of step IDs to retry],
  "summary": "Brief summary of the review"
}}"""

    def __init__(self, model: BaseChatModel, *, max_retries: int = 2) -> None:
        self._model = model
        self._max_retries = max_retries

    async def execute(self, plan: ExecutionPlan) -> dict[str, Any]:
        """Review the plan results and return an assessment."""
        plan_summary = self._format_plan(plan)

        messages = [
            SystemMessage(content="You are a review assistant. Analyze results critically."),
            HumanMessage(content=self.REVIEW_PROMPT.format(
                goal=plan.goal,
                plan_summary=plan_summary,
            )),
        ]

        response: AIMessage = await self._model.ainvoke(messages)
        content = response.content if isinstance(response.content, str) else str(response.content)

        # Parse review
        review = PlanningPhase._extract_json(content)
        if not review:
            # Fallback
            failed = [s for s in plan.steps if s.status == PlanStepStatus.FAILED]
            review = {
                "goal_achieved": len(failed) == 0,
                "confidence": 0.5,
                "issues": [f"Step {s.id} failed: {s.error}" for s in failed],
                "retry_steps": [s.id for s in failed if s.retries < self._max_retries],
                "summary": "Automatic review (LLM response was not parseable)",
            }

        # Enforce retry limit
        retry_ids: list[int] = review.get("retry_steps", [])
        valid_retries: list[int] = []
        for sid in retry_ids:
            if 0 < sid <= len(plan.steps):
                step = plan.steps[sid - 1]
                if step.retries < self._max_retries:
                    valid_retries.append(sid)
                    step.retries += 1
        review["retry_steps"] = valid_retries

        return review

    @staticmethod
    def _format_plan(plan: ExecutionPlan) -> str:
        """Format plan with results for review."""
        lines: list[str] = []
        for step in plan.steps:
            status = step.status.value
            lines.append(f"### Step {step.id} [{status}]")
            lines.append(f"Description: {step.description}")
            if step.result:
                lines.append(f"Result: {step.result[:300]}")
            if step.error:
                lines.append(f"Error: {step.error}")
            lines.append("")
        return "\n".join(lines)


# ── Deep Agent ──────────────────────────────────────────────────────────────


class DeepAgent:
    """Multi-phase goal-solving agent.

    Orchestrates Planning → Execution → Review, with optional retry loops
    and filesystem persistence of intermediate results.

    Parameters
    ----------
    model:
        LangChain ``BaseChatModel`` used for all LLM calls.
    tools:
        Available tools for the execution phase.
    system_prompt:
        Base system prompt (prepended to planning/review prompts).
    max_retries:
        Maximum number of review→retry cycles.  Defaults to 2.
    max_iterations_per_step:
        Tool-loop cap per execution step.
    save_intermediate:
        Whether to save plan/results to disk.
    session_id:
        Identifier for this deep agent run (used for filesystem paths).
    """

    def __init__(
        self,
        *,
        model: BaseChatModel,
        tools: Sequence[Any] | None = None,
        system_prompt: str | None = None,
        max_retries: int = 2,
        max_iterations_per_step: int = 15,
        save_intermediate: bool = True,
        session_id: str = "",
    ) -> None:
        self._model = model
        self._tools = list(tools) if tools else []
        self._system_prompt = system_prompt
        self._max_retries = max_retries
        self._max_iterations_per_step = max_iterations_per_step

        self._planning = PlanningPhase(model)
        self._execution = ExecutionPhase(
            model, self._tools, max_iterations_per_step=max_iterations_per_step
        )
        self._review = ReviewPhase(model, max_retries=max_retries)

        self._middleware = FilesystemMiddleware(session_id=session_id) if save_intermediate else None
        self._session_id = session_id or "deep-agent"

    # ── Public API ──────────────────────────────────────────────────────────

    async def run(self, goal: str) -> AsyncIterator[DeepAgentEvent]:
        """Run the full deep agent lifecycle.

        Yields ``DeepAgentEvent`` objects for the caller to process
        (streaming updates, UI rendering, etc.).

        Parameters
        ----------
        goal:
            The high-level goal to accomplish.
        """
        yield DeepAgentEvent(DeepAgentPhase.PLANNING, "start", {"goal": goal})

        # ── Phase 1: Planning ───────────────────────────────────────────
        try:
            plan = await self._planning.execute(goal)
            if self._middleware:
                self._middleware.save_plan(plan)

            yield DeepAgentEvent(
                DeepAgentPhase.PLANNING,
                "plan_created",
                {
                    "steps": len(plan.steps),
                    "complexity": plan.estimated_complexity,
                    "reasoning": plan.reasoning,
                },
            )
        except Exception as exc:
            yield DeepAgentEvent(
                DeepAgentPhase.PLANNING, "error", {"error": str(exc)}
            )
            yield DeepAgentEvent(DeepAgentPhase.DONE, "failed")
            return

        # ── Phase 2 & 3: Execute → Review loop ─────────────────────────
        attempt = 0
        while attempt <= self._max_retries:
            # Execution
            yield DeepAgentEvent(
                DeepAgentPhase.EXECUTION,
                "execution_start",
                {"attempt": attempt + 1, "steps": len(plan.steps)},
            )

            plan = await self._execution.execute(plan)

            # Yield step events after execution completes
            for step in plan.steps:
                if self._middleware:
                    self._middleware.save_step_result(step)
                yield DeepAgentEvent(
                    DeepAgentPhase.EXECUTION,
                    "step_done",
                    {
                        "step_id": step.id,
                        "status": step.status.value,
                        "result": step.result[:200] if step.result else "",
                    },
                )

            yield DeepAgentEvent(
                DeepAgentPhase.EXECUTION,
                "execution_done",
                {
                    "success": sum(1 for s in plan.steps if s.status == PlanStepStatus.SUCCESS),
                    "failed": sum(1 for s in plan.steps if s.status == PlanStepStatus.FAILED),
                    "skipped": sum(1 for s in plan.steps if s.status == PlanStepStatus.SKIPPED),
                },
            )

            # Review
            yield DeepAgentEvent(DeepAgentPhase.REVIEW, "review_start", {"attempt": attempt + 1})

            review = await self._review.execute(plan)
            if self._middleware:
                self._middleware.save_review(review)

            yield DeepAgentEvent(
                DeepAgentPhase.REVIEW,
                "review_done",
                {
                    "goal_achieved": review.get("goal_achieved", False),
                    "confidence": review.get("confidence", 0),
                    "issues": review.get("issues", []),
                    "summary": review.get("summary", ""),
                },
            )

            # Check if done
            if review.get("goal_achieved", False):
                yield DeepAgentEvent(
                    DeepAgentPhase.DONE,
                    "success",
                    {
                        "summary": review.get("summary", ""),
                        "steps_completed": sum(
                            1 for s in plan.steps if s.status == PlanStepStatus.SUCCESS
                        ),
                    },
                )
                return

            # Retry failed steps
            retry_ids = review.get("retry_steps", [])
            if not retry_ids or attempt >= self._max_retries:
                yield DeepAgentEvent(
                    DeepAgentPhase.DONE,
                    "partial_success",
                    {
                        "summary": review.get("summary", ""),
                        "issues": review.get("issues", []),
                    },
                )
                return

            # Reset failed steps for retry
            for sid in retry_ids:
                if 0 < sid <= len(plan.steps):
                    plan.steps[sid - 1].status = PlanStepStatus.PENDING
                    plan.steps[sid - 1].result = ""
                    plan.steps[sid - 1].error = None

            attempt += 1
            yield DeepAgentEvent(
                DeepAgentPhase.EXECUTION,
                "retry",
                {"attempt": attempt + 1, "retry_steps": retry_ids},
            )

        yield DeepAgentEvent(DeepAgentPhase.DONE, "max_retries_exceeded")
