"""Tests for library branch management (Phase 3: branch = library)."""

import subprocess
import pytest
from skillm.config import Config
from skillm.core import Library


def test_default_library_is_main(tmp_library):
    """First init creates a default branch, add works immediately."""
    assert tmp_library.current_library() in ("main", "master")


def test_create_library(tmp_library):
    """Create a new library (orphan branch)."""
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


def test_three_level_tags(tmp_library, sample_skill):
    """Publish creates three-level tags: library/skill/version."""
    name, ver = tmp_library.publish(sample_skill)
    lib = tmp_library.current_library()

    # Tag should be library/skill/version
    tag = f"{lib}/{name}/{ver}"
    assert tmp_library.backend.git.tag_exists(tag)


def test_publish_to_different_libraries(tmp_library, sample_skill):
    """Publish same skill to two libraries, both get separate tags."""
    lib1 = tmp_library.current_library()
    name1, ver1 = tmp_library.publish(sample_skill)

    tmp_library.create_library("other")
    name2, ver2 = tmp_library.publish(sample_skill)

    # Both tags should exist
    assert tmp_library.backend.git.tag_exists(f"{lib1}/{name1}/{ver1}")
    assert tmp_library.backend.git.tag_exists(f"other/{name2}/{ver2}")


def test_search_across_libraries(tmp_library, sample_skill):
    """Search finds skills from all libraries."""
    lib1 = tmp_library.current_library()
    tmp_library.publish(sample_skill)

    tmp_library.create_library("other")
    tmp_library.publish(sample_skill)

    # Rebuild indexes all libraries
    count = tmp_library.rebuild()
    assert count == 2  # one version in each library

    results = tmp_library.search("test")
    assert len(results) >= 2


def test_install_from_non_active_library(tmp_library, sample_skill, tmp_path):
    """Install a skill from a library that isn't currently active."""
    from skillm.core import Project

    lib1 = tmp_library.current_library()
    tmp_library.publish(sample_skill)

    # Switch to different library
    tmp_library.create_library("other")

    # Should still be able to get files from lib1's tag
    path = tmp_library.get_skill_files_path("my-skill", "v0.1", library=lib1)
    assert (path / "SKILL.md").exists()


def test_list_skill_dirs_by_library(tmp_library, sample_skill):
    """list_skill_dirs_by_library groups by library."""
    lib1 = tmp_library.current_library()
    tmp_library.publish(sample_skill)

    tmp_library.create_library("other")
    tmp_library.publish(sample_skill)

    by_lib = tmp_library.backend.list_skill_dirs_by_library()
    assert lib1 in by_lib
    assert "other" in by_lib
    assert len(by_lib[lib1]) == 1
    assert len(by_lib["other"]) == 1


def test_list_skill_dirs_filtered(tmp_library, sample_skill):
    """list_skill_dirs with library filter only returns that library's skills."""
    lib1 = tmp_library.current_library()
    tmp_library.publish(sample_skill)

    tmp_library.create_library("other")
    tmp_library.publish(sample_skill)

    skills_lib1 = tmp_library.backend.list_skill_dirs(library=lib1)
    assert len(skills_lib1) == 1

    skills_other = tmp_library.backend.list_skill_dirs(library="other")
    assert len(skills_other) == 1


def test_remove_skill_only_affects_current_library(tmp_library, sample_skill):
    """Removing a skill only removes tags from the current library."""
    lib1 = tmp_library.current_library()
    tmp_library.publish(sample_skill)

    tmp_library.create_library("other")
    tmp_library.publish(sample_skill)

    # Remove from "other"
    tmp_library.remove("my-skill")

    # other's tag should be gone
    assert not tmp_library.backend.git.tag_exists(f"other/my-skill/v0.1")
    # lib1's tag should still exist
    assert tmp_library.backend.git.tag_exists(f"{lib1}/my-skill/v0.1")


def test_push_pull_with_libraries(tmp_path, sample_skill):
    """Push/pull preserves library branch structure."""
    bare = tmp_path / "shared.git"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", str(bare)], capture_output=True, check=True)

    # Library A: publish to two libraries, push
    lib_a_path = tmp_path / "lib_a"
    config_a = Config()
    config_a.library.path = str(lib_a_path)
    lib_a = Library(config_a)
    lib_a.init()

    lib_a.publish(sample_skill)  # on default branch
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
    (sample_skill / "SKILL.md").write_text("# My Skill v2\n\nUpdated.\n")
    lib_a.publish(sample_skill)

    # We now have local commits ahead of origin
    branch = lib_a.current_library()

    # Reset should drop the unpushed commit
    lib_a.switch_library(branch, reset=True)

    # After reset, working tree should match what was pushed (v0.1 only)
    # The v0.2 tag still exists but the working tree is back to remote state
    skill_dir = lib_a.backend.skills_dir / "my-skill"
    content = (skill_dir / "SKILL.md").read_text()
    assert "v2" not in content


def test_auto_version_per_library(tmp_library, sample_skill):
    """Version numbering is independent per library."""
    tmp_library.publish(sample_skill)
    _, ver1 = tmp_library.publish(sample_skill)
    assert ver1 == "v0.2"

    tmp_library.create_library("other", orphan=True)
    _, ver2 = tmp_library.publish(sample_skill)
    assert ver2 == "v0.1"  # starts fresh in new library


