"""Tests for library branch management."""

import subprocess
import pytest
from skillm.config import Config
from skillm.core import Library


def test_default_library_is_main(tmp_library):
    """First init creates a default branch, add works immediately."""
    assert tmp_library.current_library() in ("main", "master")


def test_create_library(tmp_library):
    """Create a new library (branch)."""
    tmp_library.create_library("infra")
    assert tmp_library.current_library() == "infra"

    libs = tmp_library.list_libraries()
    assert "infra" in libs


def test_switch_library(tmp_library):
    """Switch between libraries."""
    original = tmp_library.current_library()
    tmp_library.create_library("ai")
    assert tmp_library.current_library() == "ai"

    tmp_library.switch_library(original)
    assert tmp_library.current_library() == original


def test_delete_library(tmp_library):
    """Delete a non-active library."""
    original = tmp_library.current_library()
    tmp_library.create_library("temp")
    tmp_library.switch_library(original)

    tmp_library.delete_library("temp")
    assert "temp" not in tmp_library.list_libraries()


def test_delete_active_library_fails(tmp_library):
    """Cannot delete the active library."""
    with pytest.raises(ValueError, match="Cannot delete active"):
        tmp_library.delete_library(tmp_library.current_library())


def test_publish_uses_commit_not_tags(tmp_library, sample_skill):
    """Publish stores commit hash, not version tags."""
    name = tmp_library.publish(sample_skill)
    skill = tmp_library.info(name)
    assert skill is not None
    assert skill.commit  # has a commit hash
    assert len(skill.commit) >= 7


def test_publish_to_different_branches(tmp_library, sample_skill):
    """Publishing same skill to two branches creates separate DB entries."""
    lib1 = tmp_library.current_library()
    tmp_library.publish(sample_skill)

    tmp_library.create_library("other")
    tmp_library.publish(sample_skill)

    # Rebuild sees only current branch's working tree
    # But both should be accessible via their qualified names
    tmp_library.rebuild()
    skill = tmp_library.info("my-skill")
    assert skill is not None


def test_push_pull_with_libraries(tmp_path, sample_skill):
    """Push/pull preserves library branch structure."""
    bare = tmp_path / "shared.git"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", str(bare)], capture_output=True, check=True)

    # Library A: publish and push
    lib_a_path = tmp_path / "lib_a"
    config_a = Config()
    config_a.library.path = str(lib_a_path)
    lib_a = Library(config_a)
    lib_a.init()

    lib_a.publish(sample_skill)
    lib_a.backend.git.add_remote("origin", str(bare))
    lib_a.push()

    # Library B: pull
    lib_b_path = tmp_path / "lib_b"
    config_b = Config()
    config_b.library.path = str(lib_b_path)
    lib_b = Library(config_b)
    lib_b.init()
    lib_b.backend.git.add_remote("origin", str(bare))
    count = lib_b.pull()

    assert count >= 1
    skill = lib_b.info("my-skill")
    assert skill is not None


def test_library_create_forks_by_default(tmp_library, sample_skill):
    """A forked library inherits skills from the current branch."""
    tmp_library.publish(sample_skill)
    tmp_library.create_library("forked")

    # Working tree should have the skill from parent branch
    dirs = tmp_library.backend.git.list_skill_dirs()
    assert len(dirs) == 1
    assert "my-skill" in dirs


def test_library_create_empty_orphan(tmp_library, sample_skill):
    """An orphan library starts empty."""
    tmp_library.publish(sample_skill)
    tmp_library.create_library("empty", orphan=True)

    # Working tree should be empty (no skill dirs)
    dirs = tmp_library.backend.git.list_skill_dirs()
    assert len(dirs) == 0


def test_switch_reset_to_initial(tmp_library, sample_skill):
    """--reset drops local commits and resets to initial state."""
    lib1 = tmp_library.current_library()

    # Publish a skill (creates commits beyond init)
    tmp_library.publish(sample_skill)

    # The skill dir should exist in working tree
    skill_dir = tmp_library.backend.skills_dir / "my-skill"
    assert skill_dir.exists()

    # Reset: should go back to initial commit (only .gitignore)
    tmp_library.switch_library(lib1, reset=True)
    assert not skill_dir.exists()


def test_switch_reset_to_remote(tmp_path, sample_skill):
    """--reset aligns branch with remote tracking ref."""
    import subprocess

    # Create a bare remote
    bare = tmp_path / "remote.git"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", str(bare)], capture_output=True, check=True)

    # Create library A, publish, push
    lib_a_path = tmp_path / "lib_a"
    config_a = Config()
    config_a.library.path = str(lib_a_path)
    lib_a = Library(config_a)
    lib_a.init()
    lib_a.publish(sample_skill)
    lib_a.backend.git.add_remote("origin", str(bare))
    lib_a.push()

    # Now publish more locally (not pushed)
    (sample_skill / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: Updated v2.\ntags: []\n---\n\n# My Skill v2\n\nUpdated.\n"
    )
    lib_a.publish(sample_skill)

    # We now have local commits ahead of origin
    branch = lib_a.current_library()

    # Reset should drop the unpushed commit
    lib_a.switch_library(branch, reset=True)

    # After reset, working tree should match what was pushed
    skill_dir = lib_a.backend.skills_dir / "my-skill"
    content = (skill_dir / "SKILL.md").read_text()
    assert "v2" not in content
