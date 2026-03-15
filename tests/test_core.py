"""Tests for core library and project operations."""

from pathlib import Path


def test_library_init(tmp_library):
    stats = tmp_library.stats()
    assert stats["skills"] == 0
    assert stats["backend"] == "local"


def test_publish_and_info(tmp_library, sample_skill):
    name, ver = tmp_library.publish(sample_skill)
    assert name == "my-skill"
    assert ver == "v0.1"

    skill = tmp_library.info("my-skill")
    assert skill is not None
    assert skill.description == "A test skill for unit tests."
    assert "test" in skill.tags
    assert skill.author == "tester"
    assert len(skill.versions) == 1


def test_publish_auto_increment(tmp_library, sample_skill):
    tmp_library.publish(sample_skill)
    _, ver2 = tmp_library.publish(sample_skill)
    assert ver2 == "v0.2"

    skill = tmp_library.info("my-skill")
    assert len(skill.versions) == 2


def test_publish_explicit_version(tmp_library, sample_skill):
    name, ver = tmp_library.publish(sample_skill, version="1.0.0")
    assert ver == "1.0.0"


def test_remove_skill(tmp_library, sample_skill):
    tmp_library.publish(sample_skill)
    assert tmp_library.remove("my-skill")
    assert tmp_library.info("my-skill") is None


def test_remove_version(tmp_library, sample_skill):
    tmp_library.publish(sample_skill)
    tmp_library.publish(sample_skill)

    assert tmp_library.remove("my-skill", version="v0.1")
    skill = tmp_library.info("my-skill")
    assert skill is not None
    assert len(skill.versions) == 1


def test_override(tmp_library, sample_skill, tmp_path):
    tmp_library.publish(sample_skill)
    skill = tmp_library.info("my-skill")
    assert len(skill.versions) == 1
    assert skill.versions[0].version == "v0.1"

    # Modify the skill content
    (sample_skill / "SKILL.md").write_text(
        "# My Skill\n\nUpdated description.\n\n"
        "<!-- skillm:meta\ntags: test, updated\nauthor: tester\n-->\n"
    )
    (sample_skill / "extra.txt").write_text("new file\n")

    name, ver = tmp_library.override(sample_skill)
    assert name == "my-skill"
    assert ver == "v0.1"  # same version string

    skill = tmp_library.info("my-skill")
    assert len(skill.versions) == 1  # still one version
    assert skill.description == "Updated description."


def test_override_nonexistent(tmp_library, sample_skill):
    import pytest
    with pytest.raises(ValueError, match="not found"):
        tmp_library.override(sample_skill)


def test_publish_major_bump(tmp_library, sample_skill):
    _, v1 = tmp_library.publish(sample_skill)
    assert v1 == "v0.1"
    _, v2 = tmp_library.publish(sample_skill)
    assert v2 == "v0.2"
    _, v3 = tmp_library.publish(sample_skill, major=True)
    assert v3 == "v1.0"
    _, v4 = tmp_library.publish(sample_skill)
    assert v4 == "v1.1"
    _, v5 = tmp_library.publish(sample_skill, major=True)
    assert v5 == "v2.0"


def test_search(tmp_library, sample_skill):
    tmp_library.publish(sample_skill)
    results = tmp_library.search("test")
    assert len(results) >= 1
    assert results[0].name.endswith("my-skill")


def test_list_skills(tmp_library, sample_skill):
    tmp_library.publish(sample_skill)
    skills = tmp_library.list_skills()
    assert len(skills) == 1


def test_tags(tmp_library, sample_skill):
    tmp_library.publish(sample_skill)
    tmp_library.tag("my-skill", ["new-tag"])
    skill = tmp_library.info("my-skill")
    assert "new-tag" in skill.tags

    tmp_library.untag("my-skill", ["new-tag"])
    skill = tmp_library.info("my-skill")
    assert "new-tag" not in skill.tags


def test_tag_updates_frontmatter(tmp_library, sample_skill):
    """tag/untag should update SKILL.md frontmatter, not just DB."""
    tmp_library.publish(sample_skill)
    tmp_library.tag("my-skill", ["new-tag"])

    # Read SKILL.md directly to verify frontmatter was updated
    skill_md = tmp_library.backend.skills_dir / "my-skill" / "SKILL.md"
    from skillm.metadata import extract_metadata
    meta = extract_metadata(skill_md.parent)
    assert "new-tag" in meta.tags

    tmp_library.untag("my-skill", ["new-tag"])
    meta = extract_metadata(skill_md.parent)
    assert "new-tag" not in meta.tags


def test_categorize_updates_frontmatter(tmp_library, sample_skill):
    """categorize should update SKILL.md frontmatter."""
    tmp_library.publish(sample_skill)
    tmp_library.categorize("my-skill", "devops")

    skill_md = tmp_library.backend.skills_dir / "my-skill" / "SKILL.md"
    from skillm.metadata import extract_metadata
    meta = extract_metadata(skill_md.parent)
    assert meta.category == "devops"

    # DB should also be updated
    skill = tmp_library.info("my-skill")
    assert skill.category == "devops"


def test_find_skills_by_tag(tmp_library, sample_skill, tmp_path):
    """find_skills_by_tag scans working tree SKILL.md files."""
    tmp_library.publish(sample_skill)

    # sample_skill has tags: test, sample
    matches = tmp_library.find_skills_by_tag("test")
    assert len(matches) == 1
    assert matches[0][0] == "my-skill"

    matches = tmp_library.find_skills_by_tag("nonexistent")
    assert len(matches) == 0


def test_find_skills_by_category(tmp_library, sample_skill):
    """find_skills_by_category scans working tree SKILL.md files."""
    tmp_library.publish(sample_skill)
    tmp_library.categorize("my-skill", "infra")

    matches = tmp_library.find_skills_by_category("infra")
    assert len(matches) == 1
    assert matches[0][0] == "my-skill"

    matches = tmp_library.find_skills_by_category("other")
    assert len(matches) == 0


def test_rebuild(tmp_library, sample_skill):
    tmp_library.publish(sample_skill)
    count = tmp_library.rebuild()
    assert count == 1
    assert tmp_library.info("my-skill") is not None


def test_project_add_drop(tmp_project, sample_skill):
    tmp_project.library.publish(sample_skill)

    ver = tmp_project.add("my-skill")
    assert ver == "v0.1"
    assert (tmp_project.skills_dir / "my-skill" / "SKILL.md").exists()

    manifest = tmp_project.list_skills()
    assert "my-skill" in manifest

    assert tmp_project.drop("my-skill")
    assert not (tmp_project.skills_dir / "my-skill").exists()


def test_project_soft_install(tmp_project, sample_skill):
    """Soft install creates a symlink to the library working tree."""
    tmp_project.library.publish(sample_skill)

    ver = tmp_project.add("my-skill", soft=True)
    assert ver == "latest"

    dest = tmp_project.skills_dir / "my-skill"
    assert dest.is_symlink()
    assert (dest / "SKILL.md").exists()

    # Manifest should record soft=True
    manifest = tmp_project.list_skills()
    assert manifest["my-skill"]["soft"] is True

    # Drop should remove the symlink
    assert tmp_project.drop("my-skill")
    assert not dest.exists()
    assert not dest.is_symlink()


def test_project_soft_install_reflects_changes(tmp_project, sample_skill):
    """Soft-installed skill reflects changes in the library immediately."""
    tmp_project.library.publish(sample_skill)
    tmp_project.add("my-skill", soft=True)

    # Modify the skill in the library working tree
    skill_md = tmp_project.library.backend.skills_dir / "my-skill" / "SKILL.md"
    skill_md.write_text("# Updated\n\nNew content.\n")

    # Project should see the change immediately (symlink)
    project_md = tmp_project.skills_dir / "my-skill" / "SKILL.md"
    assert "Updated" in project_md.read_text()


def test_project_sync(tmp_project, sample_skill):
    tmp_project.library.publish(sample_skill)
    tmp_project.add("my-skill")

    # Simulate missing files
    import shutil
    shutil.rmtree(tmp_project.skills_dir / "my-skill")

    synced = tmp_project.sync()
    assert "my-skill" in synced
    assert (tmp_project.skills_dir / "my-skill" / "SKILL.md").exists()


def test_project_upgrade(tmp_project, sample_skill):
    tmp_project.library.publish(sample_skill)
    tmp_project.add("my-skill")

    # Publish v2
    tmp_project.library.publish(sample_skill)

    upgraded = tmp_project.upgrade()
    assert len(upgraded) == 1
    assert upgraded[0] == ("my-skill", "v0.1", "v0.2")


def test_push_pull_via_git(tmp_path, sample_skill):
    """Push and pull skills via a shared bare git repo."""
    import subprocess
    from skillm.config import Config
    from skillm.core import Library

    # Create a bare repo (simulates GitHub/GitLab)
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
    lib_a.publish(sample_skill)  # v0.2
    lib_a.backend.git.add_remote("origin", str(bare))
    lib_a.push()

    # Library B: pull from bare
    lib_b_path = tmp_path / "lib_b"
    config_b = Config()
    config_b.library.path = str(lib_b_path)
    lib_b = Library(config_b)
    lib_b.init()
    lib_b.backend.git.add_remote("origin", str(bare))
    count = lib_b.pull()

    # Both versions should be available (rebuild returns version count)
    assert count == 2
    skill = lib_b.info("my-skill")
    assert skill is not None
    assert len(skill.versions) == 2


def test_project_enable_disable(tmp_project, sample_skill):
    tmp_project.library.publish(sample_skill)
    tmp_project.add("my-skill")

    assert tmp_project.disable("my-skill")
    manifest = tmp_project.list_skills()
    assert manifest["my-skill"]["enabled"] is False

    assert tmp_project.enable("my-skill")
    manifest = tmp_project.list_skills()
    assert manifest["my-skill"]["enabled"] is True
