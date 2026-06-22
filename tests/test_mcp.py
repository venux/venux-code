"""Tests for MCP adapter, tool wrapper, and connection manager."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from venux_code.llm.tools.mcp_tool import (
    MCPToolWrapper,
    _create_params_schema,
    _json_type_to_python,
)
from venux_code.llm.tools.mcp_adapter import MCPAdapter, MCPConnectionManager


# ── JSON type mapping ─────────────────────────────────────────────────────


class TestJsonTypeMapping:
    def test_string_type(self):
        assert _json_type_to_python({"type": "string"}) is str

    def test_integer_type(self):
        assert _json_type_to_python({"type": "integer"}) is int

    def test_number_type(self):
        assert _json_type_to_python({"type": "number"}) is float

    def test_boolean_type(self):
        assert _json_type_to_python({"type": "boolean"}) is bool

    def test_array_type(self):
        assert _json_type_to_python({"type": "array"}) is list

    def test_object_type(self):
        assert _json_type_to_python({"type": "object"}) is dict

    def test_enum_defaults_to_str(self):
        assert _json_type_to_python({"enum": ["a", "b"]}) is str

    def test_unknown_type_defaults_to_str(self):
        assert _json_type_to_python({"type": "foobar"}) is str

    def test_no_type_defaults_to_str(self):
        assert _json_type_to_python({}) is str


# ── Schema creation ───────────────────────────────────────────────────────


class TestCreateParamsSchema:
    def test_none_schema(self):
        model_cls = _create_params_schema(None)
        assert issubclass(model_cls, BaseModel)
        # Should have no fields
        assert len(model_cls.model_fields) == 0

    def test_empty_schema(self):
        model_cls = _create_params_schema({})
        assert issubclass(model_cls, BaseModel)
        assert len(model_cls.model_fields) == 0

    def test_required_and_optional_fields(self):
        schema = {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "File name"},
                "count": {"type": "integer", "description": "Number of items"},
                "verbose": {"type": "boolean", "description": "Verbose output"},
            },
            "required": ["filename"],
        }
        model_cls = _create_params_schema(schema)
        assert "filename" in model_cls.model_fields
        assert "count" in model_cls.model_fields
        assert "verbose" in model_cls.model_fields

        # filename is required (no default)
        field_info = model_cls.model_fields["filename"]
        assert field_info.is_required()

        # count is optional (has default)
        field_info_count = model_cls.model_fields["count"]
        assert not field_info_count.is_required()

    def test_enum_field(self):
        schema = {
            "type": "object",
            "properties": {
                "mode": {"enum": ["fast", "slow"], "description": "Mode"},
            },
            "required": ["mode"],
        }
        model_cls = _create_params_schema(schema)
        assert "mode" in model_cls.model_fields


# ── MCPToolWrapper ────────────────────────────────────────────────────────


class TestMCPToolWrapper:
    def _make_mcp_tool(self, name="test_tool", description="A test tool", input_schema=None):
        return SimpleNamespace(
            name=name,
            description=description,
            inputSchema=input_schema,
        )

    def test_basic_attributes(self):
        mcp_tool = self._make_mcp_tool()
        adapter = MagicMock()
        adapter.name = "test-server"
        wrapper = MCPToolWrapper(mcp_tool=mcp_tool, adapter=adapter)

        assert wrapper.name == "test_tool"
        assert wrapper.description == "A test tool"
        assert wrapper.requires_permission is False

    def test_description_fallback(self):
        mcp_tool = self._make_mcp_tool(description=None)
        adapter = MagicMock()
        adapter.name = "test-server"
        wrapper = MCPToolWrapper(mcp_tool=mcp_tool, adapter=adapter)

        assert "test_tool" in wrapper.description

    def test_parameters_schema_generated(self):
        schema = {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
            },
            "required": ["path"],
        }
        mcp_tool = self._make_mcp_tool(input_schema=schema)
        adapter = MagicMock()
        adapter.name = "test-server"
        wrapper = MCPToolWrapper(mcp_tool=mcp_tool, adapter=adapter)

        assert issubclass(wrapper.parameters_schema, BaseModel)
        assert "path" in wrapper.parameters_schema.model_fields

    @pytest.mark.asyncio
    async def test_execute_success(self):
        mcp_tool = self._make_mcp_tool()
        adapter = MagicMock()
        adapter.name = "test-server"
        adapter.call_tool = AsyncMock()

        # Mock result with text content
        text_block = SimpleNamespace(text="result output")
        adapter.call_tool.return_value = SimpleNamespace(
            content=[text_block],
            isError=False,
        )

        wrapper = MCPToolWrapper(mcp_tool=mcp_tool, adapter=adapter)
        result = await wrapper.execute({"arg": "value"})

        assert result.success is True
        assert result.output == "result output"
        adapter.call_tool.assert_called_once_with("test_tool", {"arg": "value"})

    @pytest.mark.asyncio
    async def test_execute_error(self):
        mcp_tool = self._make_mcp_tool()
        adapter = MagicMock()
        adapter.name = "test-server"
        adapter.call_tool = AsyncMock()

        text_block = SimpleNamespace(text="something went wrong")
        adapter.call_tool.return_value = SimpleNamespace(
            content=[text_block],
            isError=True,
        )

        wrapper = MCPToolWrapper(mcp_tool=mcp_tool, adapter=adapter)
        result = await wrapper.execute({})

        assert result.success is False
        assert result.error == "something went wrong"

    @pytest.mark.asyncio
    async def test_execute_runtime_error(self):
        mcp_tool = self._make_mcp_tool()
        adapter = MagicMock()
        adapter.name = "test-server"
        adapter.call_tool = AsyncMock(side_effect=RuntimeError("not connected"))

        wrapper = MCPToolWrapper(mcp_tool=mcp_tool, adapter=adapter)
        result = await wrapper.execute({})

        assert result.success is False
        assert "not connected" in result.error

    def test_repr(self):
        mcp_tool = self._make_mcp_tool(name="my_tool")
        adapter = MagicMock()
        adapter.name = "my-server"
        wrapper = MCPToolWrapper(mcp_tool=mcp_tool, adapter=adapter)
        r = repr(wrapper)
        assert "my_tool" in r
        assert "my-server" in r


# ── MCPAdapter ────────────────────────────────────────────────────────────


class TestMCPAdapter:
    def test_initial_state(self):
        adapter = MCPAdapter(name="test")
        assert adapter.name == "test"
        assert adapter.is_connected is False
        assert adapter._session is None

    def test_list_tools_not_connected(self):
        from venux_code.llm.tools.mcp_adapter import MCPAdapter

        adapter = MCPAdapter(name="test")
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_list_tools_not_connected_async(self):
        adapter = MCPAdapter(name="test")
        with pytest.raises(RuntimeError, match="not connected"):
            await adapter.list_tools()

    @pytest.mark.asyncio
    async def test_call_tool_not_connected(self):
        adapter = MCPAdapter(name="test")
        with pytest.raises(RuntimeError, match="not connected"):
            await adapter.call_tool("test", {})

    def test_as_base_tools_empty(self):
        adapter = MCPAdapter(name="test")
        tools = adapter.as_base_tools()
        assert tools == []

    @pytest.mark.asyncio
    async def test_disconnect_no_task(self):
        """disconnect() on a never-connected adapter should be a no-op."""
        adapter = MCPAdapter(name="test")
        await adapter.disconnect()  # should not raise

    @pytest.mark.asyncio
    async def test_context_manager(self):
        adapter = MCPAdapter(name="test")
        result = await adapter.__aenter__()
        assert result is adapter
        await adapter.__aexit__(None, None, None)

    def test_repr_disconnected(self):
        adapter = MCPAdapter(name="test")
        assert "disconnected" in repr(adapter)

    @pytest.mark.asyncio
    async def test_double_connect_raises(self):
        """Connecting when already connected should raise."""
        adapter = MCPAdapter(name="test")
        adapter._connected = True
        with pytest.raises(RuntimeError, match="already connected"):
            await adapter._start_connection(None)


# ── MCPConnectionManager ─────────────────────────────────────────────────


class TestMCPConnectionManager:
    def test_initial_state(self):
        mgr = MCPConnectionManager()
        assert len(mgr) == 0
        assert mgr.list_adapters() == []

    def test_add_stdio(self):
        mgr = MCPConnectionManager()
        mgr.add_stdio("fs", "npx", ["-y", "@mcp/fs", "/tmp"])
        assert len(mgr._pending) == 1
        name, transport, kwargs = mgr._pending[0]
        assert name == "fs"
        assert transport == "stdio"
        assert kwargs["command"] == "npx"

    def test_add_sse(self):
        mgr = MCPConnectionManager()
        mgr.add_sse("remote", "http://example.com/sse", headers={"Auth": "token"})
        assert len(mgr._pending) == 1
        name, transport, kwargs = mgr._pending[0]
        assert name == "remote"
        assert transport == "sse"
        assert kwargs["url"] == "http://example.com/sse"

    def test_add_streamable_http(self):
        mgr = MCPConnectionManager()
        mgr.add_streamable_http("api", "http://example.com/mcp")
        assert len(mgr._pending) == 1
        name, transport, kwargs = mgr._pending[0]
        assert name == "api"
        assert transport == "http"

    def test_register_adapter(self):
        mgr = MCPConnectionManager()
        adapter = MCPAdapter(name="test")
        adapter._connected = True
        adapter._tools_cache = []
        mgr.register(adapter)

        assert len(mgr) == 1
        assert "test" in mgr
        assert mgr.get_adapter("test") is adapter

    def test_get_adapter_missing(self):
        mgr = MCPConnectionManager()
        assert mgr.get_adapter("nonexistent") is None

    def test_as_base_tools_empty(self):
        mgr = MCPConnectionManager()
        assert mgr.as_base_tools() == []

    def test_repr(self):
        mgr = MCPConnectionManager()
        mgr.add_stdio("fs", "npx")
        r = repr(mgr)
        assert "pending=1" in r

    @pytest.mark.asyncio
    async def test_disconnect_all_empty(self):
        mgr = MCPConnectionManager()
        await mgr.disconnect_all()  # no-op, should not raise
