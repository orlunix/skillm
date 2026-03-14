"""Core business logic for skillm v2 — git-backed package manager."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .config import Config, Source, load_config, save_config
from .db import Database
from .git import GitError, GitRepo
from .lockfile import LockFile, _dir_integrity
from .metadata import extract_metadata
from .models import Skill, Version

SKILLS_JSON = "skills.json"
LOCK_FILENAME = "skills.lock"


class SourceManager:
    """Manages multiple skill sources (git repos) and the cache index."""

    def __init__(self, config: Config | None = None):
        self.config = config or load_config()
        self.db = Database(self.config.cache_path / "index.db")
        self.db.initialize()
        self._sync_sources_to_cache()

    def _sync_sources_to_cache(self) -> None:
        """Ensure all configured sources are in the cache DB."""
        for src in self.config.sources:
            self.db.upsert_source(src.name, src.url, src.priority)

    # ── Source lifecycle ─────────────────────────────────────

    def init_source(self, name: str, url: str, priority: int = 10) -> Source:
        """Initialize a new source (create git repo if local)."""
        source = Source(name=name, url=url, priority=priority)
        path = source.resolved_path
        repo = GitRepo(path)
        if not repo.is_repo():
            repo.init()
            # Create a .gitkeep so we have an initial commit
            (path / ".gitkeep").write_text("")
            repo.add(".gitkeep")
            repo.commit("skillm: initialize source")

        # Add to config
        existing = self.config.get_source(name)
        if existing is None:
            self.config.sources.append(source)
            self.config.sources.sort(key=lambda s: s.priority)
        else:
            existing.url = url
            existing.priority = priority

        if not self.config.settings.default_source:
            self.config.settings.default_source = name

        save_config(self.config)
        self.db.upsert_source(name, url, priority)
        return source

    def add_source(self, name: str, url: str, priority: int = 10) -> Source:
        """Add an existing source (git repo must already exist)."""
        source = Source(name=name, url=url, priority=priority)

        existing = self.config.get_source(name)
        if existing is None:
            self.config.sources.append(source)
            self.config.sources.sort(key=lambda s: s.priority)
        else:
            existing.url = url
            existing.priority = priority

        if not self.config.settings.default_source:
            self.config.settings.default_source = name

        save_config(self.config)
        self.db.upsert_source(name, url, priority)
        return source

    def remove_source(self, name: str) -> bool:
        """Remove a source from config (does not delete the git repo)."""
        self.config.sources = [s for s in self.config.sources if s.name != name]
        if self.config.settings.default_source == name:
            if self.config.sources:
                self.config.settings.default_source = self.config.sources[0].name
            else:
                self.config.settings.default_source = ""
        save_config(self.config)
        self.db.delete_skills_by_source(name)
        return True

    def set_default(self, name: str) -> None:
        """Set the default source."""
        if self.config.get_source(name) is None:
            raise ValueError(f"Source '{name}' not found")
        self.config.settings.default_source = name
        save_config(self.config)

    def get_repo(self, source_name: str) -> GitRepo:
        """Get a GitRepo for a source."""
        src = self.config.get_source(source_name)
        if src is None:
            raise ValueError(f"Source '{source_name}' not found")
        return GitRepo(src.resolved_path)

    def resolve_source(self, name: str | None = None) -> Source:
        """Resolve a source by name, or return the default."""
        if name:
            src = self.config.get_source(name)
            if src is None:
                raise ValueError(f"Source '{name}' not found")
            return src
        src = self.config.get_default_source()
        if src is None:
            raise ValueError("No sources configured. Run: skillm source init NAME PATH")
        return src

    # ── Skill operations ─────────────────────────────────────

    def add_skill(
        self,
        source_dir: Path,
        source_name: str | None = None,
        name: str | None = None,
        message: str | None = None,
    ) -> tuple[str, str]:
        """Add a skill directory to a source repo.

        1. Extract metadata from SKILL.md
        2. Copy files to <source-repo>/<skill-name>/
        3. git add + git commit
        4. Update cache

        Returns (skill_name, source_name).
        """
        source_dir = source_dir.resolve()
        meta = extract_metadata(source_dir, name_override=name)
        skill_name = meta.name

        src = self.resolve_source(source_name)
        repo = GitRepo(src.resolved_path)

        # Copy files into the source repo
        dest = src.resolved_path / skill_name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source_dir, dest)

        # Git add + commit
        repo.add(skill_name)
        commit_msg = message or f"skillm: add {skill_name}"
        commit = repo.commit(commit_msg)

        # Update cache
        self._cache_skill(src.name, skill_name, meta, commit)

        return skill_name, src.name

    def publish(
        self,
        skill_name: str,
        source_name: str | None = None,
        major: bool = False,
        message: str | None = None,
    ) -> tuple[str, str]:
        """Create a version tag for a skill.

        1. Find existing tags for this skill
        2. Compute next version
        3. Create git tag

        Returns (skill_name, version).
        """
        src = self.resolve_source(source_name)
        repo = GitRepo(src.resolved_path)

        # Verify skill exists in repo
        skill_dir = src.resolved_path / skill_name
        if not skill_dir.exists():
            raise ValueError(f"Skill '{skill_name}' not found in source '{src.name}'")

        # Auto-commit any uncommitted changes first
        if repo.has_changes(skill_name):
            repo.add(skill_name)
            repo.commit(message or f"skillm: update {skill_name}")

        version = repo.next_version(skill_name, major=major)
        tag_name = f"{skill_name}/{version}"
        tag_msg = message or f"skillm: publish {skill_name} {version}"
        repo.tag(tag_name, tag_msg)

        # Update cache with version info
        now = datetime.now(timezone.utc).isoformat()
        skill = self.db.get_skill(skill_name, source=src.name)
        if skill:
            commit = repo.tag_commit(tag_name)
            self.db.insert_version(Version(
                skill_id=skill.id,
                version=version,
                published_at=now,
            ))

        return skill_name, version

    def remove_skill(
        self,
        skill_name: str,
        source_name: str | None = None,
        version: str | None = None,
        message: str | None = None,
    ) -> bool:
        """Remove a skill or version from a source.

        If version is specified, only removes that version tag.
        Otherwise removes the skill directory and all tags.
        """
        src = self.resolve_source(source_name)
        repo = GitRepo(src.resolved_path)

        if version:
            # Just remove the version tag
            tag_name = f"{skill_name}/{version}"
            if repo.tag_exists(tag_name):
                repo.delete_tag(tag_name)
            skill = self.db.get_skill(skill_name, source=src.name)
            if skill:
                self.db.delete_version(skill.id, version)
                remaining = self.db.get_versions(skill.id)
                if not remaining:
                    self.db.delete_skill(skill_name, source=src.name)
            return True

        # Remove entire skill directory
        skill_dir = src.resolved_path / skill_name
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
            repo.add("-A")
            repo.commit(message or f"skillm: remove {skill_name}")

        # Remove all version tags
        for tag_name, _, _ in repo.skill_versions(skill_name):
            repo.delete_tag(tag_name)

        self.db.delete_skill(skill_name, source=src.name)
        return True

    # ── Query operations ─────────────────────────────────────

    def info(self, name: str, source: str | None = None) -> Skill | None:
        return self.db.get_skill(name, source=source)

    def list_skills(self, source: str | None = None) -> list[Skill]:
        return self.db.list_skills(source=source)

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
            "sources": len(self.config.sources),
            "cache_path": str(self.config.cache_path),
        }

    # ── Git operations ───────────────────────────────────────

    def push(self, source_name: str | None = None) -> str:
        """Push a source repo to its remote."""
        src = self.resolve_source(source_name)
        repo = GitRepo(src.resolved_path)
        if not repo.has_remote():
            raise GitError(f"Source '{src.name}' has no remote configured")
        return repo.push()

    def pull(self, source_name: str | None = None) -> str:
        """Pull a source repo from its remote."""
        src = self.resolve_source(source_name)
        repo = GitRepo(src.resolved_path)
        if not repo.has_remote():
            raise GitError(f"Source '{src.name}' has no remote configured")
        result = repo.pull()
        self.rebuild_cache(source_name=src.name)
        return result

    def log(self, skill_name: str, source_name: str | None = None, max_count: int = 20) -> str:
        """Get git log for a skill."""
        src = self.resolve_source(source_name)
        repo = GitRepo(src.resolved_path)
        return repo.log(path=skill_name, max_count=max_count)

    def diff(self, skill_name: str, source_name: str | None = None) -> str:
        """Get uncommitted changes for a skill."""
        src = self.resolve_source(source_name)
        repo = GitRepo(src.resolved_path)
        return repo.diff(path=skill_name)

    # ── Cache operations ─────────────────────────────────────

    def rebuild_cache(self, source_name: str | None = None) -> int:
        """Rebuild the cache index from git repos.

        If source_name is given, only rebuild that source.
        Returns count of skills indexed.
        """
        sources = [self.config.get_source(source_name)] if source_name else self.config.sources
        sources = [s for s in sources if s is not None]

        count = 0
        for src in sources:
            self.db.delete_skills_by_source(src.name)
            repo = GitRepo(src.resolved_path)
            if not repo.is_repo():
                continue

            # Scan skill directories
            skill_names = repo.list_skill_dirs()
            for name in skill_names:
                try:
                    skill_dir = src.resolved_path / name
                    meta = extract_metadata(skill_dir, name_override=name)
                    now = datetime.now(timezone.utc).isoformat()

                    try:
                        commit = repo.head_commit()
                    except GitError:
                        commit = ""

                    skill_id = self.db.insert_skill(Skill(
                        name=name,
                        source=src.name,
                        description=meta.description,
                        category=meta.category,
                        author=meta.author,
                        updated_at=now,
                    ))

                    if meta.tags:
                        self.db.set_tags(skill_id, meta.tags)

                    # Index version tags
                    for tag_name, major, minor in repo.skill_versions(name):
                        version_str = f"v{major}.{minor}"
                        try:
                            tag_commit = repo.tag_commit(tag_name)
                        except GitError:
                            tag_commit = ""
                        self.db.insert_version(Version(
                            skill_id=skill_id,
                            version=version_str,
                            published_at=now,
                        ))

                    count += 1
                except Exception:
                    continue

            now = datetime.now(timezone.utc).isoformat()
            self.db.update_source_synced(src.name, now)

        return count

    def _cache_skill(self, source_name: str, skill_name: str, meta, commit: str) -> None:
        """Update cache for a single skill."""
        now = datetime.now(timezone.utc).isoformat()

        skill = self.db.get_skill(skill_name, source=source_name)
        if skill is None:
            skill_id = self.db.insert_skill(Skill(
                name=skill_name,
                source=source_name,
                description=meta.description,
                category=meta.category,
                author=meta.author,
                updated_at=now,
            ))
        else:
            skill.description = meta.description
            skill.category = meta.category or skill.category
            skill.author = meta.author or skill.author
            skill.updated_at = now
            self.db.update_skill(skill)
            skill_id = skill.id

        if meta.tags:
            self.db.set_tags(skill_id, meta.tags)

    # ── Install operations ───────────────────────────────────

    def get_skill_files(
        self,
        skill_name: str,
        version: str | None = None,
        source_name: str | None = None,
    ) -> Path:
        """Get the path to skill files in a source repo.

        If version is specified, extracts files at that version's tag to a temp dir.
        Otherwise returns the working tree path.
        """
        src = self.resolve_source(source_name)

        if version:
            repo = GitRepo(src.resolved_path)
            tag_name = f"{skill_name}/{version}"
            if not repo.tag_exists(tag_name):
                raise ValueError(f"Version '{version}' not found for '{skill_name}'")
            # Extract to a temporary location in the cache
            extract_dir = self.config.cache_path / "extract" / skill_name / version
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            repo.extract_to(tag_name, f"{skill_name}/", extract_dir)
            return extract_dir

        # Working tree path
        skill_dir = src.resolved_path / skill_name
        if not skill_dir.exists():
            raise FileNotFoundError(f"Skill '{skill_name}' not found in source '{src.name}'")
        return skill_dir


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

    Uses skills.json for manifest and skills.lock for integrity.
    """

    def __init__(
        self,
        project_dir: Path | None = None,
        source_manager: SourceManager | None = None,
        agent: str = DEFAULT_AGENT,
    ):
        self.project_dir = (project_dir or Path.cwd()).resolve()
        self.source_manager = source_manager or SourceManager()
        self.agent = agent

        agent_dir_name = AGENT_DIRS.get(agent, f".{agent}")
        self.agent_dir = self.project_dir / agent_dir_name
        self.skills_dir = self.agent_dir / "skills"
        self.skills_json = self.agent_dir / SKILLS_JSON
        self.lock_file_path = self.agent_dir / LOCK_FILENAME
        self._lock = LockFile(self.lock_file_path)

    def _ensure_dirs(self) -> None:
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

    def add(self, name: str, version: str | None = None, pin: bool = False, source: str | None = None) -> str:
        """Install a skill from a source into this project. Returns installed version."""
        self._ensure_dirs()
        sm = self.source_manager
        src = sm.resolve_source(source)

        skill = sm.info(name, source=src.name)
        if skill is None:
            # Try to find it by scanning the repo
            sm.rebuild_cache(source_name=src.name)
            skill = sm.info(name, source=src.name)
            if skill is None:
                raise ValueError(f"Skill '{name}' not found in source '{src.name}'")

        if version is None or version == "latest":
            latest = sm.db.get_latest_version(skill.id)
            if latest:
                version = latest.version
            else:
                version = None  # No published version, use HEAD

        # Get skill files
        src_path = sm.get_skill_files(name, version=version, source_name=src.name)

        # Copy to project
        dest = self.skills_dir / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src_path, dest)

        # Update manifest
        manifest = self._load_manifest()
        manifest["skills"][name] = {
            "version": version or "HEAD",
            "source": src.name,
            "pinned": pin,
        }
        self._save_manifest(manifest)

        # Update lock file
        self._lock.load()
        repo = sm.get_repo(src.name)
        try:
            commit = repo.tag_commit(f"{name}/{version}") if version else repo.head_commit()
        except GitError:
            commit = ""
        integrity = _dir_integrity(dest)
        self._lock.set(name, version or "HEAD", src.name, commit=commit, integrity=integrity)
        self._lock.save()

        return version or "HEAD"

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

        self._lock.load()
        self._lock.remove(name)
        self._lock.save()

        return True

    def sync(self) -> list[str]:
        """Install missing skills from skills.json."""
        manifest = self._load_manifest()
        synced = []

        for name, info in manifest["skills"].items():
            dest = self.skills_dir / name
            if not dest.exists():
                version = info.get("version")
                source = info.get("source")
                if version == "HEAD":
                    version = None
                self.add(name, version=version, pin=info.get("pinned", False), source=source)
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
            source = info.get("source")
            sm = self.source_manager
            src = sm.resolve_source(source)

            skill = sm.info(skill_name, source=src.name)
            if skill is None:
                continue

            latest = sm.db.get_latest_version(skill.id)
            if latest is None or latest.version == old_version:
                continue

            self.add(skill_name, version=latest.version, pin=False, source=src.name)
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

    def verify(self) -> list[tuple[str, bool]]:
        """Verify installed skills match lock file. Returns list of (name, ok)."""
        self._lock.load()
        results = []
        manifest = self._load_manifest()
        for name in manifest.get("skills", {}):
            dest = self.skills_dir / name
            ok = self._lock.verify(name, dest)
            results.append((name, ok))
        return results
