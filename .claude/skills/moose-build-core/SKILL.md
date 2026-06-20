---
name: moose-build-core
description: Slim sibling of /moose-build-feature. Spawns only implementer + test-writer + test-runner (no docs-writer, no docs-builder smoke gate). Use when the spec adds no new registered syntax and no new doc page.
disable-model-invocation: true
---

# /moose-build-core

Drive a feature end-to-end from a structured `spec.md` using the **smallest viable team**: implementer + test-writer + test-runner (+ conditional unit-test-writer). **No `docs-writer`, no `docs-builder` smoke gate.** Saves the 20–40 min worst-case smoke build and one full agent's worth of context.

Stops when the build is clean and the new regression tests pass, or after **5** iterations (then halts and surfaces state).

## When to use this instead of `/moose-build-feature`

| Situation | Use |
|---|---|
| New internal C++/Python with no public-syntax change, no new doc page | **`/moose-build-core`** |
| New registered MOOSE object exposed in input syntax, or new/edited doc page | `/moose-build-feature` (it runs the `!syntax` smoke gate) |
| Bug fix / parameter tweak / ≤2-file change | Just do it inline — neither skill is needed |

If you're unsure whether C++ renames in your diff could break `!syntax` in untouched doc pages: use `/moose-build-feature`. The smoke gate exists precisely for that risk.

## Usage

```
/moose-build-core [path/to/spec.md]
```

If no path is given, defaults to `<worktree-root>/spec.md` (where `/moose-design-feature` writes by default).

**Assumes the user already ran `/new-feature`** and is in that worktree.

## Team

You are the **team lead**. There's one implicit team per session — you don't create or name it (`TeamCreate`/`TeamDelete` no longer exist; cleanup is automatic on session exit). Spawn named teammates with `Agent` (each gets a `name` + `subagent_type`), coordinate them through a **shared task list** (`TaskCreate` / `TaskUpdate` / `TaskList` / `TaskGet`), and route with `SendMessage`. The task list — not your prose — is the source of truth for who-does-what and what's done.

| Teammate name | `subagent_type` | Role |
|---|---|---|
| `implementer` | `moose-implementer` | C++/Python under `<repo>/src` and `<repo>/include` |
| `test-writer` | `moose-test-writer` | Regression `tests` spec + `.i` input |
| `unit-test-writer` | `moose-unit-test-writer` | gtest under `unit/` — spawn only if spec calls for it |
| `test-runner` | `moose-test-runner` | Build (when authorized) + run + diagnose + gold regen |

`moose-scout` is **not** a standing teammate — spawn it ad-hoc with `Agent` when a teammate reports `NEEDS_CONTEXT`; forward its findings via `SendMessage`.

If the spec has `## Doc plan: yes`, refuse with: *"This spec calls for docs — use `/moose-build-feature` instead. `/moose-build-core` does not run the docs gate."* No silent demotion.

## Steps

### 1. Read the spec and dispatch

1. Resolve the spec path from `$ARGUMENTS` or default to `<worktree-root>/spec.md`. Refuse if missing.
2. `Read` the spec.
3. **Detect format.** Structured (Summary / Physics / Reuse decisions / Test plan / Doc plan / Out of scope) — parse directly. Freeform — infer `{repo, kind, files-to-touch, unit-tests on/off}` and confirm once with `AskUserQuestion`.
4. **Refuse if `## Doc plan` is yes** (see §Team). The user should run `/moose-build-feature` instead.
5. **Extract dispatch:** `repo`, `object kind`, `files to touch`, `unit-tests on/off` (on iff `unit/` is in files-to-touch), reuse decisions, test plan entries, out-of-scope items.
6. **Reuse-only short-circuit.** If `## Reuse decisions` is entirely `Reuse as-is`, skip `implementer`. Tell the user. Continue with test work only.

### 2. Set up the run

No team to create — the session *is* the team. Pick a short run label (`moose-core-<feature>`, where `<feature>` is the worktree directory name) to title your tasks and reports. Tell the user the label, which teammates you'll spawn, and the §Caveats.

### 3. Spawn teammates

Always:
- `implementer`
- `test-writer`
- `test-runner`

Conditional:
- `unit-test-writer` — iff files-to-touch contains a `unit/` path

Spawn via `Agent` with a `name` + `subagent_type`. Each spawn message carries the spec slice the teammate needs:
- `implementer`: Summary, Physics, Reuse decisions, Out of scope.
- `test-writer` / `unit-test-writer`: Summary, matching Test plan entry, Out of scope.
- `test-runner`: Summary + list of test names. Nothing else.

**Don't respawn teammates within a run.** Wake idle teammates with `SendMessage`.

### 4. Seed the shared task list

The task list is the single source of truth for the run — teammates read it, claim work, and report progress through it. `TaskCreate` one task per item below, then `TaskUpdate` each to set its `owner` and `blockedBy`. Teammates move their task `pending → in_progress → completed` via `TaskUpdate`; you watch with `TaskList`/`TaskGet` and wake or route with `SendMessage`.

- `iter-1: implement <feature>` — owner `implementer`. Body carries Reuse decisions + Out of scope. (Skip if reuse-only.)
- `iter-1: write test "<test_name>"` — one task per `## Test plan` entry, owner `test-writer` (or `unit-test-writer` if gtest). Body carries Tester kind, asserted behavior, mutation rationale.
- `iter-1: build + run new tests` — owner `test-runner`. `blockedBy` implementer + test-writer(s).

### 5. Iterate (max 5 rounds)

#### 5a. Implementer (always first, sequential)

`SendMessage` to `implementer` with the spec slice (iter 1 only) and, on iter ≥ 2, the previous round's structured failure report from `test-runner`. Wait for idle.

#### 5b. Tests (parallel)

`SendMessage` to `test-writer` and `unit-test-writer` (if spawned) in a single tool-call. Each reads the implementer's latest output. Wait for both to mark complete.

#### 5c. Test runner

`SendMessage` to `test-runner` with **explicit build authorization**:

> Run tests in scope `<scope>`, restricting to `--re=<new-test-name(s)>`.
> You are authorized to build the affected app first (`cd <scope> && make -j 6`).
> If any test produces a `MISSING GOLD FILE` status or a structural DIFF, do **not** regenerate gold yet — just report it.

Wait for completion.

#### 5d. Route the test-runner report

| Test-runner result | Action |
|---|---|
| All `OK` and build clean | **Done.** Exit loop → §6. |
| Build error | `SendMessage` to `implementer` with the compiler output |
| `*** ERROR ***` / segfault / mooseError flagged as real code bug | `SendMessage` to `implementer` with the runtime error |
| **MISSING GOLD FILE** or structural DIFF | Pause for user confirmation (see 5e) |
| Tiny DIFF with tolerance suggestion | `SendMessage` to `test-writer` with the suggested tolerance |
| TIMEOUT | `SendMessage` to `test-writer` (suggest `max_time` bump or `heavy = true`) |
| RACE | `SendMessage` to `test-writer` (suggest `prereq` / `working_directory` fix) |
| Skip caveat | Surface to user; usually env/build issue |
| Teammate `BLOCKED` | Halt loop, surface report |
| Teammate `NEEDS_CONTEXT` | Spawn `moose-scout` (one-shot), forward findings to the asker |

#### 5e. Gold-file pause

1. Show the test-runner output (run command, observed values, gold values if any).
2. Ask: *"Are these output values physically correct? Approve gold regeneration?"*
3. On approval, `SendMessage` to `test-runner` with **"Regenerate gold for `<test_name>`"**. The agent re-runs verbose, copies outputs to `gold/`, re-runs to confirm OK, stages but does **not** commit.
4. Continue the loop.

If values are wrong → route to `implementer` instead.

### 6. Done

Stop when **build clean + all new regression tests pass**.

1. Gracefully shut down each teammate: `SendMessage { to: <name>, message: { type: "shutdown_request" } }`. Wait for responses. There's no `TeamDelete` — once teammates have shut down the run is complete and the session cleans up automatically.
2. Final report:
   - Files created / modified (per teammate)
   - The exact commands `test-runner` ran
   - Final test counts (passed / failed / skipped)
   - Any `DONE_WITH_CONCERNS` flagged across the run
   - Suggested commit message; **do not commit**

### 7. Halt at iteration cap

If iteration 5 finishes without green:

1. Stop dispatching; **don't** auto-shut-down the teammates (leave them running for inspection).
2. Summarize the last iteration's failure, routing tried, unresolved blocker.
3. Ask: extend the budget (by how much), simplify the spec, or escalate. On extend, continue from where you stopped.

## Failure handling

- **`BLOCKED`** → halt, surface report, leave the teammates running for inspection.
- **`NEEDS_CONTEXT`** → spawn `moose-scout` ad-hoc via `Agent`; forward its cited findings to the asking teammate via `SendMessage`.
- **`DONE_WITH_CONCERNS`** → record in `TaskUpdate`, continue, surface in final report.

## Hard constraints

- **Never commit or push.** Final report includes a suggested commit message; that's it.
- **Never run `clang-format` / `black`.** Pre-commit hook handles style.
- **Never run `moosedocs.py`.** This skill has no docs gate; if you need one, the user picked the wrong skill — surface that, don't improvise.
- **Don't create or destroy worktrees / branches / conda envs.** That's `/new-feature`'s job.
- **Don't substitute for a teammate.** Even one-line edits go through the right teammate.
- **Don't respawn a teammate.** Wake idle teammates with `SendMessage`.
- **Don't loop on the same failure** more than 2–3 iterations without surfacing.

## Caveats to surface up front

After spawning teammates, before iteration 1, briefly tell the user:

- This is the **slim** path: no `docs-writer`, no `docs-builder` smoke gate. If your C++ renames could break `!syntax` in untouched doc pages, rerun with `/moose-build-feature`.
- Style isn't checked (pre-commit hook handles it on commit).
- Iteration cap is **5** rounds; on hit, surfaces state and asks before extending.
- Run state lives in the session's shared task list; a session crash loses in-flight iteration history.
- Interrupt at any time; on resume, picks up from the open tasks in the shared list.

## Canonical references

- `/moose-build-feature` SKILL.md — the full team workflow this one is derived from.
- Each teammate's own `.md` in `.claude/agents/` for its workflow and constraints.
- `moose-test-runner` already encodes the build/run/diagnose/gold-regen flowchart — trust its routing recommendations rather than re-deriving them.
- `CLAUDE.md` for the meta-repo's submodule + branch rules.
