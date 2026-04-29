---
name: moose-test-standards
description: MOOSE regression test standards — tests spec HIT syntax, SQA traceability fields, the Tester catalog (Exodiff/CSVDiff/RunException/...), directory layout, gold conventions, parametrization patterns (AD/non-AD, refinement, recover, multiapp), and anti-patterns. Auto-loads when authoring or editing a tests spec or .i test input in moose, blackbear, or isopod.
user-invocable: false
---

# MOOSE Regression Test Standards

Reference for authoring regression tests in `moose`, `moose/modules/<m>`, `blackbear`, and `isopod`. Covers the `tests` HIT spec, the companion `.i` input, the `gold/` outputs, and SQA traceability. Apply whenever editing a `tests` spec or test input.

For *running* tests, debugging failures, or regenerating golds, see the **moose-run-tests** skill.

## File location

A regression test is a directory under `<repo>/test/tests/<area>/<feature>/` (or `<repo>/modules/<m>/test/tests/...`) containing:

```
tests              # HIT spec — required
<feature>.i        # MOOSE input — required (one or more)
gold/              # reference outputs — required when using a diff-style Tester
  <feature>_out.e  # exodus / csv / json / png reference
mesh.e             # optional committed mesh
*.cmp              # optional custom Exodiff comparison file
```

Test scope per repo (where you `cd` and what binary the harness invokes):

| Scope | cd here | Binary | testroot |
|---|---|---|---|
| moose framework | `moose/test/` | `moose_test-opt` | `moose/test/testroot` (`app_name = moose_test`) |
| module | `moose/modules/<m>/` | `<m>-opt` (production app — also runs tests) | `moose/modules/<m>/testroot` (`app_name = <m>`) |
| blackbear | `blackbear/` | `blackbear-opt` (production) | none — `run_tests` passes `app_name='blackbear'` directly |
| isopod | `isopod/` | `isopod-opt` (production) | `isopod/testroot` |

The harness walks upward from CWD to find `testroot`, or falls back to the `app_name` baked into the `run_tests` shim.

**`<Module>TestApp.C` exists** at `moose/modules/<m>/test/src/base/` for many modules — but it's NOT a separate binary. It's a class that registers test-only objects, used when downstream apps (combined, blackbear, isopod) link the module with `--allow-test-objects`. Module tests run on the production `<m>-opt` binary.

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

- One top-level `[Tests]` block.
- Children of `[Tests]` are either **leaf tests** (have `type =`) or **requirement-grouping parents** (have `requirement =`, contain leaf children with `detail =`).
- `[]` and `[../]` close blocks identically. New tests use `[]`.
- Strings: single or double quotes. Adjacent quoted fragments concatenate (`'foo ' 'bar'` → `foo bar`) — used for long requirement lines.
- Lists: space-separated tokens in one quoted string. `issues = '#1234 #5678'`.

### Auto-inheritance from `[Tests]`

Six SQA params declared on `[Tests]` propagate to every leaf as defaults: `design`, `issues`, `verification`, `validation`, `deprecated`, `collections`. Children can override locally.

**Tester params (`type`, `input`, `cli_args`, `prereq`, `max_parallel`, etc.) do NOT inherit.** No `[GlobalParams]` analog exists for tests.

## SQA traceability fields

Required on every test (or inherited from `[Tests]`/parent):

| Field | Convention |
|---|---|
| `requirement = '...'` | Active voice, present tense, "shall" wording. `'The system shall <verb> <object>.'` Subject can be `'PorousFlow shall'`, `'BlackBear shall'`, etc. |
| `design = 'Foo.md Bar.md'` | Space-separated `.md` filenames; suffix-matched against `git ls-files`. |
| `issues = '#1234 #5678'` | `#NNNN` (same repo), `repo#NNNN` (cross-repo), or 6+ hex SHA. **`#000` is anti-pattern** — cite a real PR. |

Optional:

| Field | Use |
|---|---|
| `detail = '...'` | Sub-requirement text on a child of a requirement-grouping parent (see hierarchical pattern below). |
| `collections = 'FUNCTIONAL ...'` | One or more of `FUNCTIONAL`, `USABILITY`, `PERFORMANCE`, `SYSTEM`, `FAILURE_ANALYSIS`. Anything else fails the SQA check. Defaults to functional; usually only set for non-functional categories. |
| `verification = 'foo.md'` / `validation = 'foo.md'` | V&V doc pointers. |
| `deprecated = true` | Excludes test from SQA. Cannot coexist with any other SQA field. |

### Hierarchical pattern (parent + `detail` children)

Use when one requirement is exercised by several test cases:

```hit
[Tests]
  issues = '#1654'
  design = 'bcs/ADNeumannBC.md'
  [ad]
    requirement = 'The system shall support Neumann boundary conditions using AD for a 1D problem'
    [test]
      type = 'Exodiff'
      input = '1d_neumann.i'
      exodiff = '1d_neumann_out.e'
      detail = 'using a generated mesh.'
    []
    [from_cubit]
      type = 'Exodiff'
      input = 'from_cubit.i'
      exodiff = 'from_cubit_out.e'
      detail = 'using an imported mesh.'
    []
    [jac]
      type = 'PetscJacobianTester'
      input = '1d_neumann.i'
      run_sim = True
      ratio_tol = 1e-7
      detail = 'and shall produce the exact Jacobian.'
    []
  []
[]
```

The RTM renders this as: "The system shall support Neumann boundary conditions … (a) using a generated mesh, (b) using an imported mesh, (c) and shall produce the exact Jacobian."

**Children of a requirement-grouping parent must use `detail`, not their own `requirement`/`design`/`issues`/`collections` — those trigger `log_extra_*` errors.**

## Universal Tester parameters

From the base `Tester` class. Apply to every `type =`.

| Param | Use |
|---|---|
| `type` | Tester class name (Exodiff, CSVDiff, RunException, etc.). Required. |
| `input` | The `.i` file (relative to spec dir). |
| `cli_args` | Extra CLI args. Mix MOOSE syntax (`Outputs/exodus=false`) with raw PETSc flags (`-pc_type hypre`). |
| `prereq` | Other test names that must run first. `prereq = ALL` runs last. Use `parent/child` for nested specs. |
| `should_execute = false` | Skip the executable invocation but still run post-checks. Used to chain a tester onto a previous run. |
| `max_parallel` / `min_parallel` | MPI rank bounds. `max_parallel = 1` forces serial. |
| `max_threads` / `min_threads` | Thread bounds. `max_threads = 1` disables threading. |
| `mesh_mode = REPLICATED` / `DISTRIBUTED` | Restrict to one mesh mode. |
| `valgrind = NONE` / `NORMAL` / `HEAVY` | Default `NONE`. |
| `heavy = true` | Only run with `--heavy`. |
| `recover = false` | Opt out of recovery split. Required for steady solves, `--mesh-only`, `--check-input`, custom-postprocessor tests. |
| `restep = false` | Opt out of restep mode. Often paired with `recover = false` on checkpoint chains. |
| `capabilities = '...'` | Boolean expression on build capabilities. **Use this** instead of legacy `petsc_version`/`method`/`mumps`/`slepc_version` (those still parse but are deprecated shims). Examples: `'method=opt'`, `'petsc>=3.18 & vtk'`, `'mfem & platform=linux'`, `'!installation_type=relocated'`. |
| `allow_test_objects = true` | Pass `--allow-test-objects` to the binary (needed when using objects registered to `<App>TestApp` rather than `<App>App`). |
| `working_directory = '../sub_app'` | chdir before running. |
| `max_time = 600` | Wall-clock seconds. Default 300. |

`RunApp`-derived testers also accept: `expect_out` (regex), `absent_out`, `match_literal`, `delete_output_before_running`, `errors`, `compute_devices`, `allow_warnings`/`allow_unused`/`allow_override`/`allow_deprecated`. `FileTester`-derived (Exodiff, CSVDiff, CheckFiles, ImageDiff, AnalyzeJacobian) add `gold_dir` (default `gold`), `abs_zero` (1e-10), `rel_err` (5.5e-6).

## Tester catalog — when to use each

| Tester | Use | Key params |
|---|---|---|
| `Exodiff` | Exodus output diff vs gold (most physics tests) | `exodiff = 'a.e b.e'` (list), `custom_cmp = '*.cmp'`, `partial`, `map`, `abs_zero`, `rel_err` |
| `CSVDiff` | Postprocessor / VPP CSV diff | `csvdiff = 'a.csv'`, `override_columns`/`override_rel_err`/`override_abs_zero`, `ignore_columns`, `custom_columns` |
| `JSONDiff` | Reporter JSON, mesh-only JSON dumps | `jsondiff = 'a.json'`, `ignored_regex_items`, `keep_system_information`. Auto-ignores app/version metadata. |
| `XMLDiff` | VTK PVD/VTU (MFEM, IGA), checkpoint XML | `xmldiff = 'a.pvd a.vtu'`, `ignored_items` |
| `CheckFiles` | Files must (not) exist after run | `check_files`, `check_not_exists`, `file_expect_out` |
| `ImageDiff` | PNG comparison (chigger/VTK rendering) | `imagediff = 'a.png'`, `allowed = 0.98`. `display_required = false` by default. |
| `RunApp` | Smoke test, stdout-pattern check | `expect_out` (regex), `absent_out`, `errors`, `match_literal` |
| `RunException` | Run expected to fail with a specific message | `expect_err` (or `expect_assert`), `expect_exit_code = 1`. Forces `recover/restep = false`. Requires either `expect_err` or `expect_assert`. |
| `RunCommand` | Arbitrary shell command (no MOOSE app) | `command = '...'` |
| `PetscJacobianTester` | Jacobian validation via `-snes_test_jacobian` | `ratio_tol`, `difference_tol`, `state`, `run_sim`, `only_final_jacobian`. Auto adds `method=opt`. |
| `AnalyzeJacobian` | Jacobian via standalone analysis script | `expect_out`, `resize_mesh`, `mesh_size`, `off_diagonal`. Forces `max_parallel = 1`. |
| `PythonUnitTest` | Python `unittest` module | `input = 'test.py'`, `test_case`, `buffer`, `separate` |
| `MMSTest` | MMS convergence (extends PythonUnitTest) | Same as PythonUnitTest. Auto-requires pandas+matplotlib + `method=opt`. |
| `CSVValidationTester` | Compare CSV against measured data (statistical) | `mean_limit`, `std_limit`, `err_type` |
| `SignalTester` | Send Unix signal mid-run | `signal = 'SIGUSR1'` |
| `SchemaDiff` | Base for JSONDiff/XMLDiff. Direct use rare. | |

**`Exodiff` has no `should_crash` param** — that's `RunException`.

## Directory layout and gold conventions

Single-test dir:

```
my_feature/
  my_feature.i
  tests
  gold/my_feature_out.e
```

AD/non-AD pair (shared gold):

```
ad_elastic/
  finite_elastic-noad.i      # writes the gold
  finite_elastic.i           # AD version, same gold
  tests                      # noAD has no prereq; AD has prereq=...-noad + jacobian tester
  gold/finite_elastic_out.e
```

Multiapp:

```
picard/
  picard_parent.i
  picard_sub.i
  tests
  gold/picard_parent_out.e
  gold/picard_parent_out_sub0.e
```

Sub-app exodus naming: `<parent_base>_<multiapp_block_name><idx>.e`. Multilevel: `<parent>_<L1name>-<idx>_<L2name>-<idx>.e`. Each level needs a gold. List them all in `exodiff = '...'`.

### Gold naming rule

- No `Outputs/file_base` set → gold is `gold/<input_basename>_out.<ext>`.
- `cli_args = 'Outputs/file_base=foo'` → gold is `gold/foo.<ext>` (no `_out`).
- Symlink in `gold/` when two inputs produce identical output.

## Input file conventions for tests

- Tiny `GeneratedMesh` (10x10 typical, often 4x4).
- Small `Executioner/num_steps` (5–20 for transients, fewer for modules).
- `[Outputs]` last, `exodus = true` (or `csv`/`json`).
- No explicit `Outputs/file_base` unless parametrizing.
- Mesh-only: drop `[Variables]/[Kernels]/[Executioner]`, run via `cli_args = '--mesh-only out.e'`, set `recover = false`.
- `--check-input` for syntax-only validation; set `recover = false`.

## Parametrization patterns

### AD vs non-AD pair

Two sibling inputs sharing one gold. noAD runs first (writes gold); AD runs with `prereq` and must match. Add a `PetscJacobianTester` triple. See `moose/modules/solid_mechanics/test/tests/ad_elastic/tests` for the canonical 9× repetition.

### Mesh refinement convergence

One input, multiple `cli_args`:

```hit
[level_00]
  type = CSVDiff
  input = mms.i
  csvdiff = mms_00.csv
  cli_args = 'Mesh/uniform_refine=0 Outputs/file_base=mms_00'
[]
[level_01]
  cli_args = 'Mesh/uniform_refine=1 Outputs/file_base=mms_01'
  ...
```

### Time-integrator sweep

```hit
[heun_0]
  cli_args = 'Executioner/TimeIntegrator/type=Heun Executioner/dt=0.00390625 Outputs/file_base=heun_0'
  exodiff = 'heun_0.e'
  restep = false
[]
```

### PETSc options sweep

`cli_args` mixes `Executioner/automatic_scaling=true` (MOOSE syntax) with `-pc_type hypre` (raw PETSc).

### 2D vs 3D

`cli_args = 'Mesh/dim=3 Mesh/nz=1'` flips a 2D input.

### Material type swap

`cli_args = 'Materials/foo/type=ADFoo'` — same input, different material.

## Recover and restart

`recover = true` is the **default**. The harness automatically clones each spec into:

1. `<test>_part1` — runs with `--test-checkpoint-half-transient`, no checks.
2. `<test>` — runs with `--recover --recoversuffix cpr`, prereq part1, full checks. `delete_output_before_running = false`.

You write only the "normal" run; the harness adds the recover legs.

**Opt out** with `recover = false` for: steady solves, `--mesh-only` runs, `--check-input` runs, custom-postprocessor tests, multiapp move tests, anything where mid-transient checkpoint is malformed.

`--recover` and `--test-restep` are incompatible. On the first leg of a manual checkpoint chain, set both `recover = false` and `restep = false`.

### Manual restart chain (separate inputs)

```hit
[steady_1]
  type = Exodiff
  input = restart_steady.i
  exodiff = steady_out.e
[]
[trans_from_steady]
  type = Exodiff
  input = restart_transient.i
  exodiff = out.e
  prereq = steady_1
[]
```

The transient input reads `Mesh/file = steady_out.e` and `Variables/u/initial_from_file_var = u`. `prereq` orders execution; previous output stays on disk.

## Test-only objects

Test-only objects live under `<app>/test/src/` and register to `<App>TestApp` (not `<App>App`).

**`--allow-test-objects` is OFF by default everywhere except `MooseTestApp`** (which uses `--disallow-test-objects` to opt out). Module/blackbear/isopod tests that need test-only objects must set `allow_test_objects = true` in the spec.

**Module tests cannot use `MooseTestApp` test-only objects** — module binaries don't link the moose_test object library. They can only use test objects from their own module (and its `DEPEND_MODULES` chain).

## Reference test files — read one before authoring

| Pattern | Reference |
|---|---|
| Simple Exodiff kernel test | `moose/test/tests/kernels/simple_transient_diffusion/{tests,simple_transient_diffusion.i,gold/}` |
| Multiple specs, shared input | `moose/test/tests/kernels/simple_transient_diffusion/tests` (8 tests, 3 inputs) |
| Hierarchical requirement+detail | `moose/test/tests/bcs/ad_1d_neumann/tests` |
| AD vs non-AD pair + Jacobian | `moose/modules/solid_mechanics/test/tests/ad_elastic/tests` |
| Mesh refinement sweep | `moose/modules/level_set/test/tests/verification/1d_level_set_mms/tests` |
| Time-integrator sweep | `moose/test/tests/time_integrators/convergence/tests` |
| Multiapp parent + sub | `moose/test/tests/multiapps/picard/{tests,picard_parent.i,picard_sub.i}` |
| Multilevel multiapp | `moose/test/tests/multiapps/picard_multilevel/2level_picard/tests` |
| Restart chain | `moose/test/tests/restart/restart_diffusion/tests` |
| Recover with checkpoint | `moose/modules/porous_flow/test/tests/recover/tests` |
| Mesh-only + check-input | `moose/test/tests/mesh/mesh_only/tests` |
| Custom Exodiff `.cmp` | `blackbear/test/tests/concrete_ASR_swelling/{tests,asr_confined.cmp}` |
| Capabilities gating | `blackbear/test/tests/neml_complex/tests` (`capabilities = 'neml'`) |
| `RunException` | `moose/test/tests/controls/time_periods/error/tests` |
| `PythonUnitTest` / `MMSTest` | `moose/test/tests/linearfvkernels/advection/tests` |
| SignalTester | `moose/test/tests/misc/signal_handler/tests` |
| Optimization multiapp (isopod) | `isopod/test/tests/optimizationreporter/boundary_measurement/tests` |

## Anti-patterns

1. **Missing `requirement`/`design`/`issues`** — fails SQA check.
2. **`issues = '#000'`** — passes regex but is meaningless. Cite a real PR.
3. **Vague `requirement`** — passive voice, no "shall", unclear subject. Use `<Subject> shall <verb> <object>`.
4. **Per-leaf `requirement`** when one parent + N `detail` children would do — triggers `log_duplicate_requirement`.
5. **Child of requirement-grouping parent has its own `requirement`/`design`/`issues`** — triggers `log_extra_*`. Use `detail`.
6. **`design` pointing at a deleted/renamed `.md`** — fails `log_design_files`. Grep specs when renaming docs.
7. **`detail` on a top-level leaf** (no parent requirement) — `log_top_level_detail`.
8. **`deprecated = true` paired with any other SQA field** — pick one.
9. **Custom `collections` value** outside `FUNCTIONAL/USABILITY/PERFORMANCE/SYSTEM/FAILURE_ANALYSIS`.
10. **Same `requirement` text in two specs** — `log_duplicate_requirement`. Rephrase.
11. **Legacy `petsc_version =`/`method =`/`mumps =`** — use `capabilities = '...'` instead.
12. **Re-stating `design`/`issues` on every child when `[Tests]` already inherits them** — wasted lines, drift risk.
13. **Forgetting `recover = false` + `restep = false`** on the first leg of a manual checkpoint chain.
14. **`block=` on `!listing` in test docs** — that's a doc concern, not a test concern. (Mentioned only because it surfaces in spec markdown.)
15. **Fabricated `input` paths** — input is relative to the spec dir; don't invent paths. If no real test exists, write the input first.
16. **Gold file not committed** — gold MUST be in git for the test to pass on a clean checkout. Binary blobs and all.
17. **`should_crash`** on Exodiff — doesn't exist. Use `RunException`.
18. **`max_time` left default for a long test** — default 300s. Either raise it or set `heavy = true`.
19. **Missing `allow_test_objects = true`** when using test-only objects on a module/app binary.
20. **Mismatched gold naming after `Outputs/file_base=` override** — gold becomes `<file_base>.<ext>`, not `<file_base>_out.<ext>`.

## Build / preview

See the **moose-run-tests** skill for `./run_tests` flags, gold regen, debugging, and CIVET.

Quick recipe:

    cd <app>/test
    ./run_tests --re=<my_test> -v --no-color -j 1   # run one test verbosely
    ./run_tests --check-input --re=<my_test>        # syntax-only validation
