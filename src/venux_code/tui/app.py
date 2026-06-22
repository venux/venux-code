"""Venux Code TUI — main Textual application.

Provides a full-screen chat interface with sidebar, status bar, and
multi-line input.  Designed to be launched from the CLI or directly.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from rich.markdown import Markdown
from rich.spinner import Spinner
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Static

from venux_code.tui.themes import get_theme
from venux_code.tui.widgets.chat import ChatDisplay, ChatMessage, Role
from venux_code.tui.widgets.input import ChatInput
from venux_code.tui.widgets.sidebar import SessionInfo, SessionSidebar
from venux_code.tui.widgets.status import StatusBar


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------

class VenuxTUI(App[None]):
    """Full-screen Venux Code TUI."""

    TITLE = "Venux Code"
    SUB_TITLE = "AI Coding Assistant"

    CSS = """
    #main-container {
        height: 1fr;
    }
    #chat-area {
        height: 1fr;
    }
    #thinking-indicator {
        height: 1;
        dock: top;
        background: $surface;
        color: $primary;
        display: none;
        padding: 0 1;
    }
    #thinking-indicator.visible {
        display: block;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True, priority=True),
        Binding("ctrl+l", "clear_chat", "Clear", show=True),
        Binding("ctrl+n", "new_session", "New Session", show=True),
        Binding("ctrl+o", "model_picker", "Model", show=True),
        Binding("ctrl+b", "toggle_sidebar", "Sidebar", show=True),
        Binding("ctrl+slash", "focus_input", "Focus Input", show=False),
    ]

    is_thinking: reactive[bool] = reactive(False)

    def __init__(
        self,
        agent: Any = None,
        session: Any = None,
        config: Any = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._agent = agent
        self._session = session
        self._config = config
        self._theme_name: str = getattr(config, "theme", "dark") if config else "dark"

    # ---- compose ---------------------------------------------------------

    def compose(self) -> ComposeResult:
        theme = get_theme(self._theme_name)
        self.theme = theme

        yield Header()
        with Horizontal(id="main-container"):
            yield SessionSidebar(on_select=self._on_session_select)
            with Vertical(id="chat-area"):
                yield Static("", id="thinking-indicator")
                yield ChatDisplay(id="chat-display")
                yield ChatInput(on_submit=self._on_user_submit, id="chat-input")
        yield StatusBar(id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Initialise status bar from config."""
        status = self.query_one("#status-bar", StatusBar)
        if self._config:
            status.update_model(getattr(self._config, "model", "—"))
        if self._session:
            status.update_session(getattr(self._session, "id", "—"))

        # Focus the input
        self.query_one("#chat-input", ChatInput).focus_input()

        # Set thinking indicator
        self._update_thinking_indicator()

    # ---- reactive watchers -----------------------------------------------

    def watch_is_thinking(self, thinking: bool) -> None:
        self._update_thinking_indicator()

    def _update_thinking_indicator(self) -> None:
        indicator = self.query_one("#thinking-indicator", Static)
        indicator.set_class(self.is_thinking, "visible")
        if self.is_thinking:
            indicator.update("⏳ Thinking…")

    # ---- actions ---------------------------------------------------------

    def action_quit(self) -> None:
        self.exit()

    def action_clear_chat(self) -> None:
        self.query_one("#chat-display", ChatDisplay).clear_chat()

    def action_new_session(self) -> None:
        display = self.query_one("#chat-display", ChatDisplay)
        display.clear_chat()
        status = self.query_one("#status-bar", StatusBar)
        status.update_session("new")
        status.set_status("New session started")

    def action_model_picker(self) -> None:
        """Placeholder for model picker modal."""
        status = self.query_one("#status-bar", StatusBar)
        status.set_status("Model picker not yet implemented")

    def action_toggle_sidebar(self) -> None:
        self.query_one(SessionSidebar).toggle()

    def action_focus_input(self) -> None:
        self.query_one("#chat-input", ChatInput).focus_input()

    # ---- callbacks -------------------------------------------------------

    def _on_session_select(self, session_id: str) -> None:
        status = self.query_one("#status-bar", StatusBar)
        status.update_session(session_id)
        status.set_status(f"Switched to session {session_id[:12]}")

    def _on_user_submit(self, text: str) -> None:
        """Handle user submitting a message."""
        display = self.query_one("#chat-display", ChatDisplay)

        # Show user message
        display.add_message(ChatMessage(role=Role.USER, content=text))

        # Start LLM call in background
        asyncio.create_task(self._run_agent(text))

    # ---- agent interaction -----------------------------------------------

    async def _run_agent(self, prompt: str) -> None:
        display = self.query_one("#chat-display", ChatDisplay)
        status = self.query_one("#status-bar", StatusBar)

        self.is_thinking = True
        status.set_status("Waiting for response…")

        try:
            if self._agent is None:
                display.add_message(
                    ChatMessage(
                        role=Role.SYSTEM,
                        content="No agent configured.  Set your API key and try again.",
                    )
                )
                return

            # Try streaming first
            if hasattr(self._agent, "stream"):
                display.begin_stream()
                try:
                    async for chunk in self._agent.stream(prompt):
                        display.append_stream(chunk)
                except Exception:
                    # Fallback to non-streaming
                    response = await self._agent.run(prompt)
                    display.end_stream()
                    display.add_message(
                        ChatMessage(role=Role.ASSISTANT, content=response)
                    )
                    return
                display.end_stream()
            else:
                response = await self._agent.run(prompt)
                display.add_message(
                    ChatMessage(role=Role.ASSISTANT, content=response)
                )

            status.add_tokens(len(prompt.split()) + 100)  # rough estimate
            status.set_status("Ready")

        except Exception as exc:
            display.add_message(
                ChatMessage(
                    role=Role.SYSTEM,
                    content=f"Error: {exc}",
                )
            )
            status.set_status(f"Error: {exc}")
        finally:
            self.is_thinking = False
