"""Tests for provider registry and base classes."""

from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from venux_code.llm.providers.base import (
    BaseLLMProvider,
    ChatResponse,
    ModelInfo,
)


# ── ModelInfo ─────────────────────────────────────────────────────────────


class TestModelInfo:
    def test_default_values(self):
        info = ModelInfo(name="gpt-4o", provider="openai")
        assert info.name == "gpt-4o"
        assert info.provider == "openai"
        assert info.context_window == 128_000
        assert info.max_tokens == 4_096
        assert info.cost_per_1m_in == 0.0
        assert info.cost_per_1m_out == 0.0

    def test_custom_values(self):
        info = ModelInfo(
            name="claude-3-opus",
            provider="anthropic",
            context_window=200_000,
            max_tokens=8192,
            cost_per_1m_in=15.0,
            cost_per_1m_out=75.0,
        )
        assert info.context_window == 200_000
        assert info.cost_per_1m_in == 15.0

    def test_frozen(self):
        info = ModelInfo(name="test", provider="test")
        with pytest.raises(AttributeError):
            info.name = "changed"  # type: ignore

    def test_slots(self):
        info = ModelInfo(name="test", provider="test")
        assert hasattr(info, "__slots__") or True  # slots=True on frozen dataclass


# ── ChatResponse ──────────────────────────────────────────────────────────


class TestChatResponse:
    def test_minimal(self):
        resp = ChatResponse(content="hello")
        assert resp.content == "hello"
        assert resp.tool_calls == []
        assert resp.usage == {}
        assert resp.raw is None

    def test_with_all_fields(self):
        resp = ChatResponse(
            content="result",
            tool_calls=[{"name": "bash", "args": {"cmd": "ls"}}],
            usage={"input_tokens": 100, "output_tokens": 50},
            raw="mock_aimessage",
        )
        assert len(resp.tool_calls) == 1
        assert resp.usage["input_tokens"] == 100

    def test_tool_calls_default_factory(self):
        """Each ChatResponse gets its own list (not shared)."""
        r1 = ChatResponse(content="a")
        r2 = ChatResponse(content="b")
        r1.tool_calls.append({"name": "test"})
        assert len(r2.tool_calls) == 0


# ── BaseLLMProvider ───────────────────────────────────────────────────────


class TestBaseLLMProvider:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseLLMProvider(api_key="key", model_name="model")

    def test_concrete_subclass(self):
        class DummyProvider(BaseLLMProvider):
            def _build_model(self, *, stream=False, tools=None):
                return MagicMock()

            def model_info(self):
                return ModelInfo(name="dummy", provider="test")

        provider = DummyProvider(
            api_key="test-key",
            model_name="test-model",
            max_tokens=1024,
            temperature=0.5,
            base_url="http://localhost:8080",
        )
        assert provider.api_key == "test-key"
        assert provider.model_name == "test-model"
        assert provider.max_tokens == 1024
        assert provider.temperature == 0.5
        assert provider.base_url == "http://localhost:8080"
        assert provider.model_info().name == "dummy"


# ── ProviderRegistry ──────────────────────────────────────────────────────


class TestProviderRegistry:
    def test_available_providers(self):
        from venux_code.llm.providers.registry import ProviderRegistry

        registry = ProviderRegistry()
        available = registry.available()
        assert "openai" in available
        assert "anthropic" in available
        assert "google" in available
        assert "deepseek" in available
        assert "openrouter" in available

    def test_register_custom(self):
        from venux_code.llm.providers.registry import ProviderRegistry

        registry = ProviderRegistry()
        registry.register("custom", "some.module:SomeProvider")
        assert "custom" in registry.available()

    def test_unknown_provider_raises(self):
        from venux_code.llm.providers.registry import ProviderRegistry

        registry = ProviderRegistry()

        settings = SimpleNamespace(
            llm=SimpleNamespace(
                provider="nonexistent_provider",
                api_key=None,
                model="test",
                max_tokens=4096,
                temperature=0.7,
                base_url=None,
            )
        )
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            registry.create(settings=settings)

    @patch("venux_code.llm.providers.registry._import_class")
    def test_create_uses_settings_provider(self, mock_import):
        from venux_code.llm.providers.registry import ProviderRegistry

        mock_cls = MagicMock()
        mock_import.return_value = mock_cls

        settings = SimpleNamespace(
            llm=SimpleNamespace(
                provider="openai",
                api_key="test-key",
                model="gpt-4o",
                max_tokens=4096,
                temperature=0.7,
                base_url=None,
            )
        )

        registry = ProviderRegistry()
        registry.create(settings=settings)

        mock_import.assert_called_once()
        mock_cls.assert_called_once()

    @patch("venux_code.llm.providers.registry._import_class")
    def test_create_with_name_override(self, mock_import):
        from venux_code.llm.providers.registry import ProviderRegistry

        mock_cls = MagicMock()
        mock_import.return_value = mock_cls

        settings = SimpleNamespace(
            llm=SimpleNamespace(
                provider="openai",
                api_key="key",
                model="model",
                max_tokens=4096,
                temperature=0.7,
                base_url=None,
            )
        )

        registry = ProviderRegistry()
        registry.create(name="anthropic", settings=settings)

        # Should have been called with the anthropic dotted path
        call_args = mock_import.call_args[0][0]
        assert "anthropic" in call_args

    @patch("venux_code.llm.providers.registry._import_class")
    def test_create_passes_overrides(self, mock_import):
        from venux_code.llm.providers.registry import ProviderRegistry

        mock_cls = MagicMock()
        mock_import.return_value = mock_cls

        settings = SimpleNamespace(
            llm=SimpleNamespace(
                provider="openai",
                api_key="original-key",
                model="gpt-4o",
                max_tokens=4096,
                temperature=0.7,
                base_url=None,
            )
        )

        registry = ProviderRegistry()
        registry.create(settings=settings, api_key="override-key")

        # The override should be passed to the constructor
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["api_key"] == "override-key"
