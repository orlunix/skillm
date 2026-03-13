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
    assert ver == "v0.1"
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
    assert upgraded[0] == ("my-skill", "v0.1", "v0.2")


def test_push(tmp_path, sample_skill):
    """Push skills from local library to remote library."""
    from skillm.config import Config
    from skillm.core import Library

    # Create local library with a skill
    local_path = tmp_path / "local"
    local_config = Config()
    local_config.library.path = str(local_path)
    local_lib = Library(local_config)
    local_lib.init()
    local_lib.publish(sample_skill)
    local_lib.publish(sample_skill)  # v0.2

    # Create remote library (empty)
    remote_path = tmp_path / "remote"
    remote_config = Config()
    remote_config.library.path = str(remote_path)
    remote_lib = Library(remote_config)
    remote_lib.init()

    # Push
    results = local_lib.push(remote_lib)
    assert len(results) == 1
    name, local_ver, remote_ver = results[0]
    assert name == "my-skill"
    assert local_ver == "v0.2"  # latest local
    assert remote_ver == "v0.1"  # first version on remote

    # Remote now has the skill
    remote_skill = remote_lib.info("my-skill")
    assert remote_skill is not None
    assert len(remote_skill.versions) == 1


def test_pull(tmp_path, sample_skill):
    """Pull skills from remote library to local library."""
    from skillm.config import Config
    from skillm.core import Library

    # Create remote library with skills
    remote_path = tmp_path / "remote"
    remote_config = Config()
    remote_config.library.path = str(remote_path)
    remote_lib = Library(remote_config)
    remote_lib.init()
    remote_lib.publish(sample_skill)

    # Create local library (empty)
    local_path = tmp_path / "local"
    local_config = Config()
    local_config.library.path = str(local_path)
    local_lib = Library(local_config)
    local_lib.init()

    # Pull
    results = local_lib.pull(remote_lib)
    assert len(results) == 1
    name, source_ver, local_ver = results[0]
    assert name == "my-skill"
    assert source_ver == "v0.1"
    assert local_ver == "v0.1"

    # Local now has the skill
    local_skill = local_lib.info("my-skill")
    assert local_skill is not None


def test_push_increments_remote_version(tmp_path, sample_skill):
    """Pushing twice increments version on remote."""
    from skillm.config import Config
    from skillm.core import Library

    local_path = tmp_path / "local"
    local_config = Config()
    local_config.library.path = str(local_path)
    local_lib = Library(local_config)
    local_lib.init()
    local_lib.publish(sample_skill)

    remote_path = tmp_path / "remote"
    remote_config = Config()
    remote_config.library.path = str(remote_path)
    remote_lib = Library(remote_config)
    remote_lib.init()

    # Push twice
    results1 = local_lib.push(remote_lib)
    assert results1[0][2] == "v0.1"

    results2 = local_lib.push(remote_lib)
    assert results2[0][2] == "v0.2"

    remote_skill = remote_lib.info("my-skill")
    assert len(remote_skill.versions) == 2


def test_project_enable_disable(tmp_project, sample_skill):
    tmp_project.library.publish(sample_skill)
    tmp_project.add("my-skill")

    assert tmp_project.disable("my-skill")
    manifest = tmp_project.list_skills()
    assert manifest["my-skill"]["enabled"] is False

    assert tmp_project.enable("my-skill")
    manifest = tmp_project.list_skills()
    assert manifest["my-skill"]["enabled"] is True
