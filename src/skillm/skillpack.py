"""Export and import .skillpack archives."""

from __future__ import annotations

import json
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import __version__


def export_skill(
    library_path: Path,
    name: str,
    version: str,
    skill_info: dict,
    output_dir: Path | None = None,
) -> Path:
    """Export a skill version as a .skillpack archive.

    Args:
        library_path: Path to skill files directory in the library
        name: Skill name
        version: Version string
        skill_info: Dict with description, author, tags
        output_dir: Where to write the archive (default: cwd)

    Returns:
        Path to the created .skillpack file
    """
    output_dir = output_dir or Path.cwd()
    archive_name = f"{name}-{version}.skillpack"
    archive_path = output_dir / archive_name

    metadata = {
        "name": name,
        "version": version,
        "description": skill_info.get("description", ""),
        "author": skill_info.get("author", ""),
        "tags": skill_info.get("tags", []),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "skillm_version": __version__,
    }

    with tarfile.open(archive_path, "w:gz") as tar:
        # Add metadata
        meta_json = json.dumps(metadata, indent=2).encode("utf-8")
        import io
        meta_info = tarfile.TarInfo(name="skillpack.json")
        meta_info.size = len(meta_json)
        tar.addfile(meta_info, io.BytesIO(meta_json))

        # Add skill files under files/
        for file_path in sorted(library_path.rglob("*")):
            if file_path.is_file():
                arcname = "files/" + str(file_path.relative_to(library_path))
                tar.add(file_path, arcname=arcname)

    return archive_path


def import_skillpack(archive_path: Path) -> tuple[Path, dict]:
    """Extract a .skillpack archive to a temp directory.

    Returns:
        Tuple of (extracted_files_dir, metadata_dict)
    """
    archive_path = archive_path.resolve()

    if not archive_path.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    extract_dir = Path(tempfile.mkdtemp(prefix="skillm-import-"))

    with tarfile.open(archive_path, "r:gz") as tar:
        # Safety: check for path traversal
        for member in tar.getmembers():
            if member.name.startswith("/") or ".." in member.name:
                raise ValueError(f"Unsafe path in archive: {member.name}")
        tar.extractall(extract_dir)

    meta_file = extract_dir / "skillpack.json"
    if not meta_file.exists():
        raise ValueError("Invalid .skillpack: missing skillpack.json")

    metadata = json.loads(meta_file.read_text())
    files_dir = extract_dir / "files"

    if not files_dir.exists():
        raise ValueError("Invalid .skillpack: missing files/ directory")

    return files_dir, metadata
