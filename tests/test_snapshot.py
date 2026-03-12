"""Tests for database snapshot management."""

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from skillm.snapshot import (
    create_snapshot, list_snapshots, rollback, _prune,
    snapshot_dir, MIN_KEEP, MAX_AGE_DAYS, MAX_TOTAL_BYTES,
)


def _make_library(tmp_path):
    lib_path = tmp_path / "library"
    lib_path.mkdir()
    db = lib_path / "library.db"
    db.write_text("version1")
    return lib_path, db


def test_create_snapshot(tmp_path):
    lib_path, db = _make_library(tmp_path)
    snap = create_snapshot(lib_path)
    assert snap is not None
    assert snap.exists()
    assert snap.read_text() == "version1"


def test_create_snapshot_no_db(tmp_path):
    lib_path = tmp_path / "empty"
    lib_path.mkdir()
    assert create_snapshot(lib_path) is None


def test_list_snapshots(tmp_path):
    lib_path, db = _make_library(tmp_path)
    create_snapshot(lib_path)
    db.write_text("version2")
    create_snapshot(lib_path)

    snaps = list_snapshots(lib_path)
    assert len(snaps) == 2
    # Newest first
    assert snaps[0][0].read_text() == "version2"
    assert snaps[1][0].read_text() == "version1"


def test_rollback_latest(tmp_path):
    lib_path, db = _make_library(tmp_path)
    create_snapshot(lib_path)

    db.write_text("version2")
    create_snapshot(lib_path)

    db.write_text("version3")

    rollback(lib_path)
    assert db.read_text() == "version2"


def test_rollback_specific(tmp_path):
    lib_path, db = _make_library(tmp_path)
    snap1 = create_snapshot(lib_path)

    db.write_text("version2")
    create_snapshot(lib_path)

    db.write_text("version3")

    rollback(lib_path, snap1)
    assert db.read_text() == "version1"


def test_rollback_no_snapshots(tmp_path):
    lib_path = tmp_path / "empty"
    lib_path.mkdir()
    (lib_path / "library.db").write_text("data")

    with pytest.raises(ValueError, match="No snapshots"):
        rollback(lib_path)


def test_prune_keeps_min(tmp_path):
    """Always keeps at least MIN_KEEP snapshots even if old."""
    lib_path, db = _make_library(tmp_path)

    # Create 15 snapshots (all recent, all small)
    for i in range(15):
        db.write_text(f"v{i}")
        create_snapshot(lib_path)

    snaps = list_snapshots(lib_path)
    # All recent and small — should keep all 15 (under size/age limits)
    assert len(snaps) >= MIN_KEEP


def test_prune_by_age(tmp_path, monkeypatch):
    """Snapshots older than MAX_AGE_DAYS are removed (beyond MIN_KEEP)."""
    lib_path, db = _make_library(tmp_path)
    snap_d = snapshot_dir(lib_path)
    snap_d.mkdir(parents=True, exist_ok=True)

    # Create 15 snapshots with fake old timestamps
    old_time = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS + 5)
    for i in range(15):
        ts = (old_time + timedelta(seconds=i)).strftime("%Y%m%dT%H%M%S%fZ")
        (snap_d / f"library.db.{ts}").write_text(f"old{i}")

    # Create 3 recent ones
    for i in range(3):
        db.write_text(f"new{i}")
        create_snapshot(lib_path)

    snaps = list_snapshots(lib_path)
    # Should keep MIN_KEEP total (old ones pruned, recent kept)
    assert len(snaps) >= 3  # at least the recent ones
    assert len(snaps) <= MIN_KEEP + 3


def test_prune_by_size(tmp_path):
    """Snapshots pruned when total exceeds MAX_TOTAL_BYTES (beyond MIN_KEEP)."""
    import skillm.snapshot as snap_mod
    original_max = snap_mod.MAX_TOTAL_BYTES

    try:
        # Set a tiny limit to trigger size pruning
        snap_mod.MAX_TOTAL_BYTES = 100  # 100 bytes

        lib_path, db = _make_library(tmp_path)

        # Create 15 snapshots with some content
        for i in range(15):
            db.write_text(f"data{i}" * 10)
            create_snapshot(lib_path)

        snaps = list_snapshots(lib_path)
        # Should keep exactly MIN_KEEP (size limit forces pruning)
        assert len(snaps) == MIN_KEEP
    finally:
        snap_mod.MAX_TOTAL_BYTES = original_max


def test_rollback_creates_safety_snapshot(tmp_path):
    lib_path, db = _make_library(tmp_path)
    create_snapshot(lib_path)

    db.write_text("current")
    rollback(lib_path)

    # Should now have 2 snapshots: original + safety snapshot of "current"
    snaps = list_snapshots(lib_path)
    assert len(snaps) >= 2
    # One of them should contain "current"
    contents = [s[0].read_text() for s in snaps]
    assert "current" in contents
