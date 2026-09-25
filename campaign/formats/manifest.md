# manifest.yaml format

One file per run, `runs/D014_<tag>/manifest.yaml`. It is the replication record. The tool writes
it. You never edit it. `campaign replay D014` must reproduce the run's `qoi.json` from this file
alone, on either host.

## The file

```yaml
run: D014
campaign: ptr-depth-sensitivity
tag: two-layer-kni-half
group: depth-sweep                     # or null
replay_of: null                        # D0nn when this run is a replay
proposal:                              # the ## Proposed entry, verbatim
  tests: halving k_Ni shifts the 1 Hz phase minimum by more than 0.05 rad
  because: [F9, D011]
  estimate_core_hours: 6
hypothesis: halving k_Ni shifts the 1 Hz phase minimum by more than 0.05 rad

started: 2026-09-25T14:03:10Z
finished: 2026-09-25T16:11:22Z         # null until done
exit: 0                                # null until done
host: teton1.hpc.inl.gov
cluster: teton                         # local | teton | bitterroot
slurm:                                 # null for a local run
  job: 8812234
  partition: general
  nodes: 1
  ntasks: 48
  walltime: "02:00:00"
  state: COMPLETED                     # last observed by reconcile
  core_hours: 5.7                      # from sacct, every attempt included
  attempts: []                         # only after a resubmit: [{job, state, core_hours}] per earlier attempt
local:                                 # null for a SLURM run
  np: 3
  core_hours: 0.4                      # np × elapsed

code:
  ptr-update: {sha: eb8109b, branch: main, dirty: false}
  moose: {sha: d96c576dc4d1c9a9dabaf01835deefa873a87d7c}
  isopod: {sha: aa4173fafd0155c2006f81f48d5f34c8783db745}
  container: moose-dev-openmpi/2026.05.08    # null locally
  binary: {path: /scratch/nezdmn/campaigns/.bincache/teton/isopod/aa4173f/isopod-opt, built: 2026-08-02T09:14:00Z, sha256: 3f1a...}
  python: {env: moose, version: 3.14.4}      # null when no python ran

command: mpiexec -np 3 ../isopod-opt -w -i main.i k_ni=45 tag=two-layer-kni-half
cwd: inverse_simulation                # relative to the project root
env:
  OMP_NUM_THREADS: "1"
  VECLIB_MAXIMUM_THREADS: "1"

inputs:                                # every file the command reads
  - {path: inverse_simulation/main.i, bytes: 4120, sha256: 9c2e..., frozen: inputs/inverse_simulation/main.i}
  - {path: inverse_simulation/config.i, bytes: 2210, sha256: 71b0..., frozen: inputs/inverse_simulation/config.i}
  - {path: real_data/snapslrb_1Hz_-1.6.csv, bytes: 48113022, sha256: d4a9..., frozen: null}
identity: "sha256:5e0c..."             # digest of the immutable blocks, written at launch

outputs:
  dir: /scratch/nezdmn/campaigns/ptr-depth-sensitivity/D014/inverse_simulation  # on `host`: where the command ran
  purge_risk: true                     # true under /scratch
  kept: ["phase_1hz.csv", "run.log"]  # written by collect: the files kept in runs/<run>/outputs/

qoi:                                   # written by collect; keys are ## Measures names
  phase_min_shift_rad: 0.071
  J: 2.2342

verdict: supported                     # supported | refuted | inconclusive | failed | null
judged: {by: loop, at: 2026-09-25T16:40:02Z, finding: F10}
```

## Who writes which block, and when

| block | writer | when |
|---|---|---|
| `run` .. `hypothesis` | `campaign run` | at mint, from the ticked proposal |
| `started`, `host`, `cluster`, `code`, `command`, `cwd`, `env`, `inputs`, `identity`, `outputs.dir` | `campaign run` | before the process starts |
| `slurm.job` .. `slurm.walltime`, `local.np` | `campaign run` | at submit or launch |
| `slurm.state`, `slurm.core_hours`, `finished`, `exit` | `campaign reconcile` (SLURM), `campaign run` (local) | on completion |
| `outputs.kept`, `qoi` | `campaign collect` | after completion |
| `slurm.attempts` | `campaign reconcile` | on a resubmit after a transient failure |
| `verdict`, `judged` | `campaign verdict` | when the loop or you judge the run |

## Immutable after launch

`command`, `cwd`, `env`, `code`, `inputs`, `hypothesis`. A wrong value in one of them makes the
run `failed`. Mint a new run; never patch the manifest.

`identity` is `sha256:` and the hex digest of those six blocks, serialized as sorted, compact JSON.
`validate` reports a manifest whose digest no longer matches, and `replay` and `verdict` refuse it.
A manifest written before the field existed has no `identity` and is not checked.

## Inputs and the freeze rule

The inputs are the `-i` file, every file it reaches through `!include` (parsed transitively), and
every `in:` line on the proposal. `campaign run` refuses to launch when a listed input is absent.

A file at or under `freeze_max_kb` (default 1024) is copied to `inputs/<path>` inside the run
directory. A larger file is recorded by size and sha256 only, with `frozen: null`. A file the run
read but the manifest does not list makes the run non-replicable. Add an `in:` line to the next
proposal and a Gotchas line to `handoff.md`.

## Verdicts

| verdict | meaning |
|---|---|
| `supported` | the measure named in `hypothesis` met the stated number |
| `refuted` | it did not |
| `inconclusive` | the run completed but the measure does not decide the hypothesis |
| `failed` | non-zero exit, a lost job, or an immutable block found wrong |

A verdict cites the finding it feeds through `judged.finding`, or `null` when no finding was
written yet.

## The replay contract

`campaign replay D014` does this, in order:

1. Read the manifest. Refuse when `verdict` is `failed`.
2. For every input, compute the working-tree sha256 and compare. On a mismatch, refuse and name
   the file. With `--restore`, copy the frozen file over the working-tree file first; a hash-only
   file cannot be restored and stays a refusal.
3. Compare every `code` sha with the working tree. Warn on a mismatch; refuse with `--strict`.
4. Mint a new run `D0nn` with `replay_of: D014`, the same `command`, `cwd`, `env` and
   `hypothesis`, and the working tree's own `code` block.
5. Launch it like any run. `collect` compares its `qoi` with the original within a tolerance per
   measure and writes the result in the new run's `note.md`.
