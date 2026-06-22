"""Tests for MemoryService."""

from __future__ import annotations

import pytest
from pathlib import Path
from typing import Any

from venux_code.memory.models import MemoryCategory, MemoryEntry, UserProfile
from venux_code.memory.builtin_provider import BuiltinMemoryProvider
from venux_code.memory.service import MemoryService, _extract_memory_candidates


@pytest.fixture
def memory_db_path(tmp_path: Path) -> Path:
    return tmp_path / "memory.db"


@pytest.fixture
def provider(memory_db_path: Path) -> BuiltinMemoryProvider:
    return BuiltinMemoryProvider(db_path=memory_db_path)


@pytest.fixture
def service(provider: BuiltinMemoryProvider) -> MemoryService:
    return MemoryService(provider)


class TestMemoryServiceCRUD:
    async def test_add(self, service: MemoryService):
        entry = await service.add("User prefers dark mode", category="user_pref")
        assert entry.id is not None
        assert entry.content == "User prefers dark mode"
        assert entry.category == MemoryCategory.USER_PREF

    async def test_add_with_tags(self, service: MemoryService):
        entry = await service.add("Uses Python 3.12", tags=["python", "version"])
        assert "python" in entry.tags
        assert "version" in entry.tags

    async def test_get(self, service: MemoryService):
        entry = await service.add("Test memory")
        found = await service.get(entry.id)
        assert found is not None
        assert found.content == "Test memory"

    async def test_get_nonexistent(self, service: MemoryService):
        found = await service.get("nonexistent-id")
        assert found is None

    async def test_update(self, service: MemoryService):
        entry = await service.add("Old content")
        updated = await service.update(entry.id, "New content")
        assert updated is not None
        assert updated.content == "New content"

    async def test_update_nonexistent(self, service: MemoryService):
        result = await service.update("fake-id", "content")
        assert result is None

    async def test_remove(self, service: MemoryService):
        entry = await service.add("Delete me")
        result = await service.remove(entry.id)
        assert result is True
        found = await service.get(entry.id)
        assert found is None

    async def test_remove_nonexistent(self, service: MemoryService):
        result = await service.remove("nonexistent")
        assert result is False

    async def test_list_all(self, service: MemoryService):
        for i in range(5):
            await service.add(f"Memory {i}")
        entries = await service.list_all()
        assert len(entries) == 5

    async def test_list_with_pagination(self, service: MemoryService):
        for i in range(10):
            await service.add(f"Memory {i}")
        page = await service.list_all(limit=3, offset=2)
        assert len(page) == 3


class TestMemoryServiceSearch:
    async def test_search(self, service: MemoryService):
        await service.add("User prefers dark mode", tags=["ui"])
        await service.add("User likes Python", tags=["lang"])
        await service.add("Project uses SQLAlchemy", tags=["db"])

        results = await service.search("user prefers")
        assert len(results) >= 1
        assert any("dark mode" in r.content for r in results)

    async def test_search_no_results(self, service: MemoryService):
        await service.add("Something unrelated")
        results = await service.search("nonexistent query xyz")
        assert len(results) == 0

    async def test_search_min_trust(self, service: MemoryService):
        await service.add("High trust", trust_score=0.9)
        await service.add("Low trust", trust_score=0.1)

        results = await service.search("trust", min_trust=0.5)
        assert len(results) == 1
        assert results[0].content == "High trust"


class TestMemoryServiceUserProfile:
    async def test_get_default_profile(self, service: MemoryService):
        profile = await service.get_user_profile()
        assert profile.name == ""
        assert profile.role == ""

    async def test_update_profile(self, service: MemoryService):
        profile = UserProfile(name="Alice", role="developer")
        await service.update_user_profile(profile)

        loaded = await service.get_user_profile()
        assert loaded.name == "Alice"
        assert loaded.role == "developer"

    async def test_merge_profiles(self, service: MemoryService):
        p1 = UserProfile(name="Alice", preferences={"theme": "dark"})
        await service.update_user_profile(p1)

        p2 = UserProfile(role="dev", preferences={"lang": "python"})
        await service.update_user_profile(p2)

        loaded = await service.get_user_profile()
        assert loaded.name == "Alice"
        assert loaded.role == "dev"
        assert loaded.preferences["theme"] == "dark"
        assert loaded.preferences["lang"] == "python"


class TestMemoryServiceNudge:
    async def test_nudge_threshold(self, service: MemoryService):
        # Default threshold is 5
        for i in range(4):
            assert await service.nudge("session1") is False
        assert await service.nudge("session1") is True

    async def test_nudge_resets(self, service: MemoryService):
        for i in range(5):
            await service.nudge("session1")
        # After triggering, should reset
        for i in range(4):
            assert await service.nudge("session1") is False
        assert await service.nudge("session1") is True

    async def test_nudge_per_session(self, service: MemoryService):
        for i in range(5):
            await service.nudge("session1")
        # session2 should have its own counter
        assert await service.nudge("session2") is False


class TestMemoryServiceFlush:
    async def test_flush_preferences(self, service: MemoryService):
        messages = [
            {"role": "user", "content": "I prefer dark mode and I always use vim."},
        ]
        saved = await service.flush_memories("session1", messages)
        assert len(saved) > 0

    async def test_flush_skips_short(self, service: MemoryService):
        messages = [
            {"role": "user", "content": "ok"},
        ]
        saved = await service.flush_memories("session1", messages)
        assert len(saved) == 0

    async def test_flush_skips_assistant(self, service: MemoryService):
        messages = [
            {"role": "assistant", "content": "I prefer dark mode and always use vim."},
        ]
        saved = await service.flush_memories("session1", messages)
        assert len(saved) == 0


class TestExtractMemoryCandidates:
    def test_preference_extraction(self):
        messages = [{"role": "user", "content": "I prefer dark mode in my editor."}]
        candidates = _extract_memory_candidates(messages)
        assert len(candidates) >= 1
        assert candidates[0][1] == MemoryCategory.USER_PREF

    def test_project_extraction(self):
        messages = [
            {"role": "user", "content": "The project uses SQLAlchemy as the ORM."}
        ]
        candidates = _extract_memory_candidates(messages)
        assert len(candidates) >= 1

    def test_deduplication(self):
        messages = [
            {"role": "user", "content": "I prefer dark mode in my editor."},
            {"role": "user", "content": "I prefer dark mode in my editor."},
        ]
        candidates = _extract_memory_candidates(messages)
        # Should be deduplicated
        contents = [c[0] for c in candidates]
        assert len(contents) == len(set(contents))

    def test_skip_non_user(self):
        messages = [
            {"role": "assistant", "content": "I prefer dark mode in my editor."},
        ]
        candidates = _extract_memory_candidates(messages)
        assert len(candidates) == 0
