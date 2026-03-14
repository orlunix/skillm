"""Local filesystem backend with git-backed versioning.

Skill files live in a git repo at ``library_path/skills/``.
Each branch is a **library** — a curated collection of skills.
Versions are three-level git tags: ``library/skill/version``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..git import GitRepo
from .base import LibraryBackend


class LocalBackend(LibraryBackend):
    """Local filesystem storage backend using git for versioning.

    The working tree always reflects the active library (= current branch).
    Tags use three-level namespace: ``library/skill/version``.
    """

    def __init__(self, library_path: Path):
        self.library_path = library_path
        self.skills_dir = library_path / "skills"
        self.db_file = library_path / "library.db"
        self._cache_dir = library_path / ".cache"
        self._git = GitRepo(self.skills_dir)

    @property
    def git(self) -> GitRepo:
        """Expose git repo for direct branch/remote operations."""
        return self._git

    def _current_library(self) -> str:
        """Get the active library name (= current git branch)."""
        return self._git.current_branch()

    def _tag_name(self, name: str, version: str, library: str | None = None) -> str:
        """Build a three-level tag: library/skill/version."""
        lib = library or self._current_library()
        return f"{lib}/{name}/{version}"

    def initialize(self) -> None:
        self.library_path.mkdir(parents=True, exist_ok=True)
        self.skills_dir.mkdir(exist_ok=True)
        self._cache_dir.mkdir(exist_ok=True)
        if not self._git.is_repo():
            self._git.init()
            # Initial commit on default 'main' branch so tags have something to point at
            self._git.commit("skillm: init")

    def get_db(self) -> Path:
        return self.db_file

    def put_db(self, local_db: Path) -> None:
        if local_db != self.db_file:
            shutil.copy2(local_db, self.db_file)

    def get_skill_files(self, name: str, version: str, library: str | None = None) -> Path:
        tag = self._tag_name(name, version, library)
        if not self._git.tag_exists(tag):
            raise FileNotFoundError(f"Skill files not found: {tag}")

        # Extract from git to cache directory
        lib = library or self._current_library()
        cache_path = self._cache_dir / lib / name / version
        if cache_path.exists():
            shutil.rmtree(cache_path)
        self._git.extract_to(tag, name, cache_path)
        return cache_path

    def put_skill_files(self, name: str, version: str, source_dir: Path) -> None:
        dest = self.skills_dir / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source_dir, dest)

        self._git.add(name)
        self._git.commit(f"skillm: {name} {version}")

        tag = self._tag_name(name, version)
        if self._git.tag_exists(tag):
            self._git.delete_tag(tag)
        self._git.tag(tag, f"{name} {version}")

    def remove_skill_files(self, name: str, version: str | None = None) -> None:
        lib = self._current_library()
        if version:
            tag = self._tag_name(name, version)
            if self._git.tag_exists(tag):
                self._git.delete_tag(tag)
        else:
            # Remove all version tags for this skill in the current library
            tags = self._git.list_tags(f"{lib}/{name}/*")
            for t in tags:
                self._git.delete_tag(t)

            # Remove from working tree and commit
            target = self.skills_dir / name
            if target.exists():
                shutil.rmtree(target)
                self._git.add("-A")
                self._git.commit(f"skillm: remove {name}")

        # Clean cache
        cache = self._cache_dir / lib / name
        if version:
            cache = cache / version
        if cache.exists():
            shutil.rmtree(cache)

    def list_skill_dirs(self, library: str | None = None) -> list[tuple[str, list[str]]]:
        """List skills and their versions.

        If library is specified, returns only skills from that library.
        Otherwise returns skills from all libraries.

        Returns list of (skill_name, [versions]) tuples.
        """
        if not self._git.is_repo():
            return []

        parsed = self._git.parse_all_tags()
        skills: dict[str, list[str]] = {}

        for lib, skill_name, version in parsed:
            if library and lib != library:
                continue
            skills.setdefault(skill_name, []).append(version)

        return [(name, sorted(versions)) for name, versions in sorted(skills.items())]

    def list_skill_dirs_by_library(self) -> dict[str, list[tuple[str, list[str]]]]:
        """List skills grouped by library.

        Returns dict of {library: [(skill_name, [versions])]}.
        """
        if not self._git.is_repo():
            return {}

        parsed = self._git.parse_all_tags()
        libs: dict[str, dict[str, list[str]]] = {}

        for lib, skill_name, version in parsed:
            libs.setdefault(lib, {}).setdefault(skill_name, []).append(version)

        return {
            lib: [(name, sorted(vers)) for name, vers in sorted(skills.items())]
            for lib, skills in sorted(libs.items())
        }

    def skill_exists(self, name: str, version: str, library: str | None = None) -> bool:
        tag = self._tag_name(name, version, library)
        return self._git.tag_exists(tag)

    # ── Library (branch) operations ────────────────────────────

    def current_library(self) -> str:
        """Get the active library name."""
        return self._current_library()

    def create_library(self, name: str) -> None:
        """Create a new library (orphan branch with init commit)."""
        self._git.create_branch(name, orphan=True)

    def switch_library(self, name: str) -> None:
        """Switch to a different library."""
        self._git.switch_branch(name)

    def delete_library(self, name: str) -> None:
        """Delete a library branch."""
        current = self._current_library()
        if name == current:
            raise ValueError(f"Cannot delete active library '{name}'. Switch first.")
        self._git.delete_branch(name)

    def list_libraries(self) -> list[str]:
        """List all local library names (branches)."""
        return self._git.list_branches()

    # ── Git remote operations ─────────────────────────────────

    def add_remote(self, name: str, url: str) -> None:
        """Add a git remote to the skills repo."""
        self._git.add_remote(name, url)

    def remove_remote(self, name: str) -> None:
        """Remove a git remote from the skills repo."""
        self._git.remove_remote(name)

    def list_remotes(self) -> list[tuple[str, str]]:
        """List git remotes as (name, url) pairs."""
        return self._git.list_remotes()

    def has_remote(self, name: str) -> bool:
        """Check if a git remote exists."""
        return self._git.has_remote(name)

    def git_push(self, remote: str = "origin", as_branch: str | None = None) -> str:
        """Push current branch and tags to a git remote."""
        branch = self._current_library()
        if as_branch:
            # Push to a different branch name on remote
            result = self._git._run(
                "push", remote, f"{branch}:{as_branch}", "--tags",
                check=False,
            )
            if result.returncode != 0:
                from ..git import GitError
                raise GitError(f"push failed: {(result.stderr or '').strip()}")
            return (result.stdout or "").strip()
        else:
            return self._git.push(remote, include_tags=True)

    def git_pull(self, remote: str = "origin") -> None:
        """Fetch all commits and tags from a git remote."""
        self._git.fetch(remote)
        # Clear cache since tags may have changed
        if self._cache_dir.exists():
            shutil.rmtree(self._cache_dir)
            self._cache_dir.mkdir(exist_ok=True)

    # ── Git remote operations ─────────────────────────────────

