---
name: moose-build
description: Drive a MOOSE feature from a structured specs/blueprint.html to a green tree, docs gated, standing gates enforced. v2 blueprints (with a work-plan block) execute as parallel waves compiled from the plan's dependency DAG; v1 blueprints and small features run the goal-driven moose-feature-loop. Runs unattended (gold is regenerated and staged for post-hoc review); surfaces only at genuine decision points.
disable-model-invocation: true
---

# /moose-build

Take a blueprint (`specs/blueprint.html`, from `/moose-blueprint`) to build clean + new regression tests green + standing gates passed, then report. Two execution modes share one goal ledger and one set of standing gates: **wave mode** (v2 blueprints with a parallelizable `#work-plan` — deterministic fan-out for creation) and **loop mode** (everything else — the autonomous `moose-feature-loop`). Repair is always model-driven: failures route through the feature loop, never re-planned here.

## Usage

```
/moose-build [path/to/blueprint.html] [--core]
```

- Blueprint defaults to `<worktree-root>/specs/blueprint.html` (accept a legacy `specs/spec.md` or `<worktree-root>/spec.md` from pre-rename worktrees). Missing → refuse: *"No blueprint found. Run `/moose-blueprint` first."*
- v2 blueprint = the seven contract blocks including `#work-plan` with a parseable `#work-plan-data` JSON island. v1 = the six blocks without it → loop mode, unchanged behavior. Freeform HTML or legacy spec.md → infer, then confirm `{repo, kind, files, unit-tests, docs}` with one `AskUserQuestion`.
- `--core` = slim mode: skip the docs gate (for features adding no registered syntax and no doc page); standing gates still run in full. Refuse `--core` when `#doc-plan` says `Needed: yes`.
- Requires a `/new-feature` worktree: walk up for a `.git` **file** beside a `moose/`+`blackbear/`+`isopod/` layout; refuse otherwise.

## The goal ledger

Compiled once, before any execution. Two sources, **additive-only** — a blueprint can add criteria, never remove or weaken a standing one:

```
STANDING (every run, unconditionally):
  C1  build clean in <scope>                     (make exits 0)
  C4  reuse decisions honored, no out-of-scope edits  (diff audit)
  C5  specs SQA-complete                         (requirement/design/issues on every new/modified spec block)
  C6  code ASCII-clean                           (source/specs/.i only; .md, .bib exempt)
  DG  docs gate                                  (unless --core)
BLUEPRINT-DERIVED:
  C2.<name>  test exists AND passes              (one per #test-plan row)
  C3  unit tests exist AND pass                  (only if gtest entries / unit/ paths)
```

Slice fields (both modes): `repo`, `object_kind`, `files_to_touch`, `scope` (top-level submodule; `moose/modules/<m>` → `moose`), `summary` + `physics` verbatim, `reuse_decisions[]`, `test_plan[]`, `out_of_scope[]`, `unit_on`, `reuse_only`, `blueprint_path`. v2 adds `units[]` + `deps` from the JSON island — validate it (parses, deps resolve, acyclic, same-file units share an edge; violations → refuse with the reason, the user fixes the blueprint). If KaTeX is rendered, recover TeX from `<annotation encoding="application/x-tex">` nodes; Grep by block id rather than whole-file-Read the font-bloated HTML.

## Standing gates — not negotiable, not blueprint-editable

The gates below are owned by this skill. Blueprints render them read-only and cannot add, remove, reorder, or alter them; the work-plan DAG governs creation only. Every gate check maps to a ledger criterion; a gate is passed when its checks are green.

**Gate A — after the last implement wave (wave mode) / inside the loop's normal flow (loop mode):**

1. **Consistency sweep** (wave mode only, ≥2 implement units): one-shot reviewer agent (`general-purpose`) that reads every new/changed source file *together* against `moose/framework/doc/content/sqa/framework_scs.md` — naming drift, param-style drift, duplicated helpers across units. Findings route to the owning unit's implementer before the build.
2. **Build clean** (C1): one-shot `moose-test-runner`, build-only — *"You are authorized to build: `cd <scope> && make -j 6`. Report compile errors verbatim with owning files."*

**Gate B — after the test/doc wave (wave mode) / after `GOAL_MET` (loop mode):**

1. **Suites green + gold staged** (C2, C3): `moose-test-runner` on the registered test names (`--re=<names>`); gold per § Gold policy.
2. **Reuse / out-of-scope audit** (C4): diff vs the blueprint's `reuse_decisions[]` + `out_of_scope[]`.
3. **SQA** (C5): grep audit of in-diff spec files for `requirement`/`design`/`issues` (parent-block declarations cover children), then authoritative `cd <doc-dir> && ./moosedocs.py check` (doc dir: `moose/modules/doc` | `blackbear/doc` | `isopod/doc`), errors filtered to the branch diff — pre-existing SQA debt is reported, not fixed. Env failure → surface the conda hint, note the grep audit still ran.
4. **ASCII** (C6): CIVET's precheck covers **code**, not documentation — `idaholab/moose` scoped the rule to code comments in `c12859fc3f` (May 2026, refs #32497), so `.md` and `.bib` are excluded from this gate and non-ASCII there (em dashes, `Nédélec`) is correct, not a defect. Never "fix" a name's diacritics.

   ```bash
   git -C <scope> diff devel...HEAD -- . ':(exclude)*gold*' ':(exclude)*.md' ':(exclude)*.bib' \
     | perl -ne 'print if /^\+/ and /[^\x00-\x7F]/'
   ```

   The code scan needs no `-CSD` — `[^\x00-\x7F]` is a byte test. Any hit fixed in place on the main thread (smart quotes → `'`/`"`, dashes → `--`, NBSP → space, unicode math → spelled out or LaTeX in a comment), re-run until clean. Separately, scan added `.md` lines for the **invisible** subset only — `perl` here **must** carry `-CSD` or it compares undecoded bytes and silently misses smart quotes — smart quotes, NBSP/NNBSP, zero-width space, BOM — which break `grep`, `!listing re=` slicing, and citation matching; leave all other non-ASCII alone:

   ```bash
   git -C <scope> diff devel...HEAD -- '*.md' \
     | perl -CSD -ne 'print if /^\+/ and /[\x{2018}\x{2019}\x{201C}\x{201D}\x{00A0}\x{202F}\x{200B}\x{FEFF}]/'
   ```
5. **Docs smoke** (DG): via the docs gate (§ Docs) — `moose-docs-writer`'s nested gate when docs are on, direct `moose-docs-builder` when off.

When you get burned by CIVET on something new: add it here as a standing check once, and every future run inherits it.

## Mode selection

**Wave mode** when the blueprint is v2 AND any computed wave has ≥3 units. **Loop mode** otherwise (v1, freeform, single-class v2, `reuse_only`). Caps both modes: `impl_iters` = 5 (`--core`) or 10 (full), `no_progress` = 2, `run_label` = worktree dir name.

## Loop mode

Spawn one `moose-feature-loop` (`Agent`, `subagent_type: "moose-feature-loop"`, always background) with the spec slice + caps + `run_label`. Briefly tell the user the goal + criteria + § Caveats, then let it run. It owns C1–C6 internally (its criteria mirror the ledger); on `GOAL_MET`, run Gate B items 2–4 yourself as the authoritative re-check, then the docs gate. Terminal handling: § Terminal statuses.

## Wave mode

Compute waves = topological levels of `units[]`. Then:

1. **Per implement wave, in order.** Mark the wave's chips `running`. Fan out — all spawns in one message: ≥3 units → one `Workflow` call (this skill's instruction is the orchestration opt-in), one `agent()` per unit with `agentType` from the unit, `phase: "Wave <n>"`; 2 units → two parallel `Agent` calls; 1 → single call. **Unit prompt = its JSON payload + the verbatim `#physics` content its `physics_ref` anchors + `reuse_decisions[]` + `out_of_scope[]` + its `notes`** — self-contained, no blueprint reads. No worktree isolation: edge-free units own disjoint files by construction (validated at parse). Chip `done`/`failed` as each report lands; any failure → finish the wave, then § Repair before proceeding.

   ```js
   // Workflow sketch (units passed via args; meta phases = ["Wave <n>"])
   const results = await parallel(args.units.map(u => () =>
     agent(u.prompt, { agentType: u.agent, label: u.id, phase: args.wave })))
   return results
   ```

2. **Gate A.** Consistency sweep → route findings → build. Chips on the gate rows. Build errors → § Repair.

3. **Test/doc wave.** Same fan-out for `test` units (`moose-test-writer` / `moose-unit-test-writer`, one per unit, prompt = its `#test-plan` row + `out_of_scope[]`) and the `doc` unit (§ Docs). Use the test names the writers report registering.

4. **Gate B.** Runner first (C2/C3 + gold), then audits 2–4, docs smoke last. Chips per row. Failures → § Repair, then re-run only the failed checks.

## Repair (both modes' failure path)

Never route individual fixes yourself. Collect the failure evidence (compiler output / runner verdict / gate findings, with owning units) and spawn `moose-feature-loop` in **repair mode**: slice + caps + `repair: true` + ledger state (criteria already met, evidence) + the failures. It routes internally and returns a terminal status. On `GOAL_MET` resume the interrupted wave/gate. Don't ping-pong: one repair spawn per gate failure, woken via `SendMessage` for subsequent failures in the same run.

## Gold policy

`MISSING GOLD` / structural DIFF on newly authored tests is first-time capture, not baseline overwrite — regenerate without pausing: runner regenerates, confirms `OK`, stages (`git add`), **never commits**. Keep every gold file + observed values for the final report. A runner-flagged *possible real regression* routes to repair instead.

## Terminal statuses (from the loop, either mode)

| Loop returns | Action |
|---|---|
| `GOAL_MET` | → remaining gates / resume wave. Carry files, commands, test counts, **staged gold + observed values**. |
| `NEEDS_DESIGN(reason)` | Stop. *"The blueprint needs a design change: `<reason>`. Re-run `/moose-blueprint`, then `/moose-build`."* |
| `BLOCKED(reason)` | Stop. Surface blocker + exact fix command (usually env: conda / missing `*-opt`). Don't auto-fix. |
| `STALLED(state)` | Surface unmet criteria + what was tried. `AskUserQuestion`: extend cap / simplify spec / abandon. On extend, re-spawn with higher `impl_iters` + prior state. |

## Docs (DG; skipped by `--core`)

**Docs ON** — spawn/wake `moose-docs-writer` with `scope`, base branch (`devel`), public surface, doc paths (wave mode: this is the `doc` unit). It authors and runs its nested write→smoke→fix loop (cap 3):

| Returns | Action |
|---|---|
| `DOCS_GREEN` | → report; carry warnings. |
| `NEEDS_CPP_CHANGE` | One C++ hop, no ping-pong: one-shot `moose-implementer` for exactly the named fix, one-shot `moose-test-runner` to confirm the suite, wake `docs-writer` to re-gate. |
| `DONE_WITH_CONCERNS` | `AskUserQuestion`: extend doc budget / escalate to implementer / ship as-is. |
| `BLOCKED` | Surface — likely env. Don't auto-fix. |

**Docs OFF (full mode, no pages authored)** — C++ renames can still break `!syntax` in untouched pages: spawn `moose-docs-builder` with `scope` + `devel`. `PASS`/`PASS_WITH_WARNINGS` → report. `FAIL` (`cpp-side`) → one-shot implementer for the `!syntax` regression + one-shot runner re-check + re-smoke. `FAIL` (`doc-side`) → surface (needs manual fix or a docs-on re-run). `BLOCKED` → surface.

## Status chips (v2 blueprints)

You own the blueprint's chips — the browser-side twin of the task list. `Edit` the chip span beside the unit's uid / at the gate row's start on every transition: dispatch → `<span class="chip wip">running</span>`, report → `chip done`/`chip failed` (`done`/`failed` text). Edit only chip spans, nothing else. Loop mode on a v2 blueprint: update chips as the loop's iteration `SendMessage`s arrive, and reconcile all chips at terminal. v1 blueprints keep their `[]` markers, same transitions.

## Clean-context review (final step, both modes)

After every standing gate and the docs gate are green — the feature is otherwise done — spawn ONE fresh `moose-pr-reviewer` (`subagent_type: "moose-pr-reviewer"`, foreground) in **local mode**. Fresh spawn is the point: it has seen none of this build's context, so it reviews the diff the way a cold PR reviewer will.

```
Run a LOCAL review (mode: local) of this branch.
  repo_root: <absolute path to the scope submodule in this worktree>
  base_branch: devel
  label: <run_label>
Follow your local-mode workflow: snapshot the diff, classify into
code/test/doc buckets, spawn the three reviewers as nested children in
parallel, merge, write the findings file. No PR exists — never call gh.
Return your local summary block including the merged findings.
```

**Report-only.** Findings go into the final report verbatim (counts + the findings list + `/tmp/moose-review-<label>.md`); do not auto-route fixes — the user decides what to apply before committing. Offer once: apply the mechanical findings now, or leave them. An errored reviewer is noted, not retried more than once; zero findings is a valid (and reportable) result.

## Final report

Files created/modified per unit/child; exact runner commands + final counts (pass/fail/skip); **gold regenerated + observed values** flagged for physics sanity-check; standing-gate results (what was fixed in place, anything surfaced from `moosedocs.py check`); docs result (smoke PASS / warnings / log path, or "docs skipped (`--core`)"); **clean-context review findings** (verbatim, + findings file path); any `DONE_WITH_CONCERNS`; wave-mode wall-clock per wave; a **diff attribution audit** — group the diff into change classes and trace each to the blueprint's stated purpose (`moose/AGENTS.md` § Surgical Changes: every changed line traces to the request); flag unattributable hunks to drop, split out, or justify in the PR body; a suggested commit message.

## Caveats + boundaries

- **Never commit or push** — the run ends at the suggested commit message. Gold is staged, never committed.
- **Never run `clang-format`/`black`** — the pre-commit hook owns style.
- Worktrees, branches, conda envs are `/new-feature`'s job.
- Docs *build* is gated; doc *quality* isn't — warnings surface for manual review. Smoke is slow (~5–10 min/round).
- Interruptible anytime: waves, gates, and the loop all narrate to the task list (and v2 chips) so the user can watch and stop.
