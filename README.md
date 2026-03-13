# skillm

Local-first, offline-capable skill manager for AI coding agents.

Manage a library of reusable skills (instructions, tools, prompts) that any coding agent — Claude Code, Cursor, Codex, OpenClaw — can consume. Think **npm for AI skills**, but your library lives on your machine.

## Why skillm

- **No internet required** — skills are stored locally, not fetched on-demand
- **You own your library** — not dependent on any platform being up
- **Version everything** — every `add` creates a new version (v0.1, v0.2, ...), safe rollback anytime
- **Push/pull sharing** — sync skills with team libraries via `push` and `pull`, just like git
- **Agent-agnostic** — works with Claude Code, Cursor, Codex, OpenClaw, or any markdown-based agent
- **Team-safe** — SSH remotes use file locking, DB snapshots protect against mistakes

## Install

```bash
pip install -e .
```

Requires Python 3.10+.

## Quick Start

### 1. Pull skills and install

```bash
# One-time setup: point to the team library
skillm remote add team /home/prgn_share/skillm

# Pull skills to your local library
skillm pull
# Pulled 5 skills from team (5 new)

# Install into your project
cd your-project/
skillm install my-skill
# Installed my-skill@v0.1 → .claude/skills/
```

That's it. The local library is auto-created on first use. `pull` defaults to the configured remote. `install` auto-creates the agent directory.

```bash
# Other useful commands
skillm list                                  # browse available skills
skillm search "pytest"                       # search by keyword
skillm install my-skill --agent cursor       # install for a different agent
skillm upgrade                               # update all project skills
```

### 2. Manage your local library

Create a skill — just a directory with a `SKILL.md`:

```bash
mkdir my-skill
cat > my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: Help with writing unit tests
tags: [testing, python]
---

# Unit Test Helper

When asked to write tests:
1. Use pytest, not unittest
2. Name test files `test_*.py`
3. Use fixtures for shared setup
EOF
```

Add it to your local library:

```bash
skillm add ./my-skill/                       # v0.1
skillm add ./my-skill/                       # v0.2 (auto-increment)
skillm add ./my-skill/ --major               # v1.0 (major bump)
```

Or import from external sources:

```bash
skillm import owner/repo                     # GitHub
skillm import clawhub:skill-slug             # ClawHub registry
skillm import ./skill.skillpack              # portable archive
```

Manage versions and metadata:

```bash
skillm versions my-skill                     # list all versions
skillm info my-skill                         # show details
skillm rm my-skill --version v0.1            # remove a version
skillm tag my-skill python web               # add tags
skillm update ./my-skill/                    # replace latest version in-place
```

### 3. Push to the remote

```bash
skillm push
# Pushed 3 skills to team (2 new, 1 updated)
```

Only the latest version of each skill is pushed. Version numbers are determined by the remote's own history.

---

## How It Works

```
Library (~/.skillm/)              Project (your-repo/)
├── library.db                    ├── .claude/
├── remotes.toml                  │   ├── skills.json
├── snapshots/                    │   └── skills/
└── skills/                       │       ├── web-scraper/SKILL.md
    ├── web-scraper/v0.1/         │       └── formatter/SKILL.md
    ├── web-scraper/v0.2/         ├── .cursor/skills/  ← other agents
    └── formatter/v1.0/           └── CLAUDE.md  ← auto-injected
```

- **Library** stores all your skills with full version history
- **Project** installs specific skill versions from the library
- **Inject** writes skill references into agent config files

## What is a Skill?

A skill is a directory with a `SKILL.md` file:

```
my-skill/
├── SKILL.md              # Required — agent instructions
├── scripts/              # Optional — helper scripts
└── templates/            # Optional — file templates
```

### SKILL.md Frontmatter

```yaml
---
name: web-scraper                 # skill name (default: directory name)
description: Scrape web pages     # one-line description
author: alice                     # author (default: git config user.name)
tags: [web, scraping, python]     # searchable tags
source: owner/repo                # where it was imported from

requires:                         # environment requirements
  bins: [python3, docker]         # CLI tools (checked via `which`)
  packages: [httpx, click]       # Python packages (checked via importlib)
  python: ">=3.10"               # Python version constraint
  env: [API_KEY, SECRET]         # required environment variables
  platform: [linux, macos]       # supported platforms
---
```

Simple format also works:

```yaml
---
requires: [python3, docker]       # treated as binary requirements
---
```

---

## Features

### Library — Managing Skills

**Add and version:**

```bash
skillm add ./my-skill/                       # creates v0.1
skillm add ./my-skill/                       # creates v0.2 (auto-increment)
skillm add ./my-skill/ --major               # creates v1.0 (major bump)
skillm add ./my-skill/ --version custom-tag  # explicit version string
skillm add ./my-skill/ --name alt-name       # override skill name from SKILL.md
skillm add ./my-skill/ -c coding             # set category on add
```

Every `add` creates a new version. Versions are never overwritten — safe from accidental breakage.

**Update in-place:**

```bash
skillm update ./my-skill/                    # overwrites latest version
skillm update ./my-skill/ --name alt-name    # override skill name
```

Replace the latest version without creating a new one. Useful for fixing typos or small corrections. Errors if the skill doesn't exist — use `add` for new skills.

**Remove:**

```bash
skillm rm my-skill --version v0.1   # remove a specific version
skillm rm my-skill                  # remove skill entirely (all versions)
```

**Browse and search:**

```bash
skillm list                         # all skills, grouped by category
skillm list -c coding               # filter by category
skillm search "pytest"              # full-text search across skill content
skillm info my-skill                # show details, versions, tags, size
skillm versions my-skill            # list all versions with sizes and dates
```

**Organize with categories and tags:**

```bash
skillm categorize my-skill devops   # set or change category
skillm tag my-skill python web      # add tags
skillm untag my-skill web           # remove tags
skillm categories                   # list categories with skill counts
```

**Import from external sources:**

```bash
skillm import owner/repo                     # GitHub repository
skillm import owner/repo/subdir              # GitHub subdirectory
skillm import owner/repo --ref v1.0          # specific git ref (tag, branch)
skillm import owner/repo --token ghp_xxx     # private repo with auth token
skillm import clawhub:slug                   # ClawHub registry
skillm import clawhub:slug@1.0.0 --token xxx # ClawHub specific version with auth
skillm import https://example.com/skill.tar.gz  # URL (tar.gz or zip)
skillm import ./skill.skillpack              # portable archive
skillm import ./path/to/dir                  # local directory
skillm import <source> --name custom-name    # override skill name
```

**Export as portable archives:**

```bash
skillm export my-skill                       # export latest version
skillm export my-skill --version v1.0        # export specific version
skillm export my-skill --output /tmp/        # custom output directory
```

`.skillpack` files are portable tar.gz archives with metadata.

### Project — Installing and Using Skills

**Install:**

```bash
skillm install my-skill                      # install latest version
skillm install my-skill@v0.1                 # install specific version
skillm install my-skill@v0.1 --pin           # pin to this version (skip on upgrade)
skillm install my-skill --agent cursor       # install into .cursor/skills/
skillm install my-skill -r /path/to/project  # install in a specific project dir
```

On install, `skillm` automatically checks the skill's environment requirements and warns about any that aren't met.

**Manage project skills:**

```bash
skillm uninstall my-skill            # remove skill from project
skillm sync                          # install all missing skills from skills.json
skillm upgrade                       # update all skills to latest library versions
skillm upgrade my-skill              # update one skill
skillm enable my-skill               # re-enable a disabled skill
skillm disable my-skill              # hide from agent, keep files
```

All project commands accept `--agent/-a` (claude, cursor, codex, openclaw) and `--project-root/-r` options.

**Inject into agent config:**

```bash
skillm inject                        # auto-detect agent format
skillm inject --format claude        # force CLAUDE.md
skillm inject --format cursor        # force .cursorrules
skillm inject --file ./custom.md     # custom config file path
```

| Agent | Skills directory | Config file |
|-------|-----------------|-------------|
| Claude Code | `.claude/skills/` | `CLAUDE.md` |
| Cursor | `.cursor/skills/` | `.cursorrules` |
| Codex | `.codex/skills/` | `AGENTS.md` |
| OpenClaw | `.openclaw/skills/` | `AGENTS.md` |

Injected content is wrapped in markers (`<!-- skillm:start -->` / `<!-- skillm:end -->`) and cleanly updated on subsequent runs.

**Check environment requirements:**

```bash
skillm check my-skill                # check a library skill
skillm check my-skill --no-scan      # skip auto-detection, check declared only
skillm doctor                        # check all project skills
skillm doctor --no-scan              # check declared requirements only
```

```
my-skill environment check:
  ✓ python3 — Found at /usr/bin/python3
  ✓ pytest — Installed (8.1.0)
  ✗ PROXY_URL — Not set
  2 passed, 1 failed

  Auto-detected (not in frontmatter):
    packages: ['requests']
```

By default, `skillm` auto-scans `SKILL.md` code blocks to detect undeclared requirements — Python imports, CLI tools, pip installs, environment variables. Use `--no-scan` to check only declared frontmatter requirements.

### Sharing — Remotes, Push, and Pull

**Configure remotes:**

```bash
skillm remote add team /home/prgn_share/skillm       # shared path
skillm remote add prod ssh://user@server:/shared/lib  # SSH remote
skillm remote list             # show all remotes, mark active
skillm remote rm old-server    # remove a remote
skillm remote switch team      # change which library is your local/active one
```

**Push and pull:**

```bash
skillm push                    # push to default remote (first non-active)
skillm push team               # push to a specific remote
skillm pull                    # pull from default remote
skillm pull team               # pull from a specific remote
```

If you only have one remote besides your active library, `push`/`pull` use it automatically — no name needed.

All `add`/`rm`/`update` operations work on your local library. Use `push` and `pull` to sync with remotes.

**SSH safety**: writes acquire a remote file lock (`flock`) so multiple team members can safely push to the same library without corrupting the database.

### Operations — Snapshots and Maintenance

**Database snapshots:**

Every write operation auto-snapshots the database. If something goes wrong, roll back instantly.

```bash
skillm library snapshots     # list snapshots with timestamps and sizes
skillm library rollback      # restore the most recent snapshot
skillm library rollback library.db.20260312T103045123456Z  # restore specific
```

Rollback creates a safety snapshot first, so you can undo a rollback too.

Pruning is automatic:
- Snapshots older than **30 days** are removed
- Total snapshot size capped at **100MB**
- At least **10 snapshots** always kept regardless

**Library maintenance:**

```bash
skillm library init                  # initialize local library (auto-runs on first use)
skillm library init --path /custom   # initialize at a custom path
skillm library stats                 # skill count, total size, backend type
skillm library check                 # verify DB matches files on disk
skillm library rebuild               # rebuild DB from skill files (fixes corruption)
skillm library compact               # VACUUM the SQLite database
```

---

## Architecture

```
CLI (Click)
  └─► Core Engine (Library + Project)
        ├─► Storage Backend
        │     ├── LocalBackend    — filesystem (default)
        │     └── SSHBackend      — remote via ssh/scp/rsync + flock
        ├─► Database (SQLite + FTS5)
        ├─► Metadata Parser (YAML frontmatter)
        ├─► Scanner (auto-detect requirements)
        ├─► Checker (verify environment)
        ├─► Importer (GitHub, ClawHub, URL)
        └─► Snapshot Manager
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| CLI | Click |
| Database | SQLite + FTS5 |
| Terminal UI | Rich |
| Config | TOML |
| Metadata | YAML frontmatter (pyyaml) |
| HTTP | httpx |
| Package format | tar.gz (.skillpack) |

## Command Reference

### Library Management

| Command | Description |
|---------|-------------|
| `skillm library init [--path PATH]` | Initialize a new library (default: ~/.skillm) |
| `skillm library stats` | Show library statistics |
| `skillm library rebuild` | Rebuild DB from skill files on disk |
| `skillm library compact` | VACUUM the SQLite database |
| `skillm library check` | Verify DB matches files on disk |
| `skillm library snapshots` | List DB snapshots |
| `skillm library rollback [SNAPSHOT]` | Restore a DB snapshot (default: latest) |

### Skills (Library)

| Command | Description |
|---------|-------------|
| `skillm add <dir> [--name NAME] [--major] [--version VER] [-c CAT]` | Add a skill (creates new version) |
| `skillm update <dir> [--name NAME]` | Replace latest version in-place |
| `skillm rm <name> [--version VER]` | Remove a skill or specific version |
| `skillm info <name>` | Show skill details |
| `skillm list [-c CATEGORY]` | List all skills (optionally filter by category) |
| `skillm search <query>` | Full-text search across skill content |
| `skillm versions <name>` | List all versions with sizes and dates |
| `skillm tag <name> <tags...>` | Add tags |
| `skillm untag <name> <tags...>` | Remove tags |
| `skillm categorize <name> <category>` | Set category |
| `skillm categories` | List categories with skill counts |
| `skillm check <name> [--scan/--no-scan]` | Check skill environment requirements |

### Project

All project commands accept `--agent/-a` (claude, cursor, codex, openclaw) and `--project-root/-r PATH` options.

| Command | Description |
|---------|-------------|
| `skillm install <name[@ver]> [--pin]` | Install skill into project |
| `skillm uninstall <name>` | Remove skill from project |
| `skillm sync` | Install all missing skills from skills.json |
| `skillm upgrade [name]` | Update to latest library versions |
| `skillm enable <name>` | Re-enable a disabled skill |
| `skillm disable <name>` | Hide skill from agent (keep files) |
| `skillm doctor [--scan/--no-scan]` | Check requirements for all project skills |
| `skillm inject [--format FMT] [--file PATH]` | Inject skill references into agent config |

### Import/Export

| Command | Description |
|---------|-------------|
| `skillm import <source> [--name NAME] [--ref REF] [--token TOKEN]` | Import from GitHub/ClawHub/URL/file |
| `skillm export <name> [--version VER] [--output DIR]` | Export as .skillpack archive |

### Remotes & Sync

| Command | Description |
|---------|-------------|
| `skillm remote add <name> <path>` | Add a remote (local path or ssh://...) |
| `skillm remote rm <name>` | Remove a remote |
| `skillm remote switch <name>` | Switch active local library |
| `skillm remote list` | List all remotes, mark active |
| `skillm push [remote]` | Push all skills to remote (default: first non-active) |
| `skillm pull [remote]` | Pull all skills from remote (default: first non-active) |

## License

TBD
