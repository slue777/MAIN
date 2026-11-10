# MAIN — Claude Code harness

A general-purpose software-development **agent harness** for Claude Code: a team
of specialized subagents plus the orchestration and self-improvement skills that
drive them. This repo is the source of truth; `install.sh` installs it into the
global Claude Code config at `~/.claude/`.

## What's in here

```
skills/
  harness/SKILL.md     orchestration — how the conductor runs the team
  evolve/SKILL.md      self-improvement loop (installs as "harness-evolve")
agents/                one file per specialist (roster: skills/harness/SKILL.md)
install.sh             copy the above into ~/.claude/ (skills + agents)
CHANGELOG.md           evolve log — what the team changed about itself and why
```

## Install

```bash
bash install.sh
```

Installs every skill under `skills/` and every agent under `agents/` into
`~/.claude/`. Re-run after editing, adding or deleting anything there to push
the change live. Override the target with `CLAUDE_HOME=/path bash install.sh`.

`~/.claude/` is **not** version-controlled and is wiped when a cloud container is
reclaimed — always edit the source in this repo and reinstall, never the
installed copy.

## Use

- **`/harness`** (or "use the harness" / "run the team") — run a task through
  the agent team. See `skills/harness/SKILL.md`.
- **`/harness-evolve`** (or "improve the team") — tune the team's own
  definitions from real signals. See `skills/evolve/SKILL.md`.

## How it works

The main Claude session acts as the **conductor**: it does trivial work itself
and delegates substantial pieces to subagents via the `Agent` tool, running
independent ones in parallel. The harness is the operating manual for that; the
agents are the specialists; `harness-evolve` is how the whole thing gets better
from use. See `skills/harness/SKILL.md` for the full pipeline and gates.
