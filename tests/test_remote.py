"""Tests for RepoManager (multi-repo management)."""

import subprocess
import pytest
from pathlib import Path

from skillm.repo import RepoManager


@pytest.fixture
def repo_mgr(tmp_path):
    """Create a RepoManager with a temporary base path."""
    return RepoManager(tmp_path)


@pytest.fixture
def bare_repo(tmp_path):
    """Create a bare git repo to act as a remote."""
    bare = tmp_path / "remote.git"
    bare.mkdir()
    subprocess.run(
        ["git", "init", "--bare", str(bare)],
        capture_output=True, check=True,
    )
    return bare


def test_init_repo(repo_mgr):
    """init_repo creates a local git repo."""
    backend = repo_mgr.init_repo("my-local")
    assert repo_mgr.repo_exists("my-local")
    assert (repo_mgr.repos_dir / "my-local" / ".git").exists()


def test_clone_repo(repo_mgr, bare_repo):
    """clone_repo clones from a URL."""
    backend = repo_mgr.clone_repo("cloned", str(bare_repo))
    assert repo_mgr.repo_exists("cloned")
    assert (repo_mgr.repos_dir / "cloned" / ".git").exists()


def test_clone_repo_duplicate_fails(repo_mgr, bare_repo):
    """clone_repo raises if repo name already exists."""
    repo_mgr.clone_repo("dup", str(bare_repo))
    with pytest.raises(ValueError, match="already exists"):
        repo_mgr.clone_repo("dup", str(bare_repo))


def test_get_backend(repo_mgr):
    """get_backend returns a LocalBackend for an existing repo."""
    repo_mgr.init_repo("test-repo")
    backend = repo_mgr.get_backend("test-repo")
    assert backend is not None


def test_get_backend_missing_raises(repo_mgr):
    """get_backend raises for non-existent repo."""
    with pytest.raises(ValueError, match="not found"):
        repo_mgr.get_backend("ghost")


def test_remove_repo(repo_mgr):
    """remove_repo deletes the repo directory."""
    repo_mgr.init_repo("disposable")
    assert repo_mgr.repo_exists("disposable")
    repo_mgr.remove_repo("disposable")
    assert not repo_mgr.repo_exists("disposable")


def test_list_repos_empty(repo_mgr):
    """list_repos returns empty list when no repos exist."""
    assert repo_mgr.list_repos() == []


def test_list_repos(repo_mgr):
    """list_repos returns all initialized repos."""
    repo_mgr.init_repo("alpha")
    repo_mgr.init_repo("beta")
    repos = repo_mgr.list_repos()
    names = [r.name for r in repos]
    assert "alpha" in names
    assert "beta" in names
    assert len(repos) == 2


def test_repo_exists(repo_mgr):
    """repo_exists returns True for existing repos, False otherwise."""
    assert not repo_mgr.repo_exists("nope")
    repo_mgr.init_repo("yes")
    assert repo_mgr.repo_exists("yes")


def test_get_all_backends(repo_mgr):
    """get_all_backends returns (name, backend) pairs for all repos."""
    repo_mgr.init_repo("one")
    repo_mgr.init_repo("two")
    all_backends = repo_mgr.get_all_backends()
    names = [name for name, _ in all_backends]
    assert "one" in names
    assert "two" in names
    assert len(all_backends) == 2


def test_list_repos_shows_origin_url(repo_mgr, bare_repo):
    """Cloned repos show their origin URL in list_repos."""
    repo_mgr.clone_repo("from-remote", str(bare_repo))
    repos = repo_mgr.list_repos()
    assert len(repos) == 1
    assert repos[0].name == "from-remote"
    assert str(bare_repo) in repos[0].url


def test_init_repo_no_origin_url(repo_mgr):
    """Local-only repos have empty origin URL."""
    repo_mgr.init_repo("local-only")
    repos = repo_mgr.list_repos()
    assert len(repos) == 1
    assert repos[0].url == ""
