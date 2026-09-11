---
name: moose-run-tests
description: MOOSE ./run_tests reference for moose, moose/modules/<m>, blackbear, and isopod: conda-run.sh invocation, scope-to-binary table, recipes, status taxonomy, skip-caveat decoder, build cascade, gold regeneration by hand, flags that do not exist, and routing by runner status into references/ for failure diagnosis and CI debugging. Preloaded by moose-test-runner; use when running, filtering, debugging, or regenerating MOOSE tests.
user-invocable: false
---

# MOOSE `./run_tests` reference

Running and diagnosing only. Authoring a `tests` spec or a `.i` input is the `moose-test-standards`
skill; gtest unit tests are the `moose-unit-test-standards` skill. `./run_tests --help` lists every
flag; this file carries the gotchas and the repo facts.

## Where to run

`run_tests` is a small Python shim and does not activate conda. Locally, run every harness or
make command through the wrapper; on INL HPC hostnames (`sawtooth*`, `lemhi*`, `bitterroot*`,
`hoodoo*`, `teton*`) there is no conda, so run the bare command inside the container shell.

    bash <meta-root>/scripts/conda-run.sh -C <scope> -- ./run_tests <flags>
    bash <meta-root>/scripts/conda-run.sh -C <scope> -- make -j N

The harness walks upward from the current directory to a `testroot` file, then walks down for
files literally named `tests`, skipping `.git`, `contrib/`, `.svn/`, and any directory holding
`.moose_ignore`.

| Scope | `<scope>` (run here) | Binary | testroot | Notes |
|---|---|---|---|---|
| Framework | `moose/test/` | `moose_test-opt` | `moose/test/testroot` | `--allow-test-objects` is on by default; `--disallow-test-objects` opts out |
| Module | `moose/modules/<m>/` | `<m>-opt` | `moose/modules/<m>/testroot` | One production binary runs prod and tests; `<M>TestApp.C` is a class, not a binary |
| Combined | `moose/modules/` | `combined-opt` | `moose/modules/testroot` | Aggregate binary linking every module |
| Blackbear | `blackbear/` | `blackbear-opt` | none; `run_tests` passes `app_name='blackbear'` | Modules: contact, heat_transfer, misc, solid_mechanics, stochastic_tools, xfem |
| Isopod | `isopod/` | `isopod-opt` | `isopod/testroot` | Modules: heat_transfer, solid_mechanics, optimization. TAO needs an opt build, so most specs carry `capabilities = 'method=opt'` |

Binary suffix: `--opt` (default), `--dbg`, `--devel`, `--oprof`, or `METHOD=<method>` in the
environment. There is no `--method` flag.

## Recipes

    ./run_tests -j N                                 # full suite for this scope
    ./run_tests --re=<name> -v --no-color -j 1       # one test, verbose; -j 1 keeps stdout uninterleaved
    ./run_tests --check-input --re=<name>            # parse only, no solve; fastest signal
    ./run_tests --failed-tests -j N                  # rerun the previous failures
    ./run_tests --show-last-run                      # replay results without running
    ./run_tests --dbg --re=<name> -v                 # dbg binary; mooseAssert fires
    ./run_tests --heavy -j N                         # heavy tests only; --all-tests = heavy + normal
    ./run_tests --re=<name> --recover                # part1 + part2 recovery split
    ./run_tests --re=<name> --valgrind -j 1
    ./run_tests --re=<name> -p 2                     # 2 MPI ranks per test
    ./run_tests --dry-run --re=<name>                # print the commands the harness would run
    ./run_tests --cli-args "Outputs/exodus=false" --re=<name>
    ./run_tests --error-deprecated -j N              # deprecation drift; not a CI gate
    ./run_tests -i always_ok -p 2                    # from moose/test: proves env, build, and harness wiring

`--check-input`, `--recover`, and `--restep` are mutually exclusive. `--re=` matches the test name
`<spec_dir>/<test_name>`; there is no changed-file-to-test mapping, so find inputs for a class with
`grep -rln "type *= *MyClass" tests/` and run the areas they live in.

## Status taxonomy

| Status | Code | Meaning |
|---|---|---|
| `OK` | 0x0 | Pass |
| `SKIP` | 0x0 | Skipped, reason in `[brackets]` |
| `SILENT` | 0x0 | Skipped silently (regex non-match, group filter) |
| `FAIL` | 0x80 | Nonzero exit, missing gold, parser error |
| `DIFF` | 0x81 | Exodiff/CSVDiff/JSONDiff mismatch |
| `DELETED` | 0x83 | Spec marked `deleted = ...` |
| `ERROR` | 0x84 | Harness error (`UNKNOWN/INVALID CAPABILITIES`, ...) |
| `RACE` | 0x85 | Race condition (only with `--pedantic-checks`) |
| `TIMEOUT` | 0x1 | Past `max_time` (default 300 s) |

The process exit code is the bitwise OR of the failures. An app exit code of 77 becomes
`SKIP [CAPABILITIES]`, so a capability mismatch never shows as `FAIL`.

## Skip-caveat decoder

| Caveat | Cause | Fix or override |
|---|---|---|
| `[Need petsc>=3.18]` and similar | `capabilities = '...'` failed; text mirrors the expression | Update the build, or `--ignore-capability petsc` for one run |
| `[mesh_mode!=DISTRIBUTED]` | Spec restricts mesh mode | `--distributed-mesh` |
| `[HEAVY]` | `heavy = true` without `--heavy` | `--heavy` |
| `[NO RECOVER]` / `[NO RESTEP]` | Spec opts out and that mode is active | Drop the mode flag |
| `[max_cpus=N]` / `[min_cpus=N]` | Parallel constraint | Adjust `-p` |
| `[ENV VAR NOT SET]` / `[ENV VAR SET]` | `env_vars` / `env_vars_not_set` | Set or unset the variable |
| `[NO DISPLAY]` | `display_required = true`, no `$DISPLAY` | |
| `[<sub> submodule not initialized]` | `required_submodule` | `git submodule update --init` |
| `[no <prog>]` | `requires` not on PATH | Install, or run through conda-run.sh |
| `[Max Fails Exceeded]` | Past `--max-fails`; this is `FAIL`, not `SKIP` | |

`--ignore` drops every caveat; `--ignore-capability NAME` drops one (repeatable). Both are
investigation aids, not fixes. Capability expressions, runtime capability names, testroot keys,
and environment variables: `references/ci-and-debugging.md`.

## Build cascade

`make` needs about 2 GB of RAM per job. From `moose/modules/` it builds `combined-opt` and every
module lib; from `moose/modules/<m>/` only that module, its binary, and its dependency modules
(`DEPEND_MODULES` in `moose/modules/modules.mk`, for example `heat_transfer -> ray_tracing`,
`contact -> solid_mechanics`); from `moose/test/` only framework and `moose_test`. The cascade is
per `make` invocation; nothing watches for stale binaries elsewhere.

| Change | What needs a rebuild |
|---|---|
| `moose/framework/src/...` | libmoose, every module lib, every binary that links libmoose; their suites are all affected |
| `moose/modules/<m>/src/...` | `lib<m>-opt.la`, `<m>-opt`, `combined-opt`, any app whose Makefile sets `<M> := yes` |
| `blackbear/` or `isopod/` source | Only that app's binary |
| `framework/src/base/CapabilityRegistry.C` | Every binary; a stale one reports `ERROR: UNKNOWN/INVALID CAPABILITIES` |

## Gold regeneration by hand

There is no `--copy-gold` and no `--update-golds`. Regenerate only after the new output is
confirmed correct, or on `FAIL` with reason `MISSING GOLD FILE` for a newly authored test.

1. `./run_tests --re=<name> -v --no-color -j 1` in `<scope>` writes fresh output into the spec dir.
2. `mkdir -p gold` in the spec dir, then `cp` every file named in the spec's `exodiff`, `csvdiff`, or
   `jsondiff` list into `gold/`. With `cli_args = 'Outputs/file_base=foo'` the gold is `gold/foo.<ext>`
   (no `_out`). A multiapp spec lists every level; copy each one. Two inputs that share one output
   share one gold through a symlink in `gold/`.
3. Re-run the same command; the test must print `OK`.
4. `git add <spec_dir>/gold/` so the gold lands in the staged diff. Leave the commit to the user and
   suggest `Regenerate <area>/<feature> gold for <change>` as its message.

`RunException` and `RunApp` tests have no gold; their fix is `expect_err`, `expect_out`, or
`absent_out` in the spec.

## Flags that do not exist

| Assumed | Reality |
|---|---|
| `--rerun-failed` | `--failed-tests` |
| `--show-failed` / `--show-skipped` / `--show-deleted` / `--show-directory` | Use `-v`; `--no-report` suppresses skipped |
| `--ok-skip` / `--no-capabilities` / `--diff-allowed` / `--store-timing` / `--load-timing` / `--copy-gold` / `--update-golds` | Do not exist |
| `--capabilities=...` / `--installation_type` | Spec-file parameters, not CLI flags |
| `--queue` | `--pbs-queue` (only with `--hpc=pbs`) |
| `--no-heavy` | Default already excludes heavy; `--heavy` = heavy only, `--all-tests` = both |
| `--method` | `--opt` / `--dbg` / `--devel` / `--oprof`, or `METHOD=...` |
| `-t <test_type>` | `-t` is `--timing`; filter with `--re=` |

## Routing by status

Read the named file before acting on a failure.

| Runner printed | Read |
|---|---|
| `DIFF` of any size | `references/failure-diagnosis.md`: tolerance drift versus structural change, standalone `exodiff`, `override_columns` |
| `DIFF` confirmed structural and correct, or `FAIL` with `MISSING GOLD FILE` | Gold regeneration above |
| `FAIL` with any other reason (`EXIT CODE N != 0`, `ERRMSG`, `EXPECTED ERROR/ASSERT/OUTPUT MISSING`, `OUTPUT NOT ABSENT`, `Application not found`, `MEMORY ERROR`) | `references/failure-diagnosis.md` |
| `TIMEOUT`; `RACE`; passes `-j 1` and fails `-p 2`; `ERROR: UNKNOWN/INVALID CAPABILITIES`; fails only under `--dbg`, `--recover`, or `--valgrind`; a regression you caused (skip versus revert) | `references/failure-diagnosis.md` |
| `SKIP` with a `[bracket]` caveat | Skip-caveat decoder above |
| Green locally, red on CIVET; the exact CI invocation or per-test timings; stepping through the app in gdb or lldb | `references/ci-and-debugging.md` |
