"""Skill loader – reads SKILL.md files from user/project directories and remote URLs."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import aiohttp

from venux_code.skills.models import Skill, SkillSource

logger = logging.getLogger(__name__)

_DEFAULT_USER_SKILLS_DIR = Path.home() / ".venux-code" / "skills"
_DEFAULT_PROJECT_SKILLS_DIR = Path(".venux-code") / "skills"
_DEFAULT_HUB_BASE_URL = "https://hub.venux-code.dev/skills"

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)


class SkillLoader:
    """Discover and load SKILL.md files from multiple locations.

    Parameters
    ----------
    user_skills_dir:
        User-level skills directory (default: ``~/.venux-code/skills/``).
    project_skills_dir:
        Project-level skills directory (default: ``.venux-code/skills/``).
    hub_base_url:
        Base URL for the skill hub (default: ``https://hub.venux-code.dev/skills``).
    """

    def __init__(
        self,
        user_skills_dir: str | Path | None = None,
        project_skills_dir: str | Path | None = None,
        hub_base_url: str | None = None,
    ) -> None:
        self._user_dir = Path(user_skills_dir) if user_skills_dir else _DEFAULT_USER_SKILLS_DIR
        self._project_dir = Path(project_skills_dir) if project_skills_dir else _DEFAULT_PROJECT_SKILLS_DIR
        self._hub_url = (hub_base_url or _DEFAULT_HUB_BASE_URL).rstrip("/")

    # ── Load all from disk ─────────────────────────────────────────────────

    async def load_all(self) -> list[Skill]:
        """Load skills from both user and project directories."""
        skills: list[Skill] = []
        skills.extend(await self._load_from_dir(self._user_dir, SkillSource.LOCAL))
        skills.extend(await self._load_from_dir(self._project_dir, SkillSource.PROJECT))
        return skills

    async def _load_from_dir(
        self, directory: Path, source: SkillSource
    ) -> list[Skill]:
        """Scan *directory* for SKILL.md files (one per subdirectory or at root)."""
        skills: list[Skill] = []
        if not directory.is_dir():
            return skills

        # Pattern 1: directory/SKILL.md (each subdir is a skill)
        for child in sorted(directory.iterdir()):
            if child.is_dir():
                skill_file = child / "SKILL.md"
                if skill_file.is_file():
                    skill = self._parse_skill_file(skill_file, source)
                    if skill:
                        skills.append(skill)
            elif child.is_file() and child.suffix == ".md":
                # Pattern 2: individual .md files at root
                skill = self._parse_skill_file(child, source)
                if skill:
                    skills.append(skill)

        return skills

    def _parse_skill_file(
        self, path: Path, source: SkillSource
    ) -> Optional[Skill]:
        """Parse a single SKILL.md file into a :class:`Skill`."""
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to read %s: %s", path, exc)
            return None

        metadata, body = _split_frontmatter(raw)
        name = metadata.get("name", path.stem.replace("SKILL", "").strip("-_ ") or path.parent.name)
        if not name:
            name = path.stem

        return Skill(
            name=name,
            description=metadata.get("description", ""),
            content=body.strip(),
            category=metadata.get("category", "general"),
            tags=[t.strip() for t in metadata.get("tags", "").split(",") if t.strip()],
            version=metadata.get("version", "1.0.0"),
            source=source,
            file_path=str(path),
        )

    # ── Remote / Hub ───────────────────────────────────────────────────────

    async def fetch_remote(self, url: str) -> str:
        """Fetch raw content from a remote URL."""
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                return await resp.text()

    async def fetch_hub_skill(self, name: str) -> str:
        """Fetch a skill's markdown content from the hub by name."""
        url = f"{self._hub_url}/{name}/SKILL.md"
        return await self.fetch_remote(url)


# ── Helpers ────────────────────────────────────────────────────────────────


def _split_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    """Split YAML-like frontmatter from the body of a markdown file.

    Returns ``(metadata_dict, body)``.
    """
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw

    fm_text = match.group(1)
    body = raw[match.end():]
    metadata: dict[str, str] = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            metadata[key.strip().lower()] = value.strip()
    return metadata, body
