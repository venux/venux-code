"""Agent state definition for LangGraph-based agent loop."""

from __future__ import annotations

from typing import Annotated, Any
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage


def _merge_messages(
    existing: list[BaseMessage], new: list[BaseMessage]
) -> list[BaseMessage]:
    """Reducer: append new messages to existing list."""
    return existing + new


class AgentState(TypedDict):
    """State flowing through the LangGraph agent graph.

    Fields
    ------
    messages:
        Conversation history (LangChain BaseMessage objects).
        Uses ``Annotated[..., add_messages]`` or a manual merge reducer
        so each node can *return* new messages without clobbering old ones.
    session_id:
        The current session identifier, carried through for logging and
        permission checks.
    tools_called:
        Running list of tool names that have been invoked so far.  Useful
        for the UI to show "thinking" indicators and for context pruning.
    is_done:
        Flag set to ``True`` when the agent decides it has finished its
        work (no more tool calls requested).  Graph edges use this to
        route to ``END``.
    iteration:
        Counter incremented on every LLM call to enforce a hard cap on
        the number of agent loops (prevents infinite loops).
    """

    messages: Annotated[list[BaseMessage], _merge_messages]
    session_id: str
    tools_called: Annotated[list[str], _merge_messages]
    is_done: bool
    iteration: int
