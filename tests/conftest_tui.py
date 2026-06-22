"""Shared TUI test fixtures for Venux Code.

Provides mock agent, config, session, and pre-built app fixtures for
Textual UI tests using pytest-asyncio.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from venux_code.tui.app import VenuxTUI
from venux_code.tui.widgets.chat import ChatDisplay, ChatMessage, Role
from venux_code.tui.widgets.input import ChatInput
from venux_code.tui.widgets.sidebar import SessionInfo, SessionSidebar
from venux_code.tui.widgets.status import StatusBar


# ---------------------------------------------------------------------------
# Mock objects
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_config():
    """Return a mock config object with typical defaults."""
    cfg = MagicMock()
    cfg.theme = "dark"
    cfg.model = "claude-sonnet-4-20250514"
    return cfg


@pytest.fixture
def mock_session():
    """Return a mock session object."""
    sess = MagicMock()
    sess.id = "test-session-1234-5678-abcd"
    return sess


@pytest.fixture
def mock_agent():
    """Return a mock agent with a simple run method."""
    agent = AsyncMock()
    agent.run = AsyncMock(return_value="Hello from mock agent!")
    return agent


@pytest.fixture
def mock_streaming_agent():
    """Return a mock agent with a stream method."""
    agent = AsyncMock()
    agent.stream = MagicMock(
        return_value=_async_iter(["Hello ", "from ", "streaming ", "agent!"])
    )
    agent.run = AsyncMock(return_value="Hello from streaming agent!")
    return agent


async def _async_iter(items):
    """Helper to create an async iterator from a list."""
    for item in items:
        yield item


# ---------------------------------------------------------------------------
# App fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tui_app(mock_agent, mock_config, mock_session):
    """Return a VenuxTUI app with mocked dependencies (not yet running)."""
    return VenuxTUI(agent=mock_agent, config=mock_config, session=mock_session)


@pytest.fixture
def tui_app_no_agent(mock_config, mock_session):
    """Return a VenuxTUI app with no agent configured."""
    return VenuxTUI(agent=None, config=mock_config, session=mock_session)


@pytest.fixture
def tui_app_minimal():
    """Return a VenuxTUI app with no config/session/agent."""
    return VenuxTUI()


@pytest.fixture
def make_tui_app():
    """Factory fixture to create VenuxTUI with custom parameters."""

    def _factory(agent=None, config=None, session=None, **kwargs):
        return VenuxTUI(agent=agent, config=config, session=session, **kwargs)

    return _factory
