"""Async LSP client that communicates with a language server over stdin/stdout.

Implements the base LSP protocol (Content-Length header framing) and exposes
high-level helpers for the operations Venux Code needs:

* ``initialize`` / ``shutdown`` – lifecycle
* ``open_file`` / ``close_file`` / ``did_change`` – document sync
* ``get_diagnostics`` – pull diagnostics for a file
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from .config import LSPServerConfig
from .models import Diagnostic

logger = logging.getLogger(__name__)


class LSPClientError(Exception):
    """Raised when the LSP client encounters a protocol or server error."""


class LSPClient:
    """Async LSP client over stdin/stdout (Content-Length framing)."""

    def __init__(self, config: LSPServerConfig) -> None:
        self._config = config
        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id: int = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._diagnostics: dict[str, list[Diagnostic]] = {}
        self._reader_task: Optional[asyncio.Task[None]] = None
        self._initialized: bool = False
        self._shutdown: bool = False

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Spawn the language-server process."""
        env = {**os.environ, **self._config.env}
        logger.info("Starting LSP server: %s %s", self._config.command, self._config.args)
        self._process = await asyncio.create_subprocess_exec(
            self._config.command,
            *self._config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._reader_task = asyncio.create_task(self._read_loop())

    async def initialize(self, root_uri: Optional[str] = None) -> dict[str, Any]:
        """Send the ``initialize`` request and wait for the response."""
        root = root_uri or self._config.root_uri or Path.cwd().as_uri()
        params: dict[str, Any] = {
            "processId": os.getpid(),
            "rootUri": root,
            "capabilities": {
                "textDocument": {
                    "synchronization": {
                        "didOpen": True,
                        "didClose": True,
                        "didChange": True,
                        "willSave": False,
                        "willSaveWaitUntil": False,
                        "save": False,
                    },
                    "publishDiagnostics": {},
                },
                "workspace": {"workspaceFolders": False},
            },
            "initializationOptions": self._config.initialization_options,
        }
        result = await self._send_request("initialize", params)
        self._initialized = True
        # Notify server that initialization is complete.
        await self._send_notification("initialized", {})
        return result

    async def shutdown(self) -> None:
        """Send ``shutdown`` request and ``exit`` notification."""
        if self._shutdown:
            return
        self._shutdown = True
        try:
            await self._send_request("shutdown", None)
            await self._send_notification("exit", None)
        except Exception:
            logger.debug("Error during shutdown", exc_info=True)
        finally:
            if self._process and self._process.stdin:
                self._process.stdin.close()
            if self._reader_task:
                self._reader_task.cancel()
            if self._process:
                try:
                    self._process.terminate()
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except (ProcessLookupError, asyncio.TimeoutError):
                    if self._process:
                        self._process.kill()

    # ── Document sync ────────────────────────────────────────────────────

    async def open_file(
        self,
        file_path: str | Path,
        text: str,
        language_id: Optional[str] = None,
    ) -> None:
        """Notify the server that a document has been opened."""
        uri = Path(file_path).resolve().as_uri()
        lang = language_id or self._guess_language(file_path)
        await self._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": lang,
                "version": 1,
                "text": text,
            },
        })

    async def close_file(self, file_path: str | Path) -> None:
        """Notify the server that a document has been closed."""
        uri = Path(file_path).resolve().as_uri()
        await self._send_notification("textDocument/didClose", {
            "textDocument": {"uri": uri},
        })

    async def did_change(
        self,
        file_path: str | Path,
        full_text: str,
        version: int = 1,
    ) -> None:
        """Send a ``didChange`` notification with full-text sync."""
        uri = Path(file_path).resolve().as_uri()
        await self._send_notification("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": version},
            "contentChanges": [{"text": full_text}],
        })

    async def get_diagnostics(
        self,
        file_path: str | Path,
        text: str,
        *,
        language_id: Optional[str] = None,
        timeout: float = 10.0,
    ) -> list[Diagnostic]:
        """Open the file, wait for diagnostics, then close it.

        This is a convenience wrapper that handles the full
        open → wait → collect → close cycle.
        """
        if not self._initialized:
            raise LSPClientError("Client not initialized; call initialize() first.")

        uri = Path(file_path).resolve().as_uri()
        # Clear any stale diagnostics for this file.
        self._diagnostics.pop(uri, None)

        await self.open_file(file_path, text, language_id)

        # Wait for the server to push diagnostics via textDocument/publishDiagnostics.
        try:
            await asyncio.wait_for(self._wait_for_diagnostics(uri), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Timed out waiting for diagnostics from %s", self._config.name)
        finally:
            await self.close_file(file_path)

        return self._diagnostics.get(uri, [])

    # ── Internals ────────────────────────────────────────────────────────

    async def _send_request(self, method: str, params: Any) -> dict[str, Any]:
        """Send a JSON-RPC request and return the ``result`` field."""
        self._request_id += 1
        msg_id = self._request_id
        message = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            message["params"] = params

        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future
        await self._write_message(message)
        return await future

    async def _send_notification(self, method: str, params: Any) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        await self._write_message(message)

    async def _write_message(self, message: dict[str, Any]) -> None:
        """Encode *message* as JSON and write it with a Content-Length header."""
        if not self._process or not self._process.stdin:
            raise LSPClientError("LSP process is not running.")
        body = json.dumps(message)
        payload = f"Content-Length: {len(body)}\r\n\r\n{body}".encode()
        self._process.stdin.write(payload)
        await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        """Read messages from the server's stdout and dispatch them."""
        assert self._process and self._process.stdout
        reader = self._process.stdout
        while True:
            # Read headers.
            content_length = await self._read_headers(reader)
            if content_length is None:
                break
            body = await reader.readexactly(content_length)
            message = json.loads(body)
            self._dispatch_message(message)

    async def _read_headers(self, reader: asyncio.StreamReader) -> int | None:
        """Parse headers and return the Content-Length value."""
        while True:
            line = await reader.readline()
            if not line:
                return None  # EOF
            line_str = line.decode("ascii").strip()
            if line_str == "":
                break  # End of headers – but we need Content-Length first.
            if line_str.lower().startswith("content-length:"):
                return int(line_str.split(":", 1)[1].strip())
        # If we hit the blank line without finding Content-Length, keep reading.
        return None

    def _dispatch_message(self, message: dict[str, Any]) -> None:
        """Route an incoming message to the correct handler."""
        if "id" in message and "method" not in message:
            # It's a response to one of our requests.
            msg_id = message["id"]
            future = self._pending.pop(msg_id, None)
            if future and not future.done():
                if "error" in message:
                    future.set_exception(
                        LSPClientError(json.dumps(message["error"]))
                    )
                else:
                    future.set_result(message.get("result", {}))
        elif "method" in message:
            method = message["method"]
            params = message.get("params", {})
            if method == "textDocument/publishDiagnostics":
                self._handle_publish_diagnostics(params)

    def _handle_publish_diagnostics(self, params: dict[str, Any]) -> None:
        """Store diagnostics pushed by the server."""
        uri: str = params.get("uri", "")
        raw_diags: list[dict[str, Any]] = params.get("diagnostics", [])
        self._diagnostics[uri] = [Diagnostic(**d) for d in raw_diags]
        logger.debug("Received %d diagnostics for %s", len(raw_diags), uri)

    async def _wait_for_diagnostics(self, uri: str) -> None:
        """Block until diagnostics for *uri* have been received."""
        while uri not in self._diagnostics:
            await asyncio.sleep(0.05)

    @staticmethod
    def _guess_language(file_path: str | Path) -> str:
        """Best-effort language-id guess from the file extension."""
        ext = Path(file_path).suffix.lstrip(".")
        return {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "jsx": "javascriptreact",
            "tsx": "typescriptreact",
            "go": "go",
            "rs": "rust",
            "java": "java",
            "c": "c",
            "cpp": "cpp",
            "h": "c",
            "hpp": "cpp",
            "rb": "ruby",
        }.get(ext, ext)
