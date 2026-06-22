"""Central application object for Venux Code.

``VenuxApp`` owns every major subsystem – settings, database, services,
LLM provider, tool registry, and agent.  It is created once at startup
and passed (or retrieved via the module-level singleton) by CLI commands,
the TUI, and tests.

Mirrors the role of ``app.go`` in OpenCode.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from venux_code.config.settings import Settings, get_settings
from venux_code.db.engine import init_db, dispose_engine
from venux_code.llm.providers.base import BaseLLMProvider
from venux_code.llm.providers.registry import create_provider
from venux_code.llm.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# System prompt used when no custom prompt is configured.
_DEFAULT_SYSTEM_PROMPT = """\
You are Venux Code, an AI coding assistant running in a terminal.
You help users write, edit, debug, and understand code.
You have access to tools for reading/writing files, running shell commands,
searching code, and more. Always think step-by-step and use tools when needed.
Be concise but thorough. Prefer showing code over describing it.
"""


class VenuxApp:
    """Singleton application context.

    Typical lifecycle::

        app = await VenuxApp.create()
        # ... use app.agent, app.services, etc. ...
        await app.shutdown()
    """

    def __init__(self) -> None:
        self.settings: Optional[Settings] = None
        self.provider: Optional[BaseLLMProvider] = None
        self.tool_registry: Optional[ToolRegistry] = None
        self.agent: Any = None  # VenuxAgent or stub
        self._initialized = False

    # ── Factory ──────────────────────────────────────────────────────────

    @classmethod
    async def create(
        cls,
        *,
        settings: Settings | None = None,
        model_override: str | None = None,
        skip_agent: bool = False,
    ) -> VenuxApp:
        """Create and fully initialise the application.

        Parameters
        ----------
        settings:
            Explicit settings; uses ``get_settings()`` when *None*.
        model_override:
            Override the model name from settings.
        skip_agent:
            If *True*, skip expensive agent/LLM initialisation (useful
            for CLI commands like ``config`` or ``doctor``).
        """
        app = cls()
        app.settings = settings or get_settings()

        if model_override:
            app.settings.llm.model = model_override

        # 1. Database
        logger.info("Initialising database …")
        await init_db(url=app.settings.db_url, echo=app.settings.database.echo)

        # 2. Tool registry
        logger.info("Loading tool registry …")
        app.tool_registry = ToolRegistry(include_defaults=True)

        # 3. LLM provider & agent
        if not skip_agent:
            app._init_provider()
            app._init_agent()

        app._initialized = True
        logger.info("VenuxApp ready (tools=%d)", len(app.tool_registry))
        return app

    # ── Internal init helpers ────────────────────────────────────────────

    def _init_provider(self) -> None:
        """Create the LLM provider from settings."""
        try:
            self.provider = create_provider(settings=self.settings)
            logger.info(
                "LLM provider: %s / %s",
                self.settings.llm.provider,
                self.settings.llm.model,
            )
        except Exception as exc:
            logger.warning("Could not create LLM provider: %s", exc)
            self.provider = None

    def _init_agent(self) -> None:
        """Create the LangGraph agent (or a fallback stub)."""
        if self.provider is None:
            self.agent = _AgentStub(model=self.settings.llm.model if self.settings else "stub")
            return

        try:
            from venux_code.llm.agent.agent import VenuxAgent

            # Build the LangChain model with tools bound
            lc_tools = self.tool_registry.as_langchain_tools() if self.tool_registry else []
            model = self.provider._build_model(tools=lc_tools or None)

            system_prompt = _DEFAULT_SYSTEM_PROMPT
            # Load memories into system prompt if available
            try:
                from venux_code.llm.prompts import build_coder_prompt
                system_prompt = build_coder_prompt()
            except Exception:
                pass

            self.agent = VenuxAgent(
                model=model,
                tools=lc_tools,
                system_prompt=system_prompt,
            )
            logger.info("VenuxAgent created with %d tools", len(lc_tools))
        except Exception as exc:
            logger.warning("Could not create VenuxAgent, using stub: %s", exc)
            self.agent = _AgentStub(model=self.settings.llm.model if self.settings else "stub")

    # ── Shutdown ─────────────────────────────────────────────────────────

    async def shutdown(self) -> None:
        """Clean up resources."""
        await dispose_engine()
        self._initialized = False
        logger.info("VenuxApp shut down")


# ── Fallback stub agent ──────────────────────────────────────────────────


@dataclass
class _AgentStub:
    """Used when the real agent cannot be created (missing API key, etc.)."""

    model: str = ""

    async def run(self, prompt: str, **kw: Any) -> str:
        return (
            f"[Venux Code stub] No LLM provider configured.\n\n"
            f"Your message was: {prompt!r}\n\n"
            f"Set VENUX_LLM__API_KEY or configure ~/.venux-code/config.yaml "
            f"to enable the AI agent."
        )

    async def stream(self, prompt: str, **kw: Any):  # type: ignore[type-arg]
        text = await self.run(prompt, **kw)
        # Yield word-by-word for a nice streaming effect
        for word in text.split(" "):
            yield word + " "


# ── Module-level singleton ───────────────────────────────────────────────

_app: Optional[VenuxApp] = None


async def get_app(**create_kwargs: Any) -> VenuxApp:
    """Return (and lazily create) the global ``VenuxApp`` singleton."""
    global _app
    if _app is None:
        _app = await VenuxApp.create(**create_kwargs)
    return _app


async def reset_app() -> None:
    """Shut down and clear the global singleton (useful in tests)."""
    global _app
    if _app is not None:
        await _app.shutdown()
        _app = None
