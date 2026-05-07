# Authoring: UserObjects

UserObjects are the MOOSE generalization for "compute something during the solve and expose it to other objects." They cover everything from simple termination checks to mesh-spanning reductions, threaded element loops, mortar integrals, and spatial fields queried by inter-app transfers.

## When to use this (vs alternatives)

Decision tree:
- Reduce values from the mesh into a state usable by other objects? -> **UserObject** family.
- Just want to output a scalar/vector to disk or query its value? -> see [postprocessor-authoring.md](./postprocessor-authoring.md) (a Postprocessor IS a UserObject under the hood — pick PP if it's only used for output).
- Need to compute a value at qps for kernels/BCs? -> see [material-authoring.md](./material-authoring.md).
- Need to write back into an AuxVariable on the mesh? -> see [auxkernel-authoring.md](./auxkernel-authoring.md).
- Need to check a stop condition? -> **Terminator** (a `GeneralUserObject`).
- Need to reduce shape-function-aware Jacobian-like contributions? -> **ShapeUserObject<T>**.
- Need to control which elements/dofs are ghosted to a rank? -> **GhostingUserObject**.

Loop-scope sub-tree — pick the smallest base that covers your read access:

| Need to read…                                              | Pick                                                          |
| ---------------------------------------------------------- | ------------------------------------------------------------- |
| Nothing from the mesh; just postprocessors / scalars / time | `GeneralUserObject`                                           |
| Element-interior qp values + materials                      | `ElementUserObject`                                           |
| Boundary side qp values (one side only)                     | `SideUserObject`                                              |
| Internal side qp values from both elem and neighbor         | `InternalSideUserObject`                                      |
| Interface side qp values across two-block interface         | `InterfaceUserObject` (extends `InterfaceUserObjectBase`)     |
| Combination of element + boundary + internal side + interface in one mesh pass | `DomainUserObject`                            |
| Mortar segment qp values (primary + secondary)              | `MortarUserObject`                                            |
| Per-node aggregations                                       | `NodalUserObject`                                             |
| General UO that itself runs threaded                        | `ThreadedGeneralUserObject`                                   |

## Contract

### **UserObject** (`framework/include/userobjects/UserObject.h:19`)
Purpose: abstract base. Defines the `execute()` / `threadJoin()` mesh-loop contract and the optional `spatialValue(Point)` hook.
- **Pure virtual**: `execute()`, `threadJoin(const UserObject &)`.
- **`spatialValue(const Point &)`**: default throws; override to make the UO queryable by Transfers (`MultiAppUserObjectTransfer`, `SpatialUserObjectFunctor`).
- **`spatialPoints()`**: optional companion when the consumer wants the discrete sample locations.

### **UserObjectBase** (`framework/include/userobjects/UserObjectBase.h:37`)
Purpose: shared lifecycle + interfaces (Restartable, MeshChanged, ScalarCoupleable, Reporter, etc.).
- **Pure virtual**: `initialize()`, `finalize()`.
- **`gatherSum<T>` / `gatherMax<T>` / `gatherMin<T>` / `gatherProxyValueMax|Min`**: reduce across MPI ranks; call from `finalize()`.
- **`needThreadedCopy()`**: returns true if MOOSE must clone one copy per thread (default false; `ThreadedGeneralUserObject` forces true).
- **`shouldDuplicateInitialExecution()`**: re-runs the UO during IC evaluation when an IC depends on it.

### **GeneralUserObject** (`framework/include/userobjects/GeneralUserObject.h:22`)
Purpose: no mesh loop. `execute()` runs once per `execute_on` flag on rank 0's primary thread.
- `threadJoin()` and `subdomainSetup()` are stubbed out — do not override.
- Adds `MaterialPropertyInterface` + `ScalarCoupleable` + `TransientInterface`, but you cannot read `_qp` material props because there is no qp loop.
- Use for: cross-postprocessor logic, file IO, time-based decisions, `Terminator`-style checks.

### **ElementUserObject** (`framework/include/userobjects/ElementUserObject.h:27`)
Purpose: element-loop. `execute()` runs per local active element on each thread.
- Available state: `_current_elem`, `_current_elem_volume`, `_q_point`, `_qrule`, `_JxW`, `_coord`. You define and step `_qp` yourself.
- `BlockRestrictable` (block parameter), full coupling + materials.
- Threaded by default; you MUST implement `threadJoin()` to merge per-thread accumulators.

### **SideUserObject** (`framework/include/userobjects/SideUserObject.h:25`)
Purpose: boundary-side loop on a sideset (`BoundaryRestrictableRequired`).
- Adds `_normals`, `_current_side`, `_current_side_elem`, `_current_side_volume`, `_current_boundary_id`, plus `_face_infos` for FV / refinement awareness.
- Use for: flux integrals, surface averages, area, anything that only needs one side.

### **InternalSideUserObject** (`framework/include/userobjects/InternalSideUserObject.h:23`)
Purpose: internal-face loop (interior of one or more blocks).
- `BlockRestrictable` + `TwoMaterialPropertyInterface` + neighbor-coupleable: `_neighbor_elem`, `_current_neighbor_volume`, neighbor variable values.
- Avoids sideset orientation issues; iterates each interior face once.

### **InterfaceUserObject** / **InterfaceUserObjectBase** (`framework/include/userobjects/InterfaceUserObject.h:19`, `InterfaceUserObjectBase.h:23`)
Purpose: two-block interface loop. `BoundaryRestrictableRequired` + neighbor-coupleable + two-material-prop.
- `InterfaceUserObjectBase` provides the data members; `InterfaceUserObject` adds the FV-aware `_fi`, `_face_infos_processed`, and concrete `execute()`/`initialize()`.

### **DomainUserObject** (`framework/include/userobjects/DomainUserObject.h:42`)
Purpose: combined Element + Boundary + InternalSide + Interface in a single mesh pass.
- `execute()` is `final` and errors — override the five `executeOn*` hooks: `executeOnElement`, `executeOnBoundary`, `executeOnInternalSide`, `executeOnExternalSide`, `executeOnInterface`.
- Use `qPoints() / qRule() / JxW() / coord() / normals()` accessors — the underlying buffers are switched by `preExecuteOn*` between volume and face quadrature automatically.
- `interface_boundaries` parameter activates `executeOnInterface`. `getInterfaceFieldVar` registers off-block variables that should only be checked on the interface side.

### **MortarUserObject** (`framework/include/userobjects/MortarUserObject.h:21`)
Purpose: per-mortar-segment execution for surface coupling on the mortar mesh.
- Pure virtual `reinit()` runs at the start of each mortar segment; implement `execute()` for the segment work.
- `threadJoin()` is `final` and empty — mortar UOs are not threaded the same way; rely on the mortar assembly loop.
- Pulls in `MortarConsumerInterface`, `TwoMaterialPropertyInterface`, `NeighborCoupleable` for primary+secondary access.

### **NodalUserObject** (`framework/include/userobjects/NodalUserObject.h:24`)
Purpose: per-local-node aggregation.
- `BlockRestrictable` + `BoundaryRestrictable` (most often boundary-only).
- `_current_node`, `_qp` (always 0). `unique_node_execute` parameter prevents double-counting on nodes that touch multiple subdomains.

### **ThreadedGeneralUserObject** (`framework/include/userobjects/ThreadedGeneralUserObject.h:15`)
Purpose: rare — a `GeneralUserObject` with one copy per thread.
- `needThreadedCopy()` returns true `final`; `threadJoin()` overridable; `subdomainSetup` stubbed.
- Use only when the work the General UO does is itself parallelizable (e.g., dispatched threaded sub-loops).

### **ShapeUserObject<T>** (`framework/include/userobjects/ShapeUserObject.h:41`)
Purpose: template that gives access to `_phi`, `_grad_phi` so a UO can compute Jacobian-like contributions on `EXEC_NONLINEAR`.
- Pick `ShapeType::Element` (`_assembly.phi()`) or `ShapeType::Side` (`_assembly.phiFace()`).
- Implement `executeJacobian(jvar)`. Marked experimental — emits a warning at construction.
- Typically composed: `class MyUO : public ShapeUserObject<ElementUserObject>`.

### **Terminator** (`framework/include/userobjects/Terminator.h:38`)
Purpose: stop the solve when an FParser expression over postprocessors is true. Concrete `GeneralUserObject` — usually used directly from input, not subclassed.
- `FailMode` = HARD / SOFT / NONE; `MessageType` = INFO / WARNING / ERROR / NONE.

### **GhostingUserObject** (`framework/include/userobjects/GhostingUserObject.h:26`)
Purpose: visualizes effective ghosting per rank by walking all `RelationshipManager` ghosting functors. Specialized; almost always used as-is.

## Coupling & material properties

- **Coupling**: `coupledValue/coupledGradient/...` are valid in any mesh-loop variant (Element/Side/InternalSide/Interface/Domain/Nodal/Mortar). `GeneralUserObject` only has `ScalarCoupleable` — no field-variable qp values.
- **Materials**: `getMaterialProperty<T>` works in mesh-loop variants. `InternalSide`/`Interface` use `TwoMaterialPropertyInterface` (`getMaterialProperty` for elem side, `getNeighborMaterialProperty` for neighbor side). `Domain` uses `ThreeMaterialPropertyInterface`.
- **Required threadJoin reduction pattern**: cast and accumulate.

  ```cpp
  void MyUO::threadJoin(const UserObject & y)
  {
    const auto & other = static_cast<const MyUO &>(y);
    _accum += other._accum;
  }
  ```

- **finalize**: the place for MPI reductions (`gatherSum`, `gatherMax`, `_communicator.allgather`, etc.). MOOSE has already merged threads by then.
- **Spatial sampling for Transfers**: override `Real spatialValue(const Point & p) const`. The signature must match `UserObject.h:36` exactly (`const`, `Real` return). Any UO that does this is automatically a "SpatialUserObject" usable by `MultiAppUserObjectTransfer` and `SpatialUserObjectFunctor`. Concrete examples: `LayeredIntegralBase::spatialValue` (returns the bin integral at `p`), `NearestPointBase::spatialValue` (delegates to the nearest sub-UO).
- **`spatialPoints()`**: when the consumer wants the discrete sample locations rather than evaluating at arbitrary points, override this too.
- **`execute_on` flags** decide WHEN the UO runs: `INITIAL`, `TIMESTEP_BEGIN`, `LINEAR`, `NONLINEAR`, `TIMESTEP_END`, `FINAL`, `CUSTOM`. Default differs per base (most reduction UOs default to `TIMESTEP_END` so consumers see the converged value). Always state the contract in your class docs — a stale getter is almost always an `execute_on` mismatch.

## Registration & build

- `registerMooseObject("AppNameApp", MyUO);` in the `.C` file.
- File location: `framework/include/userobjects/` and `framework/src/userobjects/` (or `<module>/include/userobjects/`).
- AD-templating is uncommon for UOs (most are non-AD; they reduce values, not residuals). Don't reach for `ADReal` unless you actually need derivatives propagated through `gatherSum` etc.
- Add to `Makefile`/`unity_group` per the module's normal pattern; no special UO build step.

## Minimal scaffold

A small `ElementUserObject` that integrates a coupled variable and exposes the result. Demonstrates `initialize`/`execute`/`threadJoin`/`finalize` all four.

```cpp
// MyIntegral.h
#pragma once
#include "ElementUserObject.h"

class MyIntegral : public ElementUserObject
{
public:
  static InputParameters validParams();
  MyIntegral(const InputParameters & params);

  virtual void initialize() override;
  virtual void execute() override;
  virtual void threadJoin(const UserObject & y) override;
  virtual void finalize() override;

  Real getValue() const { return _integral; }

protected:
  const VariableValue & _u;
  Real _integral;
};
```

```cpp
// MyIntegral.C
#include "MyIntegral.h"
#include "libmesh/quadrature.h"

registerMooseObject("MyApp", MyIntegral);

InputParameters
MyIntegral::validParams()
{
  auto params = ElementUserObject::validParams();
  params.addRequiredCoupledVar("variable", "Field to integrate over the block");
  params.addClassDescription("Integrates the coupled variable over the block.");
  return params;
}

MyIntegral::MyIntegral(const InputParameters & params)
  : ElementUserObject(params), _u(coupledValue("variable")), _integral(0)
{
}

void MyIntegral::initialize() { _integral = 0; }

void MyIntegral::execute()
{
  for (unsigned int qp = 0; qp < _qrule->n_points(); ++qp)
    _integral += _JxW[qp] * _coord[qp] * _u[qp];
}

void MyIntegral::threadJoin(const UserObject & y)
{
  const auto & other = static_cast<const MyIntegral &>(y);
  _integral += other._integral;
}

void MyIntegral::finalize() { gatherSum(_integral); }
```

Reference implementation worth reading: `framework/include/userobjects/ElementIntegralUserObject.h:22` + its `.C` — same shape as above and is the ancestor of `ElementIntegralVariableUserObject`, `LayeredAverage`, etc.

## Common pitfalls

1. **Forgetting `threadJoin`**: per-thread state stays partial — only thread 0's accumulator survives, others are silently dropped. Pure virtual on `UserObject`, but easy to forget when refactoring.
2. **`spatialValue` not actually overriding the base**: signature must be `Real spatialValue(const Point & p) const` exactly. Drop the `const`, change the return type, or omit `override` and you silently shadow — `UserObject::spatialValue` then `mooseError`s at transfer time.
3. **Reading material properties from a `GeneralUserObject`**: there's no qp loop and no `_current_elem`. You can declare the dependency, but reading `_prop[_qp]` is undefined. Use a mesh-loop UO and feed its result into the General UO via `getUserObject<>` if you need both.
4. **`gatherSum` outside `finalize`**: MPI calls fired from `execute` deadlock on imbalanced meshes. Reduce only in `finalize`.
5. **Double-counting on internal sides**: `ElementUserObject::execute` runs once per element, so doing flux work by visiting `elem.side(s).neighbor()` from inside an element UO double-counts (each face is visited from both sides). Use `InternalSideUserObject` or `DomainUserObject::executeOnInternalSide`.
6. **Stale getter due to `execute_on` mismatch**: consumer (Transfer, AuxKernel) runs on a flag your UO doesn't. Most reduction UOs default to `TIMESTEP_END`; AuxKernels default to `LINEAR`/`TIMESTEP_END` depending on family. Add explicit `execute_on` to both ends and document it.
7. **`DomainUserObject::execute()` override**: it is `final` and errors. Override the `executeOn*` family instead.
8. **Mortar `threadJoin`**: it is `final` and empty. Don't try to accumulate by overriding it; do the reduction in `finalize` after the mortar loop.
9. **`NodalUserObject` double-execute on shared blocks**: a node on two subdomains is visited twice unless `unique_node_execute = true` (default). Toggle off only when the duplication is desired.
10. **`ShapeUserObject` enabled for AD/coupled vars unexpectedly**: every variable touched via `coupled()` while `compute_jacobians = true` joins `_jacobian_moose_variables`, triggering an `executeJacobian` pass per variable. Disable per-variable by gating the `coupled` call or setting the parameter false.

