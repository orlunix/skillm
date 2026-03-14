"""Tests for cache database operations."""

from pathlib import Path
from skillm.db import Database
from skillm.models import Skill, Version


def test_initialize(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    assert db.skill_count() == 0
    db.close()


def test_source_crud(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()

    db.upsert_source("infra", "/path/to/infra", 10)
    db.upsert_source("ai", "ssh://git@server:/opt/ai", 20)

    # Update priority
    db.upsert_source("infra", "/path/to/infra", 5)
    db.close()


def test_skill_crud(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    db.upsert_source("test", "/tmp/test", 10)

    # Insert
    skill_id = db.insert_skill(Skill(
        name="test-skill", source="test", description="A test",
        author="me", updated_at="2026-01-01",
    ))
    assert skill_id > 0

    # Get
    skill = db.get_skill("test-skill")
    assert skill is not None
    assert skill.name == "test-skill"
    assert skill.source == "test"

    # Get with source filter
    skill = db.get_skill("test-skill", source="test")
    assert skill is not None

    skill_none = db.get_skill("test-skill", source="nonexistent")
    assert skill_none is None

    # Update
    skill = db.get_skill("test-skill")
    skill.description = "Updated"
    skill.updated_at = "2026-01-02"
    db.update_skill(skill)
    skill = db.get_skill("test-skill")
    assert skill.description == "Updated"

    # List
    skills = db.list_skills()
    assert len(skills) == 1

    skills = db.list_skills(source="test")
    assert len(skills) == 1

    # Delete
    assert db.delete_skill("test-skill")
    assert db.get_skill("test-skill") is None
    db.close()


def test_versions(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    db.upsert_source("test", "/tmp/test", 10)

    skill_id = db.insert_skill(Skill(
        name="s", source="test", updated_at="2026-01-01",
    ))

    db.insert_version(Version(
        skill_id=skill_id, version="v0.1",
        git_tag="s/v0.1", published_at="2026-01-01",
    ))
    db.insert_version(Version(
        skill_id=skill_id, version="v0.2",
        git_tag="s/v0.2", published_at="2026-01-02",
    ))

    versions = db.get_versions(skill_id)
    assert len(versions) == 2

    latest = db.get_latest_version(skill_id)
    assert latest.version == "v0.2"

    assert db.delete_version(skill_id, "v0.1")
    assert len(db.get_versions(skill_id)) == 1
    db.close()


def test_tags(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    db.upsert_source("test", "/tmp/test", 10)

    skill_id = db.insert_skill(Skill(
        name="s", source="test", updated_at="2026-01-01",
    ))

    db.set_tags(skill_id, ["web", "scraping"])
    assert db.get_tags(skill_id) == ["scraping", "web"]

    db.add_tags(skill_id, ["python"])
    assert "python" in db.get_tags(skill_id)

    db.remove_tags(skill_id, ["web"])
    tags = db.get_tags(skill_id)
    assert "web" not in tags
    assert "scraping" in tags
    db.close()


def test_search(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    db.upsert_source("test", "/tmp/test", 10)

    skill_id = db.insert_skill(Skill(
        name="web-scraper", source="test", description="Scrape websites",
        updated_at="2026-01-01",
    ))
    db.add_tags(skill_id, ["python", "httpx"])

    results = db.search("scrape")
    assert len(results) == 1
    assert results[0].name == "web-scraper"

    results = db.search("httpx")
    assert len(results) == 1

    results = db.search("nonexistent")
    assert len(results) == 0
    db.close()


def test_priority_resolution(tmp_path):
    """Skills from higher-priority sources should be returned first."""
    db = Database(tmp_path / "test.db")
    db.initialize()
    db.upsert_source("infra", "/path/infra", 10)
    db.upsert_source("personal", "/path/personal", 30)

    # Same skill in two sources
    db.insert_skill(Skill(
        name="deploy", source="infra", description="Infra version",
        updated_at="2026-01-01",
    ))
    db.insert_skill(Skill(
        name="deploy", source="personal", description="Personal version",
        updated_at="2026-01-01",
    ))

    # Without source filter, should get infra (lower priority number = higher priority)
    skill = db.get_skill("deploy")
    assert skill is not None
    assert skill.source == "infra"

    # With explicit source filter
    skill = db.get_skill("deploy", source="personal")
    assert skill.source == "personal"

    db.close()


def test_clear(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    db.upsert_source("test", "/tmp/test", 10)
    db.insert_skill(Skill(
        name="s", source="test", updated_at="2026-01-01",
    ))
    assert db.skill_count() == 1
    db.clear()
    assert db.skill_count() == 0
    db.close()
