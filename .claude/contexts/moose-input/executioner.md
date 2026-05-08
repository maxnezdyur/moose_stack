# Authoring inputs: Executioner & Problem (the solve loop)

Reach for this guide when you need to pick the **Executioner** for a `.i` file and tune the surrounding solve (PETSc options, time-stepper, time-integrator, predictor) — and to decide whether to override the default `[Problem]`. If you're configuring the preconditioner itself, see [preconditioning.md](./preconditioning.md). If you're tuning multi-app fixed-point coupling, see [multiapps.md](./multiapps.md). Adaptivity inside the solve is `[Executioner/Adaptivity]`; the standalone `[Adaptivity]` block runs *between* solves — see [adaptivity.md](./adaptivity.md).

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. Each catalog entry cites both the **source header** (`<file>:<line of class>`) and one **canonical example .i** (`<file>:<line of the sub-block>`).

## When to use this (vs alternatives)

Decide on **steady vs transient vs eigen vs optimize**, then pick **solve type**, then drop in a **time stepper / integrator** if transient.

1. Single nonlinear solve, no time dependence: **`type = Steady`**. This is the default for diffusion, steady-state heat conduction, mechanical equilibrium without inertia, etc.
2. Multiple solves marching in time (with `du/dt` kernels somewhere): **`type = Transient`**. Even a single-step pseudo-transient counts.
3. Generalized eigenvalue problem `A x = k B x` (criticality, buckling): **`type = Eigenvalue`** with a `[Problem] type = EigenProblem`. For older or simpler use-cases use `InversePowerMethod` or `NonlinearEigen`.
4. PDE-constrained optimization (forward + adjoint): **`type = Optimize`** at the top app and **`type = SteadyAndAdjoint`** / **`TransientAndAdjoint`** at the sub-app — this is the optimization module's domain, see [optimization.md](./optimization.md). Defer details there.
5. Pure linear-FV solve (no Newton, assemble matrix + RHS once per step): use `Steady` or `Transient` and set `solve_type = LINEAR`. Variables must be `MooseLinearVariableFVReal` and kernels must come from `[LinearFVKernels]` — see [kernels.md](./kernels.md).

`solve_type` selection:

- **`NEWTON`** — exact Newton with a real Jacobian. Best convergence, requires correct Jacobian (use `AD*` kernels or write the Jac yourself). Default for AD inputs.
- **`PJFNK`** — preconditioned Jacobian-Free Newton-Krylov. Tolerates incorrect/missing Jacobian entries; preconditioner is built from whatever Jacobian you provide. Slower per iteration than NEWTON. Common in legacy non-AD inputs.
- **`LINEAR`** — assemble linear system once, solve once per step. Only valid with `[LinearFVKernels]` or fully linear FE problems.
- **`FD`** — finite-difference Jacobian. Debug-only; very expensive.

## Catalog

### Executioners

##### `Steady`
- Source: `framework/include/executioners/Steady.h:17`
- Example: `test/tests/executioners/executioner/steady.i:68` (sub-block `[Executioner]`)
- One nonlinear solve. No `dt`/`num_steps`. Pair with all-nonzero residual contributions (no `TimeDerivative` kernels).
- Required: `solve_type` (`NEWTON|PJFNK|LINEAR|FD`).
- Useful: `petsc_options_iname`/`petsc_options_value`, `nl_rel_tol`, `nl_abs_tol`, `l_tol`, `automatic_scaling`, `line_search`.

##### `Transient`
- Source: `framework/include/executioners/Transient.h:20`
- Example: `test/tests/executioners/executioner/transient.i:105`
- Time-marching loop. Drives a `[TimeStepper]` and `[TimeIntegrator]` sub-block (or pick a built-in `scheme`).
- Required: `solve_type`. Plus one of: `dt` + (`num_steps` | `end_time`), or a `[TimeStepper]` sub-block.
- Useful: `start_time` (default 0), `scheme` (legacy shortcut, see TimeIntegrators below), `dtmin`, `dtmax`, `n_startup_steps`, `steady_state_detection`, `steady_state_tolerance`, `abort_on_solve_fail`.

##### `Eigenvalue`
- Source: `framework/include/executioners/Eigenvalue.h:28`
- Example: `test/tests/problems/eigen_problem/initial_condition/ne_ic.i:52`
- General-purpose eigenvalue solver (SLEPc-backed). **Must** be paired with `[Problem] type = EigenProblem`. Mark eigen kernels with `extra_vector_tags = eigen` or use `*EigenKernel` classes.
- Required: `solve_type` (typically `PJFNK` or `NEWTON`).
- Useful: `which_eigen_pairs` (`LARGEST_MAGNITUDE|SMALLEST_MAGNITUDE|...`), `n_eigen_pairs`, `n_basis_vectors`, `eigen_problem_type` (`GEN_NON_HERMITIAN|...`), `free_power_iterations`, `nonlinear_eigen` (toggle nonlinear eigen).

##### `InversePowerMethod`
- Source: `framework/include/executioners/InversePowerMethod.h:14`
- Example: `test/tests/executioners/eigen_executioners/ipm.i:96`
- Hand-rolled inverse-power iteration (one Newton solve per outer iteration). Useful for criticality search where SLEPc isn't available or for didactic clarity. Pair with `EigenProblem`.
- Required: `solve_type`, `bx_norm` (postprocessor name normalizing the Bx vector).
- Useful: `k0` (initial eigenvalue guess), `min_power_iterations`, `max_power_iterations`, `xdiff` (convergence postprocessor), `eig_check_tol`.

##### `NonlinearEigen`
- Source: `framework/include/executioners/NonlinearEigen.h:14`
- Example: `test/tests/executioners/eigen_executioners/ne.i:54`
- Inverse-power outer + nonlinear inner (handles eigenvalue problems with nonlinear residual contributions, e.g. neutronics with thermal feedback). Pair with `EigenProblem`.
- Required: `solve_type`, `bx_norm`.
- Useful: `free_power_iterations` (linear warmup), `nl_abs_tol`, `source_abs_tol`, `pfactor`.

##### `SteadyAndAdjoint` (optimization module)
- Source: `modules/optimization/include/executioners/SteadyAndAdjoint.h:18`
- Example: `modules/optimization/test/tests/executioners/steady_and_adjoint/adjoint_rhs.i:166`
- Runs the forward `Steady` solve, then the adjoint solve in the same executioner. Sub-app of an `Optimize` parent. See [optimization.md](./optimization.md).
- Required: `solve_type`. Plus an `[Adjoint]` sub-block defining the adjoint variables/kernels.

##### `TransientAndAdjoint` (optimization module)
- Source: `modules/optimization/include/executioners/TransientAndAdjoint.h:18`
- Example: `modules/optimization/test/tests/executioners/transient_and_adjoint/self_adjoint.i`
- Transient analog of `SteadyAndAdjoint`. Stores forward solutions for backward-in-time adjoint sweep.

##### `Optimize` (optimization module)
- Source: `modules/optimization/include/executioners/Optimize.h:23`
- Example: `modules/optimization/test/tests/executioners/constrained/equality/quadratic_minimize_constrained.i`
- Outer optimization loop driving a forward+adjoint sub-app via TAO. Top-level executioner in the parent app. Defer details to [optimization.md](./optimization.md).

### Time steppers (`[Executioner/TimeStepper]`)

Time steppers pick the next `dt`. The `[TimeStepper]` sub-block sits inside `[Executioner]`. Multiple steppers can be composed via `[TimeSteppers]` (top-level inside `[Executioner]`) which builds a `CompositionDT` automatically.

##### `ConstantDT`
- Source: `framework/include/timesteppers/ConstantDT.h:14`
- Example: `test/tests/time_steppers/constant_dt/constant_dt.i:56` (sub-block `[TimeStepper]`)
- Fixed `dt` every step.
- Required: `dt`.
- Useful: `growth_factor` (cap on dt change after a cutback).

##### `IterationAdaptiveDT`
- Source: `framework/include/timesteppers/IterationAdaptiveDT.h:32`
- Example: `test/tests/time_steppers/iteration_adaptive/adapt_tstep_shrink_init_dt.i:48`
- Grows/shrinks dt based on nonlinear/linear iteration counts. The default workhorse for stiff transient problems.
- Required: `dt` (initial).
- Useful: `optimal_iterations`, `iteration_window`, `growth_factor`, `cutback_factor`, `linear_iteration_ratio`, `timestep_limiting_postprocessor`, `timestep_limiting_function`, `force_step_every_function_point`.

##### `FunctionDT`
- Source: `framework/include/timesteppers/FunctionDT.h:18`
- Example: `test/tests/time_steppers/function_dt/function_dt_no_interpolation.i:79`
- `dt(t)` from a `Function`. Use when you have a known time-dependence schedule.
- Required: `function`.
- Useful: `min_dt`, `interpolate` (default true; false to step the function as a piecewise-constant table).

##### `TimeSequenceStepper`
- Source: `framework/include/timesteppers/TimeSequenceStepper.h:18`
- Example: `test/tests/time_steppers/timesequence_stepper/timesequence_restart1.i:70`
- Hits an explicit list of times.
- Required: `time_sequence`.

##### `CSVTimeSequenceStepper`
- Source: `framework/include/timesteppers/CSVTimeSequenceStepper.h:23`
- Example: search `test/tests/time_steppers/timesequence_stepper` for `type = CSVTimeSequenceStepper`.
- TimeSequenceStepper but the times come from a CSV column.
- Required: `file_name`, `column_name`.

##### `ExodusTimeSequenceStepper`
- Source: `framework/include/timesteppers/ExodusTimeSequenceStepper.h:18`
- Example: search `test/tests/time_steppers/timesequence_stepper` for `type = ExodusTimeSequenceStepper`.
- Steps to the times stored in an Exodus file (e.g. replay a prior run).
- Required: `mesh`.

##### `PostprocessorDT`
- Source: `framework/include/timesteppers/PostprocessorDT.h:18`
- Example: `test/tests/time_steppers/postprocessor_dt/postprocessor_dt.i:89`
- `dt` from a postprocessor (e.g. CFL number computed each step).
- Required: `postprocessor`.
- Useful: `dt` (initial), `factor`, `offset`.

##### `LogConstantDT`
- Source: `framework/include/timesteppers/LogConstantDT.h:16`
- Example: `test/tests/time_steppers/logconstant_dt/logconstant_dt.i:48`
- Logarithmically-spaced time steps (creep, diffusion across many decades).
- Required: `log_dt`, `first_dt`.

##### `SolutionTimeAdaptiveDT`
- Source: `framework/include/timesteppers/SolutionTimeAdaptiveDT.h:19`
- Example: `test/tests/time_steppers/time_adaptive/time_adaptive.i`
- Adapts `dt` based on wall-clock time per step (cost-based).
- Required: `dt`.

##### `FixedPointIterationAdaptiveDT`
- Source: `framework/include/timesteppers/FixedPointIterationAdaptiveDT.h:17`
- Example: `test/tests/time_steppers/fixed_point_iteration_adaptive_dt/fp_adaptive_dt.i`
- Like `IterationAdaptiveDT` but driven by Picard / fixed-point iteration counts (multi-app coupling).
- Required: `target_iterations`, `target_window`.

##### `CompositionDT` (auto-built from `[TimeSteppers]`)
- Source: `framework/include/timesteppers/CompositionDT.h:27`
- Example: `test/tests/time_steppers/time_stepper_system/time_stepper_system.i`
- Takes the min of multiple steppers. Use `[TimeSteppers]` block (note plural) inside `[Executioner]` and just list the children.

### Time integrators (`[Executioner/TimeIntegrator]`)

Time integrators discretize `du/dt`. Either set `scheme = ...` directly on `[Executioner]` (legacy shortcut, only for the simple choices listed in `TransientBase.C:84`) or add an explicit `[TimeIntegrator]` sub-block (required for everything else, including DIRK and Newmark-Beta with non-default params).

##### `ImplicitEuler`
- Source: `framework/include/timeintegrators/ImplicitEuler.h:17`
- Example: `test/tests/time_integrators/implicit-euler/ie.i:86` (`scheme = 'implicit-euler'`)
- First-order BDF1. Default `scheme`. Robust, dissipative, never use it for second-order accuracy.

##### `BDF2`
- Source: `framework/include/timeintegrators/BDF2.h:18`
- Example: `test/tests/time_integrators/bdf2/bdf2.i:95` (`scheme = 'bdf2'`)
- Second-order backward differentiation. Standard choice for most stiff transient problems. Bootstraps with one BDF1 step.

##### `CrankNicolson`
- Source: `framework/include/timeintegrators/CrankNicolson.h:22`
- Example: `test/tests/time_integrators/crank-nicolson/cranic_adapt.i:74` (sub-block `[TimeIntegrator]`)
- Second-order trapezoidal rule. Less dissipative than BDF2 but can ring on stiff problems.

##### `ExplicitEuler`
- Source: `framework/include/timeintegrators/ExplicitEuler.h:17`
- Example: `test/tests/time_integrators/explicit-euler/ee-2d-linear.i:87` (`scheme = 'explicit-euler'`)
- First-order explicit. Stable only for very small `dt`. Use `ActuallyExplicitEuler` if you want explicit *and* a lumped/consistent mass matrix solve.

##### `ActuallyExplicitEuler`
- Source: `framework/include/timeintegrators/ActuallyExplicitEuler.h:18`
- Example: `test/tests/time_integrators/actually_explicit_euler/actually_explicit_euler.i:48`
- Truly explicit: solves `M u_dot = -R(u_old)` once per step. Requires a `MassMatrix` kernel and `extra_tag_matrices` set on `[Problem]`.
- Required: pair with `solve_type = LINEAR`.
- Useful: `solve_type = consistent|lumped|lump_preconditioned`.

##### `CentralDifference`
- Source: `framework/include/timeintegrators/CentralDifference.h:18`
- Example: `test/tests/time_integrators/central-difference/central_difference.i`
- Explicit second-order, the canonical choice for explicit dynamics (wave propagation, impact). Inherits from `ActuallyExplicitEuler`.

##### `NewmarkBeta`
- Source: `framework/include/timeintegrators/NewmarkBeta.h:18`
- Example: `test/tests/time_integrators/newmark-beta/newmark_beta_prescribed_parameters.i:67`
- Standard Newmark-Beta for structural dynamics (couples displacement, velocity, acceleration). HHT-alpha damping is achieved via `alpha` on the matching `InertialForce` kernel — there is no separate `HHT` time integrator class.
- Required: `beta`, `gamma`.

##### `LStableDirk2` / `LStableDirk3` / `LStableDirk4` / `AStableDirk4`
- Source: `framework/include/timeintegrators/LStableDirk2.h:38` / `LStableDirk3.h:40` / `LStableDirk4.h:51` / `AStableDirk4.h:51`
- Example: `test/tests/time_integrators/dirk/dirk-2d-heat.i:89`
- Diagonally-implicit Runge-Kutta. Higher-order than BDF2, multiple internal stages. Use when temporal accuracy matters (combustion, kinetics).

##### `ExplicitSSPRungeKutta`
- Source: `framework/include/timeintegrators/ExplicitSSPRungeKutta.h:17`
- Example: `test/tests/time_integrators/explicit_ssp_runge_kutta/explicit_ssp_runge_kutta.i`
- Strong-stability-preserving explicit RK (orders 1-3). Use for hyperbolic problems with shocks.
- Required: `order`.

### Problem types (`[Problem]`)

The default is `FEProblem` — most inputs omit `[Problem]` entirely. Override only when you need eigen, reference-residual convergence, no-solve dump, or external coupling.

##### `FEProblem` (default)
- Source: `framework/include/problems/FEProblem.h:20`
- Example: `test/tests/problems/no_solve/no_solve.i:22` (with `solve = false`)
- Standard FE problem. Top-level params are inherited from `FEProblemBase`: `coord_type`, `coord_block`, `kernel_coverage_check`, `material_coverage_check`, `solve` (default true), `extra_tag_matrices`, `extra_tag_vectors`, `extra_tag_solutions`, `error_on_jacobian_nonzero_reallocation`, `verbose_setup`, `near_null_space_dimension`, `null_space_dimension`.

##### `EigenProblem`
- Source: `framework/include/problems/EigenProblem.h:21`
- Example: `test/tests/problems/eigen_problem/eigensolvers/ne.i`
- Required pairing for `Eigenvalue`/`InversePowerMethod`/`NonlinearEigen` executioners. Splits residual into `A` (regular) and `B` (eigen-tagged) parts. Eigen kernels must set `extra_vector_tags = eigen` or use `*EigenKernel` types.
- Useful: `negative_sign_eigen_kernel` (default true), `bx_norm`, `active_eigen_index`.

##### `ReferenceResidualProblem`
- Source: `framework/include/problems/ReferenceResidualProblem.h:19`
- Example: `test/tests/problems/reference_residual_problem/abs_ref.i:11`
- Wraps `FEProblem` to compute a *reference* residual once and use it as the convergence yardstick — robust when residuals span many orders of magnitude across variables (mechanics + thermal). Pair with `nl_rel_tol` on the executioner.
- Useful: `reference_vector` (vector tag holding the reference residual), `extra_tag_vectors = ref` (must declare on the same `[Problem]`), `acceptable_iterations`, `acceptable_multiplier`, `group_variables`.

##### `DumpObjectsProblem`
- Source: `framework/include/problems/DumpObjectsProblem.h:36`
- Example: `test/tests/problems/dump_objects/add_mat_and_kernel.i:9`
- Debugging only: print the validated input deck (after Action expansion) instead of solving. Pair with `[Executioner] type = Steady` to keep things simple — solve never runs.
- Useful: `dump_path` (subset of objects).

##### `ExternalProblem`
- Source: `framework/include/problems/ExternalProblem.h:14`
- Example: `test/tests/problems/external_problem/external_steady.i`
- Base class for embedding an external code; you typically don't instantiate `ExternalProblem` directly but a derived class from a coupling app.

##### Top-level `[Problem]` params worth knowing
- `solve = false` — skip the Newton/eigen solve. Useful for mesh-only checks or aux-only postprocessing runs.
- `kernel_coverage_check` (default `true`, also `false`/`SKIP_LIST`/`ONLY_LIST`) — error if a subdomain has no kernels. Set `false` for staggered solves where one subdomain only carries aux variables.
- `material_coverage_check` (default `true`) — same idea for materials.
- `coord_type = 'XYZ RZ RSPHERICAL'` (per `coord_block`) — switch axisymmetric / spherical. See `test/tests/problems/mixed_coord/mixed_coord_test.i:3`.
- `extra_tag_matrices = 'mass'` — declares matrix tags so `MassMatrix` and friends have somewhere to assemble. Required for `ActuallyExplicitEuler`.
- `extra_tag_vectors = 'ref eigen'` — declares vector tags for reference-residual and eigen problems.

## Cross-cutting concerns

### PETSc options

`petsc_options_iname`/`petsc_options_value` are paired arrays. Common patterns:

- **Direct solve (small / debugging)**: `'-pc_type' = 'lu'`; in parallel add `'-pc_factor_mat_solver_type' = 'mumps'`.
- **Algebraic multigrid (scalar elliptic — diffusion, heat conduction)**: `'-pc_type -pc_hypre_type' = 'hypre boomeramg'`. Tune `-pc_hypre_boomeramg_strong_threshold` for anisotropy.
- **Eigen problems**: `'-eps_type' = 'krylovschur'`, `'-st_type' = 'sinvert'`, `'-st_pc_type' = 'lu'` (SLEPc).
- **FGMRES vs GMRES**: use `'-ksp_type' = 'fgmres'` whenever the preconditioner contains a Krylov solve (nested PC); otherwise default `gmres` is fine.
- **Newton variant**: `'-snes_type' = 'newtontr'` for trust region; don't set `-snes_type` and `line_search` to conflicting values.

`petsc_options` (no suffix) is the boolean-flag list: `petsc_options = '-snes_converged_reason -ksp_monitor_true_residual'`.

### Convergence tolerances

- `nl_rel_tol` (default `1e-8`) and `nl_abs_tol` (default `1e-50`) — `nl_abs_tol` is effectively off by default; raise to `~1e-10` for O(1) residuals.
- `nl_max_its` (default 50), `nl_div_tol` (default `1e10`).
- `l_tol` (default `1e-5`), `l_max_its` (default 10000) — relative to RHS. With a tight `nl_abs_tol` loosen `l_tol` to `1e-3` to avoid over-solving inside Newton.
- For reference-residual problems, `nl_rel_tol` is taken against the reference vector — see `ReferenceResidualProblem` above.

### `automatic_scaling` & `line_search`

- `automatic_scaling = true` rescales each variable by the diagonal of the Jacobian — invaluable when variables span many orders of magnitude (displacements in m alongside temperatures in K). Combine with `compute_scaling_once = false` to refresh each step.
- `line_search = 'none|basic|bt|cp|l2|...'`. Default `bt` (backtracking). Use `'none'` for smooth quadratic problems; `'l2'` for stiff inelastic mechanics.
- `compute_initial_residual_before_preset_bcs` (default false) — flip true only if the very first residual must include Dirichlet violation.

### Predictor

`[Executioner/Predictor]` accelerates transient solves by extrapolating the next time step's initial guess. The only registered types in framework are `SimplePredictor` and `AdamsPredictor` (multi-step variant).

##### `SimplePredictor`
- Source: `framework/include/predictors/SimplePredictor.h:36`
- Example: `test/tests/predictors/simple/predictor_skip_test.i:67` (sub-block `[Predictor]`)
- Linear extrapolation `u_init = u_old + scale * (u_old - u_older)`. Halves Newton-iter counts on smooth transients; can blow up on shocks.
- Required: `scale` (e.g. 1.0 for full extrapolation, 0.5 for half).
- Useful: `skip_after_failed_timestep`, `skip_times`, `skip_times_old`.

### Adaptivity sub-block vs top-level `[Adaptivity]`

- `[Executioner/Adaptivity]` (steady) refines **between Newton solves**; (transient) refines once per time step before the solve. This is the modern path.
- Top-level `[Adaptivity]` is a separate parser kept for backward compatibility. Prefer the executioner sub-block. See [adaptivity.md](./adaptivity.md) for indicators/markers.

### Coupling with `[Preconditioning]`

For `solve_type = NEWTON` the executioner assembles the Jacobian; `[Preconditioning]` controls the *preconditioner* of the linear solve inside Newton. Without an explicit `[Preconditioning]` block, MOOSE falls back to `ilu` (serial) / `bjacobi` (parallel) — usually too weak for multi-variable problems. Always add at least `[Preconditioning] [SMP] type = SMP; full = true; []`. See [preconditioning.md](./preconditioning.md).

### Mesh-only & MultiApp

- `--mesh-only` on the command line writes the mesh to Exodus and exits without an executioner. `[Problem] solve = false` constructs the full action chain but skips the Newton solve.
- Multi-app (Picard) coupling uses the parent `[Executioner]`'s `fixed_point_*` parameters (`fixed_point_max_its`, `fixed_point_rel_tol`, `relaxation_factor`, `accept_on_max_fixed_point_iteration`) plus `[MultiApps]` / `[Transfers]`. For tight coupling pair with `FixedPointIterationAdaptiveDT`. See [multiapps.md](./multiapps.md).

## Minimal scaffold

Three patterns covering ~90% of inputs.

### Steady, NEWTON, hypre/boomeramg (scalar elliptic)

```hit
[Preconditioning]
  [SMP]
    type = SMP
    full = true
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  petsc_options_iname = '-pc_type -pc_hypre_type'
  petsc_options_value = 'hypre boomeramg'
  nl_rel_tol = 1e-10
  nl_abs_tol = 1e-12
  automatic_scaling = true
[]
```

### Transient, IterationAdaptiveDT + BDF2, with predictor

```hit
[Executioner]
  type = Transient
  solve_type = NEWTON
  petsc_options_iname = '-pc_type -pc_hypre_type'
  petsc_options_value = 'hypre boomeramg'

  end_time = 100.0
  dtmin = 1e-3
  dtmax = 5.0

  nl_rel_tol = 1e-8
  nl_abs_tol = 1e-10
  l_tol = 1e-4

  automatic_scaling = true
  line_search = bt

  [TimeStepper]
    type = IterationAdaptiveDT
    dt = 0.1
    optimal_iterations = 6
    iteration_window = 2
    growth_factor = 1.5
    cutback_factor = 0.5
  []

  [TimeIntegrator]
    type = BDF2
  []

  [Predictor]
    type = SimplePredictor
    scale = 1.0
    skip_after_failed_timestep = true
  []
[]
```

### Eigenvalue (inverse power, scalar criticality-style)

```hit
[Variables]
  [u]
  []
[]

[Kernels]
  [diff]
    type = Diffusion
    variable = u
  []
  [rhs]
    type = MassEigenKernel
    variable = u
    extra_vector_tags = eigen
  []
[]

[BCs]
  [all]
    type = DirichletBC
    variable = u
    boundary = 'left right top bottom'
    value = 0
  []
[]

[Problem]
  type = EigenProblem
  active_eigen_index = 0
[]

[Postprocessors]
  [unorm]
    type = ElementIntegralVariablePostprocessor
    variable = u
    execute_on = 'initial linear'
  []
[]

[Executioner]
  type = InversePowerMethod
  max_power_iterations = 50
  xdiff = unorm
  bx_norm = unorm
  k0 = 1.0
  solve_type = PJFNK
  petsc_options_iname = '-pc_type'
  petsc_options_value = 'lu'
[]
```
