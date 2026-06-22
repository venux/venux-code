"""LSP server configuration loader.

Reads ``lsp_servers`` from the application settings (JSON / YAML config)
and exposes typed ``LSPServerConfig`` instances.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


class LSPServerConfig(BaseModel):
    """Configuration for a single LSP server."""

    name: str = Field(description="Unique identifier for this server.")
    command: str = Field(description="Executable to spawn (e.g. 'pyright-langserver').")
    args: list[str] = Field(default_factory=lambda: ["--stdio"], description="CLI arguments.")
    languages: list[str] = Field(
        default_factory=list,
        description="File extensions (without dot) this server handles, e.g. ['py'].",
    )
    initialization_options: dict[str, Any] = Field(
        default_factory=dict,
        description="Passed as initializationOptions during LSP initialize.",
    )
    root_uri: Optional[str] = Field(
        default=None,
        description="Workspace root URI. Defaults to CWD if unset.",
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Extra environment variables for the spawned process.",
    )


class LSPConfig:
    """Convenience wrapper that resolves the correct server for a file."""

    def __init__(self, servers: list[LSPServerConfig]) -> None:
        self._servers = servers
        self._by_lang: dict[str, list[LSPServerConfig]] = {}
        for srv in servers:
            for lang in srv.languages:
                self._by_lang.setdefault(lang, []).append(srv)

    @classmethod
    def from_settings(cls, settings: Any | None = None) -> "LSPConfig":
        """Build an ``LSPConfig`` from application settings.

        Expects ``settings.lsp_servers`` to be a list of dicts.
        Falls back to an empty list if the attribute is absent.
        """
        if settings is None:
            try:
                from venux_code.config.settings import get_settings

                settings = get_settings()
            except Exception:
                return cls([])

        raw: list[dict[str, Any]] = getattr(settings, "lsp_servers", [])
        servers = [LSPServerConfig(**entry) for entry in raw]
        return cls(servers)

    @property
    def servers(self) -> list[LSPServerConfig]:
        return list(self._servers)

    def server_for_file(self, file_path: str | Path) -> Optional[LSPServerConfig]:
        """Return the first server whose languages match the file extension."""
        ext = Path(file_path).suffix.lstrip(".")
        candidates = self._by_lang.get(ext, [])
        return candidates[0] if candidates else None
