"""Main agent loop built on LangGraph.

``VenuxAgent`` constructs a ``StateGraph`` with three nodes:

1. **call_llm** – send the current messages to the chat model.
2. **should_continue** – decide whether to execute tools or finish.
3. **execute_tools** – run tool calls produced by the LLM.

The graph loops ``call_llm → should_continue → execute_tools → call_llm``
until the model stops requesting tool calls (or the iteration cap is hit).

Public API
----------
* ``VenuxAgent.run(user_message) -> AsyncIterator[AgentEvent]``
  yields streaming events for the UI / API layer.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Optional, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from venux_code.config.settings import get_settings
from venux_code.message.models import Message as VenuxMessage, ToolCall as VenuxToolCall, ToolCallFunction

from .state import AgentState

logger = logging.getLogger(__name__)

# ── Maximum agent loop iterations ───────────────────────────────────────────
MAX_ITERATIONS = 50

# ── Context window guard (characters) ───────────────────────────────────────
CONTEXT_CHAR_BUDGET = 120_000  # ≈ 30k tokens for most models


# ── Event types yielded to callers ─────────────────────────────────────────


class AgentEventType(str, Enum):
    """Types of events emitted by the agent loop."""

    LLM_TOKEN = "llm_token"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_RESULT = "tool_call_result"
    TOOL_PERMISSION_NEEDED = "tool_permission_needed"
    AGENT_DONE = "agent_done"
    ERROR = "error"


@dataclass
class AgentEvent:
    """A single streaming event from the agent."""

    type: AgentEventType
    data: dict[str, Any] = field(default_factory=dict)


# ── Agent ───────────────────────────────────────────────────────────────────


class VenuxAgent:
    """LangGraph-based coding agent.

    Parameters
    ----------
    model:
        Any LangChain ``BaseChatModel`` (OpenAI, Anthropic, Ollama, …).
    tools:
        List of LangChain-compatible tool objects (created from
        ``venux_code.llm.tools.registry.ToolRegistry``).
    system_prompt:
        Optional system message prepended to every conversation.
    max_iterations:
        Hard cap on agent loop rounds.  Defaults to ``MAX_ITERATIONS``.
    """

    def __init__(
        self,
        *,
        model: BaseChatModel,
        tools: Sequence[Any] | None = None,
        system_prompt: str | None = None,
        max_iterations: int = MAX_ITERATIONS,
    ) -> None:
        self._model = model
        self._tools = list(tools) if tools else []
        self._system_prompt = system_prompt
        self._max_iterations = max_iterations

        # Bind tools to the model so it can emit tool_call arguments
        if self._tools:
            self._model_with_tools = model.bind_tools(self._tools)
        else:
            self._model_with_tools = model

        # Build the LangGraph graph
        self._graph = self._build_graph()

    # ── Graph construction ──────────────────────────────────────────────────

    def _build_graph(self) -> Any:
        """Create and compile the LangGraph ``StateGraph``."""
        graph = StateGraph(AgentState)

        # Nodes
        graph.add_node("call_llm", self._call_llm)
        graph.add_node("execute_tools", ToolNode(self._tools))

        # Edges
        graph.set_entry_point("call_llm")
        graph.add_conditional_edges(
            "call_llm",
            self._should_continue,
            {
                "execute_tools": "execute_tools",
                "end": END,
            },
        )
        graph.add_edge("execute_tools", "call_llm")

        return graph.compile()

    # ── Nodes ───────────────────────────────────────────────────────────────

    async def _call_llm(self, state: AgentState) -> dict[str, Any]:
        """Send current messages to the LLM and return the response."""
        messages = self._apply_system_prompt(state["messages"])
        messages = self._enforce_context_budget(messages)

        iteration = state.get("iteration", 0) + 1

        response: AIMessage = await self._model_with_tools.ainvoke(messages)

        return {
            "messages": [response],
            "iteration": iteration,
        }

    @staticmethod
    def _should_continue(state: AgentState) -> str:
        """Decide whether to call tools or end."""
        last = state["messages"][-1]

        # Guard against infinite loops
        if state.get("iteration", 0) >= MAX_ITERATIONS:
            return "end"

        if isinstance(last, AIMessage) and last.tool_calls:
            return "execute_tools"
        return "end"

    # ── Public API ──────────────────────────────────────────────────────────

    async def run(
        self,
        user_message: str,
        *,
        session_id: str = "",
        history: list[BaseMessage] | None = None,
        permission_callback: Any | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Run the agent loop and stream ``AgentEvent`` s.

        Parameters
        ----------
        user_message:
            The user's text input.
        session_id:
            Current session identifier.
        history:
            Prior conversation messages (optional).
        permission_callback:
            ``async (tool_name, params) -> bool`` called before executing
            a tool whose ``requires_permission`` is ``True``.
        """
        initial_messages: list[BaseMessage] = list(history or [])
        initial_messages.append(HumanMessage(content=user_message))

        initial_state: AgentState = {
            "messages": initial_messages,
            "session_id": session_id,
            "tools_called": [],
            "is_done": False,
            "iteration": 0,
        }

        try:
            async for event in self._graph.astream_events(
                initial_state, version="v2"
            ):
                kind = event.get("event", "")

                # ── LLM streaming tokens ───────────────────────────────────
                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        yield AgentEvent(
                            type=AgentEventType.LLM_TOKEN,
                            data={"token": chunk.content},
                        )

                # ── Tool call started ──────────────────────────────────────
                elif kind == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    tool_input = event.get("data", {}).get("input", {})
                    yield AgentEvent(
                        type=AgentEventType.TOOL_CALL_START,
                        data={"tool": tool_name, "params": tool_input},
                    )

                # ── Tool call finished ─────────────────────────────────────
                elif kind == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    output = event.get("data", {}).get("output", "")
                    yield AgentEvent(
                        type=AgentEventType.TOOL_CALL_RESULT,
                        data={"tool": tool_name, "result": output},
                    )

            # Mark done
            yield AgentEvent(type=AgentEventType.AGENT_DONE, data={})

        except Exception as exc:
            logger.exception("Agent loop error")
            yield AgentEvent(
                type=AgentEventType.ERROR,
                data={"error": str(exc)},
            )

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _apply_system_prompt(
        self, messages: list[BaseMessage]
    ) -> list[BaseMessage]:
        """Prepend the system prompt if configured and not already present."""
        if not self._system_prompt:
            return messages
        if messages and isinstance(messages[0], SystemMessage):
            return messages
        return [SystemMessage(content=self._system_prompt)] + messages

    @staticmethod
    def _enforce_context_budget(
        messages: list[BaseMessage],
    ) -> list[BaseMessage]:
        """Drop older messages if total character count exceeds budget.

        Always keeps the system message (index 0) and the most recent
        user message.  Intermediate messages are dropped oldest-first.
        """
        total = sum(len(m.content or "") for m in messages)
        if total <= CONTEXT_CHAR_BUDGET:
            return messages

        # Keep system message if present
        start_idx = 1 if messages and isinstance(messages[0], SystemMessage) else 0
        system = messages[:start_idx]
        rest = messages[start_idx:]

        # Always keep last message
        last = rest[-1:]
        body = rest[:-1]

        # Drop oldest until under budget
        while body and sum(len(m.content or "") for m in system + body + last) > CONTEXT_CHAR_BUDGET:
            body.pop(0)

        return system + body + last

    # ── Conversion helpers for persistence ──────────────────────────────────

    @staticmethod
    def langchain_to_venux_message(
        msg: BaseMessage, *, session_id: str = ""
    ) -> VenuxMessage:
        """Convert a LangChain message to a Venux domain ``Message``."""
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

        if isinstance(msg, HumanMessage):
            role = "user"
        elif isinstance(msg, AIMessage):
            role = "assistant"
        elif isinstance(msg, ToolMessage):
            role = "tool"
        elif isinstance(msg, SystemMessage):
            role = "system"
        else:
            role = "assistant"

        tool_calls: list[VenuxToolCall] = []
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(
                    VenuxToolCall(
                        id=tc.get("id", ""),
                        function=ToolCallFunction(
                            name=tc.get("name", ""),
                            arguments=str(tc.get("args", {})),
                        ),
                    )
                )

        return VenuxMessage(
            session_id=session_id,
            role=role,  # type: ignore[arg-type]
            content=msg.content if isinstance(msg.content, str) else str(msg.content or ""),
            tool_calls=tool_calls,
            tool_call_id=getattr(msg, "tool_call_id", None),
        )
