---
name: analysis-status
description: Reads the MOOSE analysis board (studies, lanes, progress, budget) without touching SLURM or any card, and reports it by lane. Use for "check my studies", "study status", "how is my sweep doing", "what is on the analysis board".
argument-hint: "[<study-id>]"
effort: low
---

# analysis-status

Read-only view of `analysis/studies/*/card.yaml`. The board below is as of the last reconcile; it does not reflect jobs that finished on the cluster since then. Report by lane: `done` studies with their `studies/<id>/results/report.html`, live lanes (`dispatched`, `running`, `collecting`, `analyzing`) with progress, and each attention-lane card (`attention`, `budget_exceeded`, `connection_down`) with the reason on the card. A `done` study can carry flagged gaps (failed cases the report marks); say so when the progress line shows them.

To advance the board against SLURM or to fire a study, run `/analysis-run`; that skill owns reconcile and the parked-card diagnosis.

!`"${CLAUDE_PROJECT_DIR:-$PWD}/analysis/analysis" status $ARGUMENTS || true`
