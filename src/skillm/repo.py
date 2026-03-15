"""Multi-repo management for skillm.

Each remote URL gets its own git clone under ~/.skillm/repos/<name>/.
Local-only repos are created with git init (no remote).
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .backends.local import LocalBackend
from .git import GitError


@dataclass
class RepoInfo:
    name: str
    path: Path
    url: str  # origin URL, or "" for local-only repos


class RepoManager:
    """Manages multiple git repo clones under ~/.skillm/repos/."""

    def __init__(self, base_path: Path):
        self.repos_dir = base_path / "repos"

    def init_repo(self, name: str) -> LocalBackend:
        """Create a local-only repo (git init, no remote)."""
        repo_path = self.repos_dir / name
        backend = LocalBackend(repo_path)
        backend.initialize()
        return backend

    def clone_repo(self, name: str, url: str) -> LocalBackend:
        """Clone a remote URL into repos/<name>/."""
        repo_path = self.repos_dir / name
        if repo_path.exists():
            raise ValueError(f"Repo '{name}' already exists at {repo_path}")
        self.repos_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "clone", url, str(repo_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise GitError(f"clone failed: {(result.stderr or '').strip()}")

        backend = LocalBackend(repo_path)
        # Ensure .cache and .gitignore exist
        cache_dir = repo_path / ".cache"
        cache_dir.mkdir(exist_ok=True)
        gitignore = repo_path / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(".cache/\n")
        return backend

    def get_backend(self, name: str) -> LocalBackend:
        """Get LocalBackend for an existing repo."""
        repo_path = self.repos_dir / name
        if not repo_path.exists():
            raise ValueError(f"Repo '{name}' not found")
        return LocalBackend(repo_path)

    def remove_repo(self, name: str) -> None:
        """Delete a repo directory."""
        repo_path = self.repos_dir / name
        if repo_path.exists():
            shutil.rmtree(repo_path)

    def list_repos(self) -> list[RepoInfo]:
        """List all repos with name, path, origin URL."""
        if not self.repos_dir.exists():
            return []
        repos = []
        for entry in sorted(self.repos_dir.iterdir()):
            if entry.is_dir() and (entry / ".git").exists():
                url = self._get_origin_url(entry)
                repos.append(RepoInfo(name=entry.name, path=entry, url=url))
        return repos

    def repo_exists(self, name: str) -> bool:
        repo_path = self.repos_dir / name
        return repo_path.exists() and (repo_path / ".git").exists()

    def get_all_backends(self) -> list[tuple[str, LocalBackend]]:
        """All (repo_name, backend) pairs for rebuild."""
        result = []
        for info in self.list_repos():
            result.append((info.name, LocalBackend(info.path)))
        return result

    def _get_origin_url(self, repo_path: Path) -> str:
        """Get the origin remote URL for a repo, or empty string."""
        try:
            result = subprocess.run(
                ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ""
