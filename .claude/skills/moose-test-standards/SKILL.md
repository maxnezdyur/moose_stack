---
name: moose-test-standards
description: MOOSE regression test standards: tests spec syntax, SQA traceability fields, the Tester catalog (Exodiff, CSVDiff, RunException, ...), gold naming, .i input conventions, parametrization patterns, and anti-patterns. Loads when authoring or editing a tests spec or a .i test input in moose, blackbear, or isopod.
user-invocable: false
---

# MOOSE Regression Test Standards

Authoring conventions for the `tests` HIT spec, the `.i` input, `gold/` outputs, and SQA traceability in `moose`, `moose/modules/<m>`, `blackbear`, and `isopod`. Running, diagnosing, and regenerating golds is the `moose-run-tests` skill.

## File layout

A test is a directory under `<repo>/test/tests/<area>/<feature>/` holding `tests` (the HIT spec), one or more `.i` inputs, and `gold/` (reference outputs, required by every diff Tester).

## Spec skeleton

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

A block opens with `[name]` and closes with `[]`. The legacy `[./name]` / `[../]` form parses identically, but new blocks do not use it; `.claude/hooks/check-added-lines.sh` flags it on added lines of a `tests` file.

About 800 existing specs still use the legacy form. When you add a block to one, write the new block in modern syntax and leave the legacy siblings as they are: converting the file inflates the diff and destroys blame. Mixed-syntax files are the expected outcome (`moose/modules/chemical_reactions/test/tests/aqueous_equilibrium/tests` is the canonical example) and match upstream's opportunistic migration. A rename is a new block: re-typing `[./old]` as `[./new]` re-introduces the legacy form.

Six SQA params set on `[Tests]` propagate to every leaf: `design`, `issues`, `verification`, `validation`, `deprecated`, `collections`. Tester params do not inherit; there is no `[GlobalParams]` analog.

## SQA traceability

Required on every leaf, directly or inherited:

| Field | Convention |
|---|---|
| `requirement` | One unambiguous "shall" sentence of observable behavior: `'The <system\|app> shall <verb> <object> [<condition>].'` Error tests: `'shall report an error when <condition>'`. "will" and "should" are wrong. Canonical guidance: `moose/framework/doc/content/sqa/what_is_a_requirement.md`. |
| `design` | Space-separated `.md` filenames, suffix-matched against `git ls-files`. |
| `issues` | `#NNNN`, `repo#NNNN`, or a 6+ hex SHA. `#000` is an anti-pattern. A new test cites the issue that motivated it (the PR's issue) on its own leaf; an inherited file-level `issues` alone is not sufficient. Append to an existing list (`'#7840 #33415'`) rather than replacing it. |

Optional: `detail` (sub-requirement text), `collections` (one of `FUNCTIONAL`, `USABILITY`, `PERFORMANCE`, `SYSTEM`, `FAILURE_ANALYSIS`), `verification` and `validation` (`.md`), `deprecated = true` (cannot coexist with the other SQA fields).

### Hierarchical pattern (one requirement, several cases)

```hit
[ad]
  requirement = 'The system shall support Neumann BCs using AD'
  [test]
    type = 'Exodiff'
    input = '1d.i'
    exodiff = '1d_out.e'
    detail = 'using a generated mesh.'
  []
  [from_cubit]
    type = 'Exodiff'
    input = 'cubit.i'
    exodiff = 'cubit_out.e'
    detail = 'using an imported mesh.'
  []
[]
```

Children of a requirement-grouping parent carry `detail` and no `requirement`, `design`, or `issues` of their own (those trigger `log_extra_*`).

## Tester params that authors get wrong

- `capabilities = '<expr>'` gates on build capabilities (`'petsc>=3.18 & vtk'`, `'method=opt'`). The legacy `petsc_version`, `method`, `mumps`, and `slepc_version` params are not used in new tests.
- `allow_test_objects = true` is required for test-only objects on module, blackbear, and isopod binaries.
- `recover = true` is the default. Set `recover = false` for steady, `--mesh-only`, `--check-input`, custom-postprocessor, and multiapp-move tests. `restep = false` opts out of restep. `--recover` and `--test-restep` are incompatible, so the first leg of a manual checkpoint chain sets both to false.
- `RunApp`-derived Testers also take `expect_out`, `absent_out`, `match_literal`, `errors`, `allow_warnings`, `allow_unused`, `allow_deprecated`. `FileTester`-derived Testers (Exodiff, CSVDiff, CheckFiles, ImageDiff, AnalyzeJacobian) take `gold_dir` (default `gold`), `abs_zero` (1e-10), `rel_err` (5.5e-6).

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
| `MMSTest` | MMS convergence | Extends `PythonUnitTest`; auto-requires pandas, matplotlib, `method=opt`. |
| `CSVValidationTester` | CSV vs measured data | `mean_limit`, `std_limit` |
| `SignalTester` | Signal mid-run | `signal = 'SIGUSR1'` |

There is no `should_crash` on Exodiff; an expected failure is a `RunException`.

## Gold conventions

- No `Outputs/file_base` set: `gold/<input_basename>_out.<ext>`.
- `cli_args = 'Outputs/file_base=foo'`: `gold/foo.<ext>` (no `_out`).
- Two inputs that share output share one gold through a symlink inside `gold/`.
- Multiapp: `<parent_base>_<multiapp_block><idx>.e`. Multilevel chains the levels. List every level in `exodiff = '...'`.
- Gold files are committed, binary blobs included.

## Input file conventions

- Nearly commentless. No comments on the first lines of a `.i`, and no header block of any size. Rationale (physics, derivation, expected result, path-dependence essays, literature citations, ASCII matrices, why the test exists) belongs in the spec's `requirement`/`detail` (and the class `.md`), not the input; a non-obvious tolerance or mutation guard is explained in the `tests` spec next to the parameter it justifies.
- Tiny mesh (4x4 to 10x10).
- Small `num_steps` (5-20).
- `[Outputs]` last; `exodus = true` default.
- No explicit `Outputs/file_base` unless parametrizing.
- Mesh-only: `cli_args = '--mesh-only out.e'` plus `recover = false`.
- `--check-input`: `recover = false`.

## Parametrization patterns

| Pattern | Mechanism |
|---|---|
| AD vs non-AD | Two inputs share one gold; noAD writes it, AD `prereq`s noAD; add a `PetscJacobianTester` triple. |
| Mesh refinement | One input, sweep `Mesh/uniform_refine=N` plus `Outputs/file_base` via `cli_args`. |
| Time-integrator sweep | `cli_args = 'Executioner/TimeIntegrator/type=Heun ... Outputs/file_base=heun_0'`; usually `restep = false`. |
| PETSc sweep | `cli_args` mixes MOOSE syntax (`Outputs/exodus=false`) and raw PETSc flags (`-pc_type hypre`). |
| 2D vs 3D | `cli_args = 'Mesh/dim=3 Mesh/nz=1'`. |
| Material swap | `cli_args = 'Materials/foo/type=ADFoo'`. |
| Restart chain | One spec runs steady; the next reads `Mesh/file = steady_out.e` and `Variables/u/initial_from_file_var = u` with `prereq = <steady test>`. |

## Test-only objects

Test-only objects live under `<app>/test/src/` and register to `<App>TestApp`, not `<App>App`. `<Module>TestApp.C` is a class compiled into the production `<m>-opt` binary, not a separate binary. `--allow-test-objects` is off by default everywhere except `MooseTestApp`, hence `allow_test_objects = true` on module, blackbear, and isopod specs. Module tests can use only the test objects of their own module and its `DEPEND_MODULES` chain, not those of `MooseTestApp`.

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

## Anti-patterns beyond the rules above

- Per-leaf `requirement` when a parent plus N `detail` children would do; `detail` on a top-level leaf with no parent requirement.
- Duplicate `requirement` text across specs; re-stating `design`/`issues` on children the `[Tests]` block already covers.
- Vague, passive `requirement` wording.
- `design` pointing at a deleted or renamed `.md`; grep the specs whenever renaming doc pages.
- Fabricated `input` paths.
- A `RunException` test cementing a restriction a small code change would remove; fix the code instead of testing the limitation as intended behavior.
