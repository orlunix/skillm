"""Tests for database snapshot management."""

import pytest
from pathlib import Path
from skillm.snapshot import create_snapshot, list_snapshots, rollback, _prune


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


def test_prune(tmp_path):
    lib_path, db = _make_library(tmp_path)

    # Create 15 snapshots
    for i in range(15):
        db.write_text(f"v{i}")
        create_snapshot(lib_path, max_keep=10)

    snaps = list_snapshots(lib_path)
    assert len(snaps) <= 10


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
