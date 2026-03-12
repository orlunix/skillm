"""Import backends for fetching skills from various sources.

Supported sources:
- Local directory
- .skillpack archive
- GitHub (owner/repo)
- ClawHub registry (clawhub:slug)
- URL (tar.gz or zip)
"""

from __future__ import annotations

import io
import re
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path

import httpx

GITHUB_API = "https://api.github.com"
CLAWHUB_API = "https://clawhub.ai/api/v1"

# Patterns for source detection
_GITHUB_RE = re.compile(r"^([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)(?:/(.+))?$")
_CLAWHUB_RE = re.compile(r"^clawhub:([a-zA-Z0-9_.-]+)(?:@(.+))?$")
_URL_RE = re.compile(r"^https?://")


def detect_source_type(source: str) -> str:
    """Detect the type of import source.

    Returns one of: 'directory', 'skillpack', 'github', 'clawhub', 'url'
    """
    path = Path(source)

    if path.suffix == ".skillpack":
        return "skillpack"

    if path.is_dir():
        return "directory"

    if _CLAWHUB_RE.match(source):
        return "clawhub"

    if _URL_RE.match(source):
        return "url"

    if _GITHUB_RE.match(source):
        return "github"

    raise ValueError(
        f"Cannot detect source type for: {source}\n"
        "Expected: local dir, .skillpack, owner/repo, clawhub:slug, or https://..."
    )


def import_from_github(
    source: str,
    ref: str | None = None,
    token: str | None = None,
) -> tuple[Path, str]:
    """Download a skill from GitHub.

    Args:
        source: owner/repo or owner/repo/subpath
        ref: Git ref (tag, branch, commit). Default: repo default branch.
        token: GitHub personal access token (optional, for private repos).

    Returns:
        Tuple of (temp_dir_with_skill_files, source_string)
    """
    match = _GITHUB_RE.match(source)
    if not match:
        raise ValueError(f"Invalid GitHub source: {source}")

    owner, repo, subpath = match.group(1), match.group(2), match.group(3)
    ref_part = f"/{ref}" if ref else ""

    url = f"{GITHUB_API}/repos/{owner}/{repo}/tarball{ref_part}"
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with httpx.Client(follow_redirects=True, timeout=60) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()

    extract_dir = Path(tempfile.mkdtemp(prefix="skillm-gh-"))

    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        # Safety check
        for member in tar.getmembers():
            if member.name.startswith("/") or ".." in member.name:
                raise ValueError(f"Unsafe path in archive: {member.name}")
        tar.extractall(extract_dir)

    # GitHub tarballs extract to a directory like owner-repo-sha/
    top_dirs = [d for d in extract_dir.iterdir() if d.is_dir()]
    if len(top_dirs) != 1:
        raise ValueError(f"Unexpected archive structure: {[d.name for d in top_dirs]}")

    skill_dir = top_dirs[0]
    if subpath:
        skill_dir = skill_dir / subpath
        if not skill_dir.exists():
            shutil.rmtree(extract_dir)
            raise FileNotFoundError(f"Subpath not found in repo: {subpath}")

    # Verify SKILL.md exists
    has_skill_md = any(f.name.lower() == "skill.md" for f in skill_dir.iterdir() if f.is_file())
    if not has_skill_md:
        shutil.rmtree(extract_dir)
        raise FileNotFoundError(f"No SKILL.md found in {source}")

    return skill_dir, f"{owner}/{repo}" + (f"/{subpath}" if subpath else "")


def import_from_clawhub(
    source: str,
    token: str | None = None,
) -> tuple[Path, str]:
    """Download a skill from ClawHub registry.

    Args:
        source: clawhub:slug or clawhub:slug@version

    Returns:
        Tuple of (temp_dir_with_skill_files, source_string)
    """
    match = _CLAWHUB_RE.match(source)
    if not match:
        raise ValueError(f"Invalid ClawHub source: {source}")

    slug = match.group(1)
    version = match.group(2)  # May be None

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with httpx.Client(follow_redirects=True, timeout=60) as client:
        # Resolve skill metadata
        resp = client.get(f"{CLAWHUB_API}/skills/{slug}", headers=headers)
        resp.raise_for_status()
        skill_data = resp.json()

        if not version:
            version = skill_data.get("latestVersion", skill_data.get("version"))

        # Download zip
        resp = client.get(
            f"{CLAWHUB_API}/download",
            params={"slug": slug, "version": version},
            headers=headers,
        )
        resp.raise_for_status()

    extract_dir = Path(tempfile.mkdtemp(prefix="skillm-ch-"))

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        # Safety check
        for name in zf.namelist():
            if name.startswith("/") or ".." in name:
                raise ValueError(f"Unsafe path in archive: {name}")
        zf.extractall(extract_dir)

    # Find SKILL.md — could be at root or in a subdirectory
    skill_dir = _find_skill_root(extract_dir)
    if skill_dir is None:
        shutil.rmtree(extract_dir)
        raise FileNotFoundError(f"No SKILL.md found in clawhub:{slug}")

    source_str = f"clawhub:{slug}"
    if version:
        source_str += f"@{version}"

    return skill_dir, source_str


def import_from_url(
    url: str,
) -> tuple[Path, str]:
    """Download a skill from a URL (tar.gz or zip).

    Returns:
        Tuple of (temp_dir_with_skill_files, source_string)
    """
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        resp = client.get(url)
        resp.raise_for_status()

    extract_dir = Path(tempfile.mkdtemp(prefix="skillm-url-"))
    data = resp.content

    # Detect format and extract
    if url.endswith(".tar.gz") or url.endswith(".tgz"):
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.name.startswith("/") or ".." in member.name:
                    raise ValueError(f"Unsafe path in archive: {member.name}")
            tar.extractall(extract_dir)
    elif url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if name.startswith("/") or ".." in name:
                    raise ValueError(f"Unsafe path in archive: {name}")
            zf.extractall(extract_dir)
    else:
        # Try tar.gz first, then zip
        try:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                for member in tar.getmembers():
                    if member.name.startswith("/") or ".." in member.name:
                        raise ValueError(f"Unsafe path in archive: {member.name}")
                tar.extractall(extract_dir)
        except tarfile.TarError:
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for name in zf.namelist():
                        if name.startswith("/") or ".." in name:
                            raise ValueError(f"Unsafe path in archive: {name}")
                    zf.extractall(extract_dir)
            except zipfile.BadZipFile:
                shutil.rmtree(extract_dir)
                raise ValueError(f"Could not extract archive from {url}")

    skill_dir = _find_skill_root(extract_dir)
    if skill_dir is None:
        shutil.rmtree(extract_dir)
        raise FileNotFoundError(f"No SKILL.md found in archive from {url}")

    return skill_dir, url


def _find_skill_root(directory: Path) -> Path | None:
    """Find the directory containing SKILL.md, searching up to 2 levels deep."""
    # Check root
    for f in directory.iterdir():
        if f.is_file() and f.name.lower() == "skill.md":
            return directory

    # Check one level down (common: archive extracts to a single subdirectory)
    for child in directory.iterdir():
        if child.is_dir():
            for f in child.iterdir():
                if f.is_file() and f.name.lower() == "skill.md":
                    return child

    # Check two levels down
    for child in directory.iterdir():
        if child.is_dir():
            for grandchild in child.iterdir():
                if grandchild.is_dir():
                    for f in grandchild.iterdir():
                        if f.is_file() and f.name.lower() == "skill.md":
                            return grandchild

    return None
