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


# ── YAML Frontmatter Tests ─────────────────────────────────

def test_yaml_frontmatter_basic(tmp_path):
    skill_dir = tmp_path / "fm-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: my-tool\n"
        "description: A tool for things\n"
        "author: bob\n"
        "tags: [cli, tool, python]\n"
        "requires: [python3, click]\n"
        "source: bob/my-tool\n"
        "---\n\n"
        "# My Tool\n\n"
        "Body text here.\n"
    )

    meta = extract_metadata(skill_dir)
    assert meta.name == "my-tool"
    assert meta.description == "A tool for things"
    assert meta.author == "bob"
    assert meta.tags == ["cli", "tool", "python"]
    assert meta.requires == ["python3", "click"]
    assert meta.source == "bob/my-tool"


def test_yaml_frontmatter_overrides_name(tmp_path):
    """Frontmatter name takes precedence over directory name."""
    skill_dir = tmp_path / "dir-name"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: frontmatter-name\n"
        "---\n\n"
        "# Heading Name\n\n"
        "Desc.\n"
    )

    meta = extract_metadata(skill_dir)
    assert meta.name == "frontmatter-name"


def test_yaml_frontmatter_name_override_wins(tmp_path):
    """Explicit name_override beats frontmatter."""
    skill_dir = tmp_path / "whatever"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: fm-name\n"
        "---\n\n"
        "# Heading\n\n"
        "Desc.\n"
    )

    meta = extract_metadata(skill_dir, name_override="explicit")
    assert meta.name == "explicit"


def test_yaml_frontmatter_description_fallback(tmp_path):
    """If frontmatter has no description, fall back to first paragraph."""
    skill_dir = tmp_path / "no-desc"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "tags: [test]\n"
        "---\n\n"
        "# My Skill\n\n"
        "The paragraph description.\n"
    )

    meta = extract_metadata(skill_dir)
    assert meta.description == "The paragraph description."


def test_yaml_frontmatter_tags_as_string(tmp_path):
    """Tags as comma-separated string should work too."""
    skill_dir = tmp_path / "str-tags"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "tags: web, scraping, python\n"
        "---\n\n"
        "# Skill\n\n"
        "Desc.\n"
    )

    meta = extract_metadata(skill_dir)
    assert meta.tags == ["web", "scraping", "python"]


def test_clawhub_compat_frontmatter(tmp_path):
    """ClawHub-style metadata.openclaw.requires.anyBins maps to requires."""
    skill_dir = tmp_path / "cam"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        '---\n'
        'name: cam\n'
        'description: Manage coding agents\n'
        'metadata:\n'
        '  openclaw:\n'
        '    emoji: "🎯"\n'
        '    requires:\n'
        '      anyBins: ["cam"]\n'
        '---\n\n'
        '# CAM\n\n'
        'Body.\n'
    )

    meta = extract_metadata(skill_dir)
    assert meta.name == "cam"
    assert meta.description == "Manage coding agents"
    assert meta.requires == ["cam"]


def test_frontmatter_beats_comment_block(tmp_path):
    """YAML frontmatter takes precedence over HTML comment block."""
    skill_dir = tmp_path / "both"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "author: from-frontmatter\n"
        "tags: [fm-tag]\n"
        "---\n\n"
        "# Skill\n\n"
        "Desc.\n\n"
        "<!-- skillm:meta\n"
        "author: from-comment\n"
        "tags: comment-tag\n"
        "-->\n"
    )

    meta = extract_metadata(skill_dir)
    assert meta.author == "from-frontmatter"
    assert meta.tags == ["fm-tag"]
