"""Multi-line input widget for composing messages."""

from __future__ import annotations

from typing import Callable, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Button, Static, TextArea


class ChatInput(Static):
    """Multi-line text input with a send button and hints bar."""

    DEFAULT_CSS = """
    ChatInput {
        dock: bottom;
        height: auto;
        max-height: 12;
        background: $surface;
        border-top: tall $border;
        padding: 0 1;
    }
    ChatInput TextArea {
        height: auto;
        min-height: 3;
        max-height: 8;
        background: $surface;
    }
    ChatInput .input-hints {
        height: 1;
        color: $foreground-muted;
        padding: 0 1;
    }
    ChatInput .send-row {
        height: 1;
        align: right middle;
        padding: 0 1;
    }
    ChatInput Button {
        min-width: 10;
    }
    """

    BINDINGS = [
        Binding("ctrl+enter", "send", "Send", show=False),
        Binding("escape", "clear_input", "Clear", show=False),
    ]

    can_send: reactive[bool] = reactive(False)

    def __init__(
        self,
        on_submit: Callable[[str], None] | None = None,
        placeholder: str = "Type a message… (Ctrl+Enter to send, Shift+Enter for newline)",
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._on_submit = on_submit
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        yield TextArea(id="chat-textarea", tab_behavior="indent")
        yield Static("Ctrl+Enter: send  │  Shift+Enter: newline  │  Esc: clear", classes="input-hints")

    def on_mount(self) -> None:
        textarea = self.query_one("#chat-textarea", TextArea)
        textarea.placeholder = self._placeholder
        textarea.watch(self, "text", self._on_text_changed)

    def _on_text_changed(self, new_value: str | None) -> None:
        self.can_send = bool(new_value and new_value.strip())

    def action_send(self) -> None:
        textarea = self.query_one("#chat-textarea", TextArea)
        text = textarea.text.strip()
        if text and self._on_submit:
            self._on_submit(text)
            textarea.clear()

    def action_clear_input(self) -> None:
        self.query_one("#chat-textarea", TextArea).clear()

    def focus_input(self) -> None:
        self.query_one("#chat-textarea", TextArea).focus()
