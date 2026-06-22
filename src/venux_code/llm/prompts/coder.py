"""Main coder agent system prompt.

Constructs the system prompt for the primary coding agent, including:
- Role definition
- Tool usage instructions
- Safety guidelines
- Context file loading (CLAUDE.md, .cursorrules, etc.)
- Memory injection
- Skill injection
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .base import PromptBuilder, load_context_files


# ── Default role ────────────────────────────────────────────────────────────

_CODER_ROLE = """\
You are Venux Code, an advanced AI coding assistant created by Nous Research.
You are an expert software engineer who writes clean, efficient, and well-tested code.
You work in a terminal-based environment with access to the local filesystem and shell.
You think step-by-step, plan before acting, and explain your reasoning concisely."""


# ── Tool usage instructions ─────────────────────────────────────────────────

_TOOL_INSTRUCTIONS = """\
You have access to the following tools. Use them to accomplish tasks:

- **bash**: Execute shell commands. Use for building, testing, running scripts, git operations.
- **view**: Read file contents. Use this instead of `cat` in bash.
- **write**: Create or overwrite files. Use this instead of `echo` heredocs.
- **edit**: Make targeted edits to existing files using find-and-replace.
- **patch**: Apply unified diff patches for complex multi-line changes.
- **glob**: Find files by pattern. Use this instead of `find` or `ls`.
- **grep**: Search file contents. Use this instead of `grep` or `rg`.
- **ls**: List directory contents.
- **fetch**: Fetch content from URLs (HTTP GET/POST).
- **web_search**: Search the web for information.
- **delegate**: Delegate sub-tasks to isolated sub-agents.

**Important guidelines:**
1. Always prefer tools over shell equivalents (use `view` not `cat`, `grep` not `grep`).
2. Read files before editing them to understand the current state.
3. Use `patch` for complex multi-line edits; use `edit` for simple find-and-replace.
4. Verify changes by reading files or running tests after modifications.
5. Be mindful of file encoding and line endings."""


# ── Safety guidelines ───────────────────────────────────────────────────────

_SAFETY_GUIDELINES = """\
1. **Never delete files** without explicit user permission.
2. **Always ask** before running destructive commands (rm -rf, DROP TABLE, etc.).
3. **Don't commit** without user approval unless explicitly asked to auto-commit.
4. **Respect .gitignore** – don't track or modify ignored files.
5. **Don't expose secrets** – never echo or log API keys, tokens, or passwords.
6. **Prefer minimal changes** – make the smallest edit that solves the problem.
7. **Explain risky operations** before executing them.
8. **Verify assumptions** – read the code before modifying it."""


# ── Builder function ────────────────────────────────────────────────────────


def build_coder_prompt(
    *,
    tools_description: str | None = None,
    memory: str | None = None,
    skills: list[str] | None = None,
    skill_descriptions: dict[str, str] | None = None,
    project_root: Path | None = None,
    extra_context: str | None = None,
    max_context_chars: int = 30_000,
) -> str:
    """Build the full system prompt for the coding agent.

    Parameters
    ----------
    tools_description:
        Human-readable tool list (from ``ToolRegistry.describe_all()``).
    memory:
        Injected memory/context from previous sessions.
    skills:
        List of active skill names.
    skill_descriptions:
        ``{skill_name: description}`` map for active skills.
    project_root:
        Root directory to search for context files.
    extra_context:
        Additional context text to append.
    max_context_chars:
        Maximum characters for the context file section.

    Returns
    -------
    str
        The assembled system prompt.
    """
    builder = PromptBuilder()

    # Role
    builder.section("Role", _CODER_ROLE)

    # Tools
    if tools_description:
        builder.section(
            "Available Tools",
            f"{_TOOL_INSTRUCTIONS}\n\n### Tool Details\n\n{tools_description}",
        )
    else:
        builder.section("Available Tools", _TOOL_INSTRUCTIONS)

    # Safety
    builder.section("Safety Guidelines", _SAFETY_GUIDELINES)

    # Skills
    if skills:
        skill_lines: list[str] = []
        for s in skills:
            desc = (skill_descriptions or {}).get(s, "")
            if desc:
                skill_lines.append(f"- **{s}**: {desc}")
            else:
                skill_lines.append(f"- **{s}**")
        builder.section(
            "Active Skills",
            "You have the following skills loaded:\n\n"
            + "\n".join(skill_lines)
            + "\n\nUse these skills when relevant to the task.",
        )

    # Memory
    builder.conditional(
        "Memory & Context",
        memory,
        condition=bool(memory),
    )

    # Project context files
    ctx = load_context_files(project_root)
    if ctx:
        if len(ctx) > max_context_chars:
            ctx = ctx[:max_context_chars] + "\n\n... (context truncated)"
        builder.section("Project Context", ctx)

    # Extra context
    builder.conditional("Additional Context", extra_context)

    # Instructions footer
    builder.raw(
        "When you have completed the task, summarize what you did and "
        "any issues encountered. If you cannot complete the task, explain why."
    )

    return builder.build()
