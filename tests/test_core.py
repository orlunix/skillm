"""Tests for core source manager and project operations."""

from pathlib import Path


def test_source_init(tmp_source_repo):
    stats = tmp_source_repo.stats()
    assert stats["skills"] == 0
    assert stats["sources"] == 1


def test_add_skill(tmp_source_repo, sample_skill):
    name, src = tmp_source_repo.add_skill(sample_skill)
    assert name == "my-skill"
    assert src == "test"

    skill = tmp_source_repo.info("my-skill")
    assert skill is not None
    assert skill.description == "A test skill for unit tests."
    assert "test" in skill.tags
    assert skill.author == "tester"
    assert skill.source == "test"


def test_add_and_publish(tmp_source_repo, sample_skill):
    tmp_source_repo.add_skill(sample_skill)
    name, ver = tmp_source_repo.publish("my-skill")
    assert name == "my-skill"
    assert ver == "v0.1"

    skill = tmp_source_repo.info("my-skill")
    assert skill is not None
    assert len(skill.versions) == 1
    assert skill.versions[0].version == "v0.1"


def test_publish_auto_increment(tmp_source_repo, sample_skill):
    tmp_source_repo.add_skill(sample_skill)
    _, v1 = tmp_source_repo.publish("my-skill")
    assert v1 == "v0.1"

    # Modify and re-add
    (sample_skill / "SKILL.md").write_text(
        "# My Skill\n\nUpdated.\n\n"
        "<!-- skillm:meta\ntags: test, sample\nauthor: tester\n-->\n"
    )
    tmp_source_repo.add_skill(sample_skill)
    _, v2 = tmp_source_repo.publish("my-skill")
    assert v2 == "v0.2"


def test_publish_major_bump(tmp_source_repo, sample_skill):
    tmp_source_repo.add_skill(sample_skill)
    _, v1 = tmp_source_repo.publish("my-skill")
    assert v1 == "v0.1"
    _, v2 = tmp_source_repo.publish("my-skill")
    assert v2 == "v0.2"
    _, v3 = tmp_source_repo.publish("my-skill", major=True)
    assert v3 == "v1.0"


def test_remove_skill(tmp_source_repo, sample_skill):
    tmp_source_repo.add_skill(sample_skill)
    assert tmp_source_repo.remove_skill("my-skill")
    assert tmp_source_repo.info("my-skill") is None


def test_remove_version(tmp_source_repo, sample_skill):
    tmp_source_repo.add_skill(sample_skill)
    tmp_source_repo.publish("my-skill")
    tmp_source_repo.publish("my-skill")

    tmp_source_repo.remove_skill("my-skill", version="v0.1")
    skill = tmp_source_repo.info("my-skill")
    assert skill is not None
    assert len(skill.versions) == 1
    assert skill.versions[0].version == "v0.2"


def test_search(tmp_source_repo, sample_skill):
    tmp_source_repo.add_skill(sample_skill)
    results = tmp_source_repo.search("test")
    assert len(results) >= 1
    assert results[0].name == "my-skill"


def test_list_skills(tmp_source_repo, sample_skill):
    tmp_source_repo.add_skill(sample_skill)
    skills = tmp_source_repo.list_skills()
    assert len(skills) == 1


def test_tags(tmp_source_repo, sample_skill):
    tmp_source_repo.add_skill(sample_skill)
    tmp_source_repo.tag("my-skill", ["new-tag"])
    skill = tmp_source_repo.info("my-skill")
    assert "new-tag" in skill.tags

    tmp_source_repo.untag("my-skill", ["new-tag"])
    skill = tmp_source_repo.info("my-skill")
    assert "new-tag" not in skill.tags


def test_rebuild_cache(tmp_source_repo, sample_skill):
    tmp_source_repo.add_skill(sample_skill)
    tmp_source_repo.publish("my-skill")

    count = tmp_source_repo.rebuild_cache()
    assert count == 1
    assert tmp_source_repo.info("my-skill") is not None


def test_log(tmp_source_repo, sample_skill):
    tmp_source_repo.add_skill(sample_skill)
    output = tmp_source_repo.log("my-skill")
    assert "my-skill" in output


def test_diff_no_changes(tmp_source_repo, sample_skill):
    tmp_source_repo.add_skill(sample_skill)
    output = tmp_source_repo.diff("my-skill")
    assert output == ""  # No uncommitted changes


# ── Project tests ─────────────────────────────────────────

def test_project_add_drop(tmp_project, sample_skill):
    sm = tmp_project.source_manager
    sm.add_skill(sample_skill)
    sm.publish("my-skill")

    ver = tmp_project.add("my-skill")
    assert ver == "v0.1"
    assert (tmp_project.skills_dir / "my-skill" / "SKILL.md").exists()

    manifest = tmp_project.list_skills()
    assert "my-skill" in manifest

    assert tmp_project.drop("my-skill")
    assert not (tmp_project.skills_dir / "my-skill").exists()


def test_project_sync(tmp_project, sample_skill):
    sm = tmp_project.source_manager
    sm.add_skill(sample_skill)
    sm.publish("my-skill")
    tmp_project.add("my-skill")

    # Simulate missing files
    import shutil
    shutil.rmtree(tmp_project.skills_dir / "my-skill")

    synced = tmp_project.sync()
    assert "my-skill" in synced
    assert (tmp_project.skills_dir / "my-skill" / "SKILL.md").exists()


def test_project_upgrade(tmp_project, sample_skill):
    sm = tmp_project.source_manager
    sm.add_skill(sample_skill)
    sm.publish("my-skill")
    tmp_project.add("my-skill")

    # Modify and publish v2
    (sample_skill / "SKILL.md").write_text(
        "# My Skill\n\nUpdated v2.\n\n"
        "<!-- skillm:meta\ntags: test\nauthor: tester\n-->\n"
    )
    sm.add_skill(sample_skill)
    sm.publish("my-skill")

    upgraded = tmp_project.upgrade()
    assert len(upgraded) == 1
    assert upgraded[0] == ("my-skill", "v0.1", "v0.2")


def test_project_enable_disable(tmp_project, sample_skill):
    sm = tmp_project.source_manager
    sm.add_skill(sample_skill)
    sm.publish("my-skill")
    tmp_project.add("my-skill")

    assert tmp_project.disable("my-skill")
    manifest = tmp_project.list_skills()
    assert manifest["my-skill"]["enabled"] is False

    assert tmp_project.enable("my-skill")
    manifest = tmp_project.list_skills()
    assert manifest["my-skill"]["enabled"] is True


def test_project_lock_file(tmp_project, sample_skill):
    sm = tmp_project.source_manager
    sm.add_skill(sample_skill)
    sm.publish("my-skill")
    tmp_project.add("my-skill")

    # Lock file should exist
    assert tmp_project.lock_file_path.exists()

    # Verify integrity
    results = tmp_project.verify()
    assert len(results) == 1
    assert results[0] == ("my-skill", True)


def test_project_install_head(tmp_project, sample_skill):
    """Install from HEAD (no published version)."""
    sm = tmp_project.source_manager
    sm.add_skill(sample_skill)
    # Don't publish — install from HEAD
    ver = tmp_project.add("my-skill")
    assert ver == "HEAD"
    assert (tmp_project.skills_dir / "my-skill" / "SKILL.md").exists()
