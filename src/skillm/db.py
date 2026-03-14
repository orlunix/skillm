"""SQLite cache database operations.

This is a pure cache — can be deleted and rebuilt from git repos.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import Skill, Version

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    name        TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    priority    INTEGER DEFAULT 10,
    last_synced TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS skills (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    source      TEXT NOT NULL REFERENCES sources(name) ON DELETE CASCADE,
    description TEXT DEFAULT '',
    category    TEXT DEFAULT '',
    author      TEXT DEFAULT '',
    head_commit TEXT DEFAULT '',
    updated_at  TEXT DEFAULT '',
    UNIQUE(name, source)
);

CREATE TABLE IF NOT EXISTS tags (
    skill_id    INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    tag         TEXT NOT NULL,
    PRIMARY KEY (skill_id, tag)
);

CREATE TABLE IF NOT EXISTS versions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id    INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    version     TEXT NOT NULL,
    git_tag     TEXT NOT NULL,
    commit_hash TEXT DEFAULT '',
    published_at TEXT DEFAULT '',
    UNIQUE(skill_id, version)
);

CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);
CREATE INDEX IF NOT EXISTS idx_skills_source ON skills(source);
CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag);
CREATE INDEX IF NOT EXISTS idx_versions_skill ON versions(skill_id);
"""


class Database:
    """SQLite cache for skill metadata. Rebuildable from git."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self) -> None:
        """Create tables and indexes."""
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def clear(self) -> None:
        """Clear all cached data."""
        self.conn.execute("DELETE FROM versions")
        self.conn.execute("DELETE FROM tags")
        self.conn.execute("DELETE FROM skills")
        self.conn.execute("DELETE FROM sources")
        self.conn.commit()

    # ── Sources ──────────────────────────────────────────────

    def upsert_source(self, name: str, url: str, priority: int = 10) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO sources(name, url, priority) VALUES(?, ?, ?)",
            (name, url, priority),
        )
        self.conn.commit()

    def update_source_synced(self, name: str, synced_at: str) -> None:
        self.conn.execute(
            "UPDATE sources SET last_synced = ? WHERE name = ?",
            (synced_at, name),
        )
        self.conn.commit()

    def get_source_synced(self, name: str) -> str:
        row = self.conn.execute(
            "SELECT last_synced FROM sources WHERE name = ?", (name,)
        ).fetchone()
        return row["last_synced"] if row else ""

    # ── Skill CRUD ───────────────────────────────────────────

    def insert_skill(self, skill: Skill) -> int:
        cur = self.conn.execute(
            "INSERT INTO skills(name, source, description, category, author, head_commit, updated_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (skill.name, skill.source, skill.description, skill.category,
             skill.author, getattr(skill, 'head_commit', ''), skill.updated_at),
        )
        skill_id = cur.lastrowid
        self.conn.commit()
        return skill_id

    def get_skill(self, name: str, source: str | None = None) -> Skill | None:
        """Get a skill by name, optionally filtered by source.

        If source is None, returns the skill from the highest-priority source.
        """
        if source:
            row = self.conn.execute(
                "SELECT * FROM skills WHERE name = ? AND source = ?",
                (name, source),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT s.* FROM skills s "
                "JOIN sources src ON s.source = src.name "
                "WHERE s.name = ? "
                "ORDER BY src.priority ASC LIMIT 1",
                (name,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_skill(row)

    def update_skill(self, skill: Skill) -> None:
        self.conn.execute(
            "UPDATE skills SET description=?, category=?, author=?, "
            "head_commit=?, updated_at=? WHERE id=?",
            (skill.description, skill.category, skill.author,
             getattr(skill, 'head_commit', ''), skill.updated_at, skill.id),
        )
        self.conn.commit()

    def delete_skill(self, name: str, source: str | None = None) -> bool:
        if source:
            cur = self.conn.execute(
                "DELETE FROM skills WHERE name = ? AND source = ?",
                (name, source),
            )
        else:
            cur = self.conn.execute(
                "DELETE FROM skills WHERE name = ?", (name,),
            )
        self.conn.commit()
        return cur.rowcount > 0

    def delete_skills_by_source(self, source: str) -> int:
        cur = self.conn.execute(
            "DELETE FROM skills WHERE source = ?", (source,),
        )
        self.conn.commit()
        return cur.rowcount

    def list_skills(self, source: str | None = None) -> list[Skill]:
        if source:
            rows = self.conn.execute(
                "SELECT * FROM skills WHERE source = ? ORDER BY name",
                (source,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM skills ORDER BY name"
            ).fetchall()
        return [self._row_to_skill(row) for row in rows]

    def _row_to_skill(self, row: sqlite3.Row) -> Skill:
        skill = Skill(
            id=row["id"], name=row["name"],
            description=row["description"],
            category=row["category"], author=row["author"],
            source=row["source"],
            updated_at=row["updated_at"],
        )
        skill.tags = self.get_tags(skill.id)
        skill.versions = self.get_versions(skill.id)
        return skill

    # ── Version CRUD ─────────────────────────────────────────

    def insert_version(self, version: Version) -> int:
        cur = self.conn.execute(
            "INSERT INTO versions(skill_id, version, git_tag, commit_hash, published_at) "
            "VALUES(?, ?, ?, ?, ?)",
            (version.skill_id, version.version,
             getattr(version, 'git_tag', ''),
             getattr(version, 'commit_hash', ''),
             version.published_at),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_versions(self, skill_id: int) -> list[Version]:
        rows = self.conn.execute(
            "SELECT * FROM versions WHERE skill_id = ? ORDER BY id",
            (skill_id,),
        ).fetchall()
        return [
            Version(
                id=r["id"], skill_id=r["skill_id"], version=r["version"],
                published_at=r["published_at"],
            )
            for r in rows
        ]

    def get_latest_version(self, skill_id: int) -> Version | None:
        row = self.conn.execute(
            "SELECT * FROM versions WHERE skill_id = ? ORDER BY id DESC LIMIT 1",
            (skill_id,),
        ).fetchone()
        if not row:
            return None
        return Version(
            id=row["id"], skill_id=row["skill_id"], version=row["version"],
            published_at=row["published_at"],
        )

    def get_version(self, skill_id: int, version: str) -> Version | None:
        row = self.conn.execute(
            "SELECT * FROM versions WHERE skill_id = ? AND version = ?",
            (skill_id, version),
        ).fetchone()
        if not row:
            return None
        return Version(
            id=row["id"], skill_id=row["skill_id"], version=row["version"],
            published_at=row["published_at"],
        )

    def delete_version(self, skill_id: int, version: str) -> bool:
        cur = self.conn.execute(
            "DELETE FROM versions WHERE skill_id = ? AND version = ?",
            (skill_id, version),
        )
        self.conn.commit()
        return cur.rowcount > 0

    # ── Tags ─────────────────────────────────────────────────

    def get_tags(self, skill_id: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT tag FROM tags WHERE skill_id = ? ORDER BY tag",
            (skill_id,),
        ).fetchall()
        return [r["tag"] for r in rows]

    def set_tags(self, skill_id: int, tags: list[str]) -> None:
        self.conn.execute("DELETE FROM tags WHERE skill_id = ?", (skill_id,))
        for tag in tags:
            self.conn.execute(
                "INSERT OR IGNORE INTO tags(skill_id, tag) VALUES(?, ?)",
                (skill_id, tag.strip().lower()),
            )
        self.conn.commit()

    def add_tags(self, skill_id: int, tags: list[str]) -> None:
        existing = self.get_tags(skill_id)
        merged = list(set(existing + [t.strip().lower() for t in tags]))
        self.set_tags(skill_id, merged)

    def remove_tags(self, skill_id: int, tags: list[str]) -> None:
        remove_set = {t.strip().lower() for t in tags}
        existing = self.get_tags(skill_id)
        self.set_tags(skill_id, [t for t in existing if t not in remove_set])

    # ── Search ───────────────────────────────────────────────

    def search(self, query: str) -> list[Skill]:
        """Search across name, description, category, and tags."""
        pattern = f"%{query}%"
        rows = self.conn.execute(
            "SELECT DISTINCT s.* FROM skills s "
            "LEFT JOIN tags t ON s.id = t.skill_id "
            "WHERE s.name LIKE ? OR s.description LIKE ? "
            "OR s.category LIKE ? OR t.tag LIKE ? "
            "ORDER BY s.name",
            (pattern, pattern, pattern, pattern),
        ).fetchall()
        return [self._row_to_skill(row) for row in rows]

    # ── Categories ───────────────────────────────────────────

    def list_categories(self) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT COALESCE(NULLIF(category, ''), 'general') as cat, "
            "COUNT(*) as cnt FROM skills GROUP BY cat ORDER BY cat"
        ).fetchall()
        return [(r["cat"], r["cnt"]) for r in rows]

    def list_skills_by_category(self, category: str) -> list[Skill]:
        if category == "general":
            rows = self.conn.execute(
                "SELECT * FROM skills WHERE category = '' OR category = 'general' "
                "ORDER BY name"
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM skills WHERE category = ? ORDER BY name",
                (category,),
            ).fetchall()
        return [self._row_to_skill(row) for row in rows]

    # ── Stats ────────────────────────────────────────────────

    def vacuum(self) -> None:
        self.conn.execute("VACUUM")

    def skill_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM skills").fetchone()
        return row["cnt"]

    def version_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM versions").fetchone()
        return row["cnt"]
