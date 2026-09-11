---
name: moose-build
description: Drives one MOOSE feature from specs/blueprint.html to a green tree with the standing gates passed, docs gated, and a clean-context review; execution is the moose-feature-loop agent. Use for "/moose-build [blueprint.html] [--core]", "build the blueprint", "build this feature". Manual invoke only; ends at a suggested commit message and never commits.
disable-model-invocation: true
argument-hint: "[blueprint.html] [--core]"
effort: medium
---

# /moose-build

Turns a blueprint from `/moose-blueprint` into a build that compiles, whose new regression tests are green,
whose standing gates pass, and whose diff has been reviewed cold, then stops at a suggested commit message;
`/moose-ship` is the next human gate. This skill compiles the goal ledger, spawns the `moose-feature-loop`
agent to do the work, runs Gate B, drives the docs pass and the review, and reports. It never edits source,
routes fixes, commits, pushes, or runs a formatter (the pre-commit hook owns style); worktrees, branches, and
conda envs are `/new-feature`'s job. Say in a line what is about to happen before each stage and close with a
recap that stands on its own; only you see script output, so the report carries what the user needs.
`<repo>` below is the slice's `repo` (`moose`, `blackbear`, `isopod`, or `moose/modules/<m>`), `<scope>` its
top-level submodule, and `<meta-root>` the worktree root (the directory holding `.clangd`).

## Usage and refusals

`$ARGUMENTS` is `[blueprint.html] [--core]`; the blueprint defaults to `<worktree-root>/specs/blueprint.html`.
Refuse when there is no blueprint ("No blueprint found. Run `/moose-blueprint` first."), when the current
directory is not inside a `/new-feature` worktree (walk up to a `.git` file beside `moose/`, `blackbear/`, and
`isopod/`), or when `--core` is given and the slice's `doc_plan.needed` is true. `--core` skips only the docs
gate (DG); every other gate runs in full.

## Slice

`python3 <meta-root>/.claude/skills/moose-build/scripts/slice_blueprint.py --check --slice <blueprint>`
validates the seven contract blocks and the `#work-plan-data` island, then prints one JSON object with the
block text as plain text (TeX recovered) plus `units` and `deps`. A failing check prints its problems instead
and exits 1: show them verbatim and stop; the user fixes the blueprint.

## Goal ledger

Standing criteria, every run: C1 build clean, C4 reuse decisions honored and no out-of-scope edits, C5 specs
SQA-complete, C6 code ASCII-clean, DG docs smoke (unless `--core`). Blueprint-derived: one `C2.<name>` (test
exists and passes) per `test_plan` entry, and C3 (unit tests exist and pass) when `unit_on`. A blueprint adds
criteria; it never removes or weakens a standing one. The gate table is `references/standing-gates.md`; read
it at the start of every run, since the list grows.

## Execution

Caps: `impl_iters` 5 with `--core`, else 10; `no_progress` 2. `run_label` is the worktree directory name.
Spawn one `moose-feature-loop` (Agent, background) with the slice JSON, `caps`, and `run_label`; tell the
user the goal and the criteria in a few lines, then let it run. The loop posts a one-line SendMessage at each
round boundary: drive the blueprint's unit chips from those and the gate chips from your own gate runs, edit
only the chip spans (markup in `<meta-root>/.claude/skills/moose-blueprint/references/work-plan-format.md`),
and reconcile every chip at the end.

On `GOAL_MET`, run Gate B: `bash <meta-root>/.claude/skills/moose-build/scripts/gates.sh <repo> all --base
devel [--core]`, in the background with Monitor (the SQA check takes minutes). Pass `--core` when the run is
`--core` or when the docs-writer will run (its SMOKE line is then B6's evidence). Read the JSON lines, one per
gate, `{"gate":"sqa|ascii|docs","status":"PASS|FAIL|BLOCKED|SKIPPED","hits":[...],"hint":"..."}`, and the
final `{"gate":"all","status":...}`. B3, the reuse and out-of-scope audit, is your own Read and Grep pass over
the diff against `reuse_decisions` and `out_of_scope`. A BLOCKED gate is surfaced with its hint, not fixed.

## Repair

Never route fixes yourself. Wake the loop with SendMessage in repair mode: the slice, `caps`, `repair: true`,
the ledger state (criteria met, with their evidence), and the failure evidence (the gate hits or the B3
finding, with the owning unit). One repair pass per failure; on `GOAL_MET` re-run only the failed check.

## Gold

MISSING GOLD or a structural diff on a newly authored test is first-time capture, not a baseline overwrite:
the loop's runner regenerates, confirms OK, and stages with `git add`; nothing is committed. The final report
lists every gold file with its observed values for a physics sanity check. A runner-flagged possible
regression goes through repair instead.

## Terminal statuses

| Loop returns | Action |
|---|---|
| `GOAL_MET` | Gate B, then docs, then review. Carry files, commands, counts, staged gold with observed values, and any CONCERNS. |
| `NEEDS_DESIGN(reason)` | Stop: "The blueprint needs a design change: `<reason>`. Re-run `/moose-blueprint`, then `/moose-build`." |
| `BLOCKED(reason)` | Stop; surface the blocker and the exact fix command (usually env: conda or a missing `*-opt`). |
| `STALLED(state)` | Surface the unmet criteria and what was tried; `AskUserQuestion`: extend the cap, simplify the spec, or abandon. Extend re-spawns with a higher `impl_iters` and the prior state. |

## Docs (DG; skipped by `--core`)

Docs on (`doc_plan.needed`): spawn `moose-docs-writer` with the scope (`<repo>`), base branch `devel`, the
public surface (the objects and syntax the implementer's FILES register), and the doc paths (`doc_plan.pages`
and the work plan's `doc` unit); it authors the pages and runs the `docs.sh` smoke itself. `DOCS_GREEN`:
report. `NEEDS_CPP_CHANGE`: one hop only, a one-shot `moose-implementer` for the named change, a one-shot
`moose-test-runner` on the registered tests, then wake the writer. `DONE_WITH_CONCERNS`: `AskUserQuestion`:
extend the doc budget, escalate to the implementer, or ship as-is. `NEEDS_CONTEXT`: one-shot `moose-scout`
with its QUESTION, then wake the writer with the MATCHES. `BLOCKED`: surface. ASCII-gate hits in `.md` files
(from the loop's payload or Gate B) go to the writer too; with docs off they are surfaced.

Docs off with no pages authored: Gate B's `docs` line (`docs.sh <repo> smoke --diff devel`) is the check,
because a C++ rename can still break `!syntax` in untouched pages. A cpp-side FAIL (missing or renamed
registered syntax) gets one implementer hop and a `moose-test-runner` re-run of
`bash <meta-root>/.claude/skills/moose-docs/scripts/docs.sh <repo> smoke --diff devel`; a doc-side FAIL is
surfaced. The smoke gates the build, not doc quality.

## Clean-context review

When every gate is green, spawn one fresh `moose-pr-reviewer` (foreground) with `mode: local`,
`repo_root: <worktree-root>/<scope>`, `base_branch: devel`, `label: <run_label>`. It has seen none of this
build, which is the point. Report-only: its summary block and `/tmp/moose-review-<run_label>.md` go into the
final report verbatim, and zero findings is a valid result. Offer once to apply the mechanical findings;
otherwise the user decides before committing.

## Final report

Files created or edited per unit; the exact runner commands with final counts; gold files with observed
values; each gate's result and what repair changed; the docs result (smoke line and log path, or "docs
skipped (--core)"); the review summary and findings file; any CONCERNS carried; a diff attribution audit that
groups the diff into change classes and traces each to the blueprint's purpose (`moose/AGENTS.md` section 3,
Surgical Changes), flagging unattributable hunks to drop, split out, or justify in the PR body; a suggested
commit message; then "run `/moose-ship` when satisfied". Write the same report to
`<meta-root>/.claude/cache/moose-build-<run_label>.json` as
`{"runId": "<run_label>", "status": "<terminal status>", "report": "<text>"}`; the session-context hook
shows the newest record after a compaction. The run is interruptible at any point: the loop's SendMessages
and the chips show where it is.
