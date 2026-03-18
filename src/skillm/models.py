"""Data models for skillm."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Skill:
    id: int | None = None
    repo: str = ""
    name: str = ""
    description: str = ""
    category: str = ""
    author: str = ""
    source: str = ""
    commit: str = ""
    updated_at: str = ""
    tags: list[str] = field(default_factory=list)
    file_count: int = 0
    total_size: int = 0


@dataclass
class SkillMeta:
    """Metadata extracted from SKILL.md."""
    name: str = ""
    description: str = ""
    category: str = ""
    tags: list[str] = field(default_factory=list)
    author: str = ""
    source: str = ""
    requires: dict | list = field(default_factory=dict)
    content: str = ""
