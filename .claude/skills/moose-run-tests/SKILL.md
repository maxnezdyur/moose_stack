---
name: moose-run-tests
description: MOOSE ./run_tests cheat sheet — real CLI flags, common recipes, status taxonomy, skip-caveat decoder, manual gold regeneration workflow, capability gating, CIVET basics, debugging recipes, env vars, and a list of commonly assumed flags that don't actually exist. Auto-loads when running, debugging, or filtering MOOSE tests; also invocable as /moose-run-tests.
user-invocable: true
---

# MOOSE `./run_tests` Cheat Sheet

Reference for running, filtering, debugging, and regenerating golds in `moose`, `moose/modules/<m>`, `blackbear`, `isopod`. For *authoring*, see **moose-test-standards** / **moose-unit-test-standards**.

**Full flag list:** `./run_tests --help`. This skill covers only the gotchas, the workflows the CLI doesn't document, and flags people invent that don't exist.

## Where to run

`run_tests` is a tiny Python shim and does NOT activate conda.

```bash
conda activate moose
cd <app>/test          # or moose/modules/<m>/test, blackbear/, isopod/
./run_tests -j 2
```

The harness walks upward from CWD looking for a `testroot` file, then `os.walk`s for files literally named `tests`. Skips `.git`, `contrib/`, `.svn/`, any dir with `.moose_ignore`.

`testroot` keys: `app_name`, `run_tests_args`, `extra_pythonpath`, `known_capabilities`, `allow_warnings`, `allow_unused`, `allow_override`.

## Most-used recipes

```bash
./run_tests -j 2                                 # full suite
./run_tests --re=<name> -v --no-color -j 1       # one test, verbose, debuggable
./run_tests --check-input --re=<name>            # parse-only, no solve
./run_tests --failed-tests -j 2                  # rerun previous failures
./run_tests --show-last-run                      # replay results, no execution
./run_tests --dbg --re=<name> -v                 # dbg binary (mooseAssert fires)
METHOD=dbg ./run_tests --re=<name> -v            # equivalent
./run_tests --heavy -j 2                         # only heavy tests
./run_tests --all-tests -j 2                     # heavy + non-heavy
./run_tests --re=<name> --recover                # part1 + part2 recovery split
./run_tests --re=<name> --valgrind -j 1
./run_tests --dry-run --re=<name>                # show what would run
./run_tests --cli-args "Outputs/exodus=false" --re=<name>
```

`--check-input`, `--recover`, `--restep` are **mutually exclusive**.

## Build method (binary suffix)

`--opt` (default) / `--dbg` / `--devel` / `--oprof` — these select the `<app>-<method>` binary. Or `METHOD=dbg` env var. **There is no `--method` flag.**

## Status taxonomy

| Status | Code | Meaning |
|---|---|---|
| `OK` | 0x0 | Pass |
| `SKIP` | 0x0 | Skipped, reason in `[brackets]` |
| `SILENT` | 0x0 | Skipped silently (regex non-match, group filter) |
| `FAIL` | 0x80 | Nonzero exit, missing gold, parser error |
| `DIFF` | 0x81 | Exodiff/CSVDiff/... mismatch |
| `DELETED` | 0x83 | Spec marked `deleted = ...` |
| `ERROR` | 0x84 | Harness error (UNKNOWN/INVALID CAPABILITIES, etc.) |
| `RACE` | 0x85 | Race condition (only with `--pedantic-checks`) |
| `TIMEOUT` | 0x1 | Past `max_time` (default 300s) |

Process exit is bitwise OR of failures.

## Skip-caveat decoder

The `[bracket]` after a test name is the skip reason:

| Caveat | Cause |
|---|---|
| `[Need petsc>=3.18]` etc. | `capabilities = '...'` check failed (text mirrors the expression) |
| `[mesh_mode!=DISTRIBUTED]` | Spec restricts mesh mode |
| `[HEAVY]` | `heavy = true` and `--heavy` not passed |
| `[NO RECOVER]` / `[NO RESTEP]` | Spec opts out + that mode is active |
| `[max_cpus=N]` / `[min_cpus=N]` | Parallel constraint |
| `[ENV VAR NOT SET]` / `[ENV VAR SET]` | `env_vars` / `env_vars_not_set` |
| `[NO DISPLAY]` | `display_required = true`, no `$DISPLAY` |
| `[<sub> submodule not initialized]` | `required_submodule` |
| `[no <prog>]` | `requires` not on PATH |
| `[Max Fails Exceeded]` | Past `--max-fails` (this is FAIL, not SKIP) |

Override: `--ignore` (drops all), `--ignore-capability NAME` (drops one, repeatable).

## Gold regeneration — manual workflow

**No automation.** No `--copy-gold`, no `--update-golds`. Manual `cp`:

```bash
cd <app>/test/tests/<area>/<feature>
./run_tests --re=<name> -v --no-color -j 1     # inspect diff; is new behavior correct?
cp <feature>_out.e gold/<feature>_out.e        # repeat for every file in spec's exodiff='...'
./run_tests --re=<name> -v --no-color -j 1     # confirm OK
git add gold/ && git commit                    # separate commit, explain physics change
```

- `Outputs/file_base=foo` → gold is `gold/foo.<ext>` (no `_out`).
- `RunException`/`RunApp` have no gold — edit `expect_err`/`expect_out`/`absent_out` instead.
- Reproduce exodiff manually: `<MOOSE_DIR>/framework/contrib/exodiff/exodiff -m -F <abs_zero> -t <rel_err> gold/<f>.e <f>.e`.

## Capability gating

Specs gate via `capabilities = '<expression>'`. Operators: `& | !` and comparisons `>= < = !=`.

```hit
capabilities = 'petsc>=3.18 & vtk & !installation_type=relocated'
capabilities = 'method=opt'
capabilities = 'mfem & platform=linux'
```

Inspect: `./<app>-opt --show-capabilities`. Augmented runtime caps: `hpc`, `machine`, `platform`, plus `known_capabilities` from `testroot`.

Overrides: `--ignore-capability NAME` (pretend NAME passes), `--only-tests-that-require NAME` (only tests whose expression depends on NAME), `--minimal-capabilities` (skip query entirely).

## CIVET (CI)

INL's CI at `civet.inl.gov`. **No in-tree `.civet.yml` / `run_cmd.sh`** — recipes live on the CIVET server and invoke `./run_tests` with extra args (commonly `--hpc=pbs`, `--max-fails 999999`, `MOOSE_TERM_FORMAT=tpnsc`). Tests opt in to the limited HPC pipeline with `group = 'hpc'`.

CIVET → MooseDocs integration lives in `moose/python/MooseDocs/extensions/civet.py`, `moose/python/mooseutils/civet_results.py`, `moose/python/TestHarness/resultsstore/civetstore.py`.

## Debugging common failures

| Failure | Cause | Fix |
|---|---|---|
| Unknown `type =` | Tester unregistered / binary not built / wrong `app_name` | `make -j`; `--yaml` to list registered |
| Tiny numeric DIFF | FP drift, parallel non-determinism | Re-run `-j 1`; if persistent, raise `rel_err`/`abs_zero` (column-scoped if possible) |
| Large DIFF | Real algorithm change | Regenerate gold (workflow above) |
| Parallel-only failure | Ghosting / race | `--pedantic-checks` to detect; reproduce with `-p N -v` |
| `UNKNOWN/INVALID CAPABILITIES` | Stale binary post-pull | `make -j` (capability registry baked in) |
| `Failed to import hit` | `$PYTHONPATH` interference, wrong env | `unset PYTHONPATH; conda activate moose` |

For deeper diagnostics (DIFF triage, valgrind, recover-only failures, race detection, CIVET-only reproductions, gdb/lldb), see **moose-test-workflows**.

## Environment variables

| Var | Effect |
|---|---|
| `MOOSE_DIR` | Roots the harness; auto-derived if unset |
| `METHOD` | Default app suffix |
| `MOOSE_TERM_FORMAT` | Output field codes (default `njcstm`; codes: `n`/`N` name, `j` dots, `c` caveats, `s` status, `p` padded pre-status, `t` time, `m` memory) |
| `MOOSE_TERM_COLS` | Terminal width |
| `MOOSE_MAX_MEMORY_PER_SLOT` | MB cap |
| `MOOSE_MPI_COMMAND` | Override `mpiexec` |
| `OMP_NUM_THREADS` | Set per-job by `--n-threads` |

**There is no `MOOSE_INSTALLATION_TYPE`** — `installation_type` is a capability name only.

## Flags that don't exist (but are commonly assumed)

| Assumed | Reality |
|---|---|
| `--rerun-failed` | `--failed-tests` |
| `--show-failed` / `--show-skipped` / `--show-deleted` / `--show-directory` | Don't exist. Use `-v`; `--no-report` suppresses skipped. |
| `--ok-skip` / `--no-capabilities` / `--diff-allowed` / `--store-timing` / `--load-timing` / `--copy-gold` / `--update-golds` | Don't exist |
| `--capabilities=...` / `--installation_type` | Spec-file parameters, not CLI flags |
| `--queue` | `--pbs-queue` (only with `--hpc=pbs`) |
| `--no-heavy` | Default already excludes heavy; `--heavy` = only-heavy, `--all-tests` = both |
| `--method` | Use `--opt`/`--dbg`/`--devel`/`--oprof` or `METHOD=...` |
| `-t <test_type>` | `-t` is `--timing`. Filter with `--re=`. |
