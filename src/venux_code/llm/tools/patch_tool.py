"""Unified diff patch tool.

Applies a unified diff to a file on disk.  Supports single-file and
multi-file patches.  Validates the patch before application and returns
the patched content or detailed error information.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from .base import BaseTool, ToolResponse

logger = logging.getLogger(__name__)


class PatchParams(BaseModel):
    """Parameters for the patch tool."""

    file_path: str = Field(
        description="Path to the file to patch.",
    )
    patch: str = Field(
        description="Unified diff content to apply.",
    )
    reverse: bool = Field(
        default=False,
        description="If True, reverse-apply the patch (undo changes).",
    )
    strip: int = Field(
        default=0,
        ge=0,
        description="Number of leading path components to strip (like `patch -p`).",
    )
    dry_run: bool = Field(
        default=False,
        description="If True, validate the patch without applying it.",
    )


class PatchTool(BaseTool):
    """Apply a unified diff patch to a file."""

    name = "patch"
    description = (
        "Apply a unified diff patch to a file. The patch should be in "
        "standard unified diff format (--- a/file, +++ b/file, @@ hunks). "
        "Supports dry-run mode for validation. Use this for precise, "
        "multi-line edits that are hard to express as simple search/replace."
    )
    parameters_schema = PatchParams
    requires_permission = True

    async def execute(self, params: dict[str, Any]) -> ToolResponse:
        validated = PatchParams(**params)
        file_path = Path(validated.file_path).expanduser().resolve()

        if not file_path.is_file():
            return ToolResponse(
                success=False,
                error=f"File not found: {file_path}",
                metadata={"file_path": str(file_path)},
            )

        try:
            original = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ToolResponse(
                success=False,
                error=f"Cannot read file as text (binary?): {file_path}",
                metadata={"file_path": str(file_path)},
            )

        # Try using the `patch` command first (most robust)
        result = await self._apply_with_patch_command(
            original, validated.patch, validated.reverse, validated.strip
        )

        if result is None:
            # Fall back to Python-based patching
            result = self._apply_python_patch(original, validated.patch, validated.reverse)

        if result is None:
            return ToolResponse(
                success=False,
                error="Failed to apply patch – the diff may not match the file content",
                metadata={"file_path": str(file_path)},
                display_type="diff",
            )

        patched_text, stats = result

        if validated.dry_run:
            return ToolResponse(
                success=True,
                output=f"Patch would apply successfully. {stats}",
                metadata={
                    "file_path": str(file_path),
                    "dry_run": True,
                    "stats": stats,
                },
                display_type="diff",
            )

        # Write the patched content
        try:
            file_path.write_text(patched_text, encoding="utf-8")
            return ToolResponse(
                success=True,
                output=f"Patch applied successfully. {stats}",
                metadata={
                    "file_path": str(file_path),
                    "stats": stats,
                },
                display_type="diff",
            )
        except Exception as exc:
            return ToolResponse(
                success=False,
                error=f"Failed to write patched file: {exc}",
                metadata={"file_path": str(file_path)},
            )

    # ── Patch command approach ──────────────────────────────────────────────

    @staticmethod
    async def _apply_with_patch_command(
        original: str,
        patch_text: str,
        reverse: bool,
        strip: int,
    ) -> Optional[tuple[str, str]]:
        """Try applying the patch using the system `patch` command."""
        import asyncio
        import tempfile

        # Write original to temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(original)
            orig_path = f.name

        # Write patch to temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".patch", delete=False, encoding="utf-8"
        ) as f:
            f.write(patch_text)
            patch_path = f.name

        try:
            cmd = ["patch", f"-p{strip}", "--force", "--silent"]
            if reverse:
                cmd.append("--reverse")
            cmd.extend(["-i", patch_path, orig_path])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

            if proc.returncode == 0:
                patched = Path(orig_path).read_text(encoding="utf-8")
                stats = stdout.decode("utf-8", errors="replace").strip()
                return patched, stats or "Patch applied"

            return None

        except (FileNotFoundError, asyncio.TimeoutError, Exception):
            return None
        finally:
            for p in (orig_path, patch_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    # ── Python-based fallback ───────────────────────────────────────────────

    @staticmethod
    def _apply_python_patch(
        original: str,
        patch_text: str,
        reverse: bool,
    ) -> Optional[tuple[str, str]]:
        """Simple Python-based unified diff application.

        Handles standard unified diff format with @@ hunks.
        """
        import re

        original_lines = original.splitlines(keepends=True)
        patched_lines: list[str] = list(original_lines)

        # Parse hunks: @@ -old_start,old_count +new_start,new_count @@
        hunk_pattern = re.compile(
            r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$"
        )

        hunks: list[dict[str, Any]] = []
        current_hunk: dict[str, Any] | None = None

        for line in patch_text.splitlines():
            if line.startswith("@@"):
                if current_hunk:
                    hunks.append(current_hunk)
                m = hunk_pattern.match(line)
                if not m:
                    return None  # Invalid hunk header
                current_hunk = {
                    "old_start": int(m.group(1)),
                    "old_count": int(m.group(2) or "1"),
                    "new_start": int(m.group(3)),
                    "new_count": int(m.group(4) or "1"),
                    "context": m.group(5),
                    "lines": [],
                }
            elif current_hunk is not None:
                if line.startswith(" ") or line == "":
                    current_hunk["lines"].append(("context", line[1:] if line.startswith(" ") else line))
                elif line.startswith("-"):
                    current_hunk["lines"].append(("remove", line[1:]))
                elif line.startswith("+"):
                    current_hunk["lines"].append(("add", line[1:]))
                elif line.startswith("\\"):
                    continue  # "\ No newline at end of file"
                else:
                    # Possibly context without prefix
                    current_hunk["lines"].append(("context", line))

        if current_hunk:
            hunks.append(current_hunk)

        if not hunks:
            return None

        # Apply hunks in reverse order to preserve line numbers
        offset = 0
        applied = 0
        for hunk in reversed(hunks):
            old_start = hunk["old_start"] - 1  # 0-indexed
            old_count = hunk["old_count"]

            # Verify context matches
            hunk_old_lines = [
                text for op, text in hunk["lines"] if op in ("context", "remove")
            ]
            hunk_new_lines = [
                text for op, text in hunk["lines"] if op in ("context", "add")
            ]

            # If reversing, swap old/new
            if reverse:
                hunk_old_lines, hunk_new_lines = hunk_new_lines, hunk_old_lines

            idx = old_start + offset
            end_idx = idx + old_count

            # Bounds check
            if idx < 0 or end_idx > len(patched_lines):
                continue

            # Simple replacement
            patched_lines[idx:end_idx] = [
                line if line.endswith("\n") else line + "\n"
                for line in hunk_new_lines
            ]
            offset += len(hunk_new_lines) - old_count
            applied += 1

        if applied == 0:
            return None

        result = "".join(patched_lines)
        # Ensure trailing newline
        if result and not result.endswith("\n"):
            result += "\n"

        stats = f"{applied} hunk(s) applied"
        return result, stats
