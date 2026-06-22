"""Base tool interface for all Venux Code tools.

Every concrete tool (bash, edit, view, …) subclasses ``BaseTool`` and
provides ``name``, ``description``, ``parameters_schema``, and an async
``execute`` method.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


# ── Response model ──────────────────────────────────────────────────────────


@dataclass
class ToolResponse:
    """Standardised response from a tool execution.

    Fields
    ------
    success:
        Whether the tool executed without errors.
    output:
        Human-readable text output (rendered in the chat).
    error:
        Error message when ``success`` is ``False``.
    metadata:
        Arbitrary extra data (exit code, file path, line count, …).
    display_type:
        Hint for the UI: ``"text"`` (default), ``"code"``, ``"diff"``,
        ``"image"``, ``"markdown"``.
    """

    success: bool
    output: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    display_type: str = "text"

    def __str__(self) -> str:
        if self.success:
            return self.output
        return f"Error: {self.error}"


# ── Base tool ───────────────────────────────────────────────────────────────


class BaseTool(ABC):
    """Abstract base class for all tools.

    Subclasses **must** set:

    * ``name`` – unique identifier used by the LLM in ``tool_calls``.
    * ``description`` – natural-language description for the model.
    * ``parameters_schema`` – a Pydantic ``BaseModel`` subclass defining
      the tool's parameters (used to generate the JSON Schema the model
      receives).

    Optionally:

    * ``requires_permission`` – if ``True``, the agent will ask for user
      permission before executing.  Defaults to ``False``.
    """

    name: str
    description: str
    requires_permission: bool = False

    # Subclasses set this to a Pydantic BaseModel *class* (not instance)
    parameters_schema: type[BaseModel]

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> ToolResponse:
        """Run the tool with the given *params* and return a ``ToolResponse``.

        Parameters
        ----------
        params:
            Validated parameters matching ``parameters_schema``.

        Returns
        -------
        ToolResponse
        """
        ...

    # ── LangChain integration ──────────────────────────────────────────────

    def to_langchain_tool(self) -> Any:
        """Convert to a LangChain ``StructuredTool`` for use with LangGraph.

        Uses ``StructuredTool.from_function`` so the agent graph can call
        ``tool.invoke(params)`` seamlessly.
        """
        from langchain_core.tools import StructuredTool

        schema = self.parameters_schema

        async def _run(**kwargs: Any) -> str:
            resp = await self.execute(kwargs)
            return str(resp)

        return StructuredTool.from_function(
            coroutine=_run,
            name=self.name,
            description=self.description,
            args_schema=schema,
        )

    def __repr__(self) -> str:
        perm = " [perm]" if self.requires_permission else ""
        return f"<Tool '{self.name}'{perm}>"
