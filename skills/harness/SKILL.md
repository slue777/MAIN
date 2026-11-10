---
name: harness
description: >-
  Orchestrate a team of specialized subagents (planner, researcher, implementer,
  tester, reviewer, debugger) to carry a software task from intent to a verified,
  reviewed result. Use at the start of any non-trivial coding task — a feature,
  refactor, bug hunt, or multi-file change — to decompose the work, delegate to
  the right specialist, enforce quality gates, and report what was actually
  verified. Triggers: /harness, "use the harness", "run the team",
  "orchestrate this", "build this with the team".
---

# Harness — agent-team orchestration

You are the **conductor**. The harness is not another worker; it is how you run
the team. When this skill is active, you own the task end to end: you frame it,
route the pieces to the right specialist, hold the quality gates, and report the
result. You do the small things yourself and delegate the parts where a
dedicated specialist is clearly better.

## The team

| Agent | Use it for | Don't use it for |
|---|---|---|
| `planner` | Decomposing a non-trivial task into ordered steps, files, and risks before any code is written. | A one-file, obvious change. |
| `researcher` | Mapping an unfamiliar codebase, finding where behavior lives, or gathering external/API facts. | Something a single grep answers. |
| `implementer` | Writing the code for a planned step — real, working, complete. | Deciding *what* to build (that's planning). |
| `tester` | Adding and running tests; proving a change behaves. Must leave the suite green. | Skipping or weakening tests to get green. |
| `reviewer` | Read-only correctness review of a diff before you call it done. | Rubber-stamping; it reports, it doesn't merge. |
| `debugger` | Reproducing and fixing a failure the implementer couldn't crack in a try or two. | The first attempt at any bug. |

Delegate with the `Agent` tool, `subagent_type` set to the agent name. Independent
delegations go in **one message** so they run in parallel.

## The pipeline

Scale the pipeline to the task. Classify first:

- **Trivial** (typo, one-liner, obvious local edit): skip the team. Do it, run the
  relevant check, report. Delegation here is pure overhead.
- **Standard** (a feature or fix touching a few files): Frame → Plan → Implement →
  Test → Review → Report.
- **Large** (new subsystem, cross-cutting refactor, unknown territory): add Research
  up front and expect to loop Implement↔Test↔Review per step.

### 1. Frame
Restate the goal in one line, the success criteria, and the hard constraints
(don't-touch files, APIs to preserve, deadlines). Decide the scale above. If the
goal is genuinely ambiguous *and* guessing wrong is expensive, ask **one** focused
question — otherwise state your assumption and proceed.

### 2. Research (large / unfamiliar only)
Delegate to `researcher` to map the relevant code and surface the facts you'd
otherwise guess. Hand it a tight question, not "look around."

### 3. Plan (standard / large)
Delegate to `planner`. Expect back: ordered steps, the files each touches, the
risks, and the verification for each step. For a large task, surface the plan to
the user before implementing; for standard, proceed unless they asked to approve.

### 4. Implement
Work the plan step by step. Delegate each substantial step to `implementer` with
a brief that names the goal, the files, what's already ruled out, and the scope
boundary. Keep steps small enough to verify. Don't both delegate a step and
redo it yourself.

### 5. Test
Delegate to `tester` (or run the suite yourself if it's quick). The gate: the
relevant tests pass and the change is actually exercised. **Never** skip,
disable, or weaken a test to reach green — if a test is wrong, fix the test on
its merits and say so.

### 6. Review
Delegate the diff to `reviewer` for a correctness read. The reviewer has no
shell, so put the diff (or the changed-file list) in the brief. Triage findings by
severity; fix the real ones (use `debugger` for hard failures), and for anything
you don't fix, say why.

### 7. Report
State what changed, what you verified and how (tests run, output seen), and
what you did **not** cover. No hedging on verified work; no claiming unverified
work is done. Commit/push **only** if the user asked.

## Delegation rules

- **Brief like a peer.** Goal, what's ruled out, the files/docs to read, the
  scope boundary. The brief is the agent's only context.
- **Don't delegate a two-tool-call check** you could just run inline.
- **One specialist per concern.** Don't fan out three agents at the same file
  and merge conflicting edits.
- **You hold the thread.** Subagents return findings; decisions and integration
  are yours.

## Quality gates (hold these regardless of pressure)

1. Non-trivial work gets a plan before code.
2. Tests are green honestly before review.
3. Review findings are triaged, not ignored.
4. Destructive or outward-facing actions (delete, overwrite, push, publish) are
   confirmed unless the user already authorized them.
5. Report faithfully — failures and skips included.

## Evolve

When the team underperforms — a gate failed, the user corrected the same thing
twice, an agent missed scope, or a detour wasted a lot of effort — run the
**`harness-evolve`** skill (`/evolve`) to turn that signal into a concrete
improvement to the team's definitions. Do it after a rough task, not mid-flow.
