"""Data models for skillm."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Skill:
    id: int | None = None
    name: str = ""
    description: str = ""
    category: str = ""
    author: str = ""
    source: str = ""
    head_commit: str = ""
    created_at: str = ""
    updated_at: str = ""
    tags: list[str] = field(default_factory=list)
    versions: list[Version] = field(default_factory=list)


@dataclass
class Version:
    id: int | None = None
    skill_id: int | None = None
    version: str = ""
    git_tag: str = ""
    commit_hash: str = ""
    published_at: str = ""


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
