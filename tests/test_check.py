"""Tests for environment verification."""

import os
import sys
from skillm.check import (
    check_requirements,
    _check_binary,
    _check_python_version,
    _check_python_package,
    _check_env_var,
    _check_platform,
)


def test_check_binary_found():
    result = _check_binary("python3")
    assert result.ok
    assert "Found" in result.message


def test_check_binary_missing():
    result = _check_binary("totally_nonexistent_binary_xyz")
    assert not result.ok
    assert "Not found" in result.message


def test_check_python_version_ok():
    current = f"{sys.version_info.major}.{sys.version_info.minor}"
    result = _check_python_version(f">={current}")
    assert result.ok


def test_check_python_version_too_high():
    result = _check_python_version(">=99.99")
    assert not result.ok


def test_check_python_package_installed():
    result = _check_python_package("click")
    assert result.ok
    assert "Installed" in result.message


def test_check_python_package_missing():
    result = _check_python_package("totally_nonexistent_package_xyz")
    assert not result.ok


def test_check_env_var_set(monkeypatch):
    monkeypatch.setenv("SKILLM_TEST_VAR", "hello123")
    result = _check_env_var("SKILLM_TEST_VAR")
    assert result.ok
    assert "hell..." in result.message


def test_check_env_var_missing(monkeypatch):
    monkeypatch.delenv("SKILLM_TEST_VAR_MISSING", raising=False)
    result = _check_env_var("SKILLM_TEST_VAR_MISSING")
    assert not result.ok


def test_check_platform_current():
    # Current platform should always pass
    plat = {"linux": "linux", "darwin": "macos", "win32": "windows"}[sys.platform]
    result = _check_platform([plat])
    assert result.ok


def test_check_platform_wrong():
    result = _check_platform(["nonexistent_os"])
    assert not result.ok


def test_check_requirements_structured():
    report = check_requirements("test-skill", {
        "bins": ["python3"],
        "packages": ["click"],
        "platform": ["linux", "macos", "windows"],
    })
    assert report.has_checks
    # python3 and click should be found, platform should match
    assert report.passed >= 2


def test_check_requirements_flat_list():
    """Legacy flat list treated as bins."""
    report = check_requirements("test-skill", ["python3", "nonexistent_xyz"])
    assert report.has_checks
    assert report.passed >= 1
    assert report.failed >= 1


def test_check_requirements_empty():
    report = check_requirements("test-skill", {})
    assert not report.has_checks
    assert report.all_ok


def test_check_requirements_none():
    report = check_requirements("test-skill", [])
    assert not report.has_checks
