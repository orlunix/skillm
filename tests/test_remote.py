"""Tests for remote management (git remotes on skills repo)."""

import pytest
from skillm.remote import RemoteConfig, load_remotes, save_remotes, get_default_remote


def test_empty_config(tmp_path, monkeypatch):
    monkeypatch.setattr("skillm.remote._remotes_path", lambda: tmp_path / "remotes.toml")
    config = load_remotes()
    assert config.default == ""
    assert config.remotes == []


def test_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("skillm.remote._remotes_path", lambda: tmp_path / "remotes.toml")

    config = RemoteConfig(default="team", remotes=["team", "backup"])
    save_remotes(config)

    loaded = load_remotes()
    assert loaded.default == "team"
    assert "team" in loaded.remotes
    assert "backup" in loaded.remotes


def test_get_default_remote(tmp_path, monkeypatch):
    monkeypatch.setattr("skillm.remote._remotes_path", lambda: tmp_path / "remotes.toml")

    assert get_default_remote() is None

    config = RemoteConfig(default="origin", remotes=["origin"])
    save_remotes(config)
    assert get_default_remote() == "origin"


def test_library_remote_operations(tmp_library):
    """Test add/remove/list remotes via Library (git remotes on skills repo)."""
    # Create a bare repo to use as remote
    import subprocess
    bare = tmp_library.config.library_path.parent / "bare.git"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", str(bare)], capture_output=True, check=True)

    # Add remote
    tmp_library.add_remote("origin", str(bare))
    assert tmp_library.has_remote("origin")

    # List remotes
    remotes = tmp_library.list_remotes()
    assert len(remotes) == 1
    assert remotes[0][0] == "origin"

    # Remove remote
    tmp_library.remove_remote("origin")
    assert not tmp_library.has_remote("origin")


def test_push_pull_via_git(tmp_path, sample_skill):
    """Test push/pull between two libraries via a shared bare repo."""
    import subprocess
    from skillm.config import Config
    from skillm.core import Library

    # Create a bare repo (like GitHub)
    bare = tmp_path / "shared.git"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", str(bare)], capture_output=True, check=True)

    # Create library A, publish a skill, push to bare
    lib_a_path = tmp_path / "lib_a"
    config_a = Config()
    config_a.library.path = str(lib_a_path)
    lib_a = Library(config_a)
    lib_a.init()
    lib_a.publish(sample_skill)
    lib_a.add_remote("shared", str(bare))
    lib_a.push("shared")

    # Create library B, pull from bare
    lib_b_path = tmp_path / "lib_b"
    config_b = Config()
    config_b.library.path = str(lib_b_path)
    lib_b = Library(config_b)
    lib_b.init()
    lib_b.add_remote("shared", str(bare))
    count = lib_b.pull("shared")

    assert count == 1
    skill = lib_b.info("my-skill")
    assert skill is not None
    assert skill.description == "A test skill for unit tests."


def test_push_pull_multiple_versions(tmp_path, sample_skill):
    """Push multiple versions, pull gets all of them."""
    import subprocess
    from skillm.config import Config
    from skillm.core import Library

    bare = tmp_path / "shared.git"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", str(bare)], capture_output=True, check=True)

    # Library A: publish two versions
    lib_a_path = tmp_path / "lib_a"
    config_a = Config()
    config_a.library.path = str(lib_a_path)
    lib_a = Library(config_a)
    lib_a.init()
    lib_a.publish(sample_skill)
    lib_a.publish(sample_skill)
    lib_a.add_remote("shared", str(bare))
    lib_a.push("shared")

    # Library B: pull
    lib_b_path = tmp_path / "lib_b"
    config_b = Config()
    config_b.library.path = str(lib_b_path)
    lib_b = Library(config_b)
    lib_b.init()
    lib_b.add_remote("shared", str(bare))
    lib_b.pull("shared")

    skill = lib_b.info("my-skill")
    assert skill is not None
    assert len(skill.versions) == 2
