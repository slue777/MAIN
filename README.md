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
agents/
  planner.md           plans a non-trivial task before any code
  researcher.md        maps the codebase / gathers external facts (read-only)
  implementer.md       writes the real, working code for a step
  tester.md            adds & runs tests; keeps the suite honestly green
  reviewer.md          adversarial correctness review of a diff (read-only)
  debugger.md          roots out stubborn failures the first try missed
install.sh             copy the above into ~/.claude/ (skills + agents)
CHANGELOG.md           evolve log — what the team changed about itself and why
```

## Install

```bash
bash install.sh
```

Installs the two skills (`harness`, `harness-evolve`) and all six agents into
`~/.claude/`. Re-run after editing anything under `skills/` or `agents/` to push
the change live. Override the target with `CLAUDE_HOME=/path bash install.sh`.

`~/.claude/` is **not** version-controlled and is wiped when a cloud container is
reclaimed — always edit the source in this repo and reinstall, never the
installed copy.

## Use

- **`/harness`** (or "use the harness" / "run the team") — the conductor frames
  the task, routes each part to the right specialist, holds the quality gates
  (plan → implement → test → review → report), and reports what was verified.
- **`/evolve`** (or "improve the team") — turns real signals (failed gates,
  repeated corrections, missed scope, wasted detours) into minimal, logged edits
  to the team's own definitions.

## How it works

The main Claude session acts as the **conductor**: it does trivial work itself
and delegates substantial pieces to subagents via the `Agent` tool, running
independent ones in parallel. The harness is the operating manual for that; the
agents are the specialists; `harness-evolve` is how the whole thing gets better
from use. See `skills/harness/SKILL.md` for the full pipeline and gates.
