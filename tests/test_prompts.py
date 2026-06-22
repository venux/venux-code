"""Tests for prompt templates, builders, and prompt functions."""

from __future__ import annotations

from pathlib import Path

import pytest

from venux_code.llm.prompts.base import (
    CONTEXT_FILE_NAMES,
    PromptBuilder,
    PromptTemplate,
    load_context_files,
)

try:
    import jinja2  # noqa: F401
    HAS_JINJA2 = True
except ImportError:
    HAS_JINJA2 = False

_jinja_skip = pytest.mark.skipif(not HAS_JINJA2, reason="jinja2 not installed")


# ── PromptTemplate ────────────────────────────────────────────────────────


class TestPromptTemplate:
    def test_simple_substitution(self):
        tmpl = PromptTemplate("Hello $name, welcome to $place!")
        result = tmpl.render(name="Alice", place="Wonderland")
        assert result == "Hello Alice, welcome to Wonderland!"

    def test_braced_variable(self):
        tmpl = PromptTemplate("Value: ${value}")
        result = tmpl.render(value=42)
        assert result == "Value: 42"

    def test_missing_variable_safe_substitute(self):
        """safe_substitute leaves unresolved $var in place."""
        tmpl = PromptTemplate("Hello $name, your age is $age")
        result = tmpl.render(name="Bob")
        assert "Bob" in result
        assert "$age" in result

    def test_no_variables(self):
        tmpl = PromptTemplate("No variables here.")
        result = tmpl.render()
        assert result == "No variables here."

    def test_name_attribute(self):
        tmpl = PromptTemplate("test", name="my_template")
        assert tmpl._name == "my_template"

    def test_default_name(self):
        tmpl = PromptTemplate("test")
        assert tmpl._name == "unnamed"

    def test_repr(self):
        tmpl = PromptTemplate("A" * 100, name="test")
        r = repr(tmpl)
        assert "test" in r
        assert "PromptTemplate" in r

    def test_from_file(self, tmp_path: Path):
        f = tmp_path / "my_prompt.txt"
        f.write_text("Hello $user, this is a test.")
        tmpl = PromptTemplate.from_file(f)
        assert tmpl._name == "my_prompt"
        result = tmpl.render(user="Tester")
        assert result == "Hello Tester, this is a test."

    @_jinja_skip
    def test_jinja_rendering(self):
        tmpl = PromptTemplate(
            "Hello {{ name }}!{% if excited %} Wow!{% endif %}",
            use_jinja=True,
        )
        result = tmpl.render(name="World", excited=True)
        assert result == "Hello World! Wow!"

    @_jinja_skip
    def test_jinja_without_condition(self):
        tmpl = PromptTemplate(
            "Hello {{ name }}!{% if excited %} Wow!{% endif %}",
            use_jinja=True,
        )
        result = tmpl.render(name="World", excited=False)
        assert result == "Hello World!"


# ── PromptBuilder ─────────────────────────────────────────────────────────


class TestPromptBuilder:
    def test_single_section(self):
        result = PromptBuilder().section("Role", "You are helpful.").build()
        assert "# Role" in result
        assert "You are helpful." in result

    def test_multiple_sections(self):
        result = (
            PromptBuilder()
            .section("Role", "Coder")
            .section("Tools", "bash, edit")
            .build()
        )
        assert "# Role" in result
        assert "# Tools" in result
        assert result.index("# Role") < result.index("# Tools")

    def test_conditional_included(self):
        result = (
            PromptBuilder()
            .section("Base", "content")
            .conditional("Extra", "memory data", condition=True)
            .build()
        )
        assert "# Extra" in result
        assert "memory data" in result

    def test_conditional_excluded(self):
        result = (
            PromptBuilder()
            .section("Base", "content")
            .conditional("Extra", "memory data", condition=False)
            .build()
        )
        assert "Extra" not in result
        assert "memory data" not in result

    def test_conditional_empty_content(self):
        result = (
            PromptBuilder()
            .section("Base", "content")
            .conditional("Extra", "", condition=True)
            .build()
        )
        assert "Extra" not in result

    def test_conditional_none_content(self):
        result = (
            PromptBuilder()
            .section("Base", "content")
            .conditional("Extra", None, condition=True)
            .build()
        )
        assert "Extra" not in result

    def test_raw_text(self):
        result = (
            PromptBuilder()
            .section("Section", "content")
            .raw("Final instructions here.")
            .build()
        )
        assert "Final instructions here." in result

    def test_raw_before_sections(self):
        """Raw parts are placed before sections in the output."""
        result = (
            PromptBuilder()
            .raw("Preamble")
            .section("Section", "content")
            .build()
        )
        assert result.index("Preamble") < result.index("# Section")

    def test_fluent_chaining(self):
        """Builder methods return self for chaining."""
        builder = PromptBuilder()
        assert builder.section("A", "a") is builder
        assert builder.conditional("B", "b") is builder
        assert builder.raw("c") is builder

    def test_empty_build(self):
        result = PromptBuilder().build()
        assert result == ""


# ── load_context_files ────────────────────────────────────────────────────


class TestLoadContextFiles:
    def test_no_files(self, tmp_path: Path):
        result = load_context_files(tmp_path)
        assert result == ""

    def test_single_file(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("# My Project")
        result = load_context_files(tmp_path)
        assert "README.md" in result
        assert "# My Project" in result

    def test_multiple_files(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("# Project")
        (tmp_path / "AGENTS.md").write_text("Agent instructions here.")
        result = load_context_files(tmp_path)
        assert "README.md" in result
        assert "AGENTS.md" in result
        assert "---" in result  # separator

    def test_empty_file_skipped(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("")  # empty
        result = load_context_files(tmp_path)
        assert result == ""

    def test_whitespace_only_skipped(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("   \n  ")
        result = load_context_files(tmp_path)
        assert result == ""

    def test_nested_context_file(self, tmp_path: Path):
        (tmp_path / ".github").mkdir()
        (tmp_path / ".github" / "copilot-instructions.md").write_text("Copilot rules.")
        result = load_context_files(tmp_path)
        assert "copilot-instructions.md" in result
        assert "Copilot rules." in result

    def test_venux_rules(self, tmp_path: Path):
        (tmp_path / ".venux").mkdir()
        (tmp_path / ".venux" / "rules.md").write_text("Custom rules.")
        result = load_context_files(tmp_path)
        assert "rules.md" in result
        assert "Custom rules." in result


# ── Coder prompt ──────────────────────────────────────────────────────────


class TestBuildCoderPrompt:
    def test_basic_prompt(self):
        from venux_code.llm.prompts.coder import build_coder_prompt

        result = build_coder_prompt()
        assert "Venux Code" in result
        assert "Role" in result

    def test_with_memory(self):
        from venux_code.llm.prompts.coder import build_coder_prompt

        result = build_coder_prompt(memory="Previous context here.")
        assert "Memory" in result
        assert "Previous context here." in result

    def test_without_memory(self):
        from venux_code.llm.prompts.coder import build_coder_prompt

        result = build_coder_prompt(memory=None)
        assert "Memory" not in result

    def test_with_skills(self):
        from venux_code.llm.prompts.coder import build_coder_prompt

        result = build_coder_prompt(
            skills=["python", "git"],
            skill_descriptions={"python": "Python expertise", "git": "Git operations"},
        )
        assert "Active Skills" in result
        assert "python" in result
        assert "Git operations" in result

    def test_with_tools_description(self):
        from venux_code.llm.prompts.coder import build_coder_prompt

        result = build_coder_prompt(tools_description="- bash: Run commands")
        assert "bash: Run commands" in result

    def test_with_project_context(self, tmp_path: Path):
        from venux_code.llm.prompts.coder import build_coder_prompt

        (tmp_path / "README.md").write_text("# Test Project\nA test.")
        result = build_coder_prompt(project_root=tmp_path)
        assert "Project Context" in result
        assert "Test Project" in result

    def test_with_extra_context(self):
        from venux_code.llm.prompts.coder import build_coder_prompt

        result = build_coder_prompt(extra_context="Special instructions.")
        assert "Additional Context" in result
        assert "Special instructions." in result

    def test_max_context_chars(self, tmp_path: Path):
        from venux_code.llm.prompts.coder import build_coder_prompt

        (tmp_path / "README.md").write_text("x" * 1000)
        result = build_coder_prompt(project_root=tmp_path, max_context_chars=100)
        assert "truncated" in result


# ── Task prompt ───────────────────────────────────────────────────────────


class TestBuildTaskPrompt:
    def test_basic(self):
        from venux_code.llm.prompts.task import build_task_prompt

        result = build_task_prompt()
        assert "Task Agent" in result
        assert "read-only" in result.lower()

    def test_with_memory(self):
        from venux_code.llm.prompts.task import build_task_prompt

        result = build_task_prompt(memory="Previous analysis.")
        assert "Previous analysis." in result

    def test_with_task_context(self):
        from venux_code.llm.prompts.task import build_task_prompt

        result = build_task_prompt(task_context="Review the auth module.")
        assert "Review the auth module." in result


# ── Summarizer prompts ───────────────────────────────────────────────────


class TestSummarizerPrompts:
    def test_summarize_conversation(self):
        from venux_code.llm.prompts.summarizer import summarize_conversation

        result = summarize_conversation("User: Fix the bug.\nAI: Done.")
        assert "conversation" in result.lower() or "summarize" in result.lower()
        assert "Fix the bug" in result

    def test_summarize_conversation_custom_ratio(self):
        from venux_code.llm.prompts.summarizer import summarize_conversation

        result = summarize_conversation("content", target_ratio=50)
        assert "50%" in result

    def test_summarize_file(self):
        from venux_code.llm.prompts.summarizer import summarize_file

        result = summarize_file("main.py", "print('hello')", language="python")
        assert "main.py" in result
        assert "print('hello')" in result
        assert "python" in result

    def test_summarize_file_auto_language(self):
        from venux_code.llm.prompts.summarizer import summarize_file

        result = summarize_file("app.ts", "const x = 1;")
        assert "ts" in result

    def test_summarize_error(self):
        from venux_code.llm.prompts.summarizer import summarize_error

        result = summarize_error("TypeError: NoneType", code_context="x = None\nx.foo()")
        assert "TypeError" in result
        assert "x.foo()" in result

    def test_summarize_error_no_context(self):
        from venux_code.llm.prompts.summarizer import summarize_error

        result = summarize_error("Some error")
        assert "Some error" in result
        assert "no additional context" in result.lower()


# ── Title prompts ─────────────────────────────────────────────────────────


class TestTitlePrompts:
    def test_generate_title_prompt(self):
        from venux_code.llm.prompts.title import generate_title_prompt

        result = generate_title_prompt("Help me refactor the auth module")
        assert "refactor" in result
        assert "auth module" in result

    def test_generate_title_prompt_truncation(self):
        from venux_code.llm.prompts.title import generate_title_prompt

        long_msg = "x" * 3000
        result = generate_title_prompt(long_msg)
        assert "..." in result
        # Original long message should be truncated
        assert long_msg not in result

    def test_generate_title_from_summary_prompt(self):
        from venux_code.llm.prompts.title import generate_title_from_summary_prompt

        result = generate_title_from_summary_prompt("Fixed authentication bug.")
        assert "Fixed authentication bug." in result

    def test_generate_title_from_summary_truncation(self):
        from venux_code.llm.prompts.title import generate_title_from_summary_prompt

        long_summary = "y" * 4000
        result = generate_title_from_summary_prompt(long_summary)
        assert "..." in result
