# skillm

Git-backed skill manager for AI coding agents.

Manage reusable skills (instructions, tools, prompts) in a local git repo that any coding agent — Claude Code, Cursor, Codex, OpenClaw — can consume. Think **npm for AI skills**, backed by git.

## Why skillm

- **Git-backed** — versions are git tags, libraries are git branches, sync is git push/pull
- **No internet required** — skills are stored locally, not fetched on-demand
- **You own your library** — a standard git repo on your machine
- **Multi-library** — organize skills into separate libraries (infra, ai, personal, ...)
- **Cross-library search** — search and install from any library, write to the active one
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

### 1. Pull a team library and install a skill

```bash
# One-time setup: add the team remote
skillm remote add team ssh://git@server/team-skills.git

# Pull the infra library
skillm pull team --library infra

# Install a skill into your project
cd your-project/
skillm install deploy-k8s
# Installed deploy-k8s@v1.0 → .claude/skills/
```

That's it. The local repo is auto-created on first use. `install` auto-creates the agent directory.

```bash
# Browse what's available
skillm list
```

```
                   infra
┏━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Name          ┃ Latest ┃ Tags               ┃   Size ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ deploy-k8s    │ v1.0   │ k8s, deployment    │ 2.1 KB │
│ monitor-setup │ v0.3   │ monitoring, grafana│ 1.4 KB │
│ db-migrate    │ v2.1   │ postgres, migration│ 3.0 KB │
└───────────────┴────────┴────────────────────┴────────┘
```

```bash
# Search by keyword
skillm search "postgres"

# Show skill details
skillm info deploy-k8s
```

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
skillm add ./my-skill/                       # v0.1
skillm add ./my-skill/                       # v0.2 (auto-increment)
skillm add ./my-skill/ --major               # v1.0 (major bump)
```

### 3. Share with your team

```bash
# Push the current library to the remote
skillm push

# Or push to a specific remote
skillm push team
```

---

## Core Concepts

### Library = Git Branch

Each git branch is a **library** — a curated collection of skills. One git repo holds all your libraries. Only one is active at a time.

```
~/.skillm/
├── config.toml             # Global config
├── library.db              # SQLite index (cache, rebuildable)
└── skills/                 # Git repo
    ├── .git/
    ├── deploy-k8s/
    │   └── SKILL.md
    └── monitor-setup/
        └── SKILL.md
```

```
skills.git
├── branch: infra       →  deploy-k8s/, monitor-setup/, ...
├── branch: ai          →  train-model/, prompt-eng/, ...
└── branch: personal    →  my-shortcuts/, ...
```

### Version = Git Tag

Every published version is a three-level git tag: `library/skill/version`.

```
infra/deploy-k8s/v1.0
ai/train-model/v2.1
personal/my-shortcuts/v0.3
```

### Remote = Git Remote

Sharing is standard git push/pull. Any URL git understands works:

```
/shared/skills                    # local path
ssh://git@server/skills.git       # SSH
https://github.com/team/skills    # HTTPS
```

### Active Library Model

- **Write operations** (`add`, `rm`, `tag`, `categorize`) target the active library
- **Read operations** (`search`, `install`) work across ALL local libraries
- **Switch** changes which library is active

### SQLite is a Cache

`library.db` is rebuildable from git tags + SKILL.md files. If corrupted, `skillm library rebuild` fully restores it. SKILL.md frontmatter is the single source of truth.

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

`requires` only declares **preconditions that skillm checks**. Language package dependencies use their ecosystem's standard files (`requirements.txt`, `package.json`) inside the skill directory.

---

## Features

### Library Management

**Create and switch libraries:**

```bash
skillm library create infra            # create a new library (independent history)
skillm library switch ai               # switch to another library
skillm library ls                      # list all libraries with tracking info
skillm library delete old-lib --yes    # delete a library
```

```
$ skillm library ls

  * infra        origin/infra      3 skill(s)
    ai           origin/ai         7 skill(s)
    team-infra   team/infra        5 skill(s)
    personal     (local)           2 skill(s)
```

**Set upstream tracking:**

```bash
skillm library set-remote origin       # current library tracks origin/<library>
skillm library unset-remote            # remove tracking
```

### Skills — Add, Search, Organize

**Add and version:**

```bash
skillm add ./my-skill/                       # creates v0.1
skillm add ./my-skill/                       # creates v0.2 (auto-increment)
skillm add ./my-skill/ --major               # creates v1.0 (major bump)
skillm add ./my-skill/ --version custom-tag  # explicit version string
skillm add ./my-skill/ --name alt-name       # override skill name
skillm add ./my-skill/ -c coding             # set category on add
```

**Update in-place:**

```bash
skillm update ./my-skill/                    # replace latest version (no new version)
```

**Remove:**

```bash
skillm rm my-skill --version v0.1   # remove a specific version
skillm rm my-skill                  # remove skill entirely (all versions)
```

**Browse and search (across all libraries):**

```bash
skillm list                         # all skills, grouped by category
skillm list -c coding               # filter by category
skillm search "pytest"              # full-text search across all libraries
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
skillm import owner/repo --ref v1.0          # specific git ref
skillm import clawhub:slug                   # ClawHub registry
skillm import clawhub:slug@1.0.0             # ClawHub specific version
skillm import https://example.com/skill.tar.gz  # URL (tar.gz or zip)
skillm import ./skill.skillpack              # portable archive
```

**Export as portable archives:**

```bash
skillm export my-skill                       # export latest version
skillm export my-skill --version v1.0        # export specific version
```

### Project — Installing and Using Skills

**Install:**

```bash
skillm install my-skill                      # install latest version
skillm install my-skill@v0.1                 # install specific version
skillm install my-skill --pin                # pin to this version (skip on upgrade)
skillm install my-skill --agent cursor       # install into .cursor/skills/
```

When a skill name exists in multiple libraries, skillm prompts you to choose:

```
Found "deploy" in multiple libraries:
  [1] infra/deploy  v1.0  — Deploy to Kubernetes
  [2] ai/deploy     v0.2  — Deploy ML models
Select: _
```

Or specify explicitly: `skillm install deploy --library infra`

**Manage project skills:**

```bash
skillm uninstall my-skill            # remove skill from project
skillm sync                          # install all missing skills from skills.json
skillm upgrade                       # update all skills to latest library versions
skillm upgrade my-skill              # update one skill
skillm enable my-skill               # re-enable a disabled skill
skillm disable my-skill              # hide from agent, keep files
```

**Inject into agent config:**

```bash
skillm inject                        # auto-detect agent format
skillm inject --format claude        # force CLAUDE.md
skillm inject --format cursor        # force .cursorrules
```

| Agent | Skills directory | Config file |
|-------|-----------------|-------------|
| Claude Code | `.claude/skills/` | `CLAUDE.md` |
| Cursor | `.cursor/skills/` | `.cursorrules` |
| Codex | `.codex/skills/` | `AGENTS.md` |
| OpenClaw | `.openclaw/skills/` | `AGENTS.md` |

**Check environment requirements:**

```bash
skillm check my-skill                # check a single skill from library
skillm check                         # check all installed project skills
skillm check --no-scan               # skip auto-detection, check declared only
```

```
my-skill environment check:
  ✓ python3 — Found at /usr/bin/python3
  ✓ pytest — Installed (8.1.0)
  ✗ API_KEY — Not set
  2 passed, 1 failed
```

### Sharing — Remotes, Push, Pull

**Configure remotes:**

```bash
skillm remote add team ssh://git@server/skills.git    # add a remote
skillm remote add shared /home/prgn_share/skills      # local path works too
skillm remote list                                     # list all remotes
skillm remote rm old-server                            # remove a remote
```

**Pull libraries from a remote:**

```bash
skillm pull team --library infra              # pull a specific library
skillm pull team --library infra,ai           # pull multiple
skillm pull team --library infra --as team-infra  # rename if local conflict
skillm pull                                   # pull from tracked remote
```

Two commands to start using a remote library: `pull` then `install`.

**Push to a remote:**

```bash
skillm push                                  # push to tracked remote
skillm push team                             # push to a specific remote
skillm push origin --as my-patch             # push as a different branch name
```

No push permission? Fork the repo and push to your own remote:

```bash
skillm remote add myfork ssh://git@server/myfork/skills.git
skillm push myfork
```

### Maintenance

**Library maintenance:**

```bash
skillm library init                  # initialize (auto-runs on first use)
skillm library init --path /custom   # initialize at a custom path
skillm library stats                 # skill count, total size, backend type
skillm library check                 # verify DB matches git tags
skillm library rebuild               # rebuild DB from git (fixes corruption)
skillm library compact               # VACUUM the SQLite database
```

**Database snapshots:**

Every write operation auto-snapshots the database.

```bash
skillm library snapshots             # list snapshots
skillm library rollback              # restore most recent snapshot
```

---

## How It Works

### Overview

```
Sources                     Local Git Repo (~/.skillm/skills/)          Your Project
───────                     ──────────────────────────────────          ────────────

SKILL.md dir ─┐              branch: infra                          .claude/
GitHub repo ──┤  skillm add    ├── deploy-k8s/SKILL.md    skillm     ├── skills.json
ClawHub ──────┤  ──────────►   ├── monitor/SKILL.md       install    ├── skills/
.skillpack ───┘                └── tag: infra/deploy-k8s/v1.0  ──►  │   └── deploy-k8s/
                                                                     └── CLAUDE.md
                             branch: ai
Remote ◄──── push/pull ────►   ├── train-model/SKILL.md
(git remote)                   └── tag: ai/train-model/v2.1
```

**The flow:**
1. **Add** skills from directories, GitHub, ClawHub, or archives into the active library
2. **Pull** libraries from remotes, or **push** your library to share with the team
3. **Search** across all libraries, **install** into any project
4. **Inject** skill references into your agent's config — your AI agent follows them

### Multi-Remote, Multi-Library Architecture

```
                         REMOTES (git remotes)
  ┌──────────────────────────────────────────────────────────┐
  │                                                          │
  │   origin (ssh://git@server/skills.git)                   │
  │     ├── branch: infra     ── tags: infra/deploy-k8s/v1.0│
  │     ├── branch: ai        ── tags: ai/train-model/v2.1  │
  │     └── branch: personal                                 │
  │                                                          │
  │   team (ssh://git@team-server/shared-skills.git)         │
  │     ├── branch: infra     ── tags: infra/db-migrate/v1.0│
  │     └── branch: devops    ── tags: devops/ci-setup/v0.3 │
  │                                                          │
  │   myfork (/home/alice/my-skills.git)                     │
  │     └── branch: personal  ── tags: personal/shortcuts/v1.0│
  │                                                          │
  └──────────────┬──────────────────────────┬────────────────┘
                 │                          │
           push (git push)          pull (git fetch + merge)
           + tags                   + tags
                 │                          │
  ┌──────────────▼──────────────────────────▼────────────────┐
  │                                                          │
  │   LOCAL GIT REPO (~/.skillm/skills/)                     │
  │                                                          │
  │   Branches (= Libraries):                                │
  │     * infra          ← tracks origin/infra               │
  │       ├── deploy-k8s/SKILL.md                            │
  │       ├── monitor-setup/SKILL.md                         │
  │       └── db-migrate/SKILL.md                            │
  │                                                          │
  │       ai             ← tracks origin/ai                  │
  │       ├── train-model/SKILL.md                           │
  │       └── prompt-eng/SKILL.md                            │
  │                                                          │
  │       team-devops    ← tracks team/devops                │
  │       └── ci-setup/SKILL.md                              │
  │                                                          │
  │       personal       ← (local only, no remote)           │
  │       └── my-shortcuts/SKILL.md                          │
  │                                                          │
  │   Tags (= Versions):                                     │
  │       infra/deploy-k8s/v1.0                              │
  │       infra/deploy-k8s/v1.1                              │
  │       ai/train-model/v2.1                                │
  │       team-devops/ci-setup/v0.3                          │
  │       personal/my-shortcuts/v1.0                         │
  │                                                          │
  │   SQLite Cache (library.db):                             │
  │       Indexes ALL libraries for fast search              │
  │       Rebuildable: skillm library rebuild                │
  │                                                          │
  └──────────────┬───────────────────────────────────────────┘
                 │
           install / upgrade / sync
           (extracts files at a specific tag)
                 │
  ┌──────────────▼───────────────────────────────────────────┐
  │                                                          │
  │   YOUR PROJECT (any working directory)                   │
  │                                                          │
  │   .claude/                                               │
  │   ├── skills.json          ← manifest (name, version,   │
  │   │                           library, pinned)           │
  │   └── skills/                                            │
  │       ├── deploy-k8s/      ← from infra library         │
  │       │   └── SKILL.md                                   │
  │       └── ci-setup/        ← from team-devops library   │
  │           └── SKILL.md                                   │
  │                                                          │
  │   CLAUDE.md                ← skillm inject writes here   │
  │                                                          │
  └──────────────────────────────────────────────────────────┘
```

**Key operations:**

| Operation | Scope | What it does |
|-----------|-------|-------------|
| `add` | Active library only | Copy skill dir → git commit → git tag |
| `search`, `list` | All local libraries | Query SQLite cache across all branches |
| `install` | All → project | Find skill in any library, extract to project |
| `push` | Active library → remote | `git push` branch + tags to tracked remote |
| `pull` | Remote → local | `git fetch` + create/update local branch |
| `library switch` | Local | `git checkout` to change active library |
| `library set-remote` | Local | `git branch --set-upstream-to` |

---

## Architecture

```
CLI (Click)
  └─► Core Engine (Library + Project)
        ├─► Git Backend (branches = libraries, tags = versions)
        ├─► Database (SQLite + FTS5, pure cache)
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
| CLI | Click (Command Line Interface Creation Kit) |
| Storage | Git (branches, tags) |
| Cache | SQLite + FTS5 |
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
| `skillm library create <name>` | Create a new library (independent skill collection) |
| `skillm library switch <name>` | Switch to a different library |
| `skillm library ls` | List all libraries with tracking info |
| `skillm library delete <name> [--yes]` | Delete a library |
| `skillm library set-remote <remote>` | Set upstream tracking for current library |
| `skillm library unset-remote` | Remove upstream tracking |
| `skillm library stats` | Show library statistics |
| `skillm library rebuild` | Rebuild DB from git tags (fixes corruption) |
| `skillm library compact` | VACUUM the SQLite database |
| `skillm library check` | Verify DB matches git tags |
| `skillm library snapshots` | List DB snapshots |
| `skillm library rollback [SNAPSHOT]` | Restore a DB snapshot |

### Skills

| Command | Description |
|---------|-------------|
| `skillm add <dir> [--name] [--major] [--version] [-c CAT]` | Add a skill (creates new version) |
| `skillm update <dir> [--name]` | Replace latest version in-place |
| `skillm rm <name> [--version VER]` | Remove a skill or specific version |
| `skillm info <name>` | Show skill details |
| `skillm list [-c CATEGORY]` | List all skills (optionally by category) |
| `skillm search <query>` | Full-text search across all libraries |
| `skillm versions <name>` | List all versions with sizes and dates |
| `skillm tag <name> <tags...>` | Add tags |
| `skillm untag <name> <tags...>` | Remove tags |
| `skillm categorize <name> <category>` | Set category |
| `skillm categories` | List categories with skill counts |
| `skillm check [name] [--scan/--no-scan]` | Check environment requirements |

### Project

All project commands accept `--agent/-a` (claude, cursor, codex, openclaw) and `--project-root/-r` options.

| Command | Description |
|---------|-------------|
| `skillm install <name[@ver]> [--pin] [--library LIB]` | Install skill into project |
| `skillm uninstall <name>` | Remove skill from project |
| `skillm sync` | Install all missing skills from skills.json |
| `skillm upgrade [name]` | Update to latest library versions |
| `skillm enable <name>` | Re-enable a disabled skill |
| `skillm disable <name>` | Hide skill from agent (keep files) |
| `skillm inject [--format FMT] [--file PATH]` | Inject skill references into agent config |

### Import/Export

| Command | Description |
|---------|-------------|
| `skillm import <source> [--name] [--ref] [--token]` | Import from GitHub/ClawHub/URL/file |
| `skillm export <name> [--version] [--output]` | Export as .skillpack archive |

### Remotes & Sync

| Command | Description |
|---------|-------------|
| `skillm remote add <name> <url>` | Add a git remote |
| `skillm remote rm <name>` | Remove a remote |
| `skillm remote list` | List all remotes |
| `skillm remote switch <name>` | Set default remote |
| `skillm push [remote] [--as BRANCH]` | Push current library to remote |
| `skillm pull [remote] [--library NAME] [--as LOCAL]` | Pull library from remote |

## License

TBD
