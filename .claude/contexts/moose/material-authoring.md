# Authoring: Materials

Materials are quadrature-point property factories (`MaterialProperty<T>`) consumed by Kernels, BCs, and other Materials; FunctorMaterials are the lazy/on-demand alternative used heavily by finite-volume and on-the-fly evaluation paths. Stateful (old/older) values, AD propagation, block/boundary/interface restriction, and derivative-property naming are all handled via mix-in interfaces on top of these two base classes.

## When to use this (vs alternatives)

Decision tree:
- Need a value at quadrature points consumed by a Kernel/BC during the residual/Jacobian assembly? -> **Material** (use `declareADProperty<T>` for AD-by-default).
- Need a value evaluable on demand at faces, elements, boundaries, or arbitrary `Point`s (FV, mixed FV/FE, `getFunctor` consumers)? -> **FunctorMaterial**.
- Need state across timesteps (old/older)? -> regular **Material** with `getMaterialPropertyOld<T>` / `getMaterialPropertyOlder<T>`. The "old" value is auto-stored when something requests state > 0; you only declare the current property.
- Need a value computed per quadrature point on a sideset (boundary integral, BC consumer)? -> regular **Material** with `boundary = '...'` set in input; `_bnd` is true and the qrule is the side qrule.
- Need a value at an internal interface (different materials on each side)? -> **InterfaceMaterial** (uses `TwoMaterialPropertyInterface`, exposes `_neighbor_elem`).
- Need d(prop)/d(coupled_var) for a non-AD off-diagonal Jacobian? -> wrap your Material in `DerivativeMaterialInterface<Material>` and use `declarePropertyDerivative`.
- Want to compute a value purely for output / visualization, not for the residual? -> see [auxkernel-authoring.md](./auxkernel-authoring.md).
- Constant or function-driven property and you don't want to write a class? -> input-only via `GenericConstantMaterial` / `GenericFunctionMaterial` / `GenericFunctorMaterial`.

## Contract

### **MaterialBase** (framework/include/materials/MaterialBase.h:62)
Purpose: abstract base for every material flavor. Owns the property-declaration API, the stateful sanity-check, block/boundary restriction, and the dependency-resolution machinery. You never inherit `MaterialBase` directly in user code.
- **Required overrides** (in concrete subclasses): `computeQpProperties()`; `computeProperties()` (already implemented by `Material`/`InterfaceMaterial`/`FunctorMaterial`); `isBoundaryMaterial()` (already implemented).
- **Optional overrides**: `initQpStatefulProperties()` (per-qp initial values for stateful props), `initStatefulProperties(unsigned int n_points)` (whole-element variant, only invoked when at least one declared property is stateful), `initialSetup()`, `subdomainSetup()`, `resolveOptionalProperties()`, `ghostable()` (return `true` if your material can be evaluated on ghosted elements; FV-friendly).
- **validParams() additions**: usually nothing at this layer; add `block`/`boundary` (already declared via the restrictable mix-ins), `addCoupledVar`, `addParam<MaterialPropertyName>`, etc., in the subclass.

### **Material** (framework/include/materials/Material.h:35)
Concrete base for volumetric / boundary / face quadrature-point materials. Inherits `MaterialBase + Coupleable + MaterialPropertyInterface`. Implements `computeProperties()` as a quadrature loop calling `computeQpProperties()`. `_bnd`, `_neighbor`, `_q_point`, `_qrule`, `_JxW`, `_current_elem`, `_current_subdomain_id`, `_current_side` are members. `ADMaterial` (framework/include/materials/ADMaterial.h:14) is `using ADMaterial = Material;` -- there is no separate AD class. AD-ness is a per-property choice via `declareADProperty<T>`.
- **Required overrides**: `computeQpProperties()`.
- **Optional overrides**: `initQpStatefulProperties()`, `initialSetup()`, `subdomainSetup()`, `resolveOptionalProperties()`.
- **validParams() additions**: `block` (inherited from BlockRestrictable), `boundary` (inherited from BoundaryRestrictable), plus your own coupled vars and `MaterialPropertyName` inputs.

### **InterfaceMaterial** (framework/include/materials/InterfaceMaterial.h:31)
Quadrature-point material on internal sidesets where each side may have a different material. Inherits `MaterialBase + NeighborCoupleable + TwoMaterialPropertyInterface`. Use when you need both `_current_elem` and `_neighbor_elem` properties simultaneously. Selected by setting `boundary = '...'` on an internal sideset.
- **Required overrides**: `computeQpProperties()`.

### **FunctorMaterial** (framework/include/functormaterials/FunctorMaterial.h:17)
Lazy property producer; properties are `Moose::FunctorBase<T>` instances callable as `prop(arg, state)` where `arg` is `ElemQpArg`/`ElemSideQpArg`/`FaceArg`/`ElemPointArg`/`NodeArg`/etc. Inherits `Material`, but `computeProperties()` and `computeQpProperties()` are stubbed `final` -- you do not override them. Instead, the lambda is captured at construction.
- **Required overrides**: register every functor property in the constructor via `addFunctorProperty<T>("name", lambda, clearance_schedule = {EXEC_ALWAYS})`. The lambda signature is `(const auto & space, const auto & state) -> T`.
- **Optional overrides**: `addFunctorPropertyByBlocks<T>` for explicit block lists.
- **validParams() additions**: same as `Material` (block restriction is honored implicitly).

## Coupling & material properties

- `declareProperty<T>(name)` (MaterialBase.h:137) returns `MaterialProperty<T> &`; `declareADProperty<T>(name)` (MaterialBase.h:144) returns `ADMaterialProperty<T> &`. The `name` argument is first looked up as a `MaterialPropertyName` input parameter; if absent it is used verbatim (this is the "let user rename my output" idiom).
- `declareGenericProperty<T, is_ad>(name)` (MaterialBase.h:147) picks AD-ness at compile time -- the canonical pattern for `XxxMaterialTempl<bool is_ad>` classes (see `GenericConstantMaterialTempl`, `GenericFunctorMaterialTempl`).
- Stateful: there is **no** `declarePropertyOld`. You declare only the current property and consumers ask for `getMaterialPropertyOld<T>` / `getMaterialPropertyOlder<T>` (Material.h:111, Material.h:116). MOOSE then flags the property as stateful and calls `initQpStatefulProperties()` on the producing material at t=0 for it.
- `getGenericMaterialProperty<T, is_ad>(name, state)` (Material.h:96) is the unified getter; `state` 0/1/2 = current/old/older. AD versions only support state 0.
- `getMaterialPropertyByName` variants bypass the input-parameter indirection (use the literal property name).
- `getOptionalMaterialProperty<T>(name)` returns a proxy resolved later in `resolveOptionalProperties()`; the proxy has `bool` conversion so you can branch on existence.
- `coupledValue("var")` / `adCoupledValue("var")` work normally inside `Material` because of the `Coupleable` base; values are at the current `_qp`.
- `DerivativeMaterialInterface<Material>` (framework/include/materials/DerivativeMaterialInterface.h:32): use when you need to declare/consume `d(prop)/d(c1, c2, ...)` properties whose names follow the `Moose::derivativePropertyName` convention. Required for non-AD off-diagonal Jacobian contributions; AD users typically don't need it.
- FunctorMaterial: `addFunctorProperty<T>("name", [this](const auto & r, const auto & t) { ... }, {EXEC_ALWAYS})` (FunctorMaterial.h:35). The lambda is templated on the spatial argument type, so write it generically with `auto`. Consumers fetch with `getFunctor<T>("name")` and call `f(arg, state)`.
- Block restriction: `block = '...'` parameter is inherited; check with `hasBlocks(id)` / `blockIDs()`. Boundary restriction: `boundary = '...'`; check `_bnd`, `boundaryIDs()`. A material with `boundary` set produces a boundary material (`isBoundaryMaterial() == true`); BCs and SideKernels see only boundary materials. Volumetric kernels see only block materials. The two coexist silently.

## Registration & build

- `registerMooseObject("YourApp", YourMaterial);` in the .C file. Templated classes register both instantiations: `registerMooseObject("App", FooMaterial); registerMooseObject("App", ADFooMaterial);` where `using FooMaterial = FooMaterialTempl<false>; using ADFooMaterial = FooMaterialTempl<true>;`.
- The historical "templ" pattern is `class FooMaterialTempl<bool is_ad> : public Material` with `declareGenericProperty<T, is_ad>` calls; both true/false are explicitly instantiated at the bottom of the .C file (`template class FooMaterialTempl<false>; template class FooMaterialTempl<true>;`). See `framework/src/materials/GenericConstantMaterial.C:68-69` for the canonical example.
- Many older materials predate this and ship as separate `FooMaterial` (non-AD) and `ADFooMaterial` (AD) classes -- this is fine, just verbose.
- File locations: standard materials under `framework/src/materials/` or `modules/<module>/src/materials/`; functor materials under `framework/src/functormaterials/` or `modules/<module>/src/functormaterials/`. Headers mirror these paths under `include/`.

## Minimal scaffold

ADMaterial computing a temperature-dependent diffusivity `D = D0 * exp(-Q / (R * T))`, consuming AD coupled variable `temperature`, declaring AD `diffusivity`.

Header (`include/materials/ArrheniusDiffusivity.h`):

```cpp
#pragma once
#include "Material.h"

class ArrheniusDiffusivity : public Material
{
public:
  static InputParameters validParams();
  ArrheniusDiffusivity(const InputParameters & parameters);

protected:
  virtual void computeQpProperties() override;

  const ADVariableValue & _T;
  const Real _D0;
  const Real _Q;
  const Real _R;

  ADMaterialProperty<Real> & _diffusivity;
};
```

Source (`src/materials/ArrheniusDiffusivity.C`):

```cpp
#include "ArrheniusDiffusivity.h"

registerMooseObject("YourApp", ArrheniusDiffusivity);

InputParameters
ArrheniusDiffusivity::validParams()
{
  InputParameters params = Material::validParams();
  params.addClassDescription("AD Arrhenius diffusivity D = D0 * exp(-Q/(R*T)).");
  params.addRequiredCoupledVar("temperature", "Temperature variable [K].");
  params.addRequiredParam<Real>("D0", "Pre-exponential factor.");
  params.addRequiredParam<Real>("Q", "Activation energy.");
  params.addParam<Real>("R", 8.314, "Gas constant.");
  params.addParam<MaterialPropertyName>(
      "diffusivity_name", "diffusivity", "Name of the declared diffusivity property.");
  return params;
}

ArrheniusDiffusivity::ArrheniusDiffusivity(const InputParameters & parameters)
  : Material(parameters),
    _T(adCoupledValue("temperature")),
    _D0(getParam<Real>("D0")),
    _Q(getParam<Real>("Q")),
    _R(getParam<Real>("R")),
    _diffusivity(declareADProperty<Real>("diffusivity_name"))
{
}

void
ArrheniusDiffusivity::computeQpProperties()
{
  _diffusivity[_qp] = _D0 * std::exp(-_Q / (_R * _T[_qp]));
}
```

The FunctorMaterial equivalent declares the property in the constructor with `addFunctorProperty<ADReal>("diffusivity", [this](const auto & r, const auto & t) { return _D0 * std::exp(-_Q / (_R * _T_functor(r, t))); });` where `_T_functor = &getFunctor<ADReal>("temperature")`.

## Common pitfalls

1. **Forgetting `initQpStatefulProperties()` when a consumer asks for `getMaterialPropertyOld`.** MOOSE flags the property stateful, then at t=0 your old/older slots are zero-initialized garbage. If `initQpStatefulProperties` is not overridden you get whatever default the type has -- often fine for `Real` but disastrous for `RankTwoTensor`. Always override it for stateful materials.
2. **AD propagation broken by mixing non-AD coupled values into an AD property.** `coupledValue("v")[_qp]` returns `Real`, not `ADReal`. Assigning it into an `ADMaterialProperty<Real>` silently zeros the derivative seeds. Use `adCoupledValue` (and `adCoupledGradient`, etc.) consistently, and if you must consume a non-AD material property in an AD calculation, use `MaterialADConverter` or accept the loss of off-diagonal Jacobian terms.
3. **`getMaterialPropertyOld<T>(name)` returns the value at the start of the current timestep, not the previous nonlinear iterate.** People reach for it when they want the previous Newton step value (which is what Picard / explicit-coupling people often want); it's not that. Old is t_n, current is t_{n+1}.
4. **Boundary materials and block materials silently coexisting under the same name.** A `Material` declared with `block = '0'` and another declared with `boundary = 'left'` and the same `prop_names` are two different properties living in different storage. A volumetric Kernel sees only the block one; a sideset BC sees only the boundary one. If a kernel running on a boundary-adjacent face seems to "lose" your property, check which world it lives in.
5. **FunctorMaterial argument types.** The lambda is called with different argument types in different contexts: `ElemQpArg` (volumetric qp), `ElemSideQpArg` (side qp), `FaceArg` (FV face), `ElemPointArg` (arbitrary point in elem), `NodeArg` (node). Write the lambda generically with `auto` and access `.point` / `.elem` / `.fi` only via overloads or the `Moose::FaceArg` API. Don't capture `_qp` -- it is meaningless inside a functor lambda.
6. **`declareProperty<T>` called outside the constructor.** Property declaration must happen during construction (or during `initialSetup`) so the dependency resolver and storage allocator see it. Declaring inside `computeQpProperties` will assert/abort.
7. **Stateful + `constant_on = SUBDOMAIN`.** The "constant on subdomain" optimization computes the property at one qp and broadcasts. Stateful properties don't play well with this because the broadcast skips the per-qp initialization for old states; either drop `constant_on` or make sure your stateful initial values are also broadcast-safe.
8. **`addRequiredCoupledVar` vs `addCoupledVar` with a default**. `addCoupledVar("var", 1.0, "...")` lets users pass a constant in input (`var = 0.5`) and `coupledValue` will return that constant. AD users want `addCoupledVar("var", 1.0, "...")` plus `adCoupledValue` -- both work. But you cannot use `addRequiredCoupledVar` and supply a default; pick one.

