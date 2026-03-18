# Development Decisions

Architectural decisions and planned changes for skillm.

## Drop Manual Versions — Use Git Commits

**Status:** Planned

**Decision:** Remove version strings (`v0.1`, `v0.2`) and git tags. Git commits are the version history.

**Current:** `skillm add` creates a new version (`v0.1` → `v0.2`) tracked via git tags. `skillm list` shows version strings.

**Target:**
- `skillm add ./my-skill/` — copies into repo, commits. First time creates, subsequent times overwrites. No version string.
- `skillm update` — removed. `add` is idempotent.
- `skillm list` — shows last commit date and short hash instead of version:

```
  Name              Updated      Commit    Description
  tree-setup        2026-03-15   a3f2b1c   Set up build tree
  p4-submit         2026-03-17   e1d4f8a   Submit changes via P4
```

**Why:** Version strings add complexity without value. Git already tracks history. `git log -- tree-setup/` shows full history. No need for a parallel versioning system.

## Link-Back on Add

**Status:** Planned

**Decision:** `skillm add ./my-skill/ --link-back` replaces the source directory with a symlink to the git-managed copy in the library repo.

**Flow:**
```bash
# First time — copies files into repo, replaces source with symlink
skillm add ./my-skill/ --link-back
# ./my-skill/ → ~/.skillm/repos/local/my-skill/

# Edit the skill (edits go to repo working tree via symlink)
vim ./my-skill/SKILL.md

# Push warns about uncommitted changes
skillm push
# Uncommitted changes in repo 'local':
#   modified: my-skill/SKILL.md
# Commit these first:
#   skillm add ./my-skill/

# User explicitly adds (commits the change)
skillm add ./my-skill/
skillm push    # clean, pushes
```

**Why:** Keeps edits in the git-managed repo automatically. User still explicitly commits via `skillm add`. Push checks for uncommitted changes and guides the user.

## Push Uncommitted Changes Check

**Status:** Planned

**Decision:** `skillm push` checks for uncommitted changes in the repo working tree. If found, lists changed skills and tells the user to `add` them first.

```
$ skillm push
Uncommitted changes in repo 'skill-lib':
  modified: tree-setup/SKILL.md
  modified: p4-submit/SKILL.md

Commit these changes first:
  skillm add ./tree-setup/
  skillm add ./p4-submit/
```

**Why:** Prevents pushing stale state. Keeps the commit-then-push workflow explicit and predictable.

## SKILL.md Format — Agent Skills Spec Alignment

**Status:** Docs updated, code not yet migrated

**Decision:** Align SKILL.md frontmatter with [agentskills.io spec](https://agentskills.io/specification).

**Mapping:**
| Old (top-level) | New (spec-aligned) |
|---|---|
| `author` | `metadata.author` |
| `tags` | `metadata.tags` |
| `category` | `metadata.category` |
| `source` | `metadata.source` |
| `requires` | `compatibility` (free text) + `metadata.requires-tools` |
| `disable-model-invocation` | `metadata.disable-model-invocation` |
| `argument-hint` | `metadata.argument-hint` |

**New top-level fields:** `license`, `compatibility`, `allowed-tools`

**Migration:** Read both old and new formats for backward compat. Write new format only.

## Soft Install as Default

**Status:** Done

**Decision:** `skillm install` defaults to soft (symlink). Use `--hard` for frozen copy. Specific version (`@v0.1`) forces hard.

## Global Install

**Status:** Done

**Decision:** `-g/--global` flag installs to `~/.claude/skills/` instead of project. Works with both soft and hard.

## Conflict Detection

**Status:** Done

**Decision:** Install warns if skill exists in parent dirs or global config. Uninstall removes from project + parent dirs; `-g` also removes global. Shows remaining copies.
