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
    def put_skill(self, name: str, source_dir: Path) -> str:
        """Store skill files from a local directory. Returns commit hash."""

    @abstractmethod
    def remove_skill(self, name: str) -> None:
        """Remove a skill entirely."""

    @abstractmethod
    def list_skill_names(self) -> list[str]:
        """List all skill names in the working tree."""

    @abstractmethod
    def skill_exists(self, name: str) -> bool:
        """Check if a skill exists in the working tree."""
