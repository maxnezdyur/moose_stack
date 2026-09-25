# Loop contract

The contract between `/campaign <id> loop` and the `campaign-loop` agent: the goal, the ledger of
criteria, one pass, the caps, and the report. The agent reads this file whole before its first
command.

## Goal

The goal is the frontmatter `stop:` of `campaign.md`, verbatim. The loop stops earlier at four
boundaries: the budget is spent, a finding refutes `## Hypothesis`, a `propose-only` campaign has
proposals that await a tick, or a SLURM run is still out.

## Ledger of criteria

Seed one entry per criterion before the first command and announce the goal and the criteria to
`main` in one SendMessage. Task tools are the ledger when the harness provides them; otherwise
keep the same list as a markdown checklist and post it at every transition.

| id | criterion | evidence |
|---|---|---|
| C1 | every ticked proposal ran and has a `done` ledger line | no `^- \[x\] D` line left under `## Proposed`, and a `  - done` line under each run launched this pass |
| C2 | every done run has a verdict | a `  - verdict` line under every run with a `done` line |
| C3 | every verdict cites a finding, or is `failed`/`inconclusive` with its note line (and a Do-not-repeat line for `failed`) | the third field of the verdict line is `F<n>` and that section exists in `FINDINGS.md`; or the `note:` and Do-not-repeat lines exist |
| C4 | spent is within budget | `<launcher> spent <id>`: every spent value at or below its budget |
| C5 | the stop is met, or a tick boundary is reached | a finding with `closes: yes` and a `<launcher> close <id> F<n>` that exited 0; or, under `propose-only`, unticked entries and no ticked one |

Update an entry the moment its evidence lands. A criterion is met only on a tool result from this
session.

## One pass

Each pass does only what the unmet criteria demand, in this order:

1. **Catch up.** Read `<launcher> status <id> --json` for the phase of every run.
   `<launcher> reconcile <id>` when any run is queued or running. `<launcher> collect <id> <D>`
   for every run finished and not collected. Learn every collected run with no
   verdict (`finding-rules.md`). This settles C2 and C3 for old runs first.
2. **Check the boundaries.** Stop with `GOAL_MET` on `closes: yes`, `REFUTED` on a hypothesis
   refutation from step 1, `BUDGET_SPENT` when `spent` shows no core-hours or no runs left or the
   wall days passed.
3. **Propose.** When no ticked or unticked entry is left in `## Proposed` and the autonomy is not
   `manual`, write the next entries (`proposal-rules.md`). Under `within-budget` tick those that
   fit, one `<launcher> tick <id> <D>` each. Under `propose-only`, stop with `NEEDS_TICK` naming the unticked ids.
4. **Run.** `<launcher> run <id> --ticked`. Under `manual`, skip this step: the user runs
   `campaign run` by hand. A local run blocks; start it with `run_in_background` when it may take
   over two minutes and wait for its completion notice before step 5.
5. **Wait.** `<launcher> reconcile <id>`. A SLURM run still queued or running ends the pass with
   `WAITING`; the skill owns the wait policy, so never sleep or poll in a loop here.
6. **Collect and learn** the runs that finished, as in step 1, then write the handoff
   (`finding-rules.md`, "The handoff after learn").
7. **Figure** when a group gained a run and its figure is stale (below). A figure never gates a
   criterion.

Then start the next pass. A refusal from `campaign run` (exit 2: unticked, a constraint knob, over
budget) is evidence, not a crash: withdraw or fix the entry per `proposal-rules.md` and continue.
Exit 4 with a `connection_down: <host>` line from any verb ends the pass with `WAITING`, naming
the host.

## Caps

`caps.max_passes` (default 5) ends the loop with `STALLED`. So does `caps.no_progress` (default 2)
consecutive passes that add no verdict and no finding.

## Figures

Spawn `moose-figure` once per stale group, and wake it with SendMessage on later passes. Its
prompt carries the gallery directory `<dir>/gallery/` in place of `<worktree-root>/specs/gallery/`,
the source (the `qoi.json` files of the group's runs, or a kept output under a run directory),
the figure list (`<file>: <what it shows and which finding it backs>`), and the size cap (5 MB).
The page is `<dir>/gallery/gallery.md` in the factory's format:

```
# Gallery: <id>
## Figure 1. <title>
![](<file.png>)
<one or two sentences: what it shows>
Look at: <one sentence>
Source: runs D012, D013, D014 `qoi.json`; rendered with <tool or script>.
```

State in its prompt that a campaign figure is a data plot of a measure against a varied knob, so
axes, ticks and labels are required, and that it runs nothing: every number it plots is already in
a `qoi.json`. Its `FIGURES_DONE` settles the figure; `BLOCKED` or `NEEDS_CONTEXT` becomes a
`FIGURE:` line in the payload and the loop continues.

## Report

One SendMessage to `main` at each pass boundary:
`pass 2: C1 C2 met; C3 unmet (D016 needs a finding); learning D016`.

The final message is exactly one status:

| status | when | payload |
|---|---|---|
| `GOAL_MET` | C5 met by a `closes: yes` finding | the closing finding heading, the runs and verdicts of this invocation, spent over budget, `FIGURE:` lines |
| `NEEDS_TICK(ids)` | `propose-only` and every criterion but C5 met | the unticked ids, each with its `tests:` sentence and estimate, the remaining budget |
| `WAITING(jobs or host)` | a SLURM run is still queued or running, or a verb exited 4 with `connection_down` | each run id, job id and `slurm.state`, or `connection_down: <host>` with "type `! ssh <host> true` in your terminal"; what is already judged |
| `BUDGET_SPENT` | C4 is at its limit | the spent JSON, the last finding, the best next run had budget remained |
| `REFUTED(F<n>)` | a finding refuted `## Hypothesis` | the finding heading, the old and the new hypothesis |
| `BLOCKED(question)` | a missing binary, a failed measure, a constraint that blocks every useful run | the exact question and the exact fix command |
| `STALLED(state)` | a cap fired | unmet criteria, what each pass tried, the best next human action |

Before returning any status, write the handoff: rewrite State, Next and Map; append one
Do-not-repeat line per failed run and one per pass that tried and failed; append one Sessions line
for this invocation (`- <date> <HH:MM> <run_label> loop: <passes>, <runs>, <findings>, <status>`);
bump `sessions`; set `updated`.
