"""Directory listing tool.

Lists files and directories with optional detail (size, permissions)
and depth control.
"""

from __future__ import annotations

import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from .base import BaseTool, ToolResponse


class LsParams(BaseModel):
    """Parameters for the ls tool."""

    path: str = Field(
        default=".",
        description="Directory path to list. Defaults to current directory.",
    )
    show_hidden: bool = Field(
        default=False,
        description="Include hidden files (starting with '.').",
    )
    long_format: bool = Field(
        default=False,
        description="Show detailed info: size, modified date, permissions.",
    )


def _human_size(size: int) -> str:
    """Convert byte count to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:>7} {unit}"
        size //= 1024
    return f"{size:>7} TB"


class LsTool(BaseTool):
    """List directory contents."""

    name = "ls"
    description = (
        "List files and directories. Supports hidden files and a long "
        "format with sizes, permissions, and modification dates."
    )
    parameters_schema = LsParams
    requires_permission = False

    async def execute(self, params: dict[str, Any]) -> ToolResponse:
        validated = LsParams(**params)
        dir_path = Path(validated.path).expanduser().resolve()

        if not dir_path.exists():
            return ToolResponse(
                success=False,
                error=f"Path not found: {dir_path}",
            )
        if not dir_path.is_dir():
            return ToolResponse(
                success=False,
                error=f"Not a directory: {dir_path}",
            )

        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return ToolResponse(
                success=False,
                error=f"Permission denied: {dir_path}",
            )

        if not validated.show_hidden:
            entries = [e for e in entries if not e.name.startswith(".")]

        if not entries:
            return ToolResponse(
                success=True,
                output=f"(empty directory: {dir_path})",
                metadata={"path": str(dir_path), "count": 0},
            )

        lines: list[str] = []
        for entry in entries:
            name = entry.name
            if entry.is_dir():
                name += "/"

            if validated.long_format:
                try:
                    st = entry.stat()
                    perms = stat.filemode(st.st_mode)
                    size = _human_size(st.st_size)
                    mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
                    lines.append(f"{perms} {size} {mtime} {name}")
                except OSError:
                    lines.append(f"?????????? {'?':>7} {'?':>16} {name}")
            else:
                lines.append(name)

        return ToolResponse(
            success=True,
            output="\n".join(lines),
            metadata={"path": str(dir_path), "count": len(entries)},
            display_type="code",
        )
