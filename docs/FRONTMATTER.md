# SKILL.md Frontmatter Specification

> Defines the YAML frontmatter format for skillm SKILL.md files.

**Version:** 2.0
**Status:** Draft

---

## Format

SKILL.md supports multiple input formats. On publish, all formats are
normalized to canonical YAML frontmatter (format 1 below).

### 1. YAML Frontmatter (canonical)

```markdown
---
name: defuddle
description: Extract clean text from web pages
author: joeseesun
tags: [scraping, html, text-extraction]
category: web
source: joeseesun/defuddle
requires:
  tools: [python3, curl]
  env: [API_KEY]
  skills: []
---

# Defuddle

Extract clean, readable text from web pages...
```

### 2. HTML Comment Block (legacy, accepted on input)

```markdown
# Defuddle

Extract clean, readable text from web pages...

<!-- skillm:meta
tags: scraping, html, text-extraction
author: joeseesun
requires: python3, curl
-->
```

On publish, this is converted to format 1. The comment block is removed.

### 3. ClawHub Compatibility (accepted on input)

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

On publish, `metadata.openclaw.requires.anyBins` is mapped to
`requires.tools` and the `metadata` block is dropped.

### Precedence

When multiple formats are present, YAML frontmatter wins for all fields.

---

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | No | Skill name. Fallback: directory name |
| `description` | string | No | One-line description. Fallback: first paragraph after heading |
| `author` | string | No | Author name |
| `tags` | list | No | Categorization tags for search |
| `category` | string | No | Skill category (e.g. `web`, `devops`, `data`) |
| `source` | string | No | Origin — e.g. `owner/repo`, `clawhub:slug`, URL |
| `requires` | object | No | Runtime prerequisites (see below) |

### `requires` field

`requires` declares **preconditions for the skill to run**.
Language-specific package dependencies (pip, npm) live in their own
standard files inside the skill directory.

```yaml
requires:
  tools: [python3, curl, jq]
  env: [API_KEY, DATABASE_URL]
  skills: [git-workflow, code-review]
```

| Sub-field | Type | Description | Auto-detect? | Check method |
|-----------|------|-------------|--------------|--------------|
| `tools` | list | System CLI binaries | Yes — scan code blocks | `which` |
| `env` | list | Environment variables | Yes — scan `$VAR` references | `os.environ` |
| `skills` | list | Other skill dependencies | No — author declares | Library lookup |

#### Legacy requires format

Flat list format from v1 is accepted on input and mapped to `tools`:

```yaml
# v1 input
requires: [python3, curl]

# normalized to
requires:
  tools: [python3, curl]
  env: []
  skills: []
```

#### Script dependencies

If a skill contains scripts, their package dependencies **must** be
declared in the corresponding ecosystem file at the skill root:

| Script type | Dependency file | Required when |
|---|---|---|
| `.py` files | `requirements.txt` | Any `.py` file has non-stdlib imports |
| `.js`/`.ts` files | `package.json` | Any `.js`/`.ts` file has `require()` or `import` |
| `.sh` files | (none) | Binaries declared in `requires.tools` |

Example:

```
my-skill/
├── SKILL.md               # requires: {tools, env, skills}
├── requirements.txt       # python packages for scripts/
├── scripts/
│   ├── scrape.py          # import httpx → must be in requirements.txt
│   └── parse.sh           # uses jq → must be in requires.tools
└── templates/
    └── config.yaml
```

On publish, skillm scans script files and:
1. Warns if `.py` files import packages not listed in `requirements.txt`
2. Warns if `requirements.txt` is missing but `.py` files have non-stdlib imports
3. Warns if `.js` files exist but `package.json` is missing
4. Auto-detects binary usage in `.sh` files and merges into `requires.tools`

---

## Normalization

On `skillm add` (publish), the following normalization is applied:

1. Read metadata from any supported input format
2. Scan skill content for undeclared `tools` and `env` dependencies
3. Merge detected dependencies with declared ones
4. Rewrite SKILL.md with canonical YAML frontmatter
5. Remove legacy comment blocks (`<!-- skillm:meta -->`)
6. Store the normalized version in git

After normalization, every SKILL.md in the library has consistent
YAML frontmatter. This ensures `rebuild()` can fully reconstruct
the SQLite index from SKILL.md files alone.

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
4. Publish to local library (normalization applied)
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
4. Publish to local library (normalization applied)
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
4. Publish to local library (normalization applied)
5. Record `source: <url>` in metadata
