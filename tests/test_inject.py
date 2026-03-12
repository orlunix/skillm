"""Tests for agent config injection."""

import json
from pathlib import Path
from skillm.inject import inject, detect_format, MARKER_START, MARKER_END


def _setup_project(project_dir, skills):
    """Helper to set up a project with skills."""
    project_dir.mkdir(exist_ok=True)
    skills_dir = project_dir / ".skills"
    skills_dir.mkdir(exist_ok=True)

    manifest = {"skills": {}}
    for name, version in skills.items():
        manifest["skills"][name] = {"version": version}
        skill_dir = skills_dir / name
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text(f"# {name}\n\nDescription of {name}.\n")

    (project_dir / "skills.json").write_text(json.dumps(manifest, indent=2))


def test_detect_format(tmp_path):
    assert detect_format(tmp_path) == "claude"  # default

    (tmp_path / ".cursorrules").write_text("")
    assert detect_format(tmp_path) == "cursor"


def test_inject_creates_file(tmp_path):
    _setup_project(tmp_path, {"my-skill": "v1"})

    target = inject(tmp_path, fmt="claude")
    assert target.name == "CLAUDE.md"
    assert target.exists()

    content = target.read_text()
    assert MARKER_START in content
    assert "my-skill" in content


def test_inject_updates_existing(tmp_path):
    _setup_project(tmp_path, {"my-skill": "v1"})

    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# My Project\n\nExisting content.\n")

    inject(tmp_path, fmt="claude")
    content = claude_md.read_text()
    assert "Existing content" in content
    assert MARKER_START in content

    # Re-inject with additional skill
    _setup_project(tmp_path, {"my-skill": "v1", "other": "v2"})
    inject(tmp_path, fmt="claude")
    content = claude_md.read_text()
    assert content.count(MARKER_START) == 1  # No duplicates
    assert "other" in content


def test_inject_disabled_skill(tmp_path):
    _setup_project(tmp_path, {"my-skill": "v1"})

    manifest = json.loads((tmp_path / "skills.json").read_text())
    manifest["skills"]["my-skill"]["enabled"] = False
    (tmp_path / "skills.json").write_text(json.dumps(manifest))

    inject(tmp_path, fmt="claude")
    content = (tmp_path / "CLAUDE.md").read_text()
    assert "my-skill" not in content or MARKER_START in content
