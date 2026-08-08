# Failure diagnosis

A test failed — this file says why and what to do. Entry point: the routing table in
**moose-test-workflows** SKILL.md. Flags, status codes, and the skip-caveat decoder:
**moose-run-tests**.

The status (FAIL/DIFF/TIMEOUT/ERROR/RACE) plus the `[bracket]` caveat picks the path. Caveat meanings: skip-caveat decoder in **moose-run-tests**.

## DIFF (Exodiff/CSVDiff/JSONDiff mismatch)

    ./run_tests --re=<name> -v --no-color -j 1

Scroll above the summary for the actual diff lines, then decide:

- Tiny last-digit drift on a few vars → loosen `rel_err`/`abs_zero` in the spec. Don't regen — you'd encode your machine's rounding.
- Large/structural diff → regenerate gold (`references/gold-regeneration.md`).
- Passes `-j 1` but fails `-p 2` → parallel non-determinism. Fix the code, not `mesh_mode`. Common culprits: missing ghost element access, non-deterministic reduction, output-ordering depending on rank.

The exodiff invocation is reproducible standalone:

    <MOOSE_DIR>/framework/contrib/exodiff/exodiff -m -F <abs_zero> -t <rel_err> \
        gold/<file>.e <file>.e

For one bad CSV column, prefer column-scoped overrides over loosening globally:

    override_columns  = 'pp_name'
    override_rel_err  = '1e-4'
    override_abs_zero = '1e-8'

## FAIL (RunApp / nonzero exit)

The "Tester failed, reason: ..." line tells you which path:

| Reason | Likely cause |
|---|---|
| `EXIT CODE N != 0` | App crashed / asserted / parse failed. Read the output above. |
| `ERRMSG` | App exited 0 but printed `ERROR`/`command not found`/`terminate called after throwing...` |
| `EXPECTED ERROR/ASSERT/OUTPUT MISSING` | RunException's `expect_err`/`expect_assert`/`expect_out` didn't match |
| `OUTPUT NOT ABSENT` | `absent_out` matched something it shouldn't |
| `Application not found` | Binary missing → `make -j` |
| `MEMORY ERROR` | valgrind run, output didn't contain `ERROR SUMMARY: 0 errors` |
| `MISSING GOLD FILE` | First-time test, gold not yet committed → `references/gold-regeneration.md` |

Common upstream causes for `EXIT CODE != 0`:
- Input parse error → grep output for `*** ERROR ***`
- Unknown `type =` → tester unregistered / binary not built / wrong `app_name`; `make -j`, then `--yaml` to list registered types
- mooseError / divergence → framework prints stack
- Segfault → exit 139; rerun under debugger
- Stale capability registry → rebuild
- `Failed to import hit` → `$PYTHONPATH` interference or wrong env → `unset PYTHONPATH`, then activate the right env (`moose`, or the worktree's `moose-<feature>` env)

## TIMEOUT

Default `max_time = 300s` (per-spec `max_time = 600` or `MOOSE_TEST_MAX_TIME` env overrides):

1. Slow filesystem / underpowered box → bump `max_time` in spec.
2. Test legitimately takes minutes → mark `heavy = true` (only runs with `--heavy`).
3. Test doing too much → split via `prereq` chain or use `--check-input` for parse-only.
4. Valgrind timeouts are auto-doubled (NORMAL) or 6x'd (HEAVY).

## Race condition

`-j 1` passes, `-j 2` fails. Detect with:

    ./run_tests --re=foo --pedantic-checks -j 2

The harness snapshots mtimes pre/post-run, intersects modified-file sets between non-prereq parallel jobs, and prints "race partner" sets. Fix with `prereq = 'other_test'` or `working_directory = 'subdir'`.

## Failure under `--dbg` only

mooseAssert fired. Either fix the precondition (real bug) or the assert is stale (fix/remove). Don't paper over with `--devel`.

## Failure under `--recover` only

The harness clones each spec into part1 (`--test-checkpoint-half-transient`) + part2 (`--recover`). If part2 fails, the SUT has a real restart bug — state isn't being dumped/loaded. `recover = false` would hide it; only set when the test legitimately can't recover (steady solves, mesh-only, custom-postprocessor tests).

## Failure under `--valgrind`

Pass criterion: `ERROR SUMMARY: 0 errors` in output. Anything else → `MEMORY ERROR` (uninitialized read, leak, invalid free). Suppression file pre-loaded: `moose/python/TestHarness/suppressions/errors.supp` (silences OpenMPI noise). `valgrind = HEAVY` on a spec restricts it to `--valgrind-heavy` runs. `--valgrind-max-fails` defaults to 5.

## `UNKNOWN/INVALID CAPABILITIES` (ERROR status)

Binary's capability metadata is stale — common after pulling changes that touched `framework/src/base/CapabilityRegistry.C`. Rebuild the scope (`make -j 2`).

## What to skip vs revert when you cause a regression

- Small regression, tracked in an issue: `skip = 'refs #1234'` in the spec until fixed.
- Many tests across modules broken: revert the offending change.

There's no flaky-test allowlist mechanism; `skip` is the only path. CIVET may have its own retry layer at the CI level.
