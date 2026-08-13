---
name: analysis-blueprint
description: Turn a vague MOOSE analysis idea into a reviewable study.yaml for the fire-and-forget analysis system. Grill the user on kind/app/baseline/params/QoIs/budget, scaffold the study dir, write and validate the spec, and stop at an approved artifact. Does NOT fire — /analysis-run executes it. Use when the user says "/analysis-blueprint", wants to plan a parameter sweep, convergence study, or optimization run.
disable-model-invocation: true
---

# /analysis-blueprint

Convert an analysis idea into a concrete `analysis/studies/<id>/study.yaml` that
`/analysis-run` executes fire-and-forget. The spec is the one load-bearing
review: in a fire-and-forget system, an underspecified study burns HPC time
unattended. Grill until every field is grounded, then stop at a validated,
approved spec. Do NOT fire.

## Usage

```
/analysis-blueprint <freeform idea>
```

e.g. `/analysis-blueprint sweep thermal conductivity and find where peak temperature exceeds 900 K`.

Run from inside `moose_stack` (the toolkit is at `analysis/`). The study runs an
existing input with command-line overrides — no C++ or input edits.

## 1. Pick a study id + kind

Derive a short kebab-case `<id>`. Classify the `kind`:

- **sweep** — vary parameters over a grid/list, collect QoIs. Embarrassingly parallel.
- **convergence** — refine one parameter (mesh/timestep) over levels, fit an order.
- **optimization** — a single self-driving job (isopod / calibration); bounded by `max_iters`.

## 2. Grill the contract (one axis at a time)

Fill every field before writing. Ask; do not assume. Use `AskUserQuestion`
where a choice is real.

- **App + baseline input**: which app (`moose`/`combined`/`blackbear`/`isopod`) and
  which existing `.i`. The input must exist and run today. Copy it to
  `studies/<id>/inputs/` plus any meshes/includes (`extra_files`).
- **Parameters**: the exact MOOSE HIT paths to vary and their ranges. Confirm each
  path exists in the input (grep the `.i` or use `/moose-params`). A wrong path
  fails every case. For ranges, choose list vs `{start, stop, num}`.
- **QoIs**: which postprocessor CSV columns are the answer, and the reduce rule
  (`last` for steady, `max`/`min` for an extremum over time). The input must
  already output a CSV (`[Outputs] csv = true`).
- **Success framing**: what question the study answers. Keep any threshold as an
  observation the report computes — the report asserts only computed quantities.
- **Budget**: a core-hour ceiling (required), max concurrent jobs, and max
  walltime per case. Estimate with `analysis estimate` after writing and sanity-
  check against the `intern` allocation.
- **Cluster + resources**: default `bitterroot`; nodes/ntasks/partition
  (`short` 6h, `general` 7d, `hbm`). One node unless the mesh needs more.
- **Smoke reductions** (optional): cheap `smoke.overrides` (coarse mesh, 1 step)
  so the local smoke solve is fast. Without them only `--check-input` runs.

## 3. Scaffold + write

```bash
analysis/analysis new <id> --kind <kind>
```

Copy the baseline input into `studies/<id>/inputs/`. Then write `study.yaml`
from the grilled facts (schema in `analysis/README.md`). Keep `Outputs/file_base`
out of the spec — the toolkit sets it per case.

## 4. Validate + estimate

```bash
analysis/analysis validate <id>     # must pass (exit 0)
analysis/analysis estimate <id>     # worst-case core-hours vs ceiling
```

Fix every validation error. If the estimate exceeds the ceiling, grill the user:
shrink the grid, cut walltime, or raise the ceiling deliberately.

## 5. Approval summary — then stop

Present a plain-language summary via `AskUserQuestion`: id, kind, app, baseline,
the case count + parameter grid, QoIs, cluster, and the estimated vs ceiling
core-hours. Options: **Looks good** / **Change X** / **Cancel**.

On approval, stop. Tell the user: *"Spec approved. Run `/analysis-run <id>` to
fire."* Do NOT smoke, dispatch, or fire — that is `/analysis-run`'s job, and the
human review of this spec is the load-bearing gate.
