---
name: moose-build-feature
description: Spin up an agent team (implementer, test writer(s), docs writer, test runner) against a structured spec.md (typically produced by /moose-design-feature).
disable-model-invocation: true
---

# /moose-build-feature

Drive a feature end-to-end from a structured `spec.md` by creating a Claude Code team (`TeamCreate`) and orchestrating MOOSE subagents as named teammates over a shared task list. Stops when build is clean + new regression tests pass, or after **10** iterations.

## Usage

```
/moose-build-feature [path/to/spec.md]
```

Defaults to `<worktree-root>/spec.md`. Spec format produced by `/moose-design-feature` (Summary / Physics / Reuse decisions / Test plan / Doc plan / Out of scope). Freeform prose also accepted with reduced fidelity.

**Assumes user already ran `/new-feature`** and is in that worktree. Don't create one. **Recommend `/moose-design-feature` first** if no spec exists.

## Team

You are the team lead. Spawn named teammates via `Agent` (passing `team_name` + `name`), route via `SendMessage`, tear down when done.

| Teammate | `subagent_type` | Role |
|---|---|---|
| `implementer` | `moose-implementer` | C++/Python under `<repo>/src` + `<repo>/include` |
| `test-writer` | `moose-test-writer` | Regression spec + `.i` |
| `unit-test-writer` | `moose-unit-test-writer` | gtest (only if spec needs it) |
| `docs-writer` | `moose-docs-writer` | `.md` under `<repo>/doc/content/` (only if spec needs it) |
| `test-runner` | `moose-test-runner` | Build + run + diagnose + gold regen |
| `docs-builder` | `moose-docs-builder` | Final gate: MooseDocs smoke build, errors filtered against branch diff |

`investigator` is **not** a teammate — spawn ad-hoc via `Agent` (no `team_name`) when a teammate reports `NEEDS_CONTEXT`. Forward findings via `SendMessage`.

Do **not** add `code-standards` or `pr-reviewer` — green gates are the done condition.

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

### 2. Create team

`TeamCreate { team_name: "moose-feature-<feature>", description: "<one line>" }` (where `<feature>` = worktree dir name). Briefly tell user the team name, who'll spawn, and the caveats below.

### 3. Spawn teammates

Always: `implementer`, `test-writer`, `test-runner`, `docs-builder`.
Conditional: `unit-test-writer` (if `unit/` in files), `docs-writer` (if Doc plan on).

Each spawn message includes spec contents + parsed dispatch (Reuse decisions + Out-of-scope as hard constraints). Don't re-state skill loads — teammate prompts handle that.

**Do not respawn within a run.** Wake idle teammates with `SendMessage`.

### 4. Seed tasks

`TaskCreate`. For structured specs, copy entries verbatim — don't paraphrase:

- `iter-1: implement <feature>` — `implementer`. Body carries full Reuse + Out-of-scope. (Skip if reuse-only.)
- `iter-1: write test "<name>"` — **one per Test plan entry**, owner `test-writer` or `unit-test-writer`. Body carries Tester kind, asserted behavior, mutation rationale.
- `iter-1: write doc page` — `docs-writer` (if on). **Blocked on implementer + test-writers** so `!listing` resolves. Runs parallel with test-runner.
- `iter-1: build + run new tests` — `test-runner`. **Blocked on implementer + test-writers only.**
- `final: smoke docs build` — `docs-builder`. Blocked on implementation loop green.

For freeform: same skeleton with one generic test task instead of one-per-entry.

### 5. Iterate (max 10 rounds)

#### 5a. Implementer (sequential, first)

`SendMessage` to `implementer` with spec (iter 1 only), `{repo, kind, files}`, and the previous iter's test-runner failure report (iter ≥ 2). Wait for task complete + idle.

#### 5b. Tests (parallel)

`SendMessage` in parallel to `test-writer` (+ `unit-test-writer`). Each reads implementer's output via `Read`. Wait for all complete.

Docs deferred to 5c — they `!listing` against impl source *and* test input; both must exist.

#### 5c. Docs + test-runner (parallel)

Single message with both `SendMessage` blocks:

- `docs-writer` (if on) — body carries Public surface + final paths
- `test-runner` — **with explicit build authorization** so it runs `make` instead of asking:

  > Run tests in scope `<scope>`, restricting to `--re=<new-test-names>`.
  > You are authorized to build: `cd <scope> && make -j 6`.
  > If MISSING GOLD or structural DIFF, **do not** regen — just report.

Independent: test-runner only touches build/gold; docs-writer only touches `doc/content/`. Wait for both.

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
| `NEEDS_CONTEXT` | One-shot `investigator`, forward findings |

#### 5e. Gold-file pause

1. Show user the test-runner output (command, observed, gold).
2. Ask: *"Are these values correct? Approve gold regen?"*
3. On approve, `SendMessage test-runner` with regen task. It re-runs verbose, copies, re-runs to confirm, stages but **does not commit**.
4. If user says wrong → route to `implementer` instead.

### 6. Done

Stop the implementation loop when build clean + new tests pass. Then docs gate, then shutdown.

#### 6a. Docs smoke gate

`SendMessage docs-builder` with scope + base branch (`devel`). It runs `/moose-docs-smoke <scope>` and filters errors against `git diff --name-only devel...HEAD`.

| Report | Action |
|---|---|
| `PASS` | → 6b |
| `PASS_WITH_WARNINGS` | → 6b. Carry warnings into final report. |
| `FAIL` | Wake `docs-writer` with filtered errors + log path + diff list. New `docs-fix-N`. Re-smoke after DONE. |
| `BLOCKED` | Surface — likely env (missing conda / `*-opt`). Don't auto-fix. |

**Doc-fix cap: 3 rounds** (separate from impl cap). After cap, halt + ask user: extend / escalate to implementer / shut down with `DONE_WITH_CONCERNS`.

Routing nuance: if `docs-writer` reports needing a C++ change (e.g. `addClassDescription`, renamed class still referenced in `!syntax`), one route to `implementer` doesn't count against the cap. No ping-pong.

#### 6b. Shutdown

For each teammate: `SendMessage { type: "shutdown_request" }`. Wait. Then `TeamDelete`.

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
- `NEEDS_CONTEXT` → one-shot `investigator`, package findings into `SendMessage`.
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

After team creation, before iter 1, tell user:

- Style isn't gate-checked (pre-commit handles on commit).
- Docs **build** is gated (smoke build, errors filtered to diff). Doc **quality** isn't — warnings surfaced for manual review.
- Smoke is slow: ~5–10 min/round, up to 4 rounds → worst case ~20–40 min on top of impl. Bump with `SMOKE_TIMEOUT=N`.
- Team state in `~/.claude/tasks/<team_name>/`; crash loses iter history.
- Interrupt anytime; resume picks up open tasks.

## Canonical references

- Each agent's `.md` in `.claude/agents/` — workflow + constraints.
- `moose-test-runner` encodes the build/run/diagnose/gold-regen flowchart — trust it.
- `CLAUDE.md` for meta-repo submodule + branch rules.
