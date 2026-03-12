"""SKILL.md parsing and metadata extraction."""

from __future__ import annotations

import re
from pathlib import Path

from .models import SkillMeta


def extract_metadata(skill_dir: Path, name_override: str | None = None) -> SkillMeta:
    """Extract metadata from a skill directory's SKILL.md file."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"No SKILL.md found in {skill_dir}")

    content = skill_md.read_text(encoding="utf-8")
    meta = SkillMeta(content=content)

    # Name: override > directory name > first heading
    if name_override:
        meta.name = name_override
    else:
        meta.name = skill_dir.name
        heading = _extract_heading(content)
        if heading and not name_override:
            # Use dir name as canonical, heading is just for display
            pass

    # Description: first non-heading, non-empty paragraph
    meta.description = _extract_description(content)

    # Parse <!-- skillm:meta --> block
    meta_block = _extract_meta_block(content)
    if meta_block:
        if "tags" in meta_block:
            meta.tags = [t.strip() for t in meta_block["tags"].split(",") if t.strip()]
        if "author" in meta_block:
            meta.author = meta_block["author"].strip()
        if "requires" in meta_block:
            meta.requires = [r.strip() for r in meta_block["requires"].split(",") if r.strip()]

    # Fallback author from git config
    if not meta.author:
        meta.author = _git_author()

    return meta


def _extract_heading(content: str) -> str:
    """Extract the first # heading from markdown."""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_description(content: str) -> str:
    """Extract the first paragraph after the heading."""
    lines = content.split("\n")
    past_heading = False
    desc_lines = []

    for line in lines:
        stripped = line.strip()
        if not past_heading:
            if stripped.startswith("#"):
                past_heading = True
            continue

        if not stripped:
            if desc_lines:
                break
            continue

        if stripped.startswith("#") or stripped.startswith("<!--"):
            if desc_lines:
                break
            continue

        desc_lines.append(stripped)

    return " ".join(desc_lines)


def _extract_meta_block(content: str) -> dict[str, str] | None:
    """Parse <!-- skillm:meta ... --> comment block."""
    match = re.search(
        r"<!--\s*skillm:meta\s*\n(.*?)-->",
        content,
        re.DOTALL,
    )
    if not match:
        return None

    block = match.group(1)
    result = {}
    for line in block.strip().split("\n"):
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()

    return result


def _git_author() -> str:
    """Try to get author name from git config."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
