---
name: analysis-run
description: Reconciles every outstanding MOOSE analysis study against SLURM, then fires one approved study on HPC through the analysis toolkit (smoke, budget gate, dispatch) and reports the board with a diagnosis of any parked card. Use for "/analysis-run <study-id>", "fire the study", "reconcile the board", "re-fire my study".
disable-model-invocation: true
argument-hint: "[<study-id>]"
effort: medium
---

# /analysis-run

The toolkit is `${CLAUDE_PROJECT_DIR:-$PWD}/analysis/analysis` (a launcher that picks a python with PyYAML; no install; `$PWD` is the meta-root or worktree root when `CLAUDE_PROJECT_DIR` is unset, which the Bash tool does not export). The durable board, `analysis/studies/<id>/card.yaml`, is the source of truth between sessions, and the toolkit sets every lane from cluster reality; this skill supplies judgment and reports. `analysis/README.md` carries the lifecycle, the lane names, the command table, and the `study.yaml` schema.

## 2FA pre-check

HPC access rides the SSH ControlMaster in `~/.ssh/config`; the toolkit never authenticates. If the master is not up, a toolkit command parks the study in `connection_down` and the user has to type `! ssh bitterroot1.hpc.inl.gov true` (or `teton1`) in their own terminal to clear 2FA, then re-run this skill. Say this before the first command when a study is about to fire.

## Reconcile, then fire

Run reconcile as a Bash tool call, on every entry, before anything else. It is side-effecting (syncs SLURM, resubmits transient failures, parks systematic ones, collects and reports finished studies), so it does not belong in a `!cmd` block:

```bash
"${CLAUDE_PROJECT_DIR:-$PWD}/analysis/analysis" reconcile --all
```

Exit 1 means at least one card sits in an attention lane (`attention`, `budget_exceeded`, `connection_down`); that is a report item, not a failure of the skill.

With a study id in `$ARGUMENTS`, fire it:

```bash
"${CLAUDE_PROJECT_DIR:-$PWD}/analysis/analysis" run <study-id>
```

`run` smokes locally when the card has not passed smoke, gates on the worst-case core-hour estimate, then dispatches. It prints `<id>: state -> <lane>` plus the reasons for a parked lane and exits 1 on any parked lane; it refuses a study already in a live lane. With no id, reconcile and report only.

## Parked cards

Diagnose from `analysis status <id>` (last reasons and history) and the log tail: collected cases have `*.out` under `analysis/studies/<id>/results/case_<NNNN>/`; cases that failed keep their logs on the cluster under the `workdir:` line of the status output, in `logs/`, readable over `ssh <cluster>`. Report the likely cause (diverged, NaN, bad path, smoke failure, budget over the ceiling). An optimization study is marked terminal when its single job ends; convergence is your call from the objective history in the report, and hitting `max_iters` without converging is reported as such.

This skill does not edit inputs, specs, lanes, or cards, and it does not poll: after a fire, the study runs unattended and the next `/analysis-run` picks it up through reconcile. Fixes to an input or to `budget.ceiling_core_hours` in `study.yaml` are the user's.

## Report

Done when reconcile has run, the named study (if any) has been fired or its parked lane explained, and the reply lists what changed by lane: newly `done` studies with their `studies/<id>/results/report.html` path, `running` studies with progress, and each attention-lane card with its cause and the next step.
