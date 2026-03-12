"""Local filesystem backend."""

from __future__ import annotations

import shutil
from pathlib import Path

from .base import LibraryBackend


class LocalBackend(LibraryBackend):
    """Local filesystem storage backend."""

    def __init__(self, library_path: Path):
        self.library_path = library_path
        self.skills_dir = library_path / "skills"
        self.db_file = library_path / "library.db"

    def initialize(self) -> None:
        self.library_path.mkdir(parents=True, exist_ok=True)
        self.skills_dir.mkdir(exist_ok=True)

    def get_db(self) -> Path:
        return self.db_file

    def put_db(self, local_db: Path) -> None:
        if local_db != self.db_file:
            shutil.copy2(local_db, self.db_file)

    def get_skill_files(self, name: str, version: str) -> Path:
        path = self.skills_dir / name / version
        if not path.exists():
            raise FileNotFoundError(f"Skill files not found: {name}/{version}")
        return path

    def put_skill_files(self, name: str, version: str, source_dir: Path) -> None:
        dest = self.skills_dir / name / version
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source_dir, dest)

    def remove_skill_files(self, name: str, version: str | None = None) -> None:
        if version:
            target = self.skills_dir / name / version
        else:
            target = self.skills_dir / name

        if target.exists():
            shutil.rmtree(target)

        # Clean up empty parent dir
        if version:
            parent = self.skills_dir / name
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()

    def list_skill_dirs(self) -> list[tuple[str, list[str]]]:
        if not self.skills_dir.exists():
            return []

        result = []
        for skill_dir in sorted(self.skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            versions = sorted(
                [v.name for v in skill_dir.iterdir() if v.is_dir()],
            )
            if versions:
                result.append((skill_dir.name, versions))
        return result

    def skill_exists(self, name: str, version: str) -> bool:
        return (self.skills_dir / name / version).exists()
