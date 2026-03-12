# SKILL.md Frontmatter Specification

> Defines the YAML frontmatter format for skillm SKILL.md files.

**Version:** 1.0
**Status:** Draft

---

## Format

SKILL.md supports two metadata formats. Both are optional — skillm works without any metadata.

### 1. YAML Frontmatter (preferred)

```markdown
---
name: defuddle
description: Extract clean text from web pages
author: joeseesun
tags: [scraping, html, text-extraction]
source: joeseesun/defuddle
requires: [python3, httpx]
---

# Defuddle

Extract clean, readable text from web pages...
```

### 2. HTML Comment Block (legacy, still supported)

```markdown
# Defuddle

Extract clean, readable text from web pages...

<!-- skillm:meta
tags: scraping, html, text-extraction
author: joeseesun
requires: python3, httpx
-->
```

### Precedence

When both formats are present, YAML frontmatter wins for all fields.

---

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | No | Skill name. Fallback: directory name |
| `description` | string | No | One-line description. Fallback: first paragraph after heading |
| `author` | string | No | Author name. Fallback: git config user.name |
| `tags` | list | No | Categorization tags for search |
| `source` | string | No | Origin — e.g. `owner/repo`, `clawhub:slug`, URL |
| `requires` | list | No | Runtime dependencies (binaries, packages) |

### ClawHub Compatibility

skillm reads ClawHub-style frontmatter transparently:

```yaml
---
name: cam
description: Manage coding agents
metadata:
  openclaw:
    emoji: "🎯"
    requires: { anyBins: ["cam"] }
---
```

When `metadata.openclaw.requires.anyBins` is present and top-level `requires` is not, skillm maps it automatically.

---

## Import Sources

skillm supports importing skills from multiple sources via `skillm import <source>`.

### Source Detection

| Source pattern | Backend | Example |
|----------------|---------|---------|
| `./path/to/dir` | Local directory | `skillm import ./my-skill/` |
| `*.skillpack` | Skillpack archive | `skillm import ./skill.skillpack` |
| `owner/repo` | GitHub | `skillm import joeseesun/defuddle` |
| `owner/repo/subpath` | GitHub subdirectory | `skillm import owner/repo/skills/tool` |
| `clawhub:slug` | ClawHub registry | `skillm import clawhub:defuddle` |
| `https://...` | URL (tar.gz or zip) | `skillm import https://example.com/skill.tar.gz` |

### GitHub Import

One-time download. No ongoing dependency on GitHub.

```bash
skillm import joeseesun/defuddle              # Default branch, repo root
skillm import joeseesun/defuddle/skills/web   # Subdirectory
skillm import joeseesun/defuddle --ref v2.0   # Specific tag/branch
skillm import joeseesun/defuddle --name my-name
```

**Flow:**
1. Download tarball via GitHub API (`/repos/{owner}/{repo}/tarball/{ref}`)
2. Extract to temp directory
3. Locate SKILL.md (repo root or subpath)
4. Publish to local library
5. Record `source: joeseesun/defuddle` in metadata

### ClawHub Import

One-time download from clawhub.ai registry.

```bash
skillm import clawhub:defuddle               # Latest version
skillm import clawhub:defuddle@1.0.0         # Specific version
```

**Flow:**
1. Resolve skill via ClawHub API (`GET /api/v1/skills/{slug}`)
2. Download ZIP via (`GET /api/v1/download?slug={slug}&version={ver}`)
3. Extract to temp directory
4. Publish to local library
5. Record `source: clawhub:defuddle@1.0.0` in metadata

### URL Import

Direct download of a tar.gz or zip archive.

```bash
skillm import https://example.com/skill.tar.gz
skillm import https://example.com/skill.zip --name custom
```

**Flow:**
1. Download archive via httpx
2. Detect format (tar.gz or zip)
3. Extract, locate SKILL.md
4. Publish to local library
5. Record `source: <url>` in metadata
