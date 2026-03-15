"""Local filesystem backend with git-backed versioning.

Each repo is a separate git clone under ``~/.skillm/repos/<name>/``.
Skill files live at the root of each repo.
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

    Each instance wraps a single git repo (one clone).
    The working tree always reflects the active library (= current branch).
    Tags use three-level namespace: ``library/skill/version``.
    """

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.skills_dir = repo_path
        self._cache_dir = repo_path / ".cache"
        self._git = GitRepo(repo_path)

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
        self.repo_path.mkdir(parents=True, exist_ok=True)
        self._cache_dir.mkdir(exist_ok=True)
        if not self._git.is_repo():
            # Create .gitignore before init
            gitignore = self.repo_path / ".gitignore"
            if not gitignore.exists():
                gitignore.write_text(".cache/\n")
            self._git.init()
            self._git.add(".gitignore")
            self._git.commit("skillm: init")

    def get_skill_files(self, name: str, version: str, library: str | None = None) -> Path:
        tag = self._tag_name(name, version, library)
        if not self._git.tag_exists(tag):
            raise FileNotFoundError(f"Skill files not found: {tag}")

        # Extract from git to cache directory
        lib = library or self._current_library()
        self._cache_dir.mkdir(exist_ok=True)
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

    def _auto_commit(self) -> None:
        """Commit any uncommitted changes so branch switches don't fail."""
        if self._git.has_changes():
            self._git.add("-A")
            self._git.commit("skillm: auto-commit before switch")

    def create_library(self, name: str, orphan: bool = False) -> None:
        """Create a new library branch.

        If orphan=True, starts empty. Otherwise forks from current branch.
        """
        self._auto_commit()
        self._git.create_branch(name, orphan=orphan)

    def switch_library(self, name: str, reset: bool = False) -> None:
        """Switch to a different library.

        If reset=True, hard-resets the branch to its remote tracking state
        (or first commit if no remote) after switching.
        """
        self._auto_commit()
        self._git.switch_branch(name)
        if reset:
            self._git.reset_branch()

    def delete_library(self, name: str) -> None:
        """Delete a library branch."""
        current = self._current_library()
        if name == current:
            raise ValueError(f"Cannot delete active library '{name}'. Switch first.")
        self._git.delete_branch(name)

    def list_libraries(self) -> list[str]:
        """List all local library names (branches)."""
        return self._git.list_branches()

    # ── Git push/pull (always target origin) ──────────────────

    def git_push(self, as_branch: str | None = None) -> str:
        """Push current branch and tags to origin."""
        branch = self._current_library()
        if as_branch:
            result = self._git._run(
                "push", "origin", f"{branch}:{as_branch}", "--tags",
                check=False,
            )
            if result.returncode != 0:
                from ..git import GitError
                raise GitError(f"push failed: {(result.stderr or '').strip()}")
            return (result.stdout or "").strip()
        else:
            return self._git.push("origin", include_tags=True)

    def git_pull(self) -> None:
        """Pull from origin (fetch + merge)."""
        self._git.fetch("origin")
        branch = self._current_library()
        # Merge remote branch into local (if remote tracking exists)
        result = self._git._run(
            "merge", f"origin/{branch}",
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            # Ignore if remote branch doesn't exist (local-only repo)
            if "not something we can merge" not in stderr and "refusing to merge" not in stderr:
                from ..git import GitError
                raise GitError(f"merge failed: {stderr}")
        # Clear cache since tags may have changed
        if self._cache_dir.exists():
            shutil.rmtree(self._cache_dir)
            self._cache_dir.mkdir(exist_ok=True)
