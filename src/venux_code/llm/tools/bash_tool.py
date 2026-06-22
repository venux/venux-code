"""Bash / shell command execution tool.

Runs arbitrary shell commands in a subprocess with configurable timeout
and working directory.  Requires permission by default.
"""

from __future__ import annotations

import asyncio
import os
import shlex
from typing import Any, Optional

from pydantic import BaseModel, Field

from .base import BaseTool, ToolResponse


class BashParams(BaseModel):
    """Parameters for the bash tool."""

    command: str = Field(description="The shell command to execute.")
    timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Maximum seconds to wait (default 30, max 300).",
    )
    working_directory: Optional[str] = Field(
        default=None,
        description="Working directory for the command. Defaults to session CWD.",
    )


class BashTool(BaseTool):
    """Execute shell commands via subprocess."""

    name = "bash"
    description = (
        "Execute a shell command and return its stdout/stderr. "
        "Use for building, testing, running scripts, git operations, etc."
    )
    parameters_schema = BashParams
    requires_permission = True

    async def execute(self, params: dict[str, Any]) -> ToolResponse:
        validated = BashParams(**params)
        command = validated.command
        timeout = validated.timeout
        cwd = validated.working_directory

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env={**os.environ},
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResponse(
                    success=False,
                    error=f"Command timed out after {timeout}s",
                    metadata={"exit_code": -1, "command": command},
                    display_type="code",
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

            # Truncate overly long output
            max_output = 50_000
            if len(stdout) > max_output:
                stdout = stdout[:max_output] + f"\n... (truncated, {len(stdout_bytes)} bytes total)"
            if len(stderr) > max_output:
                stderr = stderr[:max_output] + f"\n... (truncated, {len(stderr_bytes)} bytes total)"

            exit_code = proc.returncode or 0
            output_parts: list[str] = []
            if stdout:
                output_parts.append(stdout)
            if stderr:
                output_parts.append(f"[stderr]\n{stderr}")

            success = exit_code == 0
            return ToolResponse(
                success=success,
                output="\n".join(output_parts) if success else "",
                error="\n".join(output_parts) if not success else None,
                metadata={"exit_code": exit_code, "command": command},
                display_type="code",
            )

        except FileNotFoundError:
            return ToolResponse(
                success=False,
                error=f"Shell not found. Command: {command}",
                metadata={"command": command},
            )
        except Exception as exc:
            return ToolResponse(
                success=False,
                error=f"Failed to execute command: {exc}",
                metadata={"command": command},
            )
