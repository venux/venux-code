"""Tests for CLI commands using Typer's CliRunner."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from venux_code.cli.main import app

runner = CliRunner()


class TestVersionCommand:
    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "venux-code" in result.output.lower()

    def test_version_subcommand(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "venux-code" in result.output.lower()


class TestConfigCommand:
    @patch("venux_code.cli.app.load_config")
    @patch("venux_code.config.settings.get_settings")
    def test_config_output(self, mock_get_settings, mock_load_config):
        mock_load_config.return_value = {
            "theme": "dark",
            "editor": "vim",
        }
        mock_settings = MagicMock()
        mock_settings.llm.provider = "openai"
        mock_settings.llm.model = "gpt-4o"
        mock_settings.db_url = "sqlite:///test.db"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.debug = False
        mock_get_settings.return_value = mock_settings

        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0


class TestDoctorCommand:
    @patch("venux_code.cli.app.check_llm", new_callable=AsyncMock)
    @patch("venux_code.cli.app.check_database", new_callable=AsyncMock)
    @patch("venux_code.cli.app.load_config")
    @patch("venux_code.config.settings.get_settings")
    @patch("venux_code.db.engine.init_db", new_callable=AsyncMock)
    @patch("venux_code.llm.tools.registry.ToolRegistry")
    @patch("venux_code.llm.providers.registry.create_provider")
    def test_doctor_runs(
        self,
        mock_create_provider,
        mock_tool_registry,
        mock_init_db,
        mock_get_settings,
        mock_load_config,
        mock_check_db,
        mock_check_llm,
    ):
        mock_load_config.return_value = {"test": "config"}
        mock_settings = MagicMock()
        mock_settings.llm.provider = "openai"
        mock_settings.llm.model = "gpt-4o"
        mock_get_settings.return_value = mock_settings

        mock_registry = MagicMock()
        mock_registry.list_names.return_value = ["bash", "view", "edit"]
        mock_tool_registry.return_value = mock_registry

        mock_provider = MagicMock()
        mock_provider.model_info.return_value = MagicMock(
            provider="openai", name="gpt-4o"
        )
        mock_create_provider.return_value = mock_provider

        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0


class TestSessionsListCommand:
    @patch("venux_code.cli.app.load_sessions", new_callable=AsyncMock)
    def test_sessions_list_empty(self, mock_load_sessions):
        mock_load_sessions.return_value = []
        result = runner.invoke(app, ["sessions", "list"])
        assert result.exit_code == 0

    @patch("venux_code.cli.app.load_sessions", new_callable=AsyncMock)
    def test_sessions_list_with_data(self, mock_load_sessions):
        mock_load_sessions.return_value = [
            {
                "id": "abc123",
                "title": "Test Session",
                "created_at": "2025-01-01",
                "message_count": 5,
            },
        ]
        result = runner.invoke(app, ["sessions", "list"])
        assert result.exit_code == 0
