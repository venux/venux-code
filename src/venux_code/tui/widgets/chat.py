"""Chat message display widget with syntax highlighting and tool-call support."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from textual.reactive import reactive
from textual.widgets import RichLog


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass
class ChatMessage:
    role: Role
    content: str
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output: str | None = None
    is_streaming: bool = False


class ChatDisplay(RichLog):
    """Scrollable chat log with rich formatting."""

    DEFAULT_CSS = """
    ChatDisplay {
        background: $background;
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
    }
    """

    messages: reactive[list[ChatMessage]] = reactive(list)
    _stream_buffer: str = ""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(highlight=True, markup=True, wrap=True, **kwargs)

    # ---- message rendering -----------------------------------------------

    def add_message(self, message: ChatMessage) -> None:
        self.messages.append(message)
        self._render_message(message)

    def _render_message(self, msg: ChatMessage) -> None:
        if msg.role == Role.USER:
            self._render_user(msg.content)
        elif msg.role == Role.ASSISTANT:
            self._render_assistant(msg.content)
        elif msg.role == Role.TOOL:
            self._render_tool(msg)
        elif msg.role == Role.SYSTEM:
            self._render_system(msg.content)

    def _render_user(self, content: str) -> None:
        panel = Panel(
            Markdown(content),
            title="[bold yellow]You[/bold yellow]",
            border_style="yellow",
            padding=(0, 1),
        )
        self.write(panel)

    def _render_assistant(self, content: str) -> None:
        panel = Panel(
            Markdown(content),
            title="[bold cyan]Assistant[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        )
        self.write(panel)

    def _render_tool(self, msg: ChatMessage) -> None:
        header = f"[bold dim white]🔧 Tool: {msg.tool_name or 'unknown'}[/bold dim white]"

        parts: list[Any] = [header]
        if msg.tool_input:
            input_json = Syntax(
                _safe_json(msg.tool_input),
                "json",
                theme="monokai",
                word_wrap=True,
            )
            parts.append(Text(""))
            parts.append(input_json)
        if msg.tool_output:
            parts.append(Text(""))
            parts.append(Syntax(msg.tool_output, "text", theme="monokai", word_wrap=True))

        panel = Panel(
            _rich_group(*parts),
            border_style="dim white",
            padding=(0, 1),
        )
        self.write(panel)

    def _render_system(self, content: str) -> None:
        self.write(Text(f"  ⚙ {content}", style="dim"))

    # ---- streaming support -----------------------------------------------

    def begin_stream(self) -> None:
        """Start a new streaming assistant message."""
        self._stream_buffer = ""
        self.write(Text("🤖 ", style="cyan"), end="")

    def append_stream(self, chunk: str) -> None:
        """Append a chunk to the current streaming message."""
        self._stream_buffer += chunk
        self.write(Text(chunk, style="foreground"), end="")

    def end_stream(self) -> None:
        """Finalise the streaming message — add it to the message list."""
        self.write(Text(""))
        msg = ChatMessage(role=Role.ASSISTANT, content=self._stream_buffer)
        self.messages.append(msg)
        self._stream_buffer = ""

    # ---- clear -----------------------------------------------------------

    def clear_chat(self) -> None:
        self.clear()
        self.messages = []

    # ---- re-render all ---------------------------------------------------

    def rerender(self) -> None:
        self.clear()
        for msg in self.messages:
            self._render_message(msg)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_json(obj: Any) -> str:
    import json
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False)
    except Exception:
        return str(obj)


def _rich_group(*renderables: Any) -> Any:
    """Group renderables for Panel content."""
    from rich.console import Group
    return Group(*renderables)
