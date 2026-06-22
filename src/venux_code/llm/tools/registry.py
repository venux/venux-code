"""Tool registry – discovers, stores, and provides access to all tools.

The registry is the single source of truth for which tools are
available.  It can produce LangChain ``StructuredTool`` objects for
the agent graph and expose metadata for the UI / permission system.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .base import BaseTool
from .bash_tool import BashTool
from .edit_tool import EditTool
from .glob_tool import GlobTool
from .grep_tool import GrepTool
from .ls_tool import LsTool
from .view_tool import ViewTool
from .write_tool import WriteTool
from .fetch_tool import FetchTool
from .web_search_tool import WebSearchTool
from .patch_tool import PatchTool
from .delegate_tool import DelegateTool

logger = logging.getLogger(__name__)

# ── Default tool set ────────────────────────────────────────────────────────

_DEFAULT_TOOLS: list[type[BaseTool]] = [
    BashTool,
    EditTool,
    GlobTool,
    GrepTool,
    LsTool,
    ViewTool,
    WriteTool,
    FetchTool,
    WebSearchTool,
    PatchTool,
]


class ToolRegistry:
    """Central registry of all available tools.

    Usage
    -----
    ```python
    registry = ToolRegistry()
    bash = registry.get("bash")
    langchain_tools = registry.as_langchain_tools()
    perm_tools = registry.get_tools_requiring_permission()
    ```
    """

    def __init__(self, *, include_defaults: bool = True) -> None:
        self._tools: dict[str, BaseTool] = {}

        if include_defaults:
            for tool_cls in _DEFAULT_TOOLS:
                self.register(tool_cls())

    # ── Registration ────────────────────────────────────────────────────────

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance.  Overwrites any existing tool with the same name."""
        if tool.name in self._tools:
            logger.warning("Overwriting tool '%s'", tool.name)
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool)

    def unregister(self, name: str) -> None:
        """Remove a tool by name."""
        self._tools.pop(name, None)

    # ── Lookup ──────────────────────────────────────────────────────────────

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name, or ``None`` if not found."""
        return self._tools.get(name)

    def list_names(self) -> list[str]:
        """Return a sorted list of all registered tool names."""
        return sorted(self._tools.keys())

    def list_tools(self) -> list[BaseTool]:
        """Return all registered tool instances."""
        return list(self._tools.values())

    def get_tools_requiring_permission(self) -> list[BaseTool]:
        """Return tools that need user permission before execution."""
        return [t for t in self._tools.values() if t.requires_permission]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    # ── LangChain integration ──────────────────────────────────────────────

    def as_langchain_tools(self) -> list[Any]:
        """Convert all registered tools to LangChain ``StructuredTool`` objects.

        Returns a list suitable for passing to ``VenuxAgent(tools=...)``.
        """
        return [tool.to_langchain_tool() for tool in self._tools.values()]

    # ── Tool descriptions (for system prompt / UI) ─────────────────────────

    def describe_all(self) -> str:
        """Return a human-readable summary of all tools."""
        lines: list[str] = []
        for name in self.list_names():
            tool = self._tools[name]
            perm = " 🔒" if tool.requires_permission else ""
            lines.append(f"- **{name}**{perm}: {tool.description}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<ToolRegistry tools={self.list_names()}>"
