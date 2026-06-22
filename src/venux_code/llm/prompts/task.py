"""Task agent prompt – for read-only / analysis tasks.

The task agent has access only to read-only tools (view, grep, glob, ls)
and is used for code review, analysis, documentation generation, etc.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import PromptBuilder, load_context_files


_TASK_ROLE = """\
You are Venux Code Task Agent, a read-only analysis assistant.
Your job is to analyze code, answer questions, and generate reports.
You have access to read-only tools – you cannot modify files or execute commands.
Provide thorough, well-structured analysis with clear reasoning."""


_TASK_TOOLS = """\
You have access to these **read-only** tools:

- **view**: Read file contents (supports line ranges and offsets).
- **grep**: Search file contents with regex patterns.
- **glob**: Find files by glob pattern.
- **ls**: List directory contents.
- **fetch**: Fetch content from URLs (HTTP GET/POST).
- **web_search**: Search the web for information.

**Important:** You do NOT have access to write, edit, bash, or patch tools.
If you need to suggest changes, describe them clearly in your response."""


_TASK_INSTRUCTIONS = """\
When analyzing code:
1. **Read the relevant files first** before making claims about them.
2. **Search broadly** to understand the codebase structure.
3. **Be specific** – cite file paths, line numbers, and code snippets.
4. **Provide actionable recommendations** – not just observations.
5. **Consider edge cases** and potential issues.
6. **Structure your response** with clear headings and sections."""


def build_task_prompt(
    *,
    tools_description: str | None = None,
    memory: str | None = None,
    project_root: Path | None = None,
    task_context: str | None = None,
) -> str:
    """Build the system prompt for the task (read-only) agent.

    Parameters
    ----------
    tools_description:
        Human-readable tool list.
    memory:
        Injected memory from previous sessions.
    project_root:
        Root directory to search for context files.
    task_context:
        Additional context specific to the task.

    Returns
    -------
    str
        The assembled system prompt.
    """
    builder = PromptBuilder()

    builder.section("Role", _TASK_ROLE)

    if tools_description:
        builder.section("Available Tools", f"{_TASK_TOOLS}\n\n### Tool Details\n\n{tools_description}")
    else:
        builder.section("Available Tools", _TASK_TOOLS)

    builder.section("Analysis Guidelines", _TASK_INSTRUCTIONS)

    builder.conditional("Memory & Context", memory, condition=bool(memory))

    # Project context
    ctx = load_context_files(project_root)
    if ctx:
        builder.section("Project Context", ctx[:20_000])

    builder.conditional("Task Context", task_context)

    builder.raw(
        "Provide a comprehensive response. Use code blocks for code snippets. "
        "If you cannot fully answer the question, explain what information is missing."
    )

    return builder.build()
