"""Prompt template system for Venux Code.

Provides a flexible template engine supporting both ``string.Template``
(simple ``$variable`` substitution) and Jinja2 (when available) for more
complex prompt construction.

Usage
-----
```python
from venux_code.llm.prompts.base import PromptTemplate

tmpl = PromptTemplate("You are $role. ${instructions}")
rendered = tmpl.render(role="a coder", instructions="Write clean code.")
```
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from string import Template
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Base template ───────────────────────────────────────────────────────────


class PromptTemplate:
    """Prompt template with variable substitution.

    Supports two modes:
    - **Simple** (default): uses ``string.Template`` with ``$var`` / ``${var}``
    - **Jinja2**: if ``use_jinja=True`` and Jinja2 is installed, uses Jinja2
      template syntax (``{{ var }}``, ``{% if %}``, etc.)

    Parameters
    ----------
    template:
        The template string.
    use_jinja:
        Whether to use Jinja2 instead of string.Template.
    name:
        Optional identifier for the template (used in logging).
    """

    def __init__(
        self,
        template: str,
        *,
        use_jinja: bool = False,
        name: str = "",
    ) -> None:
        self._template_str = template
        self._use_jinja = use_jinja
        self._name = name or "unnamed"

    def render(self, **variables: Any) -> str:
        """Render the template with the given variables.

        Parameters
        ----------
        **variables:
            Key-value pairs to substitute into the template.

        Returns
        -------
        str
            The rendered prompt string.
        """
        if self._use_jinja:
            return self._render_jinja(**variables)
        return self._render_simple(**variables)

    def _render_simple(self, **variables: Any) -> str:
        """Render using ``string.Template``."""
        tmpl = Template(self._template_str)
        try:
            return tmpl.safe_substitute(**variables)
        except Exception:
            logger.warning(
                "Template '%s' rendering failed, returning raw template",
                self._name,
            )
            return self._template_str

    def _render_jinja(self, **variables: Any) -> str:
        """Render using Jinja2 (if available)."""
        try:
            from jinja2 import Environment, BaseLoader

            env = Environment(loader=BaseLoader(), autoescape=False)
            tmpl = env.from_string(self._template_str)
            return tmpl.render(**variables)
        except ImportError:
            logger.warning(
                "Jinja2 not installed, falling back to string.Template "
                "for template '%s'",
                self._name,
            )
            return self._render_simple(**variables)
        except Exception as exc:
            logger.error("Jinja2 rendering failed for '%s': %s", self._name, exc)
            return self._template_str

    @classmethod
    def from_file(cls, path: Path | str, **kwargs: Any) -> PromptTemplate:
        """Load a template from a file."""
        p = Path(path)
        content = p.read_text(encoding="utf-8")
        name = kwargs.pop("name", p.stem)
        return cls(content, name=name, **kwargs)

    def __repr__(self) -> str:
        preview = self._template_str[:60].replace("\n", "\\n")
        return f"<PromptTemplate '{self._name}': \"{preview}...\">"


# ── Context file loading ───────────────────────────────────────────────────

# Files the agent should look for in the project root for extra context.
CONTEXT_FILE_NAMES: list[str] = [
    "CLAUDE.md",
    ".cursorrules",
    ".github/copilot-instructions.md",
    "AGENTS.md",
    "CONVENTIONS.md",
    "README.md",
    ".venux/rules.md",
]


def load_context_files(project_root: Path | None = None) -> str:
    """Load context from well-known project files.

    Searches *project_root* (or CWD) for files listed in
    ``CONTEXT_FILE_NAMES`` and concatenates their contents.

    Returns
    -------
    str
        Combined context text, or empty string if no files found.
    """
    root = project_root or Path.cwd()
    parts: list[str] = []

    for name in CONTEXT_FILE_NAMES:
        path = root / name
        if path.is_file():
            try:
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(f"## {name}\n\n{content}")
            except Exception:
                logger.debug("Could not read context file: %s", path)

    return "\n\n---\n\n".join(parts)


# ── Prompt builder ──────────────────────────────────────────────────────────


class PromptBuilder:
    """Fluent API for constructing complex prompts from sections.

    Usage
    -----
    ```python
    prompt = (
        PromptBuilder()
        .section("Role", "You are a senior Python developer.")
        .section("Tools", tool_descriptions)
        .conditional("Memory", memory, condition=bool(memory))
        .build()
    )
    ```
    """

    def __init__(self) -> None:
        self._sections: list[tuple[str, str]] = []
        self._raw_parts: list[str] = []

    def section(self, title: str, content: str) -> PromptBuilder:
        """Add a titled section."""
        if content.strip():
            self._sections.append((title, content.strip()))
        return self

    def conditional(
        self, title: str, content: str | None, *, condition: bool = True
    ) -> PromptBuilder:
        """Add a section only if *condition* is True and content is non-empty."""
        if condition and content and content.strip():
            self._sections.append((title, content.strip()))
        return self

    def raw(self, text: str) -> PromptBuilder:
        """Add raw text (no section header)."""
        if text.strip():
            self._raw_parts.append(text.strip())
        return self

    def build(self) -> str:
        """Assemble all sections into the final prompt string."""
        parts: list[str] = []

        for raw in self._raw_parts:
            parts.append(raw)

        for title, content in self._sections:
            parts.append(f"# {title}\n\n{content}")

        return "\n\n".join(parts)
