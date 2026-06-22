"""View / read a file's contents.

Supports reading the whole file or a specific line range with line
numbers.  Optionally shows line count and total size.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from .base import BaseTool, ToolResponse


class ViewParams(BaseModel):
    """Parameters for the view tool."""

    path: str = Field(description="Absolute or relative path to the file.")
    offset: int = Field(
        default=1,
        ge=1,
        description="Line number to start reading from (1-indexed).",
    )
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        description="Maximum number of lines to read. None for entire file.",
    )


class ViewTool(BaseTool):
    """Read and display file contents."""

    name = "view"
    description = (
        "Read the contents of a file. Supports reading a specific line "
        "range with offset and limit. Returns the content with line numbers."
    )
    parameters_schema = ViewParams
    requires_permission = False

    async def execute(self, params: dict[str, Any]) -> ToolResponse:
        validated = ViewParams(**params)
        file_path = Path(validated.path).expanduser().resolve()

        if not file_path.exists():
            return ToolResponse(
                success=False,
                error=f"Path not found: {file_path}",
            )
        if not file_path.is_file():
            return ToolResponse(
                success=False,
                error=f"Not a file: {file_path} (use ls for directories)",
            )

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return ToolResponse(
                success=False,
                error=f"Failed to read file: {exc}",
            )

        lines = content.splitlines()
        total_lines = len(lines)

        # Apply offset (1-indexed)
        start = max(0, validated.offset - 1)
        end = len(lines)
        if validated.limit is not None:
            end = min(end, start + validated.limit)

        selected = lines[start:end]

        # Format with line numbers
        numbered = []
        for i, line in enumerate(selected, start=start + 1):
            numbered.append(f"{i:>6}|{line}")

        output = "\n".join(numbered)
        if end < total_lines:
            output += f"\n... ({total_lines - end} more lines)"

        return ToolResponse(
            success=True,
            output=output,
            metadata={
                "file": str(file_path),
                "total_lines": total_lines,
                "offset": validated.offset,
                "shown": len(selected),
            },
            display_type="code",
        )
