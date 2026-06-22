"""Tests for built-in tools: bash, view, write, ls, glob, grep."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from venux_code.llm.tools.base import ToolResponse
from venux_code.llm.tools.bash_tool import BashTool
from venux_code.llm.tools.view_tool import ViewTool
from venux_code.llm.tools.write_tool import WriteTool
from venux_code.llm.tools.ls_tool import LsTool
from venux_code.llm.tools.glob_tool import GlobTool
from venux_code.llm.tools.grep_tool import GrepTool


# ── BashTool ────────────────────────────────────────────────────────────────


class TestBashTool:
    async def test_echo(self):
        tool = BashTool()
        result = await tool.execute({"command": "echo hello"})
        assert result.success is True
        assert "hello" in result.output

    async def test_exit_code(self):
        tool = BashTool()
        result = await tool.execute({"command": "exit 42"})
        assert result.success is False
        assert result.metadata.get("exit_code") == 42

    async def test_timeout(self):
        tool = BashTool()
        result = await tool.execute({"command": "sleep 10", "timeout": 1})
        assert result.success is False
        assert "timed out" in result.error.lower()

    async def test_stderr(self):
        tool = BashTool()
        result = await tool.execute({"command": "echo oops >&2; exit 1"})
        assert result.success is False

    async def test_working_directory(self, tmp_path: Path):
        tool = BashTool()
        result = await tool.execute(
            {"command": "pwd", "working_directory": str(tmp_path)}
        )
        assert result.success is True
        assert str(tmp_path) in result.output

    def test_metadata(self):
        tool = BashTool()
        assert tool.name == "bash"
        assert tool.requires_permission is True


# ── ViewTool ────────────────────────────────────────────────────────────────


class TestViewTool:
    async def test_read_file(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3\n")
        tool = ViewTool()
        result = await tool.execute({"path": str(f)})
        assert result.success is True
        assert "line1" in result.output
        assert "line2" in result.output

    async def test_offset_and_limit(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("a\nb\nc\nd\ne\n")
        tool = ViewTool()
        result = await tool.execute({"path": str(f), "offset": 2, "limit": 2})
        assert result.success is True
        assert "b" in result.output
        assert "c" in result.output
        assert "a" not in result.output

    async def test_nonexistent_file(self):
        tool = ViewTool()
        result = await tool.execute({"path": "/nonexistent/file.txt"})
        assert result.success is False
        assert "not found" in result.error.lower()

    async def test_directory_not_file(self, tmp_path: Path):
        tool = ViewTool()
        result = await tool.execute({"path": str(tmp_path)})
        assert result.success is False
        assert "not a file" in result.error.lower()

    async def test_line_numbers(self, tmp_path: Path):
        f = tmp_path / "numbered.txt"
        f.write_text("first\nsecond\n")
        tool = ViewTool()
        result = await tool.execute({"path": str(f)})
        assert "1|" in result.output
        assert "2|" in result.output

    def test_metadata(self):
        tool = ViewTool()
        assert tool.name == "view"
        assert tool.requires_permission is False


# ── WriteTool ───────────────────────────────────────────────────────────────


class TestWriteTool:
    async def test_create_file(self, tmp_path: Path):
        f = tmp_path / "new.py"
        tool = WriteTool()
        result = await tool.execute({"path": str(f), "content": "print('hi')\n"})
        assert result.success is True
        assert f.read_text() == "print('hi')\n"
        assert result.metadata.get("created") is True

    async def test_overwrite_file(self, tmp_path: Path):
        f = tmp_path / "exists.txt"
        f.write_text("old")
        tool = WriteTool()
        result = await tool.execute({"path": str(f), "content": "new"})
        assert result.success is True
        assert f.read_text() == "new"
        assert result.metadata.get("created") is False

    async def test_create_parents(self, tmp_path: Path):
        f = tmp_path / "deep" / "nested" / "file.txt"
        tool = WriteTool()
        result = await tool.execute(
            {"path": str(f), "content": "hello", "create_parents": True}
        )
        assert result.success is True
        assert f.exists()

    async def test_no_create_parents(self, tmp_path: Path):
        f = tmp_path / "no" / "parent" / "file.txt"
        tool = WriteTool()
        result = await tool.execute(
            {"path": str(f), "content": "hello", "create_parents": False}
        )
        assert result.success is False

    def test_metadata(self):
        tool = WriteTool()
        assert tool.name == "write"
        assert tool.requires_permission is True


# ── LsTool ──────────────────────────────────────────────────────────────────


class TestLsTool:
    async def test_list_directory(self, project_dir: Path):
        tool = LsTool()
        result = await tool.execute({"path": str(project_dir)})
        assert result.success is True
        assert "src" in result.output
        assert "README.md" in result.output

    async def test_hidden_files(self, tmp_path: Path):
        (tmp_path / ".hidden").write_text("secret")
        (tmp_path / "visible.txt").write_text("shown")
        tool = LsTool()
        result = await tool.execute({"path": str(tmp_path), "show_hidden": False})
        assert "visible.txt" in result.output
        assert ".hidden" not in result.output

        result2 = await tool.execute({"path": str(tmp_path), "show_hidden": True})
        assert ".hidden" in result2.output

    async def test_long_format(self, tmp_path: Path):
        (tmp_path / "file.txt").write_text("hello")
        tool = LsTool()
        result = await tool.execute({"path": str(tmp_path), "long_format": True})
        assert result.success is True
        assert "file.txt" in result.output

    async def test_nonexistent_path(self):
        tool = LsTool()
        result = await tool.execute({"path": "/nonexistent/dir"})
        assert result.success is False

    async def test_empty_directory(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        tool = LsTool()
        result = await tool.execute({"path": str(empty)})
        assert result.success is True
        assert "empty" in result.output

    def test_metadata(self):
        tool = LsTool()
        assert tool.name == "ls"
        assert tool.requires_permission is False


# ── GlobTool ────────────────────────────────────────────────────────────────


class TestGlobTool:
    async def test_glob_py_files(self, project_dir: Path):
        tool = GlobTool()
        result = await tool.execute({"pattern": "*.py", "path": str(project_dir / "src")})
        assert result.success is True
        assert "main.py" in result.output
        assert "utils.py" in result.output

    async def test_recursive_glob(self, project_dir: Path):
        tool = GlobTool()
        result = await tool.execute({"pattern": "**/*.py", "path": str(project_dir)})
        assert result.success is True
        assert "main.py" in result.output

    async def test_no_matches(self, tmp_path: Path):
        tool = GlobTool()
        result = await tool.execute({"pattern": "*.xyz", "path": str(tmp_path)})
        assert result.success is True
        assert "No files matched" in result.output

    async def test_max_results(self, tmp_path: Path):
        for i in range(20):
            (tmp_path / f"file{i:02d}.txt").write_text("")
        tool = GlobTool()
        result = await tool.execute(
            {"pattern": "*.txt", "path": str(tmp_path), "max_results": 5}
        )
        assert result.success is True
        assert result.metadata.get("count") == 5

    def test_metadata(self):
        tool = GlobTool()
        assert tool.name == "glob"
        assert tool.requires_permission is False


# ── GrepTool ────────────────────────────────────────────────────────────────


class TestGrepTool:
    async def test_grep_pattern(self, project_dir: Path):
        tool = GrepTool()
        result = await tool.execute(
            {"pattern": "def ", "path": str(project_dir / "src"), "file_glob": "*.py"}
        )
        assert result.success is True
        assert "helper" in result.output

    async def test_grep_no_matches(self, tmp_path: Path):
        (tmp_path / "test.py").write_text("nothing here")
        tool = GrepTool()
        result = await tool.execute(
            {"pattern": "NONEXISTENT", "path": str(tmp_path)}
        )
        assert result.success is True
        assert "No matches" in result.output

    async def test_grep_case_insensitive(self, tmp_path: Path):
        (tmp_path / "test.py").write_text("Hello World\nhello world\n")
        tool = GrepTool()
        result = await tool.execute(
            {"pattern": "hello", "path": str(tmp_path), "case_sensitive": False}
        )
        assert result.success is True
        # Should find both lines
        assert result.metadata.get("matches", 0) == 2

    async def test_grep_literal(self, tmp_path: Path):
        (tmp_path / "test.py").write_text("a+b=c\nab=c\n")
        tool = GrepTool()
        result = await tool.execute(
            {"pattern": "a+b", "path": str(tmp_path), "literal": True}
        )
        assert result.success is True
        assert result.metadata.get("matches", 0) == 1

    async def test_grep_context_lines(self, tmp_path: Path):
        (tmp_path / "test.py").write_text("line1\nline2 MATCH line2\nline3\n")
        tool = GrepTool()
        result = await tool.execute(
            {"pattern": "MATCH", "path": str(tmp_path), "context_lines": 1}
        )
        assert result.success is True
        assert "line1" in result.output
        assert "line3" in result.output

    async def test_invalid_regex(self, tmp_path: Path):
        tool = GrepTool()
        result = await tool.execute({"pattern": "[invalid", "path": str(tmp_path)})
        assert result.success is False
        assert "Invalid regex" in result.error

    def test_metadata(self):
        tool = GrepTool()
        assert tool.name == "grep"
        assert tool.requires_permission is False


# ── ToolResponse ────────────────────────────────────────────────────────────


class TestToolResponse:
    def test_success_str(self):
        r = ToolResponse(success=True, output="ok")
        assert str(r) == "ok"

    def test_failure_str(self):
        r = ToolResponse(success=False, error="boom")
        assert str(r) == "Error: boom"

    def test_default_values(self):
        r = ToolResponse(success=True)
        assert r.output == ""
        assert r.error is None
        assert r.metadata == {}
        assert r.display_type == "text"


# ── ToolRegistry ────────────────────────────────────────────────────────────


class TestToolRegistry:
    def test_default_tools(self):
        from venux_code.llm.tools.registry import ToolRegistry

        registry = ToolRegistry()
        assert "bash" in registry
        assert "view" in registry
        assert "write" in registry
        assert "ls" in registry
        assert "glob" in registry
        assert "grep" in registry

    def test_list_names_sorted(self):
        from venux_code.llm.tools.registry import ToolRegistry

        registry = ToolRegistry()
        names = registry.list_names()
        assert names == sorted(names)

    def test_get_tool(self):
        from venux_code.llm.tools.registry import ToolRegistry

        registry = ToolRegistry()
        bash = registry.get("bash")
        assert bash is not None
        assert bash.name == "bash"

    def test_get_nonexistent(self):
        from venux_code.llm.tools.registry import ToolRegistry

        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_register_custom(self):
        from venux_code.llm.tools.registry import ToolRegistry

        registry = ToolRegistry(include_defaults=False)
        assert len(registry) == 0

        tool = BashTool()
        registry.register(tool)
        assert "bash" in registry
        assert len(registry) == 1

    def test_unregister(self):
        from venux_code.llm.tools.registry import ToolRegistry

        registry = ToolRegistry()
        registry.unregister("bash")
        assert "bash" not in registry

    def test_permission_tools(self):
        from venux_code.llm.tools.registry import ToolRegistry

        registry = ToolRegistry()
        perm_tools = registry.get_tools_requiring_permission()
        perm_names = [t.name for t in perm_tools]
        assert "bash" in perm_names
        assert "write" in perm_names
        assert "view" not in perm_names

    def test_as_langchain_tools(self):
        from venux_code.llm.tools.registry import ToolRegistry

        registry = ToolRegistry()
        lc_tools = registry.as_langchain_tools()
        assert len(lc_tools) > 0
        names = [t.name for t in lc_tools]
        assert "bash" in names

    def test_describe_all(self):
        from venux_code.llm.tools.registry import ToolRegistry

        registry = ToolRegistry()
        desc = registry.describe_all()
        assert "bash" in desc
        assert "view" in desc

    def test_no_defaults(self):
        from venux_code.llm.tools.registry import ToolRegistry

        registry = ToolRegistry(include_defaults=False)
        assert len(registry) == 0
        assert registry.list_names() == []
