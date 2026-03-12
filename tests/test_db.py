"""Tests for database operations."""

from pathlib import Path
from skillm.db import Database
from skillm.models import Skill, Version, FileRecord


def test_initialize(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    assert db.skill_count() == 0
    db.close()


def test_skill_crud(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()

    # Insert
    skill_id = db.insert_skill(Skill(
        name="test-skill", description="A test", author="me",
        created_at="2026-01-01", updated_at="2026-01-01",
    ))
    assert skill_id > 0

    # Get
    skill = db.get_skill("test-skill")
    assert skill is not None
    assert skill.name == "test-skill"
    assert skill.description == "A test"

    # Update
    skill.description = "Updated"
    skill.updated_at = "2026-01-02"
    db.update_skill(skill)
    skill = db.get_skill("test-skill")
    assert skill.description == "Updated"

    # List
    skills = db.list_skills()
    assert len(skills) == 1

    # Delete
    assert db.delete_skill("test-skill")
    assert db.get_skill("test-skill") is None
    db.close()


def test_versions(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()

    skill_id = db.insert_skill(Skill(
        name="s", created_at="2026-01-01", updated_at="2026-01-01",
    ))

    db.insert_version(Version(
        skill_id=skill_id, version="v1", file_count=2,
        total_size=1024, published_at="2026-01-01",
    ))
    db.insert_version(Version(
        skill_id=skill_id, version="v2", file_count=3,
        total_size=2048, published_at="2026-01-02",
    ))

    versions = db.get_versions(skill_id)
    assert len(versions) == 2

    latest = db.get_latest_version(skill_id)
    assert latest.version == "v2"

    assert db.delete_version(skill_id, "v1")
    assert len(db.get_versions(skill_id)) == 1
    db.close()


def test_tags(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()

    skill_id = db.insert_skill(Skill(
        name="s", created_at="2026-01-01", updated_at="2026-01-01",
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

    skill_id = db.insert_skill(Skill(
        name="web-scraper", description="Scrape websites",
        created_at="2026-01-01", updated_at="2026-01-01",
    ))
    db.update_search_content(skill_id, "Use httpx to scrape pages")

    results = db.search("scrape")
    assert len(results) == 1
    assert results[0].name == "web-scraper"

    results = db.search("httpx")
    assert len(results) == 1
    db.close()


def test_files(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()

    skill_id = db.insert_skill(Skill(
        name="s", created_at="2026-01-01", updated_at="2026-01-01",
    ))
    ver_id = db.insert_version(Version(
        skill_id=skill_id, version="v1", published_at="2026-01-01",
    ))

    db.insert_file(FileRecord(
        version_id=ver_id, rel_path="SKILL.md", size=100, sha256="abc123",
    ))
    files = db.get_files(ver_id)
    assert len(files) == 1
    assert files[0].rel_path == "SKILL.md"
    db.close()
