---
name: harness-evolve
description: >-
  Improve the harness itself — its orchestration skill and its agent-team
  definitions — from real signals: failed quality gates, repeated user
  corrections, agents that missed scope, friction, and slow paths. Use after a
  rough task, when the team underperformed, or on request to tune it. Reads the
  harness source, diagnoses the cause, proposes minimal edits, applies the
  approved ones to the committed source, reinstalls to the global config, and
  logs the change. Triggers: /harness-evolve, "evolve the harness", "improve the team",
  "tune the agents", "why did the team do that".
---

# Harness-evolve — the self-improvement loop

The harness earns its keep by getting better from use. This skill is how. It
changes the team's *definitions* (the `harness`/`harness-evolve` skills and the
`agents/*.md` files), from evidence, one cause at a time.

**Evolve from signals, not vibes.** Only change a definition when a concrete
signal shows the current definition caused the problem. "It could be better" is
not a signal; "the reviewer kept flagging style and missed a null deref" is.

## Where the source lives

The repo (`skills/`, `agents/`) is the source of truth and `~/.claude/` is an
install of it. Edit the repo source, then run `bash install.sh`; never edit the
installed copy, which is lost when the container is reclaimed.

## The loop

### 1. Collect signals
Gather concrete evidence from the session(s) at hand:
- A quality gate that failed or was bypassed.
- A correction the user had to give more than once.
- An agent that returned off-scope, incomplete, or wrong output.
- A dead end, a long detour, or work that had to be redone.
- A routing mistake (wrong agent, or a trivial task over-delegated).

If there is no concrete signal, stop and say so — there is nothing to evolve.

### 2. Diagnose
For each signal, name the cause and locate it in a definition: a missing
instruction, a vague boundary, an over-broad trigger, a wrong tool grant, a
missing gate. One cause → one change.

### 3. Propose
Write the minimal edit that removes the cause. Prefer sharpening an existing
instruction over adding a new rule. Show the user the proposed diff with a one-
line "because <signal>". For anything that changes team *behavior* (a new gate,
a changed boundary, adding/removing an agent), confirm before applying.

### 4. Apply
Edit the repo source. Keep changes small and reversible.

### 5. Reinstall & log
Run `bash install.sh` so the change is live, append an entry to `CHANGELOG.md`, and — if the user wants it
persisted — commit the source and changelog.

## Guardrails (never evolve these away)

- Never weaken or remove a quality gate in `skills/harness/SKILL.md`, or an
  agent's boundary against skipping or weakening tests.
- Don't add process the evidence doesn't justify. Ceremony is a cost.
- Don't delete or gut an agent without a signal that it's the problem.
- One change per cause; no opportunistic rewrites riding along.
- Preserve each agent's output contract and scope boundary unless that's the
  thing being fixed.

## Output

A short report: the signals, the cause of each, the exact edits made (or
proposed and awaiting confirmation), and the `CHANGELOG.md` entry. Keep it to
what changed and why.
