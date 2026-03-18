"""Local filesystem backend with git-backed storage.

Each repo is a separate git clone under ``~/.skillm/repos/<name>/``.
Skill files live at the root of each repo.
Each branch is a **library** — a curated collection of skills.
Versions are git commits — no tags needed.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..git import GitRepo
from .base import LibraryBackend


class LocalBackend(LibraryBackend):
    """Local filesystem storage backend using git.

    Each instance wraps a single git repo (one clone).
    The working tree always reflects the active library (= current branch).
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

    def put_skill(self, name: str, source_dir: Path) -> str:
        """Copy skill files into the repo and commit. Returns commit hash."""
        dest = self.skills_dir / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source_dir, dest)

        self._git.add(name)
        self._git.commit(f"skillm: add {name}")
        return self._git.head_commit()

    def remove_skill(self, name: str) -> None:
        """Remove a skill from the working tree and commit."""
        target = self.skills_dir / name
        if target.exists():
            shutil.rmtree(target)
            self._git.add("-A")
            self._git.commit(f"skillm: remove {name}")

        # Clean cache
        cache = self._cache_dir / name
        if cache.exists():
            shutil.rmtree(cache)

    def list_skill_names(self) -> list[str]:
        """List skill directories in the working tree."""
        if not self.skills_dir.exists():
            return []
        names = []
        for item in sorted(self.skills_dir.iterdir()):
            if not item.is_dir() or item.name.startswith("."):
                continue
            if (item / "SKILL.md").exists():
                names.append(item.name)
        return names

    def skill_exists(self, name: str) -> bool:
        return (self.skills_dir / name / "SKILL.md").exists()

    def uncommitted_changes(self) -> list[str]:
        """Return list of changed skill directories in the working tree."""
        if not self._git.has_changes():
            return []
        result = self._git._run("status", "--porcelain", check=False)
        changed = set()
        for line in (result.stdout or "").strip().split("\n"):
            if not line.strip():
                continue
            # Format: "XY path" or "XY path -> new_path"
            path = line[3:].strip().split(" -> ")[0]
            # Get top-level directory (skill name)
            parts = path.split("/")
            if parts and not parts[0].startswith("."):
                changed.add(parts[0])
        return sorted(changed)

    def skill_commit_info(self, name: str) -> tuple[str, str]:
        """Get last commit hash and date for a skill directory.

        Returns (short_hash, iso_date).
        """
        result = self._git._run(
            "log", "-1", "--format=%h %aI", "--", name,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return ("", "")
        parts = result.stdout.strip().split(" ", 1)
        return (parts[0], parts[1] if len(parts) > 1 else "")

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
        """Push current branch to origin."""
        branch = self._current_library()
        if as_branch:
            result = self._git._run(
                "push", "origin", f"{branch}:{as_branch}",
                check=False,
            )
            if result.returncode != 0:
                from ..git import GitError
                raise GitError(f"push failed: {(result.stderr or '').strip()}")
            return (result.stdout or "").strip()
        else:
            return self._git.push("origin", include_tags=False)

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
        # Clear cache
        if self._cache_dir.exists():
            shutil.rmtree(self._cache_dir)
            self._cache_dir.mkdir(exist_ok=True)
