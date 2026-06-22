"""Session sidebar — lists saved sessions for quick switching."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Label, ListItem, ListView, Static


@dataclass
class SessionInfo:
    id: str
    title: str
    created_at: str = ""
    message_count: int = 0


class SessionSidebar(Vertical):
    """Collapsible sidebar listing chat sessions."""

    DEFAULT_CSS = """
    SessionSidebar {
        width: 30;
        min-width: 0;
        background: $panel;
        border-right: tall $border;
        overflow-y: auto;
    }
    SessionSidebar.collapsed {
        width: 0;
        min-width: 0;
        display: none;
    }
    SessionSidebar .sidebar-title {
        padding: 1 1 0 1;
        text-style: bold;
        color: $primary;
    }
    SessionSidebar ListView {
        height: 1fr;
    }
    SessionSidebar ListItem {
        padding: 0 1;
    }
    SessionSidebar ListItem.--highlight {
        background: $surface;
    }
    """

    collapsed: reactive[bool] = reactive(False)
    sessions: reactive[list[SessionInfo]] = reactive(list)
    selected_session_id: reactive[Optional[str]] = reactive(None)

    def __init__(
        self,
        on_select: Callable[[str], None] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._on_select = on_select

    def compose(self) -> ComposeResult:
        yield Label("📁 Sessions", classes="sidebar-title")
        yield ListView(id="session-list")

    def watch_collapsed(self, collapsed: bool) -> None:
        self.set_class(collapsed, "collapsed")

    def watch_sessions(self, sessions: list[SessionInfo]) -> None:
        self._refresh_list()

    def _refresh_list(self) -> None:
        list_view = self.query_one("#session-list", ListView)
        list_view.clear()
        for session in self.sessions:
            display = f"{session.title or session.id[:8]}"
            if session.message_count:
                display += f"  ({session.message_count})"
            item = ListItem(Label(display), id=f"session-{session.id}")
            list_view.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle session selection."""
        item_id = event.item.id or ""
        if item_id.startswith("session-"):
            sid = item_id.removeprefix("session-")
            self.selected_session_id = sid
            if self._on_select:
                self._on_select(sid)

    def toggle(self) -> None:
        self.collapsed = not self.collapsed

    def add_session(self, session: SessionInfo) -> None:
        self.sessions = [session, *self.sessions]

    def set_sessions(self, sessions: list[SessionInfo]) -> None:
        self.sessions = sessions
