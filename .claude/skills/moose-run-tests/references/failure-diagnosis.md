# Failure diagnosis

Reached from the routing table in `moose-run-tests/SKILL.md`. The status (`DIFF`, `FAIL`,
`TIMEOUT`, `RACE`, `ERROR`) plus the "Tester failed, reason: ..." line picks the section. Flags,
status codes, the skip-caveat decoder, and the gold procedure are in SKILL.md.

## DIFF (Exodiff/CSVDiff/JSONDiff mismatch)

    ./run_tests --re=<name> -v --no-color -j 1

The diff lines sit above the summary block. Then decide:

- Last-digit drift on a few variables: loosen `rel_err` / `abs_zero` in the spec. Regenerating
  would encode this machine's rounding into the gold.
- Large or structural diff, new behavior confirmed correct: regenerate gold (SKILL.md).
- Passes `-j 1` and fails `-p 2`: parallel non-determinism in the code, not a `mesh_mode` problem.
  Usual culprits: missing ghost-element access, a non-deterministic reduction, output order that
  depends on rank.

The exodiff invocation reproduces standalone:

    <MOOSE_DIR>/framework/contrib/exodiff/exodiff -m -F <abs_zero> -t <rel_err> gold/<file>.e <file>.e

For one bad CSV column, scope the override to that column instead of loosening globally:

    override_columns  = 'pp_name'
    override_rel_err  = '1e-4'
    override_abs_zero = '1e-8'

## FAIL (nonzero exit or output pattern)

| Reason | Cause |
|---|---|
| `EXIT CODE N != 0` | The app crashed, asserted, or failed to parse; the output above says which |
| `ERRMSG` | The app exited 0 but printed `ERROR`, `command not found`, or `terminate called after throwing...` |
| `EXPECTED ERROR/ASSERT/OUTPUT MISSING` | RunException's `expect_err` / `expect_assert` / `expect_out` did not match |
| `OUTPUT NOT ABSENT` | `absent_out` matched |
| `Application not found` | Binary missing; build the scope |
| `MEMORY ERROR` | valgrind run without `ERROR SUMMARY: 0 errors` in the output |
| `MISSING GOLD FILE` | New test with no committed gold; gold procedure in SKILL.md |

Repo-specific causes behind `EXIT CODE N != 0`:

- Input parse error: grep the output for `*** ERROR ***`.
- Unknown `type =`: the tester is unregistered, the binary is stale, or `app_name` is wrong. Rebuild,
  then `./<app>-opt --yaml` lists the registered types.
- `Failed to import hit`: `$PYTHONPATH` interference or the wrong env. `unset PYTHONPATH`, then run
  through `conda-run.sh` locally or inside the container shell on HPC.

## TIMEOUT

Default `max_time` is 300 s; `MOOSE_TEST_MAX_TIME` overrides it for a run. A test that legitimately
takes minutes gets `heavy = true` (runs only with `--heavy`) or a raised `max_time` in the spec
(`moose-test-standards`). Valgrind runs multiply the limit by 2 (`NORMAL`) or 6 (`HEAVY`).

## RACE

`-j 1` passes and `-j 2` fails. Detect with:

    ./run_tests --re=<name> --pedantic-checks -j 2

The harness snapshots file mtimes before and after each run, intersects the modified sets of
parallel jobs that have no `prereq` link, and prints the "race partner" sets. Fix with
`prereq = 'other_test'` or `working_directory = 'subdir'`.

## Failure only under `--dbg`

A `mooseAssert` fired. Fix the precondition (a real bug) or fix or remove a stale assert; `--devel`
is not a workaround.

## Failure only under `--recover`

The harness runs part1 (`--test-checkpoint-half-transient`) then part2 (`--recover`). A part2
failure is a real restart bug: state is not dumped or loaded. `recover = false` hides it and is
correct only for the cases `moose-test-standards` lists (steady, mesh-only, check-input,
custom-postprocessor, multiapp move).

## Failure only under `--valgrind`

Pass criterion: `ERROR SUMMARY: 0 errors`. Anything else is `MEMORY ERROR` (uninitialized read,
leak, invalid free). The suppression file `moose/python/TestHarness/suppressions/errors.supp`
silences OpenMPI noise. `valgrind = HEAVY` on a spec restricts it to `--valgrind-heavy` runs;
`--valgrind-max-fails` defaults to 5.

## `ERROR: UNKNOWN/INVALID CAPABILITIES`

The binary's capability metadata is stale, usually after pulling a change to
`framework/src/base/CapabilityRegistry.C`. Rebuild the scope.

## A regression you caused: skip or revert

- Small, tracked in an issue: `skip = 'refs #1234'` in the spec until fixed.
- Many tests across modules broken: revert the change.

There is no flaky-test allowlist; `skip` is the only mechanism. CIVET may retry at the CI level.
