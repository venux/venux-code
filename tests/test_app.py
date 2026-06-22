"""Tests for VenuxApp central application class."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venux_code.app import VenuxApp, _AgentStub, get_app, reset_app


# ── _AgentStub ────────────────────────────────────────────────────────────


class TestAgentStub:
    @pytest.mark.asyncio
    async def test_run_returns_stub_message(self):
        stub = _AgentStub(model="test-model")
        result = await stub.run("Hello there")
        assert "stub" in result.lower()
        assert "Hello there" in result

    @pytest.mark.asyncio
    async def test_run_mentions_api_key(self):
        stub = _AgentStub()
        result = await stub.run("test")
        assert "API_KEY" in result or "api_key" in result.lower()

    @pytest.mark.asyncio
    async def test_stream_yields_words(self):
        stub = _AgentStub(model="test")
        chunks = []
        async for chunk in stub.stream("test"):
            chunks.append(chunk)
        assert len(chunks) > 0
        full = "".join(chunks)
        assert "stub" in full.lower()

    def test_default_model(self):
        stub = _AgentStub()
        assert stub.model == ""


# ── VenuxApp ──────────────────────────────────────────────────────────────


class TestVenuxApp:
    def test_initial_state(self):
        app = VenuxApp()
        assert app.settings is None
        assert app.provider is None
        assert app.tool_registry is None
        assert app.agent is None
        assert app._initialized is False

    @pytest.mark.asyncio
    async def test_create_skip_agent(self):
        """Test create with skip_agent=True (no LLM needed)."""
        with patch("venux_code.app.init_db", new_callable=AsyncMock) as mock_db, \
             patch("venux_code.app.ToolRegistry") as mock_registry_cls, \
             patch("venux_code.app.get_settings") as mock_get_settings:

            mock_settings = SimpleNamespace(
                db_url="sqlite+aiosqlite:///:memory:",
                database=SimpleNamespace(echo=False),
                llm=SimpleNamespace(provider="openai", model="gpt-4o"),
            )
            mock_get_settings.return_value = mock_settings
            mock_registry_instance = MagicMock()
            mock_registry_instance.__len__ = MagicMock(return_value=5)
            mock_registry_cls.return_value = mock_registry_instance

            app = await VenuxApp.create(skip_agent=True)

            assert app._initialized is True
            assert app.tool_registry is not None
            assert app.provider is None  # skipped
            mock_db.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_with_settings(self):
        """Test create with explicit settings."""
        with patch("venux_code.app.init_db", new_callable=AsyncMock), \
             patch("venux_code.app.ToolRegistry") as mock_registry_cls:

            mock_registry_instance = MagicMock()
            mock_registry_instance.__len__ = MagicMock(return_value=3)
            mock_registry_cls.return_value = mock_registry_instance

            settings = SimpleNamespace(
                db_url="sqlite+aiosqlite:///:memory:",
                database=SimpleNamespace(echo=False),
                llm=SimpleNamespace(provider="openai", model="gpt-4o"),
            )

            app = await VenuxApp.create(settings=settings, skip_agent=True)
            assert app.settings is settings

    @pytest.mark.asyncio
    async def test_shutdown(self):
        with patch("venux_code.app.dispose_engine", new_callable=AsyncMock) as mock_dispose:
            app = VenuxApp()
            app._initialized = True
            await app.shutdown()
            assert app._initialized is False
            mock_dispose.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_provider_failure(self):
        """Provider init failure should leave provider as None."""
        with patch("venux_code.app.create_provider", side_effect=Exception("no key")):
            app = VenuxApp()
            app.settings = SimpleNamespace(
                llm=SimpleNamespace(provider="openai", model="gpt-4o")
            )
            app._init_provider()
            assert app.provider is None

    @pytest.mark.asyncio
    async def test_init_agent_with_stub(self):
        """When provider is None, agent should be an _AgentStub."""
        app = VenuxApp()
        app.settings = SimpleNamespace(llm=SimpleNamespace(model="gpt-4o"))
        app.provider = None
        app.tool_registry = MagicMock()
        app.tool_registry.as_langchain_tools.return_value = []

        app._init_agent()
        assert isinstance(app.agent, _AgentStub)


# ── Singleton management ──────────────────────────────────────────────────


class TestSingleton:
    @pytest.mark.asyncio
    async def test_reset_app_clears_singleton(self):
        """reset_app should clear the global singleton."""
        import venux_code.app as app_module

        # Ensure clean state
        app_module._app = None

        # Set a fake app
        fake_app = MagicMock()
        fake_app.shutdown = AsyncMock()
        app_module._app = fake_app

        await reset_app()
        assert app_module._app is None
        fake_app.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_app_noop_when_none(self):
        """reset_app should be a no-op when no singleton exists."""
        import venux_code.app as app_module
        app_module._app = None
        await reset_app()  # should not raise
        assert app_module._app is None

    @pytest.mark.asyncio
    async def test_get_app_creates_singleton(self):
        """get_app should create and cache a VenuxApp."""
        import venux_code.app as app_module

        # Save and clear
        old_app = app_module._app
        app_module._app = None

        try:
            with patch.object(VenuxApp, "create", new_callable=AsyncMock) as mock_create:
                mock_app = MagicMock()
                mock_create.return_value = mock_app

                result = await get_app(skip_agent=True)
                assert result is mock_app
                assert app_module._app is mock_app

                # Second call should return cached
                result2 = await get_app()
                assert result2 is mock_app
                mock_create.assert_called_once()
        finally:
            app_module._app = old_app
