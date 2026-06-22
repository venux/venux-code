"""Tests for LSP models, config, client, and diagnostics tool."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venux_code.lsp.models import (
    Diagnostic,
    DiagnosticSeverity,
    Position,
    Range,
)
from venux_code.lsp.config import LSPConfig, LSPServerConfig


# ── LSP Models ────────────────────────────────────────────────────────────


class TestPosition:
    def test_create_position(self):
        pos = Position(line=5, character=10)
        assert pos.line == 5
        assert pos.character == 10

    def test_position_defaults(self):
        pos = Position(line=0, character=0)
        assert pos.line == 0
        assert pos.character == 0

    def test_position_validation_negative_line(self):
        with pytest.raises(Exception):
            Position(line=-1, character=0)

    def test_position_validation_negative_character(self):
        with pytest.raises(Exception):
            Position(line=0, character=-1)


class TestRange:
    def test_create_range(self):
        r = Range(
            start=Position(line=1, character=0),
            end=Position(line=1, character=10),
        )
        assert r.start.line == 1
        assert r.end.character == 10

    def test_range_single_line(self):
        r = Range(
            start=Position(line=0, character=5),
            end=Position(line=0, character=15),
        )
        assert r.start.line == r.end.line


class TestDiagnosticSeverity:
    def test_values(self):
        assert DiagnosticSeverity.ERROR == 1
        assert DiagnosticSeverity.WARNING == 2
        assert DiagnosticSeverity.INFORMATION == 3
        assert DiagnosticSeverity.HINT == 4

    def test_is_int(self):
        assert isinstance(DiagnosticSeverity.ERROR, int)


class TestDiagnostic:
    def _make_diag(self, severity=None, code=None, source=None, message="test"):
        return Diagnostic(
            range=Range(
                start=Position(line=0, character=0),
                end=Position(line=0, character=5),
            ),
            severity=severity,
            code=code,
            source=source,
            message=message,
        )

    def test_severity_label_error(self):
        d = self._make_diag(severity=DiagnosticSeverity.ERROR)
        assert d.severity_label == "error"

    def test_severity_label_warning(self):
        d = self._make_diag(severity=DiagnosticSeverity.WARNING)
        assert d.severity_label == "warning"

    def test_severity_label_info(self):
        d = self._make_diag(severity=DiagnosticSeverity.INFORMATION)
        assert d.severity_label == "info"

    def test_severity_label_hint(self):
        d = self._make_diag(severity=DiagnosticSeverity.HINT)
        assert d.severity_label == "hint"

    def test_severity_label_none(self):
        d = self._make_diag(severity=None)
        assert d.severity_label == "unknown"

    def test_format_for_display_basic(self):
        d = self._make_diag(
            severity=DiagnosticSeverity.ERROR, message="undefined var"
        )
        result = d.format_for_display()
        assert "1:1" in result  # line+1:char+1
        assert "error" in result
        assert "undefined var" in result

    def test_format_for_display_with_source(self):
        d = self._make_diag(
            severity=DiagnosticSeverity.WARNING,
            source="pyright",
            message="unused import",
        )
        result = d.format_for_display()
        assert "[pyright]" in result

    def test_format_for_display_with_code(self):
        d = self._make_diag(
            severity=DiagnosticSeverity.ERROR,
            code="reportUndefinedVariable",
            message="bad",
        )
        result = d.format_for_display()
        assert "(reportUndefinedVariable)" in result

    def test_format_for_display_with_file_uri(self):
        d = self._make_diag(message="err")
        result = d.format_for_display("file:///home/user/test.py")
        assert "test.py:" in result

    def test_format_for_display_no_severity(self):
        d = self._make_diag(severity=None, message="unknown issue")
        result = d.format_for_display()
        assert "unknown" in result

    def test_defaults(self):
        d = Diagnostic(
            range=Range(
                start=Position(line=0, character=0),
                end=Position(line=0, character=1),
            ),
            message="minimal",
        )
        assert d.severity is None
        assert d.code is None
        assert d.source is None
        assert d.tags == []
        assert d.related_information == []


# ── LSP Config ────────────────────────────────────────────────────────────


class TestLSPServerConfig:
    def test_defaults(self):
        cfg = LSPServerConfig(name="pyright", command="pyright-langserver")
        assert cfg.args == ["--stdio"]
        assert cfg.languages == []
        assert cfg.initialization_options == {}
        assert cfg.root_uri is None
        assert cfg.env == {}

    def test_custom_values(self):
        cfg = LSPServerConfig(
            name="ts-server",
            command="typescript-language-server",
            args=["--stdio", "--verbose"],
            languages=["ts", "tsx"],
            initialization_options={"disableAutomaticTypingAcquisition": True},
        )
        assert len(cfg.args) == 2
        assert "ts" in cfg.languages
        assert "tsx" in cfg.languages


class TestLSPConfig:
    def test_from_settings_none(self):
        """from_settings with None and no get_settings returns empty."""
        with patch("venux_code.lsp.config.LSPConfig.__init__", return_value=None) as mock_init:
            pass
        # Test that from_settings returns empty config when settings has no lsp_servers
        settings = SimpleNamespace()  # no lsp_servers attr
        config = LSPConfig.from_settings(settings)
        assert config.servers == []

    def test_from_settings_with_servers(self):
        settings = SimpleNamespace(
            lsp_servers=[
                {"name": "pyright", "command": "pyright-langserver", "languages": ["py"]},
                {"name": "ts", "command": "tsserver", "languages": ["ts"]},
            ]
        )
        config = LSPConfig.from_settings(settings)
        assert len(config.servers) == 2

    def test_server_for_file_match(self):
        servers = [
            LSPServerConfig(name="pyright", command="pyright", languages=["py"]),
            LSPServerConfig(name="ts", command="tsserver", languages=["ts", "tsx"]),
        ]
        config = LSPConfig(servers)
        result = config.server_for_file("main.py")
        assert result is not None
        assert result.name == "pyright"

    def test_server_for_file_tsx(self):
        servers = [
            LSPServerConfig(name="ts", command="tsserver", languages=["ts", "tsx"]),
        ]
        config = LSPConfig(servers)
        result = config.server_for_file("/path/to/App.tsx")
        assert result is not None
        assert result.name == "ts"

    def test_server_for_file_no_match(self):
        servers = [
            LSPServerConfig(name="pyright", command="pyright", languages=["py"]),
        ]
        config = LSPConfig(servers)
        result = config.server_for_file("style.css")
        assert result is None

    def test_servers_property_returns_copy(self):
        servers = [
            LSPServerConfig(name="pyright", command="pyright", languages=["py"]),
        ]
        config = LSPConfig(servers)
        result = config.servers
        result.append(LSPServerConfig(name="extra", command="extra"))
        assert len(config.servers) == 1


# ── LSP Client ────────────────────────────────────────────────────────────


class TestLSPClientMessageFraming:
    @pytest.mark.asyncio
    async def test_write_message_format(self):
        """Verify _write_message produces Content-Length header framing."""
        from venux_code.lsp.client import LSPClient

        config = LSPServerConfig(name="test", command="test")
        client = LSPClient(config)

        # Mock process stdin
        mock_stdin = AsyncMock()
        mock_process = MagicMock()
        mock_process.stdin = mock_stdin
        client._process = mock_process

        message = {"jsonrpc": "2.0", "method": "test", "params": {}}
        await client._write_message(message)

        # Verify write was called
        mock_stdin.write.assert_called_once()
        mock_stdin.drain.assert_called_once()

        written = mock_stdin.write.call_args[0][0]
        decoded = written.decode()

        # Must have Content-Length header
        assert decoded.startswith("Content-Length: ")
        # Must have double CRLF separator
        assert "\r\n\r\n" in decoded

        # Extract body and verify
        header, body = decoded.split("\r\n\r\n", 1)
        content_length = int(header.split(": ")[1])
        assert content_length == len(body)

        # Body must be valid JSON matching the message
        parsed = json.loads(body)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["method"] == "test"

    @pytest.mark.asyncio
    async def test_write_message_no_process(self):
        from venux_code.lsp.client import LSPClient, LSPClientError

        config = LSPServerConfig(name="test", command="test")
        client = LSPClient(config)
        client._process = None

        with pytest.raises(LSPClientError, match="not running"):
            await client._write_message({"test": True})

    @pytest.mark.asyncio
    async def test_send_notification_no_params(self):
        """Notifications without params should omit the params field."""
        from venux_code.lsp.client import LSPClient

        config = LSPServerConfig(name="test", command="test")
        client = LSPClient(config)

        mock_stdin = AsyncMock()
        mock_process = MagicMock()
        mock_process.stdin = mock_stdin
        client._process = mock_process

        await client._send_notification("exit", None)

        written = mock_stdin.write.call_args[0][0].decode()
        _, body = written.split("\r\n\r\n", 1)
        parsed = json.loads(body)
        assert "params" not in parsed
        assert parsed["method"] == "exit"


class TestLSPClientDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_response_resolves_future(self):
        from venux_code.lsp.client import LSPClient

        config = LSPServerConfig(name="test", command="test")
        client = LSPClient(config)

        future = asyncio.get_running_loop().create_future()
        client._pending[1] = future

        client._dispatch_message({"id": 1, "result": {"capabilities": {}}})
        assert future.done()
        assert future.result() == {"capabilities": {}}

    @pytest.mark.asyncio
    async def test_dispatch_response_error(self):
        from venux_code.lsp.client import LSPClient, LSPClientError

        config = LSPServerConfig(name="test", command="test")
        client = LSPClient(config)

        future = asyncio.get_running_loop().create_future()
        client._pending[1] = future

        client._dispatch_message({
            "id": 1,
            "error": {"code": -32600, "message": "Invalid Request"},
        })
        assert future.done()
        with pytest.raises(LSPClientError):
            future.result()

    def test_dispatch_publish_diagnostics(self):
        from venux_code.lsp.client import LSPClient

        config = LSPServerConfig(name="test", command="test")
        client = LSPClient(config)

        client._dispatch_message({
            "method": "textDocument/publishDiagnostics",
            "params": {
                "uri": "file:///test.py",
                "diagnostics": [
                    {
                        "range": {
                            "start": {"line": 0, "character": 0},
                            "end": {"line": 0, "character": 5},
                        },
                        "message": "error here",
                        "severity": 1,
                    }
                ],
            },
        })

        assert "file:///test.py" in client._diagnostics
        assert len(client._diagnostics["file:///test.py"]) == 1
        assert client._diagnostics["file:///test.py"][0].message == "error here"


class TestLSPClientGuessLanguage:
    def test_python(self):
        from venux_code.lsp.client import LSPClient

        assert LSPClient._guess_language("main.py") == "python"

    def test_typescript(self):
        from venux_code.lsp.client import LSPClient

        assert LSPClient._guess_language("app.ts") == "typescript"

    def test_unknown_extension(self):
        from venux_code.lsp.client import LSPClient

        assert LSPClient._guess_language("file.xyz") == "xyz"


# ── Diagnostics Tool ──────────────────────────────────────────────────────


class TestDiagnosticsTool:
    def test_name(self):
        from venux_code.llm.tools.diagnostics_tool import DiagnosticsTool

        assert DiagnosticsTool.name == "diagnostics"

    def test_description(self):
        from venux_code.llm.tools.diagnostics_tool import DiagnosticsTool

        assert "diagnostics" in DiagnosticsTool.description.lower()

    def test_requires_permission_false(self):
        from venux_code.llm.tools.diagnostics_tool import DiagnosticsTool

        assert DiagnosticsTool.requires_permission is False

    @pytest.mark.asyncio
    async def test_execute_file_not_found(self):
        from venux_code.llm.tools.diagnostics_tool import DiagnosticsTool

        tool = DiagnosticsTool()
        result = await tool.execute({"file_path": "/nonexistent/file.py"})
        assert result.success is False
        assert result.error is not None and "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_no_server_configured(self, tmp_path):
        from venux_code.llm.tools.diagnostics_tool import DiagnosticsTool

        test_file = tmp_path / "test.xyz"
        test_file.write_text("content")

        with patch(
            "venux_code.llm.tools.diagnostics_tool.LSPConfig.from_settings",
            return_value=LSPConfig([]),
        ):
            tool = DiagnosticsTool()
            result = await tool.execute({"file_path": str(test_file)})
            assert result.success is False
            assert result.error is not None and "No LSP server" in result.error

    def test_build_summary(self):
        from venux_code.llm.tools.diagnostics_tool import DiagnosticsTool

        diagnostics = [
            Diagnostic(
                range=Range(
                    start=Position(line=0, character=0),
                    end=Position(line=0, character=5),
                ),
                severity=DiagnosticSeverity.ERROR,
                message="err1",
            ),
            Diagnostic(
                range=Range(
                    start=Position(line=1, character=0),
                    end=Position(line=1, character=5),
                ),
                severity=DiagnosticSeverity.ERROR,
                message="err2",
            ),
            Diagnostic(
                range=Range(
                    start=Position(line=2, character=0),
                    end=Position(line=2, character=5),
                ),
                severity=DiagnosticSeverity.WARNING,
                message="warn1",
            ),
        ]
        summary = DiagnosticsTool._build_summary(diagnostics)
        assert "2 errors" in summary
        assert "1 warning" in summary
