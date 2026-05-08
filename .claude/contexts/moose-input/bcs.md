# Authoring inputs: Boundary conditions and constraints

Reach for this guide when you need to constrain a variable on a sideset/nodeset by **picking from the catalog** of registered MOOSE boundary conditions and constraints — strong Dirichlet, weak Neumann, Robin/penalty, FV BCs, linear-FV BCs, mortar/equality constraints, and DG-aware boundary terms. Volumetric residuals: [kernels.md](./kernels.md). Per-node soft Dirichlet / NCP enforcement: see `[NodalKernels]` in [kernels.md](./kernels.md). New BC C++: `../moose/bc-authoring.md`.

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. Each entry cites both the **source header** (`<file>:<line of class>`) and one **canonical example .i** (`<file>:<line of the sub-block>`). AD twins (`ADFoo`) live in the same header as the templated class — same required params, same patterns.

## When to use this (vs alternatives)

Decide **block** first, then **strong vs weak**, then **AD vs non-AD**.

1. FE Dirichlet/Neumann/Robin (most common): **`[BCs]`** — `ADDirichletBC`, `ADFunctionNeumannBC`, `ADRobinBC`. Default to AD-named classes.
2. Cell-centered FV (`type = MooseVariableFVReal`): **`[FVBCs]`** — always AD; `FVDirichletBC`, `FVFunctorDirichletBC`, `FVFunctorNeumannBC`.
3. Linear-system FV (`type = MooseLinearVariableFVReal`, no Newton): **`[LinearFVBCs]`** — `LinearFVAdvectionDiffusionFunctorDirichletBC`, `LinearFVAdvectionDiffusionOutflowBC`.
4. Mortar/equality/tied across an internal interface, or pin a sideset's average: **`[Constraints]`** — `EqualValueConstraint`, `PenaltyEqualValueConstraint`, `TiedValueConstraint`, `LinearNodalConstraint`, `EqualValueEmbeddedConstraint`. Mortar **contact** constraints: [contact.md](./contact.md).
5. DG external boundary paired with `[DGKernels]` interior facets: **`[BCs]`** with a DG-aware class — `DGFunctionDiffusionDirichletBC` (DG external BCs live in `[BCs]`, not in any DG-specific block).
6. Periodic boundary: **`[BCs/Periodic]`** action sub-block, *not* a typed BC entry — see periodic note in cross-cutting concerns.
7. Per-node soft Dirichlet that needs block restriction: prefer `[NodalKernels]/PenaltyDirichletNodalKernel` over `PenaltyDirichletBC`.

**Strong vs weak.** Strong Dirichlet (`DirichletBC`, `ADDirichletBC`) writes the value directly into the solution vector at nodes — exact, FE-only. Weak Dirichlet (`PenaltyDirichletBC`, `ADRobinBC`, `FVFunctorDirichletBC`) integrates a residual; the value is enforced approximately, scales with the penalty, works on FV. Neumann-type BCs are always weak.

**FE vs FV vs Linear-FV.** `[BCs]` is for FE variables. `[FVBCs]` is for cell-centered FV (always AD). `[LinearFVBCs]` is for `MooseLinearVariableFVReal` (no Newton; matrix + RHS assembled directly). The three blocks are mutually exclusive — wrong block triggers "no objects of this type" at parse.

## Catalog

### `[BCs]` — FE boundary conditions

#### Strong Dirichlet (nodal value imposition)

##### `DirichletBC` / `ADDirichletBC`
- Source: `framework/include/bcs/DirichletBC.h:19` / `framework/include/bcs/ADDirichletBC.h:19`
- Example: `test/tests/bcs/1d_neumann/1d_neumann.i:21` (sub-block `[left]`); AD: `test/tests/bcs/ad_bc_preset_nodal/bc_preset_nodal.i:34`
- Canonical strong nodal Dirichlet: forces `u = value` at every node on the sideset.
- Required: `variable`, `boundary`, `value`.
- Useful: `preset` (default true — set the value before the residual evaluates).

##### `FunctionDirichletBC` / `ADFunctionDirichletBC`
- Source: `framework/include/bcs/FunctionDirichletBC.h:20` / `framework/include/bcs/ADFunctionDirichletBC.h:19`
- Example: `test/tests/bcs/function_dirichlet_bc/test.i:65`; AD: `test/tests/bcs/ad_function_dirichlet_bc/test.i:64` (sub-block `[all]`)
- Strong Dirichlet with the value coming from a `Function` of `(t,x,y,z)`.
- Required: `variable`, `boundary`, `function`.
- Useful: `preset`.

##### `FunctorDirichletBC`
- Source: `framework/include/bcs/FunctorDirichletBC.h:17`
- Example: `test/tests/bcs/functor_dirichlet_bc/test.i:56` (sub-block `[all]`)
- AD strong Dirichlet from any functor (variable, function, functor mat-prop) — use when the value depends on a coupled variable / material output.
- Required: `variable`, `boundary`, `functor`.

##### `MatchedValueBC` / `ADMatchedValueBC`
- Source: `framework/include/bcs/MatchedValueBC.h:18` (templated; both twins registered in `framework/src/bcs/MatchedValueBC.C:12`)
- Example: `test/tests/bcs/matched_value_bc/matched_value_bc_test.i:53` (sub-block `[left_u]`); AD: `test/tests/bcs/ad_matched_value_bc/test.i:51`
- Forces `u = v` at the boundary (`v` is a coupled variable). Glues two FE variables across a sideset without mortar.
- Required: `variable`, `boundary`, `v`.

##### `PostprocessorDirichletBC`
- Source: `framework/include/bcs/PostprocessorDirichletBC.h:19`
- Example: `test/tests/postprocessors/change_over_fixed_point/change_over_fixed_point.i:27` (sub-block `[right]`)
- Value comes from the current value of a `Postprocessor` (fixed-point / sub-app coupling).
- Required: `variable`, `boundary`, `postprocessor`.

##### `VectorDirichletBC`
- Source: `framework/include/bcs/VectorDirichletBC.h:19`
- Example: `test/tests/auxkernels/vector_variable_nodal/vector_variable_nodal.i:31` (sub-block `[left]`)
- Strong Dirichlet for vector FE variables (`LAGRANGE_VEC`, `NEDELEC_ONE`). All components from a `RealVectorValue`.
- Required: `variable`, `boundary`, `values` (3-entry).

##### `VectorFunctionDirichletBC` / `ADVectorFunctionDirichletBC`
- Source: `framework/include/bcs/VectorFunctionDirichletBC.h:19` / `framework/include/bcs/ADVectorFunctionDirichletBC.h:19`
- Example: `test/tests/kernels/vector_fe/lagrange_vec.i:35`; AD: `test/tests/bcs/ad_vector_function_neumann_bc/vector_ad_neumann_bc.i:23` (sub-block `[top_bottom]`)
- Vector FE strong Dirichlet with each component from a `Function`.
- Required: `variable`, `boundary`. At least one of `function`, `function_x`/`function_y`/`function_z`.

##### `ArrayDirichletBC` / `ADArrayDirichletBC`
- Source: `framework/include/bcs/ArrayDirichletBC.h:19` / `framework/include/bcs/ADArrayDirichletBC.h:19`
- Example: `test/tests/auxkernels/array_var_component/array_var_component.i:26`; AD: `test/tests/kernels/array_kernels/ad_array_diffusion_test.i:26`
- Strong Dirichlet for array variables (one constant per component).
- Required: `variable`, `boundary`, `values` (length = array size).

##### `EigenDirichletBC`
- Source: `framework/include/bcs/EigenDirichletBC.h:18`
- Example: search `test/tests/problems` for `type = EigenDirichletBC`.
- Zero-value strong Dirichlet that participates correctly in eigenproblems (no spurious eigenvalues).
- Required: `variable`, `boundary`.

#### Weak Neumann (flux imposition)

##### `NeumannBC` / `ADNeumannBC`
- Source: `framework/include/bcs/NeumannBC.h:19` (templated; both twins registered in `framework/src/bcs/NeumannBC.C:12`)
- Example: `test/tests/bcs/1d_neumann/1d_neumann.i:27` (sub-block `[right]`); AD: `test/tests/bcs/ad_1d_neumann/1d_neumann.i:27`
- Imposes `du/dn = value` on the sideset. Class description: "$\partial u / \partial n = h$".
- Required: `variable`, `boundary`, `value`.

##### `FunctionNeumannBC` / `ADFunctionNeumannBC`
- Source: `framework/include/bcs/FunctionNeumannBC.h:19` / `framework/include/bcs/ADFunctionNeumannBC.h:19`
- Example: `test/tests/bcs/function_neumann_bc/test.i:42` (sub-block `[right]`); AD: `test/tests/bcs/ad_function_neumann_bc/test.i:42`
- Spatially/temporally varying flux from a `Function`.
- Required: `variable`, `boundary`, `function`.

##### `FunctorNeumannBC`
- Source: `framework/include/bcs/FunctorNeumannBC.h:17`
- Example: `test/tests/bcs/functor_neumann_bc/functor_neumann_bc.i:54` (sub-block `[right]`)
- AD Neumann with the flux value supplied as any functor (variable, function, functor mat-prop, etc.).
- Required: `variable`, `boundary`, `functor`.
- Useful: `factor` (default 1).

##### `CoupledVarNeumannBC` / `ADCoupledVarNeumannBC`
- Source: `framework/include/bcs/CoupledVarNeumannBC.h:23` (templated; both twins registered in `framework/src/bcs/CoupledVarNeumannBC.C:12`)
- Example: `test/tests/bcs/coupled_var_neumann/coupled_var_neumann.i:55` (sub-block `[right]`)
- Flux equals a coupled variable (`v`) — for boundary flux that is a transferred aux/sub-app field.
- Required: `variable`, `boundary`, `v`.
- Useful: `coef` (default 1), `scale_factor` (functor multiplier).

##### `MatNeumannBC` / `ADMatNeumannBC`
- Source: `framework/include/bcs/MatNeumannBC.h:20` (templated; both twins registered in `framework/src/bcs/MatNeumannBC.C:12`)
- Example: `test/tests/bcs/mat_neumann_bc/mat_neumann.i:37` (sub-block `[top]`); AD: `test/tests/bcs/mat_neumann_bc/ad_mat_neumann.i:37`
- `NeumannBC` multiplied by a material-property mask — flux = `value * boundary_material`.
- Required: `variable`, `boundary`, `boundary_material`.
- Useful: `value` (default 1).

##### `PostprocessorNeumannBC`
- Source: `framework/include/bcs/PostprocessorNeumannBC.h:18`
- Example: `test/tests/bcs/pp_neumann/pp_neumann.i:36` (sub-block `[right]`)
- Constant flux equal to the current value of a `Postprocessor`.
- Required: `variable`, `boundary`, `postprocessor`.

##### `VacuumBC`
- Source: `framework/include/bcs/VacuumBC.h:20`
- Example: `test/tests/bcs/misc_bcs/vacuum_bc_test.i:48` (sub-block `[top]`)
- Neutron-transport vacuum flux `alpha/2 u` (also a Robin-style absorbing diffusion BC).
- Required: `variable`, `boundary`.
- Useful: `alpha` (default 1).

##### `DirectionalNeumannBC`
- Source: `framework/include/bcs/DirectionalNeumannBC.h:21`
- Example: search `test/tests/bcs` for `type = DirectionalNeumannBC`.
- Flux `int_S value * (n . d) psi dS` for a fixed direction `d`.
- Required: `variable`, `boundary`, `value`, `vector`.

##### `FunctionGradientNeumannBC`
- Source: `framework/include/bcs/FunctionGradientNeumannBC.h:19`
- Example: search `test/tests/bcs` for `type = FunctionGradientNeumannBC`.
- Imposes `D grad(exact_solution) . n` from a known `Function` — common for MMS.
- Required: `variable`, `boundary`, `exact_solution`.

##### `DiffusionFluxBC`
- Source: `framework/include/bcs/DiffusionFluxBC.h:26`
- Example: `test/tests/bcs/conservative_advection_bc/no_upwinding_2D.i:85` (sub-block `[outlet_diffusive_flux]`)
- Natural outflow boundary that integrates `(D grad u . n) psi` so the diffusive flux exits unprescribed; pair with an advective BC.
- Required: `variable`, `boundary`.
- Useful: `diffusivity` (default `D`).

##### `ConservativeAdvectionBC` / `ADConservativeAdvectionBC`
- Source: `framework/include/bcs/ConservativeAdvectionBC.h:22`
- Example: `test/tests/bcs/conservative_advection_bc/no_upwinding_2D.i:79` (sub-block `[outlet_avective_flux]`)
- Outflow advective flux `(v . n) u psi`. Pair with `ConservativeAdvection` interior kernel.
- Required: `variable`, `boundary`. Exactly one of `velocity_variable` / `velocity_function` / `velocity_material`.
- Useful: `primal_variable`, `advected_quantity`.

##### `SinDirichletBC` / `SinNeumannBC`
- Source: `framework/include/bcs/SinDirichletBC.h:25` / `framework/include/bcs/SinNeumannBC.h:26`
- Example: `test/tests/bcs/sin_bc/sin_dirichlet_test.i:51` (sub-block `[left]`)
- Time-ramped from `initial` to `final` via `sin(pi t/(2 duration))`.
- Required: `variable`, `boundary`, `initial`, `final`, `duration`.

##### `WeakGradientBC`
- Source: `framework/include/bcs/WeakGradientBC.h:26`
- Example: `test/tests/bcs/misc_bcs/weak_gradient_bc_test.i:70` (sub-block `[top]`)
- Explicitly adds the natural `(grad u . n) psi` term — needed when another `[BCs]` entry on the same sideset suppresses it.
- Required: `variable`, `boundary`.

#### Penalty / Robin (weak Dirichlet, mixed)

##### `PenaltyDirichletBC` / `ADPenaltyDirichletBC`
- Source: `framework/include/bcs/PenaltyDirichletBC.h:34` / `framework/include/bcs/ADPenaltyDirichletBC.h:34`
- Example: `test/tests/bcs/penalty_dirichlet_bc/penalty_dirichlet_bc_test.i:56` (sub-block `[bc_all]`); AD: `test/tests/bcs/ad_penalty_dirichlet_bc/penalty_dirichlet_bc_test.i:56`
- Weak Dirichlet via penalty `(penalty (u - value), psi)`. Use when strong Dirichlet is unacceptable (e.g. discontinuous variables, NCP enforcement).
- Required: `variable`, `boundary`, `penalty`.
- Useful: `value` (default 0).

##### `FunctionPenaltyDirichletBC` / `ADFunctionPenaltyDirichletBC`
- Source: `framework/include/bcs/FunctionPenaltyDirichletBC.h:23` / `framework/include/bcs/ADFunctionPenaltyDirichletBC.h:22`
- Example: `test/tests/bcs/penalty_dirichlet_bc/function_penalty_dirichlet_bc_test.i:56` (sub-block `[bc_all]`)
- Penalty Dirichlet with the target value supplied as a `Function`.
- Required: `variable`, `boundary`, `penalty`, `function`.

##### `ADRobinBC`
- Source: `framework/include/bcs/ADRobinBC.h:14`
- Example: `test/tests/bcs/ad_bcs/ad_bc.i:28` (sub-block `[right]`)
- Generic Robin term `(coef u, psi)` — pairs with an interior diffusion kernel to give `D grad u . n + coef u = 0`. AD-only (no non-AD twin registered).
- Required: `variable`, `boundary`.
- Useful: `coefficient` (default 1).

##### `ConvectiveFluxBC`
- Source: `framework/include/bcs/ConvectiveFluxBC.h:14`
- Example: `test/tests/bcs/misc_bcs/convective_flux_bc.i:41` (sub-block `[right]`)
- Newton's-cooling-style Robin: `(coefficient (u - final), psi)` ramped via `(initial -> final)` over `duration`. Generic transient-ramped Robin.
- Required: `variable`, `boundary`, `final`.
- Useful: `initial` (default 0), `duration` (default 0), `rate` / `coefficient` (default 7.27).

##### `ConvectiveHeatFluxBC` / `ADConvectiveHeatFluxBC`
- Source: `modules/heat_transfer/include/bcs/ConvectiveHeatFluxBC.h:18` / `modules/heat_transfer/include/bcs/ADConvectiveHeatFluxBC.h:18`
- Example: `modules/heat_transfer/test/tests/convective_heat_flux/equilibrium.i:27` (sub-block `[right]`); AD: `modules/heat_transfer/test/tests/ad_convective_heat_flux/equilibrium.i:27`
- Standard convective heat-flux `q = htc (T - T_inf)`. Both inputs accept var/function/const.
- Required: `variable`, `boundary`. Exactly one each of `T_infinity` / `T_infinity_functor` and `heat_transfer_coefficient` / `heat_transfer_coefficient_functor`.

#### Vector / array integrated BCs

##### `VectorPenaltyDirichletBC`
- Source: `framework/include/bcs/VectorPenaltyDirichletBC.h:19`
- Example: `test/tests/bcs/vector_penalty_dirichlet_bc/test.i:25` (sub-block `[left]`)
- Component-wise penalty Dirichlet for vector FE variables.
- Required: `variable`, `boundary`, `penalty`.
- Useful: `function`, `function_x`/`function_y`/`function_z`.

##### `ADVectorMatchedValueBC`
- Source: `framework/include/bcs/ADVectorMatchedValueBC.h:17`
- Example: search `test/tests/bcs` for `type = ADVectorMatchedValueBC`.
- Strong Dirichlet that matches a vector FE variable to a coupled vector variable on the boundary.
- Required: `variable`, `boundary`, `v`.

##### `ArrayPenaltyDirichletBC`
- Source: `framework/include/bcs/ArrayPenaltyDirichletBC.h:14`
- Example: `test/tests/kernels/array_kernels/array_save_in.i:94` (sub-block `[right]`)
- Penalty Dirichlet for array variables.
- Required: `variable`, `boundary`, `penalty`.
- Useful: `value` (length-array).

##### `ArrayNeumannBC` / `ArrayVacuumBC`
- Source: `framework/include/bcs/ArrayNeumannBC.h:14` / `framework/include/bcs/ArrayVacuumBC.h:14`
- Example: `test/tests/bcs/array_vacuum/array_vacuum.i:31` (`[left]` is `ArrayVacuumBC`)
- Neumann/Vacuum analogues for array variables.
- Required: `variable`, `boundary`. `value` (Neumann) or `alpha` (Vacuum) — array-sized.

#### DG-aware BCs (live in `[BCs]`)

##### `DGFunctionDiffusionDirichletBC`
- Source: `framework/include/bcs/DGFunctionDiffusionDirichletBC.h:24`
- Example: `test/tests/coord_type/coord_type_rz_integrated.i:59` (sub-block `[source]`)
- SIPG boundary penalty term — Dirichlet value on a DG external boundary. Pairs with `DGDiffusion` interior facets. **DG external BCs go in `[BCs]`, not `[DGKernels]`.**
- Required: `variable`, `boundary`, `function`, `sigma`, `epsilon`.
- Useful: `diff` (default 1; must match `DGDiffusion`'s `diff`).

For DG advection, use `ConservativeAdvectionBC` on the outflow + no BC on the inflow (upwind interior facets handle it).

### `[FVBCs]` — finite-volume boundary conditions (always AD)

#### Dirichlet (face-value imposition)

##### `FVDirichletBC`
- Source: `framework/include/fvbcs/FVDirichletBC.h:17`
- Example: `test/tests/fvbcs/fv_neumannbc/fv_neumannbc.i:40` (sub-block `[left]`)
- Constant face value at the boundary cell-face.
- Required: `variable`, `boundary`, `value`.

##### `FVFunctionDirichletBC`
- Source: `framework/include/fvbcs/FVFunctionDirichletBC.h:17`
- Example: `test/tests/fvkernels/mms/diffusion.i:32` (sub-block `[fdiff]`)
- Face value from a `Function`.
- Required: `variable`, `boundary`, `function`.

##### `FVFunctorDirichletBC` / `FVADFunctorDirichletBC`
- Source: `framework/include/fvbcs/FVFunctorDirichletBC.h:19` (templated; both twins registered in `framework/src/fvbcs/FVFunctorDirichletBC.C:12`)
- Example: `test/tests/fvbcs/fv_functor_dirichlet/fv_functor_dirichlet.i:26` (sub-block `[left]`)
- Face value from any functor. Inputs identical between twins; difference is AD propagation through the functor.
- Required: `variable`, `boundary`, `functor`.

##### `FVPostprocessorDirichletBC`
- Source: `framework/include/fvbcs/FVPostprocessorDirichletBC.h:14`
- Example: `test/tests/fvbcs/fv_pp_dirichlet/fv_pp_dirichlet.i:25` (sub-block `[left]`)
- Face value driven by a `Postprocessor` — fixed-point/picard FV coupling.
- Required: `variable`, `boundary`, `postprocessor`.

#### Neumann (flux imposition)

##### `FVNeumannBC`
- Source: `framework/include/fvbcs/FVNeumannBC.h:17`
- Example: `test/tests/fvbcs/fv_neumannbc/fv_neumannbc.i:46` (sub-block `[right]`)
- Constant flux into the domain.
- Required: `variable`, `boundary`, `value`.

##### `FVFunctionNeumannBC`
- Source: `framework/include/fvbcs/FVFunctionNeumannBC.h:19`
- Example: search `test/tests/fvkernels` for `type = FVFunctionNeumannBC`.
- Flux from a `Function`.
- Required: `variable`, `boundary`, `function`.

##### `FVFunctorNeumannBC`
- Source: `framework/include/fvbcs/FVFunctorNeumannBC.h:18`
- Example: `test/tests/fvbcs/fv_functor_neumannbc/fv_functor_neumann.i:42` (sub-block `[left]`)
- Flux from any functor — the canonical way to impose a material-mask or coupled-variable flux in FV.
- Required: `variable`, `boundary`, `functor`.
- Useful: `factor`.

#### Outflow

##### `FVConstantScalarOutflowBC`
- Source: `framework/include/fvbcs/FVConstantScalarOutflowBC.h:17`
- Example: `test/tests/fvkernels/fv_constant_scalar_advection/2D_constant_scalar_advection.i:43` (sub-block `[fv_outflow]`)
- Outflow advective flux for a passive scalar with constant velocity — pair with `FVAdvection`.
- Required: `variable`, `boundary`, `velocity` (RealVectorValue).

For NS-style outflow / wall / symmetry / inlet BCs in FV, see the `INSFV*` and `WCNSFV*` registered classes under `modules/navier_stokes/src/fvbcs/` (covered in [navier-stokes.md](./navier-stokes.md)).

### `[LinearFVBCs]` — pre-assembled linear-system FV BCs

Variable must be `MooseLinearVariableFVReal`. The `LinearFVAdvectionDiffusion*` family assumes a diffusion-advection-reaction PDE.

##### `LinearFVAdvectionDiffusionFunctorDirichletBC`
- Source: `framework/include/linearfvbcs/LinearFVAdvectionDiffusionFunctorDirichletBC.h:18`
- Example: `test/tests/linearfvkernels/diffusion/diffusion-1d.i:45` (sub-block `[dir]`); advection: `test/tests/linearfvkernels/advection/advection-1d.i:58` (sub-block `[inflow]`)
- Strong Dirichlet from any functor.
- Required: `variable`, `boundary`, `functor`.
- Useful: `use_two_term_expansion` (default true — cell + gradient extrapolation, higher order).

##### `LinearFVAdvectionDiffusionOutflowBC`
- Source: `framework/include/linearfvbcs/LinearFVAdvectionDiffusionOutflowBC.h:18`
- Example: `test/tests/linearfvkernels/advection/advection-1d.i:64` (sub-block `[outflow]`)
- Advective outflow + zero-diffusive-gradient face value via cell-extrapolation.
- Required: `variable`, `boundary`.
- Useful: `use_two_term_expansion`.

##### `LinearFVAdvectionDiffusionExtrapolatedBC`
- Source: `framework/include/linearfvbcs/LinearFVAdvectionDiffusionExtrapolatedBC.h:18`
- Example: `modules/navier_stokes/test/tests/finite_volume/ins/natural_convection/linear_segregated/2d/diff_heated_cavity_linear_segregated.i:183` (sub-block `[T_all]`)
- Pure cell-to-face extrapolation (zero-gradient on both fluxes). Base class of `OutflowBC`; use directly when neither flux is prescribed.
- Required: `variable`, `boundary`.
- Useful: `use_two_term_expansion`.

##### `LinearFVAdvectionDiffusionFunctorNeumannBC`
- Source: `framework/include/linearfvbcs/LinearFVAdvectionDiffusionFunctorNeumannBC.h:18`
- Example: search `test/tests/linearfvkernels` for `type = LinearFVAdvectionDiffusionFunctorNeumannBC`.
- Neumann flux for linear-FV variables, value from a functor.
- Required: `variable`, `boundary`, `functor`.

##### `LinearFVAdvectionDiffusionFunctorRobinBC`
- Source: `framework/include/linearfvbcs/LinearFVAdvectionDiffusionFunctorRobinBC.h:19`
- Example: search `test/tests/linearfvkernels` for `type = LinearFVAdvectionDiffusionFunctorRobinBC`.
- Robin BC `q = htc (u - u_ref)` for linear-FV; both `htc` and `u_ref` are functors.
- Required: `variable`, `boundary`, `functor` (the `u_ref` value), `coefficient_functor` (the `htc`).

### `[Constraints]` — equality and mortar constraints

#### Mortar (lower-d sideset coupling)

##### `EqualValueConstraint`
- Source: `framework/include/constraints/EqualValueConstraint.h:18`
- Example: `test/tests/mortar/convergence-studies/solution-continuity/continuity.i:160` (sub-block `[mortar]`)
- Mortar Lagrange-multiplier `u_primary = u_secondary` on a non-matching interface. Needs lower-d blocks (see cross-cutting).
- Required: `variable` (LM, on secondary lower-d block), `secondary_variable`, `primary_boundary`, `secondary_boundary`, `primary_subdomain`, `secondary_subdomain`.

##### `PenaltyEqualValueConstraint` / `ADPenaltyEqualValueConstraint`
- Source: `framework/include/constraints/PenaltyEqualValueConstraint.h:25` (templated; both twins registered in `framework/src/constraints/PenaltyEqualValueConstraint.C:12`)
- Example: `test/tests/mortar/coincident-nodes/test.i:50` (sub-block `[mortar]`)
- Penalty version of `EqualValueConstraint` — no LM DOF. Trades exactness for simpler linearization.
- Required: `secondary_variable`, `primary_boundary`, `secondary_boundary`, `primary_subdomain`, `secondary_subdomain`, `penalty_value`.

##### `EqualGradientConstraint`
- Source: `framework/include/constraints/EqualGradientConstraint.h:18`
- Example: `test/tests/mortar/continuity-2d-conforming/equalgradient.i:69` (sub-block `[cedx]`)
- Mortar `grad u . e_i` continuity per component. Pair multiple instances for full gradient continuity.
- Required: `variable` (LM), `secondary_variable`, `primary_boundary`, `secondary_boundary`, `primary_subdomain`, `secondary_subdomain`, `component`.

##### `PeriodicSegmentalConstraint` / `ADPeriodicSegmentalConstraint`
- Source: `framework/include/constraints/PeriodicSegmentalConstraint.h:30` / `framework/include/constraints/ADPeriodicSegmentalConstraint.h`
- Example: `test/tests/mortar/ad_periodic_segmental_constraint/periodic_simple2d.i:132` (sub-block, AD twin)
- Periodic-homogenization jump `u_primary - u_secondary = epsilon . (X_primary - X_secondary)` for a macroscopic-strain scalar variable. Pair with `EqualValueConstraint` on off-diagonal sidesets.
- Required: `variable` (LM), `secondary_variable`, `primary_boundary`, `secondary_boundary`, `primary_subdomain`, `secondary_subdomain`, `epsilon` (scalar variable).

#### Node-face equality (no mortar)

##### `TiedValueConstraint`
- Source: `framework/include/constraints/TiedValueConstraint.h:19`
- Example: `test/tests/constraints/tied_value_constraint/tied_value_constraint_test.i:43` (sub-block `[value]`)
- Old-style node-face tie of a single variable. For new work prefer mortar `EqualValueConstraint`.
- Required: `variable`, `secondary`, `primary`, `penalty`.

##### `CoupledTiedValueConstraint`
- Source: `framework/include/constraints/CoupledTiedValueConstraint.h:19`
- Example: `test/tests/constraints/coupled_tied_value_constraint/coupled_tied_value_constraint.i:53` (sub-block `[value]`)
- `TiedValueConstraint` with a coupled variable in the constraint (multi-physics ties).
- Required: `variable`, `v`, `secondary`, `primary`, `penalty`.

##### `EqualValueEmbeddedConstraint` / `ADEqualValueEmbeddedConstraint`
- Source: `framework/include/constraints/EqualValueEmbeddedConstraint.h:24` (templated; both twins registered in `framework/src/constraints/EqualValueEmbeddedConstraint.C:23`)
- Example: `test/tests/constraints/equal_value_embedded_constraint/embedded_constraint.i:57` (sub-block `[equal]`)
- Embedded/immersed: variable on the secondary subdomain matches the surrounding primary subdomain at embedded nodes.
- Required: `variable`, `secondary`, `primary`, `penalty`, `formulation` (`KINEMATIC`/`PENALTY`).

#### Nodal (no integration)

##### `LinearNodalConstraint`
- Source: `framework/include/constraints/LinearNodalConstraint.h:21`
- Example: `test/tests/constraints/nodal_constraint/linear_nodal_constraint.i:38` (sub-block `[c1]`)
- `u_secondary = sum_i weight_i * u_primary_i + offset` — slave/master tying at nodes (exact, no integration).
- Required: `variable`, `primary`, `secondary`, `weights`, `penalty`.
- Useful: `formulation`.

##### `EqualValueBoundaryConstraint`
- Source: `framework/include/constraints/EqualValueBoundaryConstraint.h:14`
- Example: `test/tests/constraints/equal_value_boundary_constraint/equal_value_boundary_constraint_test.i:48` (sub-block `[y_top]`)
- All sideset nodes share one unknown value (free Dirichlet). For symmetry / multi-point constraints.
- Required: `variable`, `boundary`, `penalty`.
- Useful: `formulation`.

Mortar **mechanical contact** (`MechanicalContactConstraint`, `NormalMortarMechanicalContact`, `TangentialMortarMechanicalContact`) is in [contact.md](./contact.md), not here.

## Cross-cutting concerns

### Sideset names (`boundary`)
- `boundary` accepts one or a list of sideset names (`boundary = 'left right'`). Names come from `[Mesh]` — typically `'left right top bottom front back'` for `GeneratedMeshGenerator`. See [mesh.md](./mesh.md).
- Strong nodal Dirichlets need a *node* set; MOOSE auto-promotes sidesets to nodesets in most cases. If not, add `SideSetsFromBoundaryGenerator` / `BoundaryToNodeSetGenerator`.
- On integrated BCs `boundary` selects the integration faces; on nodal BCs it selects the clamped nodes.

### AD vs non-AD
- Default to `AD*` for new inputs — automatic off-diag Jacobians, no manual `args`. `[FVBCs]` is *always* AD. `[LinearFVBCs]` is non-AD by construction (direct matrix assembly). For `[Constraints]`, `EqualValueConstraint` / `EqualGradientConstraint` are AD-only; mortar tied/penalty have AD twins (`ADPenaltyEqualValueConstraint`, `ADEqualValueEmbeddedConstraint`).

### `value` vs `function` vs `functor` vs coupled-variable
- **`value`**: scalar constant (controllable). Steady boundary data.
- **`function`**: name of a `[Functions]` entry; varies in `(t,x,y,z)`. Most BCs have a `Function*` twin.
- **`functor`**: variable / function / functor mat-prop / wrapped postprocessor. Most general; on the `*Functor*` family (`FunctorDirichletBC`, `FVFunctorDirichletBC`, `FunctorNeumannBC`, all `LinearFVAdvectionDiffusionFunctor*`).
- **Coupled variable** (`v`): explicit coupling. Adds the variable's DOFs to the BC Jacobian footprint. Used by `MatchedValueBC`, `CoupledVarNeumannBC`, `CoupledTiedValueConstraint`.
- **Postprocessor** (`postprocessor`): reads the *current* PP value at residual time. Used by `Postprocessor*BC` for sub-app coupling.

### Mortar setup
Every mortar constraint (`EqualValueConstraint`, `EqualGradientConstraint`, `PenaltyEqualValueConstraint`, `PeriodicSegmentalConstraint`) requires **lower-d blocks** on each side of the interface, generated in `[Mesh]` by chained `LowerDBlockFromSidesetGenerator` entries (one per side, with `new_block_name = primary_lower` / `secondary_lower`). The Lagrange-multiplier `variable` (e.g. `lambda`) is declared with `block = 'secondary_lower'` in `[Variables]`. `secondary_variable` is the primal variable being constrained. `PenaltyEqualValueConstraint` skips the LM (no `variable` param). Canonical setup: `test/tests/mortar/convergence-studies/solution-continuity/continuity.i`. See [mesh.md](./mesh.md) for the generator.

### Periodic boundaries
Declared via the `[BCs/Periodic]` action sub-block (not a typed BC):

```hit
[BCs]
  [Periodic]
    [x]
      variable = u
      primary = 'left'
      secondary = 'right'
      translation = '1 0 0'
    []
  []
[]
```

Example: `test/tests/bcs/periodic/periodic_array_bc_test.i:48`. For periodic constraints with a non-zero jump (homogenization), use `PeriodicSegmentalConstraint` in `[Constraints]` instead.

### Sign convention for Neumann
`NeumannBC` enforces `du/dn = value` on the outward normal — i.e. `value > 0` means *outward*-pointing gradient (flux out of the domain for a `+(D grad u, grad psi)` Laplacian residual). `VacuumBC` adds `+(alpha/2 u, psi)_S`; `ADRobinBC` adds `+(coef u, psi)_S`. Flip signs in `function`/`value` if your physics convention treats flux-in as positive.

### Composition
- `block = subdomain` is *not* meaningful on BCs — sidesets already live between subdomains. For block-restricted soft Dirichlets use `[NodalKernels]` with `boundary` + `block`. Mortar constraints respect the lower-d primary/secondary subdomains declared in `[Mesh]`.
- Strong Dirichlet on a sideset overrides any integrated BC at the same nodes — pick one. Multiple integrated BCs (`DiffusionFluxBC` + `ConservativeAdvectionBC`) on the same sideset *do* compose; this is correct for full convection-diffusion outlets.

## Minimal scaffold

FE block: strong Dirichlet (left), function Neumann (right), Robin (top), zero Dirichlet (bottom):

```hit
[BCs]
  [left_strong]
    type = ADDirichletBC
    variable = u
    boundary = 'left'
    value = 1.0
  []
  [right_flux]
    type = ADFunctionNeumannBC
    variable = u
    boundary = 'right'
    function = flux_fn
  []
  [top_robin]
    type = ADRobinBC
    variable = u
    boundary = 'top'
    coefficient = 5.0
  []
  [bottom_zero]
    type = ADDirichletBC
    variable = u
    boundary = 'bottom'
    value = 0.0
  []
[]
```

FV variant — Dirichlet inlet, functor Neumann walls, outflow:

```hit
[FVBCs]
  [inlet]
    type = FVDirichletBC
    variable = u
    boundary = 'left'
    value = 1.0
  []
  [walls]
    type = FVFunctorNeumannBC
    variable = u
    boundary = 'top bottom'
    functor = 0.0
  []
  [outlet]
    type = FVConstantScalarOutflowBC
    variable = u
    boundary = 'right'
    velocity = '1 0 0'
  []
[]
```

Mortar `EqualValueConstraint` (requires `primary_lower` / `secondary_lower` from `LowerDBlockFromSidesetGenerator` and a `lambda` variable on `secondary_lower`):

```hit
[Constraints]
  [continuity]
    type = EqualValueConstraint
    variable = lambda
    secondary_variable = u
    primary_boundary = right_block_left
    secondary_boundary = left_block_right
    primary_subdomain = primary_lower
    secondary_subdomain = secondary_lower
  []
[]
```
