"""Tests for .skillpack export/import."""

from pathlib import Path
from skillm.skillpack import export_skill, import_skillpack


def test_export_import_roundtrip(tmp_path):
    # Create a skill directory
    skill_dir = tmp_path / "source"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Test\n\nA test skill.\n")
    (skill_dir / "helper.py").write_text("print('hi')\n")

    # Export
    archive = export_skill(
        skill_dir, "test-skill", "v1",
        {"description": "A test", "author": "me", "tags": ["test"]},
        output_dir=tmp_path,
    )
    assert archive.exists()
    assert archive.name == "test-skill-v1.skillpack"

    # Import
    files_dir, metadata = import_skillpack(archive)
    assert metadata["name"] == "test-skill"
    assert metadata["version"] == "v1"
    assert (files_dir / "SKILL.md").exists()
    assert (files_dir / "helper.py").exists()

    # Cleanup
    import shutil
    shutil.rmtree(files_dir.parent)


def test_import_missing_file(tmp_path):
    try:
        import_skillpack(tmp_path / "nonexistent.skillpack")
        assert False, "Should have raised"
    except FileNotFoundError:
        pass
