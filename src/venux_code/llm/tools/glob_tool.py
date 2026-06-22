"""Glob / file pattern search tool.

Finds files matching a glob pattern with optional directory scoping
and exclusion filters.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from .base import BaseTool, ToolResponse

# Common directories to skip for performance
_SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".eggs",
    ".next",
}


class GlobParams(BaseModel):
    """Parameters for the glob tool."""

    pattern: str = Field(
        description=(
            "Glob pattern to match files. Examples: '*.py', '**/*.ts', "
            "'src/**/*.go'. Uses Python pathlib glob syntax."
        )
    )
    path: str = Field(
        default=".",
        description="Root directory to search from. Defaults to '.'.",
    )
    max_results: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of results to return.",
    )


class GlobTool(BaseTool):
    """Find files matching a glob pattern."""

    name = "glob"
    description = (
        "Find files matching a glob pattern (e.g. '*.py', '**/*.ts'). "
        "Returns matching file paths sorted by name."
    )
    parameters_schema = GlobParams
    requires_permission = False

    async def execute(self, params: dict[str, Any]) -> ToolResponse:
        validated = GlobParams(**params)
        root = Path(validated.path).expanduser().resolve()

        if not root.is_dir():
            return ToolResponse(
                success=False,
                error=f"Not a directory: {root}",
            )

        matches: list[str] = []
        try:
            for match in root.glob(validated.pattern):
                # Skip common noise directories
                parts = match.relative_to(root).parts
                if any(p in _SKIP_DIRS for p in parts[:-1]):
                    continue

                if match.is_file():
                    matches.append(str(match))

                if len(matches) >= validated.max_results:
                    break
        except Exception as exc:
            return ToolResponse(
                success=False,
                error=f"Glob search failed: {exc}",
            )

        matches.sort()

        if not matches:
            return ToolResponse(
                success=True,
                output=f"No files matched pattern '{validated.pattern}' in {root}",
                metadata={"pattern": validated.pattern, "count": 0},
            )

        output = "\n".join(matches)
        truncated = len(matches) >= validated.max_results
        if truncated:
            output += f"\n... (stopped at {validated.max_results} results)"

        return ToolResponse(
            success=True,
            output=output,
            metadata={
                "pattern": validated.pattern,
                "count": len(matches),
                "truncated": truncated,
            },
            display_type="code",
        )
