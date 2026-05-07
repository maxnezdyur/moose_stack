# Authoring: Initial Conditions

ICs set the value of a variable at simulation start (`t = 0` or restart). They run once, before the solve, and project a user-supplied spatial function onto the variable's degrees of freedom.

## When to use this (vs alternatives)

Decision tree:

- **Setting a value once at the start of the simulation?** Use an IC.
  - Field variable (`u`, `T`, displacement, ...)?
    - Continuous Galerkin / Lagrange / Hermite (FE)? Subclass `InitialCondition` (`InitialConditionTempl<Real>`).
    - Vector FE field (Nedelec, Raviart-Thomas, etc.)? Subclass `VectorInitialCondition` (`InitialConditionTempl<RealVectorValue>`).
    - Array variable (multi-component)? Subclass `ArrayInitialCondition` (`InitialConditionTempl<RealEigenVector>`).
    - Finite-volume cell-centered variable? Subclass `FVInitialCondition` (`FVInitialConditionTempl<Real>`).
  - Scalar variable (single global DOF, no spatial dependence)? Subclass `ScalarInitialCondition`.
- **Need a constant?** Use `ConstantIC` / `FVConstantIC` / `ScalarConstantIC` directly from input — no C++.
- **Need a spatial function?** Use `FunctionIC` / `FVFunctionIC` with a `Function` object.
- **Need value pulled from any functor (variable, function, functor material property, postprocessor)?** Use `FunctorIC`.
- **Need values that depend on a `UserObject`?** Subclass an IC; the dependency resolver will ensure the UO runs first (unless `ignore_uo_dependency = true`). For UOs to execute in `PRE_IC`, set `force_preic = true` on the UO.
- **Want to set a value every timestep, not just at the start?** Wrong tool — use an [AuxKernel](./auxkernel-authoring.md).
- **Want to enforce a value during the solve?** Wrong tool — use a [BoundaryCondition](./bc-authoring.md) or constraint.
- **Need values from a previous Exodus solution?** Use `SolutionIC` / `ScalarSolutionIC` with a `SolutionUserObject`.

## Contract

### **InitialConditionBase** (`framework/include/ics/InitialConditionBase.h:39`)

Purpose: abstract base for FE field ICs. Inherits `MooseObject`, `BlockRestrictable`, `BoundaryRestrictable`, `Coupleable`, `MaterialPropertyInterface`, `FunctionInterface`, `UserObjectInterface`, `PostprocessorInterface`, `Restartable`, `DependencyResolverInterface`, `ElementIDInterface`. Provides dependency tracking and the abstract `compute`/`computeNodal` interface; you almost never derive from this directly — derive from `InitialCondition` instead.

- **Pure virtuals**: `variable()` (returns the target FE variable), `compute()` (block IC projection), `computeNodal(const Point&)` (boundary-restricted projection). All implemented by `InitialConditionTempl<T>`.
- **Optional override**: `initialSetup()` (`framework/include/ics/InitialConditionBase.h:90`).

### **InitialConditionTempl\<T\>** (`framework/include/ics/InitialConditionTempl.h:30`)

Purpose: implements the projection workhorse for FE variables. `T` is `Real`, `RealVectorValue`, or `RealEigenVector`.

- **Required override**: `value(const Point & p)` — returns `T` at `p`. (`framework/include/ics/InitialConditionTempl.h:61`)
- **Optional overrides**:
  - `gradient(const Point & p)` — returns `GradientType`. Required for C1-continuous (Hermite) elements; otherwise default zero is fine. (`framework/include/ics/InitialConditionTempl.h:69`)
  - `initialSetup()`.
- **Aliases** (`framework/include/ics/InitialConditionTempl.h:200-202`):
  - `InitialCondition` = `InitialConditionTempl<Real>`
  - `VectorInitialCondition` = `InitialConditionTempl<RealVectorValue>`
  - `ArrayInitialCondition` = `InitialConditionTempl<RealEigenVector>`
- **validParams() additions**: typically `addRequiredParam<...>("value" / "function" / ...)`. The required `variable` param is added by the base (`framework/src/ics/InitialConditionBase.C:24`).

### **FVInitialConditionBase** (`framework/include/fvics/FVInitialConditionBase.h:33`)

Purpose: abstract base for finite-volume ICs (cell-centered). Inherits `BlockRestrictable`, `FunctionInterface`, `Restartable`, `DependencyResolverInterface`, `NonADFunctorInterface`. Note: no `BoundaryRestrictable`, no `Coupleable`, no `MaterialPropertyInterface` — FV ICs are leaner.

- **Pure virtual**: `computeElement(const ElemInfo & elem_info)` (`framework/include/fvics/FVInitialConditionBase.h:62`). Implemented by `FVInitialConditionTempl<T>`.
- **Optional override**: `initialSetup()`.
- **Registered base name**: `FVInitialCondition` (`framework/src/fvics/FVInitialConditionBase.C:25`).

### **FVInitialConditionTempl\<T\>** (`framework/include/fvics/FVInitialConditionTempl.h:32`)

- **Required override**: `value(const Point & p)` — evaluated at the cell centroid. (`framework/include/fvics/FVInitialConditionTempl.h:55`)
- **No `gradient` hook** — FV variables are piecewise constant per cell.
- **Alias**: `FVInitialCondition` = `FVInitialConditionTempl<Real>` (`framework/include/fvics/FVInitialConditionTempl.h:78`).

### **ScalarInitialCondition** (`framework/include/ics/ScalarInitialCondition.h:33`)

Purpose: IC for scalar variables (one or a small number of global DOFs, no spatial dependence). Inherits `ScalarCoupleable`, `FunctionInterface`, `UserObjectInterface`. No block/boundary restriction, no material interface.

- **Required override**: `value()` — returns `Real`, called once per scalar component (`framework/include/ics/ScalarInitialCondition.h:64`). The component index is exposed as `_i` in the protected member `unsigned int _i` and walked from `0` to `_var.order()-1` by `compute(DenseVector<Number>&)` (`framework/src/ics/ScalarInitialCondition.C:65`).
- **Optional overrides**: `initialSetup()`, `compute(DenseVector<Number>&)` (default loops over `_i` calling `value()`).
- **Registered base name**: `ScalarInitialCondition` (`framework/src/ics/ScalarInitialCondition.C:23`).

## Coupling & material properties

ICs run **before Materials and UserObjects** in the standard pipeline. This affects what you can read inside `value()`:

- **`coupledValue("v")`** — returns the value of variable `v` *at the IC's evaluation point*. For an FE IC, `value(p)` is called per node/qp, and `coupledValue` returns the projected value of `v` at that point. Works only if `v` itself already has an IC (the dependency resolver handles ordering via `getRequestedItems()` / `getSuppliedItems()` set up in `framework/src/ics/InitialConditionBase.C:60-65`).
- **`getMaterialProperty<...>("prop")`** — generally **not safe** at IC time because Materials are evaluated during element assembly, not before ICs. Reading a regular material property in `value()` typically returns zero or stale data. The exception: `getGenericMaterialProperty` for a property tied to a constant or a `Function` material may work after `initialSetup()`, but treat this as fragile and prefer functors.
- **`Moose::Functor<Real>`** via `FunctorIC` is the modern, supported escape hatch — functors abstract over variables, functions, postprocessors, and functor material properties, and the functor system has IC-aware checks (see `framework/src/ics/FunctorIC.C` for the `force_preic` postprocessor guard).
- **`getFunction("f")`** — always safe; functions are pure spatial+temporal expressions with no element/material context.
- **`getPostprocessorValue("pp")`** — only safe if the postprocessor has `force_preic = true` so it executes in the `PRE_IC` phase (see `framework/src/userobjects/UserObjectBase.C` and `framework/include/loops/ComputeUserObjectsThread.h`). Otherwise the value is the default (typically zero).
- **UserObjects** — same rule: dependency resolver puts UOs requested by an IC ahead of it, but those UOs must be executable in `PRE_IC` (set `force_preic = true` if needed).

## Registration & build

- `registerMooseObject("MooseApp", MyIC);` — usually in the app's namespace, e.g. `registerMooseObject("MyAppApp", MyIC);` for a downstream app.
- File locations:
  - FE field ICs: header in `include/ics/`, source in `src/ics/`.
  - FV ICs: header in `include/fvics/`, source in `src/fvics/`.
  - Scalar ICs: header/source live in `include/ics/` and `src/ics/` (same directory as field ICs).
- Input syntax block: FE/FV/scalar all live under `[ICs]` in the input file. The action system routes by `registerBase()` ("InitialCondition", "FVInitialCondition", "ScalarInitialCondition").

## Minimal scaffold

A scalar-field IC that returns `amp * sin(k * x)` plus a spatially varying coupled-variable contribution:

```cpp
// include/ics/SinusoidIC.h
#pragma once
#include "InitialCondition.h"

class SinusoidIC : public InitialCondition
{
public:
  static InputParameters validParams();
  SinusoidIC(const InputParameters & parameters);

  virtual Real value(const Point & p) override;

protected:
  const Real _amp;
  const Real _k;
  const VariableValue & _coupled;
};
```

```cpp
// src/ics/SinusoidIC.C
#include "SinusoidIC.h"

registerMooseObject("MyApp", SinusoidIC);

InputParameters
SinusoidIC::validParams()
{
  InputParameters params = InitialCondition::validParams();
  params.addClassDescription("amp * sin(k*x) plus an offset from a coupled variable.");
  params.addRequiredParam<Real>("amp", "Amplitude");
  params.addParam<Real>("k", 1.0, "Wave number");
  params.addRequiredCoupledVar("offset", "Variable whose IC value is added");
  return params;
}

SinusoidIC::SinusoidIC(const InputParameters & parameters)
  : InitialCondition(parameters),
    _amp(getParam<Real>("amp")),
    _k(getParam<Real>("k")),
    _coupled(coupledValue("offset"))
{
}

Real
SinusoidIC::value(const Point & p)
{
  return _amp * std::sin(_k * p(0)) + _coupled[_qp];
}
```

For an `FVInitialCondition`: replace `InitialCondition` with `FVInitialCondition`, drop coupling (no `Coupleable`), and the same `value(const Point & p)` is invoked at each cell centroid. For a `ScalarInitialCondition`: override `Real value()` (no point), use `_i` if you need to distinguish components.

## Common pitfalls

1. **Reading material properties.** ICs run before Materials, so `_prop[_qp]` typically yields zero. If you need a material-derived initial value, prefer a `FunctorIC` referencing a functor material property, or move the computation into a `UserObject` with `force_preic = true`.
2. **Postprocessors in ICs.** Postprocessor values default to zero unless the PP runs in the `PRE_IC` execution phase (`force_preic = true`). `FunctorIC` warns when a postprocessor functor lacks this flag (`framework/src/ics/FunctorIC.C`).
3. **Restart skips ICs.** On restart, ICs are not re-run (the variable comes from the checkpoint). To force an IC to overwrite the restart value, set `force_preic = true` on the IC (or use the Action option that re-applies ICs on restart). This trips up users moving from a steady solve to a transient.
4. **Nodal vs elemental `value(Point)`.** For a nodal Lagrange variable, `value(p)` is called once per node (and `_current_node` is non-null). For elemental (`MONOMIAL` / `CONSTANT`) variables, `value(p)` is called at quadrature points and projected; `_current_node` is null. Conditional logic that branches on `_current_node` must handle both.
5. **FV ICs are cell-centered only.** `FVInitialConditionTempl<T>::value(p)` is invoked at cell centroids. There is no `gradient` hook — FV solutions are piecewise constant per cell.
6. **Scalar ICs return a single number per component.** `ScalarInitialCondition::value()` takes no `Point`. If `_var.order() > 1`, `compute()` walks `_i` from `0` to `order-1` and you must use `_i` to distinguish components — otherwise every component receives the same value.
7. **Vector/Array IC `value()` return type.** When subclassing `VectorInitialCondition` (`InitialConditionTempl<RealVectorValue>`) or `ArrayInitialCondition` (`InitialConditionTempl<RealEigenVector>`), `value(p)` must return `RealVectorValue` / `RealEigenVector`, not `Real` — easy mistake when copy-pasting from a scalar IC.
8. **`coupledValue` only works at the IC point.** Don't try to integrate or sample a coupled variable across the element from `value(p)` — you'll get one value per call. Use a `UserObject` upstream if you need that.

