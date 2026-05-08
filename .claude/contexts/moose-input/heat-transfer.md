# Authoring inputs: Heat Transfer module

Reach for this guide when you're writing or editing a `.i` file for a heat-conduction problem (steady or transient, with or without a heat source, with surface convection / radiation, with a gap between bodies). The framework-level `[Kernels]` you'll need (`HeatConduction`, `ADHeatConduction`, `HeatConductionTimeDerivative`, etc.) are already in [kernels.md](./kernels.md) — this file pulls them together with the **module-only** objects (BCs, Materials, the `[Physics/HeatConduction]` and `[ThermalContact]` shorthand actions, postprocessors) and shows the typical conduction recipe end-to-end. For the C++ side (writing a new HT kernel / BC / gap flux model) see `../moose/heat-transfer-authoring.md`.

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. Each catalog entry cites a **source header** and one **canonical example .i**. AD twins (`ADFoo`) live in the same templated header as the non-AD class — same params, same patterns; differences called out per-entry where they exist.

## When to use this (vs alternatives)

Three orthogonal decisions: which **block** you author, **AD vs non-AD**, and **shorthand vs hand-rolled**.

1. New thermal problem and you don't need fine control over individual kernels: use **`[Physics/HeatConduction/FiniteElement/<name>]`** (or `FiniteVolume`) — one block expands to `[Variables]` + temperature `[Kernels]` + standard `[BCs]` + an IC. Defaults to AD. See the catalog below for the param surface.
2. Mixing heat conduction with another physics (mechanics, chemistry, electromagnetics) where you need explicit control: hand-roll **`[Kernels]`** + **`[BCs]`** + **`[Materials]`**. Pull `ADHeatConduction` (volumetric `-div(k grad T)`), `ADHeatConductionTimeDerivative` (transient), and a heat-source kernel from [kernels.md](./kernels.md); pull surface BCs from this catalog.
3. AD vs non-AD: **default to AD** (`ADHeatConduction`, `ADConvectiveHeatFluxBC`, `ADHeatConductionMaterial`, ...). The non-AD twin exists for legacy parity and for cases where you must hand-author a Jacobian. Don't mix — `ADHeatConduction` consumes an `ADMaterialProperty<Real> "thermal_conductivity"` so the matching `[Materials]` entry must be `AD*` too.
4. Heat exchange across a gap (two surfaces, displaced or fixed mesh): use the **`[ThermalContact]`** action (legacy, node-on-face, both AD and non-AD). For modular mortar gap conduction (AD-only) use `[MortarGapHeatTransfer]` — see `../moose/heat-transfer-authoring.md`.
5. Surface radiation to a far-field temperature: `FunctionRadiativeBC` / `ADFunctionRadiativeBC` (one Function emissivity), `InfiniteCylinderRadiativeBC` (geometry factor for cylindrical exchange). For **enclosure** (cavity) radiation (mutual surface-to-surface within an enclosure), use `[GrayDiffuseRadiation]` action + `GrayLambertNeumannBC` (not in this guide).
6. Coupling to a fluid temperature defined as an aux-variable (e.g. multiapp from a thermal-hydraulics solver): `CoupledConvectiveHeatFluxBC` accepts AuxVariable inputs for `T_infinity`/`htc`. The plain `ConvectiveHeatFluxBC` accepts `MaterialProperty<Real>` (use `GenericConstantMaterial` to wrap constants) or, for the AD form, also `Moose::Functor<ADReal>`.

## Catalog

### `[Physics/HeatConduction/FiniteElement/<name>]` — CG action shorthand

##### `HeatConductionCG`
- Source: `modules/heat_transfer/include/physics/HeatConductionCG.h:17` (registered to syntax `Physics/HeatConduction/FiniteElement/*` at `modules/heat_transfer/src/base/HeatTransferApp.C:56`)
- Example: `modules/heat_transfer/test/tests/physics/test_cg.i:11` (block `[HeatConduction]`/`[FiniteElement]`/`[h1]`)
- Adds the temperature variable, conduction kernel, time derivative (when transient), heat-source kernel, IC, and standard BCs in one block.
- Required: at least one of `thermal_conductivity` (MaterialPropertyName) — defaulted to `"thermal_conductivity"` so a matching `[Materials]` entry is sufficient.
- Useful (defined on `HeatConductionCG`):
  - `temperature_name` (default `T`) — name of the variable created.
  - `thermal_conductivity`, `specific_heat`, `density` — MaterialPropertyNames.
  - `use_automatic_differentiation` (default `true`) — flips between `ADHeatConduction` and `HeatConduction` underneath.
- Useful (inherited from `HeatConductionPhysicsBase`, `modules/heat_transfer/src/physics/HeatConductionPhysicsBase.C:18`):
  - `initial_temperature` (default `300`) — used as `FunctionIC` value.
  - `heat_source_var` (couples an AuxVariable as a volumetric source via `ADCoupledForce`); `heat_source_blocks` block-restricts it.
  - `heat_source_functor` — Real / FunctionName / PostprocessorName (uses `BodyForce` underneath).
  - `heat_flux_boundaries` + `boundary_heat_fluxes` — list pair, applies `FunctorNeumannBC` per boundary.
  - `insulated_boundaries` — listed boundaries get zero-flux (no BC added; that IS the natural BC).
  - `fixed_temperature_boundaries` + `boundary_temperatures` — list pair, applies `FunctorDirichletBC`.
  - `fixed_convection_boundaries` + `fixed_convection_T_fluid` + `fixed_convection_htc` — list triple, applies `ADConvectiveHeatFluxBC` (AD only).
  - `transient` (inherited from `PhysicsBase`) — when on a `Transient` executioner, `ADHeatConductionTimeDerivative` is added.
  - `preconditioning` (`default|defer`, default `default`) — auto-adds hypre/boomeramg PETSc options.
- The matching FV variant is `[Physics/HeatConduction/FiniteVolume/<name>]` → `HeatConductionFV` (`modules/heat_transfer/include/physics/HeatConductionFV.h:18`). Same param surface, different kernel/BC factory under the hood.

### `[Kernels]` — heat-transfer-specific (entries also catalogued in [kernels.md](./kernels.md))

##### `HeatConduction` / `ADHeatConduction`
- Source: `modules/heat_transfer/include/kernels/HeatConduction.h:24` / `modules/heat_transfer/include/kernels/ADHeatConduction.h:14`
- Example: `modules/heat_transfer/test/tests/verify_against_analytical/2d_steady_state.i:23` (sub-block `[HeatDiff]`); AD: `modules/heat_transfer/test/tests/ad_heat_conduction/test.i:23`
- `-div(k grad T)` using a `MaterialProperty<Real>` named `thermal_conductivity`.
- Required: `variable`.
- Useful: `diffusion_coefficient` (non-AD, default `thermal_conductivity`) / `thermal_conductivity` (AD).

##### `HeatConductionTimeDerivative` / `ADHeatConductionTimeDerivative`
- Source: `modules/heat_transfer/include/kernels/HeatConductionTimeDerivative.h:26` / `modules/heat_transfer/include/kernels/ADHeatConductionTimeDerivative.h:14`
- Example: `modules/heat_transfer/test/tests/verify_against_analytical/1D_transient.i:33` (sub-block `[HeatTdot]`); AD: `modules/heat_transfer/test/tests/ad_heat_conduction/test.i:28`
- `rho * c_p * dT/dt` using `MaterialProperty<Real>` named `density` and `specific_heat`.
- Required: `variable`.
- Useful: `specific_heat` (default `specific_heat`), `density_name` (default `density`).

##### `HeatSource`
- Source: `modules/heat_transfer/include/kernels/HeatSource.h:16`
- Example: `modules/heat_transfer/test/tests/heat_source_bar/heat_source_bar.i:36` (sub-block `[heatsource]`)
- Thin alias of `BodyForce` with heat-source-friendly param names. For an AD variant with a material-property source mask, use `ADMatHeatSource` (`modules/heat_transfer/include/kernels/ADMatHeatSource.h`) — see `modules/heat_transfer/test/tests/heat_source_bar/ad_heat_source_bar.i:37`.
- Required: `variable`.
- Useful: `value` (default 1), `function`, `postprocessor`.

##### `JouleHeatingSource`
- Source: `modules/heat_transfer/include/kernels/JouleHeatingSource.h:27` (NOTE: deprecation announced for the non-AD form; prefer `ADJouleHeatingSource` `modules/heat_transfer/include/kernels/ADJouleHeatingSource.h`).
- Example: `modules/heat_transfer/test/tests/joule_heating/transient_jouleheating.i:27` (sub-block `[HeatSrc]`)
- `Q = sigma * |grad phi|^2` from an electric-potential coupled variable.
- Required: `variable`, `elec`.
- Useful: `electrical_conductivity` (default `electrical_conductivity`).

### `[BCs]` — heat-transfer-specific

##### `ConvectiveHeatFluxBC` / `ADConvectiveHeatFluxBC`
- Source: `modules/heat_transfer/include/bcs/ConvectiveHeatFluxBC.h:18` / `ADConvectiveHeatFluxBC.h:18`
- Example: `modules/heat_transfer/test/tests/convective_heat_flux/flux.i:44` (sub-block `[right]`); AD: `modules/heat_transfer/test/tests/ad_convective_heat_flux/flux.i` (search `type = ADConvectiveHeatFluxBC`).
- Newton's law of cooling `q = htc * (T - T_inf)` integrated over a sideset.
- Required: `variable`, `boundary`.
- Required (non-AD, MaterialPropertyName): `T_infinity`, `heat_transfer_coefficient`. Bare numeric inputs (`T_infinity = 200.0`) are auto-promoted to a constant material via standard MOOSE plumbing.
- Required (AD, exactly ONE source per quantity): either MaterialPropertyName via `T_infinity` / `heat_transfer_coefficient`, OR functor via `T_infinity_functor` / `heat_transfer_coefficient_functor`.
- Useful (non-AD): `heat_transfer_coefficient_dT` (defaults to a property of the same name; supply 0 if `htc` is constant).

##### `CoupledConvectiveHeatFluxBC`
- Source: `modules/heat_transfer/include/bcs/CoupledConvectiveHeatFluxBC.h:19`
- Example: `modules/heat_transfer/test/tests/postprocessors/ad_convective_ht_side_integral.i:59` (sub-block `[channel_heat_transfer]`)
- Convective BC where `T_infinity` and `htc` come from coupled (Aux)Variables — the typical multi-app coupling shape.
- Required: `variable`, `boundary`, `T_infinity` (CoupledVar), `htc` (CoupledVar).
- Useful: `alpha` (vector of phase fractions when `T_infinity`/`htc` are vector-valued), `scale_factor`.

##### `FunctionRadiativeBC` / `ADFunctionRadiativeBC`
- Source: `modules/heat_transfer/include/bcs/FunctionRadiativeBC.h:21` (typedefs at `:37` / `:38`).
- Example: `modules/heat_transfer/test/tests/radiative_bcs/function_radiative_bc.i:57` (sub-block `[bot_right]`).
- Surface radiation `q = sigma * eps(t,x,y,z) * (T^4 - Tinf^4)` to a far-field `Function`.
- Required: `variable`, `boundary`, `emissivity_function` (FunctionName), `Tinfinity` (FunctionName).
- Useful: `stefan_boltzmann_constant` (default 5.670367e-8 W/(m^2·K^4)).

##### `InfiniteCylinderRadiativeBC` / `ADInfiniteCylinderRadiativeBC`
- Source: `modules/heat_transfer/include/bcs/InfiniteCylinderRadiativeBC.h:19` (typedefs at `:47` / `:48`).
- Example: `modules/heat_transfer/test/tests/radiative_bcs/radiative_bc_cyl.i:56` (sub-block `[radiative_bc]`).
- Radiative exchange between two coaxial infinite cylinders; precomputes the geometry-and-emissivity factor.
- Required: `variable`, `boundary`, `boundary_emissivity`, `boundary_radius`, `cylinder_emissivity`, `cylinder_radius`, `Tinfinity` (FunctionName).
- Useful: `stefan_boltzmann_constant`.

##### `HeatConductionBC`
- Source: `modules/heat_transfer/include/bcs/HeatConductionBC.h:17`
- `q = -k grad T . n` natural BC; reads `MaterialProperty<Real>` named `thermal_conductivity`. No in-tree test uses this directly; for ordinary fixed-flux Neumann prefer the framework's `NeumannBC` or `FunctorNeumannBC`.
- Required: `variable`, `boundary`.

##### `GapHeatTransfer`
- Source: `modules/heat_transfer/include/bcs/GapHeatTransfer.h:20`
- Example: `modules/heat_transfer/test/tests/gap_heat_transfer_htonly/gap_heat_transfer_htonly_test.i:48` (the `[ThermalContact]` action expands to this BC plus a `GapConductance` material plus a `PenetrationAux` aux kernel).
- Conduction-plus-radiation across a small gap, evaluated against `PenetrationLocator` data; reads `MaterialProperty<Real>` named `gap_conductance`.
- Almost never authored directly — drive it via the `[ThermalContact]` action (next section).

### `[Materials]` — heat-transfer-specific

##### `HeatConductionMaterial` / `ADHeatConductionMaterial`
- Source: `modules/heat_transfer/include/materials/HeatConductionMaterial.h:22` (typedefs at `:50` / `:51`).
- Example: `modules/heat_transfer/test/tests/gap_heat_transfer_htonly/gap_heat_transfer_htonly_test.i:149` (sub-block `[heat1]`); AD: `modules/heat_transfer/test/tests/postprocessors/ad_convective_ht_side_integral.i:85` (sub-block `[pronghorn_solid_material]`).
- Declares `thermal_conductivity` (always also `thermal_conductivity_dT` for the non-AD form's Jacobian) and `specific_heat`. Constants OR `Function`s of a coupled `temp` variable.
- Required: at least one of `thermal_conductivity` (Real) or `thermal_conductivity_temperature_function` (FunctionName); same pair for `specific_heat`.
- Useful: `temp` (CoupledVar — required when any property is a function of T), `min_T` (Real — clamp T-argument from below before evaluating the temperature function), `block`.

##### `AnisoHeatConductionMaterial`
- Source: `modules/heat_transfer/include/materials/AnisoHeatConductionMaterial.h`
- Example: `modules/heat_transfer/test/tests/heat_conduction_patch/heat_conduction_patch_hex20_aniso.i` (search `type = AnisoHeatConductionMaterial`).
- Tensor-valued `thermal_conductivity` + scalar `specific_heat`. Pair with `AnisoHeatConduction` kernel — the scalar `HeatConduction` kernel will not pick up tensor properties.
- Required: `thermal_conductivity` (vector of 3 OR 9 reals).

##### `GapConductance` / `GapConductanceConstant` (gap conductance closures)
- Source: `modules/heat_transfer/include/materials/GapConductance.h:17` and `GapConductanceConstant.h`.
- Implicitly added by `[ThermalContact]`. Direct authoring is rare; `GapConductance` declares `gap_conductance`/`_dT`/`gap_conductivity`, `GapConductanceConstant` declares a constant areal `gap_conductance`.

##### `ElectricalConductivity`
- Source: `modules/heat_transfer/include/materials/ElectricalConductivity.h`
- Example: `modules/heat_transfer/test/tests/joule_heating/transient_jouleheating.i:79` (sub-block `[sigma]`).
- Declares `electrical_conductivity` (with `T`-dependence built-in for copper). Pairs with `JouleHeatingSource` / `ADJouleHeatingSource`.
- Required: `temperature` (CoupledVar).

(Specific-heat-of-fluid families like `SpecificHeatPureFluid` live in the `fluid_properties` module, not `heat_transfer` — author them via `[FluidProperties]` instead. They are NOT in `modules/heat_transfer/include/materials/`.)

### `[ThermalContact]` action

##### `[ThermalContact/<name>]` → `ThermalContactAction` (`type = GapHeatTransfer`)
- Source: `modules/heat_transfer/include/actions/ThermalContactAction.h:16` (registered to syntax `ThermalContact/*` at `modules/heat_transfer/src/base/HeatTransferApp.C:59`).
- Example: `modules/heat_transfer/test/tests/gap_heat_transfer_htonly/gap_heat_transfer_htonly_test.i:48`; with `min_gap`/`max_gap`: `modules/heat_transfer/test/tests/heat_conduction/min_gap/min_gap.i:134`.
- One sub-block expands to: `GapHeatTransfer` BC on `secondary`, a `GapConductance` material on `secondary`, an `AuxVariable` + `PenetrationAux` capturing the gap distance, and (optionally) a save-in vector for the secondary-side flux. Behind the scenes also wires the `PenetrationLocator` and its relationship managers.
- Required: `variable` (the temperature), `secondary` (boundary list), `type` (string — set to `GapHeatTransfer` for the standard model; `GapPerfectConductance` for the penalty-perfect-conduction variant).
- Useful (`ThermalContactAction`):
  - `primary` (boundary list, paired with `secondary`).
  - `quadrature` (default `false`) — `true` switches to quadrature-point-based gap evaluation (recommended for non-conforming meshes).
  - `gap_conductivity` (default 1) — bulk gas conductivity; the action turns this into a `gap_conductance` material property.
  - `gap_conductivity_function` (FunctionName), `gap_conductivity_function_variable` (typically the temperature) — temperature-dependent gas conductivity.
  - `appended_property_name` — suffix for declared property names; required when you have multiple `[ThermalContact]` blocks on the same problem (otherwise the second block tries to re-declare `gap_conductance`).
  - `displacements` — the displacement variable list (for displaced-mesh problems).
- Useful (forwarded from `GapConductance::actionParameters()`, `modules/heat_transfer/src/materials/GapConductance.C:84`):
  - `gap_geometry_type` (`PLATE|CYLINDER|SPHERE`) — default depends on coordinate system.
  - `cylinder_axis_point_1` / `cylinder_axis_point_2` (RealVectorValue) — required when `gap_geometry_type = CYLINDER`.
  - `sphere_origin` (RealVectorValue) — required when `gap_geometry_type = SPHERE`.
  - `emissivity_primary` (default 1, range [0,1]) — primary surface emissivity for the radiation term. Set to 0 to disable radiation.
  - `emissivity_secondary` (default 1, range [0,1]).
  - `min_gap` (default 1e-6) — lower clamp on gap width (avoids division-by-zero when surfaces touch).
  - `min_gap_order` (default 0, allowed 0 or 1) — order of Taylor expansion of `1/gap` below `min_gap`.
  - `max_gap` (default 1e6) — upper clamp; gap heat transfer is zeroed beyond this.

The action does NOT take a `gap_conductance` parameter — it computes that property internally from `gap_conductivity` / `gap_width`. Don't confuse the two.

### `[Postprocessors]` — heat-transfer-relevant

##### `SideDiffusiveFluxAverage` (framework, but the canonical HT diagnostic)
- Source: `framework/include/postprocessors/SideFluxAverage.h` (typedef chain).
- Example: `modules/heat_transfer/test/tests/convective_heat_flux/flux.i:55` (sub-block `[right_flux]`).
- `(1/|S|) * int_S (-D grad u . n) dS` — boundary-averaged heat flux. Use `diffusivity = thermal_conductivity` to get the actual heat flux.
- Required: `variable`, `boundary`, `diffusivity` (MaterialPropertyName OR a bare number — bare numbers are auto-promoted).

##### `ConvectiveHeatTransferSideIntegral` / `ADConvectiveHeatTransferSideIntegral`
- Source: `modules/heat_transfer/include/postprocessors/ConvectiveHeatTransferSideIntegral.h:18` (typedefs `:44` / `:45`).
- Example: `modules/heat_transfer/test/tests/postprocessors/ad_convective_ht_side_integral.i:108` (sub-block `[Qw1]`).
- `int_S htc * (T_solid - T_fluid) dS` — total convective heat transfer crossing a sideset. Mirror of `ConvectiveHeatFluxBC` for diagnostics.
- Required: `boundary`, `T_solid` (CoupledVar). Plus exactly one source for fluid temperature (`T_fluid_var` CoupledVar OR `T_fluid` MaterialPropertyName), and exactly one source for HTC (`htc_var` CoupledVar OR `htc` MaterialPropertyName).

##### `HomogenizedThermalConductivity`
- Source: `modules/heat_transfer/include/postprocessors/HomogenizedThermalConductivity.h:19`
- Example: `modules/heat_transfer/test/tests/homogenization/heatConduction2D.i:120` (sub-block `[k_xx]`).
- Returns a single `(row, col)` component of the homogenized thermal-conductivity tensor for a unit-cell setup with characteristic functions `chi`. Pair with `HomogenizedHeatConduction` kernel for the unit-cell solve.
- Required: `chi` (CoupledVar list — one per spatial dimension), `row` (uint), `col` (uint).
- Useful: `scale_factor`, `diffusion_coefficient` (default `thermal_conductivity`), `is_tensor`.

##### `ThermalConductivity`
- Source: `modules/heat_transfer/include/postprocessors/ThermalConductivity.h`
- Effective thermal conductivity `k = q * dx / (T_hot - T_cold)` from a heat flux pp and two temperature pps (steady-state slab analog).
- Required: `dx` (Real), `flux` (PostprocessorName), `T_hot` (PostprocessorName).

### `[AuxKernels]` — heat-transfer-specific

##### `JouleHeatingHeatGeneratedAux`
- Source: `modules/heat_transfer/include/auxkernels/JouleHeatingHeatGeneratedAux.h:25`
- Example: `modules/heat_transfer/test/tests/joule_heating/transient_aux_jouleheating.i:46` (sub-block `[joule_heating_calculation]`).
- Aux output of the Joule heating term `Q = sigma * |grad phi|^2` (or via a precomputed AD material property). Pair with `JouleHeatingSource` for diagnostics.
- Required: `variable`. Plus exactly one source: `heating_term` (ADMaterialPropertyName) OR the legacy `(elec, electrical_conductivity)` pair.

For a generic boundary-flux output, use the framework `DiffusionFluxAux` — see [kernels.md](./kernels.md) `[AuxKernels]` catalog.

## Cross-cutting concerns

### Material-property names — the spelling matters
- `thermal_conductivity`, `density`, `specific_heat` are the **default** property names that every HT kernel/BC reaches for. If you use `HeatConductionMaterial` / `ADHeatConductionMaterial` / `GenericConstantMaterial` with these names, you don't need to touch the kernel's `diffusion_coefficient` / `density_name` / `specific_heat` parameters. If you rename a property (e.g. multiple materials in one mesh) you MUST also override the kernel's parameter to match.
- `thermal_conductivity_dT` is required for **non-AD** Jacobians — `HeatConductionMaterial` produces it automatically; `GenericConstantMaterial` does NOT (so the non-AD path with constant materials silently has a wrong Jacobian for temperature-dependent setups). Use `ADHeatConduction` + `ADHeatConductionMaterial` to avoid the trap.
- `gap_conductance` (areal, W/(m^2·K)) is what `GapHeatTransfer` BC reads. `gap_conductivity` (bulk, W/(m·K)) is what you typically *input* to `[ThermalContact]`; the action computes `gap_conductance = gap_conductivity / gap_width` internally. Don't pass one expecting the other (factor-of-gap-width error, often orders of magnitude).

### The `[ThermalContact]` action expands quietly
- A single `[ThermalContact/foo]` sub-block adds: a `GapHeatTransfer` BC, a `GapConductance` material, an `AuxVariable` named `penetration` (or `penetration_<appended>`), a `PenetrationAux` aux kernel, and (when requested) a `save_in` vector for the secondary-side flux. It also registers the `PenetrationLocator` and its relationship managers.
- Two `[ThermalContact]` blocks on the same temperature but different boundary pairs MUST set distinct `appended_property_name` values, or the second block will fail to add `gap_conductance` (already declared by the first). The aux variable name is also derived from `appended_property_name`.
- For displaced-mesh problems pass `displacements = 'disp_x disp_y ...'` so the gap geometry tracks the deformed configuration.

### AD vs non-AD chain
- `ADHeatConduction` reads `ADMaterialProperty<Real> "thermal_conductivity"` — produced by `ADHeatConductionMaterial` or `ADGenericConstantMaterial`. Pairing `ADHeatConduction` with non-AD `HeatConductionMaterial` will fail at setup ("property declared as non-AD"). Same trap with `GenericConstantMaterial` vs `ADGenericConstantMaterial`.
- `ADConvectiveHeatFluxBC` accepts EITHER an AD material property OR a functor (variable/function/functor-mat-prop). Exactly one source per quantity — listing both `T_infinity` and `T_infinity_functor` errors at setup. The `initialSetup()` override decides whether the functor lives on the boundary side or the neighbor side; if your functor is defined only on a subdomain that doesn't touch the sideset on the primary side, it transparently switches to the neighbor (good for multiphysics couplings; surprising if you don't expect it).
- `[ThermalContact]` is itself non-AD-friendly (the underlying `GapHeatTransfer` BC + `GapConductance` material are non-AD). Mixing it with AD-only physics elsewhere in the input is fine; the BC contributes a finite-difference Jacobian into the same residual.

### Coupling temperature into mechanics (and back)
- For thermo-mechanical problems, declare the temperature once (typically via `[Physics/HeatConduction]`) and pass its name into the strain materials via `temperature = T` (e.g. `ComputeThermalExpansionEigenstrain`). See [solid-mechanics.md](./solid-mechanics.md). The mechanics `[Physics/SolidMechanics/QuasiStatic]` action accepts `eigenstrain_names` to pick up the thermal eigenstrain.
- For Joule-heating problems, declare `T` and `elec` as separate `[Variables]`, run `HeatConduction` on `T` and `HeatConduction` (with `diffusion_coefficient = electrical_conductivity`) on `elec`, and add `JouleHeatingSource` (or AD) on `T` with `elec = elec`. See `modules/heat_transfer/test/tests/joule_heating/transient_jouleheating.i` end-to-end.

### Block / boundary restriction
- Most HT objects accept `block` (subdomain list) and `boundary` (sideset list). `HeatConductionMaterial` MUST be block-restricted (or applied globally) — the kernels error at setup if `thermal_conductivity` isn't declared on every block where the kernel runs.
- For `[ThermalContact]`, `primary` and `secondary` are **boundary lists**, not subdomains. The boundary pair must match across the gap (same number of elements/nodes if `quadrature = false`, arbitrary if `quadrature = true`).

## Minimal scaffold

A 1D transient heat-conduction bar with a volumetric heat source, a fixed temperature on the left, and convective cooling on the right. Two equivalent forms below — the **Physics shorthand** is what you should write for new inputs; the **hand-rolled** version expands what the action creates and is what you need when you must mix HT with other physics.

### Form A — `[Physics/HeatConduction]` shorthand

```hit
[Mesh]
  [bar]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 40
    xmax = 0.01
  []
[]

[Physics]
  [HeatConduction]
    [FiniteElement]
      [bar]
        temperature_name = T
        initial_temperature = 300

        # Material-property names (defaults shown)
        thermal_conductivity = thermal_conductivity
        specific_heat       = specific_heat
        density             = density

        # Volumetric heat source as a constant functor
        heat_source_functor = 3.8e8

        # Boundary conditions
        fixed_temperature_boundaries = 'left'
        boundary_temperatures        = '600'

        fixed_convection_boundaries  = 'right'
        fixed_convection_T_fluid     = '300'
        fixed_convection_htc         = '500'
      []
    []
  []
[]

[Materials]
  [props]
    type = ADGenericConstantMaterial
    prop_names  = 'thermal_conductivity specific_heat density'
    prop_values = '3.0                  300.0         10431.0'
  []
[]

[Executioner]
  type = Transient
  scheme = bdf2
  num_steps = 20
  dt = 0.5
  solve_type = NEWTON
[]

[Postprocessors]
  [right_flux]
    type = SideDiffusiveFluxAverage
    variable = T
    boundary = right
    diffusivity = thermal_conductivity
  []
[]

[Outputs]
  exodus = true
[]
```

### Form B — hand-rolled `[Kernels]` + `[BCs]` + `[Materials]`

```hit
[Mesh]
  [bar]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 40
    xmax = 0.01
  []
[]

[Variables]
  [T]
    initial_condition = 300
  []
[]

[Kernels]
  [conduction]
    type = ADHeatConduction
    variable = T
  []
  [time]
    type = ADHeatConductionTimeDerivative
    variable = T
  []
  [source]
    type = HeatSource
    variable = T
    value = 3.8e8
  []
[]

[BCs]
  [left]
    type = DirichletBC
    variable = T
    boundary = left
    value = 600
  []
  [right]
    type = ADConvectiveHeatFluxBC
    variable = T
    boundary = right
    T_infinity_functor = 300
    heat_transfer_coefficient_functor = 500
  []
[]

[Materials]
  [props]
    type = ADGenericConstantMaterial
    prop_names  = 'thermal_conductivity specific_heat density'
    prop_values = '3.0                  300.0         10431.0'
  []
[]

[Executioner]
  type = Transient
  scheme = bdf2
  num_steps = 20
  dt = 0.5
  solve_type = NEWTON
  petsc_options_iname = '-pc_type -pc_hypre_type'
  petsc_options_value = 'hypre boomeramg'
[]

[Postprocessors]
  [right_flux]
    type = SideDiffusiveFluxAverage
    variable = T
    boundary = right
    diffusivity = thermal_conductivity
  []
[]

[Outputs]
  exodus = true
[]
```

To add a gap between two bodies (legacy node-on-face), append a `[ThermalContact]` block — the action creates the `GapHeatTransfer` BC, the `GapConductance` material, and the `penetration` aux variable for you:

```hit
[ThermalContact]
  [gap]
    type = GapHeatTransfer
    variable = T
    primary  = right_of_left_body
    secondary = left_of_right_body
    emissivity_primary   = 0.8
    emissivity_secondary = 0.8
    gap_conductivity     = 0.025   # bulk gas (W/(m*K))
    quadrature           = true
  []
[]
```
