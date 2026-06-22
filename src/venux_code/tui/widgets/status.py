"""Status bar widget — displays model, session, token usage, and cost."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static


class StatusBar(Static):
    """Bottom status bar showing session metadata."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $foreground;
        padding: 0 1;
    }
    """

    model: reactive[str] = reactive("—")
    session_id: reactive[str] = reactive("—")
    tokens_used: reactive[int] = reactive(0)
    cost: reactive[float] = reactive(0.0)
    status_text: reactive[str] = reactive("Ready")

    def render(self) -> Text:
        parts = Text()
        parts.append(" ⚡ ", style="bold accent")
        parts.append(f"Model: {self.model}", style="secondary")
        parts.append("  │  ", style="dim")
        parts.append(f"Session: {self.session_id[:12]}", style="secondary")
        parts.append("  │  ", style="dim")
        parts.append(f"Tokens: {self.tokens_used:,}", style="success")
        parts.append("  │  ", style="dim")
        parts.append(f"Cost: ${self.cost:.4f}", style="warning")
        parts.append("  │  ", style="dim")
        parts.append(self.status_text, style="primary")
        return parts

    # Convenience mutators -------------------------------------------------

    def update_model(self, model: str) -> None:
        self.model = model

    def update_session(self, session_id: str) -> None:
        self.session_id = session_id

    def add_tokens(self, count: int, cost_per_token: float = 0.0) -> None:
        self.tokens_used += count
        self.cost += count * cost_per_token

    def set_status(self, text: str) -> None:
        self.status_text = text
