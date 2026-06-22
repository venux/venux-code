"""Application settings with layered configuration loading.

Priority (highest wins):
  1. Environment variables (prefix VENUX_)
  2. Project config (.venux-code.json in CWD or parents)
  3. User config (~/.venux-code/config.yaml)
  4. Defaults defined here
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_USER_CONFIG_DIR = Path.home() / ".venux-code"
_USER_CONFIG_PATH = _USER_CONFIG_DIR / "config.yaml"
_PROJECT_CONFIG_NAME = ".venux-code.json"


def _find_project_config() -> Optional[Path]:
    """Walk up from CWD to find .venux-code.json."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        candidate = parent / _PROJECT_CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dict."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file and return its contents as a dict."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


class LLMProviderSettings(BaseSettings):
    """Configuration for a single LLM provider."""

    model_config = SettingsConfigDict(extra="allow")

    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.7


class PermissionSettings(BaseSettings):
    """Permission system configuration."""

    auto_approve: bool = False
    auto_approve_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    url: str = "sqlite+aiosqlite:///./venux-code.db"
    echo: bool = False


class Settings(BaseSettings):
    """Root application settings.

    Loaded from (in priority order):
      - env vars with VENUX_ prefix
      - .venux-code.json project config
      - ~/.venux-code/config.yaml user config
      - field defaults
    """

    model_config = SettingsConfigDict(
        env_prefix="VENUX_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # ── General ────────────────────────────────────────────────────────────
    app_name: str = "venux-code"
    version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    # ── Paths ──────────────────────────────────────────────────────────────
    data_dir: Path = Field(default_factory=lambda: _USER_CONFIG_DIR / "data")
    session_dir: Path = Field(default_factory=lambda: _USER_CONFIG_DIR / "sessions")

    # ── Sub-sections ───────────────────────────────────────────────────────
    llm: LLMProviderSettings = Field(default_factory=LLMProviderSettings)
    permission: PermissionSettings = Field(default_factory=PermissionSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)

    # ── Convenience ────────────────────────────────────────────────────────
    @property
    def db_url(self) -> str:
        """Shortcut to database URL."""
        return self.database.url

    # ── Layered loading ────────────────────────────────────────────────────
    @model_validator(mode="before")
    @classmethod
    def _merge_config_sources(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Merge user YAML, project JSON, then env overrides.

        Pydantic-settings already handled env vars before this validator
        runs, so we merge the file sources *underneath* the env values.
        """
        merged: dict[str, Any] = {}

        # Layer 1: user config YAML
        if _USER_CONFIG_PATH.is_file():
            merged.update(_load_yaml(_USER_CONFIG_PATH))

        # Layer 2: project config JSON
        project_cfg = _find_project_config()
        if project_cfg is not None:
            merged.update(_load_json(project_cfg))

        # Layer 3: values already set by env vars / explicit kwargs
        merged.update(values)

        return merged


# ── Singleton ──────────────────────────────────────────────────────────────

_settings: Optional[Settings] = None


def get_settings(**overrides: Any) -> Settings:
    """Return the cached ``Settings`` instance, creating it on first call.

    Parameters
    ----------
    **overrides:
        Keyword arguments forwarded to ``Settings(**overrides)`` on first
        creation.  Ignored on subsequent calls.
    """
    global _settings
    if _settings is None:
        _settings = Settings(**overrides)
    return _settings


def reset_settings() -> None:
    """Clear the cached settings (useful in tests)."""
    global _settings
    _settings = None
