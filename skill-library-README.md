# Peregrine Skill Library

Shared AI coding skills for the Peregrine team.

This repo contains reusable skills — instructions, tools, and prompts — that AI coding agents (Claude Code, Cursor, Codex, OpenClaw) can follow. Skills are managed with [skillm](https://github.com/orlunix/skillm).

## Branches

Each branch is a curated collection of related skills.

| Branch | Description |
|--------|-------------|
| `infra` | Tree setup, build systems, regression, P4 workflows |
| `coding` | Code review, testing, refactoring patterns |
| `ai` | Model training, prompt engineering, evaluation |

## Getting Started

```bash
# Clone this repo as "peregrine" (one-time)
skillm repo add peregrine https://oauth2:<YOUR_GITLAB_TOKEN>@gitlab-master.nvidia.com/peregrine/tools/ai/skill-library.git

# Switch to the branch you need
skillm branch infra

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

1. Create a skill directory with a `SKILL.md`:

```
my-skill/
├── SKILL.md              # Required
├── scripts/              # Optional
└── templates/            # Optional
```

2. Write the `SKILL.md`:

```yaml
---
name: my-skill
description: Short description of what this skill does
tags: [relevant, tags]
author: your-name
requires:
  tools: [python3]
  env: [P4PORT]
---

# My Skill

Instructions for the AI agent go here.
```

3. Publish:

```bash
skillm branch infra              # switch to the right branch
skillm add ./my-skill/           # add to library, creates a commit
skillm push                      # share with the team
```

If you don't have push access to the main branch:

```bash
skillm push -b my-feature        # push to a new remote branch
```

Then create a merge request on GitLab.

## Repo Structure

```
skill-library.git
├── branch: infra
│   ├── tree-setup/SKILL.md
│   ├── run-regression/SKILL.md
│   └── p4-submit/SKILL.md
├── branch: coding
│   ├── code-review/SKILL.md
│   └── test-patterns/SKILL.md
└── branch: ai
    └── prompt-eng/SKILL.md
```

Each skill is a directory at the repo root. Git history tracks all changes. Branches organize skills into collections.
