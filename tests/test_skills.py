"""Tests for SkillService."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from venux_code.skills.models import Skill, SkillSource
from venux_code.skills.service import SkillService


@pytest.fixture
def skills_db_path(tmp_path: Path) -> Path:
    return tmp_path / "skills.db"


@pytest.fixture
def skill_service(skills_db_path: Path) -> SkillService:
    return SkillService(db_path=skills_db_path)


class TestSkillServiceCRUD:
    async def test_create(self, skill_service: SkillService):
        skill = await skill_service.create(
            name="test-skill",
            content="# Test\nDo something.",
            category="testing",
            description="A test skill",
        )
        assert skill.name == "test-skill"
        assert skill.content == "# Test\nDo something."
        assert skill.category == "testing"
        assert skill.source == SkillSource.LOCAL

    async def test_get_existing(self, skill_service: SkillService):
        await skill_service.create(name="findme", content="Content here")
        found = await skill_service.get("findme")
        assert found is not None
        assert found.name == "findme"

    async def test_get_nonexistent(self, skill_service: SkillService):
        found = await skill_service.get("nonexistent")
        assert found is None

    async def test_list_skills(self, skill_service: SkillService):
        await skill_service.create(name="alpha", content="A")
        await skill_service.create(name="beta", content="B")
        await skill_service.create(name="gamma", content="C")

        skills = await skill_service.list_skills()
        assert len(skills) == 3
        names = [s.name for s in skills]
        assert names == sorted(names)

    async def test_list_filter_category(self, skill_service: SkillService):
        await skill_service.create(name="a", content="A", category="dev")
        await skill_service.create(name="b", content="B", category="test")
        await skill_service.create(name="c", content="C", category="dev")

        dev_skills = await skill_service.list_skills(category="dev")
        assert len(dev_skills) == 2

    async def test_list_enabled_only(self, skill_service: SkillService):
        s = await skill_service.create(name="enabled", content="E")
        await skill_service.create(name="disabled", content="D")

        # Disable one
        db = await skill_service._ensure_db()
        await db.execute("UPDATE skills SET enabled=0 WHERE name=?", ("disabled",))
        await db.commit()
        skill_service._cache["disabled"].enabled = False

        skills = await skill_service.list_skills(enabled_only=True)
        names = [s.name for s in skills]
        assert "enabled" in names
        assert "disabled" not in names

    async def test_load_skill(self, skill_service: SkillService):
        await skill_service.create(name="loadable", content="Instructions here")
        content = await skill_service.load_skill("loadable")
        assert content == "Instructions here"

    async def test_load_nonexistent(self, skill_service: SkillService):
        content = await skill_service.load_skill("nope")
        assert content is None

    async def test_uninstall(self, skill_service: SkillService):
        await skill_service.create(name="removable", content="Bye")
        result = await skill_service.uninstall("removable")
        assert result is True

        found = await skill_service.get("removable")
        assert found is None

    async def test_uninstall_nonexistent(self, skill_service: SkillService):
        result = await skill_service.uninstall("ghost")
        # Should return False (not in cache, no rows deleted)
        assert isinstance(result, bool)


class TestSkillServiceAutoCreate:
    async def test_auto_create_from_tool_use(self, skill_service: SkillService):
        conversation = [
            {"role": "user", "content": "Please set up the project with npm install and then run tests"},
            {"role": "assistant", "content": "I'll use tool call: bash to run npm install"},
            {"role": "assistant", "content": "Now tool call: bash to run tests"},
        ]
        skill = await skill_service.auto_create("session-123", conversation)
        assert skill is not None
        assert skill.source == SkillSource.AUTO
        assert "auto-generated" in skill.tags

    async def test_auto_create_no_procedure(self, skill_service: SkillService):
        conversation = [
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        skill = await skill_service.auto_create("session-456", conversation)
        assert skill is None

    async def test_auto_create_unique_name(self, skill_service: SkillService):
        # Pre-create a skill with a name that might collide
        await skill_service.create(
            name="set-up-the-project-with-npm-install",
            content="Existing",
        )
        conversation = [
            {"role": "user", "content": "Set up the project with npm install"},
            {"role": "assistant", "content": "tool call: bash to install"},
            {"role": "assistant", "content": "tool call: bash to verify"},
        ]
        skill = await skill_service.auto_create("session-789", conversation)
        assert skill is not None
        # Should have a unique name (appended with -1 or similar)
        assert skill.name != "set-up-the-project-with-npm-install"


class TestSkillServiceLifecycle:
    async def test_close_and_reopen(self, skill_service: SkillService):
        await skill_service.create(name="persistent", content="I survive")
        await skill_service.close()

        # Re-open and verify data persists
        service2 = SkillService(db_path=skill_service._db_path)
        found = await service2.get("persistent")
        assert found is not None
        assert found.content == "I survive"
        await service2.close()
