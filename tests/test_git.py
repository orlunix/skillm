"""Tests for git wrapper."""

import pytest
from pathlib import Path
from skillm.git import GitRepo, GitError


def test_init_and_is_repo(tmp_path):
    repo = GitRepo(tmp_path / "repo")
    assert not repo.is_repo()
    repo.init()
    assert repo.is_repo()


def test_add_commit(tmp_path):
    repo = GitRepo(tmp_path / "repo")
    repo.init()

    (tmp_path / "repo" / "file.txt").write_text("hello")
    repo.add("file.txt")
    commit = repo.commit("initial commit")
    assert len(commit) == 40  # SHA hash


def test_tag_operations(tmp_path):
    repo = GitRepo(tmp_path / "repo")
    repo.init()
    (tmp_path / "repo" / "file.txt").write_text("hello")
    repo.add("file.txt")
    repo.commit("initial")

    repo.tag("v1.0", "release 1.0")
    assert repo.tag_exists("v1.0")
    assert "v1.0" in repo.list_tags()

    commit = repo.tag_commit("v1.0")
    assert len(commit) == 40

    repo.delete_tag("v1.0")
    assert not repo.tag_exists("v1.0")


def test_skill_versions(tmp_path):
    repo = GitRepo(tmp_path / "repo")
    repo.init()
    (tmp_path / "repo" / "file.txt").write_text("hello")
    repo.add("file.txt")
    repo.commit("initial")

    repo.tag("my-skill/v0.1")
    repo.tag("my-skill/v0.2")
    repo.tag("my-skill/v1.0")
    repo.tag("other/v1.0")

    versions = repo.skill_versions("my-skill")
    assert len(versions) == 3
    assert versions[0] == ("my-skill/v0.1", 0, 1)
    assert versions[1] == ("my-skill/v0.2", 0, 2)
    assert versions[2] == ("my-skill/v1.0", 1, 0)


def test_next_version(tmp_path):
    repo = GitRepo(tmp_path / "repo")
    repo.init()
    (tmp_path / "repo" / "file.txt").write_text("hello")
    repo.add("file.txt")
    repo.commit("initial")

    # No tags yet
    assert repo.next_version("my-skill") == "v0.1"
    assert repo.next_version("my-skill", major=True) == "v1.0"

    repo.tag("my-skill/v0.1")
    assert repo.next_version("my-skill") == "v0.2"

    repo.tag("my-skill/v0.2")
    assert repo.next_version("my-skill", major=True) == "v1.0"


def test_has_changes(tmp_path):
    repo = GitRepo(tmp_path / "repo")
    repo.init()
    (tmp_path / "repo" / "file.txt").write_text("hello")
    repo.add("file.txt")
    repo.commit("initial")

    assert not repo.has_changes()

    (tmp_path / "repo" / "file.txt").write_text("changed")
    assert repo.has_changes()
    assert repo.has_changes("file.txt")


def test_log(tmp_path):
    repo = GitRepo(tmp_path / "repo")
    repo.init()
    (tmp_path / "repo" / "file.txt").write_text("hello")
    repo.add("file.txt")
    repo.commit("first commit")

    output = repo.log()
    assert "first commit" in output


def test_list_skill_dirs(tmp_path):
    repo = GitRepo(tmp_path / "repo")
    repo.init()

    # Create skill directories
    (tmp_path / "repo" / "skill-a").mkdir()
    (tmp_path / "repo" / "skill-a" / "SKILL.md").write_text("# A")
    (tmp_path / "repo" / "skill-b").mkdir()
    (tmp_path / "repo" / "skill-b" / "SKILL.md").write_text("# B")
    (tmp_path / "repo" / "not-a-skill").mkdir()
    (tmp_path / "repo" / "not-a-skill" / "README.md").write_text("# Not")

    dirs = repo.list_skill_dirs()
    assert "skill-a" in dirs
    assert "skill-b" in dirs
    assert "not-a-skill" not in dirs


def test_extract_to(tmp_path):
    repo = GitRepo(tmp_path / "repo")
    repo.init()

    # Create a skill with files
    (tmp_path / "repo" / "my-skill").mkdir()
    (tmp_path / "repo" / "my-skill" / "SKILL.md").write_text("# My Skill")
    (tmp_path / "repo" / "my-skill" / "helper.py").write_text("print('hi')")
    repo.add("my-skill")
    repo.commit("add skill")
    repo.tag("my-skill/v1.0")

    # Extract at tag
    dest = tmp_path / "extracted"
    repo.extract_to("my-skill/v1.0", "my-skill/", dest)
    assert (dest / "SKILL.md").exists()
    assert (dest / "helper.py").exists()
    assert (dest / "SKILL.md").read_text() == "# My Skill"
