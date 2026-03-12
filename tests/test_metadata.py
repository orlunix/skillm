"""Tests for metadata extraction."""

from pathlib import Path
from skillm.metadata import extract_metadata


def test_extract_basic(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "# My Skill\n\nA great skill for testing.\n\n## Instructions\n\nDo stuff.\n"
    )

    meta = extract_metadata(skill_dir)
    assert meta.name == "my-skill"
    assert "great skill" in meta.description


def test_extract_with_meta_block(tmp_path):
    skill_dir = tmp_path / "tagged"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "# Tagged Skill\n\n"
        "Description here.\n\n"
        "<!-- skillm:meta\n"
        "tags: web, scraping, python\n"
        "author: alice\n"
        "requires: httpx, beautifulsoup4\n"
        "-->\n"
    )

    meta = extract_metadata(skill_dir)
    assert meta.tags == ["web", "scraping", "python"]
    assert meta.author == "alice"
    assert meta.requires == ["httpx", "beautifulsoup4"]


def test_extract_name_override(tmp_path):
    skill_dir = tmp_path / "original"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Original\n\nDesc.\n")

    meta = extract_metadata(skill_dir, name_override="custom-name")
    assert meta.name == "custom-name"


def test_missing_skill_md(tmp_path):
    skill_dir = tmp_path / "empty"
    skill_dir.mkdir()

    try:
        extract_metadata(skill_dir)
        assert False, "Should have raised"
    except FileNotFoundError:
        pass
