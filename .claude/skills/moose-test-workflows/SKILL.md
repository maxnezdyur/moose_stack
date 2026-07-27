---
name: moose-test-workflows
description: MOOSE test workflows — what to actually do (not just what flags exist). Per-scope cd/build/run cheat sheet, pre-push routine, build cascade rules, failure-diagnosis flowchart, gold regeneration end-to-end, CIVET-only failure causes, interactive debugging. Auto-loads when running, debugging, or regenerating MOOSE tests; complements moose-run-tests (flag reference) and moose-test-standards (authoring).
user-invocable: false
---

# MOOSE Test Workflows

Procedures and diagnosis. Flags, status taxonomy, skip-caveat decoder, env vars: **moose-run-tests**. Authoring conventions: **moose-test-standards**.

## Per-scope cheat sheet

| Scope | cd here | Binary | testroot | Notes |
|---|---|---|---|---|
| Framework | `moose/test/` | `moose_test-opt` | `moose/test/testroot` | `--allow-test-objects` ON by default (use `--disallow-test-objects` to opt out) |
| Module | `moose/modules/<m>/` | `<m>-opt` (production app) | `moose/modules/<m>/testroot` | One binary for prod + tests; `<Module>TestApp.C` is just a class, not a separate binary |
| Combined modules | `moose/modules/` | `combined-opt` | `moose/modules/testroot` | Aggregate binary linking every module |
| Blackbear | `blackbear/` | `blackbear-opt` | none — `run_tests` passes `app_name='blackbear'` | Modules: contact, heat_transfer, misc, solid_mechanics, stochastic_tools, xfem |
| Isopod | `isopod/` | `isopod-opt` | `isopod/testroot` | Modules: heat_transfer, solid_mechanics, optimization. TAO requires opt build → most tests gated `capabilities = 'method=opt'` |

## Pre-push routine (community practice, not codified)

The contributing guide does not prescribe a pre-push command. Implicit floor:

    cd <changed-scope>          # framework / module / blackbear / isopod
    make -j 2                    # ~2GB RAM per job; drop -j on RAM-constrained boxes
    ./run_tests -j 2             # full suite for this scope

If you touched framework code that other scopes link against, re-run their suites too. CIVET catches OS/compiler/PETSc/parallel/heavy/distributed-mesh permutations you can't reproduce locally. Engineers periodically run `--error-deprecated` to catch deprecation drift, but it's not a gate.

## Canary smoke

Quick proof-of-life that conda env, framework build, and harness wiring are intact:

    cd moose/test
    ./run_tests -i always_ok -p 2

The spec is at `moose/test/tests/test_harness/always_ok` — a `RunApp` against `good.i`. If this fails, your build is broken; don't debug individual tests yet.

## "What tests do I run for changed file X?"

No automated mapping exists. Manual approach:

    # By area (test name format is <spec_dir>/<test_name>)
    cd moose/test
    ./run_tests --re=kernels       # if you touched framework/src/kernels/

    # By class type — grep test inputs
    grep -rln "type *= *MyClass" tests/

    # By module — cd to the module root and run its full suite

Framework changes may need both `moose/test` and any module that links the changed file.

## Build cascade rules

| Change | What needs rebuild |
|---|---|
| `moose/framework/src/...` | libmoose, every module lib, every binary that links libmoose. Rebuild from any scope; that scope's binary picks it up. |
| `moose/modules/<m>/src/...` | `lib<m>-opt.la`, `<m>-opt`, `combined-opt`, plus any downstream app whose Makefile sets `<M> := yes`. Cascade is per-`make` invocation; no global watcher. |
| `blackbear/` or `isopod/` source | Only that app's binary. No cascade. |
| `framework/src/base/CapabilityRegistry.C` | All binaries — augmented capability list is baked in. Stale binary → `UNKNOWN/INVALID CAPABILITIES` errors. |

`make` from `moose/modules/` (top) builds combined + every module lib. From `moose/modules/<m>/` it builds only that module's lib + binary + dep modules. From `moose/test/` it builds framework + moose_test only. Module deps cascade automatically via `DEPEND_MODULES` in `moose/modules/modules.mk` (e.g. `heat_transfer → ray_tracing`, `contact → solid_mechanics`).

## Failure-diagnosis flowchart

The status (FAIL/DIFF/TIMEOUT/ERROR/RACE) plus the `[bracket]` caveat picks the path. Caveat meanings: skip-caveat decoder in **moose-run-tests**.

### DIFF (Exodiff/CSVDiff/JSONDiff mismatch)

    ./run_tests --re=<name> -v --no-color -j 1

Scroll above the summary for the actual diff lines, then decide:

- Tiny last-digit drift on a few vars → loosen `rel_err`/`abs_zero` in the spec. Don't regen — you'd encode your machine's rounding.
- Large/structural diff → regenerate gold (below).
- Passes `-j 1` but fails `-p 2` → parallel non-determinism. Fix the code, not `mesh_mode`. Common culprits: missing ghost element access, non-deterministic reduction, output-ordering depending on rank.

The exodiff invocation is reproducible standalone:

    <MOOSE_DIR>/framework/contrib/exodiff/exodiff -m -F <abs_zero> -t <rel_err> \
        gold/<file>.e <file>.e

For one bad CSV column, prefer column-scoped overrides over loosening globally:

    override_columns  = 'pp_name'
    override_rel_err  = '1e-4'
    override_abs_zero = '1e-8'

### FAIL (RunApp / nonzero exit)

The "Tester failed, reason: ..." line tells you which path:

| Reason | Likely cause |
|---|---|
| `EXIT CODE N != 0` | App crashed / asserted / parse failed. Read the output above. |
| `ERRMSG` | App exited 0 but printed `ERROR`/`command not found`/`terminate called after throwing...` |
| `EXPECTED ERROR/ASSERT/OUTPUT MISSING` | RunException's `expect_err`/`expect_assert`/`expect_out` didn't match |
| `OUTPUT NOT ABSENT` | `absent_out` matched something it shouldn't |
| `Application not found` | Binary missing → `make -j` |
| `MEMORY ERROR` | valgrind run, output didn't contain `ERROR SUMMARY: 0 errors` |
| `MISSING GOLD FILE` | First-time test, gold not yet committed |

Exit code 77 is silently converted to `SKIP "CAPABILITIES"`, so capability mismatches won't show as FAIL.

Common upstream causes for `EXIT CODE != 0`:
- Input parse error → grep output for `*** ERROR ***`
- Unknown `type =` → tester unregistered / binary not built / wrong `app_name`; `make -j`, then `--yaml` to list registered types
- mooseError / divergence → framework prints stack
- Segfault → exit 139; rerun under debugger
- Stale capability registry → rebuild
- `Failed to import hit` → `$PYTHONPATH` interference or wrong env → `unset PYTHONPATH`, then activate the right env (`moose`, or the worktree's `moose-<feature>` env)

### TIMEOUT

Default `max_time = 300s` (per-spec `max_time = 600` or `MOOSE_TEST_MAX_TIME` env overrides):

1. Slow filesystem / underpowered box → bump `max_time` in spec.
2. Test legitimately takes minutes → mark `heavy = true` (only runs with `--heavy`).
3. Test doing too much → split via `prereq` chain or use `--check-input` for parse-only.
4. Valgrind timeouts are auto-doubled (NORMAL) or 6x'd (HEAVY).

### Race condition

`-j 1` passes, `-j 2` fails. Detect with:

    ./run_tests --re=foo --pedantic-checks -j 2

The harness snapshots mtimes pre/post-run, intersects modified-file sets between non-prereq parallel jobs, and prints "race partner" sets. Fix with `prereq = 'other_test'` or `working_directory = 'subdir'`.

### Failure under `--dbg` only

mooseAssert fired. Either fix the precondition (real bug) or the assert is stale (fix/remove). Don't paper over with `--devel`.

### Failure under `--recover` only

The harness clones each spec into part1 (`--test-checkpoint-half-transient`) + part2 (`--recover`). If part2 fails, the SUT has a real restart bug — state isn't being dumped/loaded. `recover = false` would hide it; only set when the test legitimately can't recover (steady solves, mesh-only, custom-postprocessor tests).

### Failure under `--valgrind`

Pass criterion: `ERROR SUMMARY: 0 errors` in output. Anything else → `MEMORY ERROR` (uninitialized read, leak, invalid free). Suppression file pre-loaded: `moose/python/TestHarness/suppressions/errors.supp` (silences OpenMPI noise). `valgrind = HEAVY` on a spec restricts it to `--valgrind-heavy` runs. `--valgrind-max-fails` defaults to 5.

### `UNKNOWN/INVALID CAPABILITIES` (ERROR status)

Binary's capability metadata is stale — common after pulling changes that touched `framework/src/base/CapabilityRegistry.C`. Rebuild the scope (`make -j 2`).

## Gold regeneration end-to-end

There is **no automation** (no `--copy-gold` / `--update-golds`). Manual `cp` workflow:

    # 1. Run the failing test, verbose, single slot
    cd <scope>           # moose/test, moose/modules/<m>/, blackbear, isopod
    ./run_tests --re=<test_name> -v --no-color -j 1

    # 2. Inspect the diff. Decide whether the new behavior is correct.
    #    (For exodiff, reproduce standalone to drill in — command above.)

    # 3. Copy fresh outputs into gold/
    cd test/tests/<area>/<feature>      # the spec dir
    mkdir -p gold
    cp <feature>_out.e gold/<feature>_out.e
    # For multiapp: copy every file listed in the spec's exodiff = '...'
    # For Outputs/file_base=foo parametrized tests: gold is gold/foo.e (no _out)

    # 4. Confirm
    cd <scope>
    ./run_tests --re=<test_name> -v --no-color -j 1

    # 5. Commit gold separately with explanation
    git add <path>/gold/
    git commit -m "Regenerate <area>/<feature> gold for <change>"

For `RunException`/`RunApp` (output-pattern) tests, there's NO gold. Edit `expect_err`/`expect_out`/`absent_out` in the spec instead.

## CIVET-only failures (passes locally, fails CI)

| Likely cause | Reproduce locally |
|---|---|
| Heavy split | `./run_tests --heavy --re=<name>` |
| Distributed mesh | `./run_tests --distributed-mesh --re=<name>` |
| Parallel scaling | `./run_tests --re=<name> -p 2` (or higher) |
| Machine arch (`machine=x86_64` vs `arm64`) | Can't fully — but check `capabilities` line in spec |
| Heavy valgrind | `./run_tests --valgrind-heavy --re=<name>` |
| Conda env drift (PETSc/MFEM/libtorch versions) | `./<app>-opt --show-capabilities` to compare |
| HPC pipeline (`group = 'hpc'`) | `./run_tests -g hpc --re=<name>` |

The forensic artifact CIVET archives is `.previous_test_results.json` — pull it down to inspect exact command, exit code, caveats, output paths, timings, PerfGraph JSON.

## Interactive debugging (gdb/lldb)

Not officially documented. Convention:

    ./run_tests --re=<test_name> --dry-run        # get the exact command the harness would run

    cd <spec_dir>
    gdb --args <path/to/app>-dbg -i <input.i> <other args>
    lldb -- <path/to/app>-dbg -i <input.i> <other args>    # macOS

For MPI failures: launch with `mpiexec`, attach with `gdb -p <pid>`. `METHOD=dbg` (or `--dbg`) gets you full symbols and live `mooseAssert`.

## What to skip vs revert when you cause a regression

- Small regression, tracked in an issue: `skip = 'refs #1234'` in the spec until fixed.
- Many tests across modules broken: revert the offending change.

There's no flaky-test allowlist mechanism; `skip` is the only path. CIVET may have its own retry layer at the CI level.

## The `.previous_test_results.json` artifact

Default location: `<scope>/.previous_test_results.json`. Override via `--results-file`. Contents:

- `testharness`: version, start/end time, args, root_dir, scheduler, moose_dir
- `environment`: hostname, user
- `apptainer`: container info if in one
- `tests`: per-test status, status_message, caveats, command, input_file, output paths, JSON metadata, validation data, max_memory
- `stats`: aggregate counts and timings

Used by `--failed-tests` (re-run only failures) and `--show-last-run` (re-print results without execution).
