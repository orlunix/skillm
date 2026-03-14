"""Abstract base class for library storage backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class LibraryBackend(ABC):
    """Abstract interface for skill library storage."""

    @abstractmethod
    def initialize(self) -> None:
        """Set up the backend (create dirs, etc.)."""

    @abstractmethod
    def get_db(self) -> Path:
        """Get or download library.db to a local path."""

    @abstractmethod
    def put_db(self, local_db: Path) -> None:
        """Upload/save the updated library.db."""

    @abstractmethod
    def get_skill_files(self, name: str, version: str, library: str | None = None) -> Path:
        """Fetch skill files, return local directory path."""

    @abstractmethod
    def put_skill_files(self, name: str, version: str, source_dir: Path) -> None:
        """Store skill files from a local directory."""

    @abstractmethod
    def remove_skill_files(self, name: str, version: str | None = None) -> None:
        """Remove skill files. If version is None, remove all versions."""

    @abstractmethod
    def list_skill_dirs(self, library: str | None = None) -> list[tuple[str, list[str]]]:
        """List all skills and their versions from the file store."""

    @abstractmethod
    def skill_exists(self, name: str, version: str, library: str | None = None) -> bool:
        """Check if a skill version exists in the store."""
