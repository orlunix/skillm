"""Tests for auto-scanning SKILL.md content."""

from skillm.scan import scan_skill_content, diff_requires, ScanResult


def test_scan_detects_python_imports():
    content = """# My Skill

```python
import httpx
from bs4 import BeautifulSoup
import os
import json
```
"""
    result = scan_skill_content(content)
    assert "httpx" in result.packages
    assert "beautifulsoup4" in result.packages
    # stdlib should be excluded
    assert "os" not in result.packages
    assert "json" not in result.packages


def test_scan_detects_bins():
    content = """# Docker Skill

```bash
$ docker build -t myapp .
$ git clone https://example.com/repo
```
"""
    result = scan_skill_content(content)
    assert "docker" in result.bins
    assert "git" in result.bins


def test_scan_detects_env_vars():
    content = """# API Skill

```python
api_key = os.environ["API_KEY"]
secret = os.getenv("SECRET_TOKEN")
```
"""
    result = scan_skill_content(content)
    assert "API_KEY" in result.env
    assert "SECRET_TOKEN" in result.env


def test_scan_ignores_common_env_vars():
    content = """# Shell Skill

```bash
echo $HOME
echo $PATH
echo $USER
```
"""
    result = scan_skill_content(content)
    assert "HOME" not in result.env
    assert "PATH" not in result.env
    assert "USER" not in result.env


def test_scan_detects_pip_install():
    content = """# Setup

```bash
pip install requests click
pip3 install flask
```
"""
    result = scan_skill_content(content)
    assert "requests" in result.packages
    assert "click" in result.packages
    assert "flask" in result.packages


def test_scan_detects_npm_install():
    content = """# Setup

```bash
npm install express
```
"""
    result = scan_skill_content(content)
    assert "node" in result.bins


def test_scan_detects_backtick_bins():
    content = """# Tools

Use `curl` to fetch data and `jq` to parse it.
"""
    result = scan_skill_content(content)
    assert "curl" in result.bins
    assert "jq" in result.bins


def test_scan_empty_content():
    result = scan_skill_content("")
    assert not result.has_findings


def test_scan_no_code_blocks():
    content = "# Simple Skill\n\nJust a description.\n"
    result = scan_skill_content(content)
    assert not result.has_findings


def test_scan_deduplicates():
    content = """# Skill

```python
import httpx
```

```python
import httpx
```
"""
    result = scan_skill_content(content)
    assert result.packages.count("httpx") == 1


def test_diff_requires_finds_missing():
    declared = {"bins": ["python3"], "packages": ["click"]}
    detected = ScanResult(
        bins=["python3", "docker"],
        packages=["click", "httpx"],
        env=["API_KEY"],
    )
    missing = diff_requires(declared, detected)
    assert "docker" in missing.bins
    assert "python3" not in missing.bins
    assert "httpx" in missing.packages
    assert "click" not in missing.packages
    assert "API_KEY" in missing.env


def test_diff_requires_flat_list():
    declared = ["python3", "docker"]
    detected = ScanResult(bins=["python3", "docker", "git"])
    missing = diff_requires(declared, detected)
    assert "git" in missing.bins
    assert "python3" not in missing.bins


def test_diff_requires_nothing_missing():
    declared = {"bins": ["docker"], "packages": ["httpx"]}
    detected = ScanResult(bins=["docker"], packages=["httpx"])
    missing = diff_requires(declared, detected)
    assert not missing.has_findings


def test_scan_result_to_requires():
    result = ScanResult(bins=["docker", "git"], packages=["httpx"], env=["API_KEY"])
    req = result.to_requires()
    assert req == {
        "bins": ["docker", "git"],
        "env": ["API_KEY"],
        "packages": ["httpx"],
    }


def test_scan_result_to_requires_empty():
    result = ScanResult()
    assert result.to_requires() == {}


def test_scan_shell_env_vars():
    content = """# Deploy

```bash
curl -H "Authorization: ${AUTH_TOKEN}" $API_URL/endpoint
```
"""
    result = scan_skill_content(content)
    assert "AUTH_TOKEN" in result.env


def test_scan_import_to_package_mapping():
    """Known import→package mappings should use pip name."""
    content = """# Scraper

```python
from PIL import Image
import yaml
import cv2
```
"""
    result = scan_skill_content(content)
    assert "Pillow" in result.packages
    assert "pyyaml" in result.packages
    assert "opencv-python" in result.packages


def test_scan_skips_package_manager_bins():
    """pip, npm, etc. should not appear as bin requirements."""
    content = """# Setup

```bash
pip install requests
npm install express
brew install jq
```
"""
    result = scan_skill_content(content)
    assert "pip" not in result.bins
    assert "npm" not in result.bins
    assert "brew" not in result.bins
