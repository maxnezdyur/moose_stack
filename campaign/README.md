# campaign

The contract and the tool for open-ended experimental work: one question, a stop condition, a
budget, and an append-only record of runs and findings. The plan is `../specs/campaigns-plan.md`.
The formats under `formats/` are the contract; change them before you change code.

```sh
~/projects/moose_stack/campaign/campaign <verb> [args]     # the launcher picks a python with PyYAML
```

## The unit

A campaign lives inside the project repository that holds its inputs. A run is replicable only
when every input has a git sha, and the vault is a build artifact.

```
<project-repo>/campaigns/<id>/
  campaign.md          the question, the stop condition, the budget, the queue of proposals
  LEDGER.md            append only: one entry per run, in launch order
  FINDINGS.md          append only: F1..Fn, each cites runs and measures
  handoff.md           State, Next, Do not repeat, Decisions, Gotchas, Map, Sessions
  method.md            optional: the validated pipeline and its regression gates
  scripts/             optional: the measure scripts that turn outputs into numbers
  gallery/             optional: figures, one gallery.md page, same rules as specs/gallery/
  runs/
    D014_<tag>/
      manifest.yaml    the replication record
      inputs/          frozen copies of the small input files, at their relative paths
      run.log
      outputs/         the kept outputs: the csv measure files, pulled or copied after the run
      qoi.json         the numbers, keyed by the names in ## Measures
      note.md          what it tested, what it showed, one paragraph
```

Big outputs stay where the run wrote them, on scratch or under the project's output directory.
The manifest names them. Commit `runs/` and the four markdown files, including the small kept files
under `runs/<run>/outputs/` that the measures read. Never commit a large output; keep the `kept`
globs to csv, json and logs.

## Formats

| file | format | template |
|---|---|---|
| `campaign.md` | [formats/campaign.md](formats/campaign.md) | [templates/campaign.md](templates/campaign.md) |
| `runs/<run>/manifest.yaml` | [formats/manifest.md](formats/manifest.md) | written by the tool only |
| `LEDGER.md` | [formats/ledger.md](formats/ledger.md) | [templates/LEDGER.md](templates/LEDGER.md) |
| `FINDINGS.md` | [formats/findings.md](formats/findings.md) | [templates/FINDINGS.md](templates/FINDINGS.md) |
| `handoff.md` | `.claude/skills/handoff/references/handoff-rules.md` | [templates/handoff.md](templates/handoff.md): the feature template with `campaign:` in place of `feature:` |

## Who writes where

| file | writer | discipline |
|---|---|---|
| `campaign.md` frontmatter | you, `campaign new` | rewrite; the budget only goes up by your hand |
| `campaign.md` `## Proposed` | the loop, you | a queue: lines are added, ticked, and consumed |
| `campaign.md` other sections | you, the loop | rewrite; a rewrite of `## Hypothesis` earns a Decisions line in `handoff.md` |
| `LEDGER.md` | `campaign run`, `reconcile`, `collect`, `verdict` | append only |
| `FINDINGS.md` | the loop, you | append only |
| `manifest.yaml` | the tool | the identity blocks are immutable after launch |
| `note.md`, `qoi.json` | `campaign collect`, the loop | rewrite until the verdict, then frozen |
| `handoff.md` | `/handoff`, the loop | the seven-section discipline |

## Commands

The launcher is `campaign/campaign`, the same shape as `factory/factory`. `<id>` may be omitted
when the current directory is inside `campaigns/<id>/`. The project root is the nearest parent
that holds a `campaigns/` directory, or `--root <path>`. Every verb that writes accepts
`--dry-run`, which prints every command, ssh, rsync and sbatch it would run.

| verb | does | writes |
|---|---|---|
| `new <id> [--root R]` | scaffold `campaigns/<id>/` from `templates/` (`handoff.md` included); refuse when it exists; link `.claude/skills/campaign`, `.claude/agents/campaign-loop.md` and `.claude/hooks/session-context.sh` into `<meta_repo>` when absent; append `campaigns/*/.factory-lease` to `.gitignore` when absent | the campaign directory, the three links, `.gitignore` |
| `validate <id>` | check the frontmatter, the four headings, every measure row, every proposal entry, id uniqueness, every manifest's identity, the ledger and the findings; exit 2 on an error | nothing |
| `status [<id>] [--json]` | one campaign, or every one under the root: status, spent over budget, runs by verdict, last finding, proposals ticked and pending. `--json`: the frontmatter, spent and budget, and per run `{id, tag, group, state, verdict, qoi}`, where `state` is `queued` (no `started`), `running` (no `finished`), `finished` (no `qoi`), `collected` (no `verdict`), `judged`, or `failed` | nothing |
| `next-id <id>` | print the next run id | nothing |
| `tick <id> <D> [--by loop\|<name>]` | turn `- [ ]` into `- [x]` for one entry. Refused unless `autonomy: within-budget` (and the ticked estimates then fit the remaining budget) or `--by` names a human. The loop uses it; a human may also tick in the file | `campaign.md` |
| `run <id> <D>` / `run <id> --ticked` | consume a ticked proposal: mint the run directory, freeze the inputs, write the manifest, launch locally or submit through sbatch, append the ledger start line; `--ticked` takes every ticked entry | the run directory, `campaign.md`, `LEDGER.md` |
| `reconcile [<id>\|--all]` | for every unfinished SLURM run: read squeue and sacct, update `slurm.state`, on completion set `finished`, `exit`, `core_hours`, pull the kept outputs, append the `done` line; resubmit a transient failure up to twice | the manifests, `LEDGER.md` |
| `collect <id> <D>` | run every measure in `## Measures`, write `qoi.json`, merge `qoi` into the manifest; idempotent; refused after the verdict | the run directory |
| `verdict <id> <D> <word> [--finding F<n>] [--by loop\|<name>]` | set `verdict` and `judged`, append the ledger verdict line; once per run | the manifest, `LEDGER.md` |
| `note <id> <D> "<text>"` | append `  - note: <text>` after the last line of that run's ledger entry, never at the end of the file | `LEDGER.md` |
| `close <id> F<n>` / `close <id> --abandon "<reason>"` | set `status: done` and `closed: {date, finding}` when `F<n>` exists and says `closes: yes`; or set `status: abandoned` and `closed.date`, and append the reason as a Decisions line in `handoff.md` | `campaign.md`, `handoff.md` |
| `replay <id> <D> [--restore] [--strict] [--cluster C]` | the replay contract in `formats/manifest.md`; the result is a new run with `replay_of` | a new run directory, `LEDGER.md` |
| `bringup --cluster <c> [<id>] [--app A]` | pin the project's code on the cluster (clone at the local HEAD when absent; refuse, exit 1, when present at another sha) and build the app binary into the bincache, once per (cluster, app, sha) | the cluster's scratch |
| `spent <id>` | the spent numbers as JSON: core-hours, runs, wall days, each with its budget | nothing |
| `doctor [<id>] [--offline]` | what is misconfigured: python, ssh reachability of the configured clusters, the binary, the three links, the `.gitignore` line, and whether `.claude/settings.json` registers `session-context.sh` for SessionStart (it prints the JSON to add; it never edits the file) | nothing |

Exit codes: 0 ok, 1 a human should look, 2 a refused write or a validation error, 3 a missing path
or a bad configuration, 4 a cluster did not answer: a failed ssh, rsync, sbatch, squeue or sacct
prints one line that starts `connection_down:` and nothing is written for that cluster.

The `how` cell of a measure row is one of two forms. A backtick span holds a command, run from the
campaign directory with `{outputs}` replaced by the run's `outputs.dir` and `{run}` by its id; it
prints one JSON object whose keys are measure names. `csv:<file>:<column>:<last|max|min>` reads a
column of a kept output file. Text after the form is a comment.

The per-machine settings live in `~/.config/moose-factory/config.toml`, the factory's file, under
a `[campaign]` table. Every key is optional.

| key | default | meaning |
|---|---|---|
| `clusters.<name>` | `teton` and `bitterroot` with their login hosts | a login host string, or a table: `host`, `partition` (`general`), `ntasks` (48), `walltime` (`02:00:00`), `account`, `wckey`, `module` (the container module; else `moose/scripts/versioner.py` names `moose-dev-openmpi/<hash>`), `build_partition` (`short`) |
| `scratch` | `/scratch/$USER/campaigns` | the remote root of every run and of the binary cache |
| `projects` | `/scratch/$USER/projects` | the remote parent of the pinned project checkouts `bringup` makes |
| `freeze_max_kb` | 1024 | an input at or under this size is copied into the run directory |
| `ssh_user` | none | the login name on the clusters, when it differs from the local one |

`$USER` in `scratch` and `projects` expands when the file is read, to `ssh_user` when set, else to
the local login name. The top-level `meta_repo` key, which the factory owns, says where the three
links of `campaign new` point; its default is `$HOME/projects/moose_stack`. SSH auth is
`~/.ssh/config`; the tool never handles credentials.

On a cluster, a run stages its frozen inputs at their project paths under
`<scratch>/<id>/<D>/`, links each hash-only input from the pinned checkout after checking its
sha256, and runs from `<scratch>/<id>/<D>/<cwd>`, which is its `outputs.dir`. The command's binary
is replaced by `moose-dev-exec <bincache binary>` in the rendered `run.sbatch`; the manifest keeps
the command as written.

## Invariants

1. Nothing runs outside `campaign run`. A bare `mpiexec` leaves no manifest and no ledger line.
2. A run id is minted once and never reused. A rejected proposal keeps its id in a Decisions line.
3. `campaign replay <run>` reproduces `qoi.json` from the manifest alone. This is the acceptance
   test of the tool and of every manifest.
4. The budget and the tick on a proposal are the only gates. Both are yours. The loop cannot
   raise a budget and cannot tick a line outside `autonomy: within-budget`.
5. Spent budget is computed from the manifests. It is never stored.
6. A line in an append-only file is never edited. A wrong line earns a second line that says so.
