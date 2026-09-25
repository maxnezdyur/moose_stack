# campaign.md format

One file, `<project-repo>/campaigns/<id>/campaign.md`. It holds the question, the stop condition,
the budget, the frozen constraints, the measures, and the queue of proposed runs. The loop reads
it whole at the start of every pass. You edit it by hand. The tool edits only `## Proposed`.

## Frontmatter

```yaml
---
id: ptr-depth-sensitivity        # kebab-case; equals the directory name
project: ptr-update              # basename of the repository root
title: SAFE thermal depth sensitivity
question: How deep can SAFE resolve k(z) before the phase signal goes flat?
stop: >
  A finding states the depth at which sensitivity falls below 1e-3 rad per W/m·K,
  with one run on each side of it.
budget:
  core_hours: 400                # sum of every run's core-hours may not exceed this
  wall_days: 7                   # counted from `created`
  max_runs: 40                   # count of runs/ directories
cluster: teton                   # local | teton | bitterroot; a proposal may override
app: isopod                      # moose | combined | blackbear | isopod
autonomy: propose-only           # propose-only | within-budget | manual
status: active                   # draft | active | done | abandoned
created: 2026-09-25
updated: 2026-09-25
closed:                          # only when status is done or abandoned
  date: 2026-10-03
  finding: F12                   # the finding that met the stop condition
---
```

Every key above `status` is required. `question` is one sentence. `stop` is a condition the loop
can check against `FINDINGS.md`; a stop that names no measure and no number cannot be met.

The budget is yours. Raise it by hand and append a Decisions line in `handoff.md`. The loop never
edits the budget. Spent budget is computed from the manifests and printed by `campaign status`.

`status: done` is legal only with a `closed.finding` that exists in `FINDINGS.md` and says
`closes: yes`. `status: abandoned` needs a `closed.date` and a Decisions line with the reason.

## Autonomy

| level | the loop may |
|---|---|
| `propose-only` | write lines under `## Proposed`. You tick them. Default. |
| `within-budget` | tick its own lines when their estimates fit the remaining budget, then run them |
| `manual` | nothing. You run `campaign run` by hand; the loop collects and learns only |

## Sections, in this order, with these exact `##` headings

| heading | discipline | content |
|---|---|---|
| `## Hypothesis` | rewrite | What you expect to find and why. One or two paragraphs. A rewrite earns a Decisions line in `handoff.md` that cites the finding that forced it. |
| `## Constraints` | rewrite | A table of the knobs a run may not change: `\| knob \| value \| why \|`. This is the frozen model. Then `Out of scope:` bullets. The loop refuses to propose a run that changes a listed knob. |
| `## Measures` | append only | A table `\| name \| unit \| how \| added \|`. `name` is the key in every `qoi.json`. `how` is a backtick command (run from the campaign directory, `{outputs}` and `{run}` substituted, prints one JSON object keyed by measure name) or `csv:<file>:<column>:<last\|max\|min>`; text after it is a comment. Add a row; never delete or rename one. |
| `## Proposed` | queue | One entry per proposed run, format below. |

## The proposed entry

```
- [ ] D015 two-layer-kni-half | depth-sweep | 6 core-h | tests: halving k_Ni shifts the 1 Hz phase minimum by more than 0.05 rad | because: F9, D011
  - cwd: inverse_simulation
  - cmd: mpiexec -np 3 ../isopod-opt -w -i main.i k_ni=45 tag=two-layer-kni-half
  - in: real_data/snapslrb_1Hz_-1.6.csv
  - cluster: local
```

The first line has six fields, separated by ` | `:

| field | rule |
|---|---|
| `D015` | the run id: `D` plus three digits, minted as one more than the highest id in `## Proposed` and `runs/` |
| `two-layer-kni-half` | the tag: `[a-z0-9._-]+`, unique in the campaign |
| `depth-sweep` | the group, or `-`. Runs in one group share one question and one figure. |
| `6 core-h` | the estimate: `ntasks × walltime` for SLURM, `np × expected hours` locally |
| `tests: ...` | the hypothesis: one checkable sentence that names a measure and a number. It becomes `hypothesis` in the manifest and the verdict is judged against it. |
| `because: ...` | the findings and runs that motivate it. At least one `F<n>` or `D<nnn>`; the first runs of a campaign, which have neither, cite `campaign.md`. |

The sub-bullets:

| key | required | rule |
|---|---|---|
| `cwd` | yes | relative to the project root; the directory the command runs from |
| `cmd` | yes | one line; the exact command; no shell variables (no `$`). The tool splits it with shell quoting rules and runs it without a shell. |
| `in` | no | one per line; relative to the project root; an input the command reads that the tool cannot find by parsing `-i` and `!include` |
| `cluster` | no | overrides the frontmatter for this run |
| `env` | no | `KEY=value`, one per line |
| `ntasks` | no | SLURM only. The task count. Default: the `-np`/`-n` of an `mpiexec` in `cmd`, else the cluster's `ntasks` |
| `walltime` | no | SLURM only. `HH:MM:SS` or `D-HH:MM:SS`. Default: the cluster's `walltime` |
| `partition` | no | SLURM only. Default: the cluster's `partition` |

## The queue

1. The loop, or you, appends an entry with `- [ ]`.
2. A tick, `- [x]`, approves it. You tick by hand. Under `within-budget` the loop ticks its own
   entries when the sum of their estimates fits the remaining budget.
3. `campaign run D015` consumes a ticked entry: it creates `runs/D015_two-layer-kni-half/`,
   copies the entry into the manifest's `proposal` block, and deletes the entry from the queue.
4. To reject an entry, delete it and append a Decisions line to `handoff.md` that names the id
   and the reason. The id is never reused.

`campaign run` refuses an unticked entry, an entry whose command changes a knob in
`## Constraints`, an entry whose estimate would exceed the remaining budget, an input that is
absent, and a run directory that exists. A command changes a knob when it holds a `<knob>=` token
(or `<path>/<knob>=`) whose `<knob>` is a first-column cell of the constraints table, backticks
stripped. The remaining budget subtracts, for every unfinished run, the larger of its estimate and
what it has used so far. `campaign tick D015` ticks one entry for the loop under
`within-budget`, and only when the ticked estimates fit the remaining budget.
