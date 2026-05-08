# Authoring inputs: XFEM module

Reach for this guide to add a sharp discontinuity (crack or material interface) to a `.i` file using the **eXtended Finite Element Method**. XFEM lives in `modules/xfem/` and is driven by a single top-level `[XFEM]` action plus one or more *cutter* user objects. The cutter decorates which edges/faces to split; the **Element Fragment Algorithm (EFA)** duplicates parent elements into overlapping phantom-node children and rescales their integration weights via the chosen `qrule`. If a needed cutter type does not exist yet (i.e. you're writing C++), see `../moose/xfem-authoring.md`.

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. Each entry cites the **source header** (`<file>:<line of class>`) and one **canonical example .i** (`<file>:<line of the sub-block>`).

## When to use this (vs alternatives)

Decide between four routes by answering: *what defines the discontinuity*, *crack or interface*, *static or growing*?

1. **Closed-form static cut** — `LineSegmentCutUserObject` (2D), `RectangleCutUserObject` / `CircleCutUserObject` / `EllipseCutUserObject` (3D). Fastest, no extra mesh files. Stationary edge cracks, half-space cuts, parametric studies.
2. **Cutter-mesh driven (possibly growing) crack** — `MeshCut2DFractureUserObject` / `MeshCut2DFunctionUserObject` (2D), `CrackMeshCut3DUserObject` + `ParisLaw` (3D). Crack geometry non-analytic *or* fracture-integral- / fatigue-driven growth. Requires a separate cutter mesh (Exodus or `PolyLineMeshGenerator`).
3. **Iso-contour of an aux variable** — `LevelSetCutUserObject` cuts on `phi = 0`. Use when the front comes from another physics (phase-field, level-set evolution).
4. **Moving material interface** (bonded jump, no free surface) — `InterfaceMeshCut2DUserObject` / `InterfaceMeshCut3DUserObject` + `XFEMMovingInterfaceVelocityBase`. Pair with `XFEMSingleVariableConstraint` (Nitsche/penalty jump) and `XFEMCutSwitchingMaterialReal` (per-side properties).

If the discontinuity *aligns with mesh boundaries* use `[InterfaceKernels]` ([kernels.md](./kernels.md)) or `Physics/Contact`; XFEM is overkill. For *smeared damage* stay with phase-field / damage models — XFEM phantom nodes are for sharp jumps only. For J / K integrals, pair the cutter with a `[DomainIntegral]` block (see [solid-mechanics.md](./solid-mechanics.md)); every `GeometricCutUserObject` is a `CrackFrontPointsProvider` and feeds crack-front points to `CrackFrontDefinition` automatically.

## Catalog

### `[XFEM]` — top-level action block

`XFEMAction` (`modules/xfem/include/actions/XFEMAction.h:15`) instantiates the XFEM controller, the EFA mesh-modifier hook, and (optionally) cut-plane aux variables and crack-tip enrichment kernels/BCs.

##### `geometric_cut_userobjects`
- List of cutter UO names. Required in practice — without it nothing gets cut. Multiple cutters compose; disambiguate intersections with `ComboCutUserObject`.

##### `qrule`
- Source: `modules/xfem/include/base/XFEM.h:107` (enum at `XFEM.h:37`).
- Example: `modules/xfem/test/tests/solid_mechanics_basic/edge_crack_3d.i:8`.
- Partial-element integration: `volfrac` (default — scale weights, fast, less accurate), `moment_fitting` (LSQ refit, slower, restricted element types), `direct` (sub-triangulation; **invalidates stateful material props** because QPs move).

##### `output_cut_plane`
- Example: `modules/xfem/test/tests/solid_mechanics_basic/edge_crack_3d.i:10`.
- When `true`, the action auto-adds 13 `MONOMIAL CONSTANT` aux variables (`xfem_volfrac`, `xfem_cut_origin_{x,y,z}`, `xfem_cut_normal_{x,y,z}`, plus `xfem_cut2_*`) and the `XFEMVolFracAux` / `XFEMCutPlaneAux` aux kernels that populate them — see `modules/xfem/src/actions/XFEMAction.C:204-285`. Do not declare these manually.

##### `use_crack_growth_increment` / `crack_growth_increment`
- Example: `modules/xfem/test/tests/solid_mechanics_basic/crack_propagation_2d.i:9-10`. Fixed `da` per XFEM update; pair with a marker UO that decides *when*.

##### `use_crack_tip_enrichment` (+ `crack_front_definition`, `displacements`, `enrichment_displacements`, `cut_off_boundary`, `cut_off_radius`)
- Near-tip enrichment (extra DOFs, separate from phantom-node Heaviside enrichment). All four extras required; missing `cut_off_boundary` enriches every node and gives an ill-conditioned system. Most workflows do **not** need this.

##### `debug_output_level` / `min_weight_multiplier`
- `debug_output_level` 0–3 (default 1). `min_weight_multiplier` (default 1e-3) floors partial-element weight scaling to avoid singular Jacobians on slivered children.

### `[UserObjects]` — XFEM cutters

Every cutter inherits `GeometricCutUserObject` (`modules/xfem/include/userobjects/GeometricCutUserObject.h:102`), which is itself a `CrackFrontPointsProvider`.

#### Closed-form 2D cuts

##### `LineSegmentCutUserObject`
- Source: `modules/xfem/include/userobjects/LineSegmentCutUserObject.h:16`
- Example: `modules/xfem/test/tests/diffusion_xfem/diffusion.i:24` (sub-block `[line_seg_cut_uo]`).
- Single line `cut_data = 'x0 y0 x1 y1'` (4 reals). Required: `cut_data`. Useful: `time_start_cut`, `time_end_cut` (default 0; interpolate cut activation in time).

##### `LineSegmentCutSetUserObject`
- Source: `modules/xfem/include/userobjects/LineSegmentCutSetUserObject.h:16`
- Example: `modules/xfem/test/tests/init_solution_propagation/init_solution_propagation.i:36`.
- N-segment 2D polyline; `cut_data` is `6*N` reals (`x0 y0 x1 y1 t_start t_end` per segment). Branched/notched cracks, prescribed propagation paths.

#### Closed-form 3D cuts

##### `RectangleCutUserObject`
- Source: `modules/xfem/include/userobjects/RectangleCutUserObject.h:16`
- Example: `modules/xfem/test/tests/solid_mechanics_basic/edge_crack_3d.i:29` (sub-block `[square_cut_uo]`).
- Planar rectangle from 4 vertices; `cut_data` = 12 reals (ordered).

##### `CircleCutUserObject`
- Source: `modules/xfem/include/userobjects/CircleCutUserObject.h:16`
- Example: `modules/xfem/test/tests/crack_tip_enrichment/penny_crack_3d.i:17`.
- Planar disk; `cut_data = 'cx cy cz r1x r1y r1z r2x r2y r2z'` (center + two radius vectors).

##### `EllipseCutUserObject`
- Source: `modules/xfem/include/userobjects/EllipseCutUserObject.h:16`
- Example: `modules/xfem/test/tests/solid_mechanics_basic/elliptical_crack.i` (search `type = EllipseCutUserObject`).
- Planar ellipse; `cut_data` packs center + two semi-axis vectors.

##### `ComboCutUserObject`
- Source: `modules/xfem/include/userobjects/ComboCutUserObject.h:14`
- Example: `modules/xfem/test/tests/switching_material/two_cuts_stationary.i:25` (sub-block `[combo]`).
- Combines existing cutters; supplies a unified `CutSubdomainID` via `cut_subdomain_combinations` + `cut_subdomains`. Required when cracks intersect or for >2-side bimaterials.

#### Level-set cut

##### `LevelSetCutUserObject`
- Source: `modules/xfem/include/userobjects/LevelSetCutUserObject.h:16`
- Example: `modules/xfem/test/tests/diffusion_xfem/levelsetcut2d.i:27` (sub-block `[level_set_cut_uo]`).
- Cuts on the zero contour of a nodal aux variable. Required: `level_set_var`. Useful: `negative_id` (default 0), `positive_id` (default 1), `execute_on = NONE` to freeze the cut inside the nonlinear solve.

#### Cutter-mesh-driven cuts (and growth)

##### `MeshCut2DFractureUserObject`
- Source: `modules/xfem/include/userobjects/MeshCut2DFractureUserObject.h:21`
- Example: `modules/xfem/test/tests/mesh_cut_2D_fracture/double_cantilever_crack_2d.i:84` (sub-block `[cut_mesh]`).
- 2D crack from a 1D cutter mesh; grows by `growth_increment` when a fracture-integral threshold is met. Required: `mesh_generator_name` (or `mesh_file`), `growth_increment`, plus a growth criterion (`k_critical` + `ki_vectorpostprocessor`/`kii_vectorpostprocessor`, *or* `stress_threshold` + `stress_vectorpostprocessor`).

##### `MeshCut2DFunctionUserObject`
- Source: `modules/xfem/include/userobjects/MeshCut2DFunctionUserObject.h:23`
- Example: `modules/xfem/test/tests/mesh_cut_2D_fracture/crack_front_stress_function_growth.i:69`.
- 2D crack growth driven by user `Function`s on the front nodes — prescribed propagation paths.

##### `CrackMeshCut3DUserObject`
- Source: `modules/xfem/include/userobjects/CrackMeshCut3DUserObject.h:25`
- Example: `modules/xfem/test/tests/solid_mechanics_basic/edge_crack_3d_fatigue.i:14`.
- 3D crack as a triangular surface mesh. `growth_dir_method = MAX_HOOP_STRESS|FUNCTION`, `growth_increment_method = REPORTER|FUNCTION`. Reporter is usually `ParisLaw` or `StressCorrosionCrackingExponential`.

##### `MeshCut2DRankTwoTensorNucleation`
- Source: `modules/xfem/include/userobjects/MeshCut2DRankTwoTensorNucleation.h:15`
- Example: `modules/xfem/test/tests/nucleation_uo/nucleate_AllEdgeCracks.i:48`.
- Marks elements for new-crack nucleation when a `RankTwoTensor` scalar (e.g. max principal stress) crosses a threshold; feeds nucleated cracks to a `MeshCut2D*UserObject`.

#### Moving material interfaces

##### `InterfaceMeshCut2DUserObject` / `InterfaceMeshCut3DUserObject`
- Source: `modules/xfem/include/userobjects/InterfaceMeshCut2DUserObject.h:19`, `InterfaceMeshCut3DUserObject.h:20` (base at `InterfaceMeshCutUserObjectBase.h:29`).
- Example: `modules/xfem/test/tests/moving_interface/cut_mesh_2d.i` (`type = InterfaceMeshCut2DUserObject`).
- Cutter mesh advances along node normals at a velocity supplied by an `interface_velocity` UO. Required: `mesh_generator_name`, `interface_velocity`, `negative_id`, `positive_id`.

##### `XFEMPhaseTransitionMovingInterfaceVelocity` + `NodeValueAtXFEMInterface`
- Source: `modules/xfem/include/userobjects/XFEMPhaseTransitionMovingInterfaceVelocity.h:14`, `NodeValueAtXFEMInterface.h:19`.
- Example: `modules/xfem/test/tests/moving_interface/phase_transition_2d.i:27` and `:34`.
- Concrete velocity UO that reads a coupled variable's value at interface nodes. `NodeValueAtXFEMInterface` is the value-sampler required by every `XFEMMovingInterfaceVelocityBase` subclass.

#### Markers and projection

##### `XFEMRankTwoTensorMarkerUserObject`
- Source: `modules/xfem/include/userobjects/XFEMRankTwoTensorMarkerUserObject.h:15`
- Example: `modules/xfem/test/tests/solid_mechanics_basic/crack_propagation_2d.i:32` (sub-block `[xfem_marker_uo]`).
- Decides *which* element gets cut next via a `RankTwoTensor` scalar (e.g. `MaxPrincipal` of `stress`) crossing a `threshold`. Pair with a static `LineSegmentCutUserObject` to grow one element per step. Useful: `average` (default true; false uses max QP).

##### `CutElementSubdomainModifier`
- Source: `modules/xfem/include/userobjects/CutElementSubdomainModifier.h:19`
- Example: `modules/xfem/test/tests/moving_interface/moving_bimaterial_finite_strain_esm.i:21`.
- Projects `CutSubdomainID` onto libMesh `SubdomainID` so ordinary subdomain-restricted objects see two distinct sides. Required when downstream is not XFEM-aware.

### `[Reporters]` — crack growth laws (3D)

##### `ParisLaw`
- Source: `modules/xfem/include/reporters/ParisLaw.h:18`
- Example: `modules/xfem/test/tests/solid_mechanics_basic/edge_crack_3d_fatigue.i:1` (sub-block `[fatigue]`).
- Fatigue growth law `da/dN = C * (Δk)^m`. Computes `effective_k = sqrt(K_I^2 + 2*K_II^2)`, scales the increment by the current max, writes `growth_increment` consumed by `CrackMeshCut3DUserObject`. Required: `growth_increment_name`, `cycles_to_max_growth_increment_name`, `crackMeshCut3DUserObject_name`, `max_growth_increment`, `paris_law_c`, `paris_law_m`.

##### `StressCorrosionCrackingExponential`
- Source: `modules/xfem/include/reporters/StressCorrosionCrackingExponential.h:19`
- Example: `modules/xfem/test/tests/solid_mechanics_basic/edge_crack_3d_scc_crit.i:6`.
- SCC growth law (exponential in K). Template for any new `CrackGrowthReporterBase` subclass.

### `[Constraints]` — XFEM jump enforcement

##### `XFEMSingleVariableConstraint`
- Source: `modules/xfem/include/constraints/XFEMSingleVariableConstraint.h:22`
- Example: `modules/xfem/test/tests/single_var_constraint_2d/stationary_jump.i:43` (sub-block `[xfem_constraint]`).
- Imposes a value jump and/or flux jump across the cut for one variable via **Nitsche** (default) or **penalty** (`use_penalty = true`). Acts on the `XFEMElementPairLocator` pairs auto-registered by the cutter. Required: `variable`, `geometric_cut_userobject`. Useful: `jump` (Function, default 0), `jump_flux` (Function, default 0), `alpha` (default 100), `use_penalty`.

##### `XFEMEqualValueAtInterface`
- Source: `modules/xfem/include/constraints/XFEMEqualValueAtInterface.h:17`
- Example: `modules/xfem/test/tests/moving_interface/phase_transition_2d.i:70`.
- Penalty-only zero-jump variant; pins both sides to `value` (default 0).

### `[DiracKernels]` — crack-face loading

##### `XFEMPressure`
- Source: `modules/xfem/include/dirackernels/XFEMPressure.h:17`
- Example: `modules/xfem/test/tests/pressure_bc/edge_2d_pressure.i:77`.
- Applies a traction / pressure on the cut faces *inside cut elements* via partial-element quadrature. Use this — not a `BC` — for crack-face pressure (the cut face has no sideset). Required: `variable`, `component`, one of `function` / `value`.

### `[AuxKernels]` — XFEM-specific outputs

##### `XFEMVolFracAux` / `XFEMCutPlaneAux`
- Source: `modules/xfem/include/auxkernels/XFEMVolFracAux.h:19`, `XFEMCutPlaneAux.h:18`.
- Auto-added by `[XFEM] output_cut_plane = true` (see `modules/xfem/src/actions/XFEMAction.C:222-285`). `XFEMVolFracAux` writes per-element volume fraction; `XFEMCutPlaneAux` writes one component (`origin_x|y|z`, `normal_x|y|z`) of cut plane id 0 or 1 per aux variable. Do not declare manually.

##### `MeshCutLevelSetAux`
- Source: `modules/xfem/include/auxkernels/MeshCutLevelSetAux.h:19`
- Example: `modules/xfem/test/tests/moving_interface/cut_mesh_2d.i:91` (sub-block `[ls]`).
- Signed-distance level-set field from an `InterfaceMeshCutUserObjectBase` cutter mesh. Required: `variable`, `mesh_cut_user_object`.

##### `CutSubdomainIDAux`
- Source: `modules/xfem/include/auxkernels/CutSubdomainIDAux.h:17`
- Example: `modules/xfem/test/tests/switching_material/two_cuts_stationary.i:73` (sub-block `[cut1_id]`).
- Writes a cutter's `CutSubdomainID` per element. Required: `variable`, `cut`.

##### `XFEMMarkerAux`
- Source: `modules/xfem/include/auxkernels/XFEMMarkerAux.h:16`
- Writes 1 on cut elements, 0 elsewhere. Diagnostic / drives `[Markers]` h-adaptivity. Required: `variable`.

### Solid-mechanics integration (cross-reference [solid-mechanics.md](./solid-mechanics.md))

Fracture-mechanics integrals are *not* XFEM objects; they live in `solid_mechanics`. XFEM cutters satisfy the `CrackFrontPointsProvider` interface so `CrackFrontDefinition` reads crack-front points without a hand-built sideset.

##### `[DomainIntegral]`
- Source: `modules/solid_mechanics/include/actions/DomainIntegralAction.h:22`
- Example: `modules/xfem/test/tests/solid_mechanics_basic/edge_crack_3d.i:45`.
- Action block that creates `CrackFrontDefinition` and the J-integral / interaction-integral VPPs for K_I, K_II, K_III. Connect via `crack_front_points_provider = <cutter_name>` (mesh cutters) or `crack_front_points = '...'` (closed-form). Required: `integrals`, `radius_inner`, `radius_outer`, `poissons_ratio`, `youngs_modulus`, plus one of `crack_front_points` / `crack_front_points_provider` / `boundary`.

##### `CrackFrontDefinition`
- Source: `modules/solid_mechanics/include/userobjects/CrackFrontDefinition.h:29`.
- Created internally by `[DomainIntegral]`. `MeshCut2DFractureUserObject` and `CrackMeshCut3DUserObject` keep a pointer and read K_I/K_II VPPs back for growth.

## Cross-cutting concerns

### `[XFEM]` action wiring
Cutter UOs must be **named** in `geometric_cut_userobjects`; placing them in `[UserObjects]` alone is not enough. The action runs across multiple tasks (`setup_xfem`, `add_aux_variable`, `add_aux_kernel`, `add_kernel`, `add_bc`) so cut-plane outputs and enrichment kernels appear automatically.

### Cutter `execute_on` ordering
Cutter UOs run on `INITIAL`, `TIMESTEP_BEGIN`, and (for level-set / moving interfaces) `XFEM_MARK`. The mesh-cut step happens **between timesteps**, before residual evaluation, so cutters never see mid-Newton state. If a cutter consumes a coupled variable that solves on the cut mesh, set `execute_on = NONE` (e.g. `two_cuts_stationary.i:16`) and let `[XFEM]`'s update loop drive it. `max_xfem_update = N` on `[Executioner]` caps cut/solve iterations per step (`=1` for stationary cuts; unlimited can re-cut indefinitely with growth).

### Pairing with `CrackFrontDefinition`
For J / K integrals add a `[DomainIntegral]` block alongside the cutter. Two patterns:
- *Closed-form cutter*: typically supply explicit `crack_front_points = '...'` (avoids ordering ambiguity, even though `getCrackFrontPoints` is implemented).
- *Mesh cutter* (`MeshCut2DFractureUserObject`, `CrackMeshCut3DUserObject`): use `crack_front_points_provider = <cutter_name>` — required for growth since the front moves.

K_I / K_II VPPs created by `[DomainIntegral]` (named `II_KI_<id>` / `II_KII_<id>`) feed back to `MeshCut2D*UserObject` via `ki_vectorpostprocessor` / `kii_vectorpostprocessor` and to `ParisLaw` via `crackMeshCut3DUserObject_name`, closing the K → growth → cut loop.

### `output_cut_plane`
Set `output_cut_plane = true` for visualization. To render the cut surface in ParaView, apply the *Slice* filter to `xfem_cut_origin_*` / `xfem_cut_normal_*` and select `xfem_volfrac < 1`.

### AD limitations
Most XFEM-aware objects are **non-AD**: `XFEMSingleVariableConstraint`, `XFEMEqualValueAtInterface`, `XFEMPressure`, `CrackTipEnrichmentStressDivergenceTensors`. The residual depends on `ElementPairInfo` reconstructed each cut step, which the AD chain cannot follow through phantom-node duplication. `XFEMCutSwitchingMaterialTempl` (`modules/xfem/include/materials/XFEMCutSwitchingMaterial.h:23`) does have AD specializations. Practical rule: pair `AD*` solid-mechanics kernels with `ADXFEMCutSwitchingMaterialReal`; accept non-AD constraints — the missing off-diagonals rarely block Newton.

### Refinement and `CutSubdomainID` vs `SubdomainID`
For J-integrals ensure 4–8 elements between `radius_inner` and `radius_outer`. Drive h-adaptivity from `XFEMMarkerAux` (cut-element mask) thresholded in `[Markers]`. **`CutSubdomainID` ≠ `SubdomainID`**: phantom-node children inherit their parent's libMesh `SubdomainID`, so subdomain-restricted objects see one block. Fix with `XFEMCutSwitchingMaterial` (re-expose side-A / side-B props under one name) when downstream reads a property, or with `CutElementSubdomainModifier` (project `CutSubdomainID` onto a fresh `SubdomainID`) when downstream is not XFEM-aware.

## Minimal scaffold

2D edge crack on a unit square cut by a single line segment. Standard small-strain solid mechanics, traction-free crack faces, displacement loading on top, fixed bottom. Static cut at t=0, no growth. `output_cut_plane = true` so ParaView can render the cut.

```hit
[GlobalParams]
  displacements = 'disp_x disp_y'
[]

[XFEM]
  geometric_cut_userobjects = 'line_seg_cut_uo'
  qrule = volfrac
  output_cut_plane = true
[]

[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 2
    nx = 11
    ny = 11
    xmin = 0
    xmax = 1
    ymin = 0
    ymax = 1
    elem_type = QUAD4
  []
[]

[UserObjects]
  [line_seg_cut_uo]
    type = LineSegmentCutUserObject
    cut_data = '0.0 0.5 0.4 0.5'   # crack from left edge to x=0.4, y=0.5
    time_start_cut = 0.0
    time_end_cut = 0.0
  []
[]

[Physics/SolidMechanics/QuasiStatic]
  [all]
    strain = SMALL
    planar_formulation = plane_strain
    add_variables = true
    generate_output = 'stress_xx stress_yy vonmises_stress'
  []
[]

[Functions]
  [pull]
    type = PiecewiseLinear
    x = '0  1'
    y = '0  0.001'
  []
[]

[BCs]
  [bottom_x]
    type = DirichletBC
    variable = disp_x
    boundary = bottom
    value = 0
  []
  [bottom_y]
    type = DirichletBC
    variable = disp_y
    boundary = bottom
    value = 0
  []
  [top_y]
    type = FunctionDirichletBC
    variable = disp_y
    boundary = top
    function = pull
  []
[]

[Materials]
  [elasticity_tensor]
    type = ComputeIsotropicElasticityTensor
    youngs_modulus = 1e6
    poissons_ratio = 0.3
  []
  [stress]
    type = ComputeLinearElasticStress
  []
[]

[Executioner]
  type = Transient
  solve_type = PJFNK
  petsc_options_iname = '-pc_type -pc_hypre_type'
  petsc_options_value = 'hypre boomeramg'
  l_tol = 1e-3
  nl_rel_tol = 1e-10
  nl_abs_tol = 1e-10
  start_time = 0.0
  end_time = 1.0
  dt = 1.0
  max_xfem_update = 1
[]

[Outputs]
  exodus = true
[]
```

To extend this into a *propagating* crack: keep the same `LineSegmentCutUserObject` (initial flaw), add an `XFEMRankTwoTensorMarkerUserObject` to flag elements ahead of the tip, set `[XFEM] use_crack_growth_increment = true` and `crack_growth_increment = 0.1` (see `modules/xfem/test/tests/solid_mechanics_basic/crack_propagation_2d.i`). To extend into a *fracture-mechanics-driven* growth: replace the line cutter with a `MeshCut2DFractureUserObject` and add a `[DomainIntegral]` block that reads `crack_front_points_provider = cut_mesh` (see `modules/xfem/test/tests/mesh_cut_2D_fracture/double_cantilever_crack_2d.i`).
