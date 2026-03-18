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
from .models import Skill
from .repo import RepoManager
from .snapshot import create_snapshot

SKILLS_JSON = "skills.json"
SKILLS_DIR = ".skills"


def get_library() -> "Library":
    """Get the local library."""
    return Library()


class Library:
    """Core library operations.

    Manages multiple git repos under ~/.skillm/repos/.
    Each repo has its own branches (libraries).
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

    def publish(self, source_dir: Path, name: str | None = None, source: str | None = None) -> str:
        """Add a skill to the library. Returns skill name.

        Idempotent: first call creates, subsequent calls update.
        """
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

        # Store files in repo and commit
        commit_hash = self.backend.put_skill(skill_name, source_dir)

        # Collect file info
        files = list(source_dir.rglob("*"))
        files = [f for f in files if f.is_file()]
        total_size = sum(f.stat().st_size for f in files)

        # DB key includes library for cross-library uniqueness
        db_name = f"{lib}/{skill_name}"

        skill_id = self.db.upsert_skill(Skill(
            repo=repo_name,
            name=db_name,
            description=meta.description,
            category=meta.category,
            author=meta.author,
            source=skill_source,
            commit=commit_hash,
            file_count=len(files),
            total_size=total_size,
            updated_at=now,
        ))

        if meta.tags:
            self.db.set_tags(skill_id, meta.tags)

        return skill_name

    def _db_name(self, name: str) -> str:
        """Qualify a skill name with the current library for DB lookup."""
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
            return self.db.get_skill(name, repo=repo)

        db_name = f"{self.current_library()}/{name}"
        active = self.config.library.active_repo
        skill = self.db.get_skill(db_name, repo=active if not repo else repo)
        if skill:
            return skill

        return self.db.find_skill_by_short_name(name, repo=repo)

    def remove(self, name: str) -> bool:
        """Remove a skill from the current library."""
        self._snapshot()
        skill = self._resolve_skill(name)
        if skill is None:
            db_name = self._db_name(name)
            repo_name = self.config.library.active_repo
            skill = self.db.get_skill(db_name, repo=repo_name)
            if skill is None:
                return False

        parts = skill.name.split("/")
        unqualified = parts[-1] if len(parts) > 1 else skill.name

        self.db.delete_skill(skill.name, repo=skill.repo)
        self.backend.remove_skill(unqualified)
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

        skill = self._resolve_skill(name)
        if skill:
            skill.category = category
            self.db.update_skill(skill)
        return True

    def _get_scan_backends(self, repo: str | None = None) -> list[tuple[str, "LocalBackend"]]:
        """Get backends to scan."""
        if repo:
            if not self.repo_mgr.repo_exists(repo):
                raise ValueError(f"Repo '{repo}' not found")
            return [(repo, self.repo_mgr.get_backend(repo))]
        return self.repo_mgr.get_all_backends()

    def find_skills_by_tag(self, tag: str, repo: str | None = None) -> list[tuple[str, "SkillMeta"]]:
        """Find all skills that have a given tag."""
        from .metadata import scan_skill_dirs
        tag = tag.strip().lower()
        results = []
        for repo_name, backend in self._get_scan_backends(repo):
            for name, meta in scan_skill_dirs(backend.skills_dir):
                if tag in [t.lower() for t in meta.tags]:
                    results.append((name, meta))
        return results

    def find_skills_by_category(self, category: str, repo: str | None = None) -> list[tuple[str, "SkillMeta"]]:
        """Find all skills that match a category."""
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
            "total_size": self.db.total_size(),
            "backend": self.config.library.backend,
            "path": str(self.config.library_path),
        }

    def rebuild(self) -> int:
        """Rebuild database from skill files across all repos.

        Scans working trees for SKILL.md files.
        Returns total number of skills indexed.
        """
        self.db.initialize()

        self.db.conn.execute("DELETE FROM tags")
        self.db.conn.execute("DELETE FROM skills")
        self.db.conn.commit()

        count = 0
        for repo_name, backend in self.repo_mgr.get_all_backends():
            lib = backend.current_library()
            from .metadata import scan_skill_dirs
            for name, meta in scan_skill_dirs(backend.skills_dir):
                try:
                    now = datetime.now(timezone.utc).isoformat()
                    db_name = f"{lib}/{name}"
                    commit_hash, _ = backend.skill_commit_info(name)

                    skill_dir = backend.skills_dir / name
                    files = [f for f in skill_dir.rglob("*") if f.is_file()]
                    total_size = sum(f.stat().st_size for f in files)

                    skill_id = self.db.insert_skill(Skill(
                        repo=repo_name,
                        name=db_name,
                        description=meta.description,
                        category=meta.category,
                        author=meta.author,
                        commit=commit_hash,
                        file_count=len(files),
                        total_size=total_size,
                        updated_at=now,
                    ))

                    if meta.tags:
                        self.db.set_tags(skill_id, meta.tags)

                    count += 1
                except Exception:
                    continue

        return count

    # ── Library (branch) operations ──────────────────────────

    def current_library(self) -> str:
        return self.backend.current_library()

    def create_library(self, name: str, orphan: bool = False) -> None:
        self.backend.create_library(name, orphan=orphan)

    def switch_library(self, name: str, reset: bool = False) -> None:
        self.backend.switch_library(name, reset=reset)

    def delete_library(self, name: str) -> None:
        self.backend.delete_library(name)

    def list_libraries(self) -> list[str]:
        return self.backend.list_libraries()

    # ── Repo operations ──────────────────────────────────────

    def add_repo(self, name: str, url: str) -> None:
        """Clone a remote URL as a named repo. Auto-switches to it and indexes skills."""
        self.repo_mgr.clone_repo(name, url)
        self.switch_repo(name)
        self.rebuild()

    def init_repo(self, name: str) -> None:
        self.repo_mgr.init_repo(name)

    def remove_repo(self, name: str) -> None:
        if name == self.config.library.active_repo:
            raise ValueError(f"Cannot remove active repo '{name}'. Switch first.")
        self.repo_mgr.remove_repo(name)

    def switch_repo(self, name: str) -> None:
        if not self.repo_mgr.repo_exists(name):
            raise ValueError(f"Repo '{name}' not found")
        self.config.library.active_repo = name
        self.backend = self.repo_mgr.get_backend(name)
        save_config(self.config)

    def list_repos(self):
        return self.repo_mgr.list_repos()

    # ── Push / Pull ──────────────────────────────────────────

    def push(self, repo_name: str | None = None, as_branch: str | None = None) -> str:
        if repo_name is None:
            repo_name = self.config.library.active_repo
        backend = self.repo_mgr.get_backend(repo_name)
        return backend.git_push(as_branch=as_branch)

    def pull(self, repo_name: str | None = None) -> int:
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
        self.agent_dir.mkdir(exist_ok=True)
        self.skills_dir.mkdir(exist_ok=True)
        if not self.skills_json.exists():
            self.skills_json.write_text(json.dumps({"skills": {}}, indent=2) + "\n")

    def init(self) -> None:
        self._ensure_dirs()

    def _load_manifest(self) -> dict:
        if self.skills_json.exists():
            return json.loads(self.skills_json.read_text())
        return {"skills": {}}

    def _save_manifest(self, manifest: dict) -> None:
        self.skills_json.write_text(json.dumps(manifest, indent=2) + "\n")

    def find_skill_conflicts(self, skill_name: str) -> list[Path]:
        """Check if a skill exists in parent directories or global config."""
        conflicts = []
        home = Path.home()
        agent_dir_name = AGENT_DIRS.get(self.agent, f".{self.agent}")

        global_dest = home / agent_dir_name / "skills" / skill_name
        if global_dest.exists() or global_dest.is_symlink():
            if global_dest.resolve() != (self.skills_dir / skill_name).resolve():
                conflicts.append(global_dest)

        current = self.project_dir.parent
        while current != home.parent and current != current.parent:
            parent_dest = current / agent_dir_name / "skills" / skill_name
            if parent_dest.exists() or parent_dest.is_symlink():
                if parent_dest.resolve() != (self.skills_dir / skill_name).resolve():
                    conflicts.append(parent_dest)
            current = current.parent

        return conflicts

    def add(self, name: str, pin: bool = False, soft: bool = False) -> str:
        """Add a skill from library to project. Returns 'linked' or commit hash.

        If soft=True, creates a symlink to the skill directory in the repo
        working tree instead of copying files.
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
            backend = self.library.backend
            src = backend.skills_dir / skill_name
            if not src.exists():
                raise ValueError(f"Skill '{skill_name}' not found in working tree")

            if dest.is_symlink():
                dest.unlink()
            elif dest.exists():
                shutil.rmtree(dest)
            dest.symlink_to(src)
            installed = "linked"
        else:
            # Hard install: copy from working tree
            skill = self.library.info(name)
            if skill is None:
                # Try directly from working tree
                src = self.library.backend.skills_dir / skill_name
                if not src.exists():
                    raise ValueError(f"Skill '{name}' not found in library")
            else:
                if skill.repo and self.library.repo_mgr.repo_exists(skill.repo):
                    backend = self.library.repo_mgr.get_backend(skill.repo)
                else:
                    backend = self.library.backend
                src = backend.skills_dir / skill_name

            if dest.is_symlink():
                dest.unlink()
            elif dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
            installed = "copied"

        manifest = self._load_manifest()
        manifest["skills"][name] = {
            "soft": soft,
            "pinned": pin,
        }
        self._save_manifest(manifest)

        return installed

    def drop(self, name: str) -> bool:
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
        """Install missing skills from skills.json."""
        manifest = self._load_manifest()
        synced = []

        for name, info in manifest["skills"].items():
            dest = self.skills_dir / name
            if not dest.exists():
                self.add(name, pin=info.get("pinned", False), soft=info.get("soft", False))
                synced.append(name)

        return synced

    def upgrade(self, name: str | None = None) -> list[str]:
        """Re-copy hard-installed skills from library. Returns list of upgraded skill names."""
        manifest = self._load_manifest()
        upgraded = []

        targets = [name] if name else list(manifest["skills"].keys())

        for skill_name in targets:
            if skill_name not in manifest["skills"]:
                continue
            info = manifest["skills"][skill_name]
            if info.get("soft", False) or info.get("pinned", False):
                continue

            self.add(skill_name, pin=False, soft=False)
            upgraded.append(skill_name)

        return upgraded

    def list_skills(self) -> dict:
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
