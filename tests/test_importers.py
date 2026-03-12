"""Tests for import source detection and local imports."""

from skillm.importers import detect_source_type


def test_detect_directory(tmp_path):
    d = tmp_path / "skill"
    d.mkdir()
    assert detect_source_type(str(d)) == "directory"


def test_detect_skillpack(tmp_path):
    f = tmp_path / "test.skillpack"
    f.write_text("")
    assert detect_source_type(str(f)) == "skillpack"


def test_detect_github():
    assert detect_source_type("owner/repo") == "github"
    assert detect_source_type("owner/repo/subpath") == "github"
    assert detect_source_type("owner/repo/deep/path") == "github"


def test_detect_clawhub():
    assert detect_source_type("clawhub:defuddle") == "clawhub"
    assert detect_source_type("clawhub:defuddle@1.0.0") == "clawhub"


def test_detect_url():
    assert detect_source_type("https://example.com/skill.tar.gz") == "url"
    assert detect_source_type("http://example.com/skill.zip") == "url"


def test_detect_invalid():
    try:
        detect_source_type("not a valid source!!!")
        assert False, "Should have raised"
    except ValueError:
        pass
