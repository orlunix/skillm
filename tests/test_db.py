"""Tests for database operations."""

from pathlib import Path
from skillm.db import Database
from skillm.models import Skill


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
        updated_at="2026-01-01",
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


def test_upsert(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()

    # First insert
    skill_id = db.upsert_skill(Skill(
        repo="local", name="upsert-skill", description="Original",
        updated_at="2026-01-01", commit="abc123",
    ))
    assert skill_id > 0

    # Upsert same skill — should update, not insert
    skill_id2 = db.upsert_skill(Skill(
        repo="local", name="upsert-skill", description="Updated",
        updated_at="2026-01-02", commit="def456",
    ))
    assert skill_id2 == skill_id

    skill = db.get_skill("upsert-skill", repo="local")
    assert skill.description == "Updated"
    assert skill.commit == "def456"

    # Only one skill in DB
    assert db.skill_count() == 1
    db.close()


def test_tags(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()

    skill_id = db.insert_skill(Skill(
        name="s", updated_at="2026-01-01",
    ))

    db.set_tags(skill_id, ["web", "scraping"])
    assert db.get_tags(skill_id) == ["scraping", "web"]

    # Replace tags
    db.set_tags(skill_id, ["python", "scraping"])
    tags = db.get_tags(skill_id)
    assert "python" in tags
    assert "scraping" in tags
    assert "web" not in tags
    db.close()


def test_search(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()

    skill_id = db.insert_skill(Skill(
        name="web-scraper", description="Scrape websites",
        updated_at="2026-01-01",
    ))
    db.set_tags(skill_id, ["python", "httpx"])

    # Search by description
    results = db.search("scrape")
    assert len(results) == 1
    assert results[0].name == "web-scraper"

    # Search by tag
    results = db.search("httpx")
    assert len(results) == 1

    # No match
    results = db.search("nonexistent")
    assert len(results) == 0
    db.close()


def test_categories(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()

    db.insert_skill(Skill(name="a", category="infra", updated_at="2026-01-01"))
    db.insert_skill(Skill(name="b", category="infra", updated_at="2026-01-01"))
    db.insert_skill(Skill(name="c", category="dev", updated_at="2026-01-01"))

    cats = db.list_categories()
    assert len(cats) == 2
    cat_dict = dict(cats)
    assert cat_dict["infra"] == 2
    assert cat_dict["dev"] == 1
    db.close()


def test_repo_filtering(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()

    db.insert_skill(Skill(repo="origin", name="s1", updated_at="2026-01-01"))
    db.insert_skill(Skill(repo="team", name="s2", updated_at="2026-01-01"))

    # Filter by repo
    origin_skills = db.list_skills(repo="origin")
    assert len(origin_skills) == 1
    assert origin_skills[0].name == "s1"

    # All repos
    all_skills = db.list_skills()
    assert len(all_skills) == 2
    db.close()


def test_find_skill_by_short_name(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()

    db.insert_skill(Skill(repo="local", name="main/deploy-k8s", updated_at="2026-01-01"))

    # Find by short name
    skill = db.find_skill_by_short_name("deploy-k8s")
    assert skill is not None
    assert skill.name == "main/deploy-k8s"

    # Not found
    assert db.find_skill_by_short_name("nonexistent") is None
    db.close()
