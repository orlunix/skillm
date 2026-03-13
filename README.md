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

### Versioning

Every `add` creates a new minor version. Versions are never overwritten — safe from accidental breakage.

```bash
skillm add ./my-skill/              # v0.1
skillm add ./my-skill/              # v0.2
skillm add ./my-skill/              # v0.3
skillm add ./my-skill/ --major      # v1.0 (major bump)
skillm add ./my-skill/              # v1.1
skillm add ./my-skill/ --version custom-tag  # explicit version string
```

List and manage versions:

```bash
skillm versions my-skill            # list all versions
skillm rm my-skill --version v0.1   # remove a specific version
skillm rm my-skill                  # remove skill entirely
```

### Categories and Tags

Organize skills however you want:

```bash
skillm add ./my-skill/ -c coding    # set category on add
skillm categorize my-skill devops   # change category later
skillm tag my-skill python web      # add tags
skillm untag my-skill web           # remove tags
skillm categories                   # list categories with counts
skillm list -c coding               # filter by category
```

### Environment Verification

Check if your machine has what a skill needs:

```bash
skillm check my-skill
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

`skillm` auto-scans `SKILL.md` code blocks to detect undeclared requirements — Python imports, CLI tools, pip installs, environment variables.

Check all project skills at once:

```bash
skillm doctor
```

### Remote Libraries

Manage remote libraries for sharing with your team:

```bash
skillm remote add team /home/prgn_share/skillm          # shared path
skillm remote add team ssh://user@server:/shared/lib     # SSH remote
skillm remote add nas /mnt/nas/skillm                    # network mount

skillm remote list             # show all remotes
skillm remote rm old-server    # remove a remote

# Push/pull between local and remote
skillm push team               # sync local → remote
skillm pull team               # sync remote → local
```

All `add`/`rm`/`update` operations work on your local library. Use `push` and `pull` to sync with remotes.

**SSH safety**: writes acquire a remote file lock (`flock`) so multiple team members can safely push to the same library without corrupting the database.

### Database Snapshots

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

### Agent Config Injection

```bash
skillm inject                        # auto-detect agent format
skillm inject --format claude        # force CLAUDE.md
skillm inject --format cursor        # force .cursorrules
skillm inject --file ./custom.md     # custom file path
```

Supported agents:

| Agent | Skills directory | Config file |
|-------|-----------------|-------------|
| Claude Code | `.claude/skills/` | `CLAUDE.md` |
| Cursor | `.cursor/skills/` | `.cursorrules` |
| Codex | `.codex/skills/` | `AGENTS.md` |
| OpenClaw | `.openclaw/skills/` | `AGENTS.md` |

Use `--agent` on any project command to target a specific agent (default: claude).

Injected content is wrapped in markers (`<!-- skillm:start -->` / `<!-- skillm:end -->`) and cleanly updated on subsequent runs.

### Enable/Disable Skills

Temporarily hide a skill from the agent without removing it:

```bash
skillm disable my-skill     # hidden from agent, files kept
skillm enable my-skill      # visible again
```

### Export and Share

```bash
skillm export my-skill                    # creates my-skill-v0.1.skillpack
skillm export my-skill --version v1.0     # specific version
skillm import ./my-skill-v0.1.skillpack   # import on another machine
```

`.skillpack` files are portable tar.gz archives with metadata.

### Library Maintenance

```bash
skillm library stats         # skill count, total size, backend type
skillm library check         # verify DB matches files on disk
skillm library rebuild       # rebuild DB from skill files (fixes corruption)
skillm library compact       # VACUUM the SQLite database
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
| `skillm library init` | Initialize a new library |
| `skillm library stats` | Show library statistics |
| `skillm library rebuild` | Rebuild DB from disk |
| `skillm library compact` | VACUUM the database |
| `skillm library check` | Verify DB integrity |
| `skillm library snapshots` | List DB snapshots |
| `skillm library rollback [name]` | Restore a DB snapshot |

### Skills (Library)

| Command | Description |
|---------|-------------|
| `skillm add <dir>` | Add a skill (creates new version) |
| `skillm add <dir> --major` | Add with major version bump |
| `skillm update <dir>` | Replace latest version in-place |
| `skillm rm <name>` | Remove a skill |
| `skillm rm <name> --version v0.1` | Remove a specific version |
| `skillm info <name>` | Show skill details |
| `skillm list` | List all skills |
| `skillm list -c <category>` | Filter by category |
| `skillm search <query>` | Full-text search |
| `skillm versions <name>` | List all versions |
| `skillm tag <name> <tags...>` | Add tags |
| `skillm untag <name> <tags...>` | Remove tags |
| `skillm categorize <name> <cat>` | Set category |
| `skillm categories` | List categories with counts |
| `skillm check <name>` | Check skill requirements |

### Project

All project commands accept `--agent/-a` (claude, cursor, codex, openclaw) and `--project-root/-r` options.

| Command | Description |
|---------|-------------|
| `skillm install <name>` | Install skill into project |
| `skillm install <name>@v0.1 --pin` | Install and pin version |
| `skillm install <name> -a cursor` | Install for a specific agent |
| `skillm install <name> -r /path` | Install in a specific project |
| `skillm uninstall <name>` | Remove skill from project |
| `skillm sync` | Install missing skills |
| `skillm upgrade [name]` | Update to latest versions |
| `skillm enable <name>` | Enable a disabled skill |
| `skillm disable <name>` | Disable a skill |
| `skillm doctor` | Check all project skills |
| `skillm inject` | Inject into agent config |

### Import/Export

| Command | Description |
|---------|-------------|
| `skillm import <source>` | Import from GitHub/ClawHub/URL/file |
| `skillm export <name>` | Export as .skillpack |

### Remotes & Sync

| Command | Description |
|---------|-------------|
| `skillm remote add <name> <path>` | Add a remote library |
| `skillm remote rm <name>` | Remove a remote |
| `skillm remote switch <name>` | Switch active local library |
| `skillm remote list` | List all remotes |
| `skillm push <remote>` | Push all skills to remote |
| `skillm pull <remote>` | Pull all skills from remote |

## License

TBD
