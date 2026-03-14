"""Shared test fixtures for skillm v2."""

import json
import pytest
from pathlib import Path
from skillm.config import Config, Source
from skillm.core import SourceManager, Project


@pytest.fixture
def tmp_source_repo(tmp_path):
    """Create a temporary source git repo with one source configured."""
    source_path = tmp_path / "source-repo"
    cache_path = tmp_path / "cache"

    config = Config()
    config.settings.cache_dir = str(cache_path)
    config.settings.default_source = "test"
    config.sources = [Source(name="test", url=str(source_path), priority=10)]

    sm = SourceManager(config)
    sm.init_source("test", str(source_path))
    return sm


@pytest.fixture
def sample_skill(tmp_path):
    """Create a sample skill directory."""
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "# My Skill\n\n"
        "A test skill for unit tests.\n\n"
        "<!-- skillm:meta\n"
        "tags: test, sample\n"
        "author: tester\n"
        "-->\n\n"
        "## Instructions\n\n"
        "Do the thing.\n"
    )
    (skill_dir / "scripts").mkdir()
    (skill_dir / "scripts" / "helper.py").write_text("print('hello')\n")
    return skill_dir


@pytest.fixture
def tmp_project(tmp_path, tmp_source_repo):
    """Create a temporary project with an initialized source."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    project = Project(
        project_dir=project_dir,
        source_manager=tmp_source_repo,
        agent="claude",
    )
    project.init()
    return project
