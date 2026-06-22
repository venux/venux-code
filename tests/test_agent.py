"""Tests for the agent loop with mock LLM provider."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from venux_code.llm.agent.agent import VenuxAgent, AgentEventType, MAX_ITERATIONS
from venux_code.llm.agent.state import AgentState
from venux_code.message.models import Message, MessageRole, ToolCall, ToolCallFunction


class TestAgentState:
    def test_state_keys(self):
        """Verify AgentState TypedDict has required keys."""
        required = {"messages", "session_id", "tools_called", "is_done", "iteration"}
        assert required == set(AgentState.__annotations__.keys())

    def test_merge_messages(self):
        from venux_code.llm.agent.state import _merge_messages

        existing = [HumanMessage(content="a")]
        new = [AIMessage(content="b")]
        merged = _merge_messages(existing, new)
        assert len(merged) == 2
        assert merged[0].content == "a"
        assert merged[1].content == "b"


class TestVenuxAgent:
    def test_create_agent(self, mock_model):
        agent = VenuxAgent(model=mock_model)
        assert agent is not None

    def test_create_with_tools(self, mock_model):
        from venux_code.llm.tools.registry import ToolRegistry

        registry = ToolRegistry()
        lc_tools = registry.as_langchain_tools()
        agent = VenuxAgent(model=mock_model, tools=lc_tools)
        assert agent is not None

    def test_create_with_system_prompt(self, mock_model):
        agent = VenuxAgent(model=mock_model, system_prompt="You are helpful.")
        assert agent._system_prompt == "You are helpful."

    async def test_run_simple_response(self, mock_model):
        """Agent should yield AGENT_DONE after a simple text response."""
        agent = VenuxAgent(model=mock_model)

        events = []
        async for event in agent.run("Hi there", session_id="test"):
            events.append(event)

        # Should have at least AGENT_DONE
        event_types = [e.type for e in events]
        assert AgentEventType.AGENT_DONE in event_types

    async def test_run_with_tool_call(self, mock_model_factory):
        """Agent should execute tools and then finish."""
        # First response: tool call; second response: final answer
        tool_call_msg = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_123",
                    "name": "bash",
                    "args": {"command": "echo hello"},
                }
            ],
        )
        final_msg = AIMessage(content="Command executed successfully.")

        model = mock_model_factory(responses=[tool_call_msg, final_msg])

        # We need a tool that actually works
        from venux_code.llm.tools.registry import ToolRegistry

        registry = ToolRegistry()
        lc_tools = registry.as_langchain_tools()

        agent = VenuxAgent(model=model, tools=lc_tools)
        events = []
        async for event in agent.run("Run echo hello", session_id="test"):
            events.append(event)

        event_types = [e.type for e in events]
        assert AgentEventType.AGENT_DONE in event_types

    async def test_run_error_handling(self, mock_model):
        """Agent should yield ERROR event on exceptions."""
        # Create a model that raises
        error_model = MagicMock()
        error_model.bind_tools.return_value = error_model

        async def raise_error(*args, **kwargs):
            raise RuntimeError("Test error")

        error_model.ainvoke = raise_error

        agent = VenuxAgent(model=error_model)
        events = []
        async for event in agent.run("Hello", session_id="test"):
            events.append(event)

        event_types = [e.type for e in events]
        assert AgentEventType.ERROR in event_types

    def test_should_continue_with_tool_calls(self):
        state: AgentState = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{"id": "c1", "name": "bash", "args": {}}],
                )
            ],
            "session_id": "test",
            "tools_called": [],
            "is_done": False,
            "iteration": 1,
        }
        assert VenuxAgent._should_continue(state) == "execute_tools"

    def test_should_continue_no_tool_calls(self):
        state: AgentState = {
            "messages": [AIMessage(content="Done.")],
            "session_id": "test",
            "tools_called": [],
            "is_done": False,
            "iteration": 1,
        }
        assert VenuxAgent._should_continue(state) == "end"

    def test_should_continue_max_iterations(self):
        state: AgentState = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{"id": "c1", "name": "bash", "args": {}}],
                )
            ],
            "session_id": "test",
            "tools_called": [],
            "is_done": False,
            "iteration": MAX_ITERATIONS,
        }
        assert VenuxAgent._should_continue(state) == "end"

    def test_apply_system_prompt(self, mock_model):
        agent = VenuxAgent(model=mock_model, system_prompt="Be helpful.")
        messages = [HumanMessage(content="Hi")]
        result = agent._apply_system_prompt(messages)
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "Be helpful."

    def test_apply_system_prompt_already_present(self, mock_model):
        agent = VenuxAgent(model=mock_model, system_prompt="Be helpful.")
        messages = [SystemMessage(content="Already there"), HumanMessage(content="Hi")]
        result = agent._apply_system_prompt(messages)
        assert result[0].content == "Already there"

    def test_apply_system_prompt_none(self, mock_model):
        agent = VenuxAgent(model=mock_model)
        messages = [HumanMessage(content="Hi")]
        result = agent._apply_system_prompt(messages)
        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)

    def test_enforce_context_budget(self):
        # Under budget: no changes
        messages = [HumanMessage(content="short")]
        result = VenuxAgent._enforce_context_budget(messages)
        assert len(result) == 1

    def test_enforce_context_budget_over(self):
        # Over budget: should drop middle messages
        messages = [
            SystemMessage(content="system"),
            HumanMessage(content="x" * 60_000),
            AIMessage(content="y" * 60_000),
            HumanMessage(content="latest"),
        ]
        result = VenuxAgent._enforce_context_budget(messages)
        # Should keep system + latest
        assert isinstance(result[0], SystemMessage)
        assert isinstance(result[-1], HumanMessage)
        assert result[-1].content == "latest"

    def test_langchain_to_venux_message_human(self):
        msg = HumanMessage(content="Hello")
        result = VenuxAgent.langchain_to_venux_message(msg, session_id="s1")
        assert result.role == MessageRole.USER
        assert result.content == "Hello"
        assert result.session_id == "s1"

    def test_langchain_to_venux_message_ai(self):
        msg = AIMessage(content="Hi there")
        result = VenuxAgent.langchain_to_venux_message(msg, session_id="s1")
        assert result.role == MessageRole.ASSISTANT

    def test_langchain_to_venux_message_tool(self):
        msg = ToolMessage(content="result", tool_call_id="tc1")
        result = VenuxAgent.langchain_to_venux_message(msg, session_id="s1")
        assert result.role == MessageRole.TOOL

    def test_langchain_to_venux_message_ai_with_tool_calls(self):
        msg = AIMessage(
            content="",
            tool_calls=[
                {"id": "tc1", "name": "bash", "args": {"command": "ls"}}
            ],
        )
        result = VenuxAgent.langchain_to_venux_message(msg, session_id="s1")
        assert result.role == MessageRole.ASSISTANT
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].function.name == "bash"
