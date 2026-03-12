"""Tests for remote library management."""

import pytest
from skillm.remote import (
    Remote,
    RemoteConfig,
    add_remote,
    load_remotes,
    remove_remote,
    save_remotes,
    switch_remote,
)


def test_remote_local():
    r = Remote(name="local", path="/home/user/.skillm")
    assert not r.is_ssh
    assert r.local_path.name == ".skillm"


def test_remote_ssh():
    r = Remote(name="team", path="ssh://user@host:/shared/lib")
    assert r.is_ssh
    host, path = r.parse_ssh()
    assert host == "user@host"
    assert path == "/shared/lib"


def test_remote_ssh_local_path_raises():
    r = Remote(name="team", path="ssh://user@host:/path")
    with pytest.raises(ValueError, match="SSH"):
        _ = r.local_path


def test_remote_parse_ssh_on_local_raises():
    r = Remote(name="local", path="/some/path")
    with pytest.raises(ValueError, match="Not an SSH"):
        r.parse_ssh()


def test_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("skillm.remote._remotes_path", lambda: tmp_path / "remotes.toml")

    config = RemoteConfig()
    config.remotes["local"] = Remote(name="local", path="/home/user/.skillm")
    config.remotes["team"] = Remote(name="team", path="ssh://dev@server:/opt/skills")
    config.active = "local"
    save_remotes(config)

    loaded = load_remotes()
    assert len(loaded.remotes) == 2
    assert loaded.active == "local"
    assert loaded.remotes["team"].is_ssh


def test_add_remote(tmp_path, monkeypatch):
    monkeypatch.setattr("skillm.remote._remotes_path", lambda: tmp_path / "remotes.toml")
    monkeypatch.setattr("skillm.remote.DEFAULT_SKILLM_DIR", tmp_path / ".skillm")

    config = add_remote("myserver", "ssh://me@box:/lib")
    assert "myserver" in config.remotes
    # Should also have default local
    assert config.active in config.remotes


def test_switch_remote(tmp_path, monkeypatch):
    monkeypatch.setattr("skillm.remote._remotes_path", lambda: tmp_path / "remotes.toml")
    monkeypatch.setattr("skillm.remote.DEFAULT_SKILLM_DIR", tmp_path / ".skillm")

    add_remote("a", "/path/a")
    add_remote("b", "/path/b")

    config = switch_remote("b")
    assert config.active == "b"


def test_switch_nonexistent(tmp_path, monkeypatch):
    monkeypatch.setattr("skillm.remote._remotes_path", lambda: tmp_path / "remotes.toml")
    monkeypatch.setattr("skillm.remote.DEFAULT_SKILLM_DIR", tmp_path / ".skillm")

    with pytest.raises(ValueError, match="not found"):
        switch_remote("nope")


def test_remove_remote(tmp_path, monkeypatch):
    monkeypatch.setattr("skillm.remote._remotes_path", lambda: tmp_path / "remotes.toml")
    monkeypatch.setattr("skillm.remote.DEFAULT_SKILLM_DIR", tmp_path / ".skillm")

    add_remote("a", "/path/a")
    add_remote("b", "/path/b")

    config = remove_remote("a")
    assert "a" not in config.remotes


def test_remove_last_remote_fails(tmp_path, monkeypatch):
    monkeypatch.setattr("skillm.remote._remotes_path", lambda: tmp_path / "remotes.toml")
    monkeypatch.setattr("skillm.remote.DEFAULT_SKILLM_DIR", tmp_path / ".skillm")

    # load_remotes creates default "local", then we add nothing else
    config = load_remotes()
    assert len(config.remotes) == 1

    with pytest.raises(ValueError, match="last remote"):
        remove_remote("local")


def test_active_switches_on_remove(tmp_path, monkeypatch):
    monkeypatch.setattr("skillm.remote._remotes_path", lambda: tmp_path / "remotes.toml")
    monkeypatch.setattr("skillm.remote.DEFAULT_SKILLM_DIR", tmp_path / ".skillm")

    add_remote("a", "/path/a")
    add_remote("b", "/path/b")
    switch_remote("a")

    config = remove_remote("a")
    assert config.active != "a"
    assert config.active in config.remotes
