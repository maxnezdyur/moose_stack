# Authoring: AuxKernels

AuxKernels populate auxiliary variables with values that are *not* solved for by the nonlinear system — they're for visualization, post-processing-style fields, derived diagnostics, and any per-DOF quantity you want available without entering the residual. They run after the nonlinear solve at each timestep and write directly into the auxiliary system's solution vector.

## When to use this (vs alternatives)

Decision tree:
- Compute a value to view in Exodus that doesn't enter the residual? → **AuxKernel** (templated on `Real`)
- Compute a vector-valued field (one `RealVectorValue` per DOF)? → **VectorAuxKernel** (`AuxKernelTempl<RealVectorValue>`)
- Compute a multi-component array (one `RealEigenVector` of size `N` per DOF)? → **ArrayAuxKernel** (`AuxKernelTempl<RealEigenVector>`)
- Operate on a scalar variable (single global DOF, no spatial structure)? → **AuxScalarKernel**
- Run on a fixed list of nodes for a scalar variable? → **AuxNodalScalarKernel** (specialization of `AuxScalarKernel`)
- Compute it once at problem start, never updated? → see [ic-authoring.md](./ic-authoring.md) — ICs run once
- Need it inside the residual (or its Jacobian)? → write a [material-authoring.md](./material-authoring.md) instead and visualize via `MaterialRealAux`
- Reduce the field to a single scalar number? → [postprocessor-authoring.md](./postprocessor-authoring.md)
- Cache spatial state for many consumers (e.g. integrals, layered averages)? → [userobject-authoring.md](./userobject-authoring.md)

**Aux variable family choice drives dispatch.** The kernel doesn't pick nodal vs elemental — the *aux variable* it writes to does, via `_var.isNodal()`:
- `FIRST_ORDER_LAGRANGE` (default for `Real` aux) → **nodal** AuxKernel: `compute()` is called once per node; `_qp` is forced to `0`; only `_current_node` is meaningful; `_q_point`, `_qrule`, `_JxW`, `_current_elem` are *not* set up for quadrature.
- `MONOMIAL` / `CONSTANT_MONOMIAL` (typical elemental choice) → **elemental** AuxKernel: `compute()` loops over qps and projects `\sum_q JxW * coord * computeValue() * test` (see `framework/src/auxkernels/AuxKernel.C`, lines ~145–270). For `CONSTANT_MONOMIAL` you'll get one DOF per element representing the volume average.
- Vector and array aux variables generally use `LAGRANGE_VEC` / `MONOMIAL` array families with the same nodal/elemental split.

If you ever read a material property, you must be elemental — see Pitfalls.

## Contract

### **AuxKernelBase** (`framework/include/auxkernels/AuxKernelBase.h:42`)
Non-templated abstract root. Holds `_subproblem`, `_sys`, `_aux_sys`, `_assembly`, `_mesh`, `_tid`, `_bnd` (true for boundary-restricted), `_check_boundary_restricted`. Mixes in `BlockRestrictable`, `BoundaryRestrictable`, `CoupleableMooseVariableDependencyIntermediateInterface`, `MaterialPropertyInterface`, `FunctionInterface`, `UserObjectInterface`, `PostprocessorInterface`, `RandomInterface`, `GeometricSearchInterface`, `Restartable`, `MeshChangedInterface`, `VectorPostprocessorInterface`, `ElementIDInterface`, `NonADFunctorInterface`. Declares `virtual void compute() = 0`.
- Don't derive from this directly; derive from `AuxKernel` / `VectorAuxKernel` / `ArrayAuxKernel`.

### **AuxKernelTempl<ComputeValueType>** (`framework/include/auxkernels/AuxKernel.h:27`)
Template that all field aux kernels derive from; three typedefs at lines 19–21:
- `AuxKernel` = `AuxKernelTempl<Real>`
- `VectorAuxKernel` = `AuxKernelTempl<RealVectorValue>`
- `ArrayAuxKernel` = `AuxKernelTempl<RealEigenVector>`

### **AuxKernel** (typedef, `framework/include/auxkernels/AuxKernel.h:19`)
Purpose: write a `Real` per DOF of a standard aux variable.
- **Required overrides**: `Real computeValue() override` (`AuxKernel.h:82`).
  - Elemental: indexed by `_qp` against `_q_point`, `_qrule`, `_JxW`, `_current_elem`.
  - Nodal: `_qp` is forced to 0; use `_current_node` (a `const Node *`).
- **Optional overrides**:
  - `precalculateValue()` (`AuxKernel.h:91`) — called once per element/node before the qp loop; cache anything expensive that doesn't depend on `_qp`.
  - `compute()` — only override when the default project-and-insert isn't right (e.g. `BuildArrayVariableAux` does this with `mooseError("Unused")` in `computeValue`).
- **Useful members**: `_var` (the `MooseVariableField<Real> &` you're writing), `_u` (current solution of `_var`), `uOld()`, `uOlder()`, `_current_elem_volume`, `_current_side` / `_current_side_volume` / `_current_boundary_id` (boundary kernels), `_current_lower_d_elem`, `isNodal()`, `isMortar()`.
- **validParams() additions**: `addRequiredCoupledVar` / `addCoupledVar`, `addParam<MaterialPropertyName>`, `addParam<FunctionName>`, `addParam<UserObjectName>`, `addParam<MooseFunctorName>`, `addRequiredParam<AuxVariableName>("variable", ...)` (already added by base — don't redo).

### **VectorAuxKernel** (typedef, `framework/include/auxkernels/AuxKernel.h:20`)
Purpose: write a `RealVectorValue` (3-component physical vector) per DOF of a *vector* aux variable (e.g. family `LAGRANGE_VEC`).
- **Required overrides**: `RealVectorValue computeValue() override`.
- Coupling for vector variables uses `coupledVectorValue` / `coupledVectorGradient`; example concrete classes: `VectorFunctionAux`, `ParsedVectorAux`, `FunctorElementalGradientAuxTempl`.

### **ArrayAuxKernel** (typedef, `framework/include/auxkernels/AuxKernel.h:21`)
Purpose: write a `RealEigenVector` (sized to `_var.count()`) per DOF of an *array* aux variable.
- **Required overrides**: `RealEigenVector computeValue() override`. The returned vector's size **must** match `_var.count()` — the framework will error/segfault otherwise.
- Has a specialized `compute()` (declared in `AuxKernel.h:255`, defined in `AuxKernel.C` ~line 220) that handles the array projection.
- Sometimes you need to override `compute()` directly when filling DOFs by index rather than projecting; pattern: see `BuildArrayVariableAux.h`, which makes `computeValue` a `mooseError("Unused")` and does the work in `compute()`.
- Coupling: `coupledArrayValue` / `coupledArrayGradient`; concrete examples `ArrayParsedAux`, `BuildArrayVariableAux`, `FunctionArrayAux`, `ArrayVarReductionAux`.

### **AuxScalarKernel** (`framework/include/auxscalarkernels/AuxScalarKernel.h:30`)
Purpose: compute the value of an auxiliary *scalar* variable (zero spatial dimension; one DOF for the whole problem, possibly a small fixed-size order). Called once per timestep, **not** per element / per qp.
- **Required overrides**: `Real computeValue() override` (`AuxScalarKernel.h:100`).
- **Useful members**: `_var` (a `MooseVariableScalar &`), `_u` (current scalar value), `uOld()`, `_i` (component index when `order > 1`).
- **No `_qp`, no `_current_elem`, no material-property access** — there's no quadrature in scalar space. Mixes in `ScalarCoupleable`, `FunctionInterface`, `UserObjectInterface`, `PostprocessorInterface`. `isActive()` lets a kernel opt out per call.
- **validParams() additions**: `addRequiredParam<VariableName>("variable", ...)` (added by base), `addCoupledScalarVar`.

### **AuxNodalScalarKernel** (`framework/include/auxscalarkernels/AuxNodalScalarKernel.h:20`)
Specialization of `AuxScalarKernel` that runs over a user-supplied list of node IDs and exposes regular field-variable coupling (`Coupleable` + `MooseVariableDependencyInterface`). Use it when your scalar-variable value is built from sampling field variables at specific nodes. Override `computeValue()` (still scalar-valued); `compute()` is overridden to iterate `_node_ids`.

## Coupling & material properties

- **Field-variable coupling** (only for `AuxKernelTempl`, not scalar): `coupledValue("u")`, `coupledGradient`, `coupledDot`, `coupledDotDu`, `coupledValueOld`, `coupledValueOlder`, `coupledVectorValue`, `coupledArrayValue`. Indexed by `_qp` even though `_qp == 0` in nodal mode (the framework wires nodal coupled values to a 1-element `MooseArray` so `(*coupled)[0]` is correct).
- **Functions**: `getFunction("name")` and call `.value(_t, _q_point[_qp])` (elemental) or `.value(_t, *_current_node)` (nodal).
- **UserObjects / Postprocessors / VPPs**: `getUserObject<T>`, `getPostprocessorValue`, `getVectorPostprocessorValue`. The aux system reorders evaluations to honor these dependencies — that's what `getDependObjects()` / `getRequestedItems()` / `getSuppliedItems()` are for.
- **Material properties**: `getMaterialProperty<T>("name")`, `getADMaterialProperty`, `getGenericMaterialProperty<T, is_ad>`, plus `Old` / `Older` flavors. `AuxKernelTempl` overrides each of these (`AuxKernel.h:182–247`) to `mooseError` if `isNodal()` is true. The error message tells the user to switch the aux variable to an elemental family.
- **Functors**: `getFunctor<T>("name")`. Functor evaluation supports nodal aux variables (`Moose::NodeArg{_current_node, &subdomain_set}`) — see `MaterialAuxBaseTempl::computeValue` (`MaterialAuxBase.h:128–141`) for the reference pattern.
- **AD coupling**: AD versions exist (`adCoupledValue`, `getADMaterialProperty`) but **the aux system does not propagate derivatives** — there is no Jacobian for an aux variable. AD here is purely cosmetic; you'll usually drop the AD type or `MetaPhysicL::raw_value(...)` it before returning. Don't write an AD AuxKernel just to "stay AD" — it costs runtime and provides no benefit.

## Registration & build

- One-liner in the `.C` file: `registerMooseObject("YourApp", YourAux);` (e.g. `framework/src/auxkernels/MaterialRealAux.C:12–15` registers `MaterialRealAux`, `ADMaterialRealAux`, `FunctorMaterialRealAux`, `ADFunctorMaterialRealAux`).
- **System attribute**: `validParams()` of `AuxKernelTempl` calls `params.registerSystemAttributeName("AuxKernel")` and additionally `params.registerBase("VectorAuxKernel")` / `"ArrayAuxKernel"` for the vector/array typedefs (`AuxKernel.C:30–37`) — this is what routes them into the right input-file block (`[AuxKernels]` for all three).
- File location: `framework/src/auxkernels/` and `framework/include/auxkernels/` (or per-module / per-app under `modules/<name>/{src,include}/auxkernels/`). Scalar variants go in `auxscalarkernels/`. AD templating is supported (e.g. `MaterialRealAuxTempl<is_ad, is_functor>`) but rarely worth it.

## Minimal scaffold

A nodal-or-elemental aux that pulls a `MaterialProperty<Real>` onto an aux variable, scaled by `factor`:

```cpp
// MyMatPropAux.h
#pragma once
#include "AuxKernel.h"

class MyMatPropAux : public AuxKernel
{
public:
  static InputParameters validParams();
  MyMatPropAux(const InputParameters & parameters);

protected:
  virtual Real computeValue() override;

  const Real & _factor;
  const MaterialProperty<Real> & _prop; // requires elemental aux variable
};
```

```cpp
// MyMatPropAux.C
#include "MyMatPropAux.h"

registerMooseObject("MyApp", MyMatPropAux);

InputParameters
MyMatPropAux::validParams()
{
  InputParameters params = AuxKernel::validParams();
  params.addClassDescription("Copy a Real material property onto an elemental aux variable, scaled by 'factor'.");
  params.addRequiredParam<MaterialPropertyName>("property", "Material property to copy.");
  params.addParam<Real>("factor", 1.0, "Multiplier.");
  return params;
}

MyMatPropAux::MyMatPropAux(const InputParameters & parameters)
  : AuxKernel(parameters),
    _factor(getParam<Real>("factor")),
    _prop(getMaterialProperty<Real>("property"))   // throws at construction if isNodal()
{
}

Real
MyMatPropAux::computeValue()
{
  return _factor * _prop[_qp];
}
```

In input:

```
[AuxVariables]
  [my_prop]
    family = MONOMIAL
    order  = CONSTANT
  []
[]

[AuxKernels]
  [my_prop_aux]
    type     = MyMatPropAux
    variable = my_prop
    property = my_material_prop
  []
[]
```

## Common pitfalls

1. **Reading a material property in a nodal AuxKernel.** `AuxKernelTempl::getMaterialProperty` (`AuxKernel.h:184–196`) hard-errors when `isNodal()` is true. Materials are evaluated at element qps; if your aux variable is `LAGRANGE` (the default `Real` family), you can't read material properties. Either switch the aux variable to `MONOMIAL` family, or use a *functor* material property — functors support nodal evaluation via `Moose::NodeArg` (see `MaterialAuxBase.h:128–141`).
2. **Using `_qp` in a nodal AuxKernel.** It's pinned to `0` and `_q_point`/`_JxW`/`_qrule` are not the per-element quadrature you'd expect. For position-dependent values in nodal mode, use `*_current_node` (a `const Node &` after deref) and ignore `_qp`.
3. **Aux variable family mismatch with what you're computing.** Computing a smooth field and writing into `CONSTANT_MONOMIAL` silently averages over each element. Computing a discontinuous quantity and writing into `LAGRANGE` produces values that are projection-smoothed across elements (the framework's elemental-to-nodal projection — see `AuxKernel.C` ~lines 165, 244). Always pick the family that matches the data you produce.
4. **Boundary-restricted AuxKernel on a nodal aux variable forgetting `_check_boundary_restricted`.** When `_bnd && !isNodal()` and an element has multiple faces on the same sideset, the default contributes the element's value once per face. Setting `check_boundary_restricted = false` allows multiple-face elements to contribute (`AuxKernelBase.h:92–100`).
5. **Returning a `RealEigenVector` of the wrong length from an `ArrayAuxKernel::computeValue`.** Must equal `_var.count()`. Use `RealEigenVector::Zero(_var.count())` as a starting point and resize before populating.
6. **Writing AD code in an AuxKernel.** Aux variables don't enter the Jacobian; AD here just slows you down. If you must read an AD material property, just call `MetaPhysicL::raw_value(_prop[_qp])` and return a `Real`.
7. **`AuxScalarKernel::computeValue` reading material properties.** `AuxScalarKernel` doesn't include `MaterialPropertyInterface` and has no `_qp`/`_current_elem` to evaluate at — there's no spatial location. Use postprocessor coupling (`getPostprocessorValue`) to get a reduced material-derived scalar instead.
8. **Forgetting that aux ordering follows declared dependencies, not file order.** Two AuxKernels writing different variables run in dependency order based on coupled vars / UOs / PPs. If `AuxA` depends on `AuxB`'s output, couple `B`'s variable in `A` (`coupledValue(...)`) — don't rely on declaration sequence.

