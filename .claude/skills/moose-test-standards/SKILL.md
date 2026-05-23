---
name: moose-test-standards
description: MOOSE regression test standards — tests spec HIT syntax, SQA traceability fields, the Tester catalog (Exodiff/CSVDiff/RunException/...), directory layout, gold conventions, parametrization patterns (AD/non-AD, refinement, recover, multiapp), and anti-patterns. Auto-loads when authoring or editing a tests spec or .i test input in moose, blackbear, or isopod.
user-invocable: false
---

# MOOSE Regression Test Standards

Reference for authoring tests in `moose`, `moose/modules/<m>`, `blackbear`, `isopod`. Covers the `tests` HIT spec, the `.i` input, `gold/` outputs, and SQA traceability.

For *running* tests, debugging, or regenerating golds: see **moose-run-tests**.

## File layout

A test is a directory under `<repo>/test/tests/<area>/<feature>/`:

```
tests              # HIT spec
<feature>.i        # input(s)
gold/<...>         # reference outputs (required for diff Testers)
```

Test scope per repo:

| Scope | cd here | Binary |
|---|---|---|
| moose framework | `moose/test/` | `moose_test-opt` |
| module | `moose/modules/<m>/` | `<m>-opt` (production app) |
| blackbear | `blackbear/` | `blackbear-opt` |
| isopod | `isopod/` | `isopod-opt` |

Module tests run on the production `<m>-opt` binary. `<Module>TestApp.C` is a class that registers test-only objects (not a separate binary); downstream apps link it with `--allow-test-objects`.

## Spec HIT skeleton

```hit
[Tests]
  design = 'MyClass.md'
  issues = '#NNNN'
  [my_test]
    type = 'Exodiff'
    input = 'my_test.i'
    exodiff = 'my_test_out.e'
    requirement = 'The system shall <verb> <object>.'
  []
[]
```

- `[]` closes blocks (same as `[../]`; use `[]` in new tests).
- Strings: single or double quotes; adjacent quoted fragments concatenate.
- Lists: space-separated tokens in one quoted string.
- Six SQA params on `[Tests]` propagate to leaves: `design`, `issues`, `verification`, `validation`, `deprecated`, `collections`. **Tester params do NOT inherit** (no `[GlobalParams]` analog).

## SQA traceability

Required (or inherited):

| Field | Convention |
|---|---|
| `requirement` | Active voice + "shall". `'The system shall <verb> <object>.'` |
| `design` | Space-separated `.md` filenames; suffix-matched against `git ls-files`. |
| `issues` | `#NNNN`, `repo#NNNN`, or 6+ hex SHA. **`#000` is anti-pattern.** |

Optional: `detail` (sub-req text), `collections` (one of `FUNCTIONAL`/`USABILITY`/`PERFORMANCE`/`SYSTEM`/`FAILURE_ANALYSIS`), `verification`/`validation` (`.md`), `deprecated = true` (cannot coexist with other SQA fields).

### Hierarchical pattern (one requirement, multiple cases)

```hit
[ad]
  requirement = 'The system shall support Neumann BCs using AD'
  [test]
    type = 'Exodiff'; input = '1d.i'; exodiff = '1d_out.e'
    detail = 'using a generated mesh.'
  []
  [from_cubit]
    type = 'Exodiff'; input = 'cubit.i'; exodiff = 'cubit_out.e'
    detail = 'using an imported mesh.'
  []
[]
```

Children of a requirement-grouping parent must use `detail`, NOT their own `requirement`/`design`/`issues` (triggers `log_extra_*`).

## Universal Tester params

| Param | Use |
|---|---|
| `type`, `input` | Required. `input` is relative to spec dir. |
| `cli_args` | Mix MOOSE syntax (`Outputs/exodus=false`) + raw PETSc flags (`-pc_type hypre`). |
| `prereq` | Tests that must run first; `ALL` = run last. |
| `should_execute = false` | Skip exec, run post-checks only. |
| `max_parallel`/`min_parallel`, `max_threads`/`min_threads` | MPI / thread bounds. |
| `mesh_mode = REPLICATED`/`DISTRIBUTED` | Restrict mesh mode. |
| `valgrind = NONE`/`NORMAL`/`HEAVY` | Default `NONE`. |
| `heavy = true` | Only with `--heavy`. |
| `recover = false` | Opt out of recovery (steady, `--mesh-only`, `--check-input`, custom-pp). |
| `restep = false` | Opt out of restep. |
| `capabilities` | Boolean expr on build caps (`'petsc>=3.18 & vtk'`, `'method=opt'`). **Use this — NOT legacy `petsc_version`/`method`/`mumps`/`slepc_version`.** |
| `allow_test_objects = true` | Required for test-only objects on module/app binaries. |
| `working_directory` | chdir before running. |
| `max_time` | Wall seconds (default 300). |

`RunApp`-derived also: `expect_out`/`absent_out`/`match_literal`/`errors`/`allow_warnings`/`allow_unused`/`allow_deprecated`. `FileTester`-derived (Exodiff/CSVDiff/CheckFiles/ImageDiff/AnalyzeJacobian): `gold_dir` (default `gold`), `abs_zero` (1e-10), `rel_err` (5.5e-6).

## Tester catalog

| Tester | Use | Key params |
|---|---|---|
| `Exodiff` | Exodus diff vs gold | `exodiff = 'a.e b.e'`, `custom_cmp`, `partial`, `map` |
| `CSVDiff` | Postprocessor / VPP CSV | `csvdiff`, `override_columns`, `ignore_columns` |
| `JSONDiff` | Reporter JSON, mesh-only JSON | `jsondiff`, `ignored_regex_items` (auto-ignores app/version) |
| `XMLDiff` | VTK PVD/VTU (MFEM, IGA) | `xmldiff`, `ignored_items` |
| `CheckFiles` | Files (not) exist after run | `check_files`, `check_not_exists` |
| `ImageDiff` | PNG comparison | `imagediff`, `allowed = 0.98` |
| `RunApp` | Smoke test, stdout match | `expect_out`, `absent_out`, `errors` |
| `RunException` | Expected failure | `expect_err` or `expect_assert`, `expect_exit_code = 1`. Forces `recover/restep = false`. |
| `RunCommand` | Arbitrary shell, no MOOSE | `command` |
| `PetscJacobianTester` | `-snes_test_jacobian` | `ratio_tol`, `difference_tol`, `state`, `run_sim` |
| `AnalyzeJacobian` | Standalone Jacobian script | `expect_out`, `off_diagonal`. Forces `max_parallel = 1`. |
| `PythonUnitTest` | Python `unittest` | `input='test.py'`, `test_case` |
| `MMSTest` | MMS convergence | Extends `PythonUnitTest`; auto-requires pandas+matplotlib+`method=opt`. |
| `CSVValidationTester` | CSV vs measured data | `mean_limit`, `std_limit` |
| `SignalTester` | Signal mid-run | `signal = 'SIGUSR1'` |

**No `should_crash` on Exodiff** — that's `RunException`.

## Gold conventions

- No `Outputs/file_base` set → `gold/<input_basename>_out.<ext>`.
- `cli_args = 'Outputs/file_base=foo'` → `gold/foo.<ext>` (no `_out`).
- Symlink in `gold/` when two inputs share output.
- Multiapp: `<parent_base>_<multiapp_block><idx>.e`. Multilevel chains levels. List every level in `exodiff = '...'`.
- **Gold MUST be committed** — binary blobs and all.

## Input file conventions

- Tiny mesh (4x4 to 10x10).
- Small `num_steps` (5–20).
- `[Outputs]` last; `exodus = true` default.
- No explicit `Outputs/file_base` unless parametrizing.
- Mesh-only: `cli_args = '--mesh-only out.e'` + `recover = false`.
- `--check-input`: `recover = false`.

## Parametrization patterns

| Pattern | Mechanism |
|---|---|
| **AD vs non-AD** | Two inputs share one gold; noAD writes it, AD `prereq`s noAD; add `PetscJacobianTester` triple. |
| **Mesh refinement** | One input, sweep `Mesh/uniform_refine=N` + `Outputs/file_base` via `cli_args`. |
| **Time-integrator sweep** | `cli_args = 'Executioner/TimeIntegrator/type=Heun ... Outputs/file_base=heun_0'`; usually `restep = false`. |
| **PETSc sweep** | `cli_args` mixes MOOSE syntax + raw `-pc_type ...`. |
| **2D ↔ 3D** | `cli_args = 'Mesh/dim=3 Mesh/nz=1'`. |
| **Material swap** | `cli_args = 'Materials/foo/type=ADFoo'`. |

## Recover and restart

`recover = true` is default. The harness clones each spec into:
1. `<test>_part1` — `--test-checkpoint-half-transient`, no checks.
2. `<test>` — `--recover --recoversuffix cpr`, prereq part1.

You write only the "normal" run. **Opt out** (`recover = false`) for: steady, `--mesh-only`, `--check-input`, custom-pp, multiapp move.

`--recover` is incompatible with `--test-restep`. On the first leg of a manual checkpoint chain, set both `recover = false` and `restep = false`.

Manual restart: one spec runs steady; the next reads `Mesh/file = steady_out.e` and `Variables/u/initial_from_file_var = u`, with `prereq = steady_1`.

## Test-only objects

Live under `<app>/test/src/`, register to `<App>TestApp` (not `<App>App`). `--allow-test-objects` is OFF by default everywhere except `MooseTestApp`. Tests using test-only objects on module/blackbear/isopod must set `allow_test_objects = true`.

Module tests cannot use `MooseTestApp` test objects — only those from their own module + its `DEPEND_MODULES` chain.

## Reference test files

| Pattern | Reference |
|---|---|
| Simple Exodiff | `moose/test/tests/kernels/simple_transient_diffusion/` |
| Hierarchical req+detail | `moose/test/tests/bcs/ad_1d_neumann/tests` |
| AD vs non-AD + Jacobian | `moose/modules/solid_mechanics/test/tests/ad_elastic/tests` |
| Mesh refinement sweep | `moose/modules/level_set/test/tests/verification/1d_level_set_mms/tests` |
| Multiapp parent+sub | `moose/test/tests/multiapps/picard/` |
| Restart chain | `moose/test/tests/restart/restart_diffusion/tests` |
| Mesh-only + check-input | `moose/test/tests/mesh/mesh_only/tests` |
| Custom `.cmp` | `blackbear/test/tests/concrete_ASR_swelling/` |
| Capabilities gating | `blackbear/test/tests/neml_complex/tests` |
| `RunException` | `moose/test/tests/controls/time_periods/error/tests` |
| `PythonUnitTest`/`MMSTest` | `moose/test/tests/linearfvkernels/advection/tests` |

## Anti-patterns

- Missing `requirement`/`design`/`issues`, or `issues = '#000'`, or vague passive `requirement`.
- Per-leaf `requirement` when parent + N `detail` children would do.
- Child of grouping parent with its own `requirement`/`design`/`issues` (use `detail`).
- `design` pointing at deleted/renamed `.md`; grep specs when renaming docs.
- `detail` on top-level leaf (no parent requirement).
- `deprecated = true` paired with any other SQA field.
- Custom `collections` value outside the five standard ones.
- Duplicate `requirement` text across specs.
- Legacy `petsc_version`/`method`/`mumps` — use `capabilities`.
- Re-stating `design`/`issues` on children when `[Tests]` already inherits.
- Missing `recover = false` + `restep = false` on first leg of manual checkpoint chain.
- Fabricated `input` paths or uncommitted gold files.
- `should_crash` on Exodiff — use `RunException`.
- Default `max_time` (300s) on a long test — raise it or set `heavy = true`.
- Missing `allow_test_objects = true` for test-only objects on module/app binaries.
- Mismatched gold naming after `Outputs/file_base=` override (`<file_base>.<ext>`, not `_out`).

## Quick recipe

```
cd <app>/test
./run_tests --re=<my_test> -v --no-color -j 1   # verbose single test
./run_tests --check-input --re=<my_test>        # syntax-only
```
