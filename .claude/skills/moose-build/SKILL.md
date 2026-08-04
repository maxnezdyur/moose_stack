---
name: moose-build
description: Drive a MOOSE feature from a structured specs/blueprint.html to a green tree — build clean, new tests green, standing gates enforced, docs gated, clean-context review — via ONE dynamically authored Workflow run. The script owns control flow (waves, gates, repair loops); typed agents (moose-implementer, moose-test-writer, moose-test-runner, ...) own all judgment. Runs unattended (gold regenerated and staged for post-hoc review); surfaces only at genuine decision points.
disable-model-invocation: true
---

# /moose-build

One Workflow run takes the blueprint to done. The pipeline — waves → Gate A → tests → Gate B → docs → clean-context review — is **code, not conversation state**: no stage can be forgotten, nothing is lost between stages, every agent's return lands in the run journal, and a killed run resumes from cache. Agents supply all judgment via `agentType` + `schema`; the main thread only parses the blueprint, launches the run, mirrors progress to chips, and renders the report. There is no wave-vs-loop mode split — a small feature is just a one-unit DAG through the same script.

## Usage

```
/moose-build [path/to/blueprint.html] [--core]
```

- Blueprint defaults to `<worktree-root>/specs/blueprint.html` (accept legacy `specs/spec.md` / `<worktree-root>/spec.md`). Missing → refuse: *"No blueprint found. Run `/moose-blueprint` first."*
- v2 blueprint = seven contract blocks including `#work-plan` with a parseable `#work-plan-data` JSON island → `units[]` + `deps`. v1 / freeform / legacy → compile a single implement unit from `#summary`+`#physics` plus one test unit per `#test-plan` row; for freeform, confirm the inferred `{repo, kind, files, unit-tests, docs}` with one `AskUserQuestion`.
- `--core` = slim mode: skip the docs gate (features adding no registered syntax and no doc page); standing gates still run in full. Refuse `--core` when `#doc-plan` says `Needed: yes`.
- Requires a `/new-feature` worktree: walk up for a `.git` **file** beside a `moose/`+`blackbear/`+`isopod/` layout; refuse otherwise.

## The goal ledger

Compiled once, before launch. Two sources, **additive-only** — a blueprint can add criteria, never remove or weaken a standing one:

```
STANDING (every run, unconditionally):
  C1  build clean in <scope>                     (make exits 0)
  C4  reuse decisions honored, no out-of-scope edits  (diff audit)
  C5  specs SQA-complete                         (requirement/design/issues on every new/modified spec block)
  C6  diff ASCII-clean                           (no non-ASCII bytes added; .bib diacritics exempt)
  DG  docs gate                                  (unless --core)
BLUEPRINT-DERIVED:
  C2.<name>  test exists AND passes              (one per #test-plan row)
  C3  unit tests exist AND pass                  (only if gtest entries / unit/ paths)
```

When you get burned by CIVET on something new: add it here as a standing check once, and every future run inherits it.

## Compile args (main thread, before launch)

The script has **no filesystem access** — everything blueprint-derived rides in `args`. Grep the blueprint by block id (never whole-file-Read the KaTeX-bloated HTML; recover TeX from `<annotation encoding="application/x-tex">` if rendered).

- `slice`: `repo`, `object_kind`, `files_to_touch`, `scope` (top-level submodule; `moose/modules/<m>` → `moose`), `reuse_decisions[]`, `test_plan[]`, `out_of_scope[]`, `unit_on`, `reuse_only`, `blueprint_path`.
- `units[]`: `{id, kind: implement|test|unit|doc, agent, deps[], prompt}` — **prompt fully rendered and self-contained**: implement = JSON payload + the verbatim `#physics` content its `physics_ref` anchors + `reuse_decisions[]` + `out_of_scope[]` + `notes`; test/unit = its `#test-plan` row + `out_of_scope[]`. Units never read the blueprint.
- `caps: {impl_iters: 5 (--core) | 10, no_progress: 2}`, `run_label` = worktree dir name, `core` flag.
- Validate the v2 island: parses, deps resolve, acyclic, same-file units share an edge; violations → refuse with the reason, the user fixes the blueprint.
- `Date.now()` / `new Date()` are unavailable in scripts — stamp any timestamps main-thread.

## The pipeline script (authored fresh each run)

Author the script per run from the skeleton — **adapt, don't transcribe**: skip the consistency sweep with <2 implement units; skip Tests when `test_plan` is empty (`reuse_only`: evidence C1 with one build-only runner call); skip DG under `--core`. Hard invariants every authored script keeps:

1. **One Workflow per run** — this skill's instruction is the orchestration opt-in.
2. **Judgment lives in agents; the script branches only on schema fields.** Never inline a heuristic (classifying a failure, judging a diff) into JS.
3. **Standing gates are unskippable code**: `status: 'DONE'` must be unreachable except through every gate. Early exits only via the terminal statuses.
4. `model: 'opus'` on every `agent()` call (standing preference).
5. `.filter(Boolean)` after every `parallel()`; a null report = dead unit → one re-dispatch, then treat as stall.
6. **The return object carries everything the final report needs** — script state dies at return. If a result looks empty, Read the run's `journal.jsonl` before re-running anything.

```js
export const meta = { name: 'moose-build', description: 'Blueprint → waves → gates → tests → docs → review',
  phases: [{title:'Gate A'},{title:'Tests'},{title:'Gate B'},{title:'Docs'},{title:'Review'}] }
const { slice, units, caps, core } = args
const O = { model: 'opus' }
const ledger = {}, gold = [], files = [], concerns = []
const term = (status, at, extra) => ({ status, at, ledger, gold, files, concerns, ...extra })
const triage = async (at, evidence) => {           // model-side judgment on a dead end
  const t = await agent(TRIAGE(at, evidence), { ...O, schema: TRIAGE_S })
  return term(t.verdict === 'NEEDS_DESIGN' ? 'NEEDS_DESIGN' : 'STALLED', at, { reason: t.reason, evidence })
}
const runUnit = async (u, ph) => {                 // one unit, with the scout hop on NEEDS_CONTEXT
  let r = await agent(u.prompt, { ...O, agentType: u.agent, label: u.id, phase: ph, schema: UNIT_S })
  if (r?.status === 'NEEDS_CONTEXT') {
    const ctx = await agent(r.question, { ...O, agentType: 'moose-scout', phase: ph })
    r = await agent(u.prompt + '\n\nScout findings:\n' + ctx, { ...O, agentType: u.agent, label: u.id + '#2', phase: ph, schema: UNIT_S })
  }
  if (r?.concerns?.length) concerns.push(...r.concerns)
  return r
}

// ---- Waves: topological levels (Kahn layering over deps); edge-free units own disjoint files
const impl = units.filter(u => u.kind === 'implement')
for (const [n, wave] of levels(impl).entries()) {
  const reports = (await parallel(wave.map(u => () => runUnit(u, `Wave ${n+1}`))))
  for (const r of reports) if (!r || r.status === 'BLOCKED') return term('BLOCKED', `Wave ${n+1}`, { reason: r?.report })
  reports.forEach(r => files.push(...r.files))
}

// ---- Gate A: consistency sweep (≥2 implement units) → build clean (C1) with repair loop
phase('Gate A')
if (impl.length >= 2) {
  const sweep = await agent(SWEEP(files), { ...O, agentType: 'general-purpose', schema: AUDIT_S })
  await parallel(sweep.findings.map(f => () => agent(FIX(f), { ...O, agentType: 'moose-implementer', phase: 'Gate A' })))
}
let build = await agent(BUILD, { ...O, agentType: 'moose-test-runner', schema: BUILD_S }), sig = '', flat = 0
for (let i = 0; !build.clean && i < caps.impl_iters; i++) {
  const s = build.errors.map(e => e.file).join()          // stall = same signature no_progress times
  flat = s === sig ? flat + 1 : 0; sig = s
  if (flat >= caps.no_progress) break
  await agent(REPAIR(build.errors), { ...O, agentType: 'moose-implementer', phase: 'Gate A' })
  build = await agent(BUILD, { ...O, agentType: 'moose-test-runner', schema: BUILD_S })
}
if (!build.clean) return await triage('build', build.errors)
ledger.C1 = true

// ---- Tests: writers fan out → runner verifies → repair routes on the runner's classification
phase('Tests')
const tw = units.filter(u => u.kind === 'test' || u.kind === 'unit')
const wrote = (await parallel(tw.map(u => () => runUnit(u, 'Tests')))).filter(Boolean)
const names = wrote.flatMap(w => w.registered)   // registered names only — unknown names in --re select 0 tests = false pass
let run = await agent(RUN(names), { ...O, agentType: 'moose-test-runner', schema: RUN_S })
for (let i = 0; run.tests.some(t => t.status !== 'OK') && i < caps.impl_iters; i++) {
  for (const t of run.tests.filter(t => t.status !== 'OK')) {
    if (t.class === 'env-blocked') return term('BLOCKED', 'tests', { reason: t.evidence })
    else if (t.class === 'gold-capture') gold.push(...(await agent(GOLD(t.name), { ...O, agentType: 'moose-test-runner', schema: RUN_S })).gold)
    else await agent(FIXTEST(t), { ...O, agentType: t.class === 'test-tweak' ? writerOf(t, tw) : 'moose-implementer', phase: 'Tests' })
  }
  run = await agent(RUN(failingNames(run)), { ...O, agentType: 'moose-test-runner', schema: RUN_S })
  // stall guard identical to the build loop → return await triage('tests', ...)
}
ledger.C2 = true; if (slice.unit_on) ledger.C3 = true

// ---- Gate B: audits — C4 reuse/out-of-scope diff, C5 SQA (grep + moosedocs.py check), C6 ASCII (fixed in place)
phase('Gate B')
// each: audit agent → route findings to the owner per the routing table → re-run that one audit; 2nd failure → triage
// ---- Docs (skip when core): docs-writer unit or docs-builder smoke; one C++ hop max — see § Docs
phase('Docs')
// ---- Clean-context review: fresh moose-pr-reviewer, local mode, report-only — see § Review
phase('Review')
const review = await agent(REVIEW_LOCAL, { ...O, agentType: 'moose-pr-reviewer', schema: REVIEW_S })
return { status: 'DONE', ledger, files, gold, docs, review, concerns, counts: run.tests }
```

### Schemas (sketches — expand to real JSON Schema in the script)

```
UNIT_S   {status: DONE|DONE_WITH_CONCERNS|NEEDS_CONTEXT|BLOCKED, files[], report, registered[]?, question?, concerns[]?}
BUILD_S  {clean: bool, errors: [{file, excerpt}]}
RUN_S    {tests: [{name, status: OK|FAIL|SKIP, class?: code-bug|test-tweak|gold-capture|possible-regression|env-blocked, evidence?}],
          gold: [{file, observed}], commands[]}
AUDIT_S  {pass: bool, findings: [{file, line?, issue, owner?}]}
TRIAGE_S {verdict: RETRY|NEEDS_DESIGN|STALLED, reason}
DOCS_S   writer: {status: DOCS_GREEN|NEEDS_CPP_CHANGE|DONE_WITH_CONCERNS|BLOCKED, change?, warnings[]}
         builder: {status: PASS|PASS_WITH_WARNINGS|FAIL, side?: cpp|doc, warnings[]}
REVIEW_S {counts, findings[], file}
```

### Routing (branch on the runner's classification — trust it, don't re-derive)

| Evidence | Route |
|---|---|
| build error (C1) | `moose-implementer` ← compiler output |
| test fails — `code-bug` / `possible-regression` (`*** ERROR ***`, segfault, suspect DIFF) | `moose-implementer` ← runtime error |
| test fails — `test-tweak` (tiny DIFF + tolerance, `TIMEOUT`, `RACE`) | owning `moose-test-writer` ← suggested fix (`max_time`/`heavy`, `prereq`/`working_directory`) |
| `gold-capture` (MISSING GOLD / structural DIFF on a new test) | `moose-test-runner` regen per § Gold |
| `env-blocked` (missing PETSc cap, missing `*-opt`) | return `BLOCKED` with the runner's fix command |
| C4 violation | `moose-implementer` ← "revert X / honor reuse decision Y" |
| C5 missing `requirement`/`design`/`issues` | `moose-test-writer` ← spec path + missing fields |
| C6 non-ASCII byte | small fix agent (Bash+Edit) in place: smart quotes → `'`/`"`, dashes → `--`, NBSP → space, unicode math → LaTeX in docs / ASCII in source |
| unit returns `NEEDS_CONTEXT` | one-shot `moose-scout`, findings appended, one re-run |
| any agent returns `BLOCKED` | return `BLOCKED`, forwarding the blocker verbatim |

Prompts the script interpolates (keep these verbatim shapes): build = *"You are authorized to build: `cd <scope> && make -j 6`. Report compile errors verbatim with owning files."*; run = *"Run tests in `<scope>`, restricting to `--re=<names>`. You are authorized to build. Diagnose, classify each failure, report; do not regenerate gold unless told."*; sweep reads every new/changed source file *together* against `moose/framework/doc/content/sqa/framework_scs.md` — naming drift, param-style drift, duplicated helpers across units.

## Decision points & resume (main thread)

The script never asks the user anything — it returns a terminal status; you ask, then resume. The launch result gives `scriptPath` + `runId`:

| Script returns | Action |
|---|---|
| `DONE` | → final report. |
| `NEEDS_DESIGN(reason)` | Stop. *"The blueprint needs a design change: `<reason>`. Re-run `/moose-blueprint`, then `/moose-build`."* |
| `BLOCKED(reason)` | Stop. Surface blocker + exact fix command (usually env: conda / missing `*-opt`). Don't auto-fix. |
| `STALLED(state)` | Surface unmet criteria + what was tried. `AskUserQuestion`: extend cap / simplify spec / abandon. On extend: bump `caps` in `args`, relaunch `Workflow({scriptPath, args, resumeFromRunId})` — the unchanged prefix replays from cache and the loop continues where it died. |

Same resume path after a user interrupt (`TaskStop`) or a crash. `DONE_WITH_CONCERNS` entries in `concerns[]` surface as one `AskUserQuestion` at report time.

## Status chips (v2 blueprints)

You own the blueprint's chips; the workflow runs in the background. Mirror the journal: `journal.jsonl` in the run's transcript dir appends a line per completed agent (label, phase, return). Poll it while the run lives (Monitor on file growth, or periodic reads at a few-minute cadence) and on each new entry `Edit` the matching chip span — unit report lands → `chip done`/`chip failed`; a wave completes → next wave's chips `<span class="chip wip">running</span>`; gate rows likewise. Edit only chip spans, nothing else. Best-effort — never block on polling, and **reconcile every chip from the final result at terminal** regardless of what polling caught. v1 blueprints keep their `[]` markers, same transitions.

## Gold policy

`MISSING GOLD` / structural DIFF on newly authored tests is first-time capture, not baseline overwrite — regenerate without pausing. Gold prompt: *"Regenerate gold for `<test>` — first-time capture; the new behavior is authorized as correct-by-design: run verbose, copy outputs to `gold/`, re-run to confirm `OK`, stage (`git add`) — **never commit**."* The criterion is met once the confirm-run is `OK`. Every gold file + observed values accumulates in `gold[]` for the final report. A runner-flagged *possible real regression* routes to `moose-implementer` instead of regenerating.

## Docs (DG; skipped by `--core`)

**Docs ON** — the `doc` unit spawns `moose-docs-writer` with `scope`, base branch (`devel`), public surface, doc paths. It runs its nested write→smoke→fix loop (cap 3) internally:

| Returns | Script action |
|---|---|
| `DOCS_GREEN` | → carry warnings into the result. |
| `NEEDS_CPP_CHANGE` | One C++ hop, no ping-pong: one-shot `moose-implementer` for exactly the named fix, one-shot `moose-test-runner` to confirm the suite, fresh `moose-docs-writer` to re-gate. |
| `DONE_WITH_CONCERNS` | Record in `concerns[]` (main thread asks at report time). |
| `BLOCKED` | Return `BLOCKED` — likely env. |

**Docs OFF (full mode, no pages authored)** — C++ renames can still break `!syntax` in untouched pages: `moose-docs-builder` with `scope` + `devel`. `PASS`/`PASS_WITH_WARNINGS` → carry. `FAIL` (`cpp-side`) → one implementer hop + runner re-check + re-smoke, once. `FAIL` (`doc-side`) → record as surfaced issue (manual fix or docs-on re-run). `BLOCKED` → return `BLOCKED`.

## Clean-context review (last stage, unskippable)

The final `agent()` call before `DONE` — fresh `moose-pr-reviewer` in **local mode**; fresh is the point: it has seen none of this build's context, so it reviews the diff the way a cold PR reviewer will.

```
Run a LOCAL review (mode: local) of this branch.
  repo_root: <absolute path to the scope submodule in this worktree>
  base_branch: devel
  label: <run_label>
Snapshot the diff, classify into code/test/doc buckets, spawn the three
reviewers as nested children in parallel, merge, write the findings file.
No PR exists — never call gh. Return the merged findings.
```

**Report-only.** Findings go into the final report verbatim (counts + findings + `/tmp/moose-review-<label>.md`); never auto-route fixes — the user decides before committing. Offer once: apply the mechanical findings now, or leave them. An errored reviewer is noted, retried at most once; zero findings is a valid, reportable result.

## Final report (main thread, from the result object)

Files created/modified per unit; exact runner commands + final counts (pass/fail/skip); **gold regenerated + observed values** flagged for physics sanity-check; standing-gate results (what was fixed in place, anything surfaced from `moosedocs.py check`); docs result (smoke PASS / warnings / log path, or "docs skipped (`--core`)"); **clean-context review findings** (verbatim, + findings file path); any concerns; wall-clock per phase; a **diff attribution audit** — group the diff into change classes and trace each to the blueprint's stated purpose (`moose/AGENTS.md` § Surgical Changes: every changed line traces to the request); flag unattributable hunks to drop, split out, or justify in the PR body; a suggested commit message.

## Caveats + boundaries

- **Never commit or push** — the run ends at the suggested commit message. Gold is staged, never committed.
- **Never run `clang-format`/`black`** — the pre-commit hook owns style.
- Worktrees, branches, conda envs are `/new-feature`'s job.
- Docs *build* is gated; doc *quality* isn't — warnings surface for manual review. Smoke is slow (~5–10 min/round).
- Debugging a weird or empty result: Read the run's `journal.jsonl` first — it records every agent's actual return.
- Interruptible anytime: `/workflows` shows the live tree; `TaskStop` the run, resume later with `resumeFromRunId`.
