"""Core business logic for skillm."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .backends.base import LibraryBackend
from .backends.local import LocalBackend
from .config import Config, load_config, save_config
from .db import Database
from .metadata import extract_metadata
from .models import FileRecord, Skill, Version

SKILLS_JSON = "skills.json"
SKILLS_DIR = ".skills"


class Library:
    """Core library operations."""

    def __init__(self, config: Config | None = None):
        self.config = config or load_config()
        self.backend = self._create_backend()
        self.db = Database(self.backend.get_db())

    def _create_backend(self) -> LibraryBackend:
        if self.config.library.backend == "local":
            return LocalBackend(self.config.library_path)
        if self.config.library.backend == "file":
            return LocalBackend(Path(self.config.library.path).expanduser())
        raise ValueError(f"Unknown backend: {self.config.library.backend}")

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
    ) -> tuple[str, str]:
        """Publish a skill directory to the library. Returns (name, version)."""
        source_dir = source_dir.resolve()
        meta = extract_metadata(source_dir, name_override=name)
        skill_name = meta.name
        skill_source = source or meta.source or ""

        now = datetime.now(timezone.utc).isoformat()

        # Get or create skill record
        skill = self.db.get_skill(skill_name)
        if skill is None:
            skill_id = self.db.insert_skill(Skill(
                name=skill_name,
                description=meta.description,
                category=meta.category,
                author=meta.author,
                source=skill_source,
                created_at=now,
                updated_at=now,
            ))
            skill = self.db.get_skill(skill_name)
        else:
            skill.description = meta.description
            skill.category = meta.category or skill.category
            skill.author = meta.author
            skill.source = skill_source or skill.source
            skill.updated_at = now
            self.db.update_skill(skill)
            skill_id = skill.id

        # Determine version
        if version is None:
            existing = self.db.get_versions(skill_id)
            next_num = len(existing) + 1
            version = f"v{next_num}"

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

    def override(self, source_dir: Path, name: str | None = None) -> tuple[str, str]:
        """Override the latest version of an existing skill. Returns (name, version).

        Raises ValueError if skill does not exist or has no versions.
        """
        source_dir = source_dir.resolve()
        meta = extract_metadata(source_dir, name_override=name)
        skill_name = meta.name

        skill = self.db.get_skill(skill_name)
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
        """Remove a skill (or specific version) from the library."""
        skill = self.db.get_skill(name)
        if skill is None:
            return False

        if version:
            self.db.delete_version(skill.id, version)
            self.backend.remove_skill_files(name, version)
            # If no versions remain, remove the skill entirely
            remaining = self.db.get_versions(skill.id)
            if not remaining:
                self.db.delete_skill(name)
        else:
            self.db.delete_skill(name)
            self.backend.remove_skill_files(name)

        return True

    def info(self, name: str) -> Skill | None:
        return self.db.get_skill(name)

    def list_skills(self) -> list[Skill]:
        return self.db.list_skills()

    def search(self, query: str) -> list[Skill]:
        return self.db.search(query)

    def tag(self, name: str, tags: list[str]) -> bool:
        skill = self.db.get_skill(name)
        if skill is None:
            return False
        self.db.add_tags(skill.id, tags)
        return True

    def untag(self, name: str, tags: list[str]) -> bool:
        skill = self.db.get_skill(name)
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
        """Rebuild database from skill files on disk."""
        self.db.initialize()

        # Clear existing data
        self.db.conn.execute("DELETE FROM files")
        self.db.conn.execute("DELETE FROM versions")
        self.db.conn.execute("DELETE FROM tags")
        self.db.conn.execute("DELETE FROM search_index")
        self.db.conn.execute("DELETE FROM skills")
        self.db.conn.commit()

        count = 0
        for name, versions in self.backend.list_skill_dirs():
            for ver in versions:
                try:
                    skill_dir = self.backend.get_skill_files(name, ver)
                    meta = extract_metadata(skill_dir)
                    now = datetime.now(timezone.utc).isoformat()

                    skill = self.db.get_skill(name)
                    if skill is None:
                        skill_id = self.db.insert_skill(Skill(
                            name=name, description=meta.description,
                            category=meta.category, author=meta.author,
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

    def get_skill_files_path(self, name: str, version: str) -> Path:
        """Get path to skill files in the library."""
        return self.backend.get_skill_files(name, version)


class Project:
    """Project-level skill operations."""

    def __init__(self, project_dir: Path | None = None, library: Library | None = None):
        self.project_dir = (project_dir or Path.cwd()).resolve()
        self.library = library or Library()
        self.skills_json = self.project_dir / SKILLS_JSON
        self.skills_dir = self.project_dir / SKILLS_DIR

    def init(self) -> None:
        """Initialize project for skill consumption."""
        self.skills_dir.mkdir(exist_ok=True)
        if not self.skills_json.exists():
            self.skills_json.write_text(json.dumps({"skills": {}}, indent=2) + "\n")

        # Add .skills to .gitignore if git repo
        gitignore = self.project_dir / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text()
            if SKILLS_DIR not in content:
                with open(gitignore, "a") as f:
                    f.write(f"\n{SKILLS_DIR}/\n")
        elif (self.project_dir / ".git").exists():
            gitignore.write_text(f"{SKILLS_DIR}/\n")

    def _load_manifest(self) -> dict:
        if self.skills_json.exists():
            return json.loads(self.skills_json.read_text())
        return {"skills": {}}

    def _save_manifest(self, manifest: dict) -> None:
        self.skills_json.write_text(json.dumps(manifest, indent=2) + "\n")

    def add(self, name: str, version: str | None = None, pin: bool = False) -> str:
        """Add a skill from library to project. Returns installed version."""
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

        # Copy files from library to project
        src = self.library.get_skill_files_path(name, version)
        dest = self.skills_dir / name
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
