---
name: moose-build
description: Drive a MOOSE feature from a structured spec.md to a green tree, then gate its docs — by handing the implement↔verify loop to the goal-driven moose-feature-loop agent and the docs to the moose-docs-writer loop. Replaces /moose-build-feature and /moose-build-core. Runs unattended (gold is regenerated and staged for post-hoc review); surfaces only at genuine decision points.
disable-model-invocation: true
---

# /moose-build

Take a structured `spec.md` (from `/moose-design-feature`) to **build clean + new regression tests green**, then run the **docs gate**. This skill is thin: it compiles the goal, spawns the autonomous `moose-feature-loop`, runs the docs loop, and reports.

## Usage

```
/moose-build [path/to/spec.md] [--core]
```

- Defaults to `<worktree-root>/specs/spec.md`. Spec format from `/moose-design-feature` (Summary / Physics / Reuse decisions / Test plan / Doc plan / Out of scope); freeform accepted with reduced fidelity.
- `--core` = **slim mode**: skip the docs gate entirely (use when the feature adds no registered syntax and no doc page). Refuse `--core` if the spec's `## Doc plan` section says `**Needed:** yes`.
- **Assumes the user already ran `/new-feature`** and is inside that worktree. Refuse otherwise.

## How it's wired

```
/moose-build (this skill, main thread — owns the human touchpoints)
  └─ moose-feature-loop (agent)         goal-driven: build clean + tests green, unattended
       ├─ moose-implementer             C++/Python
       ├─ moose-test-writer / unit      regression specs + .i / gtest
       ├─ moose-test-runner             build + run + diagnose + autonomous gold regen
       └─ moose-scout                   one-shot recon on NEEDS_CONTEXT
  └─ moose-docs-writer (agent)          docs gate, only after GOAL_MET (docs on)
       └─ moose-docs-builder            nested smoke gate
```
## Steps

### 1. Read spec + compile the goal slice

1. Resolve the spec path (arg or `<worktree-root>/specs/spec.md`; also accept a legacy `<worktree-root>/spec.md` if the new path is absent). Refuse if missing: *"No spec found. Run `/moose-design-feature` first."*
2. Detect the worktree root (walk up for a `.git` **file** beside a `moose/`+`blackbear/`+`isopod/` layout). Refuse if not in a feature worktree.
3. Detect format: **structured** (the six headings) → parse directly; **freeform** → infer + one `AskUserQuestion` to confirm `{repo, kind, files, unit-tests, docs}`.
4. Extract the **spec slice** for the loop: `repo`, `object_kind`, `files_to_touch`, `scope`, `reuse_decisions[]`, `test_plan[]` (Tester kind + asserted behavior + mutation rationale, verbatim), `out_of_scope[]`, `unit_on` (any `unit/` in files), `reuse_only` (every reuse decision is `Reuse as-is`).
5. Resolve **mode**: `--core`, or the `## Doc plan` section's `**Needed:**` line is `no` → no docs-writer; `**Needed:** yes` → docs on. **Refuse `--core` when `**Needed:** yes`** (don't silently demote — the user picked the wrong flag).
6. Set `caps`: `impl_iters` = 5 (`--core`) or 10 (full); `no_progress` = 2. Pick a `run_label` = `moose-<feature>` (worktree dir name).

### 2. Run the feature loop (unattended)

Spawn **one** `moose-feature-loop` (`Agent`, `subagent_type: "moose-feature-loop"`) in background always, passing the spec slice + `caps` + `run_label`. Briefly tell the user the goal, the criteria it'll burn down, and the §Caveats. Then let it run.

Act on its terminal return:

| Loop returns | Action |
|---|---|
| `GOAL_MET` | → step 3 (docs gate). Carry its report (files, commands, test counts, **staged gold + observed values**) forward. |
| `NEEDS_DESIGN(reason)` | Stop. Tell the user: *"The spec needs a design change: `<reason>`. Re-run `/moose-design-feature` to revise, then `/moose-build` again."* |
| `BLOCKED(reason)` | Stop. Surface the blocker + the exact fix command (usually env: conda / missing `*-opt`). Don't auto-fix. |
| `STALLED(state)` | Surface the unmet criteria + what was tried each round. `AskUserQuestion`: extend the cap (by how much) / simplify the spec / abandon. On extend, re-spawn the loop with a higher `impl_iters` and its prior state. |

### 3. Docs gate (only after `GOAL_MET`; skip entirely in `--core`)

**Docs ON** — the tree is green and built, so wake/spawn `moose-docs-writer` with the `scope`, base branch (`devel`), public surface, and final doc paths. It **owns** the gate: authors pages and runs its nested write→smoke→fix loop (cap 3, inside docs-writer). Act on its return:

| `docs-writer` returns | Action |
|---|---|
| `DOCS_GREEN` (`PASS` / `PASS_WITH_WARNINGS`) | → step 4. Carry warnings into the report. |
| `NEEDS_CPP_CHANGE` | Spawn a one-shot `moose-implementer` for exactly the named C++ fix (`addClassDescription` / renamed `!syntax`), then a one-shot `moose-test-runner` (*authorized to build: `cd <scope> && make -j 6`*) to confirm the suite still passes, then wake `docs-writer` to re-run its gate. No ping-pong — one C++ hop. |
| `DONE_WITH_CONCERNS` (still red after 3 doc-side rounds) | `AskUserQuestion`: extend doc budget / escalate to implementer / ship with `DONE_WITH_CONCERNS`. |
| `BLOCKED` | Surface — likely env. Don't auto-fix. |

**Docs OFF (full mode, no pages authored)** — C++ renames can still break `!syntax` in untouched pages. Spawn `moose-docs-builder` directly with `scope` + base branch (`devel`):

| `docs-builder` report | Action |
|---|---|
| `PASS` / `PASS_WITH_WARNINGS` | → step 4 (carry warnings). |
| `FAIL` (`cpp-side`) | Spawn a one-shot `moose-implementer` for the named `!syntax` regression, then a one-shot `moose-test-runner` (*"Run tests in `<scope>` `--re=<new-test-names>`. You are authorized to build: `cd <scope> && make -j 6`."*) to confirm the rebuilt suite still passes, then re-smoke. The late edit is a doc-driven `!syntax`/`addClassDescription` fix only (no logic change), so the regression re-run is sufficient re-verification. |
| `FAIL` (`doc-side`) | Surface to the user: a `.md` in this branch's diff is broken (shortcode / `!listing` / citation / `!syntax` path), but docs were off so no `docs-writer` ran — needs a manual fix or a re-run with docs on. Don't auto-fix. |
| `BLOCKED` | Surface. Don't auto-fix. |

### 4. Final report

- Files created / modified (per child).
- Exact commands `test-runner` ran; final test counts (pass / fail / skip).
- **Gold files regenerated + their observed values** — flagged for the user to sanity-check the physics.
- Docs result (smoke PASS / warnings / log path), or "docs skipped (`--core`)".
- Any `DONE_WITH_CONCERNS` across the run.
- Suggested commit message. **Do not commit.**

## Caveats to surface up front

- Runs **unattended**: gold is regenerated and **staged** (never committed) — review it in the final diff before you commit.
- Style isn't gate-checked (the pre-commit hook handles it on commit).
- Docs **build** is gated (smoke build, errors filtered to the branch diff); doc **quality** isn't — warnings are surfaced for manual review. `--core` skips the docs gate entirely.
- Smoke is slow: ~5–10 min/round, up to 3 fix rounds (inside `docs-writer`).
- Interrupt anytime; the loop narrates to the task list so you can watch and stop it.

## Hard constraints

- **Never commit or push.** The report includes a suggested commit message; that's it.
- **Never run `clang-format` / `black`.** The pre-commit hook handles style.
- **Don't create / destroy worktrees, branches, or conda envs.** That's `/new-feature`.
- **Don't do the loop's job here.** This skill spawns the loop and reacts to its terminal status — it does not route implement/test/run failures itself (that logic lives in `moose-feature-loop`).
- **Refuse `--core` when the spec needs docs.** No silent demotion.

## Canonical references

- `/moose-design-feature` — produces the `spec.md` this skill consumes. Match its `{repo, kind, files-to-touch}` vocabulary.
- `CLAUDE.md` — meta-repo submodule + branch rules.
- Wiring + ownership: the **How it's wired** diagram above.
