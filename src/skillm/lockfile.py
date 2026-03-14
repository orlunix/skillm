"""Lock file management for installed skills.

The lock file (.claude/skills.lock) records exact versions and integrity
info for reproducible installs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


LOCK_FILENAME = "skills.lock"


def _file_integrity(file_path: Path) -> str:
    """Compute sha256 hash of a file."""
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def _dir_integrity(dir_path: Path) -> str:
    """Compute a deterministic integrity hash for a directory.

    Hashes all files sorted by relative path, then hashes the combined result.
    """
    h = hashlib.sha256()
    for f in sorted(dir_path.rglob("*")):
        if f.is_file():
            rel = str(f.relative_to(dir_path))
            h.update(rel.encode())
            h.update(f.read_bytes())
    return h.hexdigest()


class LockEntry:
    """A single locked skill entry."""

    def __init__(
        self,
        name: str,
        version: str,
        source: str,
        commit: str = "",
        integrity: str = "",
    ):
        self.name = name
        self.version = version
        self.source = source
        self.commit = commit
        self.integrity = integrity

    def to_dict(self) -> dict:
        d = {
            "version": self.version,
            "source": self.source,
        }
        if self.commit:
            d["commit"] = self.commit
        if self.integrity:
            d["integrity"] = self.integrity
        return d

    @classmethod
    def from_dict(cls, name: str, data: dict) -> LockEntry:
        return cls(
            name=name,
            version=data.get("version", ""),
            source=data.get("source", ""),
            commit=data.get("commit", ""),
            integrity=data.get("integrity", ""),
        )


class LockFile:
    """Manages the skills.lock file."""

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self.entries: dict[str, LockEntry] = {}

    def load(self) -> None:
        """Load lock file from disk."""
        if not self.lock_path.exists():
            self.entries = {}
            return
        data = json.loads(self.lock_path.read_text())
        self.entries = {}
        for name, info in data.get("skills", {}).items():
            self.entries[name] = LockEntry.from_dict(name, info)

    def save(self) -> None:
        """Write lock file to disk."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "lockVersion": 1,
            "skills": {
                name: entry.to_dict()
                for name, entry in sorted(self.entries.items())
            },
        }
        self.lock_path.write_text(json.dumps(data, indent=2) + "\n")

    def set(
        self,
        name: str,
        version: str,
        source: str,
        commit: str = "",
        integrity: str = "",
    ) -> None:
        """Add or update a lock entry."""
        self.entries[name] = LockEntry(
            name=name,
            version=version,
            source=source,
            commit=commit,
            integrity=integrity,
        )

    def remove(self, name: str) -> bool:
        """Remove a lock entry. Returns True if it existed."""
        if name in self.entries:
            del self.entries[name]
            return True
        return False

    def get(self, name: str) -> LockEntry | None:
        """Get a lock entry by name."""
        return self.entries.get(name)

    def verify(self, name: str, installed_dir: Path) -> bool:
        """Verify installed skill matches lock file integrity."""
        entry = self.entries.get(name)
        if entry is None or not entry.integrity:
            return True  # No lock entry or no integrity = assume OK
        if not installed_dir.exists():
            return False
        return _dir_integrity(installed_dir) == entry.integrity
