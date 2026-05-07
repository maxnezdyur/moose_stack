# Authoring: XFEM module

The XFEM module implements the eXtended Finite Element Method using the **phantom-node Heaviside enrichment** approach: parent elements traversed by a cutting plane are replaced by overlapping partial child elements via the Element Fragment Algorithm (EFA), and partial-element integration weights are scaled (VOLFRAC / MOMENT_FITTING / DIRECT). True near-tip enrichment (extra DOFs) is also available but is a separate, smaller code path.

## When to use this (vs alternatives)

Pick a cutter by answering three orthogonal questions:

1. **How is the discontinuity defined?**
   - *Closed-form geometry* (line, rectangle, circle, ellipse): extend `GeometricCut2DUserObject` or `GeometricCut3DUserObject`.
   - *Explicit cutter mesh* (arbitrary crack surface, possibly grown over time): extend `MeshCut2DUserObjectBase` (2D crack), `MeshCutUserObjectBase` directly (3D crack — see `CrackMeshCut3DUserObject`), or `InterfaceMeshCutUserObjectBase` (moving material interface).
   - *Iso-contour of an aux variable* (level set): use `LevelSetCutUserObject` directly — no subclass usually needed.
2. **Crack or material interface?**
   - *Crack* (free surface, may grow, may need fracture integrals): pair the cutter with `CrackFrontDefinition` from solid_mechanics, optionally with `CrackGrowthReporterBase` (e.g. `ParisLaw`) for fatigue.
   - *Material interface* (bonded across a jump): use `XFEMCutSwitchingMaterial` to swap material props by side, optionally `XFEMSingleVariableConstraint` to enforce Nitsche/penalty jump conditions.
3. **Stationary or growing?**
   - *Stationary*: any closed-form cutter or a static cutter mesh works.
   - *Growing crack*: `MeshCut2DFractureUserObject` / `MeshCut2DFunctionUserObject` (2D), `CrackMeshCut3DUserObject` + `CrackGrowthReporterBase` (3D).
   - *Moving interface*: `InterfaceMeshCut2DUserObject` / `InterfaceMeshCut3DUserObject` driven by a `XFEMMovingInterfaceVelocityBase` user object.

If you only need traction-free crack faces and a closed-form path, the closed-form route is the shortest. Reach for mesh cutters when the geometry is non-analytic or when you need fracture-integral-driven growth. Reach for level set when the front is the zero contour of an existing field (e.g. coupled to a phase-field or driven by another physics module).

For non-XFEM alternatives:

- *Aligned interfaces* (mesh fits the discontinuity): use [contact-authoring.md] (mechanical jump) or standard `InterfaceKernel` — XFEM is overkill.
- *Element death / damage diffusion*: stay with [solid-mechanics-authoring.md] damage models; XFEM phantom-node is for sharp discontinuities, not smeared damage.

## Contract

### **XFEM** (`modules/xfem/include/base/XFEM.h:107`)

The XFEM controller (subclass of `XFEMInterface`). One per problem; obtained via `getParam<MooseSharedPointer<XFEM>>` or constructed by `XFEMAction`. Owns the EFA mesh, the list of `GeometricCutUserObject`s, the cut element map, and the quadrature rule. Hooks worth knowing: `getXFEMQRule()`, `getCutSubdomainID(gcuo, cut_elem, parent_elem)`, `getXFEMCutElemPairs(interface_id)`, `update()` (called from `XFEMAction`'s `MeshModifier`-like step). Most authors do not subclass `XFEM`; they register a `GeometricCutUserObject` and let the controller drive cutting.

### **GeometricCutUserObject** (`modules/xfem/include/userobjects/GeometricCutUserObject.h:102`)

Abstract base — every cutter inherits this. Subclass of `CrackFrontPointsProvider` so it can feed `CrackFrontDefinition`.

- Required overrides (pure virtual): `cutElementByGeometry(elem, cut_edges, cut_nodes)` (2D), `cutElementByGeometry(elem, cut_faces)` (3D), `cutFragmentByGeometry(frag_edges, cut_edges)` (2D), `cutFragmentByGeometry(frag_faces, cut_faces)` (3D). All four must be implemented even if the cutter is dimension-specific (the wrong-dimension ones return `false`).
- Override `getCutSubdomainID(const Node *)` (`:189`) — default `mooseError`s. Return values have no physical meaning but must be consistent across the run; conventionally 0 = negative side, 1 = positive side.
- Optional: `getCrackFrontPoints` / `getCrackPlaneNormals` (inherited from `CrackFrontPointsProvider`); `shouldHealMesh()` to merge children back at every step.
- The controller calls `initialize() / execute() / threadJoin() / finalize()` to gather `_marked_elems_2d` / `_marked_elems_3d` and serialize/deserialize across ranks (see `serialize`/`deserialize` at `:222`).

### **GeometricCut2DUserObject / GeometricCut3DUserObject** (`modules/xfem/include/userobjects/GeometricCut2DUserObject.h:16`, `GeometricCut3DUserObject.h:16`)

Dimension specializations. Both implement all four `cutElementByGeometry` / `cutFragmentByGeometry` virtuals on top of their own protected primitives:

- 2D: subclass stores `_cut_line_endpoints` (vector of `pair<Point,Point>`) plus `_cut_time_ranges`. `cutFraction(cut_num)` interpolates between start/end times for time-based propagation.
- 3D: subclass overrides `isInsideCutPlane(Point) = 0` and sets `_center` / `_normal`. `intersectWithEdge` / `isInsideEdge` / `getRelativePosition` are provided.

This is where most authors hook in for a new closed-form cutter.

### **LineSegmentCutSetUserObject / RectangleCutUserObject / CircleCutUserObject / EllipseCutUserObject** (`modules/xfem/include/userobjects/LineSegmentCutSetUserObject.h:16`, `RectangleCutUserObject.h:16`, `CircleCutUserObject.h:16`, `EllipseCutUserObject.h:16`)

Closed-form variants. All take a flat `cut_data` vector and parse it in the constructor. Useful templates — `CircleCutUserObject` is the canonical example for 3D (overrides `isInsideCutPlane` plus `getCrackFrontPoints`); `LineSegmentCutSetUserObject` for 2D (parses N segments of 6 reals each: x0,y0,x1,y1,t_start,t_end).

`ComboCutUserObject` (`ComboCutUserObject.h:14`) chains multiple cutters and disambiguates `CutSubdomainID` via a user-supplied dictionary; useful when two cracks intersect.

### **LevelSetCutUserObject** (`modules/xfem/include/userobjects/LevelSetCutUserObject.h:16`)

Reads the zero contour of a nodal aux variable (`level_set_var`). All four `cutElementByGeometry`/`cutFragmentByGeometry` virtuals are implemented; `getCutSubdomainID(node)` returns `_negative_id` if `phi(node) < 0` else `_positive_id`. Typically used directly without subclassing.

### **MeshCutUserObjectBase / MeshCut2DUserObjectBase** (`modules/xfem/include/userobjects/MeshCutUserObjectBase.h:18`, `MeshCut2DUserObjectBase.h:21`)

For cutters defined by an explicit cutter mesh (Exodus or generated).

- `MeshCutUserObjectBase` owns a `std::unique_ptr<MeshBase> _cutter_mesh` and exposes `getCutterMesh()` for output.
- `MeshCut2DUserObjectBase` adds: `MooseMesh & _mesh` (the structural mesh), a `MeshCut2DNucleationBase * _nucleate_uo`, a `CrackFrontDefinition * _crack_front_definition`, and ordering bookkeeping in `_original_and_current_front_node_ids`. It implements all four `cutElementByGeometry`/`cutFragmentByGeometry` virtuals against the cutter mesh.
- Required override on subclasses: `findActiveBoundaryGrowth()` (pure virtual at `MeshCut2DUserObjectBase.h:83`) — populates `_active_front_node_growth_vectors` based on whatever criterion (fracture integrals, stress, etc.). Helpers `growFront()` and `addNucleatedCracksToMesh()` then advance the cutter mesh.
- Concrete examples: `MeshCut2DFractureUserObject` (`MeshCut2DFractureUserObject.h:21`) drives growth from K_I/K_II via fracture-integral VPPs; `MeshCut2DFunctionUserObject` drives growth from a Function. `CrackMeshCut3DUserObject` (`CrackMeshCut3DUserObject.h:25`) is the 3D counterpart — it inherits `MeshCutUserObjectBase` directly (not a `MeshCut3DUserObjectBase` — none exists) and rolls its own boundary tracking.

### **InterfaceMeshCutUserObjectBase** (`modules/xfem/include/userobjects/InterfaceMeshCutUserObjectBase.h:29`)

For *moving material interfaces* (not cracks). Inherits `GeometricCutUserObject` directly.

- Holds a `std::shared_ptr<MeshBase> _cutter_mesh`, a `XFEMMovingInterfaceVelocityBase * _interface_velocity` UO, an optional `Function * _func`, plus negative/positive `CutSubdomainID`s.
- Required overrides: `calculateSignedDistance(Point) = 0`, `nodeNormal(node_id) = 0`, `calculateNormals() = 0` (pure virtuals at `:57`, `:60`, `:65`). Subclasses also implement the four `cutElementByGeometry`/`cutFragmentByGeometry` virtuals from `GeometricCutUserObject`.
- Concrete subclasses: `InterfaceMeshCut2DUserObject` (`InterfaceMeshCut2DUserObject.h:19`) and `InterfaceMeshCut3DUserObject`.

### **XFEMMovingInterfaceVelocityBase** (`modules/xfem/include/userobjects/XFEMMovingInterfaceVelocityBase.h:15`)

Companion to `InterfaceMeshCutUserObjectBase`. Subclass of `DiscreteElementUserObject`.

- Required override: `computeMovingInterfaceVelocity(node_id, normal) = 0`. Returns scalar velocity along normal.
- Holds a `NodeValueAtXFEMInterface * _value_at_interface_uo` so velocities can depend on a coupled-variable value at the interface.
- Concrete subclass: `XFEMPhaseTransitionMovingInterfaceVelocity`.

### **CrackGrowthReporterBase** + **ParisLaw** (`modules/xfem/include/reporters/CrackGrowthReporterBase.h:18`, `ParisLaw.h:18`)

`GeneralReporter` that consumes K_I (and optionally K_II) VPPs from `CrackFrontDefinition` and writes a `growth_increment` reporter consumed by `CrackMeshCut3DUserObject`.

- Required override: `computeGrowth(std::vector<int> & index)` (pure virtual at `:33`) — index is `-1` for inactive crack-front points, otherwise the position in the K_I VPP. Fill `_growth_increment` and the per-front coordinates `_x/_y/_z/_id` (declared in the base).
- `ParisLaw` implementation (`ParisLaw.C:54`) computes `effective_k = sqrt(K_I^2 + 2*K_II^2)`, finds `max_k`, sets `_dn = max_growth_increment / (C * max_k^m)`, and scales each point's increment by `(effective_k / max_k)^m`. Use it as the template for any new growth law (stress-corrosion, threshold, mixed-mode envelope, etc.).
- `StressCorrosionCrackingExponential` is a second concrete example.

### **XFEMSingleVariableConstraint** (`modules/xfem/include/constraints/XFEMSingleVariableConstraint.h:22`)

Subclass of `ElemElemConstraint`. Enforces a value or flux jump across the partial-element interface for one variable using either Nitsche stabilization or the penalty method.

- Required overrides: `computeQpResidual(DGResidualType)`, `computeQpJacobian(DGJacobianType)`, `reinitConstraintQuadrature(ElementPairInfo)`. The base provides `_interface_normal`, `_alpha`, `_jump`, `_jump_flux`, `_use_penalty`.
- The element pair list comes from `XFEMElementPairLocator`, registered automatically when an `XFEMCutElemPairs` entry exists for the interface ID.
- `XFEMEqualValueAtInterface` is a thin variant for the zero-jump case.

### **CrackTipEnrichmentStressDivergenceTensors** + **EnrichmentFunctionCalculation** + **CrackTipEnrichmentCutOffBC** (`modules/xfem/include/kernels/CrackTipEnrichmentStressDivergenceTensors.h:25`, `base/EnrichmentFunctionCalculation.h:17`, `bcs/CrackTipEnrichmentCutOffBC.h:19`)

True near-tip enrichment (the second sum in the original XFEM ansatz). Separate from phantom-node Heaviside enrichment.

- Kernel inherits both `ALEKernel` and `EnrichmentFunctionCalculation`. `validParams` requires `displacements`, enrichment displacement variables, and a `CrackFrontDefinition` UO. `computeQpResidual / computeQpJacobian / computeQpOffDiagJacobian` evaluate the residual using `crackTipEnrichementFunctionAtPoint(point, B)` and `crackTipEnrichementFunctionDerivativeAtPoint(point, dB)`.
- `EnrichmentFunctionCalculation` is a non-MooseObject helper holding the four near-tip basis functions and the local-to-global rotation. Reusable from BCs and IC objects.
- `CrackTipEnrichmentCutOffBC` is a `DirichletBC` that pins enrichment DOFs to zero outside `_cut_off_radius` of any crack tip. Apply it to a boundary that contains all nodes that *might* otherwise pick up enrichment.
- `ComputeCrackTipEnrichmentSmallStrain` (`materials/ComputeCrackTipEnrichmentSmallStrain.h`) is the matching strain calculator.
- All three are wired by `XFEMAction` when `use_crack_tip_enrichment = true` (see `XFEMAction.h:32` block of params).

## Coupling & material properties

XFEM-specific concepts beyond the base classes above:

- **`CutSubdomainID`** is a per-cutter side identifier (`unsigned int`, by convention 0 / 1) — it is **not** the libMesh `SubdomainID`. Each `GeometricCutUserObject` defines its own; `ComboCutUserObject` combines them via a user dictionary.
- **`XFEMCutSwitchingMaterial`** (`materials/XFEMCutSwitchingMaterial.h:23`, templated for `Real` / `RankTwoTensor` / `RankThreeTensor` / `RankFourTensor`, AD and non-AD): pulls `CutSubdomainID` for the current element from a `GeometricCutUserObject` and re-exposes the corresponding side's material property under a single name. Use this when downstream kernels/materials cannot themselves be subdomain-restricted.
- **`CutElementSubdomainModifier`** (`userobjects/CutElementSubdomainModifier.h:19`, subclass of `ElementSubdomainModifier`): projects `CutSubdomainID` from a `GeometricCutUserObject` onto MOOSE's `SubdomainID` so that ordinary subdomain-restricted objects (kernels, materials, BCs) can target one side. Required when the downstream object is not XFEM-aware.
- **`LevelSetBiMaterialBase`** + `LevelSetBiMaterialReal` / `LevelSetBiMaterialRankTwo` / `LevelSetBiMaterialRankFour` (`materials/`): legacy switching material driven by a level-set aux variable rather than a cutter's `CutSubdomainID`. Prefer `XFEMCutSwitchingMaterial` when you have a cutter UO.
- **`XFEMElementPairLocator`** (`geomsearch/XFEMElementPairLocator.h:15`): exposes the touching partial-element pairs for a given interface ID to constraints (`XFEMSingleVariableConstraint`) and Dirac kernels (`XFEMPressure`). One is created per geometric cut.
- **`XFEMPressure`** (`dirackernels/XFEMPressure.h:17`): Dirac kernel that applies a traction (or pressure) on the cut faces inside cut elements, integrated with the partial-element quadrature. Use this for crack-face pressure loading instead of trying to apply a `BC`.
- **`XFEMMaterialStateMarkerBase`** + `XFEMRankTwoTensorMarkerUserObject`: nucleation/state markers that mark elements for cutting based on a material state (e.g. principal-stress threshold). Feed nucleated cracks into the EFA, not into a separate cutter.
- **`NodeValueAtXFEMInterface`**: utility UO that samples a coupled variable at interface nodes; required by `XFEMMovingInterfaceVelocityBase`.

The `XFEM_QRULE` enum (`base/XFEM.h:37`) selects partial-element integration: `VOLFRAC` (default — scale standard weights by physical volume fraction; fast, less accurate), `MOMENT_FITTING` (least-squares per-point weights; slower, more accurate, restricted to certain element types), `DIRECT` (sub-triangulation with new quadrature points; most accurate but breaks stateful material props at QPs because integration points move). Set via `[XFEM] qrule = ... []`.

## Registration & build

- All XFEM objects use `registerMooseObject("XFEMApp", ClassName)` (see `LineSegmentCutSetUserObject.C:15`, `CircleCutUserObject.C:18`, `ParisLaw.C:15`).
- Actions use `registerMooseAction("XFEMApp", XFEMAction, "<task>")` for tasks `setup_xfem`, `add_aux_variable`, `add_aux_kernel`, `add_variable`, `add_kernel`, `add_bc` (see `actions/XFEMAction.C:32-42`).
- The `[XFEM]` block is wired by `XFEMAction` (`include/actions/XFEMAction.h:15`). Required parameter: `geometric_cut_userobjects`. Common knobs: `qrule` (volfrac / moment_fitting / direct), `output_cut_plane`, `use_crack_growth_increment`, `use_crack_tip_enrichment` (plus `crack_front_definition`, `displacements`, `enrichment_displacements`, `cut_off_boundary`, `cut_off_radius` when enrichment is on).
- Module flag in `modules.mk`: `XFEM := yes`.
- Header lives under `modules/xfem/include/<bucket>/`; source under `modules/xfem/src/<bucket>/`. Buckets: `actions`, `auxkernels`, `base`, `bcs`, `constraints`, `dirackernels`, `efa`, `geomsearch`, `kernels`, `materials`, `outputs`, `reporters`, `userobjects`.

## Minimal scaffold

A 2D closed-form cutter (the most common XFEM extension). Half-space cut by a single line `n · (x - x0) = 0`, time-independent, no growth. Subclasses `GeometricCut2DUserObject` so the four `cutElementByGeometry`/`cutFragmentByGeometry` virtuals come for free — you only fill `_cut_line_endpoints` and override `getCutSubdomainID(node)`.

```cpp
// include/userobjects/HalfPlaneCutUserObject.h
#pragma once
#include "GeometricCut2DUserObject.h"

class HalfPlaneCutUserObject : public GeometricCut2DUserObject
{
public:
  static InputParameters validParams();
  HalfPlaneCutUserObject(const InputParameters & parameters);

  virtual CutSubdomainID getCutSubdomainID(const Node * node) const override;

protected:
  const Point _origin;
  const RealVectorValue _normal;
};
```

```cpp
// src/userobjects/HalfPlaneCutUserObject.C
#include "HalfPlaneCutUserObject.h"

registerMooseObject("XFEMApp", HalfPlaneCutUserObject);

InputParameters
HalfPlaneCutUserObject::validParams()
{
  InputParameters params = GeometricCut2DUserObject::validParams();
  params.addRequiredParam<Point>("origin", "A point on the cutting line");
  params.addRequiredParam<RealVectorValue>("normal", "Outward normal of the half-plane (2D)");
  params.addClassDescription("Half-plane (single straight line) 2D cut for XFEM.");
  return params;
}

HalfPlaneCutUserObject::HalfPlaneCutUserObject(const InputParameters & parameters)
  : GeometricCut2DUserObject(parameters),
    _origin(getParam<Point>("origin")),
    _normal(getParam<RealVectorValue>("normal"))
{
  // GeometricCut2DUserObject expects a vector of (p1, p2) endpoints. For an
  // infinite line we synthesize two endpoints far enough to span any mesh.
  const Real big = 1.0e6;
  const RealVectorValue tangent(-_normal(1), _normal(0), 0.0);
  _cut_line_endpoints.emplace_back(_origin - big * tangent, _origin + big * tangent);
  _cut_time_ranges.emplace_back(std::numeric_limits<Real>::lowest(),
                                std::numeric_limits<Real>::max());
}

CutSubdomainID
HalfPlaneCutUserObject::getCutSubdomainID(const Node * node) const
{
  const RealVectorValue r(*node - _origin);
  return (r * _normal) >= 0.0 ? CutSubdomainID(1) : CutSubdomainID(0);
}
```

Wire in input:

```
[UserObjects]
  [hp_cut]
    type = HalfPlaneCutUserObject
    origin = '0.5 0.5 0'
    normal = '0 1 0'
  []
[]

[XFEM]
  geometric_cut_userobjects = 'hp_cut'
  qrule = volfrac
  output_cut_plane = true
[]
```

For a 3D variant, swap the parent to `GeometricCut3DUserObject` and override `isInsideCutPlane(Point) const = 0` instead of populating `_cut_line_endpoints` (see `CircleCutUserObject.C` as the canonical template).

## Common pitfalls

1. **Geometric cut vs EFA mesh modification.** A `GeometricCutUserObject` only *decorates* edges/faces with cut info; the actual mesh modification is performed by `XFEM::cutMeshWithEFA` driven from `XFEMAction`. Returning `true` from `cutElementByGeometry` does not split the mesh — pushing entries into `_marked_elems_2d`/`_marked_elems_3d` does.
2. **Cutter UO vs cutter mesh.** `MeshCutUserObjectBase` owns a `MeshBase` cutter mesh; this mesh is *not* the simulation mesh and is not visible to the rest of MOOSE except via `getCutterMesh()`. Don't confuse it with `MooseMesh & _mesh` (the structural mesh) that `MeshCut2DUserObjectBase` also holds.
3. **`CutSubdomainID` is not `SubdomainID`.** Partial children share their parent's libMesh `SubdomainID`. Subdomain-restricted kernels/materials/BCs see them as the same block. Either use `CutElementSubdomainModifier` to project `CutSubdomainID` onto `SubdomainID`, or use `XFEMCutSwitchingMaterial` to deliver the right side's properties under a common name.
4. **Wrong `xfem_qrule`.** `VOLFRAC` is the default and is fine for coarse studies. `MOMENT_FITTING` is more accurate and only marginally slower but is restricted to a smaller set of element types. `DIRECT` regenerates quadrature points and *invalidates* stateful material data at QPs — only safe for stateless materials. Picking `DIRECT` with a plasticity/creep model produces silently-wrong results.
5. **`CrackFrontDefinition` is not an XFEM object.** It lives in solid_mechanics (see [solid-mechanics-authoring.md]). XFEM mesh cutters supply points to it via `getCrackFrontPoints` / `getCrackPlaneNormals` (the `CrackFrontPointsProvider` interface), but they don't own it. If you wire enrichment or `ParisLaw`, you must add a `[VectorPostprocessors]` and a `CrackFrontDefinition` block alongside the cutter.
6. **Near-tip enrichment is separate from phantom-node enrichment.** They can be combined but typically aren't. Phantom nodes are automatic for any cutter; near-tip enrichment requires `[XFEM] use_crack_tip_enrichment = true`, dedicated `enrichment_displacements` variables, the `CrackTipEnrichmentStressDivergenceTensors` kernel, the `ComputeCrackTipEnrichmentSmallStrain` material, and a `CrackTipEnrichmentCutOffBC` to pin far-field DOFs to zero. Forgetting the cut-off BC produces a large, ill-conditioned system because every node in the mesh ends up enriched.

