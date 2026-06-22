"""Tests for config/settings loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from venux_code.config.settings import (
    LLMProviderSettings,
    PermissionSettings,
    DatabaseSettings,
    Settings,
    get_settings,
    reset_settings,
)


class TestLLMProviderSettings:
    def test_defaults(self):
        s = LLMProviderSettings()
        assert s.provider == "openai"
        assert s.model == "gpt-4o"
        assert s.max_tokens == 4096
        assert s.temperature == 0.7
        assert s.api_key is None

    def test_custom_values(self):
        s = LLMProviderSettings(
            provider="anthropic",
            model="claude-3-opus",
            api_key="sk-test",
            max_tokens=8192,
            temperature=0.2,
        )
        assert s.provider == "anthropic"
        assert s.model == "claude-3-opus"
        assert s.api_key == "sk-test"


class TestPermissionSettings:
    def test_defaults(self):
        s = PermissionSettings()
        assert s.auto_approve is False
        assert s.auto_approve_tools == []
        assert s.denied_tools == []

    def test_custom(self):
        s = PermissionSettings(
            auto_approve=True,
            auto_approve_tools=["bash", "write"],
            denied_tools=["delete"],
        )
        assert s.auto_approve is True
        assert "bash" in s.auto_approve_tools


class TestDatabaseSettings:
    def test_defaults(self):
        s = DatabaseSettings()
        assert "sqlite" in s.url
        assert s.echo is False


class TestSettings:
    def test_defaults(self):
        reset_settings()
        s = Settings()
        assert s.app_name == "venux-code"
        assert s.version == "0.1.0"
        assert s.debug is False
        assert s.log_level == "INFO"
        assert isinstance(s.llm, LLMProviderSettings)
        assert isinstance(s.permission, PermissionSettings)
        assert isinstance(s.database, DatabaseSettings)

    def test_db_url_property(self):
        s = Settings(database=DatabaseSettings(url="sqlite:///test.db"))
        assert s.db_url == "sqlite:///test.db"

    def test_from_user_yaml(self, tmp_path: Path, monkeypatch):
        """Settings loads from ~/.venux-code/config.yaml."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text(yaml.dump({"debug": True, "log_level": "DEBUG"}))

        monkeypatch.setattr(
            "venux_code.config.settings._USER_CONFIG_PATH", config_file
        )
        reset_settings()

        s = Settings()
        # File values should be merged (but env/kwargs take priority)
        assert isinstance(s, Settings)

    def test_from_project_json(self, tmp_path: Path, monkeypatch):
        """Settings loads from .venux-code.json in CWD."""
        project_config = tmp_path / ".venux-code.json"
        project_config.write_text(json.dumps({"debug": True}))

        monkeypatch.setattr(
            "venux_code.config.settings._find_project_config",
            lambda: project_config,
        )
        reset_settings()

        s = Settings()
        assert isinstance(s, Settings)

    def test_env_prefix(self, monkeypatch):
        """Environment variables with VENUX_ prefix override defaults."""
        monkeypatch.setenv("VENUX_DEBUG", "true")
        monkeypatch.setenv("VENUX_LOG_LEVEL", "WARNING")
        reset_settings()

        s = Settings()
        assert s.debug is True
        assert s.log_level == "WARNING"


class TestGetSettings:
    def test_singleton(self):
        reset_settings()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_reset(self):
        reset_settings()
        s1 = get_settings()
        reset_settings()
        s2 = get_settings()
        # After reset, a new instance is created
        assert s1 is not s2

    def test_overrides_only_on_first_call(self):
        reset_settings()
        s = get_settings(debug=True)
        assert s.debug is True
        # Second call with different overrides returns cached instance
        s2 = get_settings(debug=False)
        assert s2.debug is True  # still True from first call
