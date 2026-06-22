"""Tests for the delegate tool."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venux_code.llm.tools.delegate_tool import DelegateTool, DelegateParams


# ── DelegateParams ────────────────────────────────────────────────────────


class TestDelegateParams:
    def test_defaults(self):
        params = DelegateParams(task="test task")
        assert params.task == "test task"
        assert params.skills == []
        assert params.max_iterations == 20
        assert params.timeout == 120
        assert params.context is None

    def test_custom_values(self):
        params = DelegateParams(
            task="review code",
            skills=["python", "security"],
            max_iterations=30,
            timeout=60,
            context="Focus on the auth module.",
        )
        assert params.task == "review code"
        assert len(params.skills) == 2
        assert params.max_iterations == 30
        assert params.timeout == 60
        assert params.context == "Focus on the auth module."

    def test_max_iterations_validation(self):
        with pytest.raises(Exception):
            DelegateParams(task="t", max_iterations=0)  # below ge=1

        with pytest.raises(Exception):
            DelegateParams(task="t", max_iterations=100)  # above le=50

    def test_timeout_validation(self):
        with pytest.raises(Exception):
            DelegateParams(task="t", timeout=5)  # below ge=10

        with pytest.raises(Exception):
            DelegateParams(task="t", timeout=1000)  # above le=600


# ── DelegateTool ──────────────────────────────────────────────────────────


class TestDelegateTool:
    def test_name(self):
        assert DelegateTool.name == "delegate"

    def test_description(self):
        assert DelegateTool.description is not None
        assert "delegate" in DelegateTool.description.lower()

    def test_requires_permission_false(self):
        assert DelegateTool.requires_permission is False

    def test_parameters_schema(self):
        assert DelegateTool.parameters_schema is DelegateParams

    @pytest.mark.asyncio
    async def test_execute_with_factory(self):
        factory = AsyncMock(return_value="Sub-agent result here")
        tool = DelegateTool(agent_factory=factory)

        result = await tool.execute({
            "task": "Review the code",
            "skills": ["python"],
            "context": "Focus on errors.",
        })

        assert result.success is True
        assert result.output == "Sub-agent result here"
        assert "session_id" in result.metadata
        assert result.metadata["skills"] == ["python"]

        factory.assert_called_once()
        call_kwargs = factory.call_args[1]
        assert "Review the code" in call_kwargs["prompt"]
        assert "Focus on errors." in call_kwargs["prompt"]
        assert call_kwargs["skills"] == ["python"]

    @pytest.mark.asyncio
    async def test_execute_factory_timeout(self):
        async def slow_factory(**kwargs):
            await asyncio.sleep(100)
            return "never"

        tool = DelegateTool(agent_factory=slow_factory)
        result = await tool.execute({
            "task": "test",
            "timeout": 10,
        })
        assert result.success is False
        assert result.error is not None and "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_factory_exception(self):
        factory = AsyncMock(side_effect=RuntimeError("Agent crashed"))
        tool = DelegateTool(agent_factory=factory)

        result = await tool.execute({"task": "test"})
        assert result.success is False
        assert result.error is not None and "failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_context_in_prompt(self):
        factory = AsyncMock(return_value="ok")
        tool = DelegateTool(agent_factory=factory)

        await tool.execute({
            "task": "Do something",
            "context": "Extra info here.",
        })

        prompt = factory.call_args[1]["prompt"]
        assert "Extra info here." in prompt
        assert "Do something" in prompt

    @pytest.mark.asyncio
    async def test_no_context(self):
        factory = AsyncMock(return_value="ok")
        tool = DelegateTool(agent_factory=factory)

        await tool.execute({"task": "Do something"})

        prompt = factory.call_args[1]["prompt"]
        assert "Do something" in prompt
        assert "Additional Context" not in prompt

    def test_init_defaults(self):
        tool = DelegateTool()
        assert tool._agent_factory is None
        assert tool._default_tools == []
        assert tool._default_system_prompt is None

    def test_init_with_defaults(self):
        mock_tool = MagicMock()
        tool = DelegateTool(
            default_tools=[mock_tool],
            default_system_prompt="Custom prompt.",
        )
        assert len(tool._default_tools) == 1
        assert tool._default_system_prompt == "Custom prompt."
