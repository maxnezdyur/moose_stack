---
name: analysis-blueprint
description: Turns a MOOSE analysis idea (parameter sweep, convergence study, optimization run) into a validated, user-approved analysis/studies/<id>/study.yaml for the fire-and-forget analysis system. Grills the user until every field is grounded, scaffolds the study directory, validates the spec, and stops at approval. Invoke as /analysis-blueprint <study idea>.
disable-model-invocation: true
argument-hint: "<study idea>"
---

# /analysis-blueprint

Goal: a `study.yaml` that `/analysis-run` can fire unattended. The spec is the one load-bearing
review in a fire-and-forget system; an underspecified study burns HPC time with nobody watching.
This skill ends at an approved spec; `/analysis-run` is the only thing that fires.

The toolkit is `${CLAUDE_PROJECT_DIR}/analysis/analysis` (run from the meta-repo). The schema and
the per-field judgment notes live in `analysis/README.md` (the `study.yaml schema` section); read
that section before grilling. A study runs an existing `.i` with command-line overrides; this skill
edits no C++ and no input file.

## Grill

Fill every `study.yaml` field from the user's answers, not from assumptions. Ask with
`AskUserQuestion`, batching independent questions into one call (up to 4). Ground each field the
way the README comments say: the baseline input exists and runs today; every parameter path
exists in that input (grep it, or `Skill(moose-params)` for the object's registered names); the
QoI columns are postprocessors the input already writes to CSV; the budget ceiling is a number
the user chose.

## Scaffold, write, validate

```
${CLAUDE_PROJECT_DIR}/analysis/analysis new <id> --kind <sweep|convergence|optimization>
${CLAUDE_PROJECT_DIR}/analysis/analysis validate <id>
${CLAUDE_PROJECT_DIR}/analysis/analysis estimate <id>
```

Copy the baseline `.i` and every file it reads into `analysis/studies/<id>/inputs/`, then write
`study.yaml` from the grilled facts. `validate` exits 0 on a good spec and 2 on errors; the exit
code is the gate, so fix every reported error and rerun. When the worst-case estimate exceeds the
ceiling, go back to the user: shrink the grid, cut the walltime, or raise the ceiling on purpose.

## Approve and stop

Present one `AskUserQuestion` summary: id, kind, app, baseline input, case count and parameter
grid, QoIs and reduce rule, cluster and resources, estimated versus ceiling core-hours. Options:
"Looks good", "Change ...", "Cancel". On approval, reply "Spec approved. Run `/analysis-run <id>`
to fire." and end the turn.
