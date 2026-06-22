"""Provider registry – creates providers by name."""

from __future__ import annotations

from typing import Any, Type

from venux_code.config.settings import Settings, get_settings
from venux_code.llm.providers.base import BaseLLMProvider

# ── lazy import map so unused providers never trigger import errors ──────────
_PROVIDER_CLASSES: dict[str, str] = {
    "openai": "venux_code.llm.providers.openai_provider:OpenAIProvider",
    "anthropic": "venux_code.llm.providers.anthropic_provider:AnthropicProvider",
    "google": "venux_code.llm.providers.google_provider:GoogleProvider",
    "gemini": "venux_code.llm.providers.google_provider:GoogleProvider",
    "deepseek": "venux_code.llm.providers.deepseek_provider:DeepSeekProvider",
    "mimo": "venux_code.llm.providers.mimo_provider:MiMoProvider",
    "kimi": "venux_code.llm.providers.kimi_provider:KimiProvider",
    "moonshot": "venux_code.llm.providers.kimi_provider:KimiProvider",
    "openrouter": "venux_code.llm.providers.openrouter_provider:OpenRouterProvider",
}


def _import_class(dotted: str) -> Type[BaseLLMProvider]:
    """Import ``module:attr`` path and return the class."""
    module_path, _, attr = dotted.partition(":")
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, attr)  # type: ignore[no-any-return]


class ProviderRegistry:
    """Registry that maps provider names to provider classes."""

    def __init__(self) -> None:
        self._classes: dict[str, str] = dict(_PROVIDER_CLASSES)

    # ── registration ──────────────────────────────────────────────────────────

    def register(self, name: str, dotted_path: str) -> None:
        """Register an additional provider at runtime."""
        self._classes[name.lower()] = dotted_path

    # ── creation ──────────────────────────────────────────────────────────────

    def create(
        self,
        name: str | None = None,
        *,
        settings: Settings | None = None,
        **overrides: Any,
    ) -> BaseLLMProvider:
        """Instantiate a provider.

        Parameters
        ----------
        name:
            Provider identifier (e.g. ``"openai"``, ``"anthropic"``).
            Falls back to ``settings.llm.provider``.
        settings:
            Application settings.  Uses ``get_settings()`` when *None*.
        **overrides:
            Extra keyword arguments forwarded to the provider constructor
            (e.g. ``api_key``, ``model_name``).
        """
        if settings is None:
            settings = get_settings()

        provider_name = (name or settings.llm.provider).lower()

        dotted = self._classes.get(provider_name)
        if dotted is None:
            available = ", ".join(sorted(self._classes))
            raise ValueError(
                f"Unknown LLM provider {provider_name!r}. "
                f"Available: {available}"
            )

        cls = _import_class(dotted)

        # Merge settings.llm values with explicit overrides.
        kwargs: dict[str, Any] = {
            "api_key": settings.llm.api_key,
            "model_name": settings.llm.model,
            "max_tokens": settings.llm.max_tokens,
            "temperature": settings.llm.temperature,
            "base_url": settings.llm.base_url,
        }
        kwargs.update(overrides)

        # Filter out None api_key – the provider will fail on first call,
        # but this avoids errors during testing / dry runs.
        return cls(**kwargs)  # type: ignore[abstract]

    # ── convenience ───────────────────────────────────────────────────────────

    def available(self) -> list[str]:
        """Return sorted list of registered provider names."""
        return sorted(self._classes)


# ── module-level shortcut ───────────────────────────────────────────────────

_registry = ProviderRegistry()


def create_provider(
    name: str | None = None,
    *,
    settings: Settings | None = None,
    **overrides: Any,
) -> BaseLLMProvider:
    """Shortcut for ``ProviderRegistry().create(...)``."""
    return _registry.create(name, settings=settings, **overrides)
