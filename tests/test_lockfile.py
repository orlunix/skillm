"""Tests for lock file management."""

from pathlib import Path
from skillm.lockfile import LockFile, LockEntry, _dir_integrity


def test_lock_file_roundtrip(tmp_path):
    lock_path = tmp_path / "skills.lock"
    lock = LockFile(lock_path)

    lock.set("my-skill", "v1.0", "infra", commit="abc123", integrity="sha256hash")
    lock.set("other-skill", "v0.2", "personal")
    lock.save()

    # Reload
    lock2 = LockFile(lock_path)
    lock2.load()

    assert "my-skill" in lock2.entries
    assert lock2.entries["my-skill"].version == "v1.0"
    assert lock2.entries["my-skill"].source == "infra"
    assert lock2.entries["my-skill"].commit == "abc123"
    assert lock2.entries["my-skill"].integrity == "sha256hash"

    assert "other-skill" in lock2.entries
    assert lock2.entries["other-skill"].version == "v0.2"


def test_lock_remove(tmp_path):
    lock = LockFile(tmp_path / "skills.lock")
    lock.set("a", "v1", "src")
    lock.set("b", "v2", "src")
    assert lock.remove("a")
    assert "a" not in lock.entries
    assert not lock.remove("nonexistent")


def test_lock_get(tmp_path):
    lock = LockFile(tmp_path / "skills.lock")
    lock.set("a", "v1", "src")
    assert lock.get("a") is not None
    assert lock.get("b") is None


def test_dir_integrity(tmp_path):
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("content")
    (skill_dir / "helper.py").write_text("code")

    h1 = _dir_integrity(skill_dir)
    assert len(h1) == 64  # sha256

    # Same content = same hash
    h2 = _dir_integrity(skill_dir)
    assert h1 == h2

    # Different content = different hash
    (skill_dir / "helper.py").write_text("changed")
    h3 = _dir_integrity(skill_dir)
    assert h3 != h1


def test_verify_integrity(tmp_path):
    lock = LockFile(tmp_path / "skills.lock")

    skill_dir = tmp_path / "installed" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("content")

    integrity = _dir_integrity(skill_dir)
    lock.set("my-skill", "v1", "src", integrity=integrity)

    # Should pass
    assert lock.verify("my-skill", skill_dir)

    # Modify file
    (skill_dir / "SKILL.md").write_text("changed")
    assert not lock.verify("my-skill", skill_dir)
