# Analysis system

Fire-and-forget MOOSE studies with a durable Kanban board. You describe a
study, approve it, and fire. The system smokes it locally, dispatches the full
study to HPC, and tracks every card across sessions. When you reopen Claude a
week later, it reconciles the board against SLURM and finishes the work.

The AI (skills `/analysis-blueprint` and `/analysis-run`) owns judgment. This
toolkit owns everything that must be reliable. SSH auth is delegated to your
`~/.ssh/config` — the toolkit never handles credentials.

## Run the CLI

```bash
analysis/analysis <command> [args]      # launcher picks a python with PyYAML
```

The launcher uses `$ANALYSIS_PYTHON`, then a `python3` that has PyYAML, then the
conda `moose` env. Inside the HPC container, `python3` already has the deps.

## Vault mode (central hub)

Study *data* can live in a standalone Obsidian vault instead of this repo. Set:

```bash
export ANALYSIS_VAULT=~/projects/analysis-vault
```

With it set, `studies/` and the board resolve into the vault, and `analysis board`
regenerates the vault's `Home.md` (a map of content) plus a per-study note
(`<id>.md`, with YAML frontmatter and `[[wikilinks]]`) — one-way from each
`card.yaml`. The frontmatter feeds Obsidian's native **Bases** core plugin (no
Dataview needed); a starter `Studies.base` in the vault gives a live table of
all studies. The toolkit *code* stays here; only data moves. Unset, studies live
in `moose_stack/analysis/studies` as before. Add the export to your shell profile
to make it the default.

## Lifecycle

```
draft → approved → smoking(local) → ready → dispatched → running
      → collecting → analyzing → reported → done
off-happy-path: attention · budget_exceeded · connection_down
```

1. `analysis new <id>` — scaffold `studies/<id>/study.yaml` + `inputs/`.
2. Edit the spec; put the baseline `.i` at `studies/<id>/inputs/`.
3. `analysis validate <id>` — hard-check the spec.
4. `analysis run <id>` — smoke locally, budget-gate, dispatch to HPC.
5. `analysis reconcile --all` — re-entry: sync SLURM, retry, collect, report.
6. Open `studies/<id>/results/report.html`.

## Commands

| Command | Purpose |
|---|---|
| `new <id> [--kind K]` | scaffold a study dir + skeleton spec |
| `validate <id>` | validate `study.yaml` (exit 2 on error) |
| `init <id>` | mint `card.yaml` from the spec |
| `smoke <id>` | local build-if-missing + smoke; → `ready` on pass |
| `estimate <id>` | worst-case core-hour estimate + budget verdict |
| `run <id> [--dry-run] [--cluster C]` | fire: smoke → gate → dispatch |
| `reconcile [<id>|--all] [--dry-run]` | re-entry: sync → advance → collect → report |
| `collect <id>` | pull CSV/logs + extract QoIs (idempotent) |
| `report <id>` | (re)render `report.html` |
| `fetch-fields <id> -c K` | on-demand pull of large field output |
| `status [<id>]` | print a card (or the whole board) |
| `board` | regenerate `BOARD.md` + `board.html` |

`--dry-run` prints every ssh/rsync/sbatch instead of running it (offline-safe).

## study.yaml schema

```yaml
id: my-study                 # required, matches the dir name
title: "..."
kind: sweep                  # sweep | convergence | optimization
app: combined                # moose | combined | blackbear | isopod
cluster: bitterroot          # default; override per run with --cluster
account: intern              # SLURM accounting key
# repo_sha: HEAD             # pin a sha; default = scratch checkout HEAD

baseline:
  input: inputs/base.i       # required, relative to the study dir
  extra_files: [inputs/mesh.e]

# one block matching `kind`:
sweep:
  method: grid               # grid (cartesian) | zip (parallel lists)
  params:
    Materials/thermal/k: [1, 2, 5, 10]          # explicit list
    BCs/right/value: {start: 300, stop: 900, num: 5}   # range → linspace
convergence:
  param: Mesh/uniform_refine
  levels: [0, 1, 2, 3, 4]
  reference: finest          # finest | analytic  (for order fit)
optimization:
  max_iters: 100             # hard bound; the input drives its own optimizer

qoi:                         # required for sweep/convergence
  csv: base_out.csv          # informational; per-case CSV is <file_base>.csv
  columns: [peak_T, avg_T]   # CSV columns to extract
  reduce: last               # last | max | min

smoke:                       # optional cheap local solve (else check-input only)
  overrides: {Mesh/gen/nx: 4, Executioner/num_steps: 1}

budget:                      # required — fire-and-forget must be bounded
  ceiling_core_hours: 200    # refuse-and-park if the worst-case estimate exceeds
  max_concurrent_jobs: 16    # SLURM array throttle (%N)
  max_walltime_per_case: "02:00:00"

resources:
  nodes: 1
  ntasks: 48
  partition: general         # short (6h) | general (7d) | hbm
```

Parameters are MOOSE HIT paths applied as command-line overrides
(`Materials/thermal/k=2.0`) — the input file is never edited.

## How it runs on HPC

- Studies execute under `/scratch/$USER/analysis/<id>/`, isolated from your dev
  checkout. Cases run as a throttled SLURM **array** (`--array=0-N%conc`).
- The binary is built **once per (cluster, app, sha)** into
  `/scratch/$USER/analysis/.bincache/`; cases depend on the build via `afterok`.
- Provenance (app, git sha, module hash, cluster, core-hours) is recorded on the
  card. `/scratch` is site-shared and may be purged — the card lets you re-run.

## Safety rails

- **Budget**: worst-case estimate (`ntasks × walltime × cases`) gates before
  submission; a mid-flight overrun cancels remaining jobs and parks the study.
- **Failure**: transient (timeout/node/preempt) auto-resubmits up to a cap;
  systematic (diverged/NaN/bad input) parks with a diagnosis. Inputs are never
  auto-edited.
- **Connectivity**: a failed probe parks the study in `connection_down`; it
  recovers on the next reconcile once the cluster is reachable.

## What is tracked in git

`study.yaml` and `card.yaml` (spec + durable state). Bulk results
(`studies/*/results/`, `board.html`) are gitignored — data, not code.
