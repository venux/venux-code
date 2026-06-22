"""LSP diagnostics tool – fetch diagnostics from a language server for a file.

Spawns (or reuses) an LSP server, opens the file, collects diagnostics
pushed by the server, and returns them as structured output.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, ClassVar, Optional

from pydantic import BaseModel, Field

from venux_code.lsp.client import LSPClient, LSPClientError
from venux_code.lsp.config import LSPConfig, LSPServerConfig
from venux_code.lsp.models import Diagnostic

from .base import BaseTool, ToolResponse

logger = logging.getLogger(__name__)

# Module-level cache so a server process can be reused across calls.
_clients: dict[str, LSPClient] = {}


class DiagnosticsParams(BaseModel):
    """Parameters for the diagnostics tool."""

    file_path: str = Field(
        description="Absolute or relative path to the file to check.",
    )
    language: Optional[str] = Field(
        default=None,
        description="Language identifier (e.g. 'python'). Auto-detected from extension if omitted.",
    )
    timeout: float = Field(
        default=10.0,
        ge=1.0,
        le=60.0,
        description="Seconds to wait for the server to respond (default 10).",
    )


class DiagnosticsTool(BaseTool):
    """Retrieve LSP diagnostics (errors, warnings, hints) for a source file."""

    name = "diagnostics"
    description = (
        "Run an LSP language server against a file and return its diagnostics "
        "(errors, warnings, hints). Useful for catching type errors, unused "
        "imports, syntax problems, and other issues before the user runs tests."
    )
    parameters_schema = DiagnosticsParams
    requires_permission = False

    async def execute(self, params: dict[str, Any]) -> ToolResponse:
        validated = DiagnosticsParams(**params)
        file_path = Path(validated.file_path).resolve()

        if not file_path.is_file():
            return ToolResponse(success=False, error=f"File not found: {file_path}")

        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            return ToolResponse(success=False, error=f"Cannot read file: {exc}")

        # Resolve which LSP server to use.
        lsp_config = LSPConfig.from_settings()
        server_cfg = lsp_config.server_for_file(file_path)
        if server_cfg is None:
            ext = file_path.suffix.lstrip(".")
            return ToolResponse(
                success=False,
                error=(
                    f"No LSP server configured for '.{ext}' files. "
                    "Add a matching entry to 'lsp_servers' in your config."
                ),
            )

        try:
            diagnostics = await self._get_diagnostics(
                server_cfg=server_cfg,
                file_path=file_path,
                text=text,
                language_id=validated.language,
                timeout=validated.timeout,
            )
        except LSPClientError as exc:
            return ToolResponse(success=False, error=f"LSP error: {exc}")
        except Exception as exc:
            logger.exception("Unexpected error in diagnostics tool")
            return ToolResponse(success=False, error=f"Unexpected error: {exc}")

        if not diagnostics:
            return ToolResponse(
                success=True,
                output=f"No diagnostics for {file_path.name} – all clear!",
                metadata={"file": str(file_path), "diagnostic_count": 0},
            )

        uri = file_path.as_uri()
        lines = [d.format_for_display(uri) for d in diagnostics]
        summary = self._build_summary(diagnostics)
        output = f"{summary}\n\n" + "\n".join(lines)

        return ToolResponse(
            success=True,
            output=output,
            display_type="text",
            metadata={
                "file": str(file_path),
                "diagnostic_count": len(diagnostics),
                "errors": sum(1 for d in diagnostics if d.severity and d.severity.value == 1),
                "warnings": sum(1 for d in diagnostics if d.severity and d.severity.value == 2),
            },
        )

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    async def _get_diagnostics(
        server_cfg: LSPServerConfig,
        file_path: Path,
        text: str,
        language_id: Optional[str],
        timeout: float,
    ) -> list[Diagnostic]:
        """Get or create a client, initialize if needed, and collect diagnostics."""
        client = _clients.get(server_cfg.name)
        if client is None:
            client = LSPClient(server_cfg)
            await client.start()
            await client.initialize()
            _clients[server_cfg.name] = client

        return await client.get_diagnostics(
            file_path,
            text,
            language_id=language_id,
            timeout=timeout,
        )

    @staticmethod
    def _build_summary(diagnostics: list[Diagnostic]) -> str:
        """Build a one-line summary of diagnostic counts by severity."""
        counts: dict[str, int] = {}
        for d in diagnostics:
            label = d.severity_label
            counts[label] = counts.get(label, 0) + 1
        parts = [f"{count} {label}" + ("s" if count > 1 else "") for label, count in counts.items()]
        return "Found " + ", ".join(parts) + "."
