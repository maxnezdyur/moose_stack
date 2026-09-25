# Campaigns: a plan for open-ended experimental work

Status: built 2026-09-25, uncommitted. Steps 1 to 6 below are done; the cluster path has run only
under `--dry-run` and a stub, never against Teton.

## The problem

The factory runs features: a blueprint, a build, a PR. The analysis toolkit runs studies: one
`.i`, one of three fixed kinds (sweep, convergence, optimization), fixed QoIs, fire and forget.
Neither fits work like PTR phase two. There the question is open, the next experiment depends
on the last result, and nobody can write the grid up front.

You already invented the answer by hand in `ptr-update/PTR/release_13x13`:

| you wrote | it does |
|---|---|
| `run.sh` | stamps a log, freezes `config.i`, appends one ledger line, refuses to clobber |
| `LOG.md`, `provenance/campaign_LOG.md` | append-only run ledger: stamp, mode/tag, git rev, log path, command |
| `provenance/campaign_RESULTS.md` | rows D0..D13 and Findings 1..16, each citing runs |
| `provenance/campaign_PLAN_*.md` | the question, the model it must match, the legs to run |
| `provenance/campaign_METHOD.md` | the validated pipeline and its regression gates |
| `ENVIRONMENT.md`, `DATA.md` | code shas, container hash, data pipeline |
| `scripts/teton/*` | bringup, build sbatch, run sbatch, sync |
| `d86_chain.sh`, `d87_watchdog.sh` | a multi-run leg with a stop rule |

That is a campaign. The plan below turns it into a tool and a loop so a session can run it
without you, and come back with findings.

## The unit: a campaign

A campaign is one question, a stop condition, a budget, and an append-only record of runs and
findings. It lives inside the project repo that holds the inputs, because a run is only
replicable when its inputs have a git sha.

```
<project-repo>/campaigns/<id>/
  campaign.md          the question, the stop condition, the budget, the autonomy level
  LEDGER.md            append-only, one row per run: id | tag | tested | verdict | evidence
  FINDINGS.md          append-only, F1..Fn, each citing run ids
  handoff.md           State, Next, Do not repeat, Decisions, Gotchas, Map, Sessions (same 7)
  runs/
    D001_<tag>/
      manifest.yaml    the replication record (below)
      inputs/          frozen copies of every file the run read (small) or their sha256 (big)
      run.log
      qoi.json         the numbers this run produced
      note.md          what it tested, what it showed, one paragraph
      figures/         optional
  method.md            optional: the current validated pipeline (your METHOD.md)
```

Big outputs stay where they were written, on scratch or under `opt_outputs/`. The manifest
points at them. `runs/` and the three markdown files are committed. `campaign.md` looks like:

```yaml
---
id: ptr-depth-sensitivity
project: ptr-update
question: How deep can SAFE resolve k(z) before the phase signal is flat?
stop: a finding states the depth at which sensitivity falls below 1e-3 rad per W/m·K,
      with one run on each side of it, or the budget is spent
budget: {core_hours: 400, wall_days: 7, max_runs: 40}
cluster: teton          # local | teton | bitterroot
autonomy: within-budget # propose-only | within-budget | manual
app: isopod
---
## Hypothesis
...
## Constraints
what a run may not change; the frozen model knobs (your "paper model this must match" table)
## Proposed
- [ ] D014 two-layer, k_Ni x 0.5 ... (est 6 core-h) because F9 says ...
```

A run is one command with frozen inputs. There is no kind field. A sweep is N runs that share
a `group`. A chain with a stop rule is a leg the loop drives, not a shell script.

## The replication record

`manifest.yaml` is the contract. A run is replicable when `campaign replay D014` reproduces it
from the manifest alone, on either host. That replay is the acceptance test of the tool.

```yaml
run: D014
group: depth-sweep
tag: two-layer-kni-half
started: 2026-09-25T14:03:10Z
finished: ...
exit: 0
host: teton1.hpc.inl.gov          # or the laptop hostname
cluster: teton                    # or local
slurm: {job: 8812234, partition: general, ntasks: 48, walltime: "02:00:00", core_hours: 5.7}
code:
  ptr-update: {sha: eb8109b, dirty: false}
  moose: {sha: d96c576}
  isopod: {sha: aa4173f}
  container: moose-dev-openmpi/2026.05.08       # versioner hash on HPC
  binary: {path: ..., built: 2026-08-02, sha256: ...}
  conda_env: moose                              # local only
command: mpiexec -np 3 isopod-opt -w -i main.i mode=g0 tag=... k_hi=600 ...
cwd: inverse_simulation
env: {OMP_NUM_THREADS: 1, VECLIB_MAXIMUM_THREADS: 1}
inputs:                                          # every file the run read
  - {path: inverse_simulation/main.i, sha256: ..., frozen: inputs/main.i}
  - {path: real_data/snapslrb_1Hz_-1.6.csv, sha256: ...}   # big: hash only
  - {path: config.i, sha256: ..., frozen: inputs/config.i}
outputs: {dir: /scratch/nezdmn/campaigns/ptr-depth-sensitivity/D014, kept: [*.csv, *.json]}
hypothesis: "halving k_Ni moves the phase minimum by more than 0.05 rad at 1 Hz"
verdict: supported | refuted | inconclusive | failed
qoi: {phase_min_shift_rad: 0.071, J: 2.2342}
```

The `code` block is what `ENVIRONMENT.md` records by hand today. The `inputs` block is what
`run.sh` froze as one `config.i`, made complete.

## The loop

One agent, `campaign-loop`, built on the pattern of `moose-feature-loop`: it owns a ledger of
criteria, dispatches children, never edits or runs anything itself. Its ledger is the campaign's
stop condition, not a build.

```
propose  read campaign.md + LEDGER.md + FINDINGS.md + handoff.md
         write N candidate runs under ## Proposed, each with: what it tests, why (cite F#),
         the exact command, the estimated cost
         autonomy=propose-only  -> stop, card says needs-you
         autonomy=within-budget -> tick them itself when the sum fits the remaining budget
run      for each ticked proposal: campaign run D0nn   (freeze, manifest, dispatch)
         local: run it; teton: sbatch through the analysis remote plumbing, record the job id
wait     campaign reconcile   (squeue/sacct, like analysis reconcile; connection_down parks)
collect  pull run.log, the kept outputs, extract qoi.json, append the LEDGER row with a verdict
         computed against the run's stated hypothesis
learn    write finding(s) to FINDINGS.md, rewrite handoff State and Next, decide:
         stop condition met      -> report
         budget spent            -> report, card says needs-you
         a finding refutes the campaign hypothesis -> report, card says needs-you
         else                    -> propose
report   a short digest to the card and to you: the findings since you last looked,
         the figures in specs/gallery/, the remaining budget, the proposed next round
```

Every run is a child of `campaign run`, never a bare `mpiexec`. That is the rule `run.sh`
already enforces: "nothing runs outside this path".

Three autonomy levels, set per campaign:

| level | the loop may |
|---|---|
| `propose-only` | write proposals. You tick boxes. Default. |
| `within-budget` | tick and run its own proposals until the budget or the stop condition. |
| `manual` | nothing. You call `campaign run` by hand; the loop only collects and learns. |

The budget is a gate you own, the same way `ceiling_core_hours` is today. The loop can never
raise it.

## Teton

Reuse `analysis/tool/{remote,dispatch,reconcile,collect}.py` as a library. They already do ssh
through `~/.ssh/config`, rsync, a per-(cluster, app, sha) binary cache under
`/scratch/$USER/analysis/.bincache/`, sbatch templates, squeue/sacct sync, transient-failure
resubmit, and `connection_down` parking. `teton` is already in `config.py`. What changes: the
dispatcher takes a manifest, not a study spec, and a run is one job, not an array.

`scripts/teton/bringup-teton.sh` becomes `campaign bringup --cluster teton`: pin the stack once
per (cluster, project sha), build once, cache. Do not clone the project repo per run; rsync the
frozen `inputs/` of one run into `/scratch/$USER/campaigns/<id>/<run>/`.

## The board

One board, not two. A campaign is a second kind of card next to features, in the same
`Home.md` and the same six kanban columns, because the factory's job is one page grouped by what
you must do, and ticking a proposal belongs in that list next to a PR waiting on you.

What differs is the card. `ext_campaigns.py` is a read-only adapter over
`campaigns/*/campaign.md`, `LEDGER.md` and `FINDINGS.md`, copied from the studies adapter it
replaces. It writes `Campaigns/<id>.md` beside `Features/`, with the same two prose regions, and
a `Campaigns.base` once, whose columns are question, spent over budget, runs by verdict, last
finding. The card shows the question, the budget line, the last finding heading and the pending
proposals. `Home.md` gets a `## Campaigns` section in place of `## Studies`. The factory
discovers campaign roots from a new `campaign_roots` list in
`~/.config/moose-factory/config.toml`.

| posture | when |
|---|---|
| needs-you | proposals await a tick; budget spent; a finding refuted the hypothesis |
| running | a run is queued or executing, local or SLURM |
| waiting | `connection_down`, or the loop sleeps on a long job |
| ready | ticked proposals and no session holds the lease |
| done | the stop condition is met |

`factory start <campaign>` reuses the lease and the `claude --bg` dispatch unchanged. The
handoff, the gallery symlink and the timeline all work as they do for a feature, because the
campaign directory carries the same `handoff.md` and a `gallery/`.

## Build order

1. **Contract first, no code.** Done 2026-09-25: `campaign/README.md`, `campaign/formats/`
   (campaign, manifest, ledger, findings) and `campaign/templates/`. Those files now override
   the sketches above where they differ.
2. **`campaign` CLI, local only.** Done. Same launcher pattern as `analysis`. Verbs: `new`, `run`,
   `replay`, `collect`, `ledger`, `status`, `validate`. `run` replaces `run.sh` and refuses
   to clobber. Acceptance: `replay` of a cheap run reproduces its `qoi.json`. Two days.
3. **Teton.** Done, untested against a real cluster. `bringup`, `run --cluster teton`, `reconcile`. Lift the analysis remote modules
   into a shared package both tools import. Acceptance: one run round-trips through SLURM
   with a complete manifest and a ledger row. Two days.
4. **The loop.** Done. `campaign-loop` agent plus `/campaign-propose`, `/campaign-run`,
   `/campaign-learn` skills, or one `/campaign` skill with those verbs. Start with
   `propose-only`; add `within-budget` after the first campaign runs end to end. Two days.
5. **The board.** Done. `ext_campaigns.py`, the `campaign_roots` key, `factory start <campaign>`,
   the doctor rows. One day.
6. **Retire the analysis toolkit.** Done. Same change as step 3, finished: once the remote
   modules live in the campaign package, delete the study concept. Details below. One day.

First campaign: SAFE thermal depth sensitivity, the question the 2026-09-08 meeting left open.
It has a real stop condition and an October meeting to feed.

## Retiring the analysis toolkit

The only study on disk is `example-k-sweep`. Nothing real is lost. The toolkit splits cleanly:

| keep, moved into `campaign/tool/` | delete |
|---|---|
| `remote.py` (ssh, rsync, probe) | `spec.py`, `model.py` (Spec, Card, the lanes) |
| `dispatch.py`: `resolve_remote_sha`, `resolve_module_hash`, `ensure_remote_binary`, the bincache | `dispatch.py`: the array sbatch, the case estimate |
| `reconcile.py`: `_classify`, `sync_card` style squeue/sacct sync, resubmit-on-transient | `reconcile.py`: `_advance_lane`, `reconcile_all` |
| `collect.py`: `extract_qoi`, `fetch_fields` | `cases.py`, `board.py`, `vault.py`, `report.py`, `cli.py` |
| `localrun.py`: `ensure_local_binary` | `analysis/studies/`, `analysis/README.md`, the launcher |
| `config.py`: the cluster table, `DEFAULT_NTASKS`, the container rules | `pyproject.toml` |
| `slurm/build.sbatch`, `slurm/case.sbatch` as templates | |

Outside `analysis/`:

- `.claude/skills/analysis-blueprint`, `analysis-run`, `analysis-status`: delete. The
  campaign skills replace them.
- `factory/tool/ext_studies.py` and the `studies` verb: delete. `config.py` drops
  `studies_dir` and `analysis_launcher`; `model.py`, `render.py`, `ext_board_html.py` and
  `README.md` drop their study rows. `ext_campaigns.py` takes the same seat.
- `~/projects/moose-factory/Studies/`: delete with the vault's `## Studies` section. The
  `example-k-sweep.md` note goes with it.
- `~/.config/moose-factory/config.toml`: drop `analysis_studies` if set.
- The moose-factory `CLAUDE.md` rules about `$ANALYSIS_VAULT` and `analysis reconcile` go.

Do it in this order so nothing is ever broken: (a) copy the keep column into the campaign
package and check `campaign validate` on the example; (b) delete `analysis/` and the three
skills in one commit; (c) delete the factory study code and the vault notes in one commit, then
`factory board` and check `git diff --stat` in the vault shows only the removal.

## Decisions taken in this draft

- Campaigns live in the project repo, not in the factory vault and not in `moose_stack`.
  Replicability needs the inputs' sha; the vault is a build artifact.
- No run kinds. One run is one command with frozen inputs. Groups replace sweeps.
- The analysis toolkit is retired, not wrapped. Its HPC plumbing moves; its study schema,
  lanes, board and skills are deleted.
- The four append-only files are the memory: `LEDGER.md`, `FINDINGS.md`, and the
  `Do not repeat` and `Decisions` sections of `handoff.md`. Same discipline as `/handoff`.
- Budget and the tick on a proposal are the only gates. Both are yours. The loop cannot
  grant either.
- Big outputs are never copied into the campaign directory. The manifest names them and the
  campaign notes the purge risk, as the analysis README does for `/scratch`.
