"""SQLite database operations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import Skill

SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    repo        TEXT NOT NULL DEFAULT 'local',
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    category    TEXT DEFAULT '',
    author      TEXT DEFAULT '',
    source      TEXT DEFAULT '',
    commit_hash TEXT DEFAULT '',
    file_count  INTEGER DEFAULT 0,
    total_size  INTEGER DEFAULT 0,
    updated_at  TEXT NOT NULL,
    UNIQUE(repo, name)
);

CREATE TABLE IF NOT EXISTS tags (
    skill_id    INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    tag         TEXT NOT NULL,
    PRIMARY KEY (skill_id, tag)
);

CREATE TABLE IF NOT EXISTS library_meta (
    key         TEXT PRIMARY KEY,
    value       TEXT
);

CREATE INDEX IF NOT EXISTS idx_skills_repo ON skills(repo);
CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag);
"""

SCHEMA_VERSION = "4"


class Database:
    """SQLite database for skill metadata."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self) -> None:
        """Create tables and indexes. Handles schema migration."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if migration needed
        try:
            row = self.conn.execute(
                "SELECT value FROM library_meta WHERE key = 'schema_version'"
            ).fetchone()
            if row and row["value"] != SCHEMA_VERSION:
                self.conn.executescript("""
                    DROP TABLE IF EXISTS files;
                    DROP TABLE IF EXISTS versions;
                    DROP TABLE IF EXISTS tags;
                    DROP TABLE IF EXISTS skills;
                    DROP TABLE IF EXISTS library_meta;
                """)
        except Exception:
            pass

        self.conn.executescript(SCHEMA)
        self.conn.execute(
            "INSERT OR REPLACE INTO library_meta(key, value) VALUES('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
        self.conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Helper ─────────────────────────────────────────────

    def _row_to_skill(self, row) -> Skill:
        skill = Skill(
            id=row["id"], repo=row["repo"], name=row["name"],
            description=row["description"], category=row["category"],
            author=row["author"], source=row["source"],
            commit=row["commit_hash"],
            file_count=row["file_count"], total_size=row["total_size"],
            updated_at=row["updated_at"],
        )
        skill.tags = self.get_tags(skill.id)
        return skill

    # ── Skill CRUD ──────────────────────────────────────────

    def insert_skill(self, skill: Skill) -> int:
        cur = self.conn.execute(
            "INSERT INTO skills(repo, name, description, category, author, source, "
            "commit_hash, file_count, total_size, updated_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (skill.repo, skill.name, skill.description, skill.category,
             skill.author, skill.source, skill.commit,
             skill.file_count, skill.total_size, skill.updated_at),
        )
        skill_id = cur.lastrowid
        self.conn.commit()
        return skill_id

    def upsert_skill(self, skill: Skill) -> int:
        """Insert or update a skill. Returns skill id."""
        existing = self.get_skill(skill.name, repo=skill.repo)
        if existing:
            existing.description = skill.description
            existing.category = skill.category or existing.category
            existing.author = skill.author or existing.author
            existing.source = skill.source or existing.source
            existing.commit = skill.commit or existing.commit
            existing.file_count = skill.file_count
            existing.total_size = skill.total_size
            existing.updated_at = skill.updated_at
            self.update_skill(existing)
            return existing.id
        return self.insert_skill(skill)

    def get_skill(self, name: str, repo: str | None = None) -> Skill | None:
        if repo:
            row = self.conn.execute(
                "SELECT * FROM skills WHERE name = ? AND repo = ?", (name, repo)
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT * FROM skills WHERE name = ?", (name,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_skill(row)

    def find_skill_by_short_name(self, short_name: str, repo: str | None = None) -> Skill | None:
        """Find a skill by its unqualified name (e.g. 'deploy-k8s' matches 'main/deploy-k8s')."""
        pattern = f"%/{short_name}"
        if repo:
            row = self.conn.execute(
                "SELECT * FROM skills WHERE name LIKE ? AND repo = ? LIMIT 1",
                (pattern, repo),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT * FROM skills WHERE name LIKE ? LIMIT 1",
                (pattern,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_skill(row)

    def update_skill(self, skill: Skill) -> None:
        self.conn.execute(
            "UPDATE skills SET description=?, category=?, author=?, source=?, "
            "commit_hash=?, file_count=?, total_size=?, updated_at=? WHERE id=?",
            (skill.description, skill.category, skill.author, skill.source,
             skill.commit, skill.file_count, skill.total_size, skill.updated_at, skill.id),
        )
        self.conn.commit()

    def delete_skill(self, name: str, repo: str | None = None) -> bool:
        if repo:
            cur = self.conn.execute(
                "DELETE FROM skills WHERE name = ? AND repo = ?", (name, repo)
            )
        else:
            cur = self.conn.execute(
                "DELETE FROM skills WHERE name = ?", (name,)
            )
        self.conn.commit()
        return cur.rowcount > 0

    def list_skills(self, repo: str | None = None) -> list[Skill]:
        if repo:
            rows = self.conn.execute(
                "SELECT * FROM skills WHERE repo = ? ORDER BY name", (repo,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM skills ORDER BY name"
            ).fetchall()
        return [self._row_to_skill(row) for row in rows]

    # ── Tags ────────────────────────────────────────────────

    def get_tags(self, skill_id: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT tag FROM tags WHERE skill_id = ? ORDER BY tag", (skill_id,)
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

    # ── Search ──────────────────────────────────────────────

    def search(self, query: str, repo: str | None = None) -> list[Skill]:
        """Search across name, description, category, and tags using LIKE."""
        pattern = f"%{query}%"
        if repo:
            rows = self.conn.execute(
                "SELECT DISTINCT s.* FROM skills s "
                "LEFT JOIN tags t ON s.id = t.skill_id "
                "WHERE s.repo = ? AND (s.name LIKE ? OR s.description LIKE ? OR s.category LIKE ? OR t.tag LIKE ?) "
                "ORDER BY s.name",
                (repo, pattern, pattern, pattern, pattern),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT DISTINCT s.* FROM skills s "
                "LEFT JOIN tags t ON s.id = t.skill_id "
                "WHERE s.name LIKE ? OR s.description LIKE ? OR s.category LIKE ? OR t.tag LIKE ? "
                "ORDER BY s.name",
                (pattern, pattern, pattern, pattern),
            ).fetchall()
        return [self._row_to_skill(row) for row in rows]

    # ── Library Meta ────────────────────────────────────────

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM library_meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO library_meta(key, value) VALUES(?, ?)",
            (key, value),
        )
        self.conn.commit()

    def list_categories(self) -> list[tuple[str, int]]:
        """List all categories with skill counts."""
        rows = self.conn.execute(
            "SELECT COALESCE(NULLIF(category, ''), 'general') as cat, COUNT(*) as cnt "
            "FROM skills GROUP BY cat ORDER BY cat"
        ).fetchall()
        return [(r["cat"], r["cnt"]) for r in rows]

    def skill_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM skills").fetchone()
        return row["cnt"]

    def total_size(self) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(total_size), 0) as total FROM skills"
        ).fetchone()
        return row["total"]

    def vacuum(self) -> None:
        self.conn.execute("VACUUM")
