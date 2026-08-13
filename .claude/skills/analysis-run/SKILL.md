---
name: analysis-run
description: Fire and reconcile a MOOSE analysis study for the fire-and-forget system. Reconciles the durable Kanban board against SLURM on every entry (a study submitted a week ago is picked up automatically), fires an approved study (smoke → budget-gate → dispatch to HPC), applies judgment to parked cards, and reports. Use when the user says "/analysis-run", "fire the study", "check my studies", "reconcile the board", or asks how a submitted analysis is doing.
disable-model-invocation: true
---

# /analysis-run

Execute and track fire-and-forget analysis studies. The durable board
(`analysis/studies/<id>/card.yaml`) is the source of truth; you are stateless
between sessions. Two things happen here: **reconcile** every outstanding study
against SLURM, and **fire** an approved one. The toolkit does the mechanics; you
supply judgment on parked cards.

## Usage

```
/analysis-run [<study-id>]     # fire that study; with no id, just reconcile + report
```

Run from inside `moose_stack`. SSH auth is delegated to `~/.ssh/config` — never
attempt to authenticate; if a probe fails, the study parks in `connection_down`.

## 1. Reconcile first — always

On every entry, before anything else, advance every outstanding card:

```bash
analysis/analysis reconcile --all
```

This syncs `sacct`/`squeue` over SSH, auto-resubmits transient failures, parks
systematic ones, enforces the budget ceiling, and drives finished studies through
collection and reporting to `done`. Then read the board:

```bash
analysis/analysis status              # whole board
analysis/analysis status <id>         # one card + recent history
```

Report to the user what changed: newly `done` studies (point at
`studies/<id>/results/report.html`), studies still `running` (progress), and
anything in an attention lane.

## 2. Fire an approved study

When given an id:

```bash
analysis/analysis run <id>            # smoke (local) → budget-gate → dispatch
```

Interpret the resulting lane:

- `dispatched` / `running` — report the case count and that it is on HPC. Done for now.
- `attention` (smoke failed) — show the smoke message; the input is broken. Do
  not retry blindly; help the user fix the input, then re-run.
- `budget_exceeded` — the estimate exceeds the ceiling. Surface the numbers;
  the user shrinks the study or raises the ceiling in `study.yaml`.
- `connection_down` — HPC unreachable. Ask the user to establish the master
  connection themselves, e.g. suggest they type ``! ssh teton1.hpc.inl.gov true``
  (or bitterroot) to clear 2FA, then re-run.

Never mark a study ready or done yourself — the toolkit sets lanes from reality.

Re-firing is safe: `run` refuses to resubmit a study already in a live lane, and
dispatch adopts any submission already carrying the study's `an-<id>` job name
(so a dropped ssh right after submit never causes a lost or duplicated array).

## 3. Judgment on parked cards

The toolkit parks; you diagnose. For each card in `attention`:

- **Systematic case failure**: read the diagnosis on the card. If useful, pull
  the log tail to explain the cause (diverged, NaN, bad path):
  `analysis/analysis fetch-fields <id> -c <case>` is for fields; for logs, the
  console output is under the study's remote `logs/` (rsync or `ssh <cluster> tail`).
  Summarize the likely cause. Do **not** edit the input to "fix" it unattended —
  surface it and let the user decide.
- **Partial sweep** (some done, some failed): the report already covers the good
  cases and flags the bad. Tell the user the study is usable with gaps.
- **Optimization done-ness**: the toolkit marks the single job terminal; you
  judge convergence from the objective history in the report. If it hit
  `max_iters` without converging, say so plainly.

## 4. When to notify vs wait

Fire-and-forget means nothing runs the AI while the user is away. After firing,
tell the user the study is on HPC and that reopening Claude later will pick it up
via reconcile. Do not poll in a loop. If they ask for a proactive ping when a
study finishes, that needs a scheduled reconcile (out of scope here) — offer it,
don't assume it.

## Caveats

- `/scratch` may be purged; the card records provenance (app/sha/module hash) so
  a purged study can be re-fired.
- A study built on one cluster is not reused on the other (cache is keyed by
  cluster); firing the same study `--cluster teton` rebuilds there.
