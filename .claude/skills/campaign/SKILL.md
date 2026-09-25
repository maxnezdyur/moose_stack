---
name: campaign
description: Drives one campaign of open-ended experimental work (one question, a stop condition, a budget, an append-only record of runs and findings) in a project repository's campaigns/<id>/ through the campaign CLI; loop mode is the campaign-loop agent. Use for "/campaign <id> [new|propose|run|learn|report|loop] [note]", "start a campaign", "propose the next runs", "run the ticked proposals", "judge the runs", "campaign report". Manual invoke only; never commits and never raises a budget.
disable-model-invocation: true
argument-hint: "<id> [new|propose|run|learn|report|loop] [note]"
effort: high
---

# /campaign

`$ARGUMENTS` is `<id> [subcommand] [note]`. The subcommand defaults to `loop`. The note is folded
into the handoff as a Gotchas or Decisions line. The formats are the contract:
`<meta_repo>/campaign/README.md` (verbs, exit codes, invariants) and
`<meta_repo>/campaign/formats/{campaign,ledger,findings,manifest}.md`. Read the format of every
file before you write to it.

!`C="${MOOSE_FACTORY_CONFIG:-$HOME/.config/moose-factory/config.toml}"; M="$(sed -n -e 's/[[:space:]]*#.*$//' -e 's/^[[:space:]]*meta_repo[[:space:]]*=[[:space:]]*//p' "$C" 2>/dev/null | head -n 1 | tr -d '"')"; M="${M:-$HOME/projects/moose_stack}"; M="${M/#\~/$HOME}"; L="$M/campaign/campaign"; echo "meta_repo: $M"; if [ -x "$L" ]; then echo "launcher: $L"; else echo "launcher: MISSING at $L"; fi; R="$PWD"; while [ "$R" != "/" ] && [ ! -d "$R/campaigns" ]; do R="$(dirname "$R")"; done; if [ -d "$R/campaigns" ]; then echo "project root: $R"; else echo "project root: none (no campaigns/ above $PWD)"; fi; [ -x "$L" ] && "$L" status $1 2>&1 | head -n 30; true`

## Resolve and refuse

- `<meta_repo>` and `<launcher>` are the first two lines above. They come from the `meta_repo` key
  of `~/.config/moose-factory/config.toml` (`$MOOSE_FACTORY_CONFIG` overrides the location), with
  `$HOME/projects/moose_stack` as the fallback. Never write a user name into a path. Call the
  launcher by that absolute path. A missing launcher: stop and say so.
- `<root>` is the nearest parent of the cwd that holds `campaigns/`. `<dir>` is
  `<root>/campaigns/<id>`. Pass `--root <root>` to every verb that takes it.
- Refuse with one sentence when no `<root>` exists: "No campaigns/ directory above this
  directory; run /campaign from the project repository that holds the campaign." The one
  exception is `new`: with no `campaigns/` above, `<root>` is `git rev-parse --show-toplevel`.
- Refuse every subcommand except `new` when `<dir>/campaign.md` is absent. Refuse `new` when it
  is present.
- Refuse any subcommand but `report` when `status:` is `done` or `abandoned`.
- An empty `<id>`: ask for it with `AskUserQuestion`, listing the directories under
  `<root>/campaigns/`.

## Rules

These hold for every subcommand and for the `campaign-loop` agent.

1. Write only inside `<dir>`: `campaign.md` (the sections its format lets the loop write),
   `FINDINGS.md` (append), `handoff.md`, `gallery/`, and new files in `scripts/`. Never edit an
   input file of the project, a `manifest.yaml`, a `qoi.json`, or a script that a `## Measures`
   row names. A changed measure is a new script and a new row.
2. Never edit or delete a line that exists in `LEDGER.md`, `FINDINGS.md`, `## Measures`, or the
   append-only sections of `handoff.md`. A wrong line earns a later line that says so. Never
   edit `LEDGER.md` by hand: a note goes through `<launcher> note <id> <D> "<text>"`.
3. Never raise the budget and never edit the frontmatter `budget` block. Budget and the tick are
   the user's gates (README invariant 4).
4. Tick only with `<launcher> tick <id> <D>`, and only under `autonomy: within-budget`; never
   edit a checkbox by hand. Close only with `<launcher> close <id> F<n>`; never edit `status` or
   `closed` by hand. Under `manual`, never launch a run.
5. Nothing runs outside `campaign run`: no bare `mpiexec`, `srun`, `sbatch`, or remote job
   command (invariant 1). `campaign collect` runs the measures; do not run them by hand.
6. Never propose a command that changes a knob in `## Constraints`.
7. Never commit, push, or switch branches. Say what to commit in the report.

## SSH first

For a non-local cluster, SSH rides the ControlMaster in `~/.ssh/config`; the tool never
authenticates. A verb that cannot reach the cluster exits 4 and prints a `connection_down: <host>`
line. That is a wait, not a failure: say "type `! ssh <host> true` in your own terminal to clear
2FA, then run `/campaign <id>`", and stop the subcommand there. Say it before the first `run`,
`reconcile` or `bringup` against a cluster too.

## new

Grill with `AskUserQuestion`, batching independent questions (up to 4 per call). Fill every field
from answers, never from assumptions:

| call | questions |
|---|---|
| 1 | the question (one sentence); the stop condition; the app; the cluster |
| 2 | the budget as three numbers (core-hours, wall days, max runs); the autonomy level (default `propose-only`) |
| 3 | the constraints: the knobs a run may not change, with value and why; what is out of scope |
| 4 | the first measures: name, unit, and how (a backtick command or `csv:<file>:<column>:<last\|max\|min>`) |

A stop condition that names no measure from call 4 and no number is not accepted; ask again.
Ground each measure: its script or its CSV column exists, or the user says it will be written
into `<dir>/scripts/`. Then:

```
<launcher> new <id> --root <root>
```

Fill `campaign.md` from the answers: frontmatter, `## Hypothesis` (ask for it in call 1 when the
question implies none), the constraints table, the measures rows. Leave `## Proposed` with no
entry. When `handoff.md` is absent, seed it as `/handoff` does for a campaign
(`.claude/skills/handoff/SKILL.md`, Preconditions). Run `<launcher> validate <id>` and fix every
error it reports until it exits 0. Show a one-`AskUserQuestion` summary (question, stop, budget,
cluster, autonomy, knobs, measures): "Looks good", "Change ...", "Cancel". On approval set
`status: active`, append a Sessions line, and end with: "Campaign written. Run `/campaign <id>
propose`." Never tick a box in `new`.

## propose

Read `campaign.md`, `LEDGER.md`, `FINDINGS.md` and `handoff.md` whole. Then follow
`references/proposal-rules.md`: mint ids with `<launcher> next-id <id>`, write the entries under
`## Proposed`, and run `<launcher> validate <id>` until it exits 0. Then, by autonomy:

| autonomy | then |
|---|---|
| `propose-only` | stop and name the ids that await your tick in `campaign.md` |
| `within-budget` | `<launcher> tick <id> <D>` for each entry whose estimate fits `<launcher> spent <id>`, by the tick rule in the reference; name any left unticked and why |
| `manual` | refuse before writing anything: "autonomy is manual; propose runs by hand." |

## run

Under `manual`, launch nothing: reconcile, collect, and print the `campaign run` command for the
user. Otherwise launch `<launcher> run <id> --ticked`, or `<launcher> run <id> <D>` when the note
names one run. A local run blocks until it exits; launch it with `run_in_background` when it may
exceed two minutes and wait with Monitor. Then apply the wait policy to every SLURM run:

- Run `<launcher> reconcile <id>` once now.
- Read the phase of every run from `<launcher> status <id> --json`. A run still queued or running
  stays out. In a `/loop` session,
  reconcile every 10 minutes while one remains: with a fixed interval, end the turn and let the
  next tick reconcile; in a self-paced `/loop`, call ScheduleWakeup with 600 seconds. In any other
  session, do not poll: report each run still out with its job id and its `slurm.state`, and say
  that `/loop 10m /campaign <id> run` or a later `/campaign <id>` picks it up.
- Run `<launcher> collect <id> <D>` for every run the JSON shows finished and not collected.
  `collect` is idempotent.

## learn

For each run `status --json` shows collected and not judged, follow `references/finding-rules.md`: judge the
verdict against the run's `hypothesis` from its `qoi`, write the finding first, then record it
with `<launcher> verdict <id> <D> <word> --finding F<n> --by loop`. Then write the handoff:
rewrite `## State`, `## Next` and `## Map`; append Do-not-repeat, Decisions and one Sessions
line; bump `sessions`; set `updated`. On a closing finding, run `<launcher> close <id> F<n>`. On a finding that refutes `## Hypothesis`, rewrite it and append a Decisions line
that cites the finding.

## report

A digest for the human, three to eight lines, no pasted evidence. It writes nothing.

1. Findings since the date of the last `## Sessions` line, one heading each (`F<n>. <claim>`).
2. Spent over budget from `<launcher> spent <id>`: core-hours, runs, wall days.
3. Verdict counts from the ledger (`supported`, `refuted`, `inconclusive`, `failed`).
4. Proposals awaiting a tick: the ids of `^- \[ \] D` lines under `## Proposed`.
5. Figures: each `## Figure` heading in `<dir>/gallery/gallery.md`, or "no figures".
6. The single next move, as one command or one file to edit.

## loop

Spawn one `campaign-loop` agent (Agent, background) with: `<root>`, `<dir>`, `<launcher>`,
`<meta_repo>/.claude/skills/campaign/references/`, the autonomy, `caps: {max_passes: 5,
no_progress: 2}`, `run_label` (`<id>-<YYYYMMDDTHHMM>`), and the note. Tell the user the goal (the
`stop:` sentence) and the criteria in a few lines, then relay its one-line round messages. The
agent owns the handoff for its passes. The contract is `references/loop-contract.md`. On return:

| agent returns | action |
|---|---|
| `GOAL_MET` | run `report`; say the stop condition is met and name the closing finding |
| `NEEDS_TICK(ids)` | run `report`; "Tick <ids> in `campaign.md`, then run `/campaign <id>`." |
| `WAITING(jobs or host)` | for jobs, apply the wait policy under `run`; for `connection_down: <host>`, give the ssh line from "SSH first"; then run `report` |
| `BUDGET_SPENT` | run `report`; offer three moves: raise the budget by hand with a Decisions line, `<launcher> close <id> --abandon "<reason>"`, or stop here |
| `REFUTED(F<n>)` | run `report`; show the finding heading and the rewritten `## Hypothesis`; the next pass waits for you |
| `BLOCKED(question)` | surface the question verbatim with the exact fix command |
| `STALLED(state)` | surface what each pass tried; `AskUserQuestion`: another five passes, abandon, or stop |

## Close

When a subcommand wrote to `<dir>`, list the files it changed and the suggested commit:
`git -C <root> add campaigns/<id> && git -C <root> commit -m "campaign <id>: <what>"`. Run no git
write yourself.
