"""Core business logic for skillm."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .backends.local import LocalBackend
from .config import Config, load_config, save_config
from .db import Database
from .metadata import extract_metadata
from .models import FileRecord, Skill, Version
from .repo import RepoManager
from .snapshot import create_snapshot

SKILLS_JSON = "skills.json"
SKILLS_DIR = ".skills"

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
    """Core library operations.

    Manages multiple git repos under ~/.skillm/repos/.
    Each repo has its own branches (libraries) and tags (versions).
    A single SQLite DB indexes skills across all repos.
    """

    def __init__(self, config: Config | None = None):
        self.config = config or load_config()
        base_path = self.config.library_path
        base_path.mkdir(parents=True, exist_ok=True)

        self.repo_mgr = RepoManager(base_path)
        self.repo_mgr.repos_dir.mkdir(parents=True, exist_ok=True)

        # Ensure we have an active repo
        active = self.config.library.active_repo or "local"
        if not self.repo_mgr.repo_exists(active):
            self.repo_mgr.init_repo(active)
        self.config.library.active_repo = active

        self.backend = self.repo_mgr.get_backend(active)
        self.db = Database(base_path / "library.db")
        self.db.initialize()

    def _snapshot(self) -> None:
        """Create a DB snapshot before write operations."""
        create_snapshot(self.config.library_path)

    def init(self) -> None:
        """Initialize a new library."""
        base_path = self.config.library_path
        base_path.mkdir(parents=True, exist_ok=True)
        self.repo_mgr.repos_dir.mkdir(parents=True, exist_ok=True)

        active = self.config.library.active_repo or "local"
        if not self.repo_mgr.repo_exists(active):
            self.repo_mgr.init_repo(active)
        self.config.library.active_repo = active

        self.backend = self.repo_mgr.get_backend(active)
        self.db = Database(base_path / "library.db")
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

        # Auto-detect source if not provided
        if not source and not meta.source:
            from .metadata import detect_source
            source = detect_source(source_dir)
        skill_source = source or meta.source or ""
        lib = self.current_library()
        repo_name = self.config.library.active_repo

        now = datetime.now(timezone.utc).isoformat()

        # DB key includes library for cross-library uniqueness
        db_name = f"{lib}/{skill_name}"

        # Get or create skill record
        skill = self.db.get_skill(db_name, repo=repo_name)
        if skill is None:
            skill_id = self.db.insert_skill(Skill(
                repo=repo_name,
                name=db_name,
                description=meta.description,
                category=meta.category,
                author=meta.author,
                source=skill_source,
                created_at=now,
                updated_at=now,
            ))
            skill = self.db.get_skill(db_name, repo=repo_name)
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

    def _resolve_skill(self, name: str) -> Skill | None:
        """Resolve a skill name with auto-resolution.

        Supports:
        - "repo:library/skill" → exact repo + name
        - "library/skill" → search all repos
        - "skill" → try active library in active repo, then search all
        """
        repo = None
        if ":" in name:
            repo, name = name.split(":", 1)

        if "/" in name:
            # Library-qualified
            return self.db.get_skill(name, repo=repo)

        # Unqualified: try current library in active repo first
        db_name = f"{self.current_library()}/{name}"
        active = self.config.library.active_repo
        skill = self.db.get_skill(db_name, repo=active if not repo else repo)
        if skill:
            return skill

        # Search across all repos for any library/name match
        return self.db.find_skill_by_short_name(name, repo=repo)

    def override(self, source_dir: Path, name: str | None = None) -> tuple[str, str]:
        """Override the latest version of an existing skill. Returns (name, version).

        Raises ValueError if skill does not exist or has no versions.
        """
        self._snapshot()
        source_dir = source_dir.resolve()
        meta = extract_metadata(source_dir, name_override=name)
        skill_name = meta.name
        db_name = self._db_name(skill_name)
        repo_name = self.config.library.active_repo

        skill = self.db.get_skill(db_name, repo=repo_name)
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
        skill = self._resolve_skill(name)
        if skill is None:
            # Fallback: try with _db_name for backward compat
            db_name = self._db_name(name)
            repo_name = self.config.library.active_repo
            skill = self.db.get_skill(db_name, repo=repo_name)
            if skill is None:
                return False

        # Extract unqualified name for backend operations
        parts = skill.name.split("/")
        unqualified = parts[-1] if len(parts) > 1 else skill.name

        if version:
            self.db.delete_version(skill.id, version)
            self.backend.remove_skill_files(unqualified, version)
            # If no versions remain, remove the skill entirely
            remaining = self.db.get_versions(skill.id)
            if not remaining:
                self.db.delete_skill(skill.name, repo=skill.repo)
        else:
            self.db.delete_skill(skill.name, repo=skill.repo)
            self.backend.remove_skill_files(unqualified)

        return True

    def info(self, name: str) -> Skill | None:
        return self._resolve_skill(name)

    def list_skills(self) -> list[Skill]:
        return self.db.list_skills()

    def search(self, query: str) -> list[Skill]:
        return self.db.search(query)

    def tag(self, name: str, tags: list[str]) -> bool:
        """Add tags to a skill — updates SKILL.md frontmatter and commits."""
        skill_dir = self.backend.skills_dir / name
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return False

        from .metadata import extract_metadata, update_frontmatter
        meta = extract_metadata(skill_dir)
        merged = sorted(set(meta.tags + [t.strip().lower() for t in tags]))
        update_frontmatter(skill_md, {"tags": merged})

        self.backend.git.add(name)
        self.backend.git.commit(f"skillm: tag {name} +{','.join(tags)}")

        # Keep DB in sync
        skill = self._resolve_skill(name)
        if skill:
            self.db.set_tags(skill.id, merged)
        return True

    def untag(self, name: str, tags: list[str]) -> bool:
        """Remove tags from a skill — updates SKILL.md frontmatter and commits."""
        skill_dir = self.backend.skills_dir / name
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return False

        from .metadata import extract_metadata, update_frontmatter
        meta = extract_metadata(skill_dir)
        remove_set = {t.strip().lower() for t in tags}
        remaining = sorted(t for t in meta.tags if t not in remove_set)
        update_frontmatter(skill_md, {"tags": remaining if remaining else None})

        self.backend.git.add(name)
        self.backend.git.commit(f"skillm: untag {name} -{','.join(tags)}")

        # Keep DB in sync
        skill = self._resolve_skill(name)
        if skill:
            self.db.set_tags(skill.id, remaining)
        return True

    def categorize(self, name: str, category: str) -> bool:
        """Set a skill's category — updates SKILL.md frontmatter and commits."""
        skill_dir = self.backend.skills_dir / name
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return False

        from .metadata import update_frontmatter
        category = category.strip().lower()
        update_frontmatter(skill_md, {"category": category})

        self.backend.git.add(name)
        self.backend.git.commit(f"skillm: categorize {name} → {category}")

        # Keep DB in sync
        skill = self._resolve_skill(name)
        if skill:
            skill.category = category
            self.db.update_skill(skill)
        return True

    def _get_scan_backends(self, repo: str | None = None) -> list[tuple[str, "LocalBackend"]]:
        """Get backends to scan. If repo is specified, just that one; otherwise all."""
        if repo:
            if not self.repo_mgr.repo_exists(repo):
                raise ValueError(f"Repo '{repo}' not found")
            return [(repo, self.repo_mgr.get_backend(repo))]
        return self.repo_mgr.get_all_backends()

    def find_skills_by_tag(self, tag: str, repo: str | None = None) -> list[tuple[str, "SkillMeta"]]:
        """Find all skills that have a given tag.

        Scans SKILL.md frontmatter in working trees.
        If repo is specified, only scans that repo; otherwise scans all repos.
        Returns list of (skill_name, SkillMeta).
        """
        from .metadata import scan_skill_dirs
        tag = tag.strip().lower()
        results = []
        for repo_name, backend in self._get_scan_backends(repo):
            for name, meta in scan_skill_dirs(backend.skills_dir):
                if tag in [t.lower() for t in meta.tags]:
                    results.append((name, meta))
        return results

    def find_skills_by_category(self, category: str, repo: str | None = None) -> list[tuple[str, "SkillMeta"]]:
        """Find all skills that match a category.

        Scans SKILL.md frontmatter in working trees.
        If repo is specified, only scans that repo; otherwise scans all repos.
        Returns list of (skill_name, SkillMeta).
        """
        from .metadata import scan_skill_dirs
        category = category.strip().lower()
        results = []
        for repo_name, backend in self._get_scan_backends(repo):
            for name, meta in scan_skill_dirs(backend.skills_dir):
                if (meta.category or "").lower() == category:
                    results.append((name, meta))
        return results

    def stats(self) -> dict:
        return {
            "skills": self.db.skill_count(),
            "versions": self.db.version_count(),
            "total_size": self.db.total_size(),
            "backend": self.config.library.backend,
            "path": str(self.config.library_path),
        }

    def rebuild(self) -> int:
        """Rebuild database from skill files across all repos and libraries.

        Indexes skills from all repos and all libraries (git tags).
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
        for repo_name, backend in self.repo_mgr.get_all_backends():
            by_library = backend.list_skill_dirs_by_library()
            for lib, skills_list in by_library.items():
                for name, versions in skills_list:
                    for ver in versions:
                        try:
                            skill_dir = backend.get_skill_files(name, ver, library=lib)
                            meta = extract_metadata(skill_dir)
                            now = datetime.now(timezone.utc).isoformat()

                            # Always use library-qualified name in DB
                            db_name = f"{lib}/{name}"

                            skill = self.db.get_skill(db_name, repo=repo_name)
                            if skill is None:
                                skill_id = self.db.insert_skill(Skill(
                                    repo=repo_name,
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

    def create_library(self, name: str, orphan: bool = False) -> None:
        """Create a new library branch.

        If orphan=True, starts empty. Otherwise forks from current branch.
        """
        self.backend.create_library(name, orphan=orphan)

    def switch_library(self, name: str, reset: bool = False) -> None:
        """Switch to a different library.

        If reset=True, hard-resets the branch to match its remote tracking
        state (or first commit if no remote).
        """
        self.backend.switch_library(name, reset=reset)

    def delete_library(self, name: str) -> None:
        """Delete a library. Cannot delete the active library."""
        self.backend.delete_library(name)

    def list_libraries(self) -> list[str]:
        """List all local library names."""
        return self.backend.list_libraries()

    # ── Repo operations ──────────────────────────────────────

    def add_repo(self, name: str, url: str) -> None:
        """Clone a remote URL as a named repo. Auto-switches to it."""
        self.repo_mgr.clone_repo(name, url)
        self.switch_repo(name)

    def init_repo(self, name: str) -> None:
        """Create a local-only repo (no remote)."""
        self.repo_mgr.init_repo(name)

    def remove_repo(self, name: str) -> None:
        """Remove a repo. Cannot remove the active repo."""
        if name == self.config.library.active_repo:
            raise ValueError(f"Cannot remove active repo '{name}'. Switch first.")
        self.repo_mgr.remove_repo(name)

    def switch_repo(self, name: str) -> None:
        """Switch to a different repo."""
        if not self.repo_mgr.repo_exists(name):
            raise ValueError(f"Repo '{name}' not found")
        self.config.library.active_repo = name
        self.backend = self.repo_mgr.get_backend(name)
        save_config(self.config)

    def list_repos(self):
        """List all repos."""
        return self.repo_mgr.list_repos()

    # ── Push / Pull ──────────────────────────────────────────

    def push(self, repo_name: str | None = None, as_branch: str | None = None) -> str:
        """Push a repo to its origin.

        If repo_name is None, pushes the active repo.
        """
        if repo_name is None:
            repo_name = self.config.library.active_repo
        backend = self.repo_mgr.get_backend(repo_name)
        return backend.git_push(as_branch=as_branch)

    def pull(self, repo_name: str | None = None) -> int:
        """Pull from a repo's origin and rebuild the database.

        Returns the number of versions indexed after rebuild.
        """
        if repo_name is None:
            repo_name = self.config.library.active_repo
        backend = self.repo_mgr.get_backend(repo_name)
        backend.git_pull()
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

    def add(self, name: str, version: str | None = None, pin: bool = False, soft: bool = False) -> str:
        """Add a skill from library to project. Returns installed version.

        If soft=True, creates a symlink to the skill directory in the repo
        working tree instead of copying files. The skill always reflects the
        latest state in the library (no need to upgrade).
        """
        self._ensure_dirs()

        # Parse qualified name
        install_name = name
        if ":" in install_name:
            _, install_name = install_name.split(":", 1)
        if "/" in install_name:
            lib_name, skill_name = install_name.split("/", 1)
        else:
            lib_name, skill_name = None, install_name

        dest = self.skills_dir / skill_name

        if soft:
            # Soft install: symlink to skill dir in repo working tree
            backend = self.library.backend
            src = backend.skills_dir / skill_name
            if not src.exists():
                raise ValueError(f"Skill '{skill_name}' not found in working tree")

            if dest.exists() or dest.is_symlink():
                if dest.is_symlink():
                    dest.unlink()
                else:
                    shutil.rmtree(dest)
            dest.symlink_to(src)

            version = "latest"
        else:
            # Hard install: copy files
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

            # Determine which backend to use for file extraction
            if skill.repo and self.library.repo_mgr.repo_exists(skill.repo):
                backend = self.library.repo_mgr.get_backend(skill.repo)
            else:
                backend = self.library.backend

            src = backend.get_skill_files(skill_name, version, library=lib_name)
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)

        # Update manifest
        manifest = self._load_manifest()
        manifest["skills"][name] = {
            "version": version,
            "pinned": pin,
            "soft": soft,
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
        if dest.is_symlink():
            dest.unlink()
        elif dest.exists():
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
