---
name: moose-build-feature
description: Spin up an agent team (implementer, test writer(s), docs writer, test runner) against a structured spec.md (typically produced by /moose-design-feature).
disable-model-invocation: true
---

# /moose-build-feature

Drive a feature end-to-end from a structured `spec.md` by spawning MOOSE subagents as named teammates and coordinating them over a **shared task list**. Stops when build is clean + new regression tests pass, or after **10** iterations.

## Usage

```
/moose-build-feature [path/to/spec.md]
```

Defaults to `<worktree-root>/spec.md`. Spec format produced by `/moose-design-feature` (Summary / Physics / Reuse decisions / Test plan / Doc plan / Out of scope). Freeform prose also accepted with reduced fidelity.

**Assumes user already ran `/new-feature`** and is in that worktree. Don't create one. **Recommend `/moose-design-feature` first** if no spec exists.

## Team

You are the **team lead**. There's one implicit team per session — you don't create or name it (`TeamCreate`/`TeamDelete` no longer exist; cleanup is automatic when the session ends). Spawn named teammates with `Agent` (give each a `name` + `subagent_type`), coordinate them through a **shared task list** (`TaskCreate` / `TaskUpdate` / `TaskList` / `TaskGet`), and route messages with `SendMessage`. The task list — not your prose — is the source of truth for who-does-what and what's done.

| Teammate | `subagent_type` | Role |
|---|---|---|
| `implementer` | `moose-implementer` | C++/Python under `<repo>/src` + `<repo>/include` |
| `test-writer` | `moose-test-writer` | Regression spec + `.i` |
| `unit-test-writer` | `moose-unit-test-writer` | gtest (only if spec needs it) |
| `docs-writer` | `moose-docs-writer` | `.md` under `<repo>/doc/content/` (only if Doc plan on); **owns the docs smoke gate** — spawns `moose-docs-builder` itself and loops write→smoke→fix until green |
| `test-runner` | `moose-test-runner` | Build + run + diagnose + gold regen |

`moose-docs-builder` is **not** a direct teammate when docs are on — `moose-docs-writer` spawns it as its own nested child to run the smoke gate. You (the lead) spawn `moose-docs-builder` directly **only when Doc plan is off** (a code-only `!syntax` smoke check — see 6a).

`moose-scout` is **not** a standing teammate — spawn it ad-hoc with `Agent` when a teammate reports `NEEDS_CONTEXT`, then forward its findings via `SendMessage`.

Do **not** bolt on a separate standards-check or PR-review pass — the green gates (new regression tests pass + docs smoke-build) are the done condition.

## Steps

### 1. Read spec + dispatch

1. Resolve spec path (arg or default). Refuse if missing: *"No spec found. Run `/moose-design-feature` first."*
2. Detect format: **structured** (has the six headings) → parse directly, skip confirmation; **freeform** → infer + one `AskUserQuestion` to confirm `{repo, kind, files, unit-tests, docs}`.
3. Extract dispatch from spec:
   - Repo, object kind, files-to-touch ← `## Summary`
   - Unit-tests on ← any `unit/` path in files
   - Docs on ← `## Doc plan` says `**Needed:** yes`
   - Reuse decisions, Test plan entries, Out of scope ← respective sections
4. **Reuse-only short-circuit:** if every Reuse decision is `Reuse as-is`, skip `implementer`. Tell user.

### 2. Set up the run

No team to create — the session *is* the team. Pick a short run label (`moose-feature-<feature>`, where `<feature>` = worktree dir name) to title your tasks and reports. Briefly tell the user the label, which teammates you'll spawn, and the caveats below.

### 3. Spawn teammates

Always: `implementer`, `test-writer`, `test-runner`.
Conditional: `unit-test-writer` (if `unit/` in files); `docs-writer` (if Doc plan on) — it spawns its own `moose-docs-builder` child for the smoke gate, so don't spawn one yourself.
Docs-off gate: if Doc plan is **off**, you spawn `docs-builder` directly at step 6 for a code-only `!syntax` smoke check.

Each spawn message includes spec contents + parsed dispatch (Reuse decisions + Out-of-scope as hard constraints). Don't re-state skill loads — teammate prompts handle that.

**Do not respawn within a run.** Wake idle teammates with `SendMessage`.

### 4. Seed the shared task list

The task list is the single source of truth for the run — every teammate reads it, claims work, and reports progress through it. Create one `TaskCreate` per work item below, then `TaskUpdate` each to set its `owner` and its `blockedBy` dependencies. Teammates move their task `pending → in_progress → completed` via `TaskUpdate`; you watch with `TaskList`/`TaskGet` and wake or route with `SendMessage`. For structured specs, copy entries verbatim — don't paraphrase:

- `iter-1: implement <feature>` — owner `implementer`. Body carries full Reuse + Out-of-scope. (Skip if reuse-only.)
- `iter-1: write test "<name>"` — **one per Test plan entry**, owner `test-writer` or `unit-test-writer`. Body carries Tester kind, asserted behavior, mutation rationale.
- `docs: write pages + pass smoke gate` — owner `docs-writer` (if Doc plan on). `blockedBy` the implementation loop going green — it `!listing`s against impl + test input *and* smokes against the built tree, so it runs at the docs gate (6a), **not** as a parallel iter-1 task. docs-writer authors the pages **and** runs its own nested smoke-gate loop, returning `DOCS_GREEN` or `NEEDS_CPP_CHANGE`.
- `iter-1: build + run new tests` — owner `test-runner`. `blockedBy` implementer + test-writers only.
- `final: smoke docs build (code-only)` — owner `docs-builder`, **only when Doc plan is off**. `blockedBy` the implementation loop going green.

Set the `blockedBy` edges explicitly so a task can't start before its inputs exist; an unblocked task left unassigned can be self-claimed by the teammate whose role matches. For freeform specs: same skeleton with one generic test task instead of one-per-entry.

### 5. Iterate (max 10 rounds)

#### 5a. Implementer (sequential, first)

`SendMessage` to `implementer` with spec (iter 1 only), `{repo, kind, files}`, and the previous iter's test-runner failure report (iter ≥ 2). Wait for task complete + idle.

#### 5b. Tests (parallel)

`SendMessage` in parallel to `test-writer` (+ `unit-test-writer`). Each reads implementer's output via `Read`. Wait for all complete.

Docs are deferred to the docs gate (step 6a): `docs-writer` both `!listing`s against impl source *and* test input **and** smoke-builds against a built, green tree — all of which only exist once the impl loop closes. Running it here would race the `*-opt` build and trip a false `cpp-side` FAIL.

#### 5c. Test runner

`SendMessage` to `test-runner` **with explicit build authorization** so it runs `make` instead of asking:

> Run tests in scope `<scope>`, restricting to `--re=<new-test-names>`.
> You are authorized to build: `cd <scope> && make -j 6`.
> If MISSING GOLD or structural DIFF, **do not** regen — just report.

Wait for its report.

#### 5d. Route test-runner report

| Result | Action |
|---|---|
| All OK, build clean | **Done** — go to 6 |
| Build error | `SendMessage implementer` with compiler output, new `iter-N+1` task |
| Real runtime error / segfault | `SendMessage implementer` |
| MISSING GOLD or structural DIFF | Pause for user (see 5e) |
| Tiny DIFF + tolerance suggestion | `SendMessage test-writer` |
| TIMEOUT | `SendMessage test-writer` (suggest `max_time` or `heavy`) |
| RACE | `SendMessage test-writer` (suggest `prereq` / `working_directory`) |
| Skip caveat | Surface to user — usually build/dep issue |
| `BLOCKED` | Halt, surface |
| `NEEDS_CONTEXT` | One-shot `moose-scout`, forward findings |

#### 5e. Gold-file pause

1. Show user the test-runner output (command, observed, gold).
2. Ask: *"Are these values correct? Approve gold regen?"*
3. On approve, `SendMessage test-runner` with regen task. It re-runs verbose, copies, re-runs to confirm, stages but **does not commit**.
4. If user says wrong → route to `implementer` instead.

### 6. Done

Stop the implementation loop when build clean + new tests pass. Then docs gate, then shutdown.

#### 6a. Docs smoke gate

**Docs ON** — now that the impl loop is green and the tree is built, wake/spawn `docs-writer` with the scope, base branch (`devel`), public surface, and final doc paths. It owns this gate: it authors the pages and runs the nested write→smoke→fix loop (cap 3 doc-side rounds, **inside** docs-writer). Act on what it returns:

| `docs-writer` returns | Action |
|---|---|
| `DOCS_GREEN` (`PASS` / `PASS_WITH_WARNINGS`) | → 6b. Carry any warnings into the final report. |
| `NEEDS_CPP_CHANGE` | Route **once** to `implementer` with the failing `!syntax` path / class / missing `addClassDescription` (does **not** count against the impl cap), then wake `docs-writer` to re-run its gate. No ping-pong. |
| `DONE_WITH_CONCERNS` (still red after 3 doc-side rounds) | Halt + ask user: extend the doc budget / escalate to `implementer` / ship with `DONE_WITH_CONCERNS`. |
| `BLOCKED` | Surface — likely env (missing conda / `*-opt`). Don't auto-fix. |

**Docs OFF** — no pages were authored, but C++ renames can still break `!syntax` in untouched pages. Spawn `docs-builder` yourself with scope + base branch (`devel`); it runs `/moose-docs-smoke <scope>` and filters errors against `git diff --name-only devel...HEAD`:

| `docs-builder` report | Action |
|---|---|
| `PASS` / `PASS_WITH_WARNINGS` | → 6b. Carry warnings into final report. |
| `FAIL` (always `cpp-side` here) | Route to `implementer` with the error lines — the break is a C++ `!syntax` regression. Re-smoke after the fix. |
| `BLOCKED` | Surface — likely env. Don't auto-fix. |

#### 6b. Shutdown

For each teammate: `SendMessage { type: "shutdown_request" }` and wait for the response. There's no `TeamDelete` — once every teammate has shut down the run is complete and the session cleans up automatically.

#### 6c. Final report

- Files created/modified per teammate
- Exact commands `test-runner` ran
- Final test counts (pass/fail/skip)
- Docs smoke result + log path + warnings
- Any `DONE_WITH_CONCERNS`
- Suggested commit message; **do not commit**

### 7. Iteration cap

If iter 10 ends red: stop dispatching, do **not** auto-shutdown. Summarize last failure + routing tried. Ask user: extend, simplify spec, or escalate.

## Failure handling

- `BLOCKED` → halt, surface, leave team intact for inspection.
- `NEEDS_CONTEXT` → one-shot `moose-scout`, package findings into `SendMessage`.
- `DONE_WITH_CONCERNS` → `TaskUpdate`, continue, surface in final report.

## Hard constraints

- **Never commit / push.** User owns commits.
- **Never run `clang-format` / `black`.** Pre-commit handles style.
- **Only `docs-builder` runs `moosedocs.py`.** Other teammates are forbidden.
- **Don't create/destroy worktrees / branches / conda envs.** That's `/new-feature`.
- **Don't substitute for a teammate** — even one-line edits go through the right one.
- **Don't respawn teammates.** Wake with `SendMessage`.
- **Don't loop on the same failure** > 2-3 iters without surfacing.

## Caveats to surface up front

After spawning teammates, before iter 1, tell user:

- Style isn't gate-checked (pre-commit handles on commit).
- Docs **build** is gated (smoke build, errors filtered to diff). Doc **quality** isn't — warnings surfaced for manual review.
- Smoke is slow: ~5–10 min/round, up to 3 fix rounds (run inside `docs-writer`) → worst case ~20–30 min on top of impl. Bump with `SMOKE_TIMEOUT=N`.
- Run state lives in the session's shared task list; a crash mid-run loses in-flight iteration history.
- Interrupt anytime; resume picks up open tasks.

## Canonical references

- Each agent's `.md` in `.claude/agents/` — workflow + constraints.
- `moose-test-runner` encodes the build/run/diagnose/gold-regen flowchart — trust it.
- `CLAUDE.md` for meta-repo submodule + branch rules.
