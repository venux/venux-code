"""Application bootstrap for Venux Code.

Initialises configuration, database, agent, and TUI — and exposes thin
helpers used by the CLI commands (doctor, config, sessions, etc.).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

@dataclass
class VenuxConfig:
    """Runtime configuration for Venux Code."""

    model: str = "anthropic/claude-sonnet-4-20250514"
    api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///venux_code.db"
    max_tokens: int = 4096
    stream: bool = True
    theme: str = "dark"
    config_path: Path = field(default_factory=lambda: Path.home() / ".venux-code" / "config.toml")
    sessions_dir: Path = field(default_factory=lambda: Path.home() / ".venux-code" / "sessions")

    # Serialise to a plain dict for the `config` CLI command
    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "api_key": "***" if self.api_key else "(not set)",
            "database_url": self.database_url,
            "max_tokens": self.max_tokens,
            "stream": self.stream,
            "theme": self.theme,
            "config_path": str(self.config_path),
            "sessions_dir": str(self.sessions_dir),
        }


def _load_toml_config(path: Path) -> dict[str, Any]:
    """Best-effort TOML loader (stdlib 3.11+)."""
    if not path.exists():
        return {}
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def get_config() -> VenuxConfig:
    """Build the merged configuration (defaults → file → env)."""
    import os

    cfg = VenuxConfig()
    file_cfg = _load_toml_config(cfg.config_path)

    # File overrides
    if "model" in file_cfg:
        cfg.model = file_cfg["model"]
    if "database_url" in file_cfg:
        cfg.database_url = file_cfg["database_url"]
    if "max_tokens" in file_cfg:
        cfg.max_tokens = int(file_cfg["max_tokens"])
    if "theme" in file_cfg:
        cfg.theme = file_cfg["theme"]

    # Env overrides
    cfg.api_key = os.environ.get("VENUX_API_KEY", file_cfg.get("api_key", ""))  # type: ignore[assignment]
    cfg.model = os.environ.get("VENUX_MODEL", cfg.model)

    return cfg


def load_config() -> dict[str, Any]:
    """Public helper used by CLI `config` command."""
    return get_config().to_dict()


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

async def check_database() -> None:
    """Verify the database is reachable. Raises on failure."""
    cfg = get_config()
    try:
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(cfg.database_url)
        async with engine.connect():
            pass
        await engine.dispose()
    except Exception as exc:
        raise RuntimeError(f"Database check failed: {exc}") from exc


async def load_sessions(limit: int = 20) -> list[dict[str, Any]]:
    """Return recent sessions from the database."""
    cfg = get_config()
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(cfg.database_url)
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT id, title, created_at, "
                    "(SELECT COUNT(*) FROM messages WHERE messages.session_id = sessions.id) AS message_count "
                    "FROM sessions ORDER BY created_at DESC LIMIT :lim"
                ),
                {"lim": limit},
            )
            rows = result.fetchall()
        await engine.dispose()
        return [
            {"id": r[0], "title": r[1], "created_at": str(r[2]), "message_count": r[3]}
            for r in rows
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# LLM connectivity check
# ---------------------------------------------------------------------------

async def check_llm() -> None:
    """Try a lightweight LLM call to verify connectivity."""
    cfg = get_config()
    if not cfg.api_key:
        raise RuntimeError("No API key configured (set VENUX_API_KEY or config file)")

    # Attempt a minimal completion
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://api.anthropic.com/v1/models", headers={"x-api-key": cfg.api_key, "anthropic-version": "2023-06-01"})
            if resp.status_code >= 400:
                raise RuntimeError(f"API returned {resp.status_code}")
    except httpx.ConnectError as exc:
        raise RuntimeError(f"Cannot reach LLM API: {exc}") from exc


# ---------------------------------------------------------------------------
# Agent bootstrap  (now uses VenuxApp)
# ---------------------------------------------------------------------------


async def bootstrap_agent(
    model: str | None = None,
    session_id: str | None = None,
) -> tuple[Any, Any]:
    """Create an agent instance backed by the real ``VenuxApp``.

    Returns ``(agent, session_stub)`` where *agent* has ``.run()`` and
    ``.stream()`` methods compatible with the TUI and CLI.
    """
    from venux_code.app import VenuxApp

    app = await VenuxApp.create(model_override=model)

    # Minimal session stub until full session management is wired in
    @dataclass
    class _Session:
        id: str = session_id or "default"
        async def close(self) -> None:
            await app.shutdown()

    return app.agent, _Session()


async def bootstrap_and_run_tui() -> None:
    """Wire everything together and launch the Textual TUI."""
    from venux_code.app import VenuxApp

    app = await VenuxApp.create()
    agent = app.agent
    cfg = get_config()

    # Wrap session for the TUI interface
    @dataclass
    class _Session:
        id: str = "default"
        async def close(self) -> None:
            await app.shutdown()

    from venux_code.tui.app import VenuxTUI  # local import to avoid heavy deps at CLI parse time

    tui = VenuxTUI(agent=agent, session=_Session(), config=cfg)
    await tui.run_async()
