---
name: moose-build
description: Drive a MOOSE feature from a structured specs/blueprint.html to a green tree, then gate its docs — by handing the implement↔verify loop to the goal-driven moose-feature-loop agent and the docs to the moose-docs-writer loop. Runs unattended (gold is regenerated and staged for post-hoc review); surfaces only at genuine decision points.
disable-model-invocation: true
---

# /moose-build

Take a blueprint (`specs/blueprint.html`, from `/moose-blueprint`) to build clean + new regression tests green, then run the docs gate. This skill is deliberately thin: compile the goal, spawn the autonomous `moose-feature-loop`, run the docs gate, report. Don't route implement/test/run failures yourself — that logic lives inside `moose-feature-loop`; you react only to its terminal status.

## Usage

```
/moose-build [path/to/blueprint.html] [--core]
```

- Blueprint defaults to `<worktree-root>/specs/blueprint.html` (accept a legacy `specs/spec.md` or `<worktree-root>/spec.md` from pre-rename worktrees). Missing → refuse: *"No blueprint found. Run `/moose-blueprint` first."*
- Structured blueprint = the six `/moose-blueprint` contract blocks (`#summary` / `#physics` / `#reuse-decisions` / `#test-plan` / `#doc-plan` / `#out-of-scope` element ids) → parse directly. Freeform HTML or legacy spec.md → infer, then confirm `{repo, kind, files, unit-tests, docs}` with one `AskUserQuestion`.
- `--core` = slim mode: skip the docs gate entirely (for features adding no registered syntax and no doc page). Refuse `--core` when the blueprint's `#doc-plan` says `Needed: yes` — no silent demotion; the user picked the wrong flag.
- Requires a `/new-feature` worktree: walk up for a `.git` **file** beside a `moose/`+`blackbear/`+`isopod/` layout; refuse otherwise.

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

## 1. Compile the goal slice

Extract from the blueprint: `repo`, `object_kind`, `files_to_touch`, `scope` (the top-level submodule of `repo`; `moose/modules/<m>` → `moose`), `summary` + `physics` (verbatim text of the `#summary`/`#physics` blocks — the iter-1 implementer payload; if KaTeX is already rendered, recover TeX from the `<annotation encoding="application/x-tex">` nodes, and Grep by block id rather than whole-file-Read the font-bloated HTML), `reuse_decisions[]`, `test_plan[]` (Tester kind + asserted behavior + mutation rationale, verbatim), `out_of_scope[]`, `unit_on` (any `gtest` test-plan entry or `unit/` path in files), `reuse_only` (`reuse_decisions[]` is non-empty AND every decision is `Reuse` — a negative-search record alone is NOT reuse-only), `blueprint_path`.

Mode: docs on unless `--core` or `#doc-plan`'s `Needed:` field is `no`. Caps: `impl_iters` = 5 (`--core`) or 10 (full), `no_progress` = 2. `run_label` = `moose-<feature>` (worktree dir name).

## 2. Run the feature loop (unattended)

Spawn one `moose-feature-loop` (`Agent`, `subagent_type: "moose-feature-loop"`, always background) with the spec slice + caps + `run_label`. Briefly tell the user the goal, the criteria it will burn down, and the §Caveats — then let it run. Act on its terminal return:

| Loop returns | Action |
|---|---|
| `GOAL_MET` | → docs gate. Carry its report (files, commands, test counts, **staged gold + observed values**) forward. |
| `NEEDS_DESIGN(reason)` | Stop. Tell the user: *"The blueprint needs a design change: `<reason>`. Re-run `/moose-blueprint` to revise, then `/moose-build` again."* |
| `BLOCKED(reason)` | Stop. Surface the blocker + the exact fix command (usually env: conda / missing `*-opt`). Don't auto-fix. |
| `STALLED(state)` | Surface the unmet criteria + what was tried each round. `AskUserQuestion`: extend the cap (by how much) / simplify the spec / abandon. On extend, re-spawn the loop with a higher `impl_iters` and its prior state. |

## 3. Docs gate (after `GOAL_MET`; skipped by `--core`)

**Docs ON** — wake/spawn `moose-docs-writer` with `scope`, base branch (`devel`), public surface, and final doc paths. It owns the gate: authors pages and runs its nested write→smoke→fix loop (cap 3).

| `docs-writer` returns | Action |
|---|---|
| `DOCS_GREEN` (`PASS` / `PASS_WITH_WARNINGS`) | → report; carry warnings. |
| `NEEDS_CPP_CHANGE` | One C++ hop, no ping-pong: spawn a one-shot `moose-implementer` for exactly the named fix (`addClassDescription` / renamed `!syntax`), then a one-shot `moose-test-runner` (authorized to build: `cd <scope> && make -j 6`) to confirm the suite still passes, then wake `docs-writer` to re-run its gate. |
| `DONE_WITH_CONCERNS` (still red after 3 doc-side rounds) | `AskUserQuestion`: extend doc budget / escalate to implementer / ship with `DONE_WITH_CONCERNS`. |
| `BLOCKED` | Surface — likely env. Don't auto-fix. |

**Docs OFF (full mode, no pages authored)** — C++ renames can still break `!syntax` in untouched pages, so spawn `moose-docs-builder` directly with `scope` + base branch (`devel`):

| `docs-builder` report | Action |
|---|---|
| `PASS` / `PASS_WITH_WARNINGS` | → report; carry warnings. |
| `FAIL` (`cpp-side`) | One-shot `moose-implementer` for the named `!syntax` regression, then one-shot `moose-test-runner` (*"Run tests in `<scope>` `--re=<new-test-names>`. You are authorized to build: `cd <scope> && make -j 6`."*), then re-smoke. The late edit is a doc-driven `!syntax`/`addClassDescription` fix with no logic change, so the regression re-run is sufficient re-verification. |
| `FAIL` (`doc-side`) | Surface: a `.md` in the branch diff is broken (shortcode / `!listing` / citation / `!syntax` path) but docs were off, so no `docs-writer` ran — needs a manual fix or a re-run with docs on. |
| `BLOCKED` | Surface. Don't auto-fix. |

## 4. Final report

Files created/modified per child; exact `test-runner` commands + final counts (pass/fail/skip); **gold files regenerated + their observed values**, flagged for the user to sanity-check the physics; docs result (smoke PASS / warnings / log path, or "docs skipped (`--core`)"); any `DONE_WITH_CONCERNS`; a suggested commit message.

## Caveats + boundaries

- **Never commit or push** — the run ends at the suggested commit message. Gold is regenerated and **staged**, never committed; the user reviews it in the final diff.
- **Never run `clang-format`/`black`** — the pre-commit hook owns style; it isn't gate-checked here.
- Worktrees, branches, and conda envs are `/new-feature`'s job — don't create or destroy them.
- Docs *build* is gated (smoke build, errors filtered to the branch diff); doc *quality* isn't — warnings surface for manual review. Smoke is slow: ~5–10 min/round, up to 3 fix rounds inside `docs-writer`.
- Interruptible anytime: the loop narrates to the task list so the user can watch and stop it.
