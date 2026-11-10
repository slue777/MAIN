# Harness changelog

`harness-evolve` appends to this log. Each entry: the signal, the cause, the
change, one line each.

## 2026-11-10 — Review fixes

- **Signal:** PR review — `planner`, `researcher`, `reviewer` were described as
  read-only but granted `Bash`. **Change:** dropped `Bash` from all three; the
  conductor now passes the diff to `reviewer` in the brief.
- **Signal:** PR review — `install.sh` left agents deleted from the repo
  installed, and replaced skills in place. **Change:** manifest-based removal of
  stale agents; skills are copied to a temp dir and swapped in.

## 2026-11-10 — Initial harness

- **New:** general-purpose SW-development agent team and orchestration.
  - Skills: `harness` (conductor / pipeline / quality gates),
    `harness-evolve` (evidence-driven self-improvement loop).
  - Agents: `planner`, `researcher`, `implementer`, `tester`, `reviewer`,
    `debugger` — each with a scoped role, method, and output contract.
  - `install.sh` installs repo source → `~/.claude/` (skills + agents).
- **Why:** bootstrap. No prior signals; this is the baseline the loop improves
  from.
