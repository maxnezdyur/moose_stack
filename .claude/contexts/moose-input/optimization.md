# Authoring inputs: Optimization

Reach for this guide when writing or editing a `.i` file driving a PETSc/TAO optimization (parameter identification, design, topology). The optimization module wraps TAO around a *main* MOOSE app holding the parameter vector and objective; one or more `FullSolveMultiApp` sub-apps run the forward (and adjoint) physics each TAO iteration. **This main + sub-app split is required** for almost every input; the only major exception is SIMP topology optimization, which bypasses TAO.

If the misfit is `(u_sim - u_meas)^2`, see `OptimizationReporter` + `OptimizationData`. For a custom scalar objective (compliance, energy, cost), see `GeneralOptimization`. For spatially-varying parameter fields on a separate FE mesh, see `ParameterMeshOptimization` + `ParameterMeshFunction`. For physics piece placement see [kernels.md](./kernels.md), [bcs.md](./bcs.md). Read the C++/architecture twin at `../moose/optimization-authoring.md` first if you don't yet know why this module needs the sub-app split.

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. Each entry cites the **source header** (`<file>:<class line>`) and one **canonical example .i**.

## When to use this (vs alternatives)

Pick the **executioner topology** first, then the **OptimizationReporter** type, then the **TAO solver**.

1. Executioner topology:
   - Steady forward + adjoint, one sub-app: `[Executioner] type = SteadyAndAdjoint` in the sub-app + `Optimize` in the main app.
   - Transient forward + adjoint, one sub-app: `TransientAndAdjoint` (handles backward-in-time adjoint sweep automatically).
   - Separate forward and adjoint sub-apps: two `FullSolveMultiApp`s with `execute_on = FORWARD` and `= ADJOINT`. Strictly more boilerplate; prefer combined.
   - SIMP topology optimization: `Steady` (or `Transient`) inside one app — no main app, no `Optimize`, no MultiApps. `DensityUpdate` + `SensitivityFilter` UOs do the design update.
   - Smoke-testing TAO on a closed-form quadratic: `Optimize` + `solve_on = none` + a self-contained reporter like `QuadraticMinimize`. No sub-apps.
2. `[OptimizationReporter]` type (registered at `modules/optimization/src/base/OptimizationApp.C:43`):
   - Misfit-based with built-in measurement plumbing: `OptimizationReporter` (deprecated alias since 12/31/2024 — works; new inputs prefer the next pattern with `OptimizationData` on the sub-app).
   - Custom scalar objective from sub-app: `GeneralOptimization`.
   - Spatially-varying parameter field on an Exodus parameter mesh: `ParameterMeshOptimization` (subclass of `GeneralOptimization`).
3. TAO solver (`tao_solver` enum at `modules/optimization/src/executioners/OptimizeSolve.C:21`):
   - Smooth, gradient-based, no constraints: `taolmvm` (unbounded) or `taobqnls`/`taoblmvm`/`taobqnktr` (bounded quasi-Newton).
   - Hessian-vector products available: `taontr`/`taobntr`.
   - Equality / inequality constraints: `taoalmm` (also needs `equality_names`/`inequality_names`).
   - Gradient-free fallback: `taonm` (Nelder-Mead), `taobncg`.
4. Parameter representation: a scalar list (`num_values = '4'` on `GeneralOptimization`) for 1–10 abstract numbers; a parameter mesh (`parameter_meshes = 'pmesh.e'`) for a spatial field — DOF count comes from the mesh's FE space and you get H1/L2 regularization via `regularization_types`.

Don't conflate this module with stochastic_tools — same Sampler/MultiApp machinery, different goal (UQ, surrogates, Bayesian inference; not TAO).

## Catalog

### `[Executioner]` — TAO driver

##### `Optimize`
- Source: `modules/optimization/include/executioners/Optimize.h:23`
- Example: `modules/optimization/examples/diffusion_reaction/optimize.i:67`
- Main-app executioner. TAO calls back into `objectiveFunction()` / `gradientFunction()` / `applyHessian()`; those run the forward/adjoint MultiApps controlled by `solve_on`.
- Required: `tao_solver` (one of `taontr taobntr taobncg taonls taobnls taobqnktr taontl taobntl taolmvm taoblmvm taonm taobqnls taoowlqn taogpcg taobmrm taoalmm`).
- Useful: `petsc_options_iname` / `petsc_options_value` (e.g. `-tao_gatol`, `-tao_grtol`, `-tao_gttol`, `-tao_max_it`, `-tao_max_funcs`, `-tao_almm_*`); `solve_on` (default `'FORWARD ADJOINT HOMOGENEOUS_FORWARD'`); `verbose = true`; `output_optimization_iterations`.

##### `SteadyAndAdjoint` (inside forward sub-app)
- Source: `modules/optimization/include/executioners/SteadyAndAdjoint.h:18`
- Example: `modules/optimization/test/tests/executioners/steady_and_adjoint/self_adjoint.i:51`
- Runs one Steady forward, then immediately the adjoint on a **second nonlinear system** declared in `[Problem]/nl_sys_names = 'nl0 adjoint'`.
- Required: `forward_system`, `adjoint_system`.
- Useful: standard Steady params (`nl_rel_tol`, `l_tol`).

##### `TransientAndAdjoint` (inside sub-app)
- Source: `modules/optimization/include/executioners/TransientAndAdjoint.h:18`
- Example: `modules/optimization/examples/diffusion_reaction/forward_and_adjoint.i:117`
- Forward in time storing each solution; adjoint sweeps backward replaying stored solutions.
- Required: `forward_system`, `adjoint_system`.
- Useful: standard Transient params (`dt`, `end_time`, `num_steps`).

### `[OptimizationReporter]` — top-level block

This is **not** `[Reporters]`. It's a dedicated top-level syntax wrapping a single `OptimizationReporterBase`-derived object. `OptimizeSolve` only introspects this base — a plain `[Reporters]/foo type = GeneralReporter` is silently ignored.

##### `OptimizationReporter` (deprecated alias)
- Source: `modules/optimization/include/optimizationreporters/OptimizationReporter.h:18`
- Example: search `modules/optimization/test/tests/optimizationreporter/optimizationdata/` for `type = OptimizationReporter`.
- Misfit-based; bundles measurement coords + values + simulated values inside the **main app**. Computes `f = 1/2 sum (u_sim - u_meas)^2 + tikhonov_coeff/2 |p|^2`.
- Required: `parameter_names` (vector of reporter value names — one per parameter group), `objective_name`, plus `OptimizationData`-style measurement params.
- Useful: `tikhonov_coeff` (default 0; coefficient regularization, NOT field), `equality_names`, `inequality_names`.

##### `GeneralOptimization`
- Source: `modules/optimization/include/optimizationreporters/GeneralOptimization.h:20`
- Example: `modules/optimization/test/tests/optimizationreporter/material/main.i:13`; constrained: `modules/optimization/test/tests/executioners/constrained/inequality/main_auto_adjoint.i:7`
- Sub-app computes the objective; this reporter just owns the scalar `_objective_val` and the parameter / gradient / constraint reporter vectors.
- Required: `parameter_names`, `objective_name`, `num_values` (vector — one per parameter group).
- Useful: `initial_condition`, `lower_bounds`, `upper_bounds`, `tikhonov_coeff`, `equality_names`, `inequality_names`, `num_values_name` (read DOF counts from a reporter).

##### `ParameterMeshOptimization`
- Source: `modules/optimization/include/optimizationreporters/ParameterMeshOptimization.h:18`
- Example: `modules/optimization/test/tests/optimizationreporter/mesh_source/main.i:5`; with regularization: `modules/optimization/test/tests/optimizationreporter/total_variation/optimizationReporterMeshIC.i:2`
- `GeneralOptimization` plus an Exodus parameter mesh — DOF count is set by the parameter mesh's FE space; can read ICs / bounds from named Exodus variables.
- Required: `parameter_names`, `objective_name`, `parameter_meshes` (vector of FileNames; one Exodus per parameter group).
- Useful: `parameter_families`, `parameter_orders`, `num_parameter_times`, `initial_condition_mesh_variable`, `lower_bounds_mesh_variable`, `upper_bounds_mesh_variable`, `exodus_timesteps_for_bounds_and_ics`, `regularization_types` (`L2|L2_GRADIENT|TOTAL_VARIATION`), `regularization_coeffs`, `tikhonov_coeff`. Pair with `ParameterMeshFunction` on sub-apps.

### `[MultiApps]` — forward / adjoint sub-app pattern

Cross-reference [multiapps.md](./multiapps.md) for full MultiApp params. Optimization-specific patterns:

##### `FullSolveMultiApp` for forward
- Required: `type = FullSolveMultiApp`, `input_files = forward.i`, `execute_on = FORWARD` (optimization-specific exec flag from `modules/optimization/include/base/OptimizationAppTypes.h`; do NOT use `TIMESTEP_END`).
- Useful: `cli_args` (`;`-separated overrides — switch a single sub-input between forward and adjoint mode); `clone_parent_mesh`; `positions`.

##### `FullSolveMultiApp` for adjoint (separate-sub-app pattern only)
- Required: `type = FullSolveMultiApp`, `input_files = adjoint.i`, `execute_on = ADJOINT`.
- Combined `SteadyAndAdjoint` / `TransientAndAdjoint` use only ONE MultiApp (forward); the sub-app's executioner runs both physics.
- For matrix-free `H s` (Hessian-vector), add a third sub-app with `execute_on = HOMOGENEOUS_FORWARD`.

### `[Transfers]` — parameter / gradient flow

Each TAO iteration: main pushes parameters down, sub-app(s) push back objective + gradient.

##### `MultiAppReporterTransfer` (parent -> forward: parameters + measurements)
- Example: `modules/optimization/examples/diffusion_reaction/optimize.i:36`
- Required: `to_multi_app = forward`, `from_reporters` / `to_reporters`. Parameters live at `OptimizationReporter/<param_name>` on the parent and typically land on a `ConstantReporter` named `params/<param_name>` on the sub-app. Misfit pattern also pushes `measurement_xcoord/ycoord/zcoord/time/values`.

##### `MultiAppReporterTransfer` (forward -> parent: objective + misfit)
- Example: `modules/optimization/examples/diffusion_reaction/optimize.i:53`
- Required: `from_multi_app = forward`, `from_reporters = '<data>/objective_value'`, `to_reporters = 'OptimizationReporter/objective_value'`. Misfit pattern also pulls `misfit_values`.

##### `MultiAppReporterTransfer` (parent -> adjoint, separate-sub-app only)
- Example: `modules/optimization/test/tests/optimizationreporter/material/main.i:88`
- Required: `to_multi_app = adjoint`; pushes `main/misfit_values` -> `misfit/misfit_values` plus measurement coords. The adjoint sub-app uses these in `[DiracKernels]/pt type = ReporterPointSource` to build `df/du`.

##### `MultiAppReporterTransfer` (adjoint sub-app -> parent: gradient)
- Example: `modules/optimization/examples/diffusion_reaction/optimize.i:53` (combined: pulls from forward MultiApp because the VPP runs there); `modules/optimization/test/tests/optimizationreporter/material/main.i:104` (separate)
- Required: `from_reporters = '<vpp>/inner_product'`, `to_reporters = 'OptimizationReporter/grad_<param_name>'`. The `grad_<name>` reporter is auto-declared by `OptimizationReporterBase` (header line 52).

##### `MultiAppCopyTransfer` (forward -> adjoint state field, separate pattern)
- Example: `modules/optimization/test/tests/optimizationreporter/material/main.i:74`
- Required: `from_multi_app = forward`, `to_multi_app = adjoint`, `source_variable`, `variable`. Used when the adjoint physics needs the converged forward field (e.g. nonlinear materials with `u`-dependent Jacobian). Combined executioners skip this — the field is already in scope.

### `[Mesh]` — parameter mesh

There is **no** `ParameterMeshGenerator`. The "parameter mesh" is just a regular Exodus file (typically produced by a separate `[Problem] solve = false` MOOSE run) that all three apps reference identically.

##### Producing a parameter mesh
- Example: `modules/optimization/examples/diffusion_reaction/parameter_mesh.i`
- Pattern: small `.i` with `[Problem] solve = false`, the desired `[Mesh]` (and optional `[Adaptivity]`), `[Outputs] exodus = true`. Run once before the optimization; reference its `*_out.e` everywhere `parameter_meshes` / `exodus_mesh` appears.

### `[Functions]` — parameter -> spatial field

##### `ParameterMeshFunction`
- Source: `modules/optimization/include/functions/ParameterMeshFunction.h:20`
- Example (forward): `modules/optimization/test/tests/optimizationreporter/mesh_source/forward.i:36`; (adjoint): `modules/optimization/test/tests/optimizationreporter/mesh_source/adjoint.i:58`
- Wraps a `ParameterMesh` + a reporter vector of values; uses FE shape functions for `p(x)`, `grad p(x)`, `dp/dt`. Time interpolation between snapshots is built in.
- Required: `exodus_mesh` (FileName, must match `parameter_meshes` on the main app), `parameter_name` (reporter path like `src_rep/vals`).
- Useful: `family`, `order` (must match parameter mesh), `parameter_times`.

##### `OptimizationFunction` (abstract base)
- Source: `modules/optimization/include/functions/OptimizationFunction.h:19`
- Subclass when you need a parameter-coupled function with closed-form `parameterGradient(t, p)` (not FE-mesh-based). See `../moose/optimization-authoring.md`.

##### `ParsedOptimizationFunction`
- Source: `modules/optimization/include/functions/ParsedOptimizationFunction.h`
- Example: `modules/optimization/test/tests/functions/parsed_function/`
- Parsed-expression function whose symbols include the optimization parameter vector.

##### `NearestReporterCoordinatesFunction`
- Source: `modules/optimization/include/functions/NearestReporterCoordinatesFunction.h`
- Example: `modules/optimization/test/tests/functions/nearest_reporter_coord/`
- Nearest-point lookup of a reporter-valued field at `(x, y, z, t)`.

### `[DiracKernels]` — adjoint forcing

##### `ReporterPointSource`
- Source: `framework/include/dirackernels/ReporterPointSource.h:21`
- Example: `modules/optimization/test/tests/optimizationreporter/mesh_source/adjoint.i:21`
- Misfit-based adjoint forcing for **steady** problems: delta-function source at each measurement point with magnitude `u_sim - u_meas`.
- Required: `variable` (adjoint var), `value_name` (e.g. `misfit/misfit_values`), `x_coord_name`, `y_coord_name`, `z_coord_name`.

##### `ReporterTimePointSource`
- Source: `modules/optimization/include/dirackernels/ReporterTimePointSource.h:18`
- Example: `modules/optimization/examples/diffusion_reaction/forward_and_adjoint.i:142`; `modules/optimization/test/tests/dirackernels/reporter_time_point_source.i:28`
- Same plus `time_name` so the source switches on/off per measurement timestep — required for **transient** misfit adjoints.
- Required: `variable`, `value_name`, `x_coord_name`, `y_coord_name`, `z_coord_name`, `time_name`.
- Useful: `weight_name`, `reverse_time_end`.

### `[Materials]` — optimization-aware

##### `ReporterOffsetFunctionMaterial` / `ADReporterOffsetFunctionMaterial`
- Source: `modules/optimization/include/materials/ReporterOffsetFunctionMaterial.h:27`
- Example: `modules/optimization/test/tests/optimizationreporter/reporter_offset/`
- `m(x) = sum_k func(x - p_k)` where offsets `p_k` come from a reporter. Smooth proxy for parameter-driven sources.
- Required: `property`, `points` OR (`coordx`, `coordy`, `coordz`), `function`.

##### `MisfitReporterOffsetFunctionMaterial` / `ADMisfitReporterOffsetFunctionMaterial`
- Source: `modules/optimization/include/materials/MisfitReporterOffsetFunctionMaterial.h:23`
- Same plus a `gradient` material property suitable for a smooth misfit objective in `[VectorPostprocessors]`.

##### `CostSensitivity`
- Source: `modules/optimization/include/materials/CostSensitivity.h:20`
- Example: `modules/optimization/test/tests/simp/2d_twoconstraints.i`
- SIMP-only: `dcost/drho` for `DensityUpdateTwoConstraints`. Pair with the solid_mechanics module's `SIMP*` materials.

### `[VectorPostprocessors]` — gradient assembly (adjoint side)

These assemble `dR/dp_i = (grad_p R(u; p)) . lambda` into the `inner_product` reporter vector that's transferred back to `OptimizationReporter/grad_<name>`.

##### `ElementOptimizationFunctionInnerProduct` (abstract base)
- Source: `modules/optimization/include/vectorpostprocessors/ElementOptimizationFunctionInnerProduct.h:15`
- Required: `variable` (adjoint), `function` (an `OptimizationFunction` — typically `ParameterMeshFunction`).

##### `ElementOptimizationSourceFunctionInnerProduct`
- Source: `modules/optimization/include/vectorpostprocessors/ElementOptimizationSourceFunctionInnerProduct.h:14`
- Example: `modules/optimization/test/tests/optimizationreporter/mesh_source/adjoint.i:65`
- For a `BodyForce`-shaped term `int f(x; p) psi` — gradient `int (df/dp_i) lambda`.
- Required: `variable`, `function`.

##### `ElementOptimizationReactionFunctionInnerProduct`
- Source: `modules/optimization/include/vectorpostprocessors/ElementOptimizationReactionFunctionInnerProduct.h:18`
- Example: `modules/optimization/examples/diffusion_reaction/forward_and_adjoint.i:153`
- For a reaction term `int rho(x; p) u psi` — gradient `int (drho/dp_i) u lambda`.
- Required: `variable` (adjoint), `function`, `forward_variable`.

##### `ElementOptimizationDiffusionCoefFunctionInnerProduct`
- Source: `modules/optimization/include/vectorpostprocessors/ElementOptimizationDiffusionCoefFunctionInnerProduct.h:14`
- Example: `modules/optimization/test/tests/vectorpostprocessors/element_source_inner_product/`
- For diffusion `int D(x; p) grad u . grad psi` — gradient `int (dD/dp_i) grad u . grad lambda`.
- Required: `variable` (adjoint), `function`, `forward_variable`.

##### `SideOptimizationNeumannFunctionInnerProduct`
- Source: `modules/optimization/include/vectorpostprocessors/SideOptimizationNeumannFunctionInnerProduct.h:14`
- Example: `modules/optimization/test/tests/executioners/constrained/inequality/forward_and_adjoint.i`
- For Neumann residual `int_Gamma g(x; p) psi` — gradient `int_Gamma (dg/dp_i) lambda`.
- Required: `variable`, `function`, `boundary`.

##### `AdjointStrainSymmetricStressGradInnerProduct`
- Source: `modules/optimization/include/vectorpostprocessors/AdjointStrainSymmetricStressGradInnerProduct.h`
- Example: `modules/optimization/test/tests/executioners/constrained/shape_optimization/`
- Solid-mechanics: contracts forward strain with adjoint strain weighted by `dC/dp`.

### `[Reporters]` — measurement, info, parameter holder, adjoint solution

##### `OptimizationData` (sub-app side)
- Source: `modules/optimization/include/reporters/OptimizationData.h:32`
- Example: `modules/optimization/test/tests/optimizationreporter/mesh_source/forward.i:48`
- Holds measurement coords + measured values + computed simulated values + misfit on the **sub-app**. Computes `_simulation_values` = `variable` evaluated at each `(x, y, z, t)` and `_misfit_values = _simulation_values - _measurement_values`.
- Required: typically nothing — provide either `measurement_points` + `measurement_values` directly OR `measurement_file` + `file_xcoord` / `file_ycoord` / `file_zcoord` / `file_time` / `file_value`.
- Useful: `variable` (the simulated state to sample), `objective_name` (default `objective_value`), `weight_names`.

##### `OptimizationInfo`
- Source: `modules/optimization/include/reporters/OptimizationInfo.h:17`
- Example: `modules/optimization/examples/diffusion_reaction/optimize.i:62`; `modules/optimization/test/tests/executioners/constrained/inequality/main_auto_adjoint.i:44`
- Pulls TAO solution status into reporter vectors for output (per-iteration `function_value`, `gnorm`, `cnorm`, `current_iterate`, etc.).
- Useful: `items` (subset of `current_iterate function_value gnorm cnorm xdiff total_iters obj_iters grad_iters hess_iters total_solves`).

##### `ConstantReporter` (parameter holder on sub-apps)
- Source: `framework/include/reporters/ConstantReporter.h`
- Pattern: every sub-app needs a `ConstantReporter` whose `real_vector_values` get **overwritten** by the parameter transfer each TAO iteration. It's how the parameter vector enters the sub-app. Pair with `ParameterMeshFunction parameter_name = src_rep/vals`.

##### `AdjointSolutionUserObject` (separate-sub-app pattern only)
- Source: `modules/optimization/include/userobjects/AdjointSolutionUserObject.h:14`
- Re-reads the adjoint Exodus on each timestep so the main app can pull updated `lambda` fields. Only needed when forward and adjoint live in **separate** sub-apps and the adjoint must be evaluated inside the forward problem.

### `[UserObjects]` — SIMP topology optimization

These bypass TAO. `[Executioner]` is `Steady` or `Transient` inside a single (no-sub-app) input.

##### `DensityUpdate`
- Source: `modules/optimization/include/userobjects/DensityUpdate.h:19`
- Example: `modules/optimization/test/tests/simp/2d.i:107`
- Optimality-criterion bisection on a filtered sensitivity. Updates design density `rho` subject to a volume-fraction constraint.
- Required: `design_density`, `density_sensitivity`, `volume_fraction`.
- Useful: `execute_on = TIMESTEP_BEGIN`, `lower_bound`, `upper_bound`.

##### `DensityUpdateTwoConstraints`
- Source: `modules/optimization/include/userobjects/DensityUpdateTwoConstraints.h:19`
- Example: `modules/optimization/test/tests/simp/2d_twoconstraints.i`
- Two constraints (e.g. mass + cost). Pair with `CostSensitivity` material.

##### `SensitivityFilter`
- Source: `modules/optimization/include/userobjects/SensitivityFilter.h:20`
- Example: `modules/optimization/test/tests/simp/2d.i:114`
- Filters raw compliance sensitivity via a `RadialAverage` to suppress checkerboarding.
- Required: `design_density`, `density_sensitivity`, `filter_UO` (a `RadialAverage` UO).
- Useful: `execute_on = TIMESTEP_END`, `force_postaux = true`. Pair with a framework `RadialAverage` UO (`radius`, `weights`, `prop_name`).

## Cross-cutting concerns

### Forward / adjoint sub-app symmetry

Forward sub-app sees `p`, outputs `objective_value` (and optionally state-variable fields). Adjoint side sees `p` plus the misfit/objective-gradient and outputs `inner_product`. Each TAO iteration: forward, then adjoint, then `OptimizeSolve::computeGradient` copies `OptimizationReporter/grad_<name>` into the PETSc gradient.

### Adjoint kernel/BC setup

`SteadyAndAdjoint` / `TransientAndAdjoint` configure adjoint physics on a **second nonlinear system** declared in `[Problem]/nl_sys_names = 'nl0 adjoint'`, with `solver_sys = adjoint` on the adjoint variables; their `[Kernels]` and `[BCs]` auto-attach to that system. For self-adjoint operators (Laplacian) the adjoint kernel matches the forward; the **source** is `df/du` — a `ReporterPointSource` for misfit objectives, a `BodyForce` proportional to displacement for compliance. Apply **zero-Dirichlet** on `Gamma_D` (where the forward had Dirichlet) — the original forward Dirichlet value yields a wrong gradient.

### Transfer direction mnemonic

- `to_multi_app = forward` -> push parameters (and measurements) DOWN.
- `from_multi_app = forward` -> pull objective (and misfit) UP.
- `to_multi_app = adjoint` -> push misfit + parameters DOWN (separate-sub-app only).
- `from_multi_app = adjoint` (or from forward if combined) -> pull `inner_product` -> `grad_<name>` UP.

`OptimizationReporter/<param_name>` on the parent is auto-declared by `OptimizationReporterBase`. On the sub-app you choose where parameters land — convention is `params/<param_name>` or `<param>_rep/vals`.

### `cli_args` to switch one sub-input between modes

When one `forward.i` plays both roles (separate-sub-app pattern with shared physics), pass `cli_args` per MultiApp to flip output knobs / load forward solutions, e.g. `cli_args = 'Outputs/console=false;UserObjects/load_u/mesh=optimize_grad_out_forward0.e'` (`modules/optimization/examples/materialTransient/optimize_grad.i:37`). For experiment-loop sweeps, per-instance overrides like `cli_args = 'omega=2.0'`.

### Data-misfit objectives via measurement reporters

`[Reporters]/main type = OptimizationData` on the main app holds measurement coords + values; transfer them to `[Reporters]/measure_data type = OptimizationData` on the sub-app along with `OptimizationReporter/<param>`. The sub-app's `OptimizationData` automatically computes `_simulation_values` and `_misfit_values`. Pull `objective_value` (and `misfit_values` for the adjoint) back. Adjoint sub-app uses `ReporterPointSource` (steady) / `ReporterTimePointSource` (transient) with `value_name = misfit/misfit_values`.

### Tikhonov vs field regularization

`tikhonov_coeff` adds `rho/2 * sum p_i^2` regardless of mesh — coefficient regularization. To regularize the *field* (`1/2 |grad p|^2`), use `ParameterMeshOptimization` with `regularization_types = L2_GRADIENT` and `regularization_coeffs`.

### Parameter mesh consistency

Main app, forward sub-app, adjoint sub-app must reference the **same** Exodus parameter mesh and the **same** FE family/order. Mismatched FE types silently produce wrong gradients (the parameter PETSc vector is interpreted with the wrong shape functions on the sub-app side).

### SIMP topology workflow

Single input: `[Executioner] type = Steady` (or pseudo-time `Transient`); `[AuxVariables]/mat_den` + `[AuxVariables]/Dc`; `[Materials]` defining the SIMP-penalized stiffness/conductivity; `[UserObjects]` containing `RadialAverage` + `SensitivityFilter` + `DensityUpdate`. No `[Optimization]` block, no `Optimize`, no MultiApps. Design vector lives in `mat_den` and is updated every step.

### TAO constraints and gradient-free fallback

Box bounds only: pick a `BOUNDED_*` solver (`taoblmvm`, `taobqnls`, `taobqnktr`, `taobncg`) and set `lower_bounds` / `upper_bounds`. Equality / inequality: `tao_solver = taoalmm`, declare `equality_names` / `inequality_names` (auto-declares `<name>` and `grad_<name>` reporter vectors); have the sub-app fill them. ALMM tuning via PETSc options like `-tao_almm_type phr -tao_almm_mu_factor 1.1 -tao_almm_subsolver_tao_type bqnktr`. Gradient-free fallback: `tao_solver = taonm` (Nelder-Mead) needs only the objective — skip the adjoint sub-app, VPPs, and gradient transfers. Slow; use only for low-dimensional verification.

## Minimal scaffold

A complete steady misfit-based optimization with a parameter mesh, combined forward+adjoint via `SteadyAndAdjoint`. First run a tiny one-shot mesh producer (a `.i` with `[Mesh/gmg] type=GeneratedMeshGenerator dim=2 nx=4 ny=4`, `[Problem] solve=false`, `[Executioner] type=Steady`, `[Outputs] exodus=true`) to get `parameter_mesh_out.e`. Then run the two files below.

`main.i` (TAO driver):

```hit
[Optimization]
[]

[OptimizationReporter]
  type = ParameterMeshOptimization
  objective_name = objective_value
  parameter_names = 'reaction_rate'
  parameter_meshes = 'parameter_mesh_out.e'
  initial_condition = 0
  lower_bounds = 0
  regularization_types = L2_GRADIENT
  regularization_coeffs = 1e-3
[]

[Reporters]
  [main]
    type = OptimizationData
    measurement_points = '0.25 0.25 0   0.75 0.75 0'
    measurement_values = '0.10 0.30'
  []
  [optInfo]
    type = OptimizationInfo
    items = 'current_iterate function_value gnorm'
  []
[]

[MultiApps/forward]
  type = FullSolveMultiApp
  input_files = forward_and_adjoint.i
  execute_on = FORWARD
[]

[Transfers]
  [to_forward]
    type = MultiAppReporterTransfer
    to_multi_app = forward
    from_reporters = 'main/measurement_xcoord main/measurement_ycoord main/measurement_zcoord
                      main/measurement_time main/measurement_values
                      OptimizationReporter/reaction_rate'
    to_reporters   = 'data/measurement_xcoord data/measurement_ycoord data/measurement_zcoord
                      data/measurement_time data/measurement_values
                      params/reaction_rate'
  []
  [from_forward]
    type = MultiAppReporterTransfer
    from_multi_app = forward
    from_reporters = 'data/objective_value adjoint_grad/inner_product'
    to_reporters   = 'OptimizationReporter/objective_value OptimizationReporter/grad_reaction_rate'
  []
[]

[Executioner]
  type = Optimize
  tao_solver = taobqnls
  petsc_options_iname = '-tao_gatol -tao_max_it'
  petsc_options_value = '1e-4 50'
  solve_on = NONE
  verbose = true
[]

[Outputs]
  csv = true
[]
```

`forward_and_adjoint.i` (one sub-app, both physics on a second nl_sys):

```hit
[Mesh/gmg]
  type = GeneratedMeshGenerator
  dim = 2
  nx = 16
  ny = 16
[]

[Problem]
  nl_sys_names = 'nl0 adjoint'
[]

[Variables]
  [u]
  []
  [u_adjoint]
    solver_sys = adjoint
  []
[]

[Reporters]
  [params]
    type = ConstantReporter
    real_vector_names = 'reaction_rate'
    real_vector_values = '0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0'
    outputs = none
  []
  [data]
    type = OptimizationData
    variable = u
    objective_name = objective_value
  []
[]

[Functions/rxn]
  type = ParameterMeshFunction
  exodus_mesh = parameter_mesh_out.e
  parameter_name = params/reaction_rate
[]

[Materials/neg_rxn]
  type = ADParsedMaterial
  expression = '-rxn'
  functor_names = 'rxn'
  property_name = 'neg_rxn_prop'
[]

[Kernels]
  [diff]
    type = ADDiffusion
    variable = u
  []
  [rxn_term]
    type = ADMatReaction
    variable = u
    reaction_rate = neg_rxn_prop
  []
  [src]
    type = ADBodyForce
    variable = u
    value = 1
  []
  [adj_diff]
    type = Diffusion
    variable = u_adjoint
  []
[]

[BCs]
  [forward_d]
    type = DirichletBC
    variable = u
    boundary = 'left bottom'
    value = 0
  []
  [adjoint_d]
    type = DirichletBC
    variable = u_adjoint
    boundary = 'left bottom'
    value = 0
  []
[]

[DiracKernels/misfit]
  type = ReporterPointSource
  variable = u_adjoint
  value_name = data/misfit_values
  x_coord_name = data/measurement_xcoord
  y_coord_name = data/measurement_ycoord
  z_coord_name = data/measurement_zcoord
[]

[VectorPostprocessors/adjoint_grad]
  type = ElementOptimizationReactionFunctionInnerProduct
  variable = u_adjoint
  forward_variable = u
  function = rxn
  execute_on = ADJOINT_TIMESTEP_END
[]

[Executioner]
  type = SteadyAndAdjoint
  forward_system = nl0
  adjoint_system = adjoint
  nl_rel_tol = 1e-12
[]
```
