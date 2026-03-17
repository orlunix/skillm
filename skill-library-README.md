# Peregrine Skill Library

Shared AI coding skills for the Peregrine team.

This repo contains reusable skills — instructions, tools, and prompts — that AI coding agents (Claude Code, Cursor, Codex, OpenClaw) can follow. Skills are managed with [skillm](https://github.com/orlunix/skillm).

## Getting Started

```bash
# Clone this repo (one-time)
skillm repo add peregrine https://oauth2:<YOUR_GITLAB_TOKEN>@gitlab-master.nvidia.com/peregrine/tools/ai/skill-library.git

# Browse what's available
skillm list

# Install a skill into your project
cd your-project/
skillm install tree-setup
```

## Browse

```bash
skillm list                      # all skills on current branch
skillm search "regression"       # search by keyword
skillm info tree-setup           # skill details
```

## Contributing a Skill

Skills follow the [Agent Skills specification](https://agentskills.io/specification).

1. Create a skill directory with a `SKILL.md`:

```
my-skill/
├── SKILL.md              # Required — metadata + instructions
├── scripts/              # Optional — executable code
├── references/           # Optional — documentation
├── assets/               # Optional — templates, resources
```

2. Write the `SKILL.md`:

```yaml
---
name: my-skill
description: Short description of what this skill does and when to use it.
compatibility: Requires python3 and P4PORT environment variable
metadata:
  author: your-name
  tags: relevant, tags
  category: infra
---

# My Skill

Instructions for the AI agent go here.
```

3. Publish:

```bash
skillm add ./my-skill/           # add to library, creates a commit
skillm push                      # share with the team
```

If you don't have push access to the main branch:

```bash
skillm push -b my-feature        # push to a new remote branch
```

Then create a merge request on GitLab.

## Sync

```bash
skillm pull                      # fetch + merge latest from remote
skillm pull --branch coding      # switch to a remote branch and pull
```

## Branches (TBD)

Branches can organize skills into collections. Two possible strategies:

- **By scope/category** — e.g. `infra`, `coding`, `ai`. Skills don't overlap, no merge conflicts. Simple but limits cross-category discovery.
- **By contribution** — everyone works on `main`, use feature branches for review. Skills are merged via MRs. Better visibility but requires review workflow.

Current branches:

| Branch | Description |
|--------|-------------|
| `main` | Default — all published skills |
| `infra` | Tree setup, build systems, regression, P4 workflows |
| `coding` | Code review, testing, refactoring patterns |
| `ai` | Model training, prompt engineering, evaluation |

> **Open question:** Should we use branches for categorization, or keep everything on `main` and use tags/categories in SKILL.md instead? Feedback welcome.
