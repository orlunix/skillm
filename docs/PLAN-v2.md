# skillm v2 — Git-Backed Development Plan

**Branch:** `v2-git-backed`
**Date:** 2026-03-14
**Status:** In progress

---

## Design Principle

**Follow git.** The skills library is a git repo. Libraries are git branches.
Versions are git tags. Remotes are git remotes. Push/pull is git push/pull.
No custom protocols.

---

## Architecture

### Branch = Library

Each git branch is a **library** — a curated collection of skills.
One git repo holds all libraries. Only one library is active at a time
(= checked-out branch). Switching library = `git checkout`.

```
~/.skillm/
├── config.toml                 # Global config
├── library.db                  # SQLite index (cache, rebuildable)
└── skills/                     # Git repo (one repo, multiple branches)
    ├── .git/
    │   └── config              # git remotes live here
    ├── my-skill/
    │   ├── SKILL.md
    │   └── scripts/
    └── other-skill/
        └── SKILL.md
```

**Branch layout (each branch = a library):**

```
skills.git
├── branch: infra       →  deploy-k8s/, monitor-setup/, ...
├── branch: ai          →  train-model/, prompt-eng/, ...
└── branch: personal    →  my-shortcuts/, ...
```

### Core concepts

- **Library** = git branch: `infra`, `ai`, `personal`
- **Version** = git tag: `infra/my-skill/v0.1` (three-level: library/skill/version)
- **Remote** = git remote: `origin`, `team`, `backup`
- **SQLite** = pure cache, rebuildable from git tags + SKILL.md
- **SKILL.md** = single source of truth for all metadata

### Tag namespace

Tags use three-level naming to avoid collisions across libraries:

```
infra/deploy-k8s/v1.0
ai/train-model/v2.1
personal/my-shortcuts/v0.3
```

### Local ↔ Remote branch mapping

Local branches track remote branches 1:1. When pulling a remote library,
the local branch name defaults to the remote branch name. If a name
conflict exists, user must specify a local name with `--as`.

```
Local                          Remote (origin)
─────                          ───────────────
infra       ←── tracks ──→    origin/infra
ai          ←── tracks ──→    origin/ai

                               Remote (team)
                               ─────────────
team-infra  ←── tracks ──→    team/infra
```

### Active library model

Only one library is active (checked out) at a time. The working tree
contains only the active library's skill files. All data for other
libraries lives in `.git`.

- **Write operations** (`add`, `publish`, `tag`, `categorize`) target the active library
- **Read operations** (`search`, `install`) work across ALL local libraries by reading tags
- **Switch** changes which library is active: `skillm library switch ai`

### Search & install across libraries

Search scans tags from all libraries. Install extracts from any tag
regardless of which library is active.

```bash
# Search across all libraries
skillm search deploy
#  infra/deploy-k8s v1.0  — Deploy to Kubernetes
#  ai/deploy-model  v0.2  — Deploy ML models

# Install from specific library (when skill name exists in multiple)
skillm install deploy-k8s                  # unique name, auto-resolve
skillm install deploy --library infra      # ambiguous, specify library

# Ambiguous name → interactive selection
skillm install deploy
# Found "deploy" in multiple libraries:
#   [1] infra/deploy  v1.0  — Deploy to Kubernetes
#   [2] ai/deploy     v0.2  — Deploy ML models
# Select: _
```

### Pull workflow

Pull is selective — user specifies which remote libraries to pull:

```bash
# Pull specific libraries from a remote
skillm pull origin --library infra
skillm pull origin --library infra,ai

# Name conflict: remote "infra" but local "infra" already tracks another remote
skillm pull team --library infra --as team-infra
```

### Push workflow

Push sends the current branch + its tags to the tracked remote.
Two options when user lacks push permission:

```bash
# Push to tracked remote (default)
skillm push

# First push for an untracked local library (sets up tracking)
skillm push origin

# Option 1: push to a different branch name on the same remote
skillm push origin --as my-infra-patch

# Option 2: fork and push to your own remote
skillm remote add myfork ssh://git@server/myfork/skills.git
skillm push myfork
```

### Library list display

```
$ skillm library list

  * infra        origin/infra      3 skills   synced
    ai           origin/ai         7 skills   synced
    team-infra   team/infra        5 skills   2 days behind
    personal     (local)           2 skills
```

- `*` marks the active library
- Tracking remote shown, `(local)` for untracked branches
- Skill count from tag index
- Sync status: synced / behind / ahead

---

## Completed

### Phase 1: Git-backed LocalBackend
- [x] `LocalBackend` uses git repo internally
- [x] `put_skill_files` → copy + git add + commit + tag
- [x] `get_skill_files` → extract from git tag to cache
- [x] `list_skill_dirs` → parse git tags
- [x] `skill_exists` → check tag exists
- [x] `remove_skill_files` → delete tag (+ rm working tree for full removal)
- [x] All 120 v1 tests pass

### Phase 2: Git-native push/pull
- [x] Remove SSHBackend (git handles SSH transport)
- [x] `Library.push(remote)` → `git push remote --tags`
- [x] `Library.pull(remote)` → `git fetch --tags` + `rebuild()`
- [x] `Library.add_remote/remove_remote/list_remotes/has_remote`
- [x] CLI: `remote add/rm/list/switch` operates on git remotes
- [x] CLI: `push/pull` uses git directly
- [x] Simplify `remote.py` — just tracks default remote name
- [x] Delete `backends/ssh.py`
- [x] 113 tests pass

> **Note:** Phase 3 will extend push/pull with per-library `--library`,
> `--as`, and three-level tags. The current implementation is a working
> foundation that will be adapted, not replaced.

---

## TODO

### Phase 3: Three-level tags + library branches

**Why first:** All subsequent phases (publish pipeline, push/pull) depend
on the three-level tag format. Migrate tags before building on top of them.

**Implicit behaviors (user never needs to think about these):**

- `skillm init` creates git repo with default branch `main` + init commit
- First `skillm add` works immediately — `main` is the default library
- Active library = current git branch, read via `git branch --show-current`
- `library create` auto-creates init commit on orphan branch (tags need a commit)

**Tag namespace (two-level → three-level):**

- [ ] New tag format: `library/skill/version` (e.g. `main/my-skill/v0.1`)
- [ ] `put_skill_files` reads current branch name, creates `branch/skill/version` tag
- [ ] `list_skill_dirs` parses three-level tags
- [ ] `get_skill_files` accepts three-level tags
- [ ] `remove_skill_files` handles three-level tags
- [ ] `rebuild()` parses three-level tags, indexes all libraries (not just current branch)
- [ ] Migration: rename existing `skill/version` tags to `main/skill/version`
- [ ] All existing tests adapted to three-level format

**Library management:**

- [ ] `skillm library create <name>` → `git checkout --orphan <name>` + init commit
- [ ] `skillm library switch <name>` → `git checkout <name>`
- [ ] `skillm library list` → `git branch -a` + tag counts + sync status
- [ ] `skillm library delete <name>` → `git branch -D <name>` (with confirmation, cannot delete active)
- [ ] `skillm library set-remote <remote>` → `git branch -u <remote>/<branch>`
- [ ] `skillm library unset-remote` → `git branch --unset-upstream`

**Cross-library search & install:**

- [ ] `skillm search` scans tags from all libraries (parse tag prefix)
- [ ] `skillm install <name>` → unique match: auto-install; ambiguous: interactive selection
- [ ] `skillm install <name> --library <lib>` → explicit library selection

**Pull — selective library subscription:**

- [ ] `skillm pull <remote> --library <name>` → fetch specific remote branch + track
- [ ] `skillm pull <remote> --library <name> --as <local-name>` → rename on conflict
- [ ] Pull multiple: `--library infra,ai`

**Push:**

- [ ] `skillm push` → push current branch + tags to tracked remote
- [ ] `skillm push <remote>` → push to specified remote (sets up tracking if untracked)
- [ ] `skillm push <remote> --as <branch>` → push to different remote branch name

**Verification:**

- [ ] Test: default init creates `main` branch, `add` works without explicit library create
- [ ] Test: `library create` creates orphan branch with init commit
- [ ] Test: three-level tags created correctly on add
- [ ] Test: create two libraries, add same-name skill to each, search finds both
- [ ] Test: install from non-active library works without switching
- [ ] Test: ambiguous install triggers selection (or `--library` resolves)
- [ ] Test: pull specific library from remote, verify local branch + tracking
- [ ] Test: pull with `--as` rename, verify tracking is correct
- [ ] Test: push sets up tracking for untracked library
- [ ] Test: push `--as` creates different branch name on remote
- [ ] Test: `library set-remote` / `unset-remote` changes tracking
- [ ] Test: `library list` shows correct tracking, counts, sync status
- [ ] Test: tag migration from two-level to three-level format
- [ ] Test: `rebuild()` indexes skills from all libraries, not just active

### Phase 4: Publish pipeline — normalize, analyze, generate

**Problem 1:** SKILL.md has multiple metadata formats (YAML frontmatter,
HTML comment block, implicit heading/paragraph). After `pull` + `rebuild`,
data not in SKILL.md (manual tags, categories) is lost.

**Problem 2:** Skills often have undeclared dependencies. Authors forget
to list required bins, packages, or env vars. `skillm check` detects
them after the fact, but they should be captured at publish time.

**Solution:** `publish` becomes a full normalization pipeline.  All metadata
is consolidated into a canonical YAML frontmatter format, and dependency
analysis is run automatically.

#### Publish pipeline

```
Original SKILL.md (any format)
        │
        ▼
1. extract_metadata()         read from any format
        │
        ▼
2. scan_skill_content()       scan code blocks for bins, packages, env vars
        │
        ▼
3. diff_requires()            compare declared vs detected
        │
        ▼
4. merge requires             union of declared + detected
        │
        ▼
5. normalize_skill_md()       rewrite as canonical YAML frontmatter
        │
        ▼
6. git add + commit + tag     store the normalized version (three-level tag)
```

#### Canonical SKILL.md format (output)

```yaml
---
name: web-scraper
description: Scrape and parse websites
tags: [web, scraping, python]
category: devops
author: hren
requires:
  tools: [python3, curl, jq]
  env: [API_KEY, DATABASE_URL]
  skills: [git-workflow]
---

## Instructions

Do the thing.
```

No matter what the input format is, the stored version always looks like this.

Language-specific package dependencies live in their own standard files
inside the skill directory — not in SKILL.md:

```
my-skill/
├── SKILL.md                # requires: {tools, env, skills}
├── requirements.txt        # Python packages (pip standard)
├── package.json            # Node packages (npm standard)
└── scripts/
    └── helper.py
```

#### Requires fields

`requires` only declares **preconditions that skillm itself checks**.
Language package deps use their ecosystem's native format.

| Field | Purpose | Auto-detect? | Check method |
|---|---|---|---|
| `tools` | System CLI binaries | Yes — scan code blocks | `which` |
| `env` | Environment variables | Yes — scan $VAR refs | `os.environ` |
| `skills` | Other skill dependencies | No — author declares | library lookup |

#### Tasks

**Normalization & write-back:**

- [ ] `normalize_skill_md(path, meta)` — rewrite SKILL.md with canonical YAML frontmatter, preserve body content
- [ ] Handle all input formats: YAML frontmatter, `<!-- skillm:meta -->` block, bare markdown
- [ ] Strip old metadata format after normalization (don't leave duplicate comment blocks)
- [ ] Call `normalize_skill_md` in `Library.publish()` before `put_skill_files`

**Dependency analysis (auto-generate `requires`):**

- [ ] Run `scan_skill_content()` during publish (currently only in CLI `add_cmd`)
- [ ] Move scan + diff + merge logic from `cli.py` into `core.py` (publish pipeline)
- [ ] Auto-populate `requires.tools` from detected binary usage (`curl`, `python3`, `jq`, etc.)
- [ ] Auto-populate `requires.env` from detected `$ENV_VAR` references
- [ ] Scan `.py` files for non-stdlib imports; warn if `requirements.txt` missing or incomplete
- [ ] Scan `.js`/`.ts` files for imports; warn if `package.json` missing
- [ ] Scan `.sh` files for binary usage; merge into `requires.tools`
- [ ] Auto-generate `requirements.txt` from `.py` imports if missing (opt-in via `--generate-deps`)
- [ ] Merge detected with explicitly declared (don't overwrite author's declarations)
- [ ] Option to skip auto-detection: `skillm add --no-scan`

**Metadata-modifying commands write to SKILL.md:**

- [ ] `skillm tag <name> <tags...>` → update SKILL.md frontmatter `tags` field, git add + commit
- [ ] `skillm untag <name> <tags...>` → update SKILL.md frontmatter, git add + commit
- [ ] `skillm categorize <name> <cat>` → update SKILL.md frontmatter `category` field, git add + commit

**Verification:**

- [ ] `rebuild()` fully reconstructs all metadata from SKILL.md alone
- [ ] Test: publish → tag → push → pull → verify tags preserved
- [ ] Test: publish → categorize → rebuild → verify category preserved
- [ ] Test: publish skill with `<!-- skillm:meta -->` format → verify stored as YAML frontmatter
- [ ] Test: publish skill with undeclared `curl` usage → verify `requires.tools` contains `curl`
- [ ] Test: publish skill with `$API_KEY` reference → verify `requires.env` contains `API_KEY`
- [ ] Test: publish skill with `requirements.txt` → verify file preserved in library

### Phase 5: Documentation & migration

- [ ] Update `docs/DESIGN.md` to reflect v2 architecture
- [ ] Write migration guide for v1 → v2 (existing libraries)
- [ ] `skillm migrate` command: convert v1 directory-per-version layout to git tags
- [ ] Update `docs/FRONTMATTER.md` if new fields are added

### Phase 6: Polish

- [ ] `skillm log <name>` — show git log for a skill (commit history)
- [ ] `skillm diff <name>` — show uncommitted changes for a skill
- [ ] Handle git merge conflicts gracefully on `pull`
- [ ] Warn if pushing to a remote that has diverged
- [ ] Shell completions for remote names + library names

---

## CLI Command Summary

| Command | Git operation |
|---|---|
| `library create <name>` | `git checkout --orphan <name>` |
| `library switch <name>` | `git checkout <name>` |
| `library list` | `git branch -a` + tag stats |
| `library delete <name>` | `git branch -D <name>` |
| `library set-remote <remote>` | `git branch -u <remote>/<branch>` |
| `library unset-remote` | `git branch --unset-upstream` |
| `remote add <name> <url>` | `git remote add` |
| `remote rm <name>` | `git remote remove` |
| `remote list` | `git remote -v` |
| `pull <remote> --library <name>` | `git fetch <remote> <branch>` + track |
| `pull <remote> --library <name> --as <local>` | fetch + create local branch with different name |
| `push` | `git push <tracked-remote> <branch> --tags` |
| `push <remote>` | `git push -u <remote> <branch> --tags` |
| `push <remote> --as <branch>` | `git push <remote> local:branch --tags` |
| `add <dir>` | copy + `git add` + commit + tag (`lib/skill/ver`) |
| `search <query>` | scan tags across all libraries |
| `install <name>` | extract from tag (interactive if ambiguous) |

---

## Key Invariants

1. **SKILL.md is truth, SQLite is cache.** Any data in SQLite must be
   derivable from SKILL.md files + git tags. `rebuild()` must produce
   an identical database.

2. **Git is the sync protocol.** No custom file-transfer code.
   Local path, SSH, HTTPS — git handles it all.

3. **Branch = Library.** Each git branch is a skill library. One active
   at a time. Tags use three-level namespace: `library/skill/version`.

4. **Search is global, write is local.** Search and install work across
   all libraries. Add, publish, tag operate on the active library only.

5. **Users never touch git directly.** All git operations are wrapped
   by skillm commands.
