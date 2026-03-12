"""Tests for CLI commands."""

from click.testing import CliRunner
from pathlib import Path
from skillm.cli import cli
from skillm.config import Config
from skillm.core import Library


def _init_library(tmp_path):
    lib_path = tmp_path / "library"
    config = Config()
    config.library.path = str(lib_path)
    lib = Library(config)
    lib.init()
    return lib_path


def _create_skill(tmp_path, name="test-skill"):
    skill_dir = tmp_path / name
    skill_dir.mkdir(exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"# {name}\n\nA test skill.\n")
    return skill_dir


def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.2.0" in result.output


def test_library_init(tmp_path, monkeypatch):
    runner = CliRunner()
    lib_path = tmp_path / "lib"
    result = runner.invoke(cli, ["library", "init", "--path", str(lib_path)])
    assert result.exit_code == 0
    assert "initialized" in result.output.lower()
    assert (lib_path / "library.db").exists()


def test_publish_and_list(tmp_path, monkeypatch):
    lib_path = _init_library(tmp_path)
    skill_dir = _create_skill(tmp_path)

    monkeypatch.setenv("SKILLM_LIBRARY_PATH", str(lib_path))

    # Patch load_config to use our temp library
    import skillm.cli
    original_get_library = skillm.cli._get_library
    def patched_get_library():
        config = Config()
        config.library.path = str(lib_path)
        return Library(config)
    monkeypatch.setattr(skillm.cli, "_get_library", patched_get_library)

    runner = CliRunner()

    result = runner.invoke(cli, ["publish", str(skill_dir)])
    assert result.exit_code == 0
    assert "test-skill" in result.output

    result = runner.invoke(cli, ["list"])
    assert result.exit_code == 0
    assert "test-skill" in result.output

    result = runner.invoke(cli, ["info", "test-skill"])
    assert result.exit_code == 0
    assert "test-skill" in result.output
