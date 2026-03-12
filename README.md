# skillm

Local-first, offline-capable skill manager for AI coding agents.

Manage a library of reusable skills (instructions, tools, prompts) that any coding agent — Claude Code, Cursor, Codex, OpenClaw — can consume. Think **npm for AI skills**, but your library lives on your machine.

## Why skillm

- **No internet required** — skills are stored locally, not fetched on-demand
- **You own your library** — not dependent on any platform being up
- **Protocol-agnostic storage** — local disk, SSH, NAS mount, S3
- **Agent-agnostic output** — works with any agent that reads markdown
- **Project-scoped** — each project declares what skills it needs

## How It Works

Skills are directories containing a `SKILL.md` file with instructions for AI agents:

```
my-skill/
├── SKILL.md              # Required — agent instructions
├── scripts/              # Optional — helper scripts
└── templates/            # Optional — file templates
```

You **publish** skills to a local library, then **add** them to projects. `skillm` installs skill files and injects references into your agent config (`CLAUDE.md`, `.cursorrules`, etc.).

```
Library (~/.skillm/)              Project (your-repo/)
├── library.db                    ├── skills.json
└── skills/                       ├── .skills/
    ├── defuddle/v2/SKILL.md      │   └── defuddle/SKILL.md
    └── web-scraper/v1/SKILL.md   └── CLAUDE.md  ← auto-injected
```

## Usage

### Library

```bash
skillm library init                # Create a new library
skillm publish ./my-skill/         # Add a skill to the library
skillm import owner/repo           # One-time import from GitHub
skillm search "scraping"           # Full-text search (FTS5)
skillm list                        # List all skills
skillm info defuddle               # Show skill details
skillm remove defuddle             # Remove from library
```

### Project

```bash
skillm init                        # Set up project for skills
skillm add defuddle                # Install a skill from library
skillm add defuddle@v1             # Specific version
skillm drop defuddle               # Remove from project
skillm sync                        # Install missing skills from skills.json
skillm upgrade                     # Update to latest versions
skillm inject                      # Write skill refs into agent config
```

### Export & Share

```bash
skillm export defuddle             # Create .skillpack archive
skillm import ./skill.skillpack    # Import from archive
```

## Architecture

```
CLI (Click)
  └─► Core Engine
        └─► Storage Backend (pluggable)
              ├── Local   — default, filesystem
              ├── SSH     — remote via scp/rsync
              ├── File    — NAS/NFS/SMB mounts
              └── S3      — cloud (planned)
```

SQLite with FTS5 indexes all skill metadata for fast search. The database is always rebuildable from the skill files on disk.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| CLI | Click |
| Database | SQLite + FTS5 |
| Terminal UI | Rich |
| Config | TOML |
| Package format | tar.gz (.skillpack) |

## Status

Early development. See [docs/DESIGN.md](docs/DESIGN.md) for the full design document.

## License

TBD
