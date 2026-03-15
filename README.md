# skillm

Git-backed skill manager for AI coding agents.

Manage reusable skills (instructions, tools, prompts) in local git repos that any coding agent — Claude Code, Cursor, Codex, OpenClaw — can consume. Think **npm for AI skills**, backed by git.

## Why skillm

- **Git-native** — repos are git clones, branches are skill collections, history is git log
- **Multi-repo** — each remote is its own git clone, no conflicts
- **No internet required** — skills stored locally, not fetched on-demand
- **Agent-agnostic** — works with Claude Code, Cursor, Codex, OpenClaw, or any markdown-based agent
- **Team-safe** — sharing is git push/pull to any remote (local path, SSH, HTTPS)

## Install

### Standalone binary (recommended for teams)

```bash
./package.sh                              # build only → dist/skillm
./package.sh --install                    # build + install to /usr/local/bin
./package.sh --install-to /home/prgn_share/bin  # build + install to shared path
```

No Python needed on target machines — just copy the binary.

### From source (development)

```bash
pip install -e .
```

Requires Python 3.10+.

## Quick Start

### 1. Pull a team repo and install a skill

```bash
# Clone the team's skill repo
skillm repo add team ssh://git@server/team-skills.git

# Browse what's available
skillm list

# Install a skill into your project
cd your-project/
skillm install deploy-k8s
# Installed deploy-k8s → .claude/skills/
```

That's it. The local repo is auto-created on first use. `install` auto-creates the agent directory.

### 2. Create and publish your own skills

Create a skill — just a directory with a `SKILL.md`:

```bash
mkdir my-skill
cat > my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: Help with writing unit tests
tags: [testing, python]
requires:
  tools: [python3, pytest]
---

# Unit Test Helper

When asked to write tests:
1. Use pytest, not unittest
2. Name test files `test_*.py`
3. Use fixtures for shared setup
EOF
```

Add it to your library:

```bash
skillm add ./my-skill/
```

### 3. Share with your team

```bash
skillm push
```

---

## Core Concepts

### Repo = Git Clone

Each remote URL gets its own git clone under `~/.skillm/repos/`. No conflicts between unrelated sources.

```
~/.skillm/
├── config.toml
└── repos/
    ├── local/               # default repo (git init, no remote)
    │   ├── .git/
    │   └── my-shortcuts/SKILL.md
    ├── team/                # git clone of ssh://server/skills.git
    │   ├── .git/
    │   ├── deploy-k8s/SKILL.md
    │   └── monitor/SKILL.md
    └── personal/            # git clone of your own remote
        ├── .git/
        └── snippets/SKILL.md
```

### Branch = Skill Collection

Each git branch within a repo is a curated collection of skills. Switch branches to switch collections.

```
repos/team/
├── branch: main       →  deploy-k8s/, monitor-setup/
├── branch: infra      →  terraform/, ansible/
└── branch: ai         →  train-model/, prompt-eng/
```

### Version = Git Commit

Every `add` creates a git commit. Git history is your version history. No tags, no version strings — git already solved versioning.

### Active Context

Two levels: **active repo** + **active branch** (git HEAD per repo).

- **Write operations** (`add`, `rm`, `tag`) target the active repo's active branch
- **Read operations** (`search`, `list`, `install`) work across all repos and branches
- `skillm repo switch` changes active repo
- `skillm branch` changes active branch within active repo

---

## What is a Skill?

A skill is a directory with a `SKILL.md` file:

```
my-skill/
├── SKILL.md              # Required — agent instructions
├── scripts/              # Optional — helper scripts
├── requirements.txt      # Optional — Python package deps
└── templates/            # Optional — file templates
```

### SKILL.md Frontmatter

```yaml
---
name: web-scraper
description: Scrape and parse websites
author: alice
tags: [web, scraping, python]
category: devops
requires:
  tools: [python3, curl, jq]       # CLI binaries (checked via `which`)
  env: [API_KEY, DATABASE_URL]      # environment variables
  skills: [git-workflow]            # other skill dependencies
---

# Web Scraper

Instructions for the agent go here...
```

---

## Command Reference

### Skill Operations

| Command | Description |
|---------|-------------|
| `skillm add <dir> [--name] [--major] [--version] [-c CAT]` | Add a skill (creates new version) |
| `skillm update <dir> [--name]` | Replace latest version in-place |
| `skillm rm <name> [--version VER]` | Remove a skill or specific version |
| `skillm info <name>` | Show skill details |
| `skillm list [-c CATEGORY]` | List all skills (optionally by category) |
| `skillm search <query>` | Full-text search |
| `skillm versions <name>` | List all versions with sizes and dates |
| `skillm tag <name> <tags...>` | Add tags |
| `skillm untag <name> <tags...>` | Remove tags |
| `skillm categorize <name> <category>` | Set category |
| `skillm categories` | List categories with skill counts |
| `skillm export <name> [--version] [--output]` | Export as .skillpack archive |
| `skillm import <source> [--name] [--ref] [--token]` | Import from GitHub/ClawHub/URL/file |

### Project Operations

All project commands accept `--agent/-a` (claude, cursor, codex, openclaw) and `--project-root/-r`.

| Command | Description |
|---------|-------------|
| `skillm install <name> [--pin]` | Install skill into project |
| `skillm uninstall <name>` | Remove skill from project |
| `skillm sync` | Install missing skills from skills.json |
| `skillm upgrade [name]` | Update to latest library versions |
| `skillm check [name] [--scan/--no-scan]` | Check environment requirements |
| `skillm inject [--format FMT] [--file PATH]` | Write skill refs into agent config |
| `skillm enable <name>` | Enable a skill in project |
| `skillm disable <name>` | Disable a skill in project |

### Branch Management

| Command | Description |
|---------|-------------|
| `skillm branch` | List all branches |
| `skillm branch <name>` | Switch to branch (auto-commits changes) |
| `skillm branch -n <name>` | Create branch (forks from current) |
| `skillm branch -n <name> --empty` | Create empty branch |
| `skillm branch <name> --reset` | Reset branch to remote/initial state |
| `skillm branch --rm <name>` | Delete branch |

### Repo Management

| Command | Description |
|---------|-------------|
| `skillm repo add <name> <url>` | Clone a remote URL as a named repo |
| `skillm repo init <name>` | Create a local-only repo (no remote) |
| `skillm repo rm <name>` | Remove a repo |
| `skillm repo switch <name>` | Switch active repo |
| `skillm repo list` | List all repos |

### Git Sync

| Command | Description |
|---------|-------------|
| `skillm push [repo] [-b BRANCH]` | Push repo to its origin |
| `skillm pull [repo] [--branch NAME]` | Pull from repo's origin |

---

## How It Works

```
Sources                    Repos (~/.skillm/repos/)              Your Project
───────                    ────────────────────────              ────────────

                           repos/team/
SKILL.md dir ─┐              branch: main                     .claude/
GitHub repo ──┤  add           ├── deploy-k8s/SKILL.md          ├── skills.json
ClawHub ──────┤  ────►         └── monitor/SKILL.md    install  ├── skills/
.skillpack ───┘                                        ──────►  │   └── deploy-k8s/
                           repos/local/                          └── CLAUDE.md
                             branch: main
Remote ◄──── push/pull ──►   └── my-shortcuts/SKILL.md
```

**The flow:**
1. **Add** skills from directories, GitHub, ClawHub, or archives into the active repo/branch
2. **Pull** from remotes, or **push** to share with the team
3. **Search** across all repos and branches, **install** into any project
4. **Inject** skill references into your agent's config

## Architecture

```
CLI (Click)
  └─► Core Engine (Library + Project)
        ├─► RepoManager (multi-repo: one clone per remote)
        ├─► Git Backend (branches = collections, commits = versions)
        ├─► Database (SQLite + FTS5, search index)
        ├─► Metadata Parser (YAML frontmatter)
        ├─► Scanner (auto-detect requirements)
        ├─► Checker (verify environment)
        └─► Importer (GitHub, ClawHub, URL)
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| CLI | Click |
| Storage | Git (repos, branches, commits) |
| Search | SQLite + FTS5 |
| Terminal UI | Rich |
| Config | TOML |
| Metadata | YAML frontmatter (pyyaml) |
| HTTP | httpx |
| Package format | tar.gz (.skillpack) |

## License

TBD
