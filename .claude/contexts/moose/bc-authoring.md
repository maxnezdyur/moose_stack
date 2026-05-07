# Authoring: Boundary Conditions

How to write a MOOSE boundary-condition C++ object: pick the right base, fill the residual hook, register, and avoid the AD/FV/sign traps below. NodalBCs *overwrite* the residual at the boundary node; IntegratedBCs *add* to it.

## When to use this (vs alternatives)

Decision tree — answer top-down:

1. **Discretization?**
   - Continuous-Galerkin FE → `bcs/` (NodalBC or IntegratedBC families).
   - Cell-centered FV (nonlinear / Newton) → `fvbcs/` (`FVDirichletBCBase`, `FVFluxBC`).
   - Linear FV (segregated, matrix-assembled) → `linearfvbcs/` (`LinearFVAdvectionDiffusionBC`).
   - DG / HDG / hybridized → see `bcs/IPHDG*`, `bcs/DG*`, `bcs/*HFEM*` (out of scope here).

2. **Strong-form vs weak-form (FE only)?**
   - Strong / essential (set `u = g` exactly at nodes) → `NodalBC` lineage. Pick `DirichletBCBase` if the constraint is `u = computeQpValue()`; pick `NodalBC` directly only if you need a residual that isn't `_u - g`.
   - Weak / natural (boundary integral on `<f, v>`) → `IntegratedBC` lineage.

3. **AD or hand-coded Jacobian (FE only)?**
   - Default to AD: `ADDirichletBC` / `ADIntegratedBC`. Cheaper to author, no off-diag bookkeeping.
   - Drop to non-AD only if (a) you must couple to a non-AD-only material, (b) you need to override `computeQpOffDiagJacobian` to skip terms for performance, or (c) you're subclassing an existing non-AD BC family.
   - For both: subclass via `GenericIntegratedBC<is_ad>` + `NeumannBCTempl<is_ad>` pattern (see `CoupledVarNeumannBC`, `MatNeumannBC`). FV BCs are AD only.

4. **Specialized FE shortcut bases?**
   - Constant-or-functor flux on the boundary → subclass `NeumannBC` (sign already correct) instead of writing a fresh `IntegratedBC`.
   - Robin-type `αu + β∂ₙu = g` → see `ADRobinBC` for the canonical shape.
   - `q · n` style flux where you have `q` as a vector → `FluxBC` (FE) — but read pitfalls; the canonical pattern is to write an `ADIntegratedBC` directly.

5. **Cross-links**
   - Constraint between two boundaries (gap, matched value across an interface, periodic) → mortar / constraint objects, see contact-authoring.md.
   - Volumetric residual, not boundary → see kernel-authoring.md.
   - Interior-face DG numerical flux → DGKernel, not a BC.

## Contract

### **BoundaryCondition** (framework/include/bcs/BoundaryCondition.h:22)
Purpose: shared root for all FE boundary conditions; provides boundary restriction, tagging, geometric search.
- **Required overrides**: none directly; all subclasses go through `NodalBCBase` or `IntegratedBCBase`.
- **Optional overrides**: `shouldApply()` (gate execution; in NodalBCs the variable values *are* available, in IntegratedBCBase the default already skips when the variable is undefined next to the boundary — call the base if you override).
- **validParams() additions**: inherits `boundary` (required), `variable`, tagging.

### **NodalBCBase** (framework/include/bcs/NodalBCBase.h:26)
Purpose: root for *strong-form* node-based BCs (residual is overwritten at the boundary node).
- **Required overrides**: none directly; subclass `NodalBC` or `ADDirichletBCBase`.
- **Optional overrides**: `checkNodalVar()` returns true; override to false for vector/array nodal variants.
- **validParams() additions**: `save_in`, `diag_save_in` (residual / diagonal-Jacobian aux output).

### **NodalBC** (framework/include/bcs/NodalBC.h:20)
Purpose: scalar non-AD node BC; you write `r = computeQpResidual()` and (optionally) Jacobian entries.
- **Required overrides**: `Real computeQpResidual()` — return the residual *value at the node* (it overwrites, so for a Dirichlet `u = g` write `_u[_qp] - g`).
- **Optional overrides**: `computeQpJacobian()` (default 1.0 → identity row), `computeQpOffDiagJacobian(unsigned int jvar)` (default 0).
- **validParams() additions**: none beyond `NodalBCBase`.
- **Available members**: `_var`, `_current_node`, `_u` (variable value at node), `_qp = 0`.

### **DirichletBCBase** (framework/include/bcs/DirichletBCBase.h:17)
Purpose: thin specialization where the residual is `_u - computeQpValue()`; supports preset of the solution vector.
- **Required overrides**: `Real computeQpValue()` — return the prescribed nodal value.
- **Optional overrides**: usually none; do *not* re-override `computeQpResidual()`.
- **validParams() additions**: `preset` bool (default true) — when true, MOOSE applies the value directly to the solution vector before residual evaluation, which is more robust for nonlinear solves.

### **DirichletBC** (framework/include/bcs/DirichletBC.h:19)
Purpose: concrete `u = constant` BC. Pattern to copy when authoring `<Source>DirichletBC`.

### **ADDirichletBCBase** (framework/include/bcs/ADDirichletBCBase.h:17)
Purpose: AD root for Dirichlet-style nodal BCs. Pure-virtual `computeValue(NumericVector<Number> &)`. Most authors actually subclass `ADDirichletBCBaseTempl<T>` (framework/include/bcs/ADDirichletBCBaseTempl.h:19) which already implements `computeValue` and asks you for `computeQpValue() -> ADReal` only.

### **ADDirichletBC** (framework/include/bcs/ADDirichletBC.h:19)
Purpose: AD analogue of `DirichletBC`. *Not* a typedef of `DirichletBC` — it's a separate class deriving from `ADDirichletBCBaseTempl<Real>`. Both can coexist in an input file.

### **IntegratedBCBase** (framework/include/bcs/IntegratedBCBase.h:19)
Purpose: root for *weak-form* boundary integrals. Provides the side quadrature loop machinery (`_qp`, `_qrule`, `_JxW`, `_coord`, `_current_side`, `_current_boundary_id`).
- **Required overrides**: none directly; subclass `IntegratedBC` or `ADIntegratedBCTempl<T>`.
- **Optional overrides**: `shouldApply()` (default skips boundary segments where the variable isn't defined; if you override, call `IntegratedBCBase::shouldApply()` first or suppress `_skip_execution_outside_variable_domain` in params).
- **validParams() additions**: `save_in`, `diag_save_in`, `skip_execution_outside_variable_domain`.

### **IntegratedBC** (framework/include/bcs/IntegratedBC.h:18)
Purpose: scalar non-AD integrated BC.
- **Required overrides**: `Real computeQpResidual()`.
- **Optional overrides**: `computeQpJacobian()`, `computeQpOffDiagJacobian(jvar)`, `computeQpOffDiagJacobianScalar(jvar)`, plus `precalculateQp{Residual,Jacobian,OffDiagJacobian}` for hoisting per-qp work.
- **Available members**: `_var`, `_u`, `_grad_u`, `_normals`, `_test`, `_grad_test`, `_phi`, `_grad_phi`, `_qp`, `_i`, `_j`, `_q_point`, `_JxW`.

### **ADIntegratedBCTempl<T>** (framework/include/bcs/ADIntegratedBC.h:20)
Purpose: AD integrated BC, templated on `Real` (`ADIntegratedBC`) or `RealVectorValue` (`ADVectorIntegratedBC`).
- **Required overrides**: `ADReal computeQpResidual()`.
- **Optional overrides**: none — Jacobians come from AD. You can override `computeResidualsForJacobian` for performance but rarely should.
- **Available members**: AD versions of `_u`, `_grad_u`, `_normals`, `_ad_q_points`, `_ad_JxW`, `_ad_coord`; non-AD `_test`, `_grad_test`, `_phi`.

### **FluxBC** (framework/include/bcs/FluxBC.h:19)
Purpose: convenience non-AD base for residuals of the form `<q · n, v>`. You provide vector `q` and its derivative.
- **Required overrides**: `RealGradient computeQpFluxResidual()`, `RealGradient computeQpFluxJacobian()`.
- **Optional overrides**: usually none; `computeQpResidual` and `computeQpJacobian` are final-ish (defined in base to dot with `_normals`).
- **Caveat**: the fact that `computeQpFluxJacobian` is *required* even when the flux is solution-independent is a known footgun — most authors prefer a hand-rolled `IntegratedBC`.

### **FVBoundaryCondition** (framework/include/fvbcs/FVBoundaryCondition.h:46)
Purpose: AD-only root for cell-centered FV BCs. All FV BCs are AD; non-AD FV does not exist in MOOSE.
- **Required overrides**: none directly; subclass `FVDirichletBCBase` or `FVFluxBC`.
- **Optional overrides**: `hasFaceSide(fi, fi_elem_side)` if your BC must support being applied to internal faces.
- **Available members**: `_var` (`MooseVariableFV<Real> &`), `_face_info`, `_subproblem`, `_fv_problem`, `_mesh`. Use `singleSidedFaceArg()` to evaluate functors on the boundary face.

### **FVFluxBC** (framework/include/fvbcs/FVFluxBC.h:23)
Purpose: AD-only flux contribution at a boundary face, returned to the owning element.
- **Required overrides**: `ADReal computeQpResidual()` — return the flux *out of* the element through the face (sign convention: positive return means flux leaving, contributing positively to the element residual; see `FVNeumannBC::computeQpResidual` returning `-_value`).
- **Optional overrides**: nothing typical.
- **Available members**: `_qp = 0` (FV is one point per face), `_u`, `_u_neighbor`, `_normal`, `uOnUSub()`, `uOnGhost()`, `elemArg()`, `neighborArg()`, `_face_type`.

### **FVDirichletBCBase** (framework/include/fvbcs/FVDirichletBCBase.h:19)
Purpose: AD-only Dirichlet-on-the-face for FV. The framework consumes the face value when computing fluxes in interior kernels — this object does not produce a residual itself.
- **Required overrides**: `ADReal boundaryValue(const FaceInfo & fi, const Moose::StateArg & state) const`.
- **Optional overrides**: rarely.

### **LinearFVBoundaryCondition** (framework/include/linearfvbcs/LinearFVBoundaryCondition.h:43)
Purpose: non-AD root for the segregated linear-FV solver. Each BC must report a face value and a normal-gradient value; concrete kernels then pull matrix/RHS contributions through `LinearFVAdvectionDiffusionBC`.
- **Required overrides**: `Real computeBoundaryValue() const`, `Real computeBoundaryNormalGradient() const`.
- **Optional overrides**: `hasFaceSide(fi, fi_elem_side)`.
- **Available members**: `_var` (`MooseLinearVariableFV<Real> &`), `_current_face_info`, `_current_face_type`, helpers `computeCellToFaceDistance()`, `computeCellToFaceVector()`, `singleSidedFaceArg()`, `functorFaceArg()`. Note: there is no `LinearFVFluxBC.h` — flux-style BCs subclass `LinearFVAdvectionDiffusionBC`.

### **LinearFVAdvectionDiffusionBC** (framework/include/linearfvbcs/LinearFVAdvectionDiffusionBC.h:20)
Purpose: linear-FV BC tailored to the advection-diffusion kernel pair. Authors implement four matrix/RHS contribution methods directly (no AD).
- **Required overrides**: `computeBoundaryValueMatrixContribution()`, `computeBoundaryValueRHSContribution()`, `computeBoundaryGradientMatrixContribution()`, `computeBoundaryGradientRHSContribution()`, plus the two from `LinearFVBoundaryCondition`.
- **Optional overrides**: `includesMaterialPropertyMultiplier()` (true for Neumann-on-diffusion), `useBoundaryGradientExtrapolation()` (true for Dirichlet-style BCs that derive the gradient from the prescribed value).

## Coupling & material properties

- **FE non-AD**: `coupledValue("v")` → `VariableValue &`, `coupledGradient("v")` → `VariableGradient &`. Off-diagonal Jacobian is on you: override `computeQpOffDiagJacobian(jvar)` and gate on the coupled var number cached in the constructor (`coupled("v")`). See `CoupledVarNeumannBC::computeQpOffDiagJacobian` (framework/src/bcs/CoupledVarNeumannBC.C:46).
- **FE AD**: `adCoupledValue("v")` / `adCoupledGradient("v")`; the AD framework picks up off-diagonals automatically — do *not* implement `computeQpOffDiagJacobian`.
- **Templated AD/non-AD pair**: use `GenericVariableValue<is_ad>` and `coupledGenericValue<is_ad>("v")` in a `Templ<bool is_ad>` class, then `typedef` both. Pattern: `CoupledVarNeumannBC` (framework/include/bcs/CoupledVarNeumannBC.h:23).
- **Material properties**: `getMaterialProperty<T>("name")` (non-AD) / `getADMaterialProperty<T>("name")` (AD) / `getGenericMaterialProperty<T, is_ad>("name")` in templated code. Materials must be declared on the relevant `boundary`, not on a subdomain — qprops on a side need `Material` blocks with `boundary = ...`. Stateful (`getMaterialPropertyOld<T>`) works on boundaries the same way.
- **Functors**: `getFunctor<T>("name")` works in FE, FV, and LinearFV BCs. Evaluate on the face via `singleSidedFaceArg(_face_info)` (FV) or `functorFaceArg(functor, _current_face_info)` (LinearFV).
- **NodalBC pitfall — coupled gradients**: gradients are not naturally defined at a node; coupling `_grad_v[_qp]` inside a NodalBC compiles but pulls a stale or zero value depending on the variable's FE family. Use an IntegratedBC if you need a gradient.
- **NeumannBC subclasses consuming a coupled gradient**: the inherited `_value` is a `Real`; if your physics needs `g(x, t, v)` per qp, derive from `IntegratedBC` directly, *not* `NeumannBC`, and write `-_test[_i][_qp] * g` yourself (matches the inherited sign).
- **FV face-flux evaluation**: `_u[_qp]` and `_u_neighbor[_qp]` resolve to the cell-center values; for face-evaluated functor data (e.g. an upwind-limited density) call `singleSidedFaceArg` and pass into the functor, otherwise the limiter is bypassed.

## Registration & build

```cpp
registerMooseObject("MooseApp", MyBC);          // non-AD
registerMooseObject("MooseApp", ADMyBC);        // AD
// or, for templated AD/non-AD pair:
registerMooseObject("MooseApp", MyBCTempl<false>);
registerMooseObject("MooseApp", MyBCTempl<true>);
```

For an *app* (blackbear/isopod), replace `"MooseApp"` with the app name (e.g. `"BlackbearApp"`). Registration goes in the `.C`, exactly once.

File locations:
- FE BCs: `framework/include/bcs/MyBC.h`, `framework/src/bcs/MyBC.C` (or `<app>/include/bcs/...`).
- FV BCs: `.../include/fvbcs/MyBC.{h,C}`.
- Linear-FV BCs: `.../include/linearfvbcs/MyBC.{h,C}`.

Explicit instantiation for templated `<bool is_ad>` classes — at the bottom of the `.C`:

```cpp
template class MyBCTempl<false>;
template class MyBCTempl<true>;
```

Documentation page: `framework/doc/content/source/bcs/MyBC.md` (or `<app>/doc/...`) with `!syntax description /BCs/MyBC` + `!syntax parameters /BCs/MyBC` + `!syntax inputs /BCs/MyBC` + `!syntax children /BCs/MyBC`. See moose-doc-standards.

## Minimal scaffold

A Robin BC `α u + ∂_n u = 0`, AD, with a coupled variable substituting for `α`:

```cpp
// framework/include/bcs/MyRobinBC.h
#pragma once
#include "ADIntegratedBC.h"

class MyRobinBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();
  MyRobinBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  /// Coefficient α (constant)
  const Real _alpha;
  /// Optional coupled scaling field
  const ADVariableValue & _scale;
};
```

```cpp
// framework/src/bcs/MyRobinBC.C
#include "MyRobinBC.h"

registerMooseObject("MooseApp", MyRobinBC);

InputParameters
MyRobinBC::validParams()
{
  InputParameters params = ADIntegratedBC::validParams();
  params.addClassDescription(
      "Imposes the Robin BC $\\alpha\\, s\\, u + \\partial_n u = 0$ in weak form.");
  params.addParam<Real>("alpha", 1.0, "Robin coefficient.");
  params.addCoupledVar("scale", 1.0, "Optional spatial scaling of the Robin term.");
  return params;
}

MyRobinBC::MyRobinBC(const InputParameters & parameters)
  : ADIntegratedBC(parameters),
    _alpha(getParam<Real>("alpha")),
    _scale(adCoupledValue("scale"))
{
}

ADReal
MyRobinBC::computeQpResidual()
{
  // Weak form: integrate (α s u) v over the boundary.
  // Sign matches NeumannBC: the natural-BC term coming from integration by parts.
  return _alpha * _scale[_qp] * _u[_qp] * _test[_i][_qp];
}
```

## Common pitfalls

1. **NodalBC residual sign.** A NodalBC residual is *the row of the residual at that DOF*, fully overwriting it. For `u = g`, write `_u[_qp] - g`, not `g - _u[_qp]`. Getting the sign wrong gives a converged-but-wrong solution because the linearization sign also flips. Don't forget `_qp = 0` is mandatory — there is no quadrature loop at a node.

2. **`ADDirichletBC` is *not* `DirichletBC`.** They are sibling concrete classes. Mixing AD and non-AD BCs on the same variable is allowed but causes silent Jacobian assembly inefficiency (the AD path computes a full block Jacobian, the non-AD path expects you to fill diag/off-diag manually). Pick one family per variable.

3. **`NeumannBC` sign convention.** `NeumannBC::computeQpResidual` returns `-_test[_i][_qp] * _value` (framework/src/bcs/NeumannBC.C:41) — the minus comes from integrating the diffusion operator by parts assuming a `(∇u, ∇v)` kernel. If you subclass `NeumannBC` and forget to keep the minus sign in your override, your flux will be wrong and indistinguishable from a sign error in the kernel.

4. **`FluxBC` has a hand-coded Jacobian even in trivial cases.** `FluxBC` (framework/include/bcs/FluxBC.h:19) requires `computeQpFluxJacobian()` — non-AD only, and there is no AD equivalent. For modern code prefer writing an `ADIntegratedBC` from scratch; only subclass `FluxBC` to extend an existing FluxBC subclass.

5. **FV flux sign convention.** `FVFluxBC::computeQpResidual` returns the flux out of the owning element through the boundary face: positive value = flux leaving = positive contribution to the element residual. `FVNeumannBC` returns `-_value` because `_value` is *into* the domain by user convention (framework/src/fvbcs/FVNeumannBC.C:31). If your FV BC produces wrong-sign mass balance, this is almost always why.

6. **FV Dirichlet does not write a residual.** `FVDirichletBCBase::boundaryValue` is *consumed by the interior FV flux kernels* when they evaluate the face. There is no residual term and no `computeQpResidual`. Do not also register an `FVFluxBC` on the same variable+boundary — the framework will error or double-count.

7. **NodalBC + coupled gradient is a trap.** `_grad_v[_qp]` at a node is undefined for Lagrange variables and zero for L2 variables; use an IntegratedBC if your formulation needs a gradient. Same applies to evaluating face-only functors at a node.

8. **`shouldApply()` interactions.** If you override `shouldApply()` on an IntegratedBC, the default skip-when-variable-not-defined-here logic is lost. Either call `IntegratedBCBase::shouldApply()` first or set `params.suppressParameter<bool>("skip_execution_outside_variable_domain")` so users don't expect it to work.

9. **`preset` semantics for Dirichlet.** With `preset = true` (default for `DirichletBCBase`), MOOSE writes `computeQpValue()` directly into the solution vector before residual evaluation, bypassing the residual row. Combined with a hand-coded `computeQpJacobian()` returning anything other than 1, this produces an inconsistent Newton system. Don't override the Jacobian on preset Dirichlets.

