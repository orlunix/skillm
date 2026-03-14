# skillm

Git-backed skill manager for AI coding agents.

Manage reusable skills (instructions, tools, prompts) for Claude Code, Cursor, Codex, or OpenClaw. Skills live in git repos. skillm wraps git — you never touch it directly. Think **npm for AI skills**, backed by git.

## Why skillm

- **Git is the backend** — versioning, history, sync, and diff come free
- **Multi-source** — pull skills from team repos, personal repos, and remote servers
- **Version = git tag** — `my-skill/v1.0`, `my-skill/v1.1`, etc.
- **Lock files** — `skills.lock` pins exact versions and integrity hashes
- **Agent-agnostic** — works with Claude Code, Cursor, Codex, OpenClaw
- **Cache is disposable** — SQLite index rebuilt from git in seconds

## Install

```bash
pip install -e .
```

Requires Python 3.10+ and git.

## Quick Start

### 1. Set up a source

A source is a git repo that holds skills. Each skill is a subdirectory with a `SKILL.md`.

```bash
# Initialize a new source (creates a git repo)
skillm source init infra /home/prgn_share/skills/infra

# Or add an existing git repo as a source
skillm source add team ssh://git@server:/opt/skills/team.git
```

### 2. Create and add a skill

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

# Add to source (git commit)
skillm add ./my-skill/
# Added my-skill to source 'infra'

# Create a version (git tag)
skillm publish my-skill
# Published my-skill@v0.1
```

### 3. Install into your project

```bash
cd your-project/
skillm install my-skill
# Installed my-skill@v0.1 → .claude/skills/

# Or install a specific version
skillm install my-skill@v0.1 --pin
```

### 4. Sync with your team

```bash
skillm push              # git push --tags
skillm pull              # git pull + rebuild cache
```

That's it. Your project now has:
```
your-project/
├── .claude/
│   ├── skills.json      # manifest
│   ├── skills.lock      # pinned versions + integrity
│   └── skills/
│       └── my-skill/
│           └── SKILL.md
└── CLAUDE.md            # (use `skillm inject` to auto-update)
```

---

## Architecture

```
┌───────────────────────────────────────────────────┐
│                    skillm CLI                      │
├──────────┬──────────┬──────────┬─────────────────┤
│  source  │ install  │  inject  │     doctor      │
│  add     │ upgrade  │  search  │     check       │
│  publish │  sync    │  list    │     cache       │
├──────────┴──────────┴──────────┴─────────────────┤
│             SourceManager (core.py)               │
│             Index Cache (SQLite)                  │
├──────────┬────────────────────┬──────────────────┤
│ source:  │    source:          │   source:        │
│ personal │    infra (git)      │   ai (git)       │
│ ~/.skillm│    /prgn_share/     │   ssh://...      │
└──────────┴────────────────────┴──────────────────┘
                      │
                      ▼
              Your Project
              ├── .claude/skills.json
              ├── .claude/skills.lock
              ├── .claude/skills/
              └── CLAUDE.md
```

Each source is a git repo. Skills are subdirectories:
```
/home/prgn_share/skills/infra/     ← git repo
├── tree-setup/SKILL.md
├── run-regression/SKILL.md
├── p4-submit/SKILL.md
└── .git/
```

Version = git tag: `tree-setup/v1.0`, `tree-setup/v1.1`.

## Config: `~/.skillm/sources.toml`

```toml
[settings]
cache_dir = "~/.skillm/cache"
default_source = "infra"

[[sources]]
name = "infra"
url = "/home/prgn_share/skills/infra"
priority = 10          # lower = higher priority

[[sources]]
name = "ai"
url = "ssh://git@server:/opt/skills/ai.git"
priority = 20

[[sources]]
name = "personal"
url = "~/.skillm/personal"
priority = 30
```

When a skill exists in multiple sources, the highest-priority source wins.

---

## What is a Skill?

A directory with a `SKILL.md`:

```
my-skill/
├── SKILL.md              # Required — agent instructions
├── scripts/              # Optional — helper scripts
└── templates/            # Optional — file templates
```

### SKILL.md Frontmatter

```yaml
---
name: web-scraper
description: Scrape web pages cleanly
author: alice
tags: [web, scraping, python]
requires:
  bins: [python3, docker]
  packages: [httpx, click]
  python: ">=3.10"
  env: [API_KEY]
  platform: [linux, macos]
---

# Web Scraper

Instructions for the AI agent...
```

---

## Command Reference

### Source Management

| Command | Description |
|---------|-------------|
| `skillm source init NAME PATH` | Initialize a new source (creates git repo) |
| `skillm source add NAME URL [--priority N]` | Add an existing source |
| `skillm source rm NAME` | Remove a source (keeps the git repo) |
| `skillm source list` | List all sources |
| `skillm source default NAME` | Set default source |

### Skills

| Command | Description |
|---------|-------------|
| `skillm add <dir> [--source S] [--message M] [--name N] [-c CAT]` | Add skill to source (git commit) |
| `skillm publish <name> [--major] [--source S]` | Create version tag (git tag) |
| `skillm rm <name> [--version V] [--source S]` | Remove skill or version |
| `skillm info <name>` | Show skill details |
| `skillm list [-c CAT] [--source S]` | List skills |
| `skillm search <query>` | Search across all sources |
| `skillm versions <name>` | List all versions |
| `skillm tag <name> <tags...>` | Add tags |
| `skillm untag <name> <tags...>` | Remove tags |
| `skillm categorize <name> <cat>` | Set category |
| `skillm categories` | List categories with counts |
| `skillm check <name> [--scan/--no-scan]` | Check environment requirements |

### Git Operations

| Command | Description |
|---------|-------------|
| `skillm push [SOURCE]` | git push --tags |
| `skillm pull [SOURCE]` | git pull + rebuild cache |
| `skillm log <name>` | git log for a skill |
| `skillm diff <name>` | Uncommitted changes for a skill |

### Project

All accept `--agent/-a` (claude, cursor, codex, openclaw) and `--project-root/-r`.

| Command | Description |
|---------|-------------|
| `skillm install <name[@ver]> [--pin] [--source S]` | Install skill into project |
| `skillm uninstall <name>` | Remove from project |
| `skillm sync` | Install missing skills from skills.json |
| `skillm upgrade [name]` | Update to latest versions |
| `skillm enable <name>` | Re-enable a disabled skill |
| `skillm disable <name>` | Hide from agent, keep files |
| `skillm doctor` | Check all project skills |
| `skillm inject [--format F]` | Inject into agent config |

### Cache & Migration

| Command | Description |
|---------|-------------|
| `skillm cache rebuild [--source S]` | Rebuild SQLite index from git |
| `skillm cache stats` | Show cache statistics |
| `skillm migrate` | Migrate from v1 config to v2 |

### Import/Export

| Command | Description |
|---------|-------------|
| `skillm import <src> [--source S] [--name N] [--ref R] [--token T]` | Import from GitHub/ClawHub/URL/file |
| `skillm export <name> [--version V] [--output DIR]` | Export as .skillpack archive |

---

## Key Workflows

### Add → Publish → Push

```bash
skillm add ./my-skill/ --source infra    # copies to repo, git commit
skillm publish my-skill                   # creates git tag my-skill/v0.1
skillm push                               # git push --tags
```

### Pull → Install → Upgrade

```bash
skillm pull                               # git pull, rebuild cache
skillm install tree-setup@v1.2            # extract at tag, copy to project
skillm upgrade                            # update all to latest tags
```

### Multi-source priority

```bash
skillm source add infra /shared/skills --priority 10
skillm source add personal ~/.skillm/mine --priority 30

# `skillm install deploy` picks infra's version (priority 10 < 30)
# `skillm install deploy --source personal` forces personal
```

## Migrating from v1

If you have an existing skillm v1 setup (`config.toml` + `remotes.toml`):

```bash
skillm migrate
# Migrated to sources.toml format.
#   Source: local → /home/user/.skillm
#   Source: team → /home/prgn_share/skillm
```

This converts your remotes into sources. Your existing skill files in the source directories are preserved — run `skillm cache rebuild` to index them.

## License

TBD
