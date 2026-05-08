# Authoring inputs: Contact module

Reach for this guide when you need to add mechanical contact (no-penetration, friction, glue) or cohesive-zone (CZM) behavior between two surfaces in a `.i` file. Almost everything funnels through the **`[Contact]` action** — it expands into the right `[Variables]` + `[UserObjects]` + `[Constraints]` + `[AuxKernels]` for whatever `model` × `formulation` combination you pick. Hand-rolled `[Constraints]` blocks are reserved for advanced/diagnostic cases. CZM is its own action under `[Physics/SolidMechanics/CohesiveZone]` plus a `[Materials]` traction-separation law.

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. Each entry cites the **source header** (`<file>:<line of class>`) and one **canonical example .i** (`<file>:<line of the sub-block>`). Cross-reference: contact pairs almost always with a `[Physics/SolidMechanics]` setup — see [solid-mechanics.md](./solid-mechanics.md). For C++ extension work (new constraints, new mortar UOs, new CZMs) see `../moose/contact-authoring.md`.

## When to use this (vs alternatives)

Decide on **discretization**, then **enforcement**, then **friction model**.

1. **`[Contact]` action vs hand-rolling `[Constraints]`.** Default to the action: it builds the lower-dimensional mortar mesh, wires the right user objects (`LMWeightedGapUserObject` / `PenaltyWeightedGapUserObject`), declares the LM nonlinear variable, and emits one constraint per displacement component. Hand-roll `[Constraints]` only if you need something the action cannot produce (custom UO, custom auxvar coupling, debugging). Never mix the two: instantiating `MechanicalContactConstraint` or `ComputeWeightedGapLMMechanicalContact` while a `[Contact]` block already enforces the same pair double-counts the contact force.
2. **Mortar vs node-face vs penalty.**
   - **Mortar** (`formulation = mortar` or `mortar_penalty`): variationally consistent surface integral on a lower-dimensional segment mesh. Required for finite-deformation, large-sliding, frictional, or curved-on-curved contact. Smoother convergence; only formulation supported with AD throughout. Needs a single primary/secondary pair (`MORTAR` errors on multi-pair).
   - **Node-face** (`formulation = kinematic | penalty | augmented_lagrange | tangential_penalty | ranfs`): legacy node-projection path; fast, robust on planar small-sliding geometry, supports multi-pair. `kinematic` solves to machine precision via the secondary residual; `penalty` is a soft spring; `augmented_lagrange` does Uzawa on top of penalty.
   - **Penalty mortar** (`formulation = mortar_penalty`): synthesizes contact pressure from gap × penalty — no Lagrange-multiplier nonlinear variable. Cheaper; good when you don't need exact non-penetration.
3. **Tied (glued) vs frictionless vs Coulomb.** `model = frictionless` allows separation but no penetration; `model = glued` (the C++ enum is `GLUED`; sometimes called "tied") sticks the surfaces together regardless of normal sign — use for bonded joints, weld lines, mesh-tying across non-conforming subdomains; `model = coulomb` adds tangential friction with `friction_coefficient`. The action errors if you set `tangential_penalty` without `coulomb`.
4. **CZM vs contact.** CZM (`[Physics/SolidMechanics/CohesiveZone]` + a traction-separation `[Materials]` law) models *cohesive interfaces* — the surfaces stay connected and carry traction even in tension, with damage/softening. Use for delamination, bonded interfaces with fracture, grain-boundary models. CZM is **not** for bodies coming into and out of contact — that's what `[Contact]` is for. CZM requires the mesh to be split with `BreakMeshByBlockGenerator` so the two subdomains share an interior sideset.
5. **Explicit dynamics** uses a separate stack (`ExplicitDynamicsContactConstraint`, `ExplicitDynamicsContactAction`). Don't mix with the implicit objects below.
6. **Thermal contact** (gap conductance) lives in `heat_transfer`, not here — see `ThermalContactAction` / `MortarGapHeatTransferAction`.

## Catalog

### `[Contact]` — the action (use this 90% of the time)

The `[Contact/<name>]` block is registered at `modules/contact/src/actions/ContactAction.C:223` and expands into the full set of objects needed for one contact pair. Repeat the sub-block for each pair (only allowed for `kinematic`/`penalty`/`augmented_lagrange`/`tangential_penalty`/`ranfs`; `mortar` requires single-pair).

##### `[Contact/<name>]`
- Source: `modules/contact/include/actions/ContactAction.h:31`
- Examples by formulation:
  - kinematic (node-face): `modules/contact/test/tests/simple_contact/simple_contact_test.i:24` (sub-block `[dummy_name]`)
  - penalty (node-face): `modules/contact/test/tests/simple_contact/simple_contact_test2.i:18`
  - mortar (LM, frictionless or coulomb): `modules/contact/test/tests/bouncing-block-contact/variational-frictional-action.i:76`
  - mortar_penalty (no LM nonlinear var): `modules/contact/test/tests/bouncing-block-contact/frictionless-penalty-weighted-gap-action.i:52`
  - mortar dynamics + Coulomb: `modules/contact/test/tests/mortar_dynamics/block-dynamics-friction-action.i:149`
  - glued/tied: `modules/contact/test/tests/glued/glued_contact_mechanical_constraint_test.i:41`
- Required: `primary` (sideset name/id), `secondary` (sideset name/id), `model` (`frictionless | glued | coulomb`), `formulation` (`mortar | mortar_penalty | kinematic | penalty | augmented_lagrange | tangential_penalty | ranfs`). `displacements` is required either here or in `[GlobalParams]`.
- Common knobs (validParams at `modules/contact/src/actions/ContactAction.C:71`):
  - `friction_coefficient` (default 0; required for `coulomb`).
  - `penalty` (default 1e8) — node-face penalty stiffness; for mortar use the `c_normal`/`c_tangential` knobs instead.
  - `tangential_tolerance` — extends edges of contact surfaces to avoid corner gaps (node-face only).
  - `capture_tolerance` (default 0) — normal distance within which nodes are captured into contact.
  - `tension_release` (default 0; <0 disables) — node releases when normal force drops below this. Node-face only.
  - `normalize_penalty` (default false) — divide penalty by tributary `NodalArea` so it scales with mesh; recommended on irregular meshes.
  - `normal_smoothing_distance`, `normal_smoothing_method` — parametric-coordinate smoothing of the contact normal across primary faces.
  - `c_normal` (default 1e6), `c_tangential` (default 1) — mortar-only numerical balance between gap magnitude and contact pressure. For stiffer materials, raise `c_normal`. These map to `c` and `c_t` on the underlying mortar constraints (`ComputeWeightedGapLMMechanicalContact`).
  - `correct_edge_dropping` (default false) — mortar-only; correct treatment of LM dofs on secondary elements without full primary contributions. Set `true` on coarse meshes to avoid spurious zero-LM nodes.
  - `use_dual` — switch the LM basis to dual functions (mortar). Defaulted on for penalty mortar, off for legacy LM mortar; set explicitly when you need PDass-style behavior.
  - `use_petrov_galerkin` (default false) — use standard test functions and dual shape for the LM (mortar).
  - `mortar_dynamics` (default false) — enable persistency-condition mortar contact. Required for `Newmark-beta` dynamic contact; pair with `newmark_beta`/`newmark_gamma`.
  - `automatic_pairing_boundaries` + `automatic_pairing_distance` + `automatic_pairing_method` (`NODE | CENTROID`) — auto-discover pairs by proximity instead of listing them.
  - `al_penetration_tolerance`, `al_incremental_slip_tolerance`, `al_frictional_force_tolerance`, `max_penalty_multiplier`, `penalty_multiplier`, `adaptivity_penalty_normal` (`SIMPLE | BUSSETTA`), `adaptivity_penalty_friction` (`SIMPLE | FRICTION_LIMIT`) — augmented-Lagrange controls; pair with `[Problem] type = AugmentedLagrangianContactProblem` and `[Convergence] type = AugmentedLagrangianContactConvergence`.

### `[Constraints]` — hand-rolled mortar (when not using `[Contact]`)

Use these only when the action cannot express what you need. The pattern is: declare a normal LM `[Variables]` entry on the secondary lower-d block, declare a `[UserObjects]` entry that integrates the weighted gap, then add one constraint for the gap and one constraint per displacement component for the residual contribution.

##### `ComputeWeightedGapLMMechanicalContact`
- Source: `modules/contact/include/constraints/ComputeWeightedGapLMMechanicalContact.h:22`
- Example: `modules/contact/test/tests/bouncing-block-contact/frictionless-weighted-gap.i:60` (sub-block `[weighted_gap_lm]`)
- LM-mortar normal-gap residual on the LM nonlinear variable. Pair with `LMWeightedGapUserObject` and `NormalMortarMechanicalContact` (one per component).
- Required: `variable` (LM normal var), `primary_boundary`, `secondary_boundary`, `primary_subdomain`, `secondary_subdomain`, `weighted_gap_uo`, `disp_x`, `disp_y` (and `disp_z` in 3D).
- Useful: `c` (default 1e6, balance term), `use_displaced_mesh = true` for finite deformation, `correct_edge_dropping`.

##### `ComputeFrictionalForceLMMechanicalContact`
- Source: `modules/contact/include/constraints/ComputeFrictionalForceLMMechanicalContact.h:20`
- Example: `modules/contact/test/tests/bouncing-block-contact/variational-frictional.i` (search `type = ComputeFrictionalForceLMMechanicalContact`)
- Coulomb mortar frictional residual on a tangential LM. Inherits the normal weighted-gap path from its parent. Pair with `LMWeightedGapUserObject` + `WeightedVelocitiesUserObject`.
- Required: same boundary/subdomain quartet, `variable` (tangential LM), `weighted_gap_uo`, `weighted_velocities_uo`, `friction_coefficient`, `disp_x`, `disp_y` (+ `disp_z`), `mu`.
- Useful: `c_t` (default 1), `epsilon` (regularization), `use_displaced_mesh = true`.

##### `NormalMortarMechanicalContact`
- Source: `modules/contact/include/constraints/NormalMortarMechanicalContact.h:16`
- Example: `modules/contact/test/tests/bouncing-block-contact/frictionless-weighted-gap.i:73` (sub-block `[normal_x]`)
- Pushes the normal-component contact pressure into the displacement residual of one component. Add **one per component**.
- Required: same boundary/subdomain quartet, `variable` (LM normal var), `secondary_variable` (the displacement variable for this component), `component` (`x|y|z`), `weighted_gap_uo`.
- Useful: `compute_lm_residuals = false` (the LM residual lives on the `Compute*` constraint), `use_displaced_mesh = true`.

##### `TangentialMortarMechanicalContact`
- Source: `modules/contact/include/constraints/TangentialMortarMechanicalContact.h:16`
- Example: `modules/contact/test/tests/bouncing-block-contact/variational-frictional.i` (search `type = TangentialMortarMechanicalContact`)
- Frictional-traction component on the displacement residual. Add one per component (and one per tangent direction in 3D).
- Required: boundary/subdomain quartet, `variable` (tangential LM), `secondary_variable` (displacement), `component`, `weighted_gap_uo`, `weighted_velocities_uo`.
- Useful: `direction` (3D only — first or second tangent), `compute_lm_residuals = false`, `use_displaced_mesh = true`.

##### `MortarGenericTraction` (CZM coupling)
- Source: `modules/contact/include/constraints/MortarGenericTraction.h:16`
- Example: `modules/contact/test/tests/cohesive_zone_model` (search `type = MortarGenericTraction`)
- Wires a `CohesiveZoneModelBase` UO's traction into the displacement residual. Used by `BilinearMixedModeCohesiveZoneModel` and friends.
- Required: boundary/subdomain quartet, `variable` (a placeholder LM, often dual), `secondary_variable`, `component`, `cohesive_zone_uo`.

##### `CartesianMortarMechanicalContact` / `ComputeWeightedGapCartesianLMMechanicalContact` / `ComputeFrictionalForceCartesianLMMechanicalContact`
- Source: `modules/contact/include/constraints/CartesianMortarMechanicalContact.h:18`, `.../ComputeWeightedGapCartesianLMMechanicalContact.h:20`, `.../ComputeFrictionalForceCartesianLMMechanicalContact.h:20`
- Example: `modules/contact/test/tests/mortar_cartesian_lms/`
- Cartesian-LM variant: separate `lm_x`/`lm_y` instead of a normal/tangential pair. Use when the contact normal is well-defined globally (e.g. flat surfaces) and you want simpler scaling.

##### `MechanicalContactConstraint` (legacy node-face)
- Source: `modules/contact/include/constraints/MechanicalContactConstraint.h:27`
- Example: `modules/contact/test/tests/mechanical_constraint/` (search `type = MechanicalContactConstraint`)
- Single class that handles **all** non-mortar formulations (`kinematic`, `penalty`, `augmented_lagrange`, `tangential_penalty`) — the `formulation` parameter selects behavior. Add one per displacement component.
- Required: `boundary` (secondary), `primary`, `variable`, `primary_variable`, `component`, `model`, `formulation`, `penalty`.
- Useful: `friction_coefficient`, `tension_release`, `capture_tolerance`, `tangential_tolerance`, `normalize_penalty`, `normal_smoothing_distance`, AL knobs (`al_penetration_tolerance`, `al_incremental_slip_tolerance`, `al_frictional_force_tolerance`).

##### `RANFSNormalMechanicalContact`
- Source: `modules/contact/include/constraints/RANFSNormalMechanicalContact.h:29`
- Example: `modules/contact/test/tests/bouncing-block-contact/bouncing-block-ranfs.i` (search `type = RANFSNormalMechanicalContact`)
- Reduced active-set node-face strategy that overwrites the secondary residual. Used when `formulation = ranfs`. One per displacement component.
- Required: `boundary`, `primary`, `variable`, `primary_variable`, `component`.

### `[UserObjects]` — mortar-only (when not using `[Contact]`)

##### `LMWeightedGapUserObject`
- Source: `modules/contact/include/userobjects/LMWeightedGapUserObject.h:21`
- Example: `modules/contact/test/tests/bouncing-block-contact/frictionless-weighted-gap.i:46` (sub-block `[weighted_gap_uo]`)
- Integrates the weighted gap on the mortar segment mesh and exposes contact pressure as the LM nonlinear variable. Use with `formulation = mortar` (LM path).
- Required: `primary_boundary`, `secondary_boundary`, `primary_subdomain`, `secondary_subdomain`, `lm_variable`, `disp_x`, `disp_y` (+ `disp_z`).
- Useful: `aux_lm`, `use_petrov_galerkin`.

##### `PenaltyWeightedGapUserObject`
- Source: `modules/contact/include/userobjects/PenaltyWeightedGapUserObject.h:23`
- Example: `modules/contact/test/tests/bouncing-block-contact/frictionless-penalty-weighted-gap.i` (search `type = PenaltyWeightedGapUserObject`)
- Synthesizes contact pressure from `penalty * gap` (+ AL multiplier). No LM nonlinear variable required. Use with `formulation = mortar_penalty`.
- Required: same primary/secondary quartet + `disp_x`/`disp_y`/`disp_z`, `penalty`.
- Useful: `penalty_multiplier`, `penetration_tolerance`, `max_penalty_multiplier`, `adaptivity_penalty_normal` (`SIMPLE | BUSSETTA`), `use_physical_gap`.

##### `PenaltyFrictionUserObject`
- Source: `modules/contact/include/userobjects/PenaltyFrictionUserObject.h:22`
- Example: `modules/contact/test/tests/bouncing-block-contact/frictional-penalty-weighted-vel.i`
- Frictional-pressure UO for `mortar_penalty` + `coulomb`.
- Required: primary/secondary quartet, `disp_*`, `friction_coefficient`, `penalty_friction`.

##### `NodalArea`
- Source: `modules/contact/include/userobjects/NodalArea.h`
- Per-node tributary area used when `normalize_penalty = true`. The `[Contact]` action declares this UO automatically when needed.

### `[Materials]` — CZM traction-separation laws

These live in `solid_mechanics/include/materials/cohesive_zone_model/` and are used by the `[Physics/SolidMechanics/CohesiveZone]` action.

##### `PureElasticTractionSeparation` / `ADPureElasticTractionSeparation`
- Source: `modules/solid_mechanics/include/materials/cohesive_zone_model/PureElasticTractionSeparation.h:18`
- Example: `modules/solid_mechanics/test/tests/cohesive_zone_model/czm_traction_separation_base.i` (sub-block `[czm_mat]`); AD variant: `modules/solid_mechanics/test/tests/cohesive_zone_model/ad_czm.i`
- Linear elastic traction-separation: `T = K * jump`. Diagonal stiffness in normal/shear.
- Required: `boundary`, `normal_stiffness`, `tangent_stiffness`.
- Useful: `base_name`.

##### `BiLinearMixedModeTraction`
- Source: `modules/solid_mechanics/include/materials/cohesive_zone_model/BiLinearMixedModeTraction.h:19`
- Example: `modules/solid_mechanics/test/tests/cohesive_zone_model/bilinear_mixed.i:111` (sub-block `[czm]`)
- Bilinear cohesive law with mixed-mode (normal/shear) damage; supports power-law and Benzeggagh-Kenane criteria.
- Required: `boundary`, `penalty_stiffness`, `GI_c`, `GII_c`, `normal_strength`, `shear_strength`, `displacements`, `eta`.
- Useful: `viscosity` (regularization for snapback), `mixed_mode_criterion` (`POWER_LAW | BK`), `power_law_parameter`.

##### `SalehaniIrani3DCTraction`
- Source: `modules/solid_mechanics/include/materials/cohesive_zone_model/SalehaniIrani3DCTraction.h:18`
- Example: `modules/solid_mechanics/test/tests/cohesive_zone_model/` (search `type = SalehaniIrani3DCTraction`)
- 3D coupled exponential-form traction-separation. Use when you want a smooth single-mode law without the bilinear discontinuity.
- Required: `boundary`, `normal_gap_at_maximum_normal_traction`, `tangential_gap_at_maximum_shear_traction`, `maximum_normal_traction`, `maximum_shear_traction`.

(Note: legacy guides sometimes mention `ExponentialCohesiveZoneMaterial`; that name does not exist in this tree — use `SalehaniIrani3DCTraction` for an exponential law, or `BiLinearMixedModeTraction` for a damage-type law.)

### `[Physics/SolidMechanics/CohesiveZone/<name>]` — CZM action

The new (Physics-style) syntax. Old inputs use `[Modules/TensorMechanics/CohesiveZoneMaster/<name>]` — both routes register the same `CohesiveZoneAction` via deprecated syntax (`modules/solid_mechanics/src/base/SolidMechanicsApp.C:111-120`). Prefer Physics for new files.

##### `[Physics/SolidMechanics/CohesiveZone/<name>]`
- Source: `modules/solid_mechanics/include/actions/CohesiveZoneAction.h:14`
- Example: `modules/solid_mechanics/test/tests/cohesive_zone_model/czm_traction_separation_base.i:62` (sub-block `[czm1]`); bilinear: `modules/solid_mechanics/test/tests/cohesive_zone_model/bilinear_mixed.i:96`
- Adds the interface kernels and interface materials needed to wire a traction-separation `[Materials]` law into the displacement residual. Pair with one CZM material entry on the same `boundary`.
- Required: `boundary` (the interface sideset created by `BreakMeshByBlockGenerator`).
- Useful: `strain` (`SMALL | FINITE`), `use_automatic_differentiation`, `base_name`, `generate_output` (`traction_x`, `traction_y`, `traction_z`, `normal_traction`, `tangent_traction`, `jump_x`, `jump_y`, `jump_z`, `normal_jump`, `tangent_jump`).

### `[Mesh]` — generators required for contact

##### `LowerDBlockFromSidesetGenerator` (mortar)
- Source: `framework/include/meshgenerators/LowerDBlockFromSidesetGenerator.h:17`
- Example: `modules/contact/test/tests/mortar_dynamics/frictional-mortar-3d-dynamics.i` (search `type = LowerDBlockFromSidesetGenerator`)
- Creates a lower-dimensional element block on a sideset — the **mortar segment mesh** lives here. The `[Contact]` action does this for you when `generate_mortar_mesh = true` (default), but you must do it by hand in `[Mesh]` if you hand-roll the mortar `[Constraints]`. Create one block per side (primary and secondary).
- Required: `input`, `sidesets`, `new_block_id` (and/or `new_block_name`).

##### `BreakMeshByBlockGenerator` (CZM)
- Source: `framework/include/meshgenerators/BreakMeshByBlockGenerator.h:18`
- Example: `modules/solid_mechanics/test/tests/cohesive_zone_model/bilinear_mixed.i:26` (sub-block `[split]`)
- Splits an interior block-block boundary into a true interface sideset (e.g. `Block1_Block2`) so each side has independent nodes — required for any `[Physics/SolidMechanics/CohesiveZone]` setup. Naming convention: `<block_a>_<block_b>` sorted alphabetically.
- Required: `input`. Useful: `add_interface_on_two_sides`, `surface_blocks`.

## Cross-cutting concerns

### Primary/secondary naming (no master/slave)
The framework moved from `master`/`slave` to `primary`/`secondary` years ago. Both still parse — the old keywords are deprecated aliases — but new inputs **must** use `primary`/`secondary`. In tests you'll occasionally see `master`/`slave`; treat that as legacy and don't propagate it. The class member naming in `MechanicalContactConstraint` is now `_primary_secondary_jacobian` etc.

### `displacements` GlobalParam
Every contact and CZM object needs the displacement variable list. Set it once at the top of the file in `[GlobalParams]` and let the action/UO/constraint pick it up:

```hit
[GlobalParams]
  displacements = 'disp_x disp_y'
[]
```

This also propagates into `[Physics/SolidMechanics/QuasiStatic]` and into the `disp_x`/`disp_y`/`disp_z` knobs on the mortar UOs.

### Mortar lower-d block prep
For mortar (`formulation = mortar` or `mortar_penalty`):
- The action with default `generate_mortar_mesh = true` builds the lower-d secondary block automatically — you don't need to call `LowerDBlockFromSidesetGenerator` yourself in that case.
- If you set `generate_mortar_mesh = false` (e.g. restart, or manual mesh construction), or if you bypass the action and put `[Constraints]` by hand, you **must** add `LowerDBlockFromSidesetGenerator` for the secondary side (and usually the primary side too) in `[Mesh]`. Conventional block ids: `3` for secondary lower, `4` for primary lower in 2D test inputs.
- For LM (variational) mortar, declare a normal LM nonlinear variable on the secondary lower-d block: `[Variables/normal_lm] block = '3' []`. For `mortar_penalty`, **do not** declare any LM variable — the action and the UO synthesize pressure from gap × penalty.

### Mortar geometry consistency
Mortar uses a finer-side-is-secondary projection. **The secondary side should be the finer (or softer, for stiffness mismatches) of the two surfaces.** Reversing primary/secondary inverts the projection and produces non-monotone gap residuals; this is mesh-dependent and easy to overlook. Convergence problems on a mortar problem that "should work" — check this first. (See contact-authoring.md pitfall #5.)

For 3D Coulomb mortar there are *two* tangent directions; the action automatically emits two tangential constraints per displacement component (`ContactAction.C:552`).

### AD-only mortar
All mortar constraints (`ComputeWeightedGapLMMechanicalContact`, `NormalMortarMechanicalContact`, `TangentialMortarMechanicalContact`, `MortarGenericTraction`) inherit from `ADMortarConstraint`/`ADMortarLagrangeConstraint` and use AD throughout. Pair them with **AD** solid-mechanics materials (`ADComputeFiniteStrainElasticStress`, `ADComputeElasticityTensor`, etc.) and the AD strain calculator from `[Physics/SolidMechanics/QuasiStatic]` (`use_automatic_differentiation = true`). Mixing AD mortar with non-AD stress materials breaks the off-diagonal Jacobian chain.

### Pairing with `[Physics/SolidMechanics]`
Contact only enforces the interface condition; you still need a momentum-balance kernel inside each body. The standard pattern is:

```hit
[Physics/SolidMechanics/QuasiStatic]
  [all]
    add_variables = true
    strain = FINITE
    use_automatic_differentiation = true   # required for mortar
  []
[]
```

This declares `disp_x`/`disp_y`/`disp_z`, adds `(AD)StressDivergenceTensors`, and is enough for the contact action to find them. See [solid-mechanics.md](./solid-mechanics.md) for the full Physics catalog.

### `use_displaced_mesh`
Mortar contact must run on the **displaced** mesh for finite deformation — the action sets this on emitted constraints automatically. If you hand-roll constraints, set `use_displaced_mesh = true` on every contact constraint and matching mortar UO.

### Augmented-Lagrange wiring
For AL formulations (`augmented_lagrange` node-face, or any mortar penalty path with AL hooks), set:

```hit
[Problem]
  type = AugmentedLagrangianContactProblem  # or AugmentedLagrangianContactFEProblem
[]
[Convergence]
  type = AugmentedLagrangianContactConvergence
[]
```

The outer (Uzawa) iteration is owned by `Problem` + `Convergence`; the inner Newton solve is the standard one. Without these, AL hooks silently no-op and your tolerances are ignored. (See `../moose/contact-authoring.md` pitfall #7.)

## Minimal scaffold

A 2D frictionless mortar contact between two blocks under quasistatic finite strain. The `[Contact]` action handles mesh prep, UOs, LM variable, and per-component constraints internally — this is the canonical input.

```hit
[GlobalParams]
  displacements = 'disp_x disp_y'
[]

[Mesh]
  [top_block]
    type = GeneratedMeshGenerator
    dim = 2
    nx = 4
    ny = 4
    xmin = 0
    xmax = 1
    ymin = 1.01      # offset slightly above bottom block
    ymax = 2.01
  []
  [top_block_id]
    type = SubdomainIDGenerator
    input = top_block
    subdomain_id = 1
  []
  [top_block_sidesets]
    type = RenameBoundaryGenerator
    input = top_block_id
    old_boundary = '0 1 2 3'
    new_boundary = 'top_bottom top_right top_top top_left'
  []
  [bottom_block]
    type = GeneratedMeshGenerator
    dim = 2
    nx = 8                # finer side -> secondary
    ny = 4
    xmin = 0
    xmax = 1
    ymin = 0
    ymax = 1
  []
  [bottom_block_id]
    type = SubdomainIDGenerator
    input = bottom_block
    subdomain_id = 2
  []
  [bottom_block_sidesets]
    type = RenameBoundaryGenerator
    input = bottom_block_id
    old_boundary = '0 1 2 3'
    new_boundary = 'bot_bottom bot_right bot_top bot_left'
  []
  [combined]
    type = MeshCollectionGenerator
    inputs = 'top_block_sidesets bottom_block_sidesets'
  []
[]

[Physics/SolidMechanics/QuasiStatic]
  [all]
    add_variables = true
    strain = FINITE
    use_automatic_differentiation = true
    generate_output = 'stress_yy'
  []
[]

[Contact]
  [contact]
    primary = top_bottom        # primary = top block's bottom face
    secondary = bot_top         # secondary = bottom block's top face (finer)
    model = frictionless
    formulation = mortar
    c_normal = 1e6
    correct_edge_dropping = true
  []
[]

[BCs]
  [fix_bot]
    type = ADDirichletBC
    variable = disp_y
    boundary = bot_bottom
    value = 0
  []
  [fix_bot_x]
    type = ADDirichletBC
    variable = disp_x
    boundary = bot_bottom
    value = 0
  []
  [push_top]
    type = ADFunctionDirichletBC
    variable = disp_y
    boundary = top_top
    function = '-0.05 * t'
  []
[]

[Materials]
  [elasticity]
    type = ADComputeIsotropicElasticityTensor
    youngs_modulus = 1e6
    poissons_ratio = 0.3
  []
  [stress]
    type = ADComputeFiniteStrainElasticStress
  []
[]

[Preconditioning]
  [smp]
    type = SMP
    full = true
  []
[]

[Executioner]
  type = Transient
  solve_type = NEWTON
  petsc_options_iname = '-pc_type -pc_factor_shift_type -pc_factor_shift_amount'
  petsc_options_value = 'lu       NONZERO               1e-15'
  line_search = none
  nl_rel_tol = 1e-10
  dt = 0.1
  end_time = 1
[]

[Outputs]
  exodus = true
[]
```

For a Coulomb-friction variant, change `model = coulomb` and add `friction_coefficient = 0.3` plus `c_tangential = 1e3`. For glued (tied) contact, change `model = glued` — same scaffold, no other knobs needed. For penalty mortar (no LM nonlinear var, cheaper), change `formulation = mortar_penalty` and replace `c_normal` with `penalty = 1e6`. For node-face penalty (legacy fast path), change to `formulation = penalty` with `penalty = 1e6`.
