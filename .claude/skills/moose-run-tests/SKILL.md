---
name: moose-run-tests
description: MOOSE ./run_tests cheat sheet — real CLI flags, common recipes, status taxonomy, skip-caveat decoder, manual gold regeneration workflow, capability gating, CIVET basics, debugging recipes, env vars, and a list of commonly assumed flags that don't actually exist. Auto-loads when running, debugging, or filtering MOOSE tests; also invocable as /moose-run-tests.
user-invocable: true
---

# MOOSE `./run_tests` Cheat Sheet

Reference for running, filtering, debugging, and regenerating golds for MOOSE regression tests in `moose`, `moose/modules/<m>`, `blackbear`, and `isopod`.

For *authoring* tests, see **moose-test-standards** (regression) and **moose-unit-test-standards** (gtest).

## The script and where to run it

`run_tests` is an 8-13 line Python shim, **not** a shell wrapper. It does not source conda — activate your env yourself.

```bash
conda activate moose
cd <app>/test          # or moose/modules/<m>/test, blackbear, isopod
./run_tests -j 8
```

The harness walks upward from CWD looking for a `testroot` file. Discovery is `os.walk` from CWD, looking for files literally named `tests` (override with `-i <name>`). Skips `.git`, `contrib/`, `.svn/`, and any directory containing `.moose_ignore`.

`testroot` keys: `app_name`, `run_tests_args` (appended to every invocation), `extra_pythonpath`, `known_capabilities`, `allow_warnings`, `allow_unused`, `allow_override`.

## Real CLI flags (grouped)

### Selection
| Flag | Effect |
|---|---|
| `--re=<regex>` | Run only tests matching this regex against `<spec_dir>/<test_name>` |
| `--failed-tests` | Re-run only tests that failed in the previous run (reads `.previous_test_results.json`) |
| `--show-last-run` | Display previous results without re-executing |
| `-i <name>` | Spec filename to look for (default: `tests`) |
| `--spec-file <path>` | Path to a single tests file or a single dir to search |
| `-C <dir>` / `--test-root <dir>` | Search for spec files in this location |
| `-g <name>` / `--group <name>` | Run only tests with `group = <name>` |
| `--not-group <name>` | Run only tests NOT in group |

### Parallelism
| Flag | Effect |
|---|---|
| `-j N` / `--jobs N` | Total parallel slots. A 2 MPI × 2 thread test consumes 4 slots. |
| `-l N` / `--load-average N` | Pause if load > N |
| `-p N` / `--parallel N` | MPI ranks per test |
| `--n-threads N` | Threads per test |
| `--min-parallel N` / `--min-threads N` | Skip tests that can't run with at least N |

### Build method (binary suffix)
| Flag | Binary |
|---|---|
| `--opt` (default) | `<app>-opt` |
| `--dbg` | `<app>-dbg` (asserts fire) |
| `--devel` | `<app>-devel` |
| `--oprof` | `<app>-oprof` |

Or set `METHOD=dbg` env var. **There is no `--method` flag.**

### Modes
| Flag | Effect |
|---|---|
| `--check-input` | Syntax-only check; don't solve |
| `--no-check-input` | Skip check_input variants |
| `--recover` | Run each test as part1 (`--test-checkpoint-half-transient`) + part2 (`--recover`) |
| `--restep` | Run with `--test-restep` (middle timestep rejected, redone) |
| `--valgrind` | Run with valgrind (NORMAL mode) |
| `--valgrind-heavy` | HEAVY valgrind mode |
| `--heavy` | Run only `heavy = true` tests (default omits them) |
| `--all-tests` | Run heavy + non-heavy |
| `-s` / `--scale` | Run tests with `scale_refine` set |
| `--dry-run` | Print commands without running |

`--check-input`, `--recover`, `--restep` are **mutually exclusive**.

### Output
| Flag | Effect |
|---|---|
| `-v` / `--verbose` | Show output of every test |
| `-q` / `--quiet` | Show only result |
| `-c` / `--no-color` | Plain output |
| `-t` / `--timing` | Show timing for passing tests |
| `--longest-jobs N` | After completion, list N slowest tests + heaviest jobs by memory |
| `--no-trimmed-output` | Don't trim long outputs |
| `--no-trimmed-output-on-error` | Don't trim on failure |
| `--no-report` | Don't list skipped tests |
| `--term-cols N` | Terminal width (or env `MOOSE_TERM_COLS`) |
| `--term-format <chars>` | Output field codes; default `njcstm` (or env `MOOSE_TERM_FORMAT`) |

Field codes: `n`/`N` name, `j` justification dots, `c` caveats, `s` status, `p` padded pre-status, `t` time, `m` memory.

### Files
| Flag | Effect |
|---|---|
| `-o <dir>` / `--output-dir <dir>` | Save output files to dir |
| `-x` / `--sep-files` | Per-test `<test>.<name>_out.txt` files (also forces quiet) |
| `--results-file <path>` | Override default `.previous_test_results.json` |

### Capabilities
| Flag | Effect |
|---|---|
| `--ignore` | Drop **all** skip caveats (capability + mesh_mode + heavy + ...) |
| `--ignore-capability NAME` | Drop one cap (extend; pass multiple times). Errors if NAME isn't registered. |
| `--only-tests-that-require NAME` | Run only tests whose `capabilities` actually depends on NAME |
| `--minimal-capabilities` | Skip the `--show-capabilities` query (auto-set when no app found) |
| `--compute-device cpu\|cuda\|hip\|mps\|ceed-cpu\|ceed-cuda\|ceed-hip\|xpu` | Pass through to app |
| `--distributed-mesh` | Filter to `mesh_mode = ALL/DISTRIBUTED` and pass `--distributed-mesh` |

### App options
| Flag | Effect |
|---|---|
| `--allow-unused` | Don't error on unused params |
| `--allow-warnings` | Don't pass `--error` |
| `--error` | Treat warnings as errors |
| `--error-unused` | Treat unused params as errors |
| `--error-deprecated` | Treat deprecations as errors |
| `--cli-args "<args>"` | Append CLI args to every test |
| `--append-runapp-cliarg ARG` | Append to RunApp tests only (extend) |
| `--recoversuffix cpr\|cpa` | Recover-mode file suffix |

### Failure handling
| Flag | Effect |
|---|---|
| `--max-fails N` | Stop running after N failures (default 50) |
| `--valgrind-max-fails N` | Same for valgrind (default 5) |

### Resources
| Flag | Effect |
|---|---|
| `--max-cpu-per-slot N` | Max %CPU per slot |
| `--max-memory-per-slot N` | Max MB per slot (or env `MOOSE_MAX_MEMORY_PER_SLOT`) |
| `--no-cpu-tracking` / `--no-memory-tracking` | Disable tracking |

### HPC
| Flag | Effect |
|---|---|
| `--hpc pbs\|slurm` | Submit jobs to a scheduler |
| `--hpc-host NAME` | Submission host (auto-detects pbs for `bitterroot`/`sawtooth`/`teton`/`windriver`) |
| `--pbs-queue NAME` | PBS queue (closest thing to `--queue`) |
| `--hpc-srun` | Use srun instead of mpiexec |
| `--hpc-project NAME` | Project name (default `moose`) |

### Diagnostic
| Flag | Effect |
|---|---|
| `--json` / `--yaml` / `--dump` | Dump Tester params and exit |
| `--pedantic-checks` | Detect race conditions in file writes |
| `--use-subdir-exe` | Use sub-dir testroots when present |
| `--capture-perf-graph` | Write `Outputs/perf_graph_json_file` for RunApp tests |

## Common recipes

```bash
# Run everything in this testroot, 8 slots
./run_tests -j 8

# One test by regex (matches against <spec_dir>/<test_name>)
./run_tests --re=simple_diffusion

# Only the failures from last run
./run_tests --failed-tests -j 8

# Replay last run's results without executing
./run_tests --show-last-run

# Single test, debugging
./run_tests --re=simple_diffusion -v --no-color -j 1

# Use dbg binary so mooseAssert fires
./run_tests --dbg --re=my_test -v
METHOD=dbg ./run_tests --re=my_test -v

# Validate inputs without solving
./run_tests --check-input --re=my_test

# Run heavy tests
./run_tests --heavy -j 8
./run_tests --all-tests -j 8     # heavy + non-heavy

# Recover-mode (each test → part1 + part2)
./run_tests --re=transient --recover

# Valgrind
./run_tests --re=my_test --valgrind -j 1

# Show 10 slowest jobs
./run_tests -j 8 --longest-jobs 10

# Per-test output files
./run_tests -j 8 --sep-files -o /tmp/out

# See what would be run
./run_tests --dry-run --re=my_test

# Treat warnings as errors
./run_tests --error --re=my_test

# Pass extra CLI args to every test
./run_tests --cli-args "Outputs/exodus=false" --re=my_test
```

## Status taxonomy

| Status | Color | Code | Meaning |
|---|---|---|---|
| `OK` | green | 0x0 | Pass |
| `SKIP` | grey | 0x0 | Skipped, reason printed |
| `SILENT` | grey | 0x0 | Skipped, NOT printed (regex non-match, group filter) |
| `FAIL` | red | 0x80 | Generic failure (nonzero exit, missing gold, parser error) |
| `DIFF` | yellow | 0x81 | Diff testers (Exodiff/CSVDiff/...) mismatch vs gold |
| `DELETED` | red | 0x83 | Marked `deleted = ...` |
| `ERROR` | red | 0x84 | Internal harness error (UNKNOWN/INVALID CAPABILITIES, etc.) |
| `RACE` | red | 0x85 | Race condition (only with `--pedantic-checks`) |
| `TIMEOUT` | red | 0x1 | Exceeded `max_time` (default 300s) |

Process exit code is bitwise OR of all failures.

## Skip-caveat decoder

The `[bracket]` after a test name is the skip reason. Common ones:

| Caveat | Cause |
|---|---|
| `[mesh_mode!=DISTRIBUTED]` | Spec restricts mesh mode |
| `[Need petsc>=3.18]` | Capability check failed (text mirrors `capabilities = ...`) |
| `[HEAVY]` | `heavy = true` and `--heavy` not passed |
| `[NO RECOVER]` / `[NO RESTEP]` | `recover = false` / `restep = false` and the recover/restep mode is active |
| `[max_cpus=N]` / `[min_cpus=N]` | Parallel constraint |
| `[ENV VAR NOT SET]` / `[ENV VAR SET]` | `env_vars` / `env_vars_not_set` |
| `[NO DISPLAY]` | `display_required = true` and no `$DISPLAY` |
| `[<sub> submodule not initialized]` | `required_submodule` |
| `[Valgrind requires non-threaded]` | Under `--valgrind` |
| `[no <prog>]` | `requires` not on PATH |
| `[Max Fails Exceeded]` | Past `--max-fails` (this is FAIL, not SKIP) |

To force-run: `--ignore` (drops all caveats), `--ignore-capability NAME` (drops one cap).

## Gold regeneration — manual workflow

There is **no automation**. No `--copy-gold`, no `--update-golds`, no helper script. It's a manual `cp`.

```bash
# 1. cd to the test directory
cd <app>/test/tests/<area>/<feature>

# 2. Run the failing test, verbose, single slot
./run_tests --re=<test_name> -v --no-color -j 1
# Inspect the diff output. This is where human judgment is required —
# is the new behavior actually correct?

# 3. Optionally run exodiff manually with the same tolerances
exodiff -F 1e-10 -t 5.5e-6 gold/<feature>_out.e <feature>_out.e

# 4. Copy fresh outputs into gold/
cp <feature>_out.e gold/<feature>_out.e
# For tests with multiple outputs, copy each name listed in
# exodiff = '...' / csvdiff = '...' from the spec.

# 5. Confirm
./run_tests --re=<test_name> -v --no-color -j 1

# 6. Commit gold separately with explanation
git add <area>/<feature>/gold/
git commit -m "Regenerate <area>/<feature> gold

<Explain the physics/numerics change that necessitated regeneration,
referencing the relevant PR or issue.>"
```

For `RunException`/`RunApp` (output-pattern) tests there's no gold — edit `expect_err`/`expect_out`/`absent_out` in the spec instead.

For `Outputs/file_base=foo` parametrized tests, gold is `gold/foo.e` (no `_out`) — match the name in the spec's `exodiff = '...'`.

## Capability gating

Tests gate via `capabilities = '<expression>'` in the spec:

```hit
capabilities = 'petsc>=3.18 & vtk & !installation_type=relocated'
capabilities = 'method=opt'
capabilities = 'mfem & platform=linux'
capabilities = 'machine=x86_64'           # works around Apple Si compiler bugs
capabilities = 'neml'                     # gate on optional dependency
```

Operators: `&`, `|`, `!`, comparisons (`>=`, `<`, `=`, `!=`).

The harness queries `<exe> --show-capabilities` at startup and parses the JSON. To inspect:

```bash
./<app>-opt --show-capabilities
```

Augmented runtime caps (added by harness): `hpc`, `machine`, `platform`, plus `known_capabilities` from `testroot`.

Runtime overrides:

- `--ignore-capability NAME` — pretend NAME is whatever the test wants (extend; pass multiple).
- `--only-tests-that-require NAME` — only run tests whose `capabilities` expression actually depends on NAME (the harness verifies dependence by re-evaluating with NAME negated).
- `--minimal-capabilities` — skip the query entirely; treat all checks as pass.

## CIVET (CI)

CIVET is INL's CI system at `https://civet.inl.gov`. **There is no `.civet.yml` in the repo and no in-tree `run_cmd.sh`** — recipes live on the CIVET server. They invoke `./run_tests` (and `./moosedocs.py check`) with extra args.

CI uses the same `./run_tests` script with extra args (commonly `--hpc=pbs`, `--max-fails 999999`, `MOOSE_TERM_FORMAT=tpnsc`). Tests opt into the limited HPC pipeline with `group = 'hpc'` in the spec.

The runner produces `.previous_test_results.json` and stdout; CIVET parses both, posts comments back to GitHub PRs (controlled by `CIVET_SERVER_POST_COMMENT=1`).

CIVET → MooseDocs flow:
- `moose/python/MooseDocs/extensions/civet.py` — `!civet badge`/`!civet results` shortcodes.
- `moose/python/mooseutils/civet_results.py` — downloads CIVET tarballs, parses run_tests output.
- `moose/python/TestHarness/resultsstore/civetstore.py` — pushes results to storage.

## Debugging common failures

| Failure | Likely cause | Fix |
|---|---|---|
| Unknown `type =` | Tester not registered; binary not built; wrong `app_name` in `testroot` | `make -j`, check `--yaml` for registered testers |
| Gold diff (small numeric) | Floating-point drift, parallel non-determinism | Re-run `-j 1`; if persistent, raise `rel_err`/`abs_zero` |
| Gold diff (large) | Real algorithm/physics change | Regenerate gold (see workflow above) |
| Parallel-only failure | Ghosting/output-ordering issue, race condition | `--pedantic-checks` to detect races; reproduce with `-p N -v` |
| `[Need petsc>=...]` skip | Build's PETSc version too old | Update build, or `--ignore-capability petsc` for one run |
| Permission denied / executable missing | `METHOD` doesn't match a built binary | `make -j`, or set `METHOD=<existing>` |
| "input file not found" | Path is relative to spec dir, not CWD | Use bare names; harness `chdir`s into spec dir |
| Failed to import hit | `$PYTHONPATH` interference, conda env wrong | `unset PYTHONPATH`, `conda activate moose` |

## Environment variables

| Var | Effect |
|---|---|
| `MOOSE_DIR` | Roots the harness; auto-derived if unset |
| `METHOD` | Default app suffix (`opt`/`dbg`/`devel`/`oprof`) |
| `MOOSE_TERM_FORMAT` | Output field codes (default `njcstm`) |
| `MOOSE_TERM_COLS` | Terminal width override |
| `MOOSE_MAX_MEMORY_PER_SLOT` | Default for `--max-memory-per-slot` (MB) |
| `MOOSE_MPI_COMMAND` | Override `mpiexec` command |
| `OMP_NUM_THREADS` | Set per-job by `--n-threads` |

There is **no `MOOSE_INSTALLATION_TYPE`** — `installation_type` is a capability name only.

## Flags that don't exist (but are commonly assumed)

These have NO equivalent in this codebase. Use the listed alternative.

| Assumed flag | Reality |
|---|---|
| `--rerun-failed` | Use `--failed-tests` |
| `--show-failed` / `--show-skipped` / `--show-deleted` / `--show-directory` / `--include-failed` / `--include-deprecated` | Don't exist. Use `-v` for everything; use `--no-report` to suppress skipped. |
| `--ok-skip` | Don't exist |
| `--no-capabilities` | Use `--ignore` (drops all caveats) |
| `--capabilities=...` | That's a *spec-file* parameter, not a CLI flag |
| `--installation_type` | Capability name, not a flag |
| `--queue` | Use `--pbs-queue` (only with `--hpc=pbs`) |
| `--diff-allowed` | Don't exist |
| `--store-timing` / `--load-timing` | Don't exist |
| `--no-heavy` | Default already excludes heavy. Use `--heavy` (only-heavy) or `--all-tests` (both). |
| `--method` | Use `--opt`/`--dbg`/`--devel`/`--oprof` or `METHOD=...` env |
| `-t <test_type>` | `-t` is `--timing`. Filter by name with `--re=`. |
| `--copy-gold` / `--update-golds` | Manual `cp` workflow (see Gold regeneration above) |
