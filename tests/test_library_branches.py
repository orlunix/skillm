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
    lib_a.add_remote("shared", str(bare))
    lib_a.push("shared")

    # Library B: pull
    lib_b_path = tmp_path / "lib_b"
    config_b = Config()
    config_b.library.path = str(lib_b_path)
    lib_b = Library(config_b)
    lib_b.init()
    lib_b.add_remote("shared", str(bare))
    count = lib_b.pull("shared")

    assert count >= 1
    skill = lib_b.info("my-skill")
    assert skill is not None


def test_library_create_is_empty(tmp_library, sample_skill):
    """A newly created library has no skills."""
    tmp_library.publish(sample_skill)
    tmp_library.create_library("empty")

    # Working tree should be empty (no skill dirs)
    dirs = tmp_library.backend.git.list_skill_dirs()
    assert len(dirs) == 0


def test_auto_version_per_library(tmp_library, sample_skill):
    """Version numbering is independent per library."""
    tmp_library.publish(sample_skill)
    _, ver1 = tmp_library.publish(sample_skill)
    assert ver1 == "v0.2"

    tmp_library.create_library("other")
    _, ver2 = tmp_library.publish(sample_skill)
    assert ver2 == "v0.1"  # starts fresh in new library


def test_set_unset_library_remote(tmp_path, tmp_library):
    """Set and unset upstream tracking for a library."""
    bare = tmp_path / "bare.git"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", str(bare)], capture_output=True, check=True)

    tmp_library.add_remote("origin", str(bare))
    tmp_library.push("origin")

    tmp_library.set_library_remote("origin")
    upstream = tmp_library.get_library_upstream()
    assert upstream is not None
    assert "origin" in upstream

    tmp_library.unset_library_remote()
    assert tmp_library.get_library_upstream() is None
