"""Tests for core library and project operations."""

from pathlib import Path


def test_library_init(tmp_library):
    stats = tmp_library.stats()
    assert stats["skills"] == 0
    assert stats["backend"] == "local"


def test_publish_and_info(tmp_library, sample_skill):
    name, ver = tmp_library.publish(sample_skill)
    assert name == "my-skill"
    assert ver == "v1"

    skill = tmp_library.info("my-skill")
    assert skill is not None
    assert skill.description == "A test skill for unit tests."
    assert "test" in skill.tags
    assert skill.author == "tester"
    assert len(skill.versions) == 1


def test_publish_auto_increment(tmp_library, sample_skill):
    tmp_library.publish(sample_skill)
    _, ver2 = tmp_library.publish(sample_skill)
    assert ver2 == "v2"

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

    assert tmp_library.remove("my-skill", version="v1")
    skill = tmp_library.info("my-skill")
    assert skill is not None
    assert len(skill.versions) == 1


def test_override(tmp_library, sample_skill, tmp_path):
    tmp_library.publish(sample_skill)
    skill = tmp_library.info("my-skill")
    assert len(skill.versions) == 1
    assert skill.versions[0].version == "v1"

    # Modify the skill content
    (sample_skill / "SKILL.md").write_text(
        "# My Skill\n\nUpdated description.\n\n"
        "<!-- skillm:meta\ntags: test, updated\nauthor: tester\n-->\n"
    )
    (sample_skill / "extra.txt").write_text("new file\n")

    name, ver = tmp_library.override(sample_skill)
    assert name == "my-skill"
    assert ver == "v1"  # same version string

    skill = tmp_library.info("my-skill")
    assert len(skill.versions) == 1  # still one version
    assert skill.description == "Updated description."


def test_override_nonexistent(tmp_library, sample_skill):
    import pytest
    with pytest.raises(ValueError, match="not found"):
        tmp_library.override(sample_skill)


def test_search(tmp_library, sample_skill):
    tmp_library.publish(sample_skill)
    results = tmp_library.search("test")
    assert len(results) >= 1
    assert results[0].name == "my-skill"


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


def test_rebuild(tmp_library, sample_skill):
    tmp_library.publish(sample_skill)
    count = tmp_library.rebuild()
    assert count == 1
    assert tmp_library.info("my-skill") is not None


def test_project_add_drop(tmp_project, sample_skill):
    tmp_project.library.publish(sample_skill)

    ver = tmp_project.add("my-skill")
    assert ver == "v1"
    assert (tmp_project.skills_dir / "my-skill" / "SKILL.md").exists()

    manifest = tmp_project.list_skills()
    assert "my-skill" in manifest

    assert tmp_project.drop("my-skill")
    assert not (tmp_project.skills_dir / "my-skill").exists()


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
    assert upgraded[0] == ("my-skill", "v1", "v2")


def test_project_enable_disable(tmp_project, sample_skill):
    tmp_project.library.publish(sample_skill)
    tmp_project.add("my-skill")

    assert tmp_project.disable("my-skill")
    manifest = tmp_project.list_skills()
    assert manifest["my-skill"]["enabled"] is False

    assert tmp_project.enable("my-skill")
    manifest = tmp_project.list_skills()
    assert manifest["my-skill"]["enabled"] is True
