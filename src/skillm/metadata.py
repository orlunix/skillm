"""SKILL.md parsing and metadata extraction.

Supports two metadata formats:
1. YAML frontmatter (preferred) — delimited by ---
2. HTML comment block (legacy) — <!-- skillm:meta ... -->

Also reads ClawHub-style frontmatter transparently.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .models import SkillMeta

# Match YAML frontmatter: starts at line 1, delimited by ---
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?\n)---\s*\n", re.DOTALL)


def extract_metadata(skill_dir: Path, name_override: str | None = None) -> SkillMeta:
    """Extract metadata from a skill directory's SKILL.md file."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        # Try case-insensitive
        for f in skill_dir.iterdir():
            if f.name.lower() == "skill.md":
                skill_md = f
                break
        else:
            raise FileNotFoundError(f"No SKILL.md found in {skill_dir}")

    content = skill_md.read_text(encoding="utf-8")
    meta = SkillMeta(content=content)

    # Try YAML frontmatter first, then fall back to HTML comment block
    fm = _extract_frontmatter(content)
    if fm:
        _apply_frontmatter(fm, meta)
    else:
        comment = _extract_meta_block(content)
        if comment:
            _apply_comment_block(comment, meta)

    # Name: override > frontmatter > directory name
    if name_override:
        meta.name = name_override
    elif not meta.name:
        meta.name = skill_dir.name

    # Description fallback: first paragraph after heading
    if not meta.description:
        meta.description = _extract_description(content)

    # Author fallback: git config
    if not meta.author:
        meta.author = _git_author()

    return meta


def _extract_frontmatter(content: str) -> dict | None:
    """Parse YAML frontmatter from --- delimiters."""
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return None

    try:
        data = yaml.safe_load(match.group(1))
        return data if isinstance(data, dict) else None
    except yaml.YAMLError:
        return None


def _apply_frontmatter(fm: dict, meta: SkillMeta) -> None:
    """Apply YAML frontmatter fields to SkillMeta."""
    if "name" in fm:
        meta.name = str(fm["name"])

    if "description" in fm:
        meta.description = str(fm["description"])

    if "category" in fm:
        meta.category = str(fm["category"]).strip().lower()

    if "author" in fm:
        meta.author = str(fm["author"])

    if "source" in fm:
        meta.source = str(fm["source"])

    if "tags" in fm:
        tags = fm["tags"]
        if isinstance(tags, list):
            meta.tags = [str(t).strip() for t in tags if t]
        elif isinstance(tags, str):
            meta.tags = [t.strip() for t in tags.split(",") if t.strip()]

    if "requires" in fm:
        reqs = fm["requires"]
        if isinstance(reqs, dict):
            # Structured format: {bins: [...], python: ">=3.10", packages: [...], ...}
            meta.requires = reqs
        elif isinstance(reqs, list):
            # Flat list — treat as bins for backward compat
            meta.requires = {"bins": [str(r).strip() for r in reqs if r]}
        elif isinstance(reqs, str):
            meta.requires = {"bins": [r.strip() for r in reqs.split(",") if r.strip()]}

    # ClawHub compatibility: metadata.openclaw.requires.anyBins → requires
    if not meta.requires and "metadata" in fm:
        md = fm["metadata"]
        if isinstance(md, dict):
            oc = md.get("openclaw", {})
            if isinstance(oc, dict):
                oc_reqs = oc.get("requires", {})
                if isinstance(oc_reqs, dict):
                    bins = oc_reqs.get("anyBins", [])
                    if isinstance(bins, list):
                        meta.requires = {"bins": [str(b) for b in bins]}


def _apply_comment_block(block: dict[str, str], meta: SkillMeta) -> None:
    """Apply HTML comment block fields to SkillMeta."""
    if "category" in block:
        meta.category = block["category"].strip().lower()
    if "tags" in block:
        meta.tags = [t.strip() for t in block["tags"].split(",") if t.strip()]
    if "author" in block:
        meta.author = block["author"].strip()
    if "requires" in block:
        meta.requires = {"bins": [r.strip() for r in block["requires"].split(",") if r.strip()]}
    if "source" in block:
        meta.source = block["source"].strip()


def _extract_heading(content: str) -> str:
    """Extract the first # heading from markdown."""
    # Skip frontmatter
    text = _FRONTMATTER_RE.sub("", content)
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_description(content: str) -> str:
    """Extract the first paragraph after the heading."""
    # Skip frontmatter
    text = _FRONTMATTER_RE.sub("", content)
    lines = text.split("\n")
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
