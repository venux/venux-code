"""Simple in-memory + SQLite-persisted memory provider.

This is the default, lightweight provider.  Data is kept in an in-process dict
for fast reads and periodically flushed to a local SQLite database so memories
survive restarts.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

from venux_code.memory.models import MemoryCategory, MemoryEntry, UserProfile

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,
    content     TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'general',
    tags        TEXT NOT NULL DEFAULT '[]',
    trust_score REAL NOT NULL DEFAULT 0.5,
    source_session_id TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_profile (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    data        TEXT NOT NULL DEFAULT '{}'
);
"""


class BuiltinMemoryProvider:
    """Lightweight SQLite-backed provider with an in-memory read cache."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".venux-code" / "memory.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, MemoryEntry] = {}
        self._profile_cache: Optional[UserProfile] = None
        self._db: Optional[aiosqlite.Connection] = None
        self._initialised = False

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def _ensure_db(self) -> aiosqlite.Connection:
        if self._db is None:
            self._db = await aiosqlite.connect(str(self._db_path))
            self._db.row_factory = aiosqlite.Row
        if not self._initialised:
            await self._db.executescript(_SCHEMA)
            await self._db.commit()
            await self._load_cache()
            self._initialised = True
        return self._db

    async def _load_cache(self) -> None:
        assert self._db is not None
        async with self._db.execute("SELECT * FROM memories") as cursor:
            async for row in cursor:
                entry = self._row_to_entry(row)
                self._cache[entry.id] = entry

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
        self._cache.clear()
        self._initialised = False

    # ── CRUD ───────────────────────────────────────────────────────────────

    async def add(self, entry: MemoryEntry) -> MemoryEntry:
        db = await self._ensure_db()
        await db.execute(
            "INSERT INTO memories (id, content, category, tags, trust_score, "
            "source_session_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            self._entry_to_params(entry),
        )
        await db.commit()
        self._cache[entry.id] = entry
        return entry

    async def get(self, entry_id: str) -> Optional[MemoryEntry]:
        await self._ensure_db()
        return self._cache.get(entry_id)

    async def update(self, entry: MemoryEntry) -> MemoryEntry:
        db = await self._ensure_db()
        await db.execute(
            "UPDATE memories SET content=?, category=?, tags=?, trust_score=?, "
            "updated_at=? WHERE id=?",
            (
                entry.content,
                entry.category.value,
                json.dumps(entry.tags),
                entry.trust_score,
                entry.updated_at.isoformat(),
                entry.id,
            ),
        )
        await db.commit()
        self._cache[entry.id] = entry
        return entry

    async def remove(self, entry_id: str) -> bool:
        db = await self._ensure_db()
        cursor = await db.execute("DELETE FROM memories WHERE id=?", (entry_id,))
        await db.commit()
        self._cache.pop(entry_id, None)
        return cursor.rowcount > 0

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[MemoryEntry]:
        await self._ensure_db()
        items = sorted(self._cache.values(), key=lambda e: e.created_at, reverse=True)
        return items[offset : offset + limit]

    # ── Search ─────────────────────────────────────────────────────────────

    async def search(
        self, query: str, limit: int = 10, min_trust: float = 0.0
    ) -> list[MemoryEntry]:
        """Simple keyword search over the in-memory cache."""
        await self._ensure_db()
        terms = query.lower().split()
        scored: list[tuple[float, MemoryEntry]] = []
        for entry in self._cache.values():
            if entry.trust_score < min_trust:
                continue
            haystack = f"{entry.content} {' '.join(entry.tags)}".lower()
            hits = sum(1 for t in terms if t in haystack)
            if hits > 0:
                scored.append((hits + entry.trust_score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:limit]]

    # ── User profile ───────────────────────────────────────────────────────

    async def load_user_profile(self) -> UserProfile:
        if self._profile_cache is not None:
            return self._profile_cache
        db = await self._ensure_db()
        async with db.execute("SELECT data FROM user_profile WHERE id=1") as cursor:
            row = await cursor.fetchone()
        if row is None:
            self._profile_cache = UserProfile()
            return self._profile_cache
        self._profile_cache = UserProfile.model_validate_json(row["data"])
        return self._profile_cache

    async def save_user_profile(self, profile: UserProfile) -> None:
        db = await self._ensure_db()
        await db.execute(
            "INSERT OR REPLACE INTO user_profile (id, data) VALUES (1, ?)",
            (profile.model_dump_json(),),
        )
        await db.commit()
        self._profile_cache = profile

    # ── Serialisation helpers ──────────────────────────────────────────────

    @staticmethod
    def _entry_to_params(entry: MemoryEntry) -> tuple:
        return (
            entry.id,
            entry.content,
            entry.category.value,
            json.dumps(entry.tags),
            entry.trust_score,
            entry.source_session_id,
            entry.created_at.isoformat(),
            entry.updated_at.isoformat(),
        )

    @staticmethod
    def _row_to_entry(row: aiosqlite.Row) -> MemoryEntry:
        return MemoryEntry(
            id=row["id"],
            content=row["content"],
            category=MemoryCategory(row["category"]),
            tags=json.loads(row["tags"]),
            trust_score=row["trust_score"],
            source_session_id=row["source_session_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
