"""Database snapshot management.

Auto-snapshots the library DB before write operations.
Keeps the last N snapshots and auto-prunes older ones.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MAX_SNAPSHOTS = 10
SNAPSHOTS_DIR = "snapshots"


def snapshot_dir(library_path: Path) -> Path:
    """Get the snapshots directory for a library."""
    return library_path / SNAPSHOTS_DIR


def create_snapshot(library_path: Path, max_keep: int = DEFAULT_MAX_SNAPSHOTS) -> Path | None:
    """Create a snapshot of library.db before a write operation.

    Returns the snapshot path, or None if no DB exists yet.
    """
    db_file = library_path / "library.db"
    if not db_file.exists():
        return None

    snap_dir = snapshot_dir(library_path)
    snap_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    snap_file = snap_dir / f"library.db.{ts}"

    shutil.copy2(db_file, snap_file)

    # Prune old snapshots
    _prune(snap_dir, max_keep)

    return snap_file


def list_snapshots(library_path: Path) -> list[tuple[Path, str]]:
    """List all snapshots, newest first. Returns (path, timestamp_str) pairs."""
    snap_dir = snapshot_dir(library_path)
    if not snap_dir.exists():
        return []

    snaps = sorted(snap_dir.glob("library.db.*"), reverse=True)
    result = []
    for snap in snaps:
        # Extract timestamp from filename: library.db.20260312T103045Z
        ts_str = snap.name.replace("library.db.", "")
        try:
            ts = datetime.strptime(ts_str, "%Y%m%dT%H%M%S%fZ")
            human = ts.strftime("%Y-%m-%d %H:%M:%S UTC")
        except ValueError:
            try:
                ts = datetime.strptime(ts_str, "%Y%m%dT%H%M%SZ")
                human = ts.strftime("%Y-%m-%d %H:%M:%S UTC")
            except ValueError:
                human = ts_str
        result.append((snap, human))

    return result


def rollback(library_path: Path, snapshot_path: Path | None = None) -> Path:
    """Rollback the DB to a snapshot.

    If no snapshot_path given, uses the most recent one.
    Returns the snapshot that was restored.
    Raises ValueError if no snapshots available.
    """
    if snapshot_path is None:
        snaps = list_snapshots(library_path)
        if not snaps:
            raise ValueError("No snapshots available")
        snapshot_path = snaps[0][0]

    if not snapshot_path.exists():
        raise ValueError(f"Snapshot not found: {snapshot_path}")

    db_file = library_path / "library.db"

    # Snapshot current state before rollback (so rollback is reversible)
    if db_file.exists():
        create_snapshot(library_path)

    shutil.copy2(snapshot_path, db_file)
    return snapshot_path


def _prune(snap_dir: Path, max_keep: int) -> int:
    """Remove oldest snapshots beyond max_keep. Returns number removed."""
    snaps = sorted(snap_dir.glob("library.db.*"), reverse=True)
    removed = 0
    for snap in snaps[max_keep:]:
        snap.unlink()
        removed += 1
    return removed
