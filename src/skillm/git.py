"""Git repository wrapper for skillm.

All git operations go through this module. Users never touch git directly.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_VERSION_TAG_RE = re.compile(r"^(.+)/v(\d+)\.(\d+)$")


class GitError(Exception):
    """Raised when a git command fails."""


class GitRepo:
    """Wrapper around a git repository."""

    def __init__(self, path: Path):
        self.path = Path(path).expanduser().resolve()

    def _run(
        self,
        *args: str,
        check: bool = True,
        capture: bool = True,
    ) -> subprocess.CompletedProcess:
        """Run a git command in the repo directory."""
        cmd = ["git", "-C", str(self.path), *args]
        try:
            return subprocess.run(
                cmd,
                capture_output=capture,
                text=True,
                check=check,
            )
        except subprocess.CalledProcessError as e:
            raise GitError(
                f"git {' '.join(args)} failed (exit {e.returncode}): "
                f"{(e.stderr or '').strip()}"
            ) from e

    # ── Repository lifecycle ─────────────────────────────────

    def init(self) -> None:
        """Initialize a new git repository."""
        self.path.mkdir(parents=True, exist_ok=True)
        self._run("init")

    def is_repo(self) -> bool:
        """Check if path is a git repository."""
        try:
            result = self._run("rev-parse", "--git-dir", check=False)
            return result.returncode == 0
        except Exception:
            return False

    # ── Basic operations ─────────────────────────────────────

    def add(self, *paths: str) -> None:
        """Stage files."""
        self._run("add", *paths)

    def commit(self, message: str) -> str:
        """Create a commit. Returns the commit hash."""
        self._run("commit", "-m", message, "--allow-empty")
        return self.head_commit()

    def head_commit(self) -> str:
        """Get the current HEAD commit hash."""
        result = self._run("rev-parse", "HEAD")
        return result.stdout.strip()

    def status(self, short: bool = True) -> str:
        """Get working tree status."""
        args = ["status"]
        if short:
            args.append("--short")
        result = self._run(*args)
        return result.stdout.strip()

    def has_changes(self, path: str | None = None) -> bool:
        """Check if there are uncommitted changes."""
        args = ["status", "--porcelain"]
        if path:
            args.extend(["--", path])
        result = self._run(*args)
        return bool(result.stdout.strip())

    def diff(self, path: str | None = None, staged: bool = False) -> str:
        """Get diff output."""
        args = ["diff"]
        if staged:
            args.append("--cached")
        if path:
            args.extend(["--", path])
        result = self._run(*args)
        return result.stdout

    # ── Log ──────────────────────────────────────────────────

    def log(
        self,
        path: str | None = None,
        max_count: int = 20,
        oneline: bool = True,
    ) -> str:
        """Get git log."""
        args = ["log", f"--max-count={max_count}"]
        if oneline:
            args.append("--oneline")
        if path:
            args.extend(["--", path])
        result = self._run(*args)
        return result.stdout.strip()

    # ── Tags (versions) ─────────────────────────────────────

    def tag(self, name: str, message: str | None = None) -> None:
        """Create a tag."""
        args = ["tag"]
        if message:
            args.extend(["-a", name, "-m", message])
        else:
            args.extend(["-a", name, "-m", name])
        self._run(*args)

    def list_tags(self, pattern: str | None = None) -> list[str]:
        """List tags, optionally filtered by pattern."""
        args = ["tag", "-l"]
        if pattern:
            args.append(pattern)
        result = self._run(*args)
        tags = result.stdout.strip().split("\n")
        return [t for t in tags if t]

    def tag_commit(self, tag_name: str) -> str:
        """Get the commit hash for a tag."""
        result = self._run("rev-list", "-1", tag_name)
        return result.stdout.strip()

    def tag_exists(self, tag_name: str) -> bool:
        """Check if a tag exists."""
        result = self._run("tag", "-l", tag_name)
        return bool(result.stdout.strip())

    def delete_tag(self, tag_name: str) -> None:
        """Delete a tag."""
        self._run("tag", "-d", tag_name)

    # ── File extraction ──────────────────────────────────────

    def show_file(self, ref: str, path: str) -> bytes:
        """Get file contents at a specific ref."""
        cmd = ["git", "-C", str(self.path), "show", f"{ref}:{path}"]
        result = subprocess.run(cmd, capture_output=True, check=True)
        return result.stdout

    def list_files(self, ref: str, path: str = "") -> list[str]:
        """List files at a ref, optionally under a path prefix."""
        args = ["ls-tree", "-r", "--name-only", ref]
        if path:
            args.append(path)
        result = self._run(*args)
        lines = result.stdout.strip().split("\n")
        return [l for l in lines if l]

    def extract_to(self, ref: str, prefix: str, dest: Path) -> None:
        """Extract files at ref/prefix to a destination directory."""
        dest.mkdir(parents=True, exist_ok=True)
        files = self.list_files(ref, prefix)
        for file_path in files:
            if prefix:
                # Strip prefix to get relative path within skill dir
                rel = file_path[len(prefix):].lstrip("/")
            else:
                rel = file_path
            if not rel:
                continue
            out_file = dest / rel
            out_file.parent.mkdir(parents=True, exist_ok=True)
            content = self.show_file(ref, file_path)
            out_file.write_bytes(content)

    # ── Remote operations ────────────────────────────────────

    def push(self, remote: str = "origin", include_tags: bool = True) -> str:
        """Push to remote."""
        args = ["push", remote]
        if include_tags:
            args.append("--tags")
        result = self._run(*args, check=False)
        if result.returncode != 0:
            raise GitError(f"push failed: {(result.stderr or '').strip()}")
        return (result.stdout or "").strip()

    def pull(self, remote: str = "origin") -> str:
        """Pull from remote."""
        args = ["pull", remote]
        result = self._run(*args, check=False)
        if result.returncode != 0:
            raise GitError(f"pull failed: {(result.stderr or '').strip()}")
        return (result.stdout or "").strip()

    def has_remote(self, name: str = "origin") -> bool:
        """Check if a remote exists."""
        result = self._run("remote")
        remotes = result.stdout.strip().split("\n")
        return name in remotes

    def fetch(self, remote: str = "origin") -> None:
        """Fetch from remote."""
        self._run("fetch", remote, "--tags")

    # ── Version helpers ──────────────────────────────────────

    def skill_versions(self, skill_name: str) -> list[tuple[str, int, int]]:
        """Get all versions for a skill from tags.

        Returns list of (tag_name, major, minor) sorted by version.
        """
        tags = self.list_tags(f"{skill_name}/v*")
        versions = []
        for t in tags:
            m = _VERSION_TAG_RE.match(t)
            if m and m.group(1) == skill_name:
                versions.append((t, int(m.group(2)), int(m.group(3))))
        versions.sort(key=lambda x: (x[1], x[2]))
        return versions

    def next_version(self, skill_name: str, major: bool = False) -> str:
        """Compute the next version string for a skill."""
        versions = self.skill_versions(skill_name)
        if not versions:
            return "v1.0" if major else "v0.1"

        _, max_maj, max_min = versions[-1]
        if major:
            return f"v{max_maj + 1}.0"
        return f"v{max_maj}.{max_min + 1}"

    def list_skill_dirs(self) -> list[str]:
        """List top-level directories that contain SKILL.md (i.e., skills)."""
        if not self.is_repo():
            return []
        # Look for any SKILL.md files in the working tree
        skills = set()
        for skill_md in self.path.rglob("SKILL.md"):
            rel = skill_md.relative_to(self.path)
            # Top-level skill: SKILL.md is at <skill-name>/SKILL.md
            parts = rel.parts
            if len(parts) == 2 and parts[1] == "SKILL.md":
                skills.add(parts[0])
        return sorted(skills)
