---
name: moose-build-feature
description: Spin up an agent team (implementer, test writer(s), docs writer, test runner) against a structured spec.md (typically produced by /moose-design-feature). Iterates write/test/check/refine until the build is clean and new regression tests pass. Manual-invoke only.
disable-model-invocation: true
---

# /moose-build-feature

Drive a feature end-to-end from a structured `spec.md` (Summary / Physics / Reuse decisions / Test plan / Doc plan / Out of scope) by creating a real Claude Code **team** (`TeamCreate`) and orchestrating the existing MOOSE subagents as named teammates over a shared task list. Specs are typically produced by `/moose-design-feature`; freeform prose is also accepted, with reduced fidelity.

Stops when the build is clean and the new regression tests pass, or after **10** iterations (then halts and surfaces state).

## Usage

```
/moose-build-feature [path/to/spec.md]
```

If no path is given, defaults to `<worktree-root>/spec.md` (where `/moose-design-feature` writes by default).

The spec is expected to follow the `/moose-design-feature` template — structured sections (Summary, Physics, Reuse decisions, Test plan, Doc plan, Out of scope). Freeform prose is also accepted; in that case you'll fall back to inference and a confirmation prompt.

**Assumes the user already ran `/new-feature`** and is in that worktree. Don't create one. **Recommend `/moose-design-feature` first** if no spec exists at the default path.

## Team

You are the **team lead**. You create the team, spawn named teammates, assign them tasks via the shared task list, route messages, and tear the team down when done.

| Teammate name | `subagent_type` | Role |
|---|---|---|
| `implementer` | `moose-implementer` | C++/Python under `<repo>/src` and `<repo>/include` |
| `test-writer` | `moose-test-writer` | Regression `tests` spec + `.i` input |
| `unit-test-writer` | `moose-unit-test-writer` | gtest under `unit/` (spawn only if spec calls for it) |
| `docs-writer` | `moose-docs-writer` | `.md` pages under `<repo>/doc/content/` (spawn only if spec calls for it) |
| `test-runner` | `moose-test-runner` | Build (when authorized) + run + diagnose + gold regen |

`investigator` is **not** a teammate — spawn it ad-hoc via `Agent` (no `team_name`) when a teammate reports `NEEDS_CONTEXT`. It returns its findings as a one-shot result, which you then forward via `SendMessage`.

You do **not** add `code-standards` or `pr-reviewer` — green gates are the done condition.

## Steps

### 1. Read the spec and dispatch

1. **Resolve the spec path.** If `$ARGUMENTS` is set, use it. Otherwise default to `<worktree-root>/spec.md`. If neither exists, refuse: *"No spec found. Run `/moose-design-feature <idea>` first, or pass a spec path explicitly."*
2. `Read` the spec.
3. **Detect the format.**
   - **Structured** (has `## Summary`, `## Physics / math`, `## Reuse decisions`, `## Test plan`, `## Doc plan`, `## Out of scope`) — parse each section directly. Skip the confirmation prompt; the user already made these decisions during `/moose-design-feature`.
   - **Freeform** (legacy) — fall back to inference: target repo, object kind, files-to-touch from prose; default unit-tests off, docs on. Then ask the user **once** with `AskUserQuestion` to confirm `{repo, kind, files-to-touch, unit-tests on/off, docs on/off}`.
4. **Extract dispatch from the parsed (or inferred) spec:**
   - **Repo** — from `## Summary` → `**Repo:**` line, or inferred from prose.
   - **Object kind** — from `## Summary` → `**Object kind:**` line, or inferred.
   - **Files to touch** — from `## Summary` → `**Predicted files to touch:**` list, or inferred.
   - **Unit tests on/off** — on iff the files-to-touch list contains a `unit/` path.
   - **Docs on/off** — on iff `## Doc plan` says `**Needed:** yes` (or the freeform default if no Doc plan section exists).
   - **Reuse decisions** — every entry under `## Reuse decisions`. These flow to the implementer's first message: `Reuse as-is` → "do not re-implement X; the existing class is authoritative." `Extend` → "extend X with <decision>; do not write a parallel implementation." `Parallel` → "duplicating X is authorized; the spec records the justification — do not second-guess it."
   - **Test plan entries** — every entry under `## Test plan`. Each becomes one task on the shared task list, owned by `test-writer` (or `unit-test-writer` if the entry specifies gtest). The entry's named test, Tester kind, asserted behavior, and mutation rationale carry into the writer's first message.
   - **Out of scope** — every entry under `## Out of scope`. Surfaced to all writers as hard "do not touch" items.
5. **Reuse-only short-circuit.** If `## Reuse decisions` covers the whole feature with `Reuse as-is` entries (i.e. no new code is needed, only tests/docs), skip spawning `implementer` entirely. Tell the user: *"Spec says reuse-only — skipping implementer."* Continue with test/doc work.

### 2. Create the team

1. Derive `team_name = moose-feature-<feature>` where `<feature>` is the worktree directory name (the same name `/new-feature` used).
2. `TeamCreate { team_name: "moose-feature-<feature>", description: "<one line from the spec>" }`. This also creates the shared task list at `~/.claude/tasks/<team_name>/`.
3. Briefly tell the user: team name, which teammates you will spawn, and the caveats listed in §Caveats.

### 3. Spawn teammates

Spawn the teammates listed above via `Agent`, passing both `team_name` and `name`. Always:
- `implementer`
- `test-writer`
- `test-runner`

Conditionally (based on step 1's spec dispatch — `unit/` paths in files-to-touch, `Doc plan` section):
- `unit-test-writer`
- `docs-writer`

Each spawn message should include the spec contents and the parsed dispatch (`{repo, kind, files-to-touch}` plus the relevant Reuse decisions and Out-of-scope items) so the teammate has context from turn one. Their existing agent prompts already load the right skills on first action — don't re-state those.

**Do not respawn teammates within a run.** They go idle between turns; wake them with `SendMessage`. Respawning loses warmed context.

### 4. Seed the task list

`TaskCreate` the initial round of work.

**For structured specs**, the task list is driven by the spec sections — don't paraphrase, copy the entries through verbatim:

- `iter-1: implement <feature>` — owner `implementer`. Carry the full **Reuse decisions** and **Out of scope** sections into the task body so the implementer treats them as hard constraints. (Skip this task if step 1 short-circuited to reuse-only.)
- `iter-1: write test "<test_name>"` — **one task per `## Test plan` entry**, owner `test-writer` (or `unit-test-writer` if the entry specifies gtest). The task body carries that entry's Tester kind, asserted behavior, and mutation rationale.
- `iter-1: write doc page for <feature>` — owner `docs-writer` *(only if `## Doc plan` is on)*. Body carries the spec's `**Public surface:**` line.
- `iter-1: build + run new tests` — owner `test-runner` (blocked on the writers above)

**For freeform specs**, fall back to the legacy skeleton:

- `iter-1: implement <feature>` — owner `implementer`
- `iter-1: write regression test for <feature>` — owner `test-writer`
- `iter-1: write unit test for <feature>` — owner `unit-test-writer` *(if applicable)*
- `iter-1: write doc page for <feature>` — owner `docs-writer` *(if applicable)*
- `iter-1: build + run new tests` — owner `test-runner` (blocked on the writers above)

Use `TaskUpdate` to set owner / status. Teammates also update tasks themselves when they complete.

### 5. Iterate (max 10 rounds)

Each round:

#### 5a. Implementer (always first, sequential)

`SendMessage` to `implementer` with:
- The spec (first iteration only; afterward they have it)
- The agreed `{repo, kind, files}`
- For iteration ≥ 2: the structured failure report from the previous iteration's `test-runner`

Wait for the implementer's task to be marked complete and the idle notification to arrive.

#### 5b. Tests + docs (parallel)

`SendMessage` in parallel (single tool-call message with multiple `SendMessage` blocks) to:
- `test-writer`
- `unit-test-writer` *(if spawned)*
- `docs-writer` *(if spawned)*

Each reads the implementer's latest output via Read; teammates don't need to read each other.

Wait for all of them to mark their tasks complete.

#### 5c. Test runner (build + run, sequential after 5b)

`SendMessage` to `test-runner` with **explicit build authorization** so it runs `make` instead of asking. Template:

> Run tests in scope `<scope>`, restricting to `--re=<new-test-name(s)>`.
> You are authorized to build the affected app first (`cd <scope> && make -j 6`).
> If any test produces a `MISSING GOLD FILE` status or a structural DIFF, do **not** regenerate gold yet — just report it.

#### 5d. Route the test-runner report

Read its report (delivered as a turn from `test-runner`) and decide:

| Test-runner result | Action |
|---|---|
| All `OK` and build clean | **Done.** Exit the loop, go to step 6. |
| Build error | `SendMessage` to `implementer` with the compiler output; new `iter-N+1` task |
| `*** ERROR ***` / segfault / mooseError flagged as real code bug | `SendMessage` to `implementer` with the runtime error |
| **MISSING GOLD FILE** or structural DIFF | Pause for user confirmation (see 5e) |
| Tiny DIFF with tolerance suggestion | `SendMessage` to `test-writer` with the suggested tolerance |
| TIMEOUT | `SendMessage` to `test-writer` (suggest `max_time` bump or `heavy = true`) |
| RACE | `SendMessage` to `test-writer` (suggest `prereq` / `working_directory` fix from the report) |
| Skip caveat (e.g. capability gate) | Surface to user; usually a build/dep issue, not an iterate fix |
| Teammate `BLOCKED` | Halt loop, surface to user with the report |
| Teammate `NEEDS_CONTEXT` | Spawn `investigator` (one-shot, not a teammate); when it returns, `SendMessage` the cited findings to the teammate that asked |

#### 5e. Gold-file pause (only when test-runner flags missing/structural diff)

1. Show the user the test-runner output (run command, observed values, gold values if any).
2. Ask: *"Are these output values physically correct? Approve gold regeneration?"*
3. On approval, `SendMessage` to `test-runner` with the **"Regenerate gold for `<test_name>`"** task. The agent will:
   - Re-run verbose, copy outputs to `gold/`, re-run to confirm OK.
   - Stage but **not** commit. Report the staged files.
4. Continue the loop.

If the user says values are wrong → route to `implementer` (the code is buggy) instead of regenerating gold.

### 6. Done

Stop when **build clean + all new regression tests pass**. Before reporting:

1. Gracefully shut down each teammate: `SendMessage { to: <name>, message: { type: "shutdown_request" } }`.
2. Wait for shutdown responses.
3. `TeamDelete` to clean up `~/.claude/teams/<team_name>/` and `~/.claude/tasks/<team_name>/`.

Then report to the user:

- Files created / modified (per teammate)
- The exact commands `test-runner` ran (so user can reproduce)
- Final test counts (passed / failed / skipped)
- Any `DONE_WITH_CONCERNS` flagged across the run
- Suggested commit message; **do not commit**

### 7. Halt at iteration cap

If iteration 10 finishes without all gates green:

1. Stop dispatching new work; do **not** auto-shut-down or `TeamDelete` (the user may want to extend).
2. Summarize the last iteration's failure, the routing decisions tried, and the unresolved blocker.
3. Ask the user: extend the budget (and by how much), simplify the spec, or escalate. On extend, continue from where you stopped. On abandon, shut down + `TeamDelete`.

## Failure handling

- **`BLOCKED`** from any teammate → halt loop, surface the report. Don't tear the team down — the user may want to inspect or resume.
- **`NEEDS_CONTEXT`** → spawn `investigator` via plain `Agent` (no `team_name`) with a focused question. When it returns, package its cited findings into a `SendMessage` to the teammate that asked.
- **`DONE_WITH_CONCERNS`** → record in TaskUpdate, continue. Surface in final report.

## Hard constraints

- **Never commit or push.** The user owns commits. Final report includes a suggested commit message; that's it.
- **Never run `clang-format` / `black`.** The pre-commit hook handles style. (If the hook fails on commit, the user fixes it.)
- **Never run `moosedocs.py` build/check.** Docs are written but not gate-checked; the user reviews them manually.
- **Don't create or destroy worktrees / branches / conda envs.** That's `/new-feature`'s job.
- **Don't substitute for a teammate** — even one-line edits go through the right teammate so the diff is consistent and skills load correctly.
- **Don't respawn a teammate** within a run; wake idle teammates with `SendMessage`. Respawning loses warmed context.
- **Don't loop on the same failure** more than 2-3 iterations without surfacing. If routing keeps producing the same error, halt and ask the user.

## Caveats to surface to the user up front

When you start the run (after team creation, before iteration 1), briefly tell the user:

- Style isn't checked (pre-commit hook handles it on commit).
- Docs aren't gate-checked (you'll need to eyeball the rendered output later).
- Team state lives in the shared task list (`~/.claude/tasks/<team_name>/`); a session crash loses iteration history.
- They can interrupt at any time; on resume, you'll pick up from the open tasks in the shared list.

## Canonical references

- Each agent's own `.md` in `.claude/agents/` for its workflow and constraints.
- `moose-test-runner` already encodes the build/run/diagnose/gold-regen flowchart — trust its routing recommendations rather than re-deriving them here.
- `CLAUDE.md` for the meta-repo's submodule + branch rules.
