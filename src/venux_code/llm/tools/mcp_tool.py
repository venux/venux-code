"""Individual MCP tool wrapper as a Venux Code ``BaseTool``.

Each MCP tool discovered by :class:`~.mcp_adapter.MCPAdapter` is wrapped
in an ``MCPToolWrapper`` so it can participate in the Venux tool system
(and be converted to a LangChain ``StructuredTool`` via the inherited
:meth:`BaseTool.to_langchain_tool`).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import mcp
from pydantic import BaseModel, Field, create_model

from .base import BaseTool, ToolResponse

logger = logging.getLogger(__name__)


# ── JSON Schema → Pydantic model helpers ────────────────────────────────────

_JSON_TYPE_MAP: dict[str, type[Any]] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _json_type_to_python(prop: dict[str, Any]) -> type[Any]:
    """Map a JSON Schema property definition to a Python type.

    Handles ``type``, ``enum`` (→ ``str`` for now), and falls back to
    ``Any`` for unknown / complex schemas.
    """
    # If enum is present, the values are typically strings.
    if "enum" in prop:
        return str

    json_type = prop.get("type", "string")
    return _JSON_TYPE_MAP.get(json_type, str)


def _create_params_schema(input_schema: dict[str, Any] | None) -> type[BaseModel]:
    """Dynamically build a Pydantic model from a JSON ``inputSchema``.

    Parameters
    ----------
    input_schema:
        The ``inputSchema`` field from an ``mcp.Tool`` object.  Expected
        to follow JSON Schema ``type: object`` conventions.

    Returns
    -------
    type[BaseModel]
        A Pydantic model class whose fields mirror the schema properties.
    """
    if not input_schema:
        return create_model("MCPToolParams")

    properties: dict[str, dict[str, Any]] = input_schema.get("properties", {})
    required_fields: set[str] = set(input_schema.get("required", []))

    field_definitions: dict[str, Any] = {}

    for prop_name, prop_def in properties.items():
        python_type = _json_type_to_python(prop_def)
        description = prop_def.get("description", "")
        is_required = prop_name in required_fields

        if is_required:
            field_definitions[prop_name] = (
                python_type,
                Field(description=description),
            )
        else:
            default = prop_def.get("default")
            field_definitions[prop_name] = (
                Optional[python_type],  # type: ignore[arg-type]
                Field(default=default, description=description),
            )

    return create_model("MCPToolParams", **field_definitions)


# ── MCPToolWrapper ───────────────────────────────────────────────────────────


class MCPToolWrapper(BaseTool):
    """Wraps a single MCP server tool as a Venux Code ``BaseTool``.

    Instances are created by :meth:`MCPAdapter.as_base_tools` (and
    indirectly by :meth:`MCPAdapter.as_langchain_tools`).  You rarely
    need to instantiate this class yourself.

    Parameters
    ----------
    mcp_tool:
        The ``mcp.Tool`` descriptor from the server.
    adapter:
        The live :class:`MCPAdapter` that owns the connection to the
        server which provides this tool.
    """

    def __init__(
        self,
        mcp_tool: mcp.Tool,
        adapter: "MCPAdapter",  # noqa: F821 — forward ref resolved at runtime
    ) -> None:
        self.name: str = mcp_tool.name
        self.description: str = (
            mcp_tool.description or f"MCP tool: {mcp_tool.name}"
        )
        self.parameters_schema: type[BaseModel] = _create_params_schema(
            mcp_tool.inputSchema
        )
        self.requires_permission: bool = False

        self._mcp_tool = mcp_tool
        self._adapter = adapter

    # ── Execute ──────────────────────────────────────────────────────────

    async def execute(self, params: dict[str, Any]) -> ToolResponse:
        """Call the underlying MCP tool via the adapter's live session.

        Parameters
        ----------
        params:
            Validated arguments matching ``parameters_schema``.

        Returns
        -------
        ToolResponse
            Success / failure with the tool's text output or error.
        """
        try:
            result = await self._adapter.call_tool(self.name, params)

            # Extract text content from the MCP result.
            output_parts: list[str] = []
            for block in result.content:
                if hasattr(block, "text"):
                    output_parts.append(block.text)
                elif hasattr(block, "data"):
                    # Base64-encoded binary (e.g. images) – represent as
                    # a placeholder; callers can inspect the raw result.
                    output_parts.append(f"[{getattr(block, 'type', 'binary')} data]")
                else:
                    output_parts.append(str(block))

            output_text = "\n".join(output_parts)

            is_error = getattr(result, "isError", False)

            return ToolResponse(
                success=not is_error,
                output=output_text if not is_error else "",
                error=output_text if is_error else None,
                metadata={
                    "mcp_tool": self.name,
                    "server": self._adapter.name,
                },
            )

        except RuntimeError:
            return ToolResponse(
                success=False,
                error=(
                    f"MCP adapter '{self._adapter.name}' is not connected. "
                    "Call connect_stdio() / connect_sse() first."
                ),
            )
        except Exception as exc:
            logger.exception("MCP tool '%s' execution failed", self.name)
            return ToolResponse(
                success=False,
                error=f"MCP tool '{self.name}' failed: {exc}",
                metadata={"mcp_tool": self.name, "server": self._adapter.name},
            )

    # ── Repr ─────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"<MCPToolWrapper '{self.name}'"
            f" server='{self._adapter.name}'>"
        )
