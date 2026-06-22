"""High-level SkillService – manages skill CRUD, installation, and auto-creation."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence

import aiosqlite

from venux_code.skills.loader import SkillLoader
from venux_code.skills.models import Skill, SkillSource

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'general',
    tags        TEXT NOT NULL DEFAULT '[]',
    version     TEXT NOT NULL DEFAULT '1.0.0',
    source      TEXT NOT NULL DEFAULT 'local',
    enabled     INTEGER NOT NULL DEFAULT 1,
    file_path   TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


class SkillService:
    """Manage skills: CRUD, install from hub/URL, and auto-create from conversation.

    Parameters
    ----------
    db_path:
        Path to the SQLite database for skill persistence.
    loader:
        Optional custom :class:`SkillLoader`.  A default one is created if
        not provided.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        loader: Optional[SkillLoader] = None,
    ) -> None:
        if db_path is None:
            db_path = Path.home() / ".venux-code" / "skills.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._loader = loader or SkillLoader()
        self._cache: dict[str, Skill] = {}
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
        async with self._db.execute("SELECT * FROM skills") as cursor:
            async for row in cursor:
                skill = self._row_to_skill(row)
                self._cache[skill.name] = skill

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
        self._cache.clear()
        self._initialised = False

    # ── List / Get ─────────────────────────────────────────────────────────

    async def list_skills(
        self,
        *,
        category: Optional[str] = None,
        enabled_only: bool = True,
    ) -> list[Skill]:
        """Return all skills, optionally filtered by category."""
        await self._ensure_db()
        # Merge file-based skills from loader
        await self._sync_file_skills()
        results = list(self._cache.values())
        if enabled_only:
            results = [s for s in results if s.enabled]
        if category:
            results = [s for s in results if s.category == category]
        results.sort(key=lambda s: s.name)
        return results

    async def get(self, name: str) -> Optional[Skill]:
        """Fetch a skill by name."""
        await self._ensure_db()
        await self._sync_file_skills()
        return self._cache.get(name)

    async def load_skill(self, name: str) -> Optional[str]:
        """Return the content of a skill for injection into the LLM context.

        Returns ``None`` if the skill is not found or disabled.
        """
        skill = await self.get(name)
        if skill is None or not skill.enabled:
            return None
        return skill.content

    # ── Create / Update ────────────────────────────────────────────────────

    async def create(
        self,
        name: str,
        content: str,
        category: str = "general",
        *,
        description: str = "",
        tags: Optional[list[str]] = None,
        version: str = "1.0.0",
        source: SkillSource = SkillSource.LOCAL,
    ) -> Skill:
        """Create a new skill and persist it."""
        await self._ensure_db()
        skill = Skill(
            name=name,
            description=description,
            content=content,
            category=category,
            tags=tags or [],
            version=version,
            source=source,
        )
        db = await self._ensure_db()
        await db.execute(
            "INSERT INTO skills (id, name, description, content, category, tags, "
            "version, source, enabled, file_path, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            self._skill_to_params(skill),
        )
        await db.commit()
        self._cache[skill.name] = skill
        logger.info("Skill created: %s", name)
        return skill

    async def uninstall(self, name: str) -> bool:
        """Remove a skill by name. Returns ``True`` if deleted."""
        db = await self._ensure_db()
        cursor = await db.execute("DELETE FROM skills WHERE name=?", (name,))
        await db.commit()
        removed = self._cache.pop(name, None)
        # Also remove file if it was a file-based skill
        if removed and removed.file_path:
            p = Path(removed.file_path)
            if p.exists():
                p.unlink()
                logger.info("Deleted skill file: %s", p)
        return cursor.rowcount > 0 or removed is not None

    # ── Install from remote ────────────────────────────────────────────────

    async def install(self, name_or_url: str) -> Skill:
        """Install a skill from a remote URL or hub name.

        If *name_or_url* looks like a URL, fetch its content directly.
        Otherwise treat it as a hub skill name and resolve via the loader.
        """
        if name_or_url.startswith(("http://", "https://")):
            content = await self._loader.fetch_remote(name_or_url)
            name = _name_from_url(name_or_url)
            description = f"Installed from {name_or_url}"
            source = SkillSource.HUB
        else:
            content = await self._loader.fetch_hub_skill(name_or_url)
            name = name_or_url
            description = f"Hub skill: {name_or_url}"
            source = SkillSource.HUB

        # Check if already installed
        existing = self._cache.get(name)
        if existing:
            existing.content = content
            existing.touch()
            db = await self._ensure_db()
            await db.execute(
                "UPDATE skills SET content=?, updated_at=? WHERE name=?",
                (content, existing.updated_at.isoformat(), name),
            )
            await db.commit()
            logger.info("Skill updated: %s", name)
            return existing

        return await self.create(
            name=name,
            content=content,
            description=description,
            source=source,
        )

    # ── Auto-create from conversation ──────────────────────────────────────

    async def auto_create(
        self,
        session_id: str,
        conversation: Sequence[dict[str, Any]],
    ) -> Optional[Skill]:
        """Extract a reusable procedure from a conversation and save as a skill.

        Each message dict should have ``role`` and ``content`` keys.

        Returns the created skill, or ``None`` if no reusable procedure was
        detected.
        """
        procedure = _extract_procedure(conversation)
        if procedure is None:
            return None

        name, content, category = procedure
        # Ensure uniqueness
        base_name = name
        counter = 1
        while name in self._cache:
            name = f"{base_name}-{counter}"
            counter += 1

        skill = await self.create(
            name=name,
            content=content,
            category=category,
            description=f"Auto-extracted from session {session_id[:8]}",
            source=SkillSource.AUTO,
            tags=["auto-generated"],
        )
        logger.info("Auto-created skill: %s from session %s", name, session_id[:8])
        return skill

    # ── File skill sync ────────────────────────────────────────────────────

    async def _sync_file_skills(self) -> None:
        """Load SKILL.md files from disk via the loader and merge into cache."""
        file_skills = await self._loader.load_all()
        for skill in file_skills:
            existing = self._cache.get(skill.name)
            if existing is None:
                # New file-based skill – persist to DB
                db = await self._ensure_db()
                await db.execute(
                    "INSERT OR IGNORE INTO skills (id, name, description, content, "
                    "category, tags, version, source, enabled, file_path, "
                    "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    self._skill_to_params(skill),
                )
                await db.commit()
                self._cache[skill.name] = skill
            elif existing.file_path and existing.file_path != skill.file_path:
                pass  # DB version takes priority

    # ── Serialisation helpers ──────────────────────────────────────────────

    @staticmethod
    def _skill_to_params(skill: Skill) -> tuple:
        return (
            skill.id,
            skill.name,
            skill.description,
            skill.content,
            skill.category,
            json.dumps(skill.tags),
            skill.version,
            skill.source.value,
            int(skill.enabled),
            skill.file_path,
            skill.created_at.isoformat(),
            skill.updated_at.isoformat(),
        )

    @staticmethod
    def _row_to_skill(row: aiosqlite.Row) -> Skill:
        return Skill(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            content=row["content"],
            category=row["category"],
            tags=json.loads(row["tags"]),
            version=row["version"],
            source=SkillSource(row["source"]),
            enabled=bool(row["enabled"]),
            file_path=row["file_path"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


# ── Helpers ────────────────────────────────────────────────────────────────


def _name_from_url(url: str) -> str:
    """Derive a skill name from a URL."""
    path = url.rstrip("/").rsplit("/", 1)[-1]
    name = path.replace(".md", "").replace("SKILL", "").strip("-_ ")
    return name or str(uuid.uuid4())[:8]


def _extract_procedure(
    conversation: Sequence[dict[str, Any]],
) -> Optional[tuple[str, str, str]]:
    """Heuristic: detect multi-step tool-use patterns in the conversation.

    Returns ``(name, markdown_content, category)`` or ``None``.
    """
    tool_calls: list[str] = []
    user_goals: list[str] = []
    assistant_summaries: list[str] = []

    for msg in conversation:
        role = msg.get("role", "")
        content = msg.get("content", "") or ""
        if role == "user" and len(content) > 10:
            user_goals.append(content[:200])
        elif role == "assistant":
            if content:
                assistant_summaries.append(content[:300])
            # Look for tool use patterns
            for m in re.finditer(r"(?:tool|function)[_\s]?call[:\s]+(\w+)", content, re.IGNORECASE):
                tool_calls.append(m.group(1))

    # Need at least 2 tool calls and a user goal to qualify as a procedure
    if len(tool_calls) < 2 or not user_goals:
        return None

    goal = user_goals[0][:100].strip()
    name = re.sub(r"[^a-zA-Z0-9\s-]", "", goal)[:50].strip().lower().replace(" ", "-")
    if not name:
        name = f"auto-procedure-{uuid.uuid4().hex[:6]}"

    # Build skill markdown
    steps = "\n".join(f"{i+1}. Use `{tc}` tool" for i, tc in enumerate(tool_calls))
    content = f"""# {goal}

## Steps
{steps}

## Notes
- Auto-generated from a conversation with {len(tool_calls)} tool calls
- Review and customise before relying on this skill
"""
    return name, content, "general"
