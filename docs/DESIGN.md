# skillm — Design Document

> Per-project AI Agent Skill Manager with local-first, protocol-agnostic storage.

**Version:** 0.2.0 (planned)
**Status:** Draft
**Date:** 2026-03-06

---

## Table of Contents

1. [Vision](#vision)
2. [Principles](#principles)
3. [Architecture Overview](#architecture-overview)
4. [Core Concepts](#core-concepts)
5. [Storage Backends](#storage-backends)
6. [Database Schema](#database-schema)
7. [Skill Format](#skill-format)
8. [CLI Commands](#cli-commands)
9. [Caching Strategy](#caching-strategy)
10. [Versioning](#versioning)
11. [Multi-User & Sharing](#multi-user--sharing)
12. [Agent Integration](#agent-integration)
13. [Implementation Plan](#implementation-plan)
14. [Future Work](#future-work)

---

## Vision

`skillm` is a **local-first, offline-capable** skill manager for AI agents. It manages a library of reusable skills (instructions, tools, prompts) that any coding agent (Claude Code, Codex, Cursor, OpenClaw, etc.) can consume.

Think: **npm for AI skills**, but your library lives on *your* machine (or your server, or your NAS — wherever you want).

### What makes it different

- **No internet required** — skills are stored locally, not fetched on-demand from GitHub
- **You own your library** — not dependent on any platform being up
- **Protocol-agnostic storage** — local disk, SSH remote, NAS mount, S3 bucket
- **Agent-agnostic output** — works with any agent that reads markdown files
- **Project-scoped consumption** — each project declares what skills it needs

---

## Principles

1. **Files are truth, DB is index.** The database is always rebuildable from the skill files. If you lose the DB, `skillm library rebuild` restores everything.

2. **Local-first, remote-optional.** Everything works offline on a single machine. Remotes are an opt-in enhancement.

3. **Offline by default.** No network call should be required for day-to-day operations (search, add to project, list). Network is only for import/sync with remotes.

4. **Agent-agnostic.** Skills are plain markdown. The injection layer supports multiple agent config formats.

5. **Simple over clever.** SQLite over Postgres. Files over blobs. SSH over custom protocols.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                    CLI Layer                      │
│  (click commands — user-facing interface)         │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│                  Core Engine                      │
│  (skill operations, metadata extraction,          │
│   version management, injection)                  │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│               Storage Abstraction                 │
│  (LibraryBackend interface)                       │
├─────────┬──────────┬──────────┬─────────────────┤
│  Local  │   SSH    │  File    │   S3 (future)   │
│ Backend │ Backend  │ Backend  │                  │
└─────────┴──────────┴──────────┴─────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│                 Local Cache                       │
│  (SQLite FTS5 index + cached skill files)         │
└─────────────────────────────────────────────────┘
```

### Directory Layout

**Library (global — the skill store):**

```
~/.skillm/                          # Default location
├── config.toml                     # Library + backend + cache config
├── library.db                      # SQLite database (FTS5 enabled)
├── skills/                         # Skill files organized by name/version
│   ├── defuddle/
│   │   ├── v1/
│   │   │   ├── SKILL.md
│   │   │   └── scripts/
│   │   └── v2/
│   │       └── SKILL.md
│   └── web-scraper/
│       └── v1/
│           └── SKILL.md
└── cache/                          # Cached data from remote backends
    ├── remote.db                   # Cached remote DB snapshot
    └── skills/                     # Cached skill files from remotes
```

**Project (per-repo — skill consumption):**

```
your-project/
├── skills.json                     # Declarative skill dependencies
├── .skills/                        # Installed skill files (gitignored)
│   ├── defuddle/
│   │   └── SKILL.md
│   └── web-scraper/
│       └── SKILL.md
└── CLAUDE.md                       # Auto-injected skills section
```

---

## Core Concepts

### Skill

A **skill** is a directory containing at minimum a `SKILL.md` file. It can also include scripts, templates, reference data, and any supporting files.

```
my-skill/
├── SKILL.md              # Required — skill instructions
├── scripts/              # Optional — helper scripts
│   └── extract.py
├── templates/            # Optional — file templates
│   └── config.yaml
└── README.md             # Optional — human docs
```

### Library

The **library** is the central store of all skills available to the user. It lives at a configurable location and is managed entirely by `skillm`.

### Project

A **project** is any directory where you work with an AI agent. It declares skill dependencies in `skills.json` and installs them to `.skills/`.

### Backend

A **backend** is a storage driver that implements the `LibraryBackend` interface. It determines *where* the library physically lives.

### Version

Each skill can have multiple **versions**. Versions are auto-incremented integers by default (v1, v2, v3) with optional semantic versioning.

---

## Storage Backends

### Backend Interface

```python
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

class LibraryBackend(ABC):
    """Abstract interface for skill library storage."""

    @abstractmethod
    def initialize(self) -> None:
        """Set up the backend (create dirs, etc.)."""

    @abstractmethod
    def get_db(self) -> Path:
        """Get or download library.db to a local path."""

    @abstractmethod
    def put_db(self, local_db: Path) -> None:
        """Upload/save the updated library.db."""

    @abstractmethod
    def get_skill_files(self, name: str, version: str) -> Path:
        """Fetch skill files, return local directory path."""

    @abstractmethod
    def put_skill_files(self, name: str, version: str, source_dir: Path) -> None:
        """Store skill files from a local directory."""

    @abstractmethod
    def remove_skill_files(self, name: str, version: Optional[str] = None) -> None:
        """Remove skill files. If version is None, remove all versions."""

    @abstractmethod
    def list_skill_dirs(self) -> list[tuple[str, list[str]]]:
        """List all skills and their versions from the file store."""

    @abstractmethod
    def skill_exists(self, name: str, version: str) -> bool:
        """Check if a skill version exists in the store."""
```

### Local Backend

The default. Everything is on the local filesystem.

```toml
[library]
backend = "local"
path = "~/.skillm"
```

**Implementation:** Direct filesystem operations. `get_db()` returns the path as-is. No network, no caching needed.

### SSH Backend

Library lives on a remote machine accessible via SSH.

```toml
[library]
backend = "ssh"
host = "192.168.1.100"
port = 22                      # Optional, default 22
user = "hren"
path = "/home/hren/skill-library"
auth = "key"                   # "key" (default) or "password"
key_file = "~/.ssh/id_ed25519" # Optional, default: SSH agent/default key
```

**Implementation:**
- Uses `subprocess` calls to `scp`/`sftp`/`rsync` (no Python dependency like paramiko)
- `get_db()`: `scp remote:path/library.db → cache/remote.db`
- `put_db()`: `scp cache/remote.db → remote:path/library.db`
- `get_skill_files()`: `scp -r remote:path/skills/name/ver/ → cache/skills/name/ver/`
- `put_skill_files()`: `scp -r local/skills/name/ver/ → remote:path/skills/name/ver/`
- Full sync: `rsync -avz remote:path/ → cache/`

**Auth resolution order:**
1. Explicit `key_file` in config
2. SSH agent
3. `~/.ssh/config` host alias
4. Password prompt (interactive only)

### File Backend

For network-mounted filesystems (NAS, NFS, SMB).

```toml
[library]
backend = "file"
path = "/mnt/nas/skill-library"
```

**Implementation:** Same as local, just a different path. Useful for NAS/shared drives.

### S3 Backend (Future)

```toml
[library]
backend = "s3"
bucket = "my-skill-library"
prefix = "skillm/"
region = "us-west-2"
```

Deferred to a later version.

---

## Database Schema

SQLite with FTS5 for full-text search.

```sql
-- ============================================
-- Core Tables
-- ============================================

CREATE TABLE skills (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    author      TEXT DEFAULT '',
    source      TEXT DEFAULT '',        -- Original source (e.g., "owner/repo")
    created_at  TEXT NOT NULL,          -- ISO 8601
    updated_at  TEXT NOT NULL           -- ISO 8601
);

CREATE TABLE versions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id    INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    version     TEXT NOT NULL,          -- "v1", "v2", or "1.0.0"
    changelog   TEXT DEFAULT '',
    file_count  INTEGER DEFAULT 0,
    total_size  INTEGER DEFAULT 0,     -- bytes
    published_at TEXT NOT NULL,         -- ISO 8601
    UNIQUE(skill_id, version)
);

CREATE TABLE tags (
    skill_id    INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    tag         TEXT NOT NULL,
    PRIMARY KEY (skill_id, tag)
);

CREATE TABLE files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id  INTEGER NOT NULL REFERENCES versions(id) ON DELETE CASCADE,
    rel_path    TEXT NOT NULL,          -- Relative path within skill dir
    size        INTEGER DEFAULT 0,     -- bytes
    sha256      TEXT NOT NULL,          -- File hash for integrity
    UNIQUE(version_id, rel_path)
);

-- ============================================
-- Full-Text Search (FTS5)
-- ============================================

CREATE VIRTUAL TABLE search_index USING fts5(
    name,
    description,
    tags,           -- Space-separated tags
    content,        -- SKILL.md content (for deep search)
    content=skills,
    content_rowid=id
);

-- ============================================
-- Library Metadata
-- ============================================

CREATE TABLE library_meta (
    key         TEXT PRIMARY KEY,
    value       TEXT
);

-- Stores: schema_version, created_at, last_rebuild, etc.

-- ============================================
-- Indexes
-- ============================================

CREATE INDEX idx_versions_skill ON versions(skill_id);
CREATE INDEX idx_tags_tag ON tags(tag);
CREATE INDEX idx_files_version ON files(version_id);
```

### FTS5 Triggers

Keep the search index in sync with the skills table:

```sql
CREATE TRIGGER skills_ai AFTER INSERT ON skills BEGIN
    INSERT INTO search_index(rowid, name, description, tags, content)
    VALUES (new.id, new.name, new.description, '', '');
END;

CREATE TRIGGER skills_au AFTER UPDATE ON skills BEGIN
    UPDATE search_index
    SET name = new.name, description = new.description
    WHERE rowid = new.id;
END;

CREATE TRIGGER skills_ad AFTER DELETE ON skills BEGIN
    DELETE FROM search_index WHERE rowid = old.id;
END;
```

Tags and content are updated separately after insert.

---

## Skill Format

### SKILL.md Structure

```markdown
# Skill Name

Short description of what this skill does.

<!-- skillm:meta
tags: scraping, youtube, video
author: renhuailu
requires: python3, httpx
-->

## When to Use

- Describe when an agent should use this skill
- ...

## Instructions

Step-by-step instructions for the agent.

## Examples

...
```

### Metadata Extraction

When a skill is published, `skillm` extracts:

| Field | Source | Fallback |
|---|---|---|
| `name` | Directory name | First `# Heading` in SKILL.md |
| `description` | First non-heading paragraph in SKILL.md | Empty |
| `tags` | `<!-- skillm:meta tags: ... -->` comment | Empty |
| `author` | `<!-- skillm:meta author: ... -->` comment | git config user.name |
| `requires` | `<!-- skillm:meta requires: ... -->` comment | Empty |

The `<!-- skillm:meta -->` block is optional. Everything still works without it — `skillm` just has less metadata to index.

---

## CLI Commands

### Library Management

```bash
# Initialize a new library
skillm library init
# Creates ~/.skillm/ with config.toml, library.db, skills/

# Configure backend
skillm library backend local --path ~/.skillm
skillm library backend ssh --host 192.168.1.100 --user hren --path /home/hren/skill-library
skillm library backend file --path /mnt/nas/skills

# Library info
skillm library stats
# Skills: 42 | Versions: 87 | Size: 12.3 MB | Backend: local

# Rebuild DB from files
skillm library rebuild
# Walks skills/ directory, re-indexes everything into library.db

# Check integrity
skillm library check
# Verifies DB matches files, reports mismatches

# Compact DB
skillm library compact
# Runs SQLite VACUUM
```

### Skill Operations

```bash
# Publish a local skill directory to the library
skillm publish ./my-skill/
skillm publish ./my-skill/ --name custom-name
skillm publish ./my-skill/ --version 2.0.0    # Explicit version
# Reads SKILL.md, extracts metadata, stores in library, indexes in DB

# Import from GitHub (one-time download into library)
skillm import joeseesun/defuddle
skillm import owner/repo/subpath
skillm import owner/repo --name my-name
# Fetches from GitHub, stores locally — never needs GitHub again

# Import from a .skillpack file
skillm import ./defuddle-v2.skillpack
# Extracts and adds to library

# Import from a local directory (copy, not link)
skillm import ./path/to/skill/ --name my-skill

# Remove from library
skillm remove defuddle
skillm remove defuddle --version v1    # Remove specific version only

# Show skill info
skillm info defuddle
# Name: defuddle
# Description: Extract clean text from web pages
# Tags: scraping, html, text
# Versions: v1, v2 (latest)
# Author: joeseesun
# Files: 3 (4.2 KB)
# Source: joeseesun/defuddle

# List all versions
skillm versions defuddle
# v1  2026-01-15  3 files  2.1 KB
# v2  2026-03-01  4 files  4.2 KB  (latest)

# Tag management
skillm tag defuddle scraping html
skillm untag defuddle html

# Search the library
skillm search "youtube"
skillm search "scraping" --tag video
# Uses FTS5 — matches against name, description, tags, and SKILL.md content

# List all skills in library
skillm list
# Shows table: name, latest version, tags, size, date
```

### Project Operations

```bash
# Initialize a project for skill consumption
skillm init
# Creates skills.json + .skills/ in current project directory

# Add a skill from library to the project
skillm add defuddle
skillm add defuddle@v1               # Specific version
skillm add defuddle --pin            # Lock to current version
# Copies from library → .skills/, updates skills.json

# Remove from project
skillm drop defuddle
# Removes from .skills/ and skills.json. (Using "drop" to distinguish from library "remove")

# Enable/disable in project (keep files, toggle visibility)
skillm enable defuddle
skillm disable defuddle

# Sync project with skills.json
skillm sync
# Installs any skills listed in skills.json but missing from .skills/

# Update project skills to latest library versions
skillm upgrade [name]
# Pulls latest version from library for all or specified skills

# Inject skills into agent config
skillm inject
skillm inject --format claude         # CLAUDE.md
skillm inject --format cursor         # .cursorrules
skillm inject --format openclaw       # AGENTS.md
skillm inject --format auto           # Detect from project files
```

### Export / Share

```bash
# Export a skill as a portable package
skillm export defuddle
# Creates defuddle-v2.skillpack (tar.gz with metadata)

skillm export defuddle --version v1
# Specific version

skillm export --all
# Export entire library as one archive

# Import on another machine
skillm import ./defuddle-v2.skillpack
```

### Remotes (Tier 2/3)

```bash
# Add a remote library
skillm remote add office ssh://hren@192.168.1.100:/home/hren/skill-library
skillm remote add nas file:///mnt/nas/skills
skillm remote add github https://github.com   # Special: GitHub import source

# List remotes
skillm remote list

# Pull from remote into local library
skillm pull defuddle --from office
skillm pull --all --from office

# Push to remote from local library
skillm push defuddle --to office
skillm push --all --to office

# Sync with remote (bidirectional)
skillm remote sync office

# Remove a remote
skillm remote remove office
```

---

## Caching Strategy

For remote backends, all operations go through a local cache:

```
~/.skillm/cache/
├── library.db         # Cached copy of remote DB
├── skills/            # Cached skill files
└── meta.json          # Cache metadata
```

### Cache Rules

| Operation | Cache Behavior |
|---|---|
| `search` | Use cached DB if < TTL. Otherwise fetch remote DB. |
| `add` (to project) | Use cached skill if hash matches. Otherwise fetch. |
| `publish` | Always writes to remote. Updates cache after. |
| `list` | Use cached DB if < TTL. |
| `info` | Use cached DB if < TTL. |

### Configuration

```toml
[cache]
enabled = true
path = "~/.skillm/cache"
ttl = 3600              # Seconds before remote DB is re-fetched
max_size = "500MB"      # Max cache size (LRU eviction)
```

### Cache Commands

```bash
skillm cache stats     # Show cache size and age
skillm cache clear     # Wipe cache
skillm cache refresh   # Force re-fetch from remote
```

---

## Versioning

### Default: Auto-increment

```
First publish  → v1
Second publish → v2
Third publish  → v3
```

Simple, predictable, no decisions needed.

### Optional: Semantic Versioning

```bash
skillm publish ./my-skill/ --version 2.0.0
```

When a semver is provided, it's stored as-is. Mixed versioning is allowed per skill (but not recommended).

### Version Resolution

```bash
skillm add defuddle          # Latest version
skillm add defuddle@v2       # Exact version
skillm add defuddle@latest   # Explicit latest
```

### Version Pinning

`skills.json` tracks the version:

```json
{
  "skills": {
    "defuddle": {
      "version": "v2",
      "pinned": false
    },
    "web-scraper": {
      "version": "v1",
      "pinned": true
    }
  }
}
```

- `pinned: false` → `skillm upgrade` will update to latest
- `pinned: true` → `skillm upgrade` skips this skill

---

## Multi-User & Sharing

### .skillpack Format

A `.skillpack` is a gzipped tar archive:

```
defuddle-v2.skillpack (tar.gz)
├── skillpack.json        # Metadata
│   {
│     "name": "defuddle",
│     "version": "v2",
│     "description": "...",
│     "author": "joeseesun",
│     "tags": ["scraping", "html"],
│     "exported_at": "2026-03-06T20:00:00Z",
│     "skillm_version": "0.2.0"
│   }
└── files/
    ├── SKILL.md
    └── scripts/
        └── extract.py
```

### Team Workflow

```
Developer A                   Shared Server (SSH)              Developer B
───────────                   ──────────────────               ───────────
skillm publish ./skill   ──►  /srv/skill-library/     ◄──  skillm pull my-skill
skillm push --to team         ├── library.db                 skillm search "..."
                              └── skills/                    skillm add my-skill
```

### Write Locking (SSH Backend)

For concurrent writes to a shared SSH library:

```python
def acquire_lock(self) -> bool:
    """Advisory lock using mkdir (atomic on all filesystems)."""
    result = self._ssh(f"mkdir {self.path}/.lock 2>/dev/null")
    return result.returncode == 0

def release_lock(self):
    self._ssh(f"rmdir {self.path}/.lock")
```

With a timeout and stale lock detection (check lock age, break if > 5 minutes).

---

## Agent Integration

### Supported Agent Configs

| Agent | Config File | Injection Method |
|---|---|---|
| Claude Code | `CLAUDE.md` | Markdown section with skill list + paths |
| Cursor | `.cursorrules` | Markdown section |
| OpenClaw | `AGENTS.md` | Markdown section |
| Codex | `AGENTS.md` | Markdown section |
| Generic | Any `.md` file | `skillm inject --file CUSTOM.md` |

### Injection Format

```markdown
## Project Skills (auto-generated by skillm)

Available skills for this project:

- **defuddle** (`joeseesun/defuddle`): Extract clean text from web pages
  → Read `.skills/defuddle/SKILL.md` when relevant

- **web-scraper** (`custom/web-scraper`): Scrape and parse websites
  → Read `.skills/web-scraper/SKILL.md` when relevant

Only read a skill's SKILL.md when the current task matches it.
<!-- end:skillm -->
```

### Auto-Detection

`skillm inject --format auto` detects the agent by checking for:

1. `CLAUDE.md` → Claude Code format
2. `.cursorrules` → Cursor format
3. `AGENTS.md` → OpenClaw/Codex format
4. Falls back to `CLAUDE.md` (most common)

---

## Implementation Plan

### Phase 1: Core Library (v0.2.0)

**Goal:** Replace GitHub-first approach with local library.

**Tasks:**

1. **Storage abstraction**
   - Define `LibraryBackend` abstract class
   - Implement `LocalBackend`
   - Config loading from `config.toml`

2. **Database layer**
   - SQLite schema with FTS5
   - CRUD operations for skills, versions, tags, files
   - Search with FTS5 ranking
   - Rebuild from filesystem

3. **Core operations**
   - `library init` — create library structure
   - `publish` — local dir → library (extract metadata, index, store)
   - `remove` — delete from library
   - `info` / `list` / `search` — query operations
   - `versions` — version listing

4. **Project operations** (migrate from v0.1)
   - `init` — unchanged
   - `add` — now reads from local library instead of GitHub
   - `drop` — remove from project
   - `enable` / `disable` — unchanged
   - `sync` — unchanged but sourced from library
   - `inject` — generalize for multiple agent formats

5. **Import sources**
   - `import` from GitHub (one-time fetch → library)
   - `import` from local directory
   - `import` from `.skillpack`

6. **Export**
   - `export` single skill → `.skillpack`
   - `export --all` → full library archive

**Estimated effort:** 2-3 days

### Phase 2: SSH Backend (v0.3.0)

**Goal:** Remote library support via SSH.

**Tasks:**

1. Implement `SSHBackend` (scp/sftp/rsync via subprocess)
2. SSH auth resolution (key → agent → config → password)
3. Local caching layer with TTL
4. `library backend ssh` command
5. Write locking for shared access
6. Cache management commands

**Estimated effort:** 1-2 days

### Phase 3: Remotes & Sharing (v0.4.0)

**Goal:** Multi-library federation.

**Tasks:**

1. `remote add/remove/list` commands
2. `pull` / `push` between local and remote libraries
3. `remote sync` — bidirectional merge
4. Conflict resolution strategy (latest-wins or prompt)
5. `File` backend for NAS/mount paths

**Estimated effort:** 1-2 days

### Phase 4: Polish & Extras (v0.5.0)

**Goal:** Production-ready.

**Tasks:**

1. `skillm serve` — local HTTP server for web UI
2. Tag-based browsing and filtering
3. Skill dependency declarations
4. Auto-update checks
5. Shell completions (bash, zsh, fish)
6. Comprehensive test suite
7. Documentation site

**Estimated effort:** 2-3 days

---

## Future Work

- **Web UI** (`skillm serve`) — browse and manage skills in a browser
- **S3 Backend** — for cloud-hosted libraries
- **Skill dependencies** — skills that require other skills
- **Skill templates** — `skillm create --template python-tool`
- **Registry protocol** — standard API for skill registries (like npm registry)
- **Skill testing** — validate skills with test cases
- **AI-powered search** — semantic search using embeddings (optional, local model)
- **Skill analytics** — track which skills are used most across projects
- **Skill linting** — validate SKILL.md format and best practices

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| CLI framework | Click |
| Database | SQLite (with FTS5) |
| HTTP client | httpx |
| Terminal UI | Rich |
| SSH operations | subprocess (scp/sftp/rsync) |
| Config format | TOML |
| Package format | tar.gz (.skillpack) |
| Build system | Hatchling |
| Testing | pytest |

---

## File Structure (Target)

```
skillm/
├── pyproject.toml
├── README.md
├── docs/
│   ├── DESIGN.md              # This document
│   └── USAGE.md               # User-facing documentation
├── src/
│   └── skillm/
│       ├── __init__.py
│       ├── cli.py             # Click CLI commands
│       ├── core.py            # Core business logic
│       ├── db.py              # SQLite + FTS5 operations
│       ├── backends/
│       │   ├── __init__.py
│       │   ├── base.py        # LibraryBackend ABC
│       │   ├── local.py       # LocalBackend
│       │   ├── ssh.py         # SSHBackend
│       │   └── file.py        # FileBackend
│       ├── models.py          # Dataclasses (Skill, Version, etc.)
│       ├── metadata.py        # SKILL.md parsing & metadata extraction
│       ├── inject.py          # Agent config injection (CLAUDE.md, etc.)
│       ├── skillpack.py       # .skillpack export/import
│       ├── cache.py           # Caching layer for remote backends
│       └── config.py          # TOML config loading
└── tests/
    ├── conftest.py
    ├── test_db.py
    ├── test_backends.py
    ├── test_core.py
    ├── test_metadata.py
    ├── test_inject.py
    ├── test_skillpack.py
    └── test_cli.py
```
