"""Data models for skillm."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Skill:
    id: int | None = None
    name: str = ""
    description: str = ""
    category: str = ""
    author: str = ""
    source: str = ""
    created_at: str = ""
    updated_at: str = ""
    tags: list[str] = field(default_factory=list)
    versions: list[Version] = field(default_factory=list)


@dataclass
class Version:
    id: int | None = None
    skill_id: int | None = None
    version: str = ""
    changelog: str = ""
    file_count: int = 0
    total_size: int = 0
    published_at: str = ""


@dataclass
class FileRecord:
    id: int | None = None
    version_id: int | None = None
    rel_path: str = ""
    size: int = 0
    sha256: str = ""


@dataclass
class SkillMeta:
    """Metadata extracted from SKILL.md."""
    name: str = ""
    description: str = ""
    category: str = ""
    tags: list[str] = field(default_factory=list)
    author: str = ""
    source: str = ""
    requires: list[str] = field(default_factory=list)
    content: str = ""
