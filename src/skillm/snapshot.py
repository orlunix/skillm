"""Database snapshot management.

Auto-snapshots the library DB before write operations.
Prunes based on:
  - Age: keep snapshots from the last 30 days
  - Disk usage: total snapshots stay under 100MB
  - Minimum: always keep at least 10 snapshots regardless
"""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

SNAPSHOTS_DIR = "snapshots"
MIN_KEEP = 10
MAX_AGE_DAYS = 30
MAX_TOTAL_BYTES = 100 * 1024 * 1024  # 100MB


def snapshot_dir(library_path: Path) -> Path:
    """Get the snapshots directory for a library."""
    return library_path / SNAPSHOTS_DIR


def create_snapshot(library_path: Path) -> Path | None:
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

    _prune(snap_dir)

    return snap_file


def list_snapshots(library_path: Path) -> list[tuple[Path, str]]:
    """List all snapshots, newest first. Returns (path, timestamp_str) pairs."""
    snap_dir = snapshot_dir(library_path)
    if not snap_dir.exists():
        return []

    snaps = sorted(snap_dir.glob("library.db.*"), reverse=True)
    result = []
    for snap in snaps:
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


def _parse_snap_time(snap: Path) -> datetime | None:
    """Parse timestamp from snapshot filename."""
    ts_str = snap.name.replace("library.db.", "")
    for fmt in ("%Y%m%dT%H%M%S%fZ", "%Y%m%dT%H%M%SZ"):
        try:
            return datetime.strptime(ts_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _prune(snap_dir: Path) -> int:
    """Prune snapshots by age and disk usage.

    Rules (applied in order):
    1. Always keep at least MIN_KEEP snapshots
    2. Remove snapshots older than MAX_AGE_DAYS
    3. If total size exceeds MAX_TOTAL_BYTES, remove oldest until under limit

    Returns number of snapshots removed.
    """
    snaps = sorted(snap_dir.glob("library.db.*"), reverse=True)

    if len(snaps) <= MIN_KEEP:
        return 0

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=MAX_AGE_DAYS)
    removed = 0

    # Pass 1: remove old snapshots (keep at least MIN_KEEP)
    for snap in list(snaps[MIN_KEEP:]):
        ts = _parse_snap_time(snap)
        if ts and ts < cutoff:
            snap.unlink()
            snaps.remove(snap)
            removed += 1

    # Pass 2: remove by size (keep at least MIN_KEEP)
    if len(snaps) > MIN_KEEP:
        total = sum(s.stat().st_size for s in snaps)
        for snap in list(reversed(snaps[MIN_KEEP:])):  # oldest first among pruneable
            if total <= MAX_TOTAL_BYTES:
                break
            size = snap.stat().st_size
            snap.unlink()
            snaps.remove(snap)
            total -= size
            removed += 1

    return removed
