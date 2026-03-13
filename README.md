# skillm

Local-first, offline-capable skill manager for AI coding agents.

Manage a library of reusable skills (instructions, tools, prompts) that any coding agent — Claude Code, Cursor, Codex, OpenClaw — can consume. Think **npm for AI skills**, but your library lives on your machine.

## Why skillm

- **No internet required** — skills are stored locally, not fetched on-demand
- **You own your library** — not dependent on any platform being up
- **Version everything** — every `add` creates a new version (v0.1, v0.2, ...), safe rollback anytime
- **Multi-remote** — switch between local, SSH, or NAS libraries with one command
- **Agent-agnostic** — works with Claude Code, Cursor, Codex, OpenClaw, or any markdown-based agent
- **Team-safe** — SSH remotes use file locking, DB snapshots protect against mistakes

## Install

```bash
pip install -e .
```

Requires Python 3.10+.

## Quick Start

### 1. Initialize your library

```bash
skillm library init
```

This creates `~/.skillm/` with a SQLite database and skill storage.

### 2. Create a skill

A skill is just a directory with a `SKILL.md` file:

```bash
mkdir my-skill
cat > my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: Help with writing unit tests
author: alice
tags: [testing, python]
requires:
  bins: [python3]
  packages: [pytest]
---

# Unit Test Helper

When asked to write tests, follow these guidelines:

1. Use pytest, not unittest
2. Name test files `test_*.py`
3. Use fixtures for shared setup
4. Aim for one assertion per test
EOF
```

### 3. Add the skill to your library

```bash
skillm add ./my-skill/
# Added my-skill@v0.1

# Edit the skill and add again — creates v0.2 automatically
skillm add ./my-skill/
# Added my-skill@v0.2

# Major version bump when the skill changes significantly
skillm add ./my-skill/ --major
# Added my-skill@v1.0
```

### 4. Browse your library

```bash
# List all skills, grouped by category
skillm list

# Search across all skill content
skillm search "pytest"

# See details for one skill
skillm info my-skill

# See all versions
skillm versions my-skill
```

### 5. Use skills in a project

```bash
cd your-project/

# Initialize project for skills
skillm init

# Install a skill from the library
skillm install my-skill

# Install a specific version
skillm install my-skill@v0.1 --pin

# Inject skill references into your agent config
skillm inject
```

After `inject`, your agent config (`CLAUDE.md`, `.cursorrules`, etc.) contains references to the installed skills. Your AI agent now follows those instructions.

### 6. Keep things up to date

```bash
# Update all project skills to latest library versions
skillm upgrade

# Or update just one
skillm upgrade my-skill

# Check what skills a project uses
skillm doctor
```

### 7. Import skills from external sources

```bash
# From GitHub
skillm import owner/repo
skillm import owner/repo/subdirectory

# From ClawHub registry
skillm import clawhub:skill-slug

# From a URL
skillm import https://example.com/skill.tar.gz

# From a .skillpack archive (portable sharing)
skillm import ./skill.skillpack
```

### 8. Share skills with your team

```bash
# Set up a shared remote library over SSH
skillm remote add team ssh://user@server:/shared/skillm
skillm remote switch team

# Now all commands operate on the team library
skillm add ./my-skill/       # adds to team library
skillm list                   # lists team skills

# Switch back to personal library
skillm remote switch local
```

---

## How It Works

```
Library (~/.skillm/)              Project (your-repo/)
├── library.db                    ├── skills.json
├── remotes.toml                  ├── .skills/
├── snapshots/                    │   ├── web-scraper/SKILL.md
└── skills/                       │   └── formatter/SKILL.md
    ├── web-scraper/v0.1/         └── CLAUDE.md  ← auto-injected
    ├── web-scraper/v0.2/
    └── formatter/v1.0/
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

Manage multiple libraries — local, SSH, or network mount:

```bash
skillm remote add local ~/.skillm                      # local (default)
skillm remote add team ssh://user@server:/shared/lib    # SSH remote
skillm remote add nas /mnt/nas/skillm                   # network mount

skillm remote switch team      # all commands now hit team library
skillm remote list             # show all, mark active
skillm remote switch local     # back to local
skillm remote rm old-server    # remove a remote
```

**SSH safety**: writes acquire a remote file lock (`flock`) so multiple team members can safely use the same library without corrupting the database.

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

| Agent | Config file |
|-------|-------------|
| Claude Code | `CLAUDE.md` |
| Cursor | `.cursorrules` |
| Codex | `AGENTS.md` |
| OpenClaw | `AGENTS.md` |

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

| Command | Description |
|---------|-------------|
| `skillm init` | Initialize project for skills |
| `skillm install <name>` | Install skill into project |
| `skillm install <name>@v0.1 --pin` | Install and pin version |
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

### Remotes

| Command | Description |
|---------|-------------|
| `skillm remote add <name> <path>` | Add a remote library |
| `skillm remote rm <name>` | Remove a remote |
| `skillm remote switch <name>` | Switch active remote |
| `skillm remote list` | List all remotes |

## License

TBD
