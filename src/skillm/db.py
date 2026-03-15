"""SQLite database operations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import FileRecord, Skill, Version

SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    category    TEXT DEFAULT '',
    author      TEXT DEFAULT '',
    source      TEXT DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS versions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id    INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    version     TEXT NOT NULL,
    changelog   TEXT DEFAULT '',
    file_count  INTEGER DEFAULT 0,
    total_size  INTEGER DEFAULT 0,
    published_at TEXT NOT NULL,
    UNIQUE(skill_id, version)
);

CREATE TABLE IF NOT EXISTS tags (
    skill_id    INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    tag         TEXT NOT NULL,
    PRIMARY KEY (skill_id, tag)
);

CREATE TABLE IF NOT EXISTS files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id  INTEGER NOT NULL REFERENCES versions(id) ON DELETE CASCADE,
    rel_path    TEXT NOT NULL,
    size        INTEGER DEFAULT 0,
    sha256      TEXT NOT NULL,
    UNIQUE(version_id, rel_path)
);

CREATE TABLE IF NOT EXISTS library_meta (
    key         TEXT PRIMARY KEY,
    value       TEXT
);

CREATE INDEX IF NOT EXISTS idx_versions_skill ON versions(skill_id);
CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag);
CREATE INDEX IF NOT EXISTS idx_files_version ON files(version_id);
"""


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
        """Create tables and indexes."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn.executescript(SCHEMA)
        self.conn.execute(
            "INSERT OR IGNORE INTO library_meta(key, value) VALUES('schema_version', '2')"
        )
        self.conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Skill CRUD ──────────────────────────────────────────

    def insert_skill(self, skill: Skill) -> int:
        cur = self.conn.execute(
            "INSERT INTO skills(name, description, category, author, source, created_at, updated_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (skill.name, skill.description, skill.category, skill.author, skill.source,
             skill.created_at, skill.updated_at),
        )
        skill_id = cur.lastrowid
        self.conn.commit()
        return skill_id

    def get_skill(self, name: str) -> Skill | None:
        row = self.conn.execute(
            "SELECT * FROM skills WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            return None
        skill = Skill(
            id=row["id"], name=row["name"], description=row["description"],
            category=row["category"], author=row["author"], source=row["source"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
        skill.tags = self.get_tags(skill.id)
        skill.versions = self.get_versions(skill.id)
        return skill

    def update_skill(self, skill: Skill) -> None:
        self.conn.execute(
            "UPDATE skills SET description=?, category=?, author=?, source=?, updated_at=? WHERE id=?",
            (skill.description, skill.category, skill.author, skill.source, skill.updated_at, skill.id),
        )
        self.conn.commit()

    def delete_skill(self, name: str) -> bool:
        cur = self.conn.execute("DELETE FROM skills WHERE name = ?", (name,))
        self.conn.commit()
        return cur.rowcount > 0

    def list_skills(self) -> list[Skill]:
        rows = self.conn.execute(
            "SELECT * FROM skills ORDER BY name"
        ).fetchall()
        skills = []
        for row in rows:
            skill = Skill(
                id=row["id"], name=row["name"], description=row["description"],
                category=row["category"], author=row["author"], source=row["source"],
                created_at=row["created_at"], updated_at=row["updated_at"],
            )
            skill.tags = self.get_tags(skill.id)
            skill.versions = self.get_versions(skill.id)
            skills.append(skill)
        return skills

    # ── Version CRUD ────────────────────────────────────────

    def insert_version(self, version: Version) -> int:
        cur = self.conn.execute(
            "INSERT INTO versions(skill_id, version, changelog, file_count, total_size, published_at) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (version.skill_id, version.version, version.changelog,
             version.file_count, version.total_size, version.published_at),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_versions(self, skill_id: int) -> list[Version]:
        rows = self.conn.execute(
            "SELECT * FROM versions WHERE skill_id = ? ORDER BY id", (skill_id,)
        ).fetchall()
        return [
            Version(
                id=r["id"], skill_id=r["skill_id"], version=r["version"],
                changelog=r["changelog"], file_count=r["file_count"],
                total_size=r["total_size"], published_at=r["published_at"],
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
            changelog=row["changelog"], file_count=row["file_count"],
            total_size=row["total_size"], published_at=row["published_at"],
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
            changelog=row["changelog"], file_count=row["file_count"],
            total_size=row["total_size"], published_at=row["published_at"],
        )

    def delete_version(self, skill_id: int, version: str) -> bool:
        cur = self.conn.execute(
            "DELETE FROM versions WHERE skill_id = ? AND version = ?",
            (skill_id, version),
        )
        self.conn.commit()
        return cur.rowcount > 0

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

    def add_tags(self, skill_id: int, tags: list[str]) -> None:
        existing = self.get_tags(skill_id)
        merged = list(set(existing + [t.strip().lower() for t in tags]))
        self.set_tags(skill_id, merged)

    def remove_tags(self, skill_id: int, tags: list[str]) -> None:
        remove_set = {t.strip().lower() for t in tags}
        existing = self.get_tags(skill_id)
        self.set_tags(skill_id, [t for t in existing if t not in remove_set])

    # ── Files ───────────────────────────────────────────────

    def insert_file(self, file_rec: FileRecord) -> int:
        cur = self.conn.execute(
            "INSERT INTO files(version_id, rel_path, size, sha256) VALUES(?, ?, ?, ?)",
            (file_rec.version_id, file_rec.rel_path, file_rec.size, file_rec.sha256),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_files(self, version_id: int) -> list[FileRecord]:
        rows = self.conn.execute(
            "SELECT * FROM files WHERE version_id = ? ORDER BY rel_path",
            (version_id,),
        ).fetchall()
        return [
            FileRecord(
                id=r["id"], version_id=r["version_id"], rel_path=r["rel_path"],
                size=r["size"], sha256=r["sha256"],
            )
            for r in rows
        ]

    # ── Search ──────────────────────────────────────────────

    def update_search_content(self, skill_id: int, content: str) -> None:
        """No-op — kept for API compatibility."""
        pass

    def search(self, query: str) -> list[Skill]:
        """Search across name, description, category, and tags using LIKE."""
        pattern = f"%{query}%"
        rows = self.conn.execute(
            "SELECT DISTINCT s.* FROM skills s "
            "LEFT JOIN tags t ON s.id = t.skill_id "
            "WHERE s.name LIKE ? OR s.description LIKE ? OR s.category LIKE ? OR t.tag LIKE ? "
            "ORDER BY s.name",
            (pattern, pattern, pattern, pattern),
        ).fetchall()
        skills = []
        for row in rows:
            skill = Skill(
                id=row["id"], name=row["name"], description=row["description"],
                category=row["category"], author=row["author"], source=row["source"],
                created_at=row["created_at"], updated_at=row["updated_at"],
            )
            skill.tags = self.get_tags(skill.id)
            skill.versions = self.get_versions(skill.id)
            skills.append(skill)
        return skills

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
        """List all categories with skill counts. Returns [(category, count)]."""
        rows = self.conn.execute(
            "SELECT COALESCE(NULLIF(category, ''), 'general') as cat, COUNT(*) as cnt "
            "FROM skills GROUP BY cat ORDER BY cat"
        ).fetchall()
        return [(r["cat"], r["cnt"]) for r in rows]

    def list_skills_by_category(self, category: str) -> list[Skill]:
        """List skills filtered by category."""
        if category == "general":
            rows = self.conn.execute(
                "SELECT * FROM skills WHERE category = '' OR category = 'general' ORDER BY name"
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM skills WHERE category = ? ORDER BY name", (category,)
            ).fetchall()
        skills = []
        for row in rows:
            skill = Skill(
                id=row["id"], name=row["name"], description=row["description"],
                category=row["category"], author=row["author"], source=row["source"],
                created_at=row["created_at"], updated_at=row["updated_at"],
            )
            skill.tags = self.get_tags(skill.id)
            skill.versions = self.get_versions(skill.id)
            skills.append(skill)
        return skills

    def vacuum(self) -> None:
        self.conn.execute("VACUUM")

    def skill_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM skills").fetchone()
        return row["cnt"]

    def version_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM versions").fetchone()
        return row["cnt"]

    def total_size(self) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(total_size), 0) as total FROM versions"
        ).fetchone()
        return row["total"]
