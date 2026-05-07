# Authoring: Contact module

The `contact` module enforces no-penetration (and friction/glue/cohesive) conditions between mechanical surfaces using either node-face or mortar discretizations, with Lagrange-multiplier, penalty, or augmented-Lagrange enforcement. This guide covers extending it: new mortar UOs, new node-face constraints, wiring `ContactModel`/`ContactFormulation` combos through `ContactAction`, custom CZMs, and AL-aware objects.

## When to use this (vs alternatives)

Decision tree:

- **Mortar vs node-face.** Mortar (variationally consistent surface integral) is preferred for finite-deformation, large-sliding, frictional, or curved contact. Node-face (`MechanicalContactConstraint` / `RANFSNormalMechanicalContact`) is the legacy, faster path and stays useful for small-sliding planar problems and explicit dynamics. Mortar requires a paired lower-dimensional mortar mesh; node-face uses framework `PenetrationLocator` only.
- **LM (Lagrange multiplier) vs penalty.** LM mortar adds a real nonlinear variable for the contact pressure (subclass `LMWeightedGapUserObject` and pair with `ComputeWeightedGapLMMechanicalContact`). Penalty mortar synthesizes the pressure from the gap (subclass `PenaltyWeightedGapUserObject`) — no extra solve variable, but tune `penalty`. Penalty is the only mortar option that integrates AL adaptively at the surface (`PenaltyWeightedGapUserObject` derives `AugmentedLagrangeInterface`).
- **Frictionless / glued / Coulomb.** Set via `ContactModel`. `FRICTIONLESS` and `GLUED` only need normal-gap UOs/constraints; `COULOMB` adds a frictional-force UO (`PenaltyFrictionUserObject` or `ComputeFrictionalForceLMMechanicalContact`) and a tangential-traction constraint.
- **CZM.** When the surface should carry traction even in tension (cohesion/damage), subclass `CohesiveZoneModelBase` and emit traction via `MortarGenericTraction`. CZM is mortar-only and penalty-style.
- **Explicit dynamics.** Use `ExplicitDynamicsContactConstraint` + `ExplicitDynamicsContactAction`; do not mix with the implicit objects in this guide.
- **Thermal contact.** Lives in `heat_transfer` (`ThermalContactAction`, `GapHeatTransfer`, `MortarGapHeatTransferAction`); shares `PenetrationLocator` but not the constraints documented here.
- **Optimization / XFEM.** Distinct constraint stacks. See [optimization-authoring.md] and [xfem-authoring.md].

## Contract

### **MechanicalContactConstraint** (modules/contact/include/constraints/MechanicalContactConstraint.h:27)
Purpose: node-face mechanical contact constraint enforcing equal normal force at coincident points across a primary/secondary interface; one instance per displacement component.
- **Required overrides**: `computeQpSecondaryValue` (line 43), `computeQpResidual(ConstraintType)` (line 45), `computeQpJacobian(ConstraintJacobianType)` (line 58), `computeQpOffDiagJacobian` (line 65), `getConnectedDofIndices` (line 73), `shouldApply` (line 86).
- **Optional overrides**: `timestepSetup` / `jacobianSetup` / `residualEnd` (lines 34-36) for stateful or AL bookkeeping; `AugmentedLagrangianContactConverged` (line 38), `updateAugmentedLagrangianMultiplier` (line 40), `updateContactStatefulData` (line 41) when implementing AL behavior; `addCouplingEntriesToJacobian` (line 84) to gate primary-secondary coupling.
- **validParams() additions**: `boundary` (secondary side, inherited from `NodeFaceConstraint`), `primary`, `component`, `model` (`ContactModel` enum), `formulation` (`ContactFormulation` enum), `penalty`, `friction_coefficient`, `tension_release`, `capture_tolerance`, AL tolerances (`al_penetration_tolerance`, `al_incremental_slip_tolerance`, `al_frictional_force_tolerance`).

### **WeightedGapUserObject / LMWeightedGapUserObject / PenaltyWeightedGapUserObject** (modules/contact/include/userobjects/WeightedGapUserObject.h:17, LMWeightedGapUserObject.h:21, PenaltyWeightedGapUserObject.h:23)
Mortar UOs that integrate the weighted gap on the lower-dimensional mortar segment mesh and expose contact pressure to constraint kernels.
- **Required overrides on `WeightedGapUserObject`**: `contactPressure()` (h:37) returning `ADVariableValue` at qps; `getNormalContactPressure(node)` (h:43); `test()` (h:109) returning the test function tied to the pressure; `constrainedByOwner()` (h:115) — return `true` if the constraint is enforced at the owning DOF (LM path), `false` if distributed (penalty path).
- **Optional overrides**: `computeQpProperties()` (h:99) for per-qp scratch; `computeQpIProperties()` (h:104) for per-qp/per-test work where the weighted gap actually accumulates into `_dof_to_weighted_gap`; `initialize`/`execute`/`finalize` if you need extra reduction.
- **validParams() additions**: pulls `MortarConsumerInterface` and `TwoMaterialPropertyInterface` params; couple `disp_x`/`disp_y`/`disp_z`. `LMWeightedGapUserObject` adds `lm_variable` (real LM nonlinear variable), `aux_lm` (Petrov-Galerkin), `use_petrov_galerkin`. `PenaltyWeightedGapUserObject` adds `penalty`, `penalty_multiplier`, `penetration_tolerance`, `max_penalty_multiplier`, `adaptivity_penalty_normal` (`SIMPLE` or `BUSSETTA`), `use_physical_gap`, and inherits AL hooks via `AugmentedLagrangeInterface`.

### **CohesiveZoneModelBase** (modules/contact/include/userobjects/CohesiveZoneModelBase.h:20)
Base for mortar CZMs. Multiply-inherits `PenaltyWeightedGapUserObject` (normal pressure path) and `WeightedVelocitiesUserObject` (tangential slip).
- **Required overrides**: `computeCZMTraction(node)` (h:49) — set `_dof_to_czm_traction[node]` from interface kinematics; `computeDamage(node)` (h:51).
- **Optional overrides**: `computeQpProperties` / `computeQpIProperties` (h:38-39) to populate per-node strength/fracture interpolations; `prepareJumpKinematicQuantities` (h:45) and `computeFandR(node)` (h:46) if the default rotation/jump bookkeeping needs adjusting.
- **validParams() additions**: pulls `PenaltyWeightedGapUserObject` and `WeightedVelocitiesUserObject` params; subclasses (e.g. `BilinearMixedModeCohesiveZoneModel`) add `normal_strength`, `shear_strength`, `GI_c`, `GII_c`, `mixed_mode_criterion`, `power_law_parameter`, `viscosity`, `regularization_alpha`, `penalty_stiffness_czm`.
- **Pair with** `MortarGenericTraction` (modules/contact/include/constraints/MortarGenericTraction.h:16) — one constraint per displacement `component`, holding a `const CohesiveZoneModelBase &` reference.

### **ContactAction** (modules/contact/include/actions/ContactAction.h:31)
Recipe to wire a new `ContactModel` × `ContactFormulation` combination:
1. Add the enum value to `CreateMooseEnumClass(ContactModel, ...)` or `CreateMooseEnumClass(ContactFormulation, ...)` at modules/contact/include/actions/ContactAction.h:16-24. Update `getModelEnum()` / `getFormulationEnum()` strings in `ContactAction.C`.
2. In `ContactAction::act()` (modules/contact/src/actions/ContactAction.C around line 482) the formulation enum routes to `addMortarContact()` (line 760) for `MORTAR`/`MORTAR_PENALTY` or `addNodeFaceContact()` (line 1234) otherwise. Decide which branch the new combo lives in.
3. For mortar: in `addMortarContact()` extend the `add_user_object`, `add_mortar_variable`, `add_constraint` task blocks with `if (_formulation == ... && _model == ...)` to emit the right UO type, LM variables (if `MORTAR`), and constraint type. The pattern is `_problem->addUserObject(uo_type, name, params)` then `_problem->addConstraint("ComputeWeightedGapLMMechanicalContact" or "MortarGenericTraction" or ...)`.
4. For node-face: in `addNodeFaceContact()` (line 1234) set `constraint_type` per formulation (`RANFS` → `RANFSNormalMechanicalContact`, default → `MechanicalContactConstraint`). Coulomb adds a tangential constraint loop.
5. Validate illegal combos at the top of `act()` (e.g. line 323 rejects `TANGENTIAL_PENALTY` without `COULOMB`; line 327 forces `MORTAR_PENALTY` to single-pair).

Do not skip the action: if you instantiate `MechanicalContactConstraint` directly under `[Constraints]` while also using mortar, you will double-count the contact force.

### **AugmentedLagrangianContactProblem** + **AugmentedLagrangeInterface** (modules/contact/include/problems/AugmentedLagrangianContactProblem.h:25, AugmentedLagrangianContactProblemInterface.h:18, userobjects/AugmentedLagrangeInterface.h:18)
Recipe for AL-aware UO/constraint:
1. Use `[Problem] type = AugmentedLagrangianContactProblem` (templated on `ReferenceResidualProblem`) or `AugmentedLagrangianContactFEProblem`. The problem owns `_lagrangian_iteration_number` and `_maximum_number_lagrangian_iterations` (interface h:34-37).
2. Make your UO multiply-inherit `AugmentedLagrangeInterface` (or derive from `PenaltyWeightedGapUserObject`, which already does). Pass `this` to its constructor.
3. Override `isAugmentedLagrangianConverged()` (return `true` once your gap/slip tolerances are met), `augmentedLagrangianSetup()` (called once per AL outer iteration to reset/update penalty), and `updateAugmentedLagrangianMultipliers()` (push the new λ from the current penalty × gap). See `PenaltyWeightedGapUserObject.C` lines 226 / 287 / 299 for the canonical implementation.
4. Drive the loop with `[Convergence] type = AugmentedLagrangianContactConvergence` (modules/contact/src/convergence/AugmentedLagrangianContactConvergence.C:128-155) — it queries the UO and calls the hooks until convergence or `_maximum_number_lagrangian_iterations`.
5. Node-face constraints get the same hooks via `MechanicalContactConstraint::AugmentedLagrangianContactConverged` / `updateAugmentedLagrangianMultiplier` (h:38-40), but the outer loop dispatcher is the same.

## Coupling & material properties

Contact-specific items the framework does not provide elsewhere:

- **PenetrationLocator**: provided by framework geomsearch, included via `#include "PenetrationLocator.h"` and consumed by `NodeFaceConstraint`-based classes. Drives `PenetrationInfo` (`_pinfo`) used in `computeContactForce`. Shared with thermal contact.
- **NodalArea** (modules/contact/include/userobjects/NodalArea.h): per-node tributary area used by penalty normalization (`_normalize_penalty`) and by `MechanicalContactConstraint::nodalArea()`.
- **Weighted gap** (`_dof_to_weighted_gap`, map of DofObject → (ADReal sum, normalization)): the integral of the gap against a test function on the mortar segment mesh. `WeightedGapUserObject::physicalGap()` divides out the normalization.
- **Contact pressure** is exposed as `ADVariableValue` on mortar segment qps via `WeightedGapUserObject::contactPressure()`. LM path: aliases the LM solution variable. Penalty path: `(penalty * gap + λ_AL)` synthesized in `PenaltyWeightedGapUserObject::reinit()`.
- **Primary/secondary surfaces**: canonical naming. The legacy `master`/`slave` aliases still appear in some tests and old PRs but new code should use primary/secondary throughout.
- **Mortar mesh / dual mortar**: `ContactAction` builds the lower-dimensional segment mesh when `_generate_mortar_mesh` is true. `_use_dual` switches LM bases to dual functions for diagonal mass-matrix-like behavior. Required for `LMWeightedGapUserObject::verifyLagrange` checks.
- **`CohesiveZoneModelBase` extras**: `_dof_to_rotation_matrix`, `_dof_to_interface_F`, `_dof_to_displacement_jump`, `_dof_to_damage` — all per-node maps populated in `prepareJumpKinematicQuantities`.

## Registration & build

- `registerMooseObject("ContactApp", YourClass);` exactly as in `MechanicalContactConstraint.C:30`, `PenaltyWeightedGapUserObject.C:15`, `ComputeWeightedGapLMMechanicalContact.C:26`, `MortarGenericTraction.C:13`, `BilinearMixedModeCohesiveZoneModel.C:24`, `AugmentedLagrangianContactProblem.C:32-33`.
- Apps must enable the module flag `CONTACT := yes` in their `Makefile` (and `MODULES += contact` if pulling via `<modules>/Makefile`).
- Headers go under `modules/contact/include/{constraints,userobjects,actions,problems,convergence,...}`. Source mirrors that layout under `modules/contact/src/`.
- For AL: outer iteration is the `AugmentedLagrangianContactConvergence` loop; inner iteration is the standard Newton solve. Do not place AL state updates inside `computeQpResidual` — they belong in the AL hooks called between outer iterations.

## Minimal scaffold

A custom mortar UO that integrates a scalar quantity (here, a "weighted normal gap squared" diagnostic) on the mortar interface. Two files, ~30-40 lines each.

`include/userobjects/WeightedGapSquaredUserObject.h`:

```cpp
#pragma once

#include "WeightedGapUserObject.h"

class WeightedGapSquaredUserObject : public virtual WeightedGapUserObject
{
public:
  static InputParameters validParams();
  WeightedGapSquaredUserObject(const InputParameters & parameters);

  virtual const ADVariableValue & contactPressure() const override { return _zero_pressure; }
  virtual Real getNormalContactPressure(const Node * const) const override { return 0.0; }
  Real getWeightedGapSquared(const Node * const node) const;

protected:
  virtual void computeQpIProperties() override;
  virtual const VariableTestValue & test() const override { return *_test; }
  virtual bool constrainedByOwner() const override { return false; }

  std::unordered_map<const DofObject *, ADReal> _dof_to_gap_squared;
  ADVariableValue _zero_pressure;
};
```

`src/userobjects/WeightedGapSquaredUserObject.C`:

```cpp
#include "WeightedGapSquaredUserObject.h"

registerMooseObject("ContactApp", WeightedGapSquaredUserObject);

InputParameters
WeightedGapSquaredUserObject::validParams()
{
  auto params = WeightedGapUserObject::validParams();
  params.addClassDescription("Diagnostic UO: integrates the squared weighted normal gap.");
  return params;
}

WeightedGapSquaredUserObject::WeightedGapSquaredUserObject(const InputParameters & parameters)
  : WeightedGapUserObject(parameters)
{
}

void
WeightedGapSquaredUserObject::computeQpIProperties()
{
  WeightedGapUserObject::computeQpIProperties();           // accumulates _dof_to_weighted_gap
  const DofObject * dof = _is_weighted_gap_nodal ? static_cast<const DofObject *>(_lower_secondary_elem->node_ptr(_i))
                                                 : static_cast<const DofObject *>(_lower_secondary_elem);
  _dof_to_gap_squared[dof] += (*_test)[_i][_qp] * _qp_gap * _qp_gap * _JxW_msm[_qp] * _coord[_qp];
}

Real
WeightedGapSquaredUserObject::getWeightedGapSquared(const Node * const node) const
{
  return MetaPhysicL::raw_value(findValue(_dof_to_gap_squared, static_cast<const DofObject *>(node), ADReal(0)));
}
```

For a real constraint, you would also reinit `contactPressure()` and pair this UO with `ComputeWeightedGapLMMechanicalContact` (LM) or extend `PenaltyWeightedGapUserObject` (penalty) instead.

## Common pitfalls

1. **master/slave → primary/secondary terminology shift.** Existing inputs and tests still use `master`/`slave`; both parse but new code, params, and class members must use primary/secondary. `MechanicalContactConstraint`'s `_primary_secondary_jacobian` member is the canonical naming.
2. **Illegal `ContactModel` × `ContactFormulation` combos.** `TANGENTIAL_PENALTY` requires `COULOMB` (ContactAction.C:323). `MORTAR_PENALTY` only supports a single primary/secondary pair (line 327). `MORTAR` + 3D `COULOMB` requires extra constraints per displacement (line 552). The action errors at construction; check there before chasing run-time issues.
3. **Don't add `MechanicalContactConstraint` manually when using mortar.** `ContactAction` emits constraints for you based on `formulation`. Adding a `[Constraints]` block of your own on top of `[Contact]` doubles the contact force and is a common cause of "non-physical contact pressure" reports.
4. **LM mortar requires a real nonlinear LM variable; penalty mortar synthesizes.** With `LMWeightedGapUserObject`, you must declare a nonlinear `lm_variable` (continuous on the secondary side, often `LAGRANGE` or dual `LAGRANGE`) and `verifyLagrange` will error if its DOFs aren't nodal. With `PenaltyWeightedGapUserObject`, do not declare an LM variable — pressure is computed from the gap.
5. **Primary/secondary mesh-fineness rule.** The secondary side should be the finer (or softer, if stiffness mismatches) of the two. Reversing it inverts the projection and produces non-monotone gap residuals; this is mesh dependent and easy to overlook.
6. **Thermal contact lives in `heat_transfer`, not here.** `ThermalContactAction`, `GapHeatTransfer`, and `MortarGapHeatTransferAction` are in modules/heat_transfer. They share `PenetrationLocator` but have an entirely separate constraint/UO stack — don't try to extend `WeightedGapUserObject` for thermal problems.
7. **AL hooks live on the UO, the outer loop on the Problem.** Forgetting `[Problem] type = AugmentedLagrangianContactProblem` while subclassing `PenaltyWeightedGapUserObject` silently disables AL: `_augmented_lagrange_problem` becomes null, `_lagrangian_iteration_number` is forced to zero, and your AL multipliers are never updated.

