# Authoring inputs: Initial conditions (ICs)

Reach for this guide when you need to set the **starting field value** of a `[Variables]` or `[AuxVariables]` entry in a `.i` file. ICs are evaluated once before the first solve (or once per restart, if not overridden — see below) and are *not* residual contributions. If you want a residual term, see [kernels.md](./kernels.md). If you want a Dirichlet/Neumann constraint that pins the field every step, see [bcs.md](./bcs.md). If you need a brand-new IC class, that's C++ — see `../moose/ic-authoring.md` (if it exists) or the existing classes in `framework/src/ics/`.

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. Each catalog entry cites the **source header** (`<file>:<line of class>`) and one **canonical example .i** (`<file>:<line of the sub-block inside [ICs] / [FVICs]>`).

## When to use this (vs alternatives)

Three plumbing options exist for a starting value. Pick the lightest that does the job.

1. **`[Variables/u] initial_condition = 0.5`** — one-line shorthand for a *uniform constant scalar*. The framework synthesizes a `ConstantIC` under the hood. No `[ICs]` block needed. Use this whenever you want a single number for the whole domain. See [variables.md](./variables.md) for the full set of `[Variables]` shortcuts.
2. **Inline `[Variables/u/InitialCondition]` sub-block** — drops one IC object directly inside the variable definition. Useful when the IC type is set once and forgotten (e.g. a `BoundingBoxIC` paired with a fixed variable). Same parameters as the catalog entries below; just nested. Example: `test/tests/ics/bounding_box_ic/bounding_box_ic_test.i:18`.
3. **Top-level `[ICs]` block** — what this guide is mainly about. Required when you want **multiple ICs** on the same variable (block-restricted), or when you want to keep all initial-condition definitions together for readability. Required for `SolutionIC`, `FunctionScalarIC`, and most module-specific phase-field ICs.
4. **`[Variables/u] initial_from_file_var = u`** — restart from an Exodus file. No `[ICs]` entry needed; the variable is read out of the mesh's solution at `initial_from_file_timestep`. The mesh must be loaded with `FileMeshGenerator … use_for_exodus_restart = true` (FV) or with `file = restart_from.e` (FE). Example: `test/tests/ics/from_exodus_solution/nodal_part2.i:25`. Use **`SolutionIC`** + `SolutionUserObject` instead when the source mesh **differs** from the run's mesh (interpolation needed) or when you want to map only some variables.

FE vs FV — they live in **different blocks** and use different base classes:

- `[ICs]` populates FE (LAGRANGE / MONOMIAL / scalar / vector / array) variables.
- `[FVICs]` populates `MooseVariableFVReal` / `MooseLinearVariableFVReal` (cell-centered FV) variables. Using `ConstantIC` on an FV variable will silently no-op or error — use `FVConstantIC`.

Scalar variables (`family = SCALAR`) need scalar-specific ICs (`ScalarConstantIC`, `FunctionScalarIC`, `ScalarComponentIC`, `ScalarSolutionIC`); the regular `ConstantIC` rejects them.

## Catalog

### `[ICs]` — FE / scalar / vector / array initial conditions

#### Constant / scalar

##### `ConstantIC`

- Source: `framework/include/ics/ConstantIC.h:30`
- Example: `test/tests/ics/constant_ic/subdomain_constant_ic_test.i:21` (sub-block `[ic_u_1]`); inline form: `test/tests/ics/constant_ic/constant_ic_test.i:27`
- Single uniform value over the (block-restricted) domain.
- Required: `variable`, `value`.
- Useful: `block` (subdomain restriction — see "multiple ICs" below).

##### `ScalarConstantIC`

- Source: `framework/include/ics/ScalarConstantIC.h:17`
- Example: `test/tests/auxscalarkernels/constant_scalar_aux/constant_scalar_aux.i:37` (sub-block `[ic_x]`)
- Constant for a `family = SCALAR` variable. (`ConstantIC` cannot be used on scalars.)
- Required: `variable`, `value`.

##### `RandomIC`

- Source: `framework/include/ics/RandomIC.h:29`
- Example: `test/tests/ics/random_ic_test/random_ic_test.i:23` (sub-block `[u]`)
- Independent uniform random value at each DOF location. Reproducible across runs given the same `seed`.
- Required: `variable`.
- Useful: `min`, `max` (default 0/1), `seed`, `legacy_generator` (set `false` for new inputs), `distribution` (sample from a `[Distributions]` entry instead of uniform).

##### `BoundingBoxIC`

- Source: `framework/include/ics/BoundingBoxIC.h:22`
- Example: `test/tests/ics/bounding_box_ic/bounding_box_ic_test.i:18` (inline under `[Variables/u]`); top-level form: `test/tests/ics/from_exodus_solution/nodal_part2.i:35`
- Sets `inside` value within an axis-aligned box `(x1,y1,z1) - (x2,y2,z2)`, `outside` value elsewhere. Step-discontinuous — for diffuse interfaces, see phase-field `SmoothCircleIC` family.
- Required: `variable`, `x1`, `y1`, `x2`, `y2`, `inside`, `outside`.
- Useful: `z1`, `z2` (default 0), `int_width` (smoothed transition width — phase_field variants only).

##### `MultiBoundingBoxIC`

- Source: `modules/phase_field/include/ics/MultiBoundingBoxIC.h:19`
- Example: `modules/phase_field/test/tests/initial_conditions/MultiBoundingBoxIC2D.i:20` (sub-block `[c1]`)
- Multiple disjoint bounding boxes with per-box `inside` values, single `outside`. `c1` and `c2` are passed as flat coordinate lists; `nbox = len(inside)`.
- Required: `variable`, `c1` (list of corners), `c2` (list of opposite corners), `inside`, `outside`.

#### Function-driven

##### `FunctionIC`

- Source: `framework/include/ics/FunctionIC.h:17`
- Example: `test/tests/ics/function_ic/parsed_function.i:45` (sub-block `[u_ic]`)
- Sets the variable to `function(t=0, x, y, z)`. The most flexible option — pair with `ParsedFunction` for arbitrary algebra.
- Required: `variable`, `function`.

##### `FunctionScalarIC`

- Source: `framework/include/ics/FunctionScalarIC.h:16`
- Example: `test/tests/ics/function_scalar_ic/function_scalar_ic.i:29` (sub-block `[f]`)
- `Function` evaluated at the origin to set a SCALAR variable. Provide one function per scalar component if the variable has `order > FIRST`.
- Required: `variable`, `function`.

##### `FunctorIC`

- Source: `framework/include/ics/FunctorIC.h:18`
- Example: `test/tests/ics/functor_ic/test.i:21` (sub-block `[u_init]`)
- Evaluates an arbitrary functor (function name, variable name, postprocessor name, functor mat-prop) at each DOF. Use this when the source is a postprocessor or another variable that's already been initialized.
- Required: `variable`, `functor`.

##### `IntegralPreservingFunctionIC`

- Source: `framework/include/ics/IntegralPreservingFunctionIC.h:18`
- Example: `test/tests/ics/integral_preserving_function_ic/sinusoidal_z.i:28` (sub-block `[power]`)
- `FunctionIC` rescaled at setup so that `∫ value dV = magnitude` (typical for power distributions where the total is fixed but the shape is not).
- Required: `variable`, `function`, `magnitude`, `integral` (postprocessor that integrates `function`).

#### From a solution file

##### `SolutionIC`

- Source: `framework/include/ics/SolutionIC.h:19`
- Example: `test/tests/ics/solution_ic/solution_ic.i:35` (sub-block `[initial_cond_nl]`); paired UO at line 63
- Reads a variable's value from an existing Exodus solution via a `SolutionUserObject`. Handles cross-mesh interpolation. Use this — *not* `initial_from_file_var` — when the source mesh differs.
- Required: `variable`, `solution_uo` (name of a `SolutionUserObject` in `[UserObjects]`), `from_variable`.
- Useful: `block` (only initialize on a subdomain), `scale_factor`.

##### `ScalarSolutionIC`

- Source: `framework/include/ics/ScalarSolutionIC.h:19`
- Example: `test/tests/ics/solution_ic/solution_scalar_ic.i` (search `type = ScalarSolutionIC`)
- Same idea as `SolutionIC` but for SCALAR variables.
- Required: `variable`, `solution_uo`, `from_variable`.

#### Vector / array variants

##### `VectorConstantIC`

- Source: `framework/include/ics/VectorConstantIC.h:27`
- Example: `test/tests/ics/vector_constant_ic/vector_constant_ic.i:22` (sub-block `[A]`)
- Constant value for a vector variable (`LAGRANGE_VEC`, `NEDELEC_ONE`, `MONOMIAL_VEC`).
- Required: `variable`, `x_value`. Provide `y_value`, `z_value` for 2D/3D respectively.

##### `VectorFunctionIC`

- Source: `framework/include/ics/VectorFunctionIC.h:28`
- Example: `test/tests/ics/vector_function_ic/vector_function_ic.i:18` (sub-block `[ICs/A]`)
- Vector variable initialized from a `VectorFunction` (e.g. `ParsedVectorFunction`).
- Required: `variable`, `function`.

##### `ArrayConstantIC`

- Source: `framework/include/ics/ArrayConstantIC.h:19`
- Example: `test/tests/ics/array_constant_ic/array_constant_ic_test.i:26` (sub-block `[uic]`)
- Constant per-component for an array variable. `value` is a flat list of length `components`.
- Required: `variable`, `value`.

##### `ArrayFunctionIC`

- Source: `framework/include/ics/ArrayFunctionIC.h:16`
- Example: `test/tests/ics/array_function_ic/array_function_ic_test.i:41` (sub-block `[uic]`)
- One `Function` per component for an array variable.
- Required: `variable`, `function` (list, length = `components`).

##### `ScalarComponentIC`

- Source: `framework/include/ics/ScalarComponentIC.h:17`
- Example: `test/tests/ics/component_ic/component_ic.i:32` (sub-block `[v_ic]`)
- Per-component constant values for a multi-order SCALAR variable (`order = THIRD`, etc.).
- Required: `variable`, `values` (list, length = scalar order).

#### Spatial special-cases

##### `RampIC` (phase_field)

- Source: `modules/phase_field/include/ics/RampIC.h:18`
- Example: `modules/phase_field/test/tests/initial_conditions/RampIC.i:14` (inline under `[Variables/c]`)
- Linear ramp along x from `value_left` at `x = xmin` to `value_right` at `xmin + xlength`.
- Required: `variable`, `value_left`, `value_right`. Picks up `xmin` and `xlength` from the mesh by default.

##### `CoupledValueFunctionIC` (phase_field)

- Source: `modules/phase_field/include/ics/CoupledValueFunctionIC.h:16`
- Example: `modules/phase_field/test/tests/misc/coupled_value_function_ic.i:21` (inline under `[Variables/out]`)
- Initial value is `f(v1, v2, v3, v4)` where each `v_i` is a coupled variable (or 0). Lets one IC depend on values that other ICs have already computed.
- Required: `variable`, `function`, `v` (1-4 coupled variables).

> Note: There is no framework `CoupledIC` class — `CoupledValueFunctionIC` (phase_field) is the canonical "IC depends on another variable's IC" object.

### `[FVICs]` — finite-volume initial conditions

The block name *must* be `[FVICs]` (not `[ICs]`). Inline form inside `[Variables/u]` uses sub-block name `[FVInitialCondition]` instead of `[InitialCondition]`.

##### `FVConstantIC`

- Source: `framework/include/fvics/FVConstantIC.h:24`
- Example: `test/tests/fvics/constant_ic/constant_ic.i:38` (sub-block `[cu]` inside `[FVICs]`); inline form: `test/tests/fvics/constant_ic/constant_ic.i:13`
- Single uniform value for an FV variable. Same role as `ConstantIC` for FE.
- Required: `variable`, `value`.
- Useful: `block`.

##### `FVFunctionIC`

- Source: `framework/include/fvics/FVFunctionIC.h:26`
- Example: `test/tests/fvics/function_ic/parsed_function.i:28` (sub-block `[u_ic]`)
- Cell-centroid evaluation of a `Function` at `t = 0`.
- Required: `variable`, `function`.

> `FVICs` does not have its own `FunctorIC` / `RandomIC` / vector / array variants in the framework — most module-level FV needs are covered by composing `FVFunctionIC` with a `ParsedFunction`, or by reading from a file via `initial_from_file_var` + `use_for_exodus_restart = true` on the mesh (see `test/tests/fvics/file_ic/file_restart.i:9`).

## Cross-cutting concerns

### Multiple ICs on the same variable

Block-restrict each one. `ConstantIC` with `block = '1 2'` on subdomain set A and another `ConstantIC` with `block = '3'` on subdomain set B is the standard pattern; together they must cover every element where the variable lives or the uncovered cells stay at zero. Worked example: `test/tests/ics/constant_ic/subdomain_constant_ic_test.i:20`. Two ICs that overlap on the same subdomain are an input error.

### IC ordering and dependencies

ICs run in dependency order — if `CoupledValueFunctionIC` for variable `out` reads from variables `v1, v2`, MOOSE evaluates the ICs of `v1` and `v2` first. Cycles are detected and reported. Avoid coupling an IC to an `AuxVariable` that is itself updated by an `[AuxKernels]` entry running on `INITIAL` execute_on, unless you want that aux-kernel value as the source — execute order is `Variable ICs → AuxVariable ICs → AuxKernels (INITIAL) → Postprocessors (INITIAL)`.

### Eigen problems overwrite ICs

For `EigenProblem` / `NonlinearEigen` executioners the eigensolver normalizes (and often re-seeds) the eigenvector at the first iteration, so any `[ICs]` you set will be overwritten. Set `[Problem] type = EigenProblem … initial_condition_for_eigenvalue` only when you specifically need a non-default starting guess; for most eigen runs, an IC is decorative and can be omitted.

### Restart from checkpoint vs explicit IC

`MultiApps`-style or `--recover` restarts from a MOOSE **checkpoint** ignore `[ICs]` by default — the saved solution wins. Restarting from an **Exodus** file is opt-in (either `initial_from_file_var` on the variable or `SolutionIC` + `SolutionUserObject`) and *not* mutually exclusive with `[ICs]`. To force the IC to run anyway when other variables are restarting from file, add `[Problem] allow_initial_conditions_with_restart = true` (see `test/tests/ics/from_exodus_solution/nodal_part2.i:48`).

### Block / subdomain restriction

`block` is supported on every framework IC. It is the only practical way to assemble a non-uniform initial state from a few simple objects (constant in region A, function-driven in region B). `boundary` is *not* a typical IC parameter — boundary-only initial values usually mean you actually want a `[BCs]` entry, not an IC.

### Inline vs top-level

The inline `[Variables/u/InitialCondition]` form and the top-level `[ICs/u_ic] variable = u` form produce identical objects; pick whichever keeps the file readable. Mixing the two for the *same* variable is an input error. The top-level form is required as soon as you need block-restricted multiple ICs.

## Minimal scaffold

```hit
[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 2
    nx = 10
    ny = 10
  []
[]

[Variables]
  [u]
  []
  [v]
    initial_condition = 0.5  # shorthand — equivalent to ConstantIC value=0.5
  []
[]

[Functions]
  [bump]
    type = ParsedFunction
    expression = 'exp(-((x-0.5)^2 + (y-0.5)^2)/0.05)'
  []
[]

[ICs]
  [u_const]
    type = ConstantIC
    variable = u
    value = 1.0
    block = 0
  []
  [u_bump]
    # Demonstrate replacing the line above with a function-driven IC instead;
    # in real input keep only one IC per (variable, block) intersection.
    type = FunctionIC
    variable = u
    function = bump
    block = 0
  []
[]

[Kernels]
  [diff]
    type = ADDiffusion
    variable = u
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
[]
```

FV variant — note the `[FVICs]` block name and `MooseVariableFVReal` type:

```hit
[Variables]
  [u]
    type = MooseVariableFVReal
  []
[]

[Functions]
  [bump]
    type = ParsedFunction
    expression = 'exp(-((x-0.5)^2 + (y-0.5)^2)/0.05)'
  []
[]

[FVICs]
  [u_ic]
    type = FVFunctionIC
    variable = u
    function = bump
  []
[]
```
