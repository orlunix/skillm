"""Core business logic for skillm."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .backends.local import LocalBackend
from .config import Config, load_config, save_config
from .db import Database
from .metadata import extract_metadata
from .models import FileRecord, Skill, Version
from .remote import get_default_remote
from .snapshot import create_snapshot

SKILLS_JSON = "skills.json"
SKILLS_DIR = ".skills"

import re

_VERSION_RE = re.compile(r"^v(\d+)\.(\d+)$")


def _next_version(existing: list, major: bool = False) -> str:
    """Compute the next version string from existing versions.

    Parses vMAJOR.MINOR format. If major=True, bumps major and resets minor.
    Otherwise bumps minor of the latest major.

    Falls back to v0.1 if no existing versions or unparseable.
    """
    if not existing:
        return "v1.0" if major else "v0.1"

    # Parse all version strings
    max_major = 0
    max_minor = 0
    for v in existing:
        m = _VERSION_RE.match(v.version)
        if m:
            maj, minor = int(m.group(1)), int(m.group(2))
            if maj > max_major or (maj == max_major and minor > max_minor):
                max_major = maj
                max_minor = minor

    if major:
        return f"v{max_major + 1}.0"
    else:
        return f"v{max_major}.{max_minor + 1}"


def get_library() -> "Library":
    """Get the local library."""
    return Library()


class Library:
    """Core library operations."""

    def __init__(self, config: Config | None = None):
        self.config = config or load_config()
        self.backend = self._create_backend()
        self.db = Database(self.backend.get_db())
        self.db.initialize()

    def _create_backend(self) -> LocalBackend:
        return LocalBackend(self.config.library_path)

    def _snapshot(self) -> None:
        """Create a DB snapshot before write operations."""
        create_snapshot(self.config.library_path)

    def init(self) -> None:
        """Initialize a new library."""
        self.backend.initialize()
        self.db = Database(self.backend.get_db())
        self.db.initialize()
        save_config(self.config)

    def publish(
        self,
        source_dir: Path,
        name: str | None = None,
        version: str | None = None,
        source: str | None = None,
        major: bool = False,
    ) -> tuple[str, str]:
        """Publish a skill directory to the library. Returns (name, version)."""
        self._snapshot()
        source_dir = source_dir.resolve()
        meta = extract_metadata(source_dir, name_override=name)
        skill_name = meta.name
        skill_source = source or meta.source or ""
        lib = self.current_library()

        now = datetime.now(timezone.utc).isoformat()

        # DB key includes library for cross-library uniqueness
        db_name = f"{lib}/{skill_name}"

        # Get or create skill record
        skill = self.db.get_skill(db_name)
        if skill is None:
            skill_id = self.db.insert_skill(Skill(
                name=db_name,
                description=meta.description,
                category=meta.category,
                author=meta.author,
                source=skill_source,
                created_at=now,
                updated_at=now,
            ))
            skill = self.db.get_skill(db_name)
        else:
            skill.description = meta.description
            skill.category = meta.category or skill.category
            skill.author = meta.author
            skill.source = skill_source or skill.source
            skill.updated_at = now
            self.db.update_skill(skill)
            skill_id = skill.id

        # Determine version (scoped to current library via git tags)
        if version is None:
            version = self.backend.git.next_version(skill_name, library=lib, major=major)

        # Collect file info
        files = list(source_dir.rglob("*"))
        files = [f for f in files if f.is_file()]
        total_size = sum(f.stat().st_size for f in files)

        # Create version record
        ver_id = self.db.insert_version(Version(
            skill_id=skill_id,
            version=version,
            file_count=len(files),
            total_size=total_size,
            published_at=now,
        ))

        # Record individual files
        for f in files:
            rel = f.relative_to(source_dir)
            file_hash = hashlib.sha256(f.read_bytes()).hexdigest()
            self.db.insert_file(FileRecord(
                version_id=ver_id,
                rel_path=str(rel),
                size=f.stat().st_size,
                sha256=file_hash,
            ))

        # Store files via backend
        self.backend.put_skill_files(skill_name, version, source_dir)

        # Update tags and search content
        if meta.tags:
            self.db.set_tags(skill_id, meta.tags)
        self.db.update_search_content(skill_id, meta.content)

        return skill_name, version

    def _db_name(self, name: str) -> str:
        """Qualify a skill name with the current library for DB lookup.

        If name already contains '/', it's already qualified.
        """
        if "/" in name:
            return name
        return f"{self.current_library()}/{name}"

    def override(self, source_dir: Path, name: str | None = None) -> tuple[str, str]:
        """Override the latest version of an existing skill. Returns (name, version).

        Raises ValueError if skill does not exist or has no versions.
        """
        self._snapshot()
        source_dir = source_dir.resolve()
        meta = extract_metadata(source_dir, name_override=name)
        skill_name = meta.name
        db_name = self._db_name(skill_name)

        skill = self.db.get_skill(db_name)
        if skill is None:
            raise ValueError(f"Skill '{skill_name}' not found in library")

        latest = self.db.get_latest_version(skill.id)
        if latest is None:
            raise ValueError(f"No versions found for '{skill_name}'")

        version = latest.version

        # Remove old version data (cascades to files table)
        self.db.delete_version(skill.id, version)
        self.backend.remove_skill_files(skill_name, version)

        now = datetime.now(timezone.utc).isoformat()

        # Update skill metadata
        skill.description = meta.description
        skill.category = meta.category or skill.category
        skill.author = meta.author
        skill.updated_at = now
        self.db.update_skill(skill)

        # Collect file info
        files = list(source_dir.rglob("*"))
        files = [f for f in files if f.is_file()]
        total_size = sum(f.stat().st_size for f in files)

        # Re-create version record with same version string
        ver_id = self.db.insert_version(Version(
            skill_id=skill.id,
            version=version,
            file_count=len(files),
            total_size=total_size,
            published_at=now,
        ))

        for f in files:
            rel = f.relative_to(source_dir)
            file_hash = hashlib.sha256(f.read_bytes()).hexdigest()
            self.db.insert_file(FileRecord(
                version_id=ver_id,
                rel_path=str(rel),
                size=f.stat().st_size,
                sha256=file_hash,
            ))

        self.backend.put_skill_files(skill_name, version, source_dir)

        if meta.tags:
            self.db.set_tags(skill.id, meta.tags)
        self.db.update_search_content(skill.id, meta.content)

        return skill_name, version

    def remove(self, name: str, version: str | None = None) -> bool:
        """Remove a skill (or specific version) from the current library."""
        self._snapshot()
        db_name = self._db_name(name)
        skill = self.db.get_skill(db_name)
        if skill is None:
            return False

        # Extract unqualified name for backend operations
        unqualified = name.split("/")[-1] if "/" in name else name

        if version:
            self.db.delete_version(skill.id, version)
            self.backend.remove_skill_files(unqualified, version)
            # If no versions remain, remove the skill entirely
            remaining = self.db.get_versions(skill.id)
            if not remaining:
                self.db.delete_skill(db_name)
        else:
            self.db.delete_skill(db_name)
            self.backend.remove_skill_files(unqualified)

        return True

    def info(self, name: str) -> Skill | None:
        return self.db.get_skill(self._db_name(name))

    def list_skills(self) -> list[Skill]:
        return self.db.list_skills()

    def search(self, query: str) -> list[Skill]:
        return self.db.search(query)

    def tag(self, name: str, tags: list[str]) -> bool:
        skill = self.db.get_skill(self._db_name(name))
        if skill is None:
            return False
        self.db.add_tags(skill.id, tags)
        return True

    def untag(self, name: str, tags: list[str]) -> bool:
        skill = self.db.get_skill(self._db_name(name))
        if skill is None:
            return False
        self.db.remove_tags(skill.id, tags)
        return True

    def stats(self) -> dict:
        return {
            "skills": self.db.skill_count(),
            "versions": self.db.version_count(),
            "total_size": self.db.total_size(),
            "backend": self.config.library.backend,
            "path": str(self.config.library_path),
        }

    def rebuild(self) -> int:
        """Rebuild database from skill files across all libraries.

        Indexes skills from all libraries (git tags), not just the active one.
        Returns total number of versions indexed.
        """
        self.db.initialize()

        # Clear existing data
        self.db.conn.execute("DELETE FROM files")
        self.db.conn.execute("DELETE FROM versions")
        self.db.conn.execute("DELETE FROM tags")
        self.db.conn.execute("DELETE FROM skills")
        self.db.conn.commit()

        count = 0
        # Index all libraries by parsing three-level tags
        by_library = self.backend.list_skill_dirs_by_library()
        for lib, skills_list in by_library.items():
            for name, versions in skills_list:
                for ver in versions:
                    try:
                        skill_dir = self.backend.get_skill_files(name, ver, library=lib)
                        meta = extract_metadata(skill_dir)
                        now = datetime.now(timezone.utc).isoformat()

                        # Always use library-qualified name in DB
                        db_name = f"{lib}/{name}"

                        skill = self.db.get_skill(db_name)
                        if skill is None:
                            skill_id = self.db.insert_skill(Skill(
                                name=db_name, description=meta.description,
                                category=meta.category, author=meta.author,
                                source=lib,
                                created_at=now, updated_at=now,
                            ))
                        else:
                            skill_id = skill.id

                        files = [f for f in skill_dir.rglob("*") if f.is_file()]
                        total_size = sum(f.stat().st_size for f in files)

                        ver_id = self.db.insert_version(Version(
                            skill_id=skill_id, version=ver, file_count=len(files),
                            total_size=total_size, published_at=now,
                        ))

                        for f in files:
                            rel = f.relative_to(skill_dir)
                            file_hash = hashlib.sha256(f.read_bytes()).hexdigest()
                            self.db.insert_file(FileRecord(
                                version_id=ver_id, rel_path=str(rel),
                                size=f.stat().st_size, sha256=file_hash,
                            ))

                        if meta.tags:
                            self.db.set_tags(skill_id, meta.tags)
                        self.db.update_search_content(skill_id, meta.content)

                        count += 1
                    except Exception:
                        continue

        return count

    def get_skill_files_path(self, name: str, version: str, library: str | None = None) -> Path:
        """Get path to skill files in the library."""
        return self.backend.get_skill_files(name, version, library=library)

    # ── Library (branch) operations ──────────────────────────

    def current_library(self) -> str:
        """Get the active library name (= current git branch)."""
        return self.backend.current_library()

    def create_library(self, name: str) -> None:
        """Create a new library (orphan branch with init commit)."""
        self.backend.create_library(name)

    def switch_library(self, name: str) -> None:
        """Switch to a different library."""
        self.backend.switch_library(name)

    def delete_library(self, name: str) -> None:
        """Delete a library. Cannot delete the active library."""
        self.backend.delete_library(name)

    def list_libraries(self) -> list[str]:
        """List all local library names."""
        return self.backend.list_libraries()

    def set_library_remote(self, remote: str) -> None:
        """Set upstream tracking for the current library."""
        self.backend.git.set_upstream(remote)

    def unset_library_remote(self) -> None:
        """Remove upstream tracking for the current library."""
        self.backend.git.unset_upstream()

    def get_library_upstream(self) -> str | None:
        """Get the upstream tracking ref for the current library."""
        return self.backend.git.get_upstream()

    # ── Remote operations (git-based) ────────────────────────

    def add_remote(self, name: str, url: str) -> None:
        """Register a git remote on the skills repo."""
        self.backend.add_remote(name, url)

    def remove_remote(self, name: str) -> None:
        """Remove a git remote from the skills repo."""
        self.backend.remove_remote(name)

    def list_remotes(self) -> list[tuple[str, str]]:
        """List git remotes as (name, url) pairs."""
        return self.backend.list_remotes()

    def has_remote(self, name: str) -> bool:
        """Check if a git remote exists."""
        return self.backend.has_remote(name)

    def push(self, remote: str | None = None, as_branch: str | None = None) -> str:
        """Push current library and tags to a git remote.

        If remote is None, uses the tracked upstream.
        If as_branch is specified, pushes to a different branch name on remote.
        """
        if remote is None:
            upstream = self.get_library_upstream()
            if upstream:
                # upstream is like "origin/main" — extract remote name
                remote = upstream.split("/")[0]
            else:
                remote = get_default_remote() or "origin"
        return self.backend.git_push(remote, as_branch=as_branch)

    def pull(self, remote: str | None = None) -> int:
        """Pull from a git remote and rebuild the database.

        Returns the number of versions indexed after rebuild.
        """
        if remote is None:
            upstream = self.get_library_upstream()
            if upstream:
                remote = upstream.split("/")[0]
            else:
                remote = get_default_remote() or "origin"
        self.backend.git_pull(remote)
        return self.rebuild()


# Agent config directory mappings
AGENT_DIRS = {
    "claude": ".claude",
    "cursor": ".cursor",
    "codex": ".codex",
    "openclaw": ".openclaw",
}
DEFAULT_AGENT = "claude"


class Project:
    """Project-level skill operations.

    Skills are installed into agent-specific directories:
      .claude/skills/my-skill/
      .cursor/skills/my-skill/
      .codex/skills/my-skill/

    The manifest (skills.json) lives in the agent directory.
    """

    def __init__(
        self,
        project_dir: Path | None = None,
        library: Library | None = None,
        agent: str = DEFAULT_AGENT,
    ):
        self.project_dir = (project_dir or Path.cwd()).resolve()
        self.library = library or Library()
        self.agent = agent

        agent_dir_name = AGENT_DIRS.get(agent, f".{agent}")
        self.agent_dir = self.project_dir / agent_dir_name
        self.skills_dir = self.agent_dir / "skills"
        self.skills_json = self.agent_dir / SKILLS_JSON

    def _ensure_dirs(self) -> None:
        """Create agent and skills directories if they don't exist."""
        self.agent_dir.mkdir(exist_ok=True)
        self.skills_dir.mkdir(exist_ok=True)
        if not self.skills_json.exists():
            self.skills_json.write_text(json.dumps({"skills": {}}, indent=2) + "\n")

    def init(self) -> None:
        """Initialize project for skill consumption."""
        self._ensure_dirs()

    def _load_manifest(self) -> dict:
        if self.skills_json.exists():
            return json.loads(self.skills_json.read_text())
        return {"skills": {}}

    def _save_manifest(self, manifest: dict) -> None:
        self.skills_json.write_text(json.dumps(manifest, indent=2) + "\n")

    def add(self, name: str, version: str | None = None, pin: bool = False) -> str:
        """Add a skill from library to project. Returns installed version."""
        self._ensure_dirs()
        skill = self.library.info(name)
        if skill is None:
            raise ValueError(f"Skill '{name}' not found in library")

        if version is None or version == "latest":
            ver = self.library.db.get_latest_version(skill.id)
            if ver is None:
                raise ValueError(f"No versions found for '{name}'")
            version = ver.version
        else:
            ver = self.library.db.get_version(skill.id, version)
            if ver is None:
                raise ValueError(f"Version '{version}' not found for '{name}'")

        # Parse qualified name: "library/skill" → library="library", skill="skill"
        if "/" in name:
            lib_name, skill_name = name.split("/", 1)
        else:
            lib_name, skill_name = None, name

        # Copy files from library to project
        src = self.library.get_skill_files_path(skill_name, version, library=lib_name)
        dest = self.skills_dir / skill_name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)

        # Update manifest
        manifest = self._load_manifest()
        manifest["skills"][name] = {
            "version": version,
            "pinned": pin,
        }
        self._save_manifest(manifest)

        return version

    def drop(self, name: str) -> bool:
        """Remove a skill from the project."""
        manifest = self._load_manifest()
        if name not in manifest["skills"]:
            return False

        del manifest["skills"][name]
        self._save_manifest(manifest)

        dest = self.skills_dir / name
        if dest.exists():
            shutil.rmtree(dest)

        return True

    def sync(self) -> list[str]:
        """Install missing skills from skills.json. Returns list of synced skill names."""
        manifest = self._load_manifest()
        synced = []

        for name, info in manifest["skills"].items():
            dest = self.skills_dir / name
            if not dest.exists():
                version = info.get("version")
                self.add(name, version=version, pin=info.get("pinned", False))
                synced.append(name)

        return synced

    def upgrade(self, name: str | None = None) -> list[tuple[str, str, str]]:
        """Upgrade skills to latest versions. Returns list of (name, old_ver, new_ver)."""
        manifest = self._load_manifest()
        upgraded = []

        targets = [name] if name else list(manifest["skills"].keys())

        for skill_name in targets:
            if skill_name not in manifest["skills"]:
                continue

            info = manifest["skills"][skill_name]
            if info.get("pinned", False):
                continue

            old_version = info["version"]
            skill = self.library.info(skill_name)
            if skill is None:
                continue

            latest = self.library.db.get_latest_version(skill.id)
            if latest is None or latest.version == old_version:
                continue

            self.add(skill_name, version=latest.version, pin=info.get("pinned", False))
            upgraded.append((skill_name, old_version, latest.version))

        return upgraded

    def list_skills(self) -> dict:
        """List skills in the project manifest."""
        return self._load_manifest().get("skills", {})

    def enable(self, name: str) -> bool:
        manifest = self._load_manifest()
        if name not in manifest["skills"]:
            return False
        manifest["skills"][name]["enabled"] = True
        self._save_manifest(manifest)
        return True

    def disable(self, name: str) -> bool:
        manifest = self._load_manifest()
        if name not in manifest["skills"]:
            return False
        manifest["skills"][name]["enabled"] = False
        self._save_manifest(manifest)
        return True
