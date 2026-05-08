# Authoring inputs: Variables and AuxVariables

Reach for this guide when you need to declare a field in a `.i` file under `[Variables]` (the unknowns the solver actually solves for) or `[AuxVariables]` (auxiliary fields populated by an `[AuxKernels]` entry, by a transfer, or by an IC). Pick **family / order / type** to match the discretization the kernels expect — an FE Lagrange variable cannot consume `[FVKernels]`, an FV variable cannot consume `[Kernels]`, and a `LinearFV` variable cannot consume Newton-style residuals.

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. Each entry cites the **C++ class header** (`<file>:<line of class>`) and one **canonical example .i** (`<file>:<line of the sub-block>`). The HIT-level params (`family`, `order`, `scaling`, `initial_condition`, `eigen`, `fv`, `components`, `block`, `outputs`) are gathered in `framework/src/variables/MooseVariableBase.C:32` and `framework/src/actions/AddVariableAction.C:28`.

## When to use this (vs alternatives)

Decide on **`[Variables]` vs `[AuxVariables]`** first, then **discretization (FE / FV / Linear-FV / Scalar)**, then **shape (scalar field / vector / array)**.

1. The field appears in a residual or constraint solved by Newton (or a linear FV system): put it in **`[Variables]`**.
2. The field is computed *from* other fields, or read in by a transfer, or only output to ExodusII: put it in **`[AuxVariables]`** and pair it with an `[AuxKernels]` entry — see [kernels.md](./kernels.md).
3. Continuous, FE residuals in `[Kernels]`, `[BCs]`, `[NodalKernels]`: use the **default** (`family = LAGRANGE`, `order = FIRST`). No `type =` needed.
4. Discontinuous-Galerkin residuals in `[DGKernels]`: choose **`L2_LAGRANGE`**, **`L2_HIERARCHIC`**, or **`MONOMIAL`** — discontinuous bases.
5. 4th-order operators (Cahn-Hilliard, biharmonic): use **`HERMITE`** at `order = THIRD` for `C^1` continuity. The mesh must be all-quad/hex.
6. Cell-centered finite-volume residuals in `[FVKernels]`: use **`type = MooseVariableFVReal`** (or set `fv = true` with `family = MONOMIAL`, `order = CONSTANT`).
7. Linear-system FV residuals in `[LinearFVKernels]` (no Newton): use **`type = MooseLinearVariableFVReal`** and set `solver_sys` to a `linear_sys_names` entry on `[Problem]`.
8. Vector PDE (curl-curl Maxwell, mixed div-grad): use a single vector variable with **`LAGRANGE_VEC`**, **`MONOMIAL_VEC`**, **`NEDELEC_ONE`**, or **`RAVIART_THOMAS`** — *not* one-variable-per-component.
9. A bundle of N coupled scalar fields with the same FE space (e.g. species concentrations): use an **array variable** with `components = N` instead of N separate variables. Pair with `[ArrayKernels]` / `ArrayBodyForce` / etc.
10. ODE unknowns with no spatial dependence (a Lagrange multiplier integrating to a constant, a 0-D balance): use **`family = SCALAR`**. The residual rows live in `[ScalarKernels]`.
11. HDG primal+face-trace pairs: the face-trace variable is **`family = SIDE_HIERARCHIC`**; the primal companion is usually `L2_LAGRANGE`. The trio is wired through `[GlobalParams]` — see [kernels.md](./kernels.md) `[HDGKernels]`.

`[Variables]` and `[AuxVariables]` use the same catalog of families/types. Differences:
- An `[AuxVariables]` entry has **no `scaling`** (it doesn't enter the Jacobian).
- `[AuxVariables]` legitimately uses **`order = CONSTANT`** with **`family = MONOMIAL`** for elemental fields (one DoF per element) — common for stress/strain components recovered by `[AuxKernels]`.
- `[AuxVariables]` cannot have `eigen = true` and is never solved by Newton — its values come from an AuxKernel, an IC, a transfer, or an Exodus restart.

## Catalog

### `[Variables]` and `[AuxVariables]` sub-block params (catalog)

#### FE field variables (continuous and discontinuous Lagrange / Hierarchic / Monomial / Hermite)

##### FE Lagrange (default)
- C++ class: `framework/include/variables/MooseVariableFE.h:46` (registered as `MooseVariable` at `framework/src/variables/MooseVariable.C:12`)
- Example: `test/tests/kernels/simple_diffusion/simple_diffusion.i:9` (sub-block `[u]`, no params — uses defaults)
- Continuous (`C^0`) Lagrange shape functions; the standard FE choice for elliptic / parabolic problems.
- `family = LAGRANGE` (default), `order = FIRST | SECOND | THIRD | ...`. `SECOND` requires `second_order = true` on the `[Mesh]` and 2nd-order elements (`QUAD9`, `HEX27`, ...).
- Sub-block params:
  - `family = LAGRANGE` — shape function family.
  - `order = FIRST` — polynomial order.
  - `initial_condition = <Real>` — constant IC shorthand. For functional ICs, use `[ICs]` instead.
  - `scaling = <Real>` — Jacobian-row scaling for ill-conditioned multiphysics. `[Variables]` only.
  - `block = <subdomain_names>` — restrict variable to subdomains.
  - `outputs = <output_names | none>` — control which `[Outputs]` write this variable.
  - `eigen = true|false` — declare as the eigen variable for `[Problem] type = EigenProblem`.

##### FE Lagrange (second-order)
- C++ class: `framework/include/variables/MooseVariableFE.h:46`
- Example: `test/tests/kernels/scalar_constraint/scalar_constraint_kernel.i:46` (sub-block `[u]` with `family = LAGRANGE`, `order = SECOND`)
- Quadratic Lagrange. Requires the mesh to be 2nd-order: set `second_order = true` on `[Mesh]` or use `elem_type = QUAD9 | HEX27 | TRI6 | TET10`.

##### FE Monomial (constant — elemental)
- C++ class: `framework/include/variables/MooseVariableFE.h:46`
- Example: `test/tests/variables/fe_monomial_const/monomial-const-2d.i:46` (sub-block `[u]` with `family = MONOMIAL`, `order = CONSTANT`)
- One DoF per element; piecewise constant. Almost always paired with `[AuxKernels]` — this is the "elemental output" idiom for stresses, fluxes, processor-id fields, etc.

##### FE Monomial / L2_LAGRANGE / L2_HIERARCHIC (discontinuous, for DG)
- C++ class: `framework/include/variables/MooseVariableFE.h:46`
- Example (DG variable): `test/tests/dgkernels/2d_diffusion_dg/2d_diffusion_dg_test.i` (search `family = MONOMIAL`); aux example `test/tests/auxkernels/element_aux_var/l2_element_aux_var_test.i:18` (sub-block `[l2_lagrange]`)
- Discontinuous higher-order bases for `[DGKernels]`. Use `MONOMIAL` (orthogonal-on-element), `L2_LAGRANGE` (Lagrange-shaped but DoFs duplicated at element interfaces), or `L2_HIERARCHIC`.
- `order = CONSTANT | FIRST | SECOND | ...`.

##### FE Hermite (`C^1`-continuous, for biharmonic / 4th-order)
- C++ class: `framework/include/variables/MooseVariableFE.h:46`
- Example: `test/tests/variables/fe_hermite/hermite-3-2d.i:45` (sub-block `[u]` with `family = HERMITE`, `order = THIRD`)
- Cubic Hermite — provides `C^1` continuity needed for 4th-order operators (Cahn-Hilliard, plate bending). Mesh must be all-quad/hex; works for `dim = 1, 2, 3`.

##### FE Hierarchic
- C++ class: `framework/include/variables/MooseVariableFE.h:46`
- Example: `test/tests/variables/fe_hier/hier-3-2d.i:45` (sub-block `[u]` with `family = HIERARCHIC`, `order = THIRD`)
- Continuous hierarchic bases (`p`-refinement-friendly).

##### FE Vector — Lagrange / Monomial vec
- C++ class: `framework/include/variables/MooseVariableFE.h:30` (`typedef MooseVariableFE<RealVectorValue> VectorMooseVariable`); registered as `VectorMooseVariable` at `framework/src/variables/VectorMooseVariable.C:12`
- Example: `test/tests/auxkernels/parsed_vector_aux/parsed_aux_test.i:17` (sub-block `[parsed]` with `family = LAGRANGE_VEC`); FV-style elemental: same file, `[parsed_elem]` line 21 with `family = MONOMIAL_VEC`
- A single variable carrying a vector value at each node/QP. Paired with vector kernels (`VectorDiffusion`, `ParsedVectorAux`) and vector BCs.
- Sub-block params: `family = LAGRANGE_VEC | MONOMIAL_VEC | L2_LAGRANGE_VEC | L2_HIERARCHIC_VEC`. `initial_condition` accepts a 3-component string `'a b c'`.
- Prefer this over three scalar variables `u_x`, `u_y`, `u_z` *only* when you have a vector kernel/BC that consumes `LAGRANGE_VEC`. Solid-mechanics convention is still scalar `disp_x`/`disp_y`/`disp_z`.

##### FE Nedelec (curl-conforming, H(curl))
- C++ class: `framework/include/variables/MooseVariableFE.h:30` (`VectorMooseVariable` typedef)
- Example: `test/tests/kernels/vector_fe/vector_kernel.i:13` (sub-block `[u]` with `family = NEDELEC_ONE`, `order = FIRST`)
- For Maxwell / curl-curl problems: `family = NEDELEC_ONE`. Pair with `VectorFEWave` etc. Mesh is typically `QUAD9 / HEX27`.

##### FE Raviart-Thomas (div-conforming, H(div))
- C++ class: `framework/include/variables/MooseVariableFE.h:30`
- Example: `test/tests/kernels/vector_fe/coupled_electrostatics.i:26` (sub-block `[u]` with `family = RAVIART_THOMAS`, `order = FIRST`)
- For mixed div-grad / Darcy / `H(div)` formulations.

##### Side-Hierarchic (face-trace variable, for HDG)
- C++ class: `framework/include/variables/MooseVariableFE.h:46`
- Example: `test/tests/hdgkernels/ldg-diffusion/diffusion.i:19` (sub-block `[face_u]` with `family = SIDE_HIERARCHIC`, default `order` for HDG is usually `CONSTANT` or `FIRST`); standalone: `test/tests/variables/side_hierarchic/side_hierarchic.i:14`
- DoFs live on element faces only — the face-trace variable required by `[HDGKernels]`. Often co-declared with an `L2_LAGRANGE` primal variable and an `L2_LAGRANGE_VEC` gradient variable; they are wired together via `[GlobalParams]`.

#### FV (cell-centered finite volume)

##### `MooseVariableFVReal` — FV variable
- C++ class: `framework/include/variables/MooseVariableFV.h:52` (registered as `MooseVariableFVReal` at `framework/src/variables/MooseVariableFV.C:30`)
- Example: `test/tests/fvkernels/fv_simple_diffusion/dirichlet.i:11` (sub-block `[v]` with `family = MONOMIAL`, `order = CONSTANT`, `fv = true`)
- Cell-centered finite volume. Paired with `[FVKernels]`, `[FVBCs]`, `[FVInterfaceKernels]` — see [kernels.md](./kernels.md). Always AD on the kernel side.
- Two equivalent ways to declare:
  ```hit
  [u]
    type = MooseVariableFVReal
  []
  ```
  or (older idiom, equivalent)
  ```hit
  [u]
    family = MONOMIAL
    order = CONSTANT
    fv = true
  []
  ```
- FV-specific sub-block params (added in `framework/src/variables/MooseVariableFV.C:34`):
  - `two_term_boundary_expansion = true|false` (default `true`) — use a 2-term Taylor expansion at boundary faces. Set `false` for cheaper / more diffusive boundary handling.
  - `face_interp_method = average | skewness-corrected` (default `average`) — face-centroid interpolation. `skewness-corrected` adds a ghost layer.
  - `cache_cell_gradients = true|false` (default `true`).
- Inherits `initial_condition`, `block`, `outputs` from base.
- *No `scaling`*: FV variables share the cell-volume-scaled Jacobian rows automatically; user-set `scaling` is allowed but rarely useful.
- Cannot be `eigen = true`.

##### `MooseLinearVariableFVReal` — Linear-system FV variable
- C++ class: `framework/include/variables/MooseLinearVariableFV.h:46` (registered as `MooseLinearVariableFVReal` at `framework/src/variables/MooseLinearVariableFV.C:35`)
- Example: `test/tests/linearfvkernels/diffusion/diffusion-1d.i:13` (sub-block `[u]` with `type = MooseLinearVariableFVReal`, `solver_sys = u_sys`)
- Variable that lives on a `LinearSystem` rather than `NonlinearSystem` — used by `[LinearFVKernels]`. The matrix is assembled directly; no Newton.
- Required: `type = MooseLinearVariableFVReal`, `solver_sys = <name>` matching `[Problem] linear_sys_names = '<name>'`.
- Sub-block params:
  - `solver_sys` — name of the linear system on `[Problem]`.
  - `initial_condition`, `block`, `outputs`.
- Cannot mix in the same input as solver-system Newton variables unless `[Problem]` declares both `solver_sys = nl0` and a separate `linear_sys_names`.

#### Array variable (N-component bundle of FE variables)

##### `ArrayMooseVariable` — array of FE shape variables
- C++ class: `framework/include/variables/MooseVariableFE.h:31` (`typedef MooseVariableFE<RealEigenVector> ArrayMooseVariable`); registered at `framework/src/variables/ArrayMooseVariable.C:12`
- Example: `test/tests/variables/array_variable/array_variable_test.i:13` (sub-block `[u]` with `components = 4`, `initial_condition = '1 2 3 4'`)
- Bundle of N components sharing one FE space — cuts solver overhead vs N separate variables. Paired with `[ArrayKernels]` (e.g. `ADArrayDiffusion`) and `ArrayDirichletBC`.
- Sub-block params:
  - `components = N` (default 1) — sets `array = true` automatically when N > 1.
  - `array = true` — force array even with 1 component.
  - `family`, `order` — works with `LAGRANGE`, `L2_LAGRANGE`, `MONOMIAL`, `L2_HIERARCHIC`.
  - `initial_condition = '<v1> <v2> ... <vN>'` — one space-separated value per component.
  - `scaling = '<s1> <s2> ... <sN>'` — per-component Jacobian scaling. See `test/tests/kernels/array_kernels/ad_array_diffusion_test.i:13`.
  - `array_var_component_names = '<n1> <n2> ...'` — custom output names per component.

#### Scalar (no spatial dependence)

##### `MooseVariableScalar`
- C++ class: `framework/include/variables/MooseVariableScalar.h:29` (registered at `framework/src/variables/MooseVariableScalar.C:22`)
- Example: `test/tests/kernels/scalar_constraint/scalar_constraint_kernel.i:51` (sub-block `[lambda]` with `family = SCALAR`, `order = FIRST`)
- A single Real (or short vector at `order = SECOND`+) per simulation, **not per node**. Used for global Lagrange multipliers, integral-constraint multipliers, ODE rows.
- Sub-block params:
  - `family = SCALAR` — required.
  - `order = FIRST | SECOND | ...` — `order = N` produces N coupled scalar values (a length-N vector ODE row).
  - `initial_condition = <Real>` (or `'v1 v2 ...'` for `order > FIRST`).
  - `scaling = <Real>`, `block` (rare for scalars), `outputs`.
- Residual rows for scalar variables live in `[ScalarKernels]`. Coupling FE field --> scalar requires `ScalarLagrangeMultiplier` in `[Kernels]` (see [kernels.md](./kernels.md)).

## Cross-cutting concerns

### `initial_condition` shorthand vs `[ICs]`
- Constants and per-component lists belong inline: `initial_condition = 0`, `initial_condition = '1 2 3 4'`. Implemented at `framework/src/actions/AddVariableAction.C:47`.
- Anything spatial (function, file, user object, parsed expression) must go in `[ICs]` — that's where `FunctionIC`, `ParsedFunctionIC`, `RandomIC`, `ConstantIC` live. See [ics.md](./ics.md).
- For restart from a previous Exodus, use `initial_from_file_var = <name>` on the variable sub-block (action param at `AddVariableAction.C:49`); the file is set on `[Mesh] file = ... initial_from_file_timestep = ...`.

### `scaling` — Jacobian-row scaling for ill-conditioned multiphysics
- One `Real` per component (1 for scalar variables, `components` for array variables): `scaling = 1e-6`. Declared at `MooseVariableBase.C:46`.
- Use when a coupled solve has variables of vastly different magnitudes (e.g. displacements `~1e-3 m` and stress-projection variables `~1e8 Pa`). Set `scaling` so the diagonal Jacobian magnitudes are comparable.
- Prefer `automatic_scaling = true` on `[Executioner]` over hand-tuning. See `test/tests/scaling/`.
- `[AuxVariables]` ignore `scaling` (no Jacobian row).

### `outputs` — filtering what gets written
- `outputs = none` hides the variable from all outputs. Useful for internal Lagrange multipliers, intermediate gradient variables in HDG, face-trace variables.
- `outputs = '<output_name1> <output_name2>'` whitelists a subset of `[Outputs]` blocks. Example: `test/tests/outputs/variables/hide_output_via_variables_block.i:17`.
- The named outputs must exist in `[Outputs]` (`exodus`, `csv`, custom names).

### `eigen = true` — eigen-problem variables
- Marks the variable as the eigen-mode unknown. Pair with `[Problem] type = EigenProblem` and `[Executioner] type = Eigenvalue`. Example: `test/tests/problems/eigen_problem/eigensolvers/ne_deficient_b.i:18`.
- Cannot combine with `fv = true`; FV variables don't support eigen.
- The `EigenKernel`-side `eigen_postprocessor` parameter (e.g. on `BodyForce` with `extra_vector_tags = eigen`) is unrelated to this variable param — see [kernels.md](./kernels.md).

### `block` — subdomain restriction
- A variable restricted to `block = '<sub1> <sub2>'` only has DoFs on those subdomains; coupled kernels must also restrict to the same blocks. Example: `test/tests/variables/multiblock_restricted_var/multiblock_restricted_var_test.i:5`.
- Mismatched restriction silently drops residual contributions on the boundary between restricted and unrestricted blocks.

### `fv_two_term_boundary_expansion`
- The HIT spelling on `MooseVariableFVReal` is **`two_term_boundary_expansion`** (no `fv_` prefix), declared at `framework/src/variables/MooseVariableFV.C:41`. Default `true`. Set to `false` to fall back to one-term boundary expansion (cheaper, more diffusive at boundaries).

### Family --> kernel-block mapping (cheat sheet)
| Variable choice | Kernel block | Notes |
|---|---|---|
| `LAGRANGE` (default) | `[Kernels]`, `[BCs]`, `[NodalKernels]`, `[DiracKernels]` | The default. AD or non-AD. |
| `MONOMIAL` / `L2_LAGRANGE` / `L2_HIERARCHIC` | `[DGKernels]` (interior facets) + `[Kernels]` for volumetric + DG-aware `[BCs]` | Continuous-FE BCs do *not* apply. |
| `HERMITE` | `[Kernels]` | Cahn-Hilliard etc. Usually `order = THIRD`. |
| `LAGRANGE_VEC` / `MONOMIAL_VEC` / `NEDELEC_ONE` / `RAVIART_THOMAS` | `[Kernels]` (vector kernels), `[BCs]` (vector BCs) | One vector variable, not 3 scalars. |
| `SIDE_HIERARCHIC` (+ `L2_LAGRANGE` primal) | `[HDGKernels]` | Trio wired through `[GlobalParams]`. |
| `SCALAR` | `[ScalarKernels]` | Global ODE / Lagrange-multiplier rows. |
| `type = MooseVariableFVReal` (or `fv = true`) | `[FVKernels]`, `[FVBCs]`, `[FVInterfaceKernels]` | Always AD; cell-centered. |
| `type = MooseLinearVariableFVReal` | `[LinearFVKernels]`, `[LinearFVBCs]` | Linear system; needs `solver_sys`. |
| Array (`components > 1`) | `[ArrayKernels]`, array-aware `[BCs]` | Per-component `scaling` and `initial_condition`. |

## Minimal scaffold

A continuous FE Lagrange variable with an inline IC:

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
    family = LAGRANGE       # default; shown for clarity
    order = FIRST           # default; shown for clarity
    initial_condition = 0.5
    scaling = 1.0
  []
[]

[AuxVariables]
  [u_elem]
    family = MONOMIAL
    order = CONSTANT        # one DoF per element — elemental output
    outputs = exodus
  []
[]

[Kernels]
  [diff]
    type = ADDiffusion
    variable = u
  []
[]

[AuxKernels]
  [u_to_elem]
    type = ProjectionAux
    variable = u_elem
    v = u
  []
[]

[BCs]
  [all]
    type = ADDirichletBC
    variable = u
    boundary = 'left right top bottom'
    value = 0
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
[]

[Outputs]
  exodus = true
[]
```

A finite-volume variable wired into `[FVKernels]`:

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
    type = MooseVariableFVReal
    initial_condition = 1.0
    two_term_boundary_expansion = true
  []
[]

[FVKernels]
  [diff]
    type = FVDiffusion
    variable = u
    coeff = 1.0
  []
  [time]
    type = FVTimeKernel
    variable = u
  []
[]

[FVBCs]
  [all]
    type = FVDirichletBC
    variable = u
    boundary = 'left right top bottom'
    value = 0
  []
[]

[Executioner]
  type = Transient
  num_steps = 10
  dt = 0.1
  solve_type = NEWTON
[]
```

A scalar Lagrange-multiplier variable plus an FE field driven by an integral constraint:

```hit
[Variables]
  [u]
    family = LAGRANGE
    order = SECOND
  []
  [lambda]
    family = SCALAR
    order = FIRST
    initial_condition = 0
  []
[]

[Kernels]
  [diff]
    type = Diffusion
    variable = u
  []
  [lm_term]
    type = ScalarLagrangeMultiplier
    variable = u
    lambda = lambda
  []
[]

[ScalarKernels]
  [avg_constraint]
    type = AverageValueConstraint
    variable = lambda
    pp_name = u_average
    value = 0
  []
[]
```
