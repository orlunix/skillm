"""Shared test fixtures."""

import json
import pytest
from pathlib import Path
from skillm.config import Config
from skillm.core import Library, Project


@pytest.fixture
def tmp_library(tmp_path):
    """Create a temporary library."""
    lib_path = tmp_path / "library"
    config = Config()
    config.library.path = str(lib_path)
    lib = Library(config)
    lib.init()
    return lib


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
def tmp_project(tmp_path, tmp_library):
    """Create a temporary project with an initialized library."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    project = Project(project_dir=project_dir, library=tmp_library, agent="claude")
    project.init()
    return project
