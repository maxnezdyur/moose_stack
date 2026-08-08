---
name: moose-build
description: Drive a MOOSE feature from a structured specs/blueprint.html to a green tree, docs gated, standing gates enforced. Execution is the goal-driven moose-feature-loop, which works unattended toward a compiled definition-of-done. Gold is regenerated and staged for post-hoc review; surfaces only at genuine decision points.
disable-model-invocation: true
---

# /moose-build

Take a blueprint (`specs/blueprint.html`, from `/moose-blueprint`) to build clean + new regression tests green + standing gates passed, then report. One execution path: the autonomous `moose-feature-loop` drives the work. This skill compiles the goal ledger, owns the standing gates, and reports. Repair is model-driven too — gate failures route back through the feature loop, never re-planned here.

## Usage

```
/moose-build [path/to/blueprint.html] [--core]
```

- Blueprint defaults to `<worktree-root>/specs/blueprint.html`. Missing → refuse: *"No blueprint found. Run `/moose-blueprint` first."*
- A blueprint with `#work-plan` + a parseable `#work-plan-data` island carries a unit decomposition — the loop's dispatch hint, and the chips this skill drives. One without it behaves the same, minus that decomposition. Freeform HTML → infer, then confirm `{repo, kind, files, unit-tests, docs}` with one `AskUserQuestion`.
- `--core` = slim mode: skip the docs gate (for features adding no registered syntax and no doc page); standing gates still run in full. Refuse `--core` when `#doc-plan` says `Needed: yes`.
- Requires a `/new-feature` worktree: walk up for a `.git` **file** beside a `moose/`+`blackbear/`+`isopod/` layout; refuse otherwise.

## The goal ledger

Compiled once, before any execution. Two sources, **additive-only** — a blueprint can add criteria, never remove or weaken a standing one:

```
STANDING (every run, unconditionally): C1, C4, C5, C6, DG (DG unless --core) — each defined with its check in references/standing-gates.md
BLUEPRINT-DERIVED:
  C2.<name>  test exists AND passes              (one per #test-plan row)
  C3  unit tests exist AND pass                  (only if gtest entries / unit/ paths)
```

Slice fields: `repo`, `object_kind`, `files_to_touch`, `scope` (top-level submodule; `moose/modules/<m>` → `moose`), `summary` + `physics` verbatim, `reuse_decisions[]`, `test_plan[]`, `out_of_scope[]`, `unit_on`, `reuse_only`, `blueprint_path`. A work plan adds `units[]` + `deps` from the JSON island — validate it (parses, deps resolve, acyclic, and units touching one file share an edge so the loop never dispatches them concurrently; violations → refuse with the reason, the user fixes the blueprint). If KaTeX is rendered, recover TeX from `<annotation encoding="application/x-tex">` nodes; Grep by block id rather than whole-file-Read the font-bloated HTML.

## Standing gates — not negotiable, not blueprint-editable

This skill owns the standing gates, and [`references/standing-gates.md`](references/standing-gates.md) is their one home. Blueprints render it read-only and cannot add, remove, reorder, or alter a gate. Every gate check maps to a ledger criterion; a gate is passed when its checks are green.

**Gate A** — `A1` build clean (C1), inside the loop's normal flow. **Gate B** — `B1`–`B6` (consistency sweep, suites green + gold staged, reuse / out-of-scope audit, SQA, ASCII, docs smoke; C2/C3, C4, C5, C6, DG), after `GOAL_MET`. Read the reference for each row's criterion, its exact check, and the agent or command it dispatches — before running Gate B, every run, because the list grows.

What the main thread runs itself, no further reading needed:

- **SQA** (`B4`, C5): grep the in-diff spec files for `requirement`/`design`/`issues` (parent-block declarations cover children), then `cd <doc-dir> && ./moosedocs.py check` — doc dir `moose/modules/doc` | `blackbear/doc` | `isopod/doc`. Errors filtered to the branch diff — pre-existing SQA debt is reported, not fixed. Env failure → surface the conda hint, note the grep audit still ran.
- **ASCII** (`B5`, C6): two scans over the branch diff, code then `.md`. Fix hits in place, re-run until clean. `.md`/`.bib` are excluded from the code scan **on purpose**, and the `.md` scan's `-CSD` is load-bearing — read the reference before "fixing" any diacritic or dropping a flag.

  ```bash
  git -C <scope> diff devel...HEAD -- . ':(exclude)*gold*' ':(exclude)*.md' ':(exclude)*.bib' \
    | perl -ne 'print if /^\+/ and /[^\x00-\x7F]/'
  ```

  ```bash
  git -C <scope> diff devel...HEAD -- '*.md' \
    | perl -CSD -ne 'print if /^\+/ and /[\x{2018}\x{2019}\x{201C}\x{201D}\x{00A0}\x{202F}\x{200B}\x{FEFF}]/'
  ```

When you get burned by CIVET on something new: add it to [`references/standing-gates.md`](references/standing-gates.md) as a standing check once, and every future run inherits it.

## Execution

Caps: `impl_iters` = 5 (`--core`) or 10 (full), `no_progress` = 2, `run_label` = worktree dir name.

Spawn one `moose-feature-loop` (`Agent`, `subagent_type: "moose-feature-loop"`, always background) with the spec slice + caps + `run_label`. Include `units[]` + `deps` when the blueprint has a work plan — the loop dispatches from that decomposition instead of deriving its own, and units joined by an edge never run concurrently. Briefly tell the user the goal + criteria + § Caveats, then let it run.

The loop owns C1–C6 internally; its criteria mirror the ledger, and Gate A's build happens inside its normal flow. On `GOAL_MET`, run Gate B yourself as the authoritative re-check: `B1` when it applies, then `B3`–`B6` (`B2` is already evidenced by the loop's runner). Chip each gate row as you go. A failed check → § Repair, then re-run only that check. Terminal handling: § Terminal statuses.

## Repair (the gate failure path)

Never route individual fixes yourself. Collect the failure evidence (compiler output / runner verdict / gate findings, with owning units) and wake the `moose-feature-loop` in **repair mode**: slice + caps + `repair: true` + ledger state (criteria already met, evidence) + the failures. It routes internally and returns a terminal status. On `GOAL_MET` resume the interrupted gate. Don't ping-pong: one repair pass per gate failure, woken via `SendMessage` for subsequent failures in the same run.

## Gold policy

`MISSING GOLD` / structural DIFF on newly authored tests is first-time capture, not baseline overwrite — regenerate without pausing: runner regenerates, confirms `OK`, stages (`git add`), **never commits**. Keep every gold file + observed values for the final report. A runner-flagged *possible real regression* routes to repair instead.

## Terminal statuses (from the loop)

| Loop returns | Action |
|---|---|
| `GOAL_MET` | → remaining gates. Carry files, commands, test counts, **staged gold + observed values**. |
| `NEEDS_DESIGN(reason)` | Stop. *"The blueprint needs a design change: `<reason>`. Re-run `/moose-blueprint`, then `/moose-build`."* |
| `BLOCKED(reason)` | Stop. Surface blocker + exact fix command (usually env: conda / missing `*-opt`). Don't auto-fix. |
| `STALLED(state)` | Surface unmet criteria + what was tried. `AskUserQuestion`: extend cap / simplify spec / abandon. On extend, re-spawn with higher `impl_iters` + prior state. |

## Docs (DG; skipped by `--core`)

**Docs ON** — spawn/wake `moose-docs-writer` with `scope`, base branch (`devel`), public surface, doc paths (the work plan's `doc` unit, when the blueprint has one). It authors and runs its nested write→smoke→fix loop (cap 3):

| Returns | Action |
|---|---|
| `DOCS_GREEN` | → report; carry warnings. |
| `NEEDS_CPP_CHANGE` | One C++ hop, no ping-pong: one-shot `moose-implementer` for exactly the named fix, one-shot `moose-test-runner` to confirm the suite, wake `docs-writer` to re-gate. |
| `DONE_WITH_CONCERNS` | `AskUserQuestion`: extend doc budget / escalate to implementer / ship as-is. |
| `BLOCKED` | Surface — likely env. Don't auto-fix. |

**Docs OFF (full mode, no pages authored)** — C++ renames can still break `!syntax` in untouched pages: spawn `moose-docs-builder` with `scope` + `devel`. `PASS`/`PASS_WITH_WARNINGS` → report. `FAIL` (`cpp-side`) → one-shot implementer for the `!syntax` regression + one-shot runner re-check + re-smoke. `FAIL` (`doc-side`) → surface (needs manual fix or a docs-on re-run). `BLOCKED` → surface.

## Status chips (blueprints with a work plan)

You own the blueprint's chips — the browser-side twin of the loop's ledger. `Edit` the chip span beside the unit's uid / at the gate row's start on every transition: work starts → `<span class="chip wip">running</span>`, evidence lands → `chip done`/`chip failed` (`done`/`failed` text). Edit only chip spans, nothing else. Drive the unit chips from the loop's iteration `SendMessage`s as they arrive, the gate chips from your own gate runs, and reconcile every chip at terminal. Blueprints with no work plan keep their `[]` markers, same transitions.

## Clean-context review (final step)

After every standing gate and the docs gate are green — the feature is otherwise done — spawn ONE fresh `moose-pr-reviewer` (`subagent_type: "moose-pr-reviewer"`, foreground) in **local mode**. Fresh spawn is the point: it has seen none of this build's context, so it reviews the diff the way a cold PR reviewer will.

```
Run a LOCAL review (mode: local) of this branch.
  repo_root: <absolute path to the scope submodule in this worktree>
  base_branch: devel
  label: <run_label>
Follow your local-mode workflow. No PR exists — never call gh.
Return your local summary block including the merged findings.
```

**Report-only.** Findings go into the final report verbatim (counts + the findings list + `/tmp/moose-review-<label>.md`); do not auto-route fixes — the user decides what to apply before committing. Offer once: apply the mechanical findings now, or leave them. An errored reviewer is noted, not retried more than once; zero findings is a valid (and reportable) result.

## Final report

Files created/modified per unit/child; exact runner commands + final counts (pass/fail/skip); **gold regenerated + observed values** flagged for physics sanity-check; standing-gate results (what was fixed in place, anything surfaced from `moosedocs.py check`); docs result (smoke PASS / warnings / log path, or "docs skipped (`--core`)"); **clean-context review findings** (verbatim, + findings file path); any `DONE_WITH_CONCERNS`; a **diff attribution audit** — group the diff into change classes and trace each to the blueprint's stated purpose (`moose/AGENTS.md` § Surgical Changes: every changed line traces to the request); flag unattributable hunks to drop, split out, or justify in the PR body; a suggested commit message.

## Caveats + boundaries

- **Never commit or push** — the run ends at the suggested commit message. Gold is staged, never committed.
- **Never run `clang-format`/`black`** — the pre-commit hook owns style.
- Worktrees, branches, conda envs are `/new-feature`'s job.
- Docs *build* is gated; doc *quality* isn't — warnings surface for manual review. Smoke is slow (~5–10 min/round).
- Interruptible anytime: the loop and the gates both narrate their progress (task list when those tools are enabled, `SendMessage` otherwise — plus the blueprint's chips) so the user can watch and stop.
