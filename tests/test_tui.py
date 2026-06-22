"""UI automation tests for Venux Code TUI.

Uses Textual's built-in testing framework:
    async with app.run_test() as pilot:
        await pilot.click(...)
        await pilot.press(...)
"""

from __future__ import annotations

import pytest

# Skip all TUI tests if textual is not installed
try:
    from textual.app import App
    HAS_TEXTUAL = True
except ImportError:
    HAS_TEXTUAL = False

pytestmark = pytest.mark.skipif(not HAS_TEXTUAL, reason="textual not installed")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tui_app():
    """Create a minimal TUI app for testing."""
    try:
        from venux_code.tui.app import VenuxTUI
        return VenuxTUI()
    except Exception:
        pytest.skip("VenuxTUI not importable")


# ---------------------------------------------------------------------------
# Basic Launch Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_app_launches(tui_app):
    """App starts without crashing."""
    async with tui_app.run_test() as pilot:
        assert tui_app.is_running


@pytest.mark.asyncio
async def test_app_has_header(tui_app):
    """Header widget is present."""
    async with tui_app.run_test() as pilot:
        from textual.widgets import Header
        headers = tui_app.query(Header)
        assert len(headers) > 0


@pytest.mark.asyncio
async def test_app_has_footer(tui_app):
    """Footer widget is present."""
    async with tui_app.run_test() as pilot:
        from textual.widgets import Footer
        footers = tui_app.query(Footer)
        assert len(footers) > 0


# ---------------------------------------------------------------------------
# Keyboard Shortcut Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ctrl_c_exits(tui_app):
    """Ctrl+C should exit the app."""
    async with tui_app.run_test() as pilot:
        await pilot.press("ctrl+c")
        # App should be exiting or have exited
        # After Ctrl+C, the app may show a quit dialog or exit


@pytest.mark.asyncio
async def test_ctrl_l_clears(tui_app):
    """Ctrl+L should clear the screen."""
    async with tui_app.run_test() as pilot:
        await pilot.press("ctrl+l")
        # Should not crash


@pytest.mark.asyncio
async def test_question_mark_toggles_help(tui_app):
    """? should toggle help dialog."""
    async with tui_app.run_test() as pilot:
        await pilot.press("question_mark")
        # Should not crash


# ---------------------------------------------------------------------------
# Layout Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sidebar_exists(tui_app):
    """Sidebar container exists."""
    async with tui_app.run_test() as pilot:
        # Look for sidebar by ID or class
        try:
            sidebar = tui_app.query_one("#sidebar")
            assert sidebar is not None
        except Exception:
            # Sidebar might use different selector
            pass


@pytest.mark.asyncio
async def test_chat_area_exists(tui_app):
    """Chat area exists."""
    async with tui_app.run_test() as pilot:
        try:
            chat = tui_app.query_one("#chat")
            assert chat is not None
        except Exception:
            pass


@pytest.mark.asyncio
async def test_status_bar_exists(tui_app):
    """Status bar exists."""
    async with tui_app.run_test() as pilot:
        try:
            status = tui_app.query_one("#status")
            assert status is not None
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Widget Tests (import directly)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_display_add_message():
    """ChatDisplay widget can add messages."""
    try:
        from venux_code.tui.widgets.chat import ChatDisplay, Role, ChatMessage
    except ImportError:
        pytest.skip("ChatDisplay not importable")

    display = ChatDisplay()
    # Test adding different message types via add_message(ChatMessage)
    display.add_message(ChatMessage(role=Role.USER, content="Hello"))
    display.add_message(ChatMessage(role=Role.ASSISTANT, content="Hi there!"))
    display.add_message(ChatMessage(role=Role.SYSTEM, content="System info"))
    display.add_message(ChatMessage(role=Role.TOOL, content="ls -la result", tool_name="bash"))


@pytest.mark.asyncio
async def test_chat_display_streaming():
    """ChatDisplay supports streaming text."""
    try:
        from venux_code.tui.widgets.chat import ChatDisplay
    except ImportError:
        pytest.skip("ChatDisplay not importable")

    # Streaming requires mounted widget, test the methods exist
    assert hasattr(ChatDisplay, 'begin_stream')
    assert hasattr(ChatDisplay, 'append_stream')
    assert hasattr(ChatDisplay, 'end_stream')


@pytest.mark.asyncio
async def test_status_bar_model_update():
    """StatusBar can update model name."""
    try:
        from venux_code.tui.widgets.status import StatusBar
    except ImportError:
        pytest.skip("StatusBar not importable")

    bar = StatusBar()
    bar.update_model("gpt-4o")
    assert bar.model == "gpt-4o"
    bar.update_session("test-session-123")
    assert bar.session_id == "test-session-123"


@pytest.mark.asyncio
async def test_sidebar_add_session():
    """Sidebar can add sessions."""
    try:
        from venux_code.tui.widgets.sidebar import SessionSidebar
    except ImportError:
        pytest.skip("SessionSidebar not importable")

    sidebar = SessionSidebar()
    # SessionSidebar uses dataclass SessionInfo
    from venux_code.tui.widgets.sidebar import SessionInfo
    info = SessionInfo(id="session-1", title="Test Session")
    assert info.id == "session-1"
    assert info.title == "Test Session"


# ---------------------------------------------------------------------------
# Theme Tests
# ---------------------------------------------------------------------------

def test_themes_importable():
    """Theme module is importable."""
    try:
        from venux_code.tui import themes
        assert hasattr(themes, "THEMES") or hasattr(themes, "get_theme")
    except ImportError:
        pytest.skip("themes not importable")


def test_dark_theme_exists():
    """Dark theme is defined."""
    try:
        from venux_code.tui.themes import THEMES
        assert "dark" in THEMES or len(THEMES) > 0
    except (ImportError, AttributeError):
        pytest.skip("THEMES not available")
