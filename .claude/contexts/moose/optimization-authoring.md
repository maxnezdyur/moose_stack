# Authoring: Optimization module

The optimization module wraps PETSc/TAO around a MOOSE main app that drives forward (and optionally adjoint) sub-apps to solve PDE-constrained inverse and design optimization problems. The main app holds the parameter vector and objective; sub-apps compute the physics, the misfit, and the gradient via the adjoint method.

## When to use this (vs alternatives)

Decision tree:

1. Goal is **parameter identification / inverse problem / design optimization** with a PDE constraint? Yes -> optimization module. If you only need uncertainty quantification, sensitivity sampling, surrogate construction, or Bayesian inference, use stochastic_tools instead (see [stochastic-tools-authoring.md] — same MultiApp/Sampler machinery, different goal).
2. Misfit is `(u_sim - u_meas)^2` at point/line/volume measurements? Yes -> `OptimizationReporter` + `OptimizationData`. Custom objective (e.g. compliance, energy, manufacturing cost)? Use `GeneralOptimization` and have the sub-app compute the scalar objective + gradient and return them via reporters.
3. Parameters live on a separate FE mesh (spatial fields you want shape-function interpolated)? Use `ParameterMeshOptimization` + `ParameterMesh` + `ParameterMeshFunction` (also gives you L2_GRADIENT regularization for free).
4. Forward problem is steady? Use `SteadyAndAdjoint` (one sub-app does both solves) for tight coupling, or separate `Steady` forward + `Steady` adjoint sub-apps with `AdjointSolutionUserObject` if you need flexibility (e.g. reuse an existing forward input).
5. Forward problem is transient? Use `TransientAndAdjoint` (handles backward-in-time adjoint sweep automatically) — separate sub-apps require manual orchestration of saved forward solutions and are rarely worth it.
6. Topology optimization (SIMP)? Use `DensityUpdate` + `SensitivityFilter` — this **bypasses TAO entirely** with an optimality-criterion bisection inside the forward executioner. Don't combine with `Optimize`.
7. Constraints?
   - Box bounds on parameters only -> any `BOUNDED_*` TAO solver.
   - Equality / inequality constraints -> `AUGMENTED_LAGRANGIAN_MULTIPLIER_METHOD` + populate `equality_names` / `inequality_names` and their `grad_*` reporter vectors.
   - Gradient-free fallback -> `NELDER_MEAD` (no adjoint needed; only objective).
8. TAO solver pick:
   - Default for smooth problems: `BOUNDED_QUASI_NEWTON` (BLMVM) or `BOUNDED_QUASI_NEWTON_TRUST_REGION`.
   - When you have Hessian-vector products: `NEWTON_TRUST_REGION` / `BOUNDED_NEWTON_TRUST_REGION`.
   - Constrained: `AUGMENTED_LAGRANGIAN_MULTIPLIER_METHOD`.
   - No gradients: `NELDER_MEAD`.

## Contract

### **OptimizationReporterBase** (modules/optimization/include/optimizationreporters/OptimizationReporterBase.h:25)

Base for all objects that expose the `(parameters, gradient, objective, [equality, inequality])` contract to `OptimizeSolve`. Derives from `GeneralReporter` so its values are reporter-vector-typed and discoverable across MultiApp boundaries.

- Pure virtual: `computeObjective() -> Real`.
- Default implementations you typically override or rely on:
  - `computeGradient(PetscVector & gradient)` (modules/optimization/src/optimizationreporters/OptimizationReporterBase.C:72) — copies `_gradients` reporter vectors to the PETSc vector and adds Tikhonov term if `tikhonov_coeff > 0`.
  - `updateParameters(const PetscVector & x)` — copies TAO's PETSc vector into `_parameters` reporter vectors. Override only if you need to broadcast the parameter vector somewhere else first.
  - `setICsandBounds()` — populated by derived classes; called once at `setInitialCondition` time.
  - `computeEqualityConstraints` / `computeInequalityConstraints` / `computeEqualityGradient` / `computeInequalityGradient` — only invoked when those reporter names are declared.
- Required reporter declarations (made for you via `validParams` + ctor): `parameter_names` -> `_parameters` vectors, `grad_<name>` (gradient) vectors automatically; `equality_names` and `inequality_names` are optional. Sub-apps read parameters and write gradients into these reporter values via transfers.
- `OptimizeSolve` introspects **only** objects that derive from `OptimizationReporterBase`. Plain `GeneralReporter` instances will not be picked up.
- registerMooseObject base class — never register the base directly.

### **OptimizationReporter** (modules/optimization/include/optimizationreporters/OptimizationReporter.h:18)

Misfit-based concrete reporter via the `OptimizationDataTempl<OptimizationReporterBase>` mixin (modules/optimization/include/reporters/OptimizationData.h:32). Owns measurement coordinates `(x, y, z, t)`, measurement values, and simulated values; computes `f = 1/2 sum (u_sim - u_meas)^2 + tikhonov_coeff/2 * |p|^2`.

- `computeObjective()` returns the misfit; `setMisfitToSimulatedValues()` lets the matrix-free Hessian path overwrite simulated values mid-iteration.
- Sub-app fills `_simulation_values` (the variable evaluated at the measurement points) — the reporter computes the misfit.
- Note: registered as **deprecated** alias since 12/31/2024 (modules/optimization/src/optimizationreporters/OptimizationReporter.C:14) — still functional, but new inputs should generally prefer the `OptimizationData` reporter (a plain `GeneralReporter`) on the sub-app + `GeneralOptimization` on the main app.

### **GeneralOptimization** (modules/optimization/include/optimizationreporters/GeneralOptimization.h:20)

For sub-app-computed objectives/gradients/constraints. Owns only a scalar `_objective_val` reporter; everything else (objective value, gradient vector, constraint values, constraint gradients) is computed in the sub-apps and pulled back via reporter transfers.

- `computeObjective()` simply returns `_objective_val` — no misfit math.
- `setICsandBounds()` reads `initial_condition`, `lower_bounds`, `upper_bounds` from input (or accepts vectors per parameter group).
- Use this when your objective is a compliance integral, an energy norm, a manufacturing cost, a fluence target, or any quantity not expressible as `(u - u_meas)^2`.

### **ParameterMeshOptimization** (modules/optimization/include/optimizationreporters/ParameterMeshOptimization.h:18)

Subclass of `GeneralOptimization` that reads parameter initial conditions and bounds off an Exodus mesh (the "parameter mesh"). Each parameter group's DOF count is set by the parameter mesh's FE space; bounds and ICs can be looked up by exodus variable + timestep.

- Adds `regularization_types = [L2_GRADIENT]` and `regularization_coeffs = [...]` — applies `1/2 * |grad p|^2` over the parameter mesh and contributes to both `computeObjective()` (modules/optimization/include/optimizationreporters/ParameterMeshOptimization.h:25) and `computeGradient()` (line 26). This is honest H1 / Tikhonov regularization on the field, not just on the coefficient vector.
- `parseExodusData(...)` reads named Exodus variables at given timesteps to seed `initial_condition` / `lower_bounds` / `upper_bounds`.
- Pair with `ParameterMeshFunction` on sub-apps to evaluate `p(x, t)` inside kernels/BCs/materials using the same shape functions.

### **AdjointSolve / AdjointTransientSolve / SteadyAndAdjoint / TransientAndAdjoint** (modules/optimization/include/executioners/AdjointSolve.h:31, AdjointTransientSolve.h:32, SteadyAndAdjoint.h:18, TransientAndAdjoint.h:18)

`AdjointSolve` is a `SolveObject` that solves `J^T lambda = -df/du` by:
1. Running the inner forward solve.
2. Calling `assembleAdjointSystem` (forms the forward Jacobian, evaluates the **adjoint system's** residual as the RHS source) (modules/optimization/include/executioners/AdjointSolve.h:66).
3. Calling `linearSolver::adjoint_solve` on the transposed matrix.
4. Applying nodal Dirichlet BCs via `applyNodalBCs` (zero on `Gamma_D`).

The adjoint lives in a **second nonlinear system** on the same problem (`_adjoint_sys_num` vs `_forward_sys_num`) — kernels/BCs registered on that second system define `df/du` (the adjoint source) and any boundary contributions to the adjoint. Most users do **not** subclass `AdjointSolve`. They configure the second nonlinear system in input.

Override only `assembleAdjointSystem` and (rarely) `linearSolve` to extend behavior — e.g. apply weighting matrices, preconditioners, or extra residual contributions. `AdjointTransientSolve` (modules/optimization/include/executioners/AdjointTransientSolve.h:32) extends this to march backward in time, storing each forward solution via `insertForwardSolution(tstep)` during the forward sweep and replaying via `setForwardSolution(tstep)` during the adjoint sweep. `SteadyAndAdjoint` and `TransientAndAdjoint` are convenience executioners that bundle the forward executioner and the adjoint solve into a single sub-app — strongly preferred over hand-wired separate sub-apps.

For separate forward + adjoint sub-apps, use **AdjointSolutionUserObject** (modules/optimization/include/userobjects/AdjointSolutionUserObject.h:14) — re-reads the adjoint Exodus on every timestep so the main app can pull updated lambda fields each TAO iteration.

### **OptimizationFunction** + **ParameterMeshFunction** (modules/optimization/include/functions/OptimizationFunction.h:19, ParameterMeshFunction.h:20)

`OptimizationFunction` is the abstract base for any function whose value depends on the optimization parameter vector. The required override is `parameterGradient(t, p) -> std::vector<Real>` returning `df/dp_i` at `(t, p)` — used by adjoint VPPs (e.g. `ElementOptimizationFunctionInnerProduct`) to assemble `dR/dp`.

`ParameterMeshFunction` is the concrete one used 90% of the time: pulls a reporter vector of parameter values + a `ParameterMesh`, and at each evaluation point uses FE shape functions to interpolate `p(x)` and `grad p(x)`. Time interpolation between snapshot timesteps is built in.

Use these inside kernels, BCs, materials in the **forward** problem to convert "abstract parameter index" into "spatial field value". The **adjoint** problem then uses the same function plus an `ElementOptimizationFunctionInnerProduct`-family VPP to compute `dR/dp` and write it back into the gradient reporter vector.

### **DensityUpdate** + **SensitivityFilter** (modules/optimization/include/userobjects/DensityUpdate.h:19, SensitivityFilter.h:20)

SIMP topology-optimization track. **Bypasses TAO entirely** — the executioner is a normal `Steady` (or fixed-point pseudo-time loop), and these UOs run inside the forward problem.

- `SensitivityFilter` filters the raw compliance sensitivity (`d compliance / d rho`) using a `RadialAverage` kernel to avoid checkerboarding.
- `DensityUpdate` runs an optimality-criterion bisection on the filtered sensitivity to update the design density `rho` subject to a volume-fraction constraint. `DensityUpdateTwoConstraints` extends to two constraints (e.g. mass + cost).
- Pair with a SIMP material like `CostSensitivity` (modules/optimization/include/materials/CostSensitivity.h) and the SM module's `SIMP*` materials for forward physics.

## Coupling & material properties

- `OptimizationReporterBase` exposes parameter / gradient / equality / inequality reporter vectors. **Only objects derived from this base type are introspected by `OptimizeSolve`** — a plain `GeneralReporter` named "OptimizationReporter" will silently be ignored.
- The standard data flow each TAO iteration:
  1. TAO calls `objectiveFunction()` -> `updateParameters(x)` writes `x` into the main-app `_parameters` reporter vectors.
  2. Main app fires its forward MultiApp; a `MultiAppReporterTransfer` pushes `_parameters` to the sub-app.
  3. Sub-app forward solve runs (with `ParameterMeshFunction` or similar evaluating `p(x)`), then writes `_simulation_values` (or `_objective_val`) back via reporter transfer.
  4. `computeObjective()` returns the scalar to TAO.
  5. TAO calls `gradientFunction()`; the adjoint sub-app runs, the inner-product VPPs fill the `grad_<param>` reporter vectors, transfers pull them back; `computeGradient` copies them into the PETSc gradient.
- `AdjointSolutionUserObject` reads adjoint solutions from a sibling sub-app's Exodus file at each timestep — used when forward and adjoint live in separate sub-apps. Prefer `SteadyAndAdjoint` / `TransientAndAdjoint` to skip the file round-trip.
- `ParameterMesh` uses FE shape functions on a separate Exodus mesh; the optimization main app, the forward sub-app, and the adjoint sub-app all instantiate `ParameterMesh` from the **same** exodus file so DOF orderings line up.

## Registration & build

- `registerMooseObject("OptimizationApp", <Class>)` for new reporters, executioners, UOs, functions, VPPs.
- Module flag in `modules/modules.mk:30`: `OPTIMIZATION := yes`.
- PETSc/TAO is required and is always available in MOOSE-PETSc builds — no extra capability gate needed.
- Tests live under `modules/optimization/test/tests/` with `tests` specs gated by `petsc_version` if you use a TAO feature added in newer PETSc.

## Minimal scaffold

A small custom `OptimizationFunction` subclass that bridges a 1D parameter vector (e.g. time-history of a boundary flux) to a function the forward problem evaluates.

Header (~30 lines):
```cpp
// MyTimeFunction.h
#pragma once
#include "OptimizationFunction.h"
#include "ReporterInterface.h"

class MyTimeFunction : public OptimizationFunction, public ReporterInterface
{
public:
  static InputParameters validParams();
  MyTimeFunction(const InputParameters & parameters);

  using Function::value;
  virtual Real value(Real t, const Point & p) const override;
  virtual std::vector<Real> parameterGradient(Real t, const Point & p) const override;

protected:
  const std::vector<Real> & _values;   // reporter vector (the parameters)
  const std::vector<Real> & _times;    // reporter vector (snapshot times)
};
```

Source (~40 lines):
```cpp
// MyTimeFunction.C
#include "MyTimeFunction.h"
registerMooseObject("MyApp", MyTimeFunction);

InputParameters
MyTimeFunction::validParams()
{
  auto params = OptimizationFunction::validParams();
  params.addRequiredParam<ReporterName>("parameter_name", "Reporter holding parameter vector");
  params.addRequiredParam<ReporterName>("time_name", "Reporter holding the snapshot times");
  return params;
}

MyTimeFunction::MyTimeFunction(const InputParameters & parameters)
  : OptimizationFunction(parameters),
    ReporterInterface(this),
    _values(getReporterValue<std::vector<Real>>("parameter_name")),
    _times(getReporterValue<std::vector<Real>>("time_name"))
{
}

Real
MyTimeFunction::value(Real t, const Point & /*p*/) const
{
  // simple piecewise linear in time
  // ...
  return 0.0;
}

std::vector<Real>
MyTimeFunction::parameterGradient(Real t, const Point & /*p*/) const
{
  // d value / d p_i — for piecewise linear, two non-zero entries per t
  std::vector<Real> g(_values.size(), 0.0);
  // ... fill g
  return g;
}
```

The forward problem then references this function inside e.g. a `NeumannBC` (`function = my_time_function`); the adjoint problem uses an `ElementOptimizationFunctionInnerProduct` (or `SideOptimization*`) VPP with the same function name to assemble `dR/dp` into the gradient reporter.

## Common pitfalls

- **Parameter ambiguity.** "Parameter" in this module means a *design variable* in the optimization vector — not a MOOSE `InputParameter`. The two share the word and nothing else. Code reviews regularly conflate them.
- **Only OptimizationReporterBase-derived reporters are introspected.** A plain `GeneralReporter` that happens to declare `parameter_results` reporter values will be silently ignored by `OptimizeSolve`. Subclass `OptimizationReporterBase` (or `GeneralOptimization`) when authoring custom objective objects.
- **Bounded TAO solvers handle box bounds only.** Inequality / equality constraints require `tao_solver = AUGMENTED_LAGRANGIAN_MULTIPLIER_METHOD` and populated `inequality_names` / `equality_names` + `grad_*` reporter vectors. Just adding `lower_bounds`/`upper_bounds` to a `BOUNDED_QUASI_NEWTON` problem will not enforce inequalities.
- **Misfit != residual.** `df/du` (the adjoint source RHS) is the derivative of the **objective** with respect to the state variable, NOT the forward PDE residual. Misfit-based reporters generate a delta-function source at measurement points; compliance objectives generate a source proportional to the displacement field. Authoring the adjoint kernel/BC requires a clean derivation.
- **SteadyAndAdjoint / TransientAndAdjoint bundle forward+adjoint in one sub-app.** They run a single `Steady`/`Transient` then immediately a single `AdjointSolve(Transient)` on the same `FEProblem`. If you instead use separate forward and adjoint sub-apps you must wire them with `AdjointSolutionUserObject` and a second `MultiApp` — much more input boilerplate, only worthwhile when the forward sub-app must remain a stock executioner.
- **AdjointSolve writes into a SECOND nonlinear system.** You configure adjoint kernels/BCs by adding a second `[Variables]`/`[Kernels]`/`[BCs]` block tied to a second `[Problem]/nl_sys_names = 'forward adjoint'` (or equivalent). Apply zero-Dirichlet on `Gamma_D` (where the forward had Dirichlet); applying the original forward Dirichlet value is a frequent mistake and yields a wrong gradient.
- **SIMP DensityUpdate replaces TAO — don't stack them.** A SIMP input has executioner `Steady` (forward) and `DensityUpdate`/`SensitivityFilter` UOs running every step; there is **no** `[Optimization]` block, no `Optimize` executioner, no main app. Adding TAO on top would double-update the design vector.
- **Parameter mesh DOF ordering.** Main app, forward sub-app, and adjoint sub-app must all instantiate `ParameterMesh` from the *same* Exodus file with the *same* FE type. Mismatched FE types silently produce wrong gradients (the parameter PETSc vector is interpreted with the wrong shape functions on the sub-app side).
- **Tikhonov coeff applies to the raw coefficient vector, not the field.** `tikhonov_coeff` adds `rho/2 * sum p_i^2` regardless of the parameter mesh. To regularize the *field* (`1/2 |grad p|^2`), use `ParameterMeshOptimization` with `regularization_types = L2_GRADIENT` instead.

