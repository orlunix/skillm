# skillm

Local-first, offline-capable skill manager for AI coding agents.

Manage a library of reusable skills (instructions, tools, prompts) that any coding agent — Claude Code, Cursor, Codex, OpenClaw — can consume. Think **npm for AI skills**, but your library lives on your machine.

## Install

```bash
pip install -e .
```

Requires Python 3.10+.

## Quick Start

```bash
# 1. Initialize your library
skillm library init

# 2. Add a skill from a local directory
skillm add ./my-skill/

# 3. Set up your project
cd your-project/
skillm init

# 4. Install a skill into the project
skillm install my-skill

# 5. Inject skill references into your agent config
skillm inject
```

That's it. Your agent (Claude Code, Cursor, etc.) now sees the skill instructions.

## What is a Skill?

A skill is a directory with a `SKILL.md` file that tells an AI coding agent how to do something:

```
my-skill/
├── SKILL.md              # Required — agent instructions
├── scripts/              # Optional — helper scripts
└── templates/            # Optional — file templates
```

`SKILL.md` can include YAML frontmatter for metadata:

```markdown
---
name: web-scraper
description: Scrape web pages with error handling
author: alice
tags: [web, scraping, python]
requires:
  bins: [python3]
  packages: [httpx, beautifulsoup4]
  env: [PROXY_URL]
---

# Web Scraper

Instructions for the agent go here...
```

## How It Works

```
Library (~/.skillm/)              Project (your-repo/)
├── library.db                    ├── skills.json
├── remotes.toml                  ├── .skills/
├── snapshots/                    │   ├── web-scraper/SKILL.md
└── skills/                       │   └── formatter/SKILL.md
    ├── web-scraper/v1/           └── CLAUDE.md  ← auto-injected
    └── formatter/v2/
```

- **Library** stores all your skills with version history
- **Project** installs specific skills from the library
- **Inject** writes skill references into agent config files

---

## Features

### Managing Skills in the Library

#### Add a skill

```bash
skillm add ./my-skill/
```

If the skill is new, it creates `v1`. If the skill already exists, it **updates the latest version in-place** (no version bump).

To force a new version:

```bash
skillm add ./my-skill/ --new-version    # creates v2, v3, etc.
skillm add ./my-skill/ --version 2.0    # explicit version string
```

Set a category on add:

```bash
skillm add ./my-skill/ -c coding
```

#### Remove a skill

```bash
skillm rm my-skill               # remove skill entirely
skillm rm my-skill --version v1  # remove only v1
```

#### Browse the library

```bash
skillm list                      # all skills, grouped by category
skillm list -c coding            # filter by category
skillm info my-skill             # detailed info for one skill
skillm versions my-skill         # list all versions
skillm search "scraping"         # full-text search
skillm categories                # show categories with counts
```

#### Tags and categories

```bash
skillm tag my-skill python web     # add tags
skillm untag my-skill web          # remove a tag
skillm categorize my-skill coding  # set category
```

### Importing Skills from External Sources

```bash
# From GitHub (downloads tarball, no git clone needed)
skillm import owner/repo
skillm import owner/repo/subdirectory
skillm import owner/repo --ref v1.0.0

# From ClawHub registry
skillm import clawhub:skill-slug
skillm import clawhub:skill-slug@1.0.0

# From a URL (tar.gz or zip)
skillm import https://example.com/skill.tar.gz

# From a .skillpack archive
skillm import ./my-skill.skillpack

# From a local directory (same as `add`)
skillm import ./path/to/skill/
```

### Using Skills in a Project

#### Set up a project

```bash
cd your-project/
skillm init
```

This creates `skills.json` and a `.skills/` directory (auto-added to `.gitignore`).

#### Install skills

```bash
skillm install my-skill             # latest version
skillm install my-skill@v1 --pin    # pin to v1
```

`install` copies skill files from the library into `.skills/my-skill/` and records the version in `skills.json`.

#### Uninstall

```bash
skillm uninstall my-skill
```

#### Sync and upgrade

```bash
skillm sync                          # install any skills in skills.json that are missing
skillm upgrade                       # update all skills to latest library versions
skillm upgrade my-skill              # update one skill
```

#### Enable/disable

```bash
skillm disable my-skill              # hide from agent but keep files
skillm enable my-skill               # re-enable
```

### Agent Config Injection

```bash
skillm inject                        # auto-detect agent format
skillm inject --format claude        # force CLAUDE.md
skillm inject --format cursor        # force .cursorrules
skillm inject --file ./custom.md     # custom file path
```

Supported agents:
- **Claude Code** → `CLAUDE.md`
- **Cursor** → `.cursorrules`
- **Codex** → `AGENTS.md`
- **OpenClaw** → `AGENTS.md`

Injected content is wrapped in markers (`<!-- skillm:start -->` / `<!-- skillm:end -->`) so it can be cleanly updated on subsequent runs.

### Environment Verification

Before installing, `skillm` can check if your machine has what the skill needs.

#### Check a single skill

```bash
skillm check my-skill
```

Output:

```
my-skill environment check:
  ✓ python3 — Found at /usr/bin/python3
  ✓ httpx — Installed (0.27.0)
  ✗ PROXY_URL — Not set
  2 passed, 1 failed

  Auto-detected (not in frontmatter):
    packages: ['beautifulsoup4']
```

The `--scan` flag (on by default) auto-scans `SKILL.md` code blocks to detect requirements that aren't declared in frontmatter — Python imports, CLI tools, pip installs, environment variables.

#### Check all project skills

```bash
skillm doctor
```

Runs `check` on every installed skill in the project.

### Auto-Scanning Requirements

When you `add` a skill, `skillm` scans its `SKILL.md` and warns about undeclared requirements:

```
Detected requirements not in frontmatter:
  bins: ['docker', 'curl']
  packages: ['requests']
  env: ['API_KEY']
Consider adding these to your SKILL.md frontmatter.
Added my-skill@v1 to library
```

What it detects:
- **Binaries**: CLI tools used in code blocks (`docker`, `git`, `curl`, etc.)
- **Python packages**: `import` statements and `pip install` commands
- **Environment variables**: `os.environ`, `os.getenv`, `$VAR`, `${VAR}`
- **Node.js**: `npm install` / `bun install` → suggests `node` as a dependency

### Remote Libraries

Instead of one local library, you can manage multiple named libraries — local paths or SSH remotes — and switch between them.

#### Add remotes

```bash
skillm remote add local ~/.skillm                      # local path
skillm remote add team ssh://user@server:/shared/lib    # SSH remote
skillm remote add nas /mnt/nas/skillm                   # network mount
```

#### Switch the active library

```bash
skillm remote switch team
```

Now **all commands** (`add`, `rm`, `install`, `list`, `search`, etc.) operate on the team library.

```bash
skillm remote switch local     # back to local
```

#### List and remove

```bash
skillm remote list             # show all, mark active
skillm remote rm team          # remove a remote
```

#### How SSH works

For SSH remotes, `skillm`:
1. Downloads the SQLite DB for reads (list, search, info)
2. Acquires a **remote file lock** (`flock`) before any write
3. Uploads files and DB after the write
4. Releases the lock

Multiple users can safely use the same SSH remote — writes are serialized via `flock`, so no database corruption.

### Database Snapshots

Every write operation (`add`, `rm`, `update`) auto-snapshots the database before making changes. If something goes wrong, you can roll back.

#### List snapshots

```bash
skillm library snapshots
```

```
  library.db.20260312T103045123456Z  2026-03-12 10:30:45 UTC  (48.0 KB) ← latest
  library.db.20260312T094512654321Z  2026-03-12 09:45:12 UTC  (44.0 KB)
```

#### Rollback

```bash
skillm library rollback                                          # restore latest snapshot
skillm library rollback library.db.20260312T094512654321Z        # restore specific one
```

Rollback itself creates a safety snapshot of the current state, so you can undo a rollback.

Last 10 snapshots are kept; older ones are auto-pruned.

### Export and Share

```bash
# Export as a portable archive
skillm export my-skill                    # creates my-skill-v1.skillpack
skillm export my-skill --version v2       # specific version

# Import on another machine
skillm import ./my-skill-v1.skillpack
```

`.skillpack` files are tar.gz archives with metadata — portable across machines.

### Library Maintenance

```bash
skillm library stats             # skill count, total size, backend type
skillm library check             # verify DB matches files on disk
skillm library rebuild           # rebuild DB from skill files (fixes corruption)
skillm library compact           # VACUUM the SQLite database
```

---

## SKILL.md Frontmatter Reference

```yaml
---
name: my-skill                    # skill name (default: directory name)
description: What this skill does # one-line description
author: your-name                 # author (default: git config user.name)
tags: [python, web, scraping]     # searchable tags
source: owner/repo                # where it was imported from

requires:                         # environment requirements
  bins: [python3, docker]         # CLI tools (checked via `which`)
  packages: [httpx, click]       # Python packages (checked via importlib)
  python: ">=3.10"               # Python version constraint
  env: [API_KEY, SECRET]         # required environment variables
  platform: [linux, macos]       # supported platforms
---
```

Flat list format also works for simple cases:

```yaml
---
requires: [python3, docker]       # treated as bins
---
```

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

| Command | Description |
|---------|-------------|
| `skillm library init` | Initialize a new library |
| `skillm library stats` | Show library statistics |
| `skillm library rebuild` | Rebuild DB from disk |
| `skillm library compact` | VACUUM the database |
| `skillm library check` | Verify DB integrity |
| `skillm library snapshots` | List DB snapshots |
| `skillm library rollback` | Restore a DB snapshot |
| `skillm add <dir>` | Add/update a skill in the library |
| `skillm rm <name>` | Remove a skill from the library |
| `skillm info <name>` | Show skill details |
| `skillm list` | List all skills |
| `skillm search <query>` | Full-text search |
| `skillm versions <name>` | List skill versions |
| `skillm tag <name> <tags>` | Add tags |
| `skillm untag <name> <tags>` | Remove tags |
| `skillm categorize <name> <cat>` | Set category |
| `skillm categories` | List categories |
| `skillm import <source>` | Import from GitHub/ClawHub/URL/file |
| `skillm export <name>` | Export as .skillpack |
| `skillm init` | Set up project for skills |
| `skillm install <name>` | Install skill into project |
| `skillm uninstall <name>` | Remove skill from project |
| `skillm sync` | Install missing skills |
| `skillm upgrade` | Update to latest versions |
| `skillm enable <name>` | Enable a disabled skill |
| `skillm disable <name>` | Disable a skill |
| `skillm check <name>` | Check skill requirements |
| `skillm doctor` | Check all project skills |
| `skillm inject` | Inject into agent config |
| `skillm remote add` | Add a remote library |
| `skillm remote rm` | Remove a remote |
| `skillm remote switch` | Switch active remote |
| `skillm remote list` | List remotes |

## License

TBD
