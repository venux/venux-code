"""MCP (Model Context Protocol) tool adapter.

Connects to MCP servers via stdio, SSE, or Streamable HTTP transports,
discovers their tools, and wraps them as Venux Code ``BaseTool`` instances
(and optionally LangChain ``StructuredTool`` objects).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import mcp
from mcp import ClientSession, StdioServerParameters

from .base import BaseTool

logger = logging.getLogger(__name__)


# ── MCPAdapter ─────────────────────────────────────────────────────────────


class MCPAdapter:
    """Connects to a single MCP server and provides access to its tools.

    Usage
    -----
    ```python
    adapter = MCPAdapter("filesystem")
    await adapter.connect_stdio("npx", ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
    tools = await adapter.list_tools()
    result = await adapter.call_tool("read_file", {"path": "/tmp/test.txt"})
    await adapter.disconnect()
    ```

    Can also be used as an async context manager:

    ```python
    async with MCPAdapter("fs") as adapter:
        await adapter.connect_stdio("mcp-fs-server", ["/tmp"])
        tools = await adapter.list_tools()
    ```
    """

    def __init__(self, name: str = "mcp-server") -> None:
        self.name = name
        self._session: ClientSession | None = None
        self._connected = False
        self._tools_cache: list[mcp.Tool] = []
        self._transport_task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()
        self._cleanup_event = asyncio.Event()
        self._error: Exception | None = None

    # ── Internal transport management ────────────────────────────────────

    async def _maintain_connection(self, transport_cm: Any) -> None:
        """Background coroutine that keeps the transport and session alive.

        Runs as an ``asyncio.Task``.  Blocks on ``_cleanup_event`` after
        initialisation so the context managers stay open until
        :meth:`disconnect` is called.
        """
        try:
            async with transport_cm as streams:
                # stdio and SSE yield (read, write); streamable HTTP may
                # yield (read, write, get_session_id).  We only need the
                # first two.
                read_stream, write_stream = streams[0], streams[1]

                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    self._session = session

                    result = await session.list_tools()
                    self._tools_cache = result.tools
                    self._connected = True
                    self._ready.set()

                    logger.info(
                        "MCPAdapter '%s': connected, %d tool(s) discovered",
                        self.name,
                        len(self._tools_cache),
                    )

                    # Keep alive until disconnect() is called.
                    await self._cleanup_event.wait()

                    self._session = None
                    self._connected = False

        except Exception as exc:
            self._error = exc
            self._connected = False
            self._ready.set()  # Unblock caller so it can propagate the error
            logger.error("MCPAdapter '%s': transport error: %s", self.name, exc)

    async def _start_connection(self, transport_cm: Any) -> None:
        """Spin up a background task that owns *transport_cm*."""
        if self._connected:
            raise RuntimeError(
                f"MCPAdapter '{self.name}' is already connected — "
                "call disconnect() first"
            )

        self._ready.clear()
        self._cleanup_event.clear()
        self._error = None

        self._transport_task = asyncio.create_task(
            self._maintain_connection(transport_cm)
        )
        await self._ready.wait()

        if self._error:
            err = self._error
            self._error = None
            raise err

    # ── Public: connect via various transports ───────────────────────────

    async def connect_stdio(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> MCPAdapter:
        """Connect to an MCP server via **stdio** transport.

        Parameters
        ----------
        command:
            Executable to spawn (e.g. ``"npx"``, ``"python"``, ``"uvx"``).
        args:
            Command-line arguments passed to the executable.
        env:
            Extra environment variables (merged with the current process
            environment).  ``None`` inherits the full parent environment.

        Returns
        -------
        MCPAdapter
            ``self`` (allows ``adapter = await MCPAdapter("x").connect_stdio(…)``).
        """
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(
            command=command,
            args=args or [],
            env=env,
        )
        await self._start_connection(stdio_client(server_params))
        return self

    async def connect_sse(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> MCPAdapter:
        """Connect to an MCP server via **SSE** (Server-Sent Events) transport.

        Parameters
        ----------
        url:
            The SSE endpoint URL (e.g. ``"http://localhost:8080/sse"``).
        headers:
            Optional HTTP headers sent with the initial connection request.

        Returns
        -------
        MCPAdapter
            ``self``.
        """
        from mcp.client.sse import sse_client

        await self._start_connection(sse_client(url, headers=headers))
        return self

    async def connect_streamable_http(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> MCPAdapter:
        """Connect via **Streamable HTTP** transport.

        Parameters
        ----------
        url:
            The HTTP endpoint URL.
        headers:
            Optional HTTP headers.

        Returns
        -------
        MCPAdapter
            ``self``.
        """
        from mcp.client.streamable_http import streamablehttp_client

        await self._start_connection(
            streamablehttp_client(url, headers=headers)
        )
        return self

    # ── Public: tool operations ──────────────────────────────────────────

    async def list_tools(self) -> list[mcp.Tool]:
        """Return the tools advertised by the connected server.

        Returns
        -------
        list[mcp.Tool]
            Snapshot of the tool list at connection time.

        Raises
        ------
        RuntimeError
            If the adapter is not connected.
        """
        if not self._connected:
            raise RuntimeError(f"MCPAdapter '{self.name}' is not connected")
        return list(self._tools_cache)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Invoke a tool on the MCP server.

        Parameters
        ----------
        name:
            Tool name (as returned by :meth:`list_tools`).
        arguments:
            Tool arguments matching the tool's ``inputSchema``.

        Returns
        -------
        mcp.types.CallToolResult
            The raw MCP result object (has ``.content`` and ``.isError``).
        """
        if not self._session:
            raise RuntimeError(f"MCPAdapter '{self.name}' is not connected")
        return await self._session.call_tool(name, arguments)

    async def as_langchain_tools(self) -> list[Any]:
        """Convert all MCP tools to LangChain ``StructuredTool`` objects.

        Returns
        -------
        list[StructuredTool]
            One per MCP tool, ready for ``VenuxAgent(tools=…)``.
        """
        from .mcp_tool import MCPToolWrapper

        tools = await self.list_tools()
        wrappers = [MCPToolWrapper(mcp_tool=t, adapter=self) for t in tools]
        return [w.to_langchain_tool() for w in wrappers]

    def as_base_tools(self) -> list[BaseTool]:
        """Wrap cached MCP tools as ``BaseTool`` instances.

        Does **not** require an active connection — uses the metadata
        cached during :meth:`list_tools` / connection setup.
        """
        from .mcp_tool import MCPToolWrapper

        return [
            MCPToolWrapper(mcp_tool=t, adapter=self) for t in self._tools_cache
        ]

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def disconnect(self) -> None:
        """Gracefully disconnect from the MCP server.

        Signals the background transport task to shut down and waits up to
        5 seconds for clean teardown.
        """
        if not self._transport_task:
            return

        self._cleanup_event.set()
        try:
            await asyncio.wait_for(self._transport_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._transport_task.cancel()
            try:
                await self._transport_task
            except asyncio.CancelledError:
                pass
        finally:
            self._transport_task = None
            self._session = None
            self._connected = False

        logger.info("MCPAdapter '%s': disconnected", self.name)

    @property
    def is_connected(self) -> bool:
        """Whether the adapter currently has a live connection."""
        return self._connected

    # ── Async context manager ────────────────────────────────────────────

    async def __aenter__(self) -> MCPAdapter:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.disconnect()

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return (
            f"<MCPAdapter '{self.name}' {status}"
            f" tools={len(self._tools_cache)}>"
        )


# ── MCPConnectionManager ───────────────────────────────────────────────────


class MCPConnectionManager:
    """Manages connections to **multiple** MCP servers.

    Servers are registered first (with transport details), then
    :meth:`connect_all` opens all connections concurrently.  The manager
    aggregates tools from every connected server.

    Usage
    -----
    ```python
    manager = MCPConnectionManager()
    manager.add_stdio("fs", "npx", ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
    manager.add_sse("remote", "http://example.com/sse")
    await manager.connect_all()

    all_tools = manager.as_base_tools()         # BaseTool instances
    lc_tools  = await manager.as_langchain_tools()  # LangChain StructuredTools

    fs_adapter = manager.get_adapter("fs")
    result = await fs_adapter.call_tool("read_file", {"path": "/tmp/a.txt"})

    await manager.disconnect_all()
    ```
    """

    def __init__(self) -> None:
        # Pending configs: list of (name, transport_type, kwargs)
        self._pending: list[tuple[str, str, dict[str, Any]]] = []
        # Live adapters keyed by server name
        self._adapters: dict[str, MCPAdapter] = {}

    # ── Registration (before connect) ────────────────────────────────────

    def add_stdio(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """Register a stdio-based MCP server for later connection."""
        self._pending.append(
            (name, "stdio", {"command": command, "args": args, "env": env})
        )

    def add_sse(
        self,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Register an SSE-based MCP server for later connection."""
        self._pending.append(
            (name, "sse", {"url": url, "headers": headers})
        )

    def add_streamable_http(
        self,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Register a Streamable HTTP MCP server for later connection."""
        self._pending.append(
            (name, "http", {"url": url, "headers": headers})
        )

    # ── Direct registration of a live adapter ────────────────────────────

    def register(self, adapter: MCPAdapter) -> None:
        """Add an already-connected :class:`MCPAdapter` directly.

        Useful when you manage the adapter lifecycle yourself.
        """
        self._adapters[adapter.name] = adapter

    # ── Connect / disconnect ─────────────────────────────────────────────

    async def connect_all(self) -> None:
        """Connect to all registered servers concurrently.

        Each server's ``connect_*`` coroutine is gathered so that slow
        servers do not block faster ones.
        """
        tasks: list[asyncio.Task[MCPAdapter]] = []

        for name, transport, kwargs in self._pending:
            adapter = MCPAdapter(name)
            if transport == "stdio":
                coro = adapter.connect_stdio(**kwargs)
            elif transport == "sse":
                coro = adapter.connect_sse(**kwargs)
            elif transport == "http":
                coro = adapter.connect_streamable_http(**kwargs)
            else:
                logger.warning("Unknown transport '%s' for server '%s'", transport, name)
                continue

            tasks.append(asyncio.create_task(coro))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, BaseException):
                logger.error("Failed to connect MCP server: %s", result)
                continue
            # result is the MCPAdapter returned by connect_*
            self._adapters[result.name] = result

        self._pending.clear()

        logger.info(
            "MCPConnectionManager: %d/%d server(s) connected",
            len(self._adapters),
            len(self._adapters) + sum(
                1 for r in results if isinstance(r, BaseException)
            ),
        )

    async def disconnect_all(self) -> None:
        """Disconnect all live adapters."""
        for adapter in self._adapters.values():
            await adapter.disconnect()
        self._adapters.clear()

    # ── Lookup ───────────────────────────────────────────────────────────

    def get_adapter(self, name: str) -> MCPAdapter | None:
        """Return the adapter for *name*, or ``None``."""
        return self._adapters.get(name)

    def list_adapters(self) -> list[MCPAdapter]:
        """Return all live adapters."""
        return list(self._adapters.values())

    # ── Aggregated tool access ───────────────────────────────────────────

    def as_base_tools(self) -> list[BaseTool]:
        """Return :class:`BaseTool` wrappers for **all** connected servers."""
        tools: list[BaseTool] = []
        for adapter in self._adapters.values():
            tools.extend(adapter.as_base_tools())
        return tools

    async def as_langchain_tools(self) -> list[Any]:
        """Return LangChain ``StructuredTool`` objects for all servers."""
        tools: list[Any] = []
        for adapter in self._adapters.values():
            tools.extend(await adapter.as_langchain_tools())
        return tools

    # ── Dunder helpers ───────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._adapters)

    def __contains__(self, name: str) -> bool:
        return name in self._adapters

    def __repr__(self) -> str:
        names = list(self._adapters.keys())
        pending = len(self._pending)
        return (
            f"<MCPConnectionManager connected={names}"
            f" pending={pending}>"
        )
