---
name: moose-build
description: Drives one MOOSE feature from specs/blueprint.md to a green tree with the standing gates passed, docs gated, and a clean-context review whose findings are applied before it stops; execution is the moose-feature-loop agent. Use for "/moose-build [blueprint.md] [--core] [--verify N] [--verify-only] [--auto]", "build the blueprint", "build this feature". --auto (from /moose-auto) asks nothing and stops where it would ask. Manual invoke only; ends at a suggested commit message and never commits.
argument-hint: "[blueprint.md] [--core] [--verify N] [--verify-only] [--auto]"
effort: medium
---

# /moose-build

Turns a blueprint from `/moose-blueprint` into a build that compiles, whose new regression tests are green,
whose standing gates pass, and whose diff has been reviewed cold with the findings applied, then stops at a suggested commit message;
`/moose-ship` is the next human gate. This skill compiles the goal ledger, spawns the `moose-feature-loop`
agent to do the work, runs Gate B, drives the docs pass and the review, and reports. It never edits source,
routes fixes, commits, pushes, or runs a formatter (the pre-commit hook owns style); worktrees, branches, and
conda envs are `/new-feature`'s job. Say in a line what is about to happen before each stage and close with a
recap that stands on its own; only you see script output, so the report carries what the user needs.
`<repo>` below is the blueprint's `repo` (`moose`, `blackbear`, `isopod`, or `moose/modules/<m>`), `<scope>` its
top-level submodule, and `<meta-root>` the worktree root (the directory holding `.clangd`).

## Usage and refusals

`$ARGUMENTS` is `[blueprint.md] [--core] [--verify N] [--verify-only] [--auto]`; the blueprint defaults to `<worktree-root>/specs/blueprint.md`.
`--auto` is the autonomous run of `/moose-auto`; see "Auto mode". `--verify N` sets the number of claim
testers (default 3; 0 skips B7). `--verify-only` is for a build whose newest record is `GOAL_MET`: it reads
the blueprint, skips the loop, the docs pass and Gate B, captures the after proofs and runs the claim round
(see "Proof and claim round") on the built tree, runs the review only when the round repaired code, and
writes a new record.
Refuse when there is no blueprint ("No blueprint found. Run `/moose-blueprint` first."), when the current
directory is not inside a `/new-feature` worktree (walk up to a `.git` file beside `moose/`, `blackbear/`, and
`isopod/`), or when `--core` is given and the doc plan says `Needed: yes`. `--core` skips only the docs
gate (DG); every other gate runs in full. Refuse also when `<meta-root>/.factory-lease` exists and its
`{bg_id, session_id, pid}` names a live session that is not this one: print that the workspace is held
and stop, because two builds in one worktree fight over `specs/blueprint.md`, one conda env and one git
index (a lease whose owner process is gone is reported as stale, never stolen; the user clears it with
`~/projects/moose_stack/factory/factory release <feature>`).

## Read the blueprint

Read `blueprint.md` whole (format: `<meta-root>/.claude/skills/moose-blueprint/references/blueprint-format.md`).
The frontmatter gives `repo`, `scope`, and `object_kind`; the fenced `json` block under `## Work plan` gives
`units`, `deps`, and every `status`. Before spawning anything, confirm the file passes the "Checks before you
stop" list in that format document (headings present, JSON parses, deps resolve and are acyclic, edge-free
units own disjoint files, test units name test headings, `## Verify` and `## Proof` pass their checks,
`status: approved`). A failing check is shown verbatim and the run stops; the user fixes the blueprint. A
blueprint written before `## Proof` existed has none: take `Kind: figure` when it has a `## Showcase`, else
`Kind: none` with `Why: older blueprint`, and say so in one line. A blueprint without `## Verify` gets its
claim written from `## Summary` and the test plan at the claim round; say so in one line too.

## Goal ledger

Standing criteria, every run: C1 build clean, C4 reuse decisions honored and no out-of-scope edits, C5 specs
SQA-complete, C6 code ASCII-clean, C7 the claim verified by fresh testers (see "Proof and claim round"), DG
docs smoke (unless `--core`). Blueprint-derived: one `C2.<name>` (test
exists and passes) per `test_plan` entry, and C3 (unit tests exist and pass) when `unit_on`. A blueprint adds
criteria; it never removes or weakens a standing one. A `showcase` unit is not a criterion: it rides along
with the loop and is reported on its own line, never as a gate. A proof is not a criterion either. The gate table is `references/standing-gates.md`; read
it at the start of every run, since the list grows.

## Execution

Caps: `impl_iters` 5 with `--core`, else 10; `no_progress` 2. `run_label` is the worktree directory name.
Spawn one `moose-feature-loop` (Agent, background) with the blueprint path, `caps`, and `run_label`; set the
frontmatter `status:` to `building`; tell the user the goal and the criteria in a few lines, then let it run.
The loop posts a one-line SendMessage at each round boundary: on each one edit the matching unit's `"status"`
in the fenced JSON (`idle`, `running`, `done`, `failed`), and edit the `gates` entries from your own gate runs.
Edit nothing else in the file; the human's view is `blueprint.html`, packed from `blueprint-page.html`, and a status edit to the markdown does not change it. Reconcile every status at
the end and set the frontmatter `status:` to `built` on success.

On `GOAL_MET`, run Gate B: `bash <meta-root>/.claude/skills/moose-build/scripts/gates.sh <repo> all --base
devel [--core]`, in the background with Monitor (the SQA check takes minutes). Pass `--core` when the run is
`--core` or when the docs-writer will run (its SMOKE line is then B6's evidence). Read the JSON lines, one per
gate, `{"gate":"sqa|ascii|docs","status":"PASS|FAIL|BLOCKED|SKIPPED","hits":[...],"hint":"..."}`, and the
final `{"gate":"all","status":...}`. B3, the reuse and out-of-scope audit, is your own Read and Grep pass over
the diff against `reuse_decisions` and `out_of_scope`. A BLOCKED gate is surfaced with its hint, not fixed.

## Repair

Never route fixes yourself. Wake the loop with SendMessage in repair mode: the blueprint path, `caps`, `repair: true`,
the ledger state (criteria met, with their evidence), and the failure evidence (the gate hits or the B3
finding, with the owning unit). One repair pass per failure; on `GOAL_MET` re-run only the failed check.

## Gold

MISSING GOLD or a structural diff on a newly authored test is first-time capture, not a baseline overwrite:
the loop's runner regenerates, confirms OK, and stages with `git add`; nothing is committed. The final report
lists every gold file with its observed values for a physics sanity check. A runner-flagged possible
regression goes through repair instead.

## Auto mode

With `--auto`, no human is present, so the build asks nothing and lowers no bar. Every gate,
criterion, cap and refusal stays as written. A blueprint approved by auto mode is legal: its
`blueprint_approved` record says `by: auto`.

- `STALLED(state)`: do not ask. Stop, and report the unmet criteria and what was tried. Never
  extend the cap and never simplify the spec on your own.
- Docs `DONE_WITH_CONCERNS`: do not ask. Stop with `STALLED(docs: <concerns>)`.
- Held review findings stay held. List them in the report, as usual.
- Never commit, push, or grant `ship`.
- The final report, the handoff and the board run happen as usual. Record each stop that replaced a
  question as one `## Decisions` line in the handoff.

## Terminal statuses

| Loop returns | Action |
|---|---|
| `GOAL_MET` | Gate B, then docs, then the proof and claim round, then review and apply. Carry files, commands, counts, staged gold with observed values, and any CONCERNS. |
| `NEEDS_DESIGN(reason)` | Stop: "The blueprint needs a design change: `<reason>`. Re-run `/moose-blueprint`, then `/moose-build`." |
| `BLOCKED(reason)` | Stop; surface the blocker and the exact fix command (usually env: conda or a missing `*-opt`). |
| `STALLED(state)` | Surface the unmet criteria and what was tried; `AskUserQuestion` (under `--auto`: stop, see "Auto mode"): extend the cap, simplify the spec, or abandon. Extend re-spawns with a higher `impl_iters` and the prior state. |

## Docs (DG; skipped by `--core`)

Docs on (`Needed: yes` in the doc plan): spawn `moose-docs-writer` with the scope (`<repo>`), base branch
`devel`, the public surface (the objects and syntax the implementer's FILES register), and the doc paths
(the doc plan's pages and the work plan's `doc` unit); it authors the pages and runs the `docs.sh` smoke itself. `DOCS_GREEN`:
report. `NEEDS_CPP_CHANGE`: one hop only, a one-shot `moose-implementer` for the named change, a one-shot
`moose-test-runner` on the registered tests, then wake the writer. `DONE_WITH_CONCERNS`: `AskUserQuestion` (under `--auto`: stop, see "Auto mode"):
extend the doc budget, escalate to the implementer, or ship as-is. `NEEDS_CONTEXT`: one-shot `moose-scout`
with its QUESTION, kind `doc`, the `<repo>` directories as scope and at most 8 files to open, then wake the
writer with the MATCHES. `BLOCKED`: surface. ASCII-gate hits in `.md` files
(from the loop's payload or Gate B) go to the writer too; with docs off they are surfaced.

Docs off with no pages authored: Gate B's `docs` line (`docs.sh <repo> smoke --diff devel`) is the check,
because a C++ rename can still break `!syntax` in untouched pages. A cpp-side FAIL (missing or renamed
registered syntax) gets one implementer hop and a `moose-test-runner` re-run of
`bash <meta-root>/.claude/skills/moose-docs/scripts/docs.sh <repo> smoke --diff devel`; a doc-side FAIL is
surfaced. The smoke gates the build, not doc quality.

## Showcase

A blueprint with a `## Showcase` section carries `showcase` units, which the loop dispatches to `moose-figure`
like any other unit; the evidence is that every file the unit names exists in `<meta-root>/specs/gallery/` and
`specs/gallery/gallery.md` has a `## Figure` section for each. Check that yourself with Read and Glob when the loop
returns, since nothing else does. A showcase unit never blocks C1 to C6 and never gates the run: a figure that
did not render is a `SHOWCASE:` line saying which file is missing and the agent's reason, and the build still
reports its real status. The files are gitignored, so they are never committed; the board links them from the
feature's card through `~/projects/moose-factory/Gallery/<feature>`, and `/moose-ship` attaches the ones a
proof names to the PR.

## Proof

The `## Proof` section of the blueprint names what the PR shows a reviewer that CI cannot. `/moose-ship`
puts it in the PR body. A proof gates nothing; a missing or weak proof is a `PROOF:` line in the report, and
the build still reports its real status. Never capture a test result, a gate result or a CI run as a proof.
Text proofs land in `<meta-root>/specs/proof/`. Every image a proof names is a `## Showcase` file, so
`moose-figure` renders it once in the loop and nothing here renders a second copy. Write
`specs/proof/proof.md`: one `## <title>` heading per proof, the file, one sentence on what it shows, the
precondition it met, and its status (`ok`, `weak (<why>)` or `skipped (<why>)`). Make the directory when it
is absent.

**Before, at the start of the run.** Capture every `-before` text proof right after "Read the blueprint" and
before the loop starts, while the checkout is still at the base ref. Confirm that `<scope>` has no diff from
its merge base with `devel`; when it has one, record `PROOF: before skipped (the diff exists)` for each
`-before` file. Write the probe script the bullet names to `specs/proof/`, run it through
`bash <meta-root>/scripts/conda-run.sh -C <scope> -- bash <probe>`, and save its output as
`<name>-before.txt` or `.md`. The probe needs a built binary: when it is missing or older than the sources,
run one build-only `moose-test-runner` round (no `--re=`) first. A probe whose input uses a name the feature
adds prints the error, and that error is the before proof. A `comparison` takes its before numbers (the
replaced method) from the same binary after the build, so it captures nothing here.

**After, once Gate B is green.** Run each probe again on the built binary and save `<name>-after.*`; a
`comparison` probe runs both methods now. A `figure` proof is the showcase figures, checked as "Showcase"
says.

**Check every proof yourself** with Read when it is captured, because nothing else does. A proof is weak
when it does not show the claim, or when it was captured without its `Precondition:` (two refinement levels
for a rate claim, different solver settings for the two methods of a comparison). Record
`PROOF: <file> weak (<why>)`, capture it once more, and never present a weak proof as a strong one. Under
`--auto` the same rules apply; the report lists every weak and skipped proof.

## Proof and claim round (B7, C7)

Run it after Gate B and the docs pass, before the review, so that a failed claim is repaired while the build
is still open and the review then reads the repaired code. Say in one line which parts run.

1. **After proofs.** Capture them as "Proof" says.
2. **The claim.** Take it from the blueprint's `## Verify` section (`Claim:`, `Reproduce:`,
   `Must still work:`). Without that section, write it from `## Summary` and the test plan: one claim,
   the command of the test that proves it, and `run_tests --re=` of the scope's tests that share its
   directory.
3. **The round.** Write 3 briefs by default (`--verify N` changes it; `--verify 0` skips B7): a
   `reproduce` brief from `Reproduce:`, a `variations` brief (the same command with one changed
   `cli_args` value that the claim must survive: one more refinement, a second parameter value, the AD
   twin), and a `regression` brief from `Must still work:`. Each brief carries `<meta-root>`, `<scope>`,
   the claim, the commands, the expected result, and the instruction to report STATUS GREEN only when
   the output shows that result and to quote the lines that show it. Spawn one fresh `moose-test-runner`
   per brief, in the foreground, the next one only when the previous one has returned; none has seen the
   build. Write the briefs and the reports to `<meta-root>/specs/verify/build-<k>.md`.
4. **The verdict.** C7 is met when the `reproduce` and `variations` testers saw the claim hold and the
   `regression` tester is GREEN. A failure that the base already had (the before proof shows it) is
   reported, not repaired. Otherwise the testers' commands, outputs and FAILURES lines are the repair
   evidence: wake the loop in repair mode as "Repair" says, re-run Gate B for the files it changed, then
   re-run the failed briefs, plus the `reproduce` brief when the repair changed code. Stop after 2 claim
   rounds: an unmet C7 is `STALLED(claim: <what failed>)`, handled as in the terminal statuses table, and
   the review does not run.

Mirror B7 into the blueprint's `gates` like the other rows: PASS is `done`, FAIL is `failed`, and SKIPPED
stays `idle`. A blueprint whose `gates` has no `B7` row predates it: add the row. After the review's fixes,
run no proof capture and no B7; Gate B in full is the check, as "Clean-context review" says.

## Clean-context review

When every gate is green and the claim round has met C7 (or was skipped), spawn one fresh `moose-pr-reviewer` (foreground) with `mode: local`,
`repo_root: <worktree-root>/<scope>`, `base_branch: devel`, `label: <run_label>`. It has seen none of this
build, which is the point. Its summary block and `/tmp/moose-review-<run_label>.md` go into the final report
verbatim, and zero findings is a valid result. Copy that findings file to `<meta-root>/specs/review-<run_label>.md`
the moment it exists, since `/tmp` is purged at boot and the worktree copy is what the board rescues and links.

Then apply the findings. Do not ask first: the user granted the build, and a finding left for them to apply
by hand is the review's cost with none of its value. Sort each finding once. It is *applicable* when the fix
stays inside the blueprint: no change to `summary`, the physics, a `reuse_decisions` row, `out_of_scope`, a
registered object or parameter name, or a `test_plan` entry. Otherwise it is *held*. Wake the loop once in
repair mode with the ledger state and the applicable findings as the failure evidence, `required` before
`suggested`, each with its file, line, text and the owning unit; a held finding is not sent. One pass, the
same cap as any repair. On `GOAL_MET` re-run Gate B in full, plus the docs smoke when a `.md` file changed,
then read the diff yourself and confirm each applied finding is present, the way B3 audits reuse; a finding
the loop reported applied but the diff does not show goes back to held with that reason. Never spawn a
second reviewer: the audit is the check, and a second review would review its own fixes. Append one line
to the blueprint's `## Amendments`: the review label, how many were applied, how many held.

## Final report

Files created or edited per unit; the exact runner commands with final counts; gold files with observed
values; each gate's result and what repair changed; the docs result (smoke line and log path, or "docs
skipped (--core)"); one `SHOWCASE:` line naming each gallery file with its `gallery.md` section heading, or "no showcase in the
blueprint"; one `PROOF:` line per proof file, `PROOF: <file> ok`, `weak (<why>)` or `skipped (<why>)`, or
`PROOF: none (<Why:>)`; the claim round: the claim, each tester's verdict, and the path of `specs/verify/build-<k>.md`; the review summary and findings file, the applied count, and every held finding verbatim with why it is held, so the user decides those before `/moose-ship` and nothing else waits; any CONCERNS carried; a diff attribution audit that
groups the diff into change classes and traces each to the blueprint's purpose (`moose/AGENTS.md` section 3,
Surgical Changes), flagging unattributable hunks to drop, split out, or justify in the PR body; a suggested
commit message; then "run `/moose-ship` when satisfied". Write the same report to
`<meta-root>/.claude/cache/moose-build-<run_label>.json` as
`{"runId": "<run_label>", "status": "<terminal status>", "report": "<text>"}`; the session-context hook
shows the newest record after a compaction. The run is interruptible at any point: the loop's SendMessages
and the status fields in the blueprint show where it is. Then run `~/projects/moose_stack/factory/factory board`
(absolute path; no `factory/` exists in this worktree) so the card moves to its new lane, and say which lane in one
line; a card left in the old lane is the first thing asked about after a build.

Then write the handoff, `<meta-root>/specs/handoff.md`, seeding it from
`<meta-root>/.claude/skills/handoff/references/handoff-template.md` when it is absent: rewrite
`## State`, `## Next` and `## Map`; append one `## Do not repeat` line per failed unit and per failed
gate from the rounds (`- <date>: tried X; failed because Y; evidence <path>; retry only if Z`), one
`## Decisions` line per AskUserQuestion outcome, and one `## Sessions` line; then bump `sessions` and
set `updated`. Never delete or edit a line already in an append-only section (the disciplines are in
`.claude/skills/handoff/references/handoff-rules.md`). A worktree's `.claude/` is frozen at the day it
was created, so both reference files are often absent there: fall back to
`~/projects/moose_stack/.claude/skills/handoff/references/`, which is canonical, and if the seven
headings are still out of reach write them from the table in `/handoff`. `factory refresh-pipeline
<feature>` is the real repair. On `STALLED` or `BLOCKED` write the handoff from the loop's `HANDOFF:`
block before reporting, because that is the moment the next session needs it.
