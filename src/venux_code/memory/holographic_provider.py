"""Advanced memory provider with FTS5 full-text search, entity resolution,
trust scoring, and semantic keyword extraction.

Uses a single SQLite database with FTS5 virtual tables for fast full-text
search and cosine-similarity–based deduplication.
"""

from __future__ import annotations

import json
import logging
import math
import re
import uuid
from collections import Counter
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
    keywords    TEXT NOT NULL DEFAULT '[]',
    source_session_id TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content, tags, keywords,
    content='memories',
    content_rowid='rowid'
);

CREATE TABLE IF NOT EXISTS user_profile (
    id   INTEGER PRIMARY KEY CHECK (id = 1),
    data TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS trust_feedback (
    id         TEXT PRIMARY KEY,
    memory_id  TEXT NOT NULL,
    positive   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""

# Keep FTS in sync via triggers
_FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, tags, keywords)
    VALUES (new.rowid, new.content, new.tags, new.keywords);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, tags, keywords)
    VALUES ('delete', old.rowid, old.content, old.tags, old.keywords);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, tags, keywords)
    VALUES ('delete', old.rowid, old.content, old.tags, old.keywords);
    INSERT INTO memories_fts(rowid, content, tags, keywords)
    VALUES (new.rowid, new.content, new.tags, new.keywords);
END;
"""

# ── Keyword extraction (TF-IDF inspired, lightweight) ──────────────────────

_STOP_WORDS = frozenset(
    "the a an is are was were be been being have has had do does did "
    "will would shall should may might can could i me my we our you your "
    "he she it they them their this that these those and but or nor for "
    "so yet at by in of to with from as into on onto off out up about "
    "above after again all also am any because before between both each "
    "few more most other some such than too very just not no now only "
    "then there here when where which while who whom how what why if "
    "its let s t d re ve ll m don isn wasn aren doesn didn won wouldn ".split()
)


def _extract_keywords(text: str, top_n: int = 10) -> list[str]:
    """Extract the most salient keywords from *text* using simple TF ranking."""
    words = re.findall(r"[a-zA-Z_]\w{2,}", text.lower())
    counts = Counter(w for w in words if w not in _STOP_WORDS)
    return [word for word, _ in counts.most_common(top_n)]


def _tokenize(text: str) -> set[str]:
    """Lowercase alphanumeric tokens."""
    return set(re.findall(r"[a-zA-Z_]\w{2,}", text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


# ── Provider ───────────────────────────────────────────────────────────────


class HolographicMemoryProvider:
    """Advanced memory provider with FTS5, entity resolution, trust scoring."""

    DUPLICATE_THRESHOLD: float = 0.6  # Jaccard similarity above this → merge

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".venux-code" / "holographic_memory.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, MemoryEntry] = {}
        self._keywords_cache: dict[str, list[str]] = {}
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
            await self._db.executescript(_FTS_TRIGGERS)
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
                self._keywords_cache[entry.id] = json.loads(row["keywords"])

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
        self._cache.clear()
        self._keywords_cache.clear()
        self._initialised = False

    # ── Entity resolution ──────────────────────────────────────────────────

    async def _resolve_duplicate(self, entry: MemoryEntry) -> Optional[MemoryEntry]:
        """Check if a similar memory already exists; if so, merge and return it."""
        new_tokens = _tokenize(entry.content)
        for existing in self._cache.values():
            if existing.category != entry.category:
                continue
            existing_tokens = _tokenize(existing.content)
            sim = _jaccard(new_tokens, existing_tokens)
            if sim >= self.DUPLICATE_THRESHOLD:
                # Merge: keep longer content, boost trust, combine tags
                if len(entry.content) > len(existing.content):
                    existing.content = entry.content
                existing.tags = list(set(existing.tags + entry.tags))
                existing.trust_score = min(1.0, existing.trust_score + 0.05)
                existing.touch()
                await self.update(existing)
                logger.debug("Merged duplicate memory %s → %s", entry.id[:8], existing.id[:8])
                return existing
        return None

    # ── CRUD ───────────────────────────────────────────────────────────────

    async def add(self, entry: MemoryEntry) -> MemoryEntry:
        db = await self._ensure_db()

        # Entity resolution
        merged = await self._resolve_duplicate(entry)
        if merged is not None:
            return merged

        keywords = _extract_keywords(entry.content)
        self._keywords_cache[entry.id] = keywords

        await db.execute(
            "INSERT INTO memories (id, content, category, tags, trust_score, "
            "keywords, source_session_id, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                entry.id,
                entry.content,
                entry.category.value,
                json.dumps(entry.tags),
                entry.trust_score,
                json.dumps(keywords),
                entry.source_session_id,
                entry.created_at.isoformat(),
                entry.updated_at.isoformat(),
            ),
        )
        await db.commit()
        self._cache[entry.id] = entry
        return entry

    async def get(self, entry_id: str) -> Optional[MemoryEntry]:
        await self._ensure_db()
        return self._cache.get(entry_id)

    async def update(self, entry: MemoryEntry) -> MemoryEntry:
        db = await self._ensure_db()
        keywords = _extract_keywords(entry.content)
        self._keywords_cache[entry.id] = keywords
        await db.execute(
            "UPDATE memories SET content=?, category=?, tags=?, trust_score=?, "
            "keywords=?, updated_at=? WHERE id=?",
            (
                entry.content,
                entry.category.value,
                json.dumps(entry.tags),
                entry.trust_score,
                json.dumps(keywords),
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
        self._keywords_cache.pop(entry_id, None)
        return cursor.rowcount > 0

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[MemoryEntry]:
        await self._ensure_db()
        items = sorted(self._cache.values(), key=lambda e: e.created_at, reverse=True)
        return items[offset : offset + limit]

    # ── FTS5 search ────────────────────────────────────────────────────────

    async def search(
        self, query: str, limit: int = 10, min_trust: float = 0.0
    ) -> list[MemoryEntry]:
        """Full-text search via SQLite FTS5, with trust-score filtering."""
        db = await self._ensure_db()

        # Sanitise FTS5 query – keep alphanumeric tokens and add OR between them
        tokens = re.findall(r"[a-zA-Z_]\w+", query)
        if not tokens:
            return []
        fts_query = " OR ".join(tokens)

        try:
            sql = (
                "SELECT m.*, rank FROM memories m "
                "JOIN memories_fts fts ON m.rowid = fts.rowid "
                "WHERE memories_fts MATCH ? "
                "ORDER BY rank"
            )
            cursor = await db.execute(sql, (fts_query,))
            rows = await cursor.fetchall()
        except Exception:
            # Fallback to cache keyword search if FTS fails
            logger.warning("FTS5 query failed, falling back to keyword search")
            return await self._keyword_search(query, limit, min_trust)

        results: list[MemoryEntry] = []
        for row in rows:
            entry = self._row_to_entry(row)
            if entry.trust_score >= min_trust:
                results.append(entry)
            if len(results) >= limit:
                break
        return results

    async def _keyword_search(
        self, query: str, limit: int, min_trust: float
    ) -> list[MemoryEntry]:
        terms = query.lower().split()
        scored: list[tuple[float, MemoryEntry]] = []
        for entry in self._cache.values():
            if entry.trust_score < min_trust:
                continue
            kws = self._keywords_cache.get(entry.id, [])
            haystack = f"{entry.content} {' '.join(entry.tags)} {' '.join(kws)}".lower()
            hits = sum(1 for t in terms if t in haystack)
            if hits > 0:
                scored.append((hits + entry.trust_score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:limit]]

    # ── Trust scoring ──────────────────────────────────────────────────────

    async def record_feedback(self, memory_id: str, positive: bool) -> None:
        """Record user feedback (👍/👎) and adjust trust score."""
        db = await self._ensure_db()
        await db.execute(
            "INSERT INTO trust_feedback (id, memory_id, positive, created_at) "
            "VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), memory_id, int(positive), datetime.now(timezone.utc).isoformat()),
        )
        # Recalculate trust score
        cursor = await db.execute(
            "SELECT SUM(positive), COUNT(*) FROM trust_feedback WHERE memory_id=?",
            (memory_id,),
        )
        row = await cursor.fetchone()
        assert row is not None
        total = row[1] or 0
        positives = row[0] or 0
        if total > 0:
            # Wilson score lower bound (simplified)
            n = total
            p = positives / n
            z = 1.96  # 95% confidence
            denominator = 1 + z * z / n
            centre = p + z * z / (2 * n)
            spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
            trust = max(0.0, min(1.0, (centre - spread) / denominator))
        else:
            trust = 0.5

        entry = self._cache.get(memory_id)
        if entry is not None:
            entry.trust_score = trust
            entry.touch()
            await db.execute(
                "UPDATE memories SET trust_score=?, updated_at=? WHERE id=?",
                (trust, entry.updated_at.isoformat(), memory_id),
            )
            await db.commit()

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
