"""Tests for CLI commands."""

from click.testing import CliRunner
from pathlib import Path
from skillm.cli import cli
from skillm.config import Config, Source
from skillm.core import SourceManager


def _setup_sm(tmp_path):
    """Create a SourceManager with a temp source repo."""
    source_path = tmp_path / "source-repo"
    cache_path = tmp_path / "cache"
    config = Config()
    config.settings.cache_dir = str(cache_path)
    config.settings.default_source = "test"
    config.sources = [Source(name="test", url=str(source_path), priority=10)]
    sm = SourceManager(config)
    sm.init_source("test", str(source_path))
    return sm


def _create_skill(tmp_path, name="test-skill"):
    skill_dir = tmp_path / name
    skill_dir.mkdir(exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"# {name}\n\nA test skill.\n")
    return skill_dir


def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "2.0.0" in result.output


def test_source_init_and_list(tmp_path, monkeypatch):
    sm = _setup_sm(tmp_path)

    import skillm.cli
    monkeypatch.setattr(skillm.cli, "_get_source_manager", lambda: sm)

    runner = CliRunner()
    result = runner.invoke(cli, ["source", "list"])
    assert result.exit_code == 0
    assert "test" in result.output


def test_add_and_list(tmp_path, monkeypatch):
    sm = _setup_sm(tmp_path)
    skill_dir = _create_skill(tmp_path)

    import skillm.cli
    monkeypatch.setattr(skillm.cli, "_get_source_manager", lambda: sm)

    runner = CliRunner()

    result = runner.invoke(cli, ["add", str(skill_dir)])
    assert result.exit_code == 0
    assert "test-skill" in result.output

    result = runner.invoke(cli, ["list"])
    assert result.exit_code == 0
    assert "test-skill" in result.output

    result = runner.invoke(cli, ["info", "test-skill"])
    assert result.exit_code == 0
    assert "test-skill" in result.output


def test_publish(tmp_path, monkeypatch):
    sm = _setup_sm(tmp_path)
    skill_dir = _create_skill(tmp_path)
    sm.add_skill(skill_dir)

    import skillm.cli
    monkeypatch.setattr(skillm.cli, "_get_source_manager", lambda: sm)

    runner = CliRunner()
    result = runner.invoke(cli, ["publish", "test-skill"])
    assert result.exit_code == 0
    assert "test-skill" in result.output
