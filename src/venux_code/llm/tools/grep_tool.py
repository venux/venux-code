"""Grep / content search tool.

Searches file contents for a regex or literal pattern with optional
file-type filtering and context lines.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from .base import BaseTool, ToolResponse

# Directories to skip
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
}

# Files to skip (binary-ish)
_SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".o", ".a", ".dll", ".exe",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".zip", ".tar", ".gz", ".bz2", ".7z",
    ".woff", ".woff2", ".ttf", ".eot",
    ".pdf", ".doc", ".docx",
    ".lock",
}

_MAX_MATCHES = 200
_MAX_LINE_LEN = 500


class GrepParams(BaseModel):
    """Parameters for the grep tool."""

    pattern: str = Field(description="Regex pattern (or literal with literal=True) to search for.")
    path: str = Field(default=".", description="Root directory to search. Defaults to '.'.")
    file_glob: Optional[str] = Field(
        default=None,
        description="Glob pattern to filter files (e.g. '*.py'). Applied after file discovery.",
    )
    case_sensitive: bool = Field(default=True, description="Case-sensitive search (default true).")
    literal: bool = Field(
        default=False,
        description="Treat pattern as a literal string instead of regex.",
    )
    context_lines: int = Field(
        default=0,
        ge=0,
        le=5,
        description="Number of context lines before/after each match.",
    )
    max_results: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of matching lines to return.",
    )


class GrepTool(BaseTool):
    """Search file contents for a pattern."""

    name = "grep"
    description = (
        "Search file contents for a regex or literal pattern. "
        "Supports file-type filtering, context lines, and case sensitivity. "
        "Returns matching lines with file paths and line numbers."
    )
    parameters_schema = GrepParams
    requires_permission = False

    async def execute(self, params: dict[str, Any]) -> ToolResponse:
        validated = GrepParams(**params)
        root = Path(validated.path).expanduser().resolve()

        if not root.is_dir():
            return ToolResponse(
                success=False,
                error=f"Not a directory: {root}",
            )

        # Compile pattern
        flags = 0 if validated.case_sensitive else re.IGNORECASE
        if validated.literal:
            pattern_str = re.escape(validated.pattern)
        else:
            pattern_str = validated.pattern
        try:
            regex = re.compile(pattern_str, flags)
        except re.error as exc:
            return ToolResponse(
                success=False,
                error=f"Invalid regex pattern: {exc}",
            )

        # Collect files to search
        if validated.file_glob:
            files = list(root.glob(f"**/{validated.file_glob}"))
        else:
            files = []
            try:
                for p in root.rglob("*"):
                    if p.is_file():
                        files.append(p)
            except PermissionError:
                pass

        # Filter out noise
        files = [
            f
            for f in files
            if f.is_file()
            and not any(d in _SKIP_DIRS for d in f.relative_to(root).parts[:-1])
            and f.suffix.lower() not in _SKIP_EXTENSIONS
        ]

        results: list[str] = []
        match_count = 0

        for filepath in files:
            try:
                text = filepath.read_text(encoding="utf-8", errors="ignore")
            except (OSError, PermissionError):
                continue

            file_lines = text.splitlines()
            rel = str(filepath.relative_to(root))

            for line_idx, line in enumerate(file_lines):
                if regex.search(line):
                    match_count += 1

                    # Context before
                    if validated.context_lines > 0:
                        start = max(0, line_idx - validated.context_lines)
                        for ci in range(start, line_idx):
                            cl = file_lines[ci]
                            if len(cl) > _MAX_LINE_LEN:
                                cl = cl[:_MAX_LINE_LEN] + "..."
                            results.append(f"{rel}:{ci + 1}: {cl}")

                    # Match line
                    display_line = line
                    if len(display_line) > _MAX_LINE_LEN:
                        display_line = display_line[:_MAX_LINE_LEN] + "..."
                    results.append(f"{rel}:{line_idx + 1}: {display_line}")

                    # Context after
                    if validated.context_lines > 0:
                        end = min(len(file_lines), line_idx + validated.context_lines + 1)
                        for ci in range(line_idx + 1, end):
                            cl = file_lines[ci]
                            if len(cl) > _MAX_LINE_LEN:
                                cl = cl[:_MAX_LINE_LEN] + "..."
                            results.append(f"{rel}:{ci + 1}: {cl}")

                    if match_count >= validated.max_results:
                        break

            if match_count >= validated.max_results:
                break

        if not results:
            return ToolResponse(
                success=True,
                output=f"No matches for '{validated.pattern}' in {root}",
                metadata={"pattern": validated.pattern, "matches": 0},
            )

        output = "\n".join(results)
        if match_count >= validated.max_results:
            output += f"\n... (stopped at {validated.max_results} matches)"

        return ToolResponse(
            success=True,
            output=output,
            metadata={
                "pattern": validated.pattern,
                "matches": match_count,
                "truncated": match_count >= validated.max_results,
            },
            display_type="code",
        )
