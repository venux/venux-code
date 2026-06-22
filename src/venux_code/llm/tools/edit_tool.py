"""File edit tool – find and replace text in a file.

Performs a precise string replacement (not regex).  Returns a unified
diff of the change so the agent / user can review it.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .base import BaseTool, ToolResponse


class EditParams(BaseModel):
    """Parameters for the edit tool."""

    path: str = Field(description="Absolute or relative path to the file.")
    old_string: str = Field(
        description="Exact text to find in the file (must be unique)."
    )
    new_string: str = Field(description="Replacement text.")
    expected_replacements: int = Field(
        default=1,
        ge=1,
        description="Expected number of replacements (default 1).",
    )


class EditTool(BaseTool):
    """Find-and-replace text in a file."""

    name = "edit"
    description = (
        "Replace text in a file. The old_string must appear exactly "
        "(including whitespace) and be unique unless expected_replacements > 1. "
        "Returns a diff of the change."
    )
    parameters_schema = EditParams
    requires_permission = True

    async def execute(self, params: dict[str, Any]) -> ToolResponse:
        validated = EditParams(**params)
        file_path = Path(validated.path).expanduser().resolve()

        if not file_path.is_file():
            return ToolResponse(
                success=False,
                error=f"File not found: {file_path}",
            )

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            return ToolResponse(
                success=False,
                error=f"Failed to read file: {exc}",
            )

        count = content.count(validated.old_string)
        if count == 0:
            return ToolResponse(
                success=False,
                error=f"old_string not found in {file_path}",
                metadata={"file": str(file_path)},
            )
        if count != validated.expected_replacements:
            return ToolResponse(
                success=False,
                error=(
                    f"Found {count} occurrences of old_string, "
                    f"expected {validated.expected_replacements}"
                ),
                metadata={"file": str(file_path), "found": count},
            )

        new_content = content.replace(
            validated.old_string, validated.new_string, validated.expected_replacements
        )

        # Generate diff
        old_lines = content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = "".join(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{file_path.name}",
                tofile=f"b/{file_path.name}",
            )
        )

        try:
            file_path.write_text(new_content, encoding="utf-8")
        except Exception as exc:
            return ToolResponse(
                success=False,
                error=f"Failed to write file: {exc}",
            )

        return ToolResponse(
            success=True,
            output=diff or "(no visible diff – content unchanged)",
            metadata={
                "file": str(file_path),
                "replacements": validated.expected_replacements,
            },
            display_type="diff",
        )
