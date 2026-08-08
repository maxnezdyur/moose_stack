---
name: moose-test-workflows
description: Router for MOOSE test procedures — carries the per-scope cd/build/run cheat sheet, pre-push routine, canary smoke, and build cascade rules inline, then routes by runner status (DIFF, FAIL, MISSING GOLD, TIMEOUT, RACE, SKIP, green-locally-red-on-CIVET) into references/ for failure diagnosis, gold regeneration, and CI/debugging. Auto-loads when running, debugging, or regenerating MOOSE tests; complements moose-run-tests (flag reference) and moose-test-standards (authoring).
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

## Routing table

Key on the status the harness printed. Read the named file before acting — every row resolves to one.

| You are holding | Read |
|---|---|
| `DIFF` — Exodiff/CSVDiff/JSONDiff mismatch, any size | `references/failure-diagnosis.md` — decides tiny drift (loosen tolerances) vs structural (regen); carries the standalone `exodiff` invocation and `override_columns` |
| `DIFF` confirmed structural, new behavior confirmed correct | `references/gold-regeneration.md` |
| `FAIL` — reason `MISSING GOLD FILE` | `references/gold-regeneration.md` |
| `FAIL` — any other reason (`EXIT CODE N != 0`, `ERRMSG`, `EXPECTED ERROR/ASSERT/OUTPUT MISSING`, `OUTPUT NOT ABSENT`, `Application not found`, `MEMORY ERROR`) | `references/failure-diagnosis.md` |
| `TIMEOUT` | `references/failure-diagnosis.md` |
| `RACE`, or passes `-j 1` and fails `-p 2` | `references/failure-diagnosis.md` |
| `ERROR` — `UNKNOWN/INVALID CAPABILITIES` | `references/failure-diagnosis.md` |
| Fails only under `--dbg` / `--recover` / `--valgrind` | `references/failure-diagnosis.md` |
| You caused a regression — skip vs revert | `references/failure-diagnosis.md` |
| `SKIP` with a `[bracket]` caveat | **moose-run-tests** skip-caveat decoder. Exit code 77 is silently converted to `SKIP "CAPABILITIES"`, so capability mismatches won't show as FAIL. |
| `SILENT` / `DELETED` | **moose-run-tests** status taxonomy |
| Green locally, red on CIVET | `references/ci-and-debugging.md` |
| Need the exact CI invocation, the host/container that ran it, or per-test timings | `references/ci-and-debugging.md` — `.previous_test_results.json` |
| Need to step through the app in gdb/lldb | `references/ci-and-debugging.md` |
| Writing or editing a `tests` spec or a `.i` input | **moose-test-standards** |
| Looking up a flag, env var, or status code | **moose-run-tests** |

**Gold regeneration has no automation.** There is no `--copy-gold` and no `--update-golds` — both are invented. Golds are copied by hand; follow `references/gold-regeneration.md` step by step.
