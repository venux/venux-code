"""High-level MemoryService – orchestrates memory CRUD, search, nudge, and flush."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, Sequence

from venux_code.memory.models import MemoryCategory, MemoryEntry, UserProfile

logger = logging.getLogger(__name__)

# ── Provider protocol ──────────────────────────────────────────────────────


class MemoryProvider(Protocol):
    """Interface that storage backends must implement."""

    async def add(self, entry: MemoryEntry) -> MemoryEntry: ...

    async def get(self, entry_id: str) -> Optional[MemoryEntry]: ...

    async def update(self, entry: MemoryEntry) -> MemoryEntry: ...

    async def remove(self, entry_id: str) -> bool: ...

    async def search(
        self, query: str, limit: int = 10, min_trust: float = 0.0
    ) -> list[MemoryEntry]: ...

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[MemoryEntry]: ...

    async def load_user_profile(self) -> UserProfile: ...

    async def save_user_profile(self, profile: UserProfile) -> None: ...

    async def close(self) -> None: ...


# ── Service ────────────────────────────────────────────────────────────────


class MemoryService:
    """Facade that exposes memory operations to the rest of the application.

    Parameters
    ----------
    provider:
        A concrete ``MemoryProvider`` implementation (e.g. built-in SQLite or
        holographic provider).
    nudge_threshold:
        Minimum number of user messages before :meth:`nudge` returns ``True``.
    """

    def __init__(
        self,
        provider: MemoryProvider,
        *,
        nudge_threshold: int = 5,
    ) -> None:
        self._provider = provider
        self._nudge_threshold = nudge_threshold
        self._message_counts: dict[str, int] = {}

    # ── CRUD ───────────────────────────────────────────────────────────────

    async def add(
        self,
        content: str,
        category: MemoryCategory | str = MemoryCategory.GENERAL,
        tags: Optional[list[str]] = None,
        *,
        source_session_id: Optional[str] = None,
        trust_score: float = 0.5,
    ) -> MemoryEntry:
        """Create and persist a new memory entry."""
        if isinstance(category, str):
            category = MemoryCategory(category)
        entry = MemoryEntry(
            content=content,
            category=category,
            tags=tags or [],
            trust_score=trust_score,
            source_session_id=source_session_id,
        )
        saved = await self._provider.add(entry)
        logger.info("Memory added: %s [%s]", saved.id[:8], category.value)
        return saved

    async def search(
        self,
        query: str,
        limit: int = 10,
        min_trust: float = 0.0,
    ) -> list[MemoryEntry]:
        """Search memories by keyword / semantic similarity."""
        return await self._provider.search(query, limit=limit, min_trust=min_trust)

    async def update(self, entry_id: str, content: str) -> Optional[MemoryEntry]:
        """Update the content of an existing entry."""
        entry = await self._provider.get(entry_id)
        if entry is None:
            return None
        entry.content = content
        entry.touch()
        return await self._provider.update(entry)

    async def remove(self, entry_id: str) -> bool:
        """Delete a memory entry. Returns ``True`` if removed."""
        return await self._provider.remove(entry_id)

    async def get(self, entry_id: str) -> Optional[MemoryEntry]:
        """Fetch a single entry by id."""
        return await self._provider.get(entry_id)

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[MemoryEntry]:
        """List memories with pagination."""
        return await self._provider.list_all(limit=limit, offset=offset)

    # ── User profile ───────────────────────────────────────────────────────

    async def get_user_profile(self) -> UserProfile:
        """Return the persisted user profile."""
        return await self._provider.load_user_profile()

    async def update_user_profile(self, profile: UserProfile) -> None:
        """Merge *profile* into the persisted one and save."""
        existing = await self._provider.load_user_profile()
        merged = existing.merge(profile)
        await self._provider.save_user_profile(merged)

    # ── Nudge ──────────────────────────────────────────────────────────────

    async def nudge(self, session_id: str) -> bool:
        """Return ``True`` when the agent should consider saving memories.

        Tracks per-session user message count and triggers after
        ``nudge_threshold`` messages.
        """
        count = self._message_counts.get(session_id, 0) + 1
        self._message_counts[session_id] = count
        if count >= self._nudge_threshold:
            self._message_counts[session_id] = 0
            return True
        return False

    # ── Flush ──────────────────────────────────────────────────────────────

    async def flush_memories(
        self,
        session_id: str,
        messages: Sequence[dict[str, Any]],
    ) -> list[MemoryEntry]:
        """Extract salient information from *messages* and persist as memories.

        Each message dict is expected to have ``role`` and ``content`` keys.

        The extraction is heuristic-based (keyword / pattern matching).  When
        an LLM is available upstream callers should pre-extract and pass
        structured hints via the ``tags`` convention.
        """
        extracted = _extract_memory_candidates(messages)
        saved: list[MemoryEntry] = []
        for content, category, tags in extracted:
            entry = await self.add(
                content,
                category=category,
                tags=tags,
                source_session_id=session_id,
                trust_score=0.6,
            )
            saved.append(entry)
        if saved:
            logger.info("Flushed %d memories from session %s", len(saved), session_id[:8])
        return saved

    async def close(self) -> None:
        """Release provider resources."""
        await self._provider.close()


# ── Extraction helpers ─────────────────────────────────────────────────────

_PREFERENCE_PATTERNS: list[tuple[str, MemoryCategory]] = [
    (r"\b(prefer|like|love|enjoy|hate|dislike)\b", MemoryCategory.USER_PREF),
    (r"\b(always|never)\s+\w+", MemoryCategory.USER_PREF),
    (r"\bmy (name|role|team|language)\b", MemoryCategory.USER_PREF),
]

_PROJECT_PATTERNS: list[tuple[str, MemoryCategory]] = [
    (r"\b(framework|library|package|dependency)\b", MemoryCategory.PROJECT),
    (r"\b(repo|project|codebase)\b", MemoryCategory.PROJECT),
    (r"\b(config|env|\.json|\.yaml|\.toml)\b", MemoryCategory.PROJECT),
]

_TOOL_PATTERNS: list[tuple[str, MemoryCategory]] = [
    (r"\b(tool|command|script|plugin)\b", MemoryCategory.TOOL),
    (r"\b(brew|npm|pip|apt|cargo)\b", MemoryCategory.TOOL),
]


def _extract_memory_candidates(
    messages: Sequence[dict[str, Any]],
) -> list[tuple[str, MemoryCategory, list[str]]]:
    """Heuristic extraction of memory-worthy facts from conversation messages."""
    candidates: list[tuple[str, MemoryCategory, list[str]]] = []
    for msg in messages:
        if msg.get("role") != "user":
            continue
        text: str = msg.get("content", "")
        if len(text) < 20:
            continue
        category = _classify_text(text)
        tags = _extract_tags(text)
        # Only keep reasonably specific sentences
        sentences = re.split(r"[.!?\n]+", text)
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 15:
                continue
            if any(re.search(p, sentence, re.IGNORECASE) for p, _ in _PREFERENCE_PATTERNS):
                candidates.append((sentence, MemoryCategory.USER_PREF, tags))
            elif any(re.search(p, sentence, re.IGNORECASE) for p, _ in _PROJECT_PATTERNS):
                candidates.append((sentence, MemoryCategory.PROJECT, tags))
            elif any(re.search(p, sentence, re.IGNORECASE) for p, _ in _TOOL_PATTERNS):
                candidates.append((sentence, MemoryCategory.TOOL, tags))
    # Deduplicate by content
    seen: set[str] = set()
    unique: list[tuple[str, MemoryCategory, list[str]]] = []
    for content, cat, tags in candidates:
        key = content.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append((content, cat, tags))
    return unique


def _classify_text(text: str) -> MemoryCategory:
    """Return the most likely category for *text*."""
    for pattern, cat in _PREFERENCE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return cat
    for pattern, cat in _PROJECT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return cat
    for pattern, cat in _TOOL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return cat
    return MemoryCategory.GENERAL


def _extract_tags(text: str) -> list[str]:
    """Pull simple keyword tags from *text*."""
    tags: list[str] = []
    # File extensions
    for m in re.finditer(r"\.\w{1,5}\b", text):
        tags.append(m.group())
    # Quoted terms
    for m in re.finditer(r'"([^"]+)"', text):
        tags.append(m.group(1))
    # #hashtags
    for m in re.finditer(r"#(\w+)", text):
        tags.append(m.group(1))
    return list(set(tags))
