"""Write content to a file.

Creates the file (and parent directories) if it doesn't exist,
or overwrites it entirely if it does.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .base import BaseTool, ToolResponse


class WriteParams(BaseModel):
    """Parameters for the write tool."""

    path: str = Field(description="Absolute or relative path to the file.")
    content: str = Field(description="The full content to write to the file.")
    create_parents: bool = Field(
        default=True,
        description="Create parent directories if they don't exist.",
    )


class WriteTool(BaseTool):
    """Write content to a file, creating it if needed."""

    name = "write"
    description = (
        "Write the full content to a file. Creates the file and parent "
        "directories if they don't exist. WARNING: overwrites existing files."
    )
    parameters_schema = WriteParams
    requires_permission = True

    async def execute(self, params: dict[str, Any]) -> ToolResponse:
        validated = WriteParams(**params)
        file_path = Path(validated.path).expanduser().resolve()

        try:
            if validated.create_parents:
                file_path.parent.mkdir(parents=True, exist_ok=True)

            existed = file_path.exists()
            file_path.write_text(validated.content, encoding="utf-8")

            line_count = validated.content.count("\n") + (1 if validated.content and not validated.content.endswith("\n") else 0)

            action = "Updated" if existed else "Created"
            return ToolResponse(
                success=True,
                output=f"{action} {file_path} ({line_count} lines, {len(validated.content)} bytes)",
                metadata={
                    "file": str(file_path),
                    "lines": line_count,
                    "bytes": len(validated.content.encode("utf-8")),
                    "created": not existed,
                },
            )
        except Exception as exc:
            return ToolResponse(
                success=False,
                error=f"Failed to write file: {exc}",
                metadata={"file": str(file_path)},
            )
