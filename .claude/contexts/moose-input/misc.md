# Authoring inputs: Misc & cross-cutting modules

Reach for this guide when a `.i` setup uses **niche / cross-cutting** input objects that don't justify a dedicated authoring file: thermo-diffusion (Soret), Arrhenius materials, generalized sensors, enclosed-volume postprocessors, fluid-property user-objects (`[FluidProperties]`), reactive-transport ODE kernels, level-set advection/reinitialization, scalar-transport Lagrange-multiplier (LM) kernels, or wiring an external PETSc solver. For mainstream physics see [kernels.md](./kernels.md), [bcs.md](./bcs.md), [solid-mechanics.md](./solid-mechanics.md), [heat-transfer.md](./heat-transfer.md), [contact.md](./contact.md). For C++-side authoring of misc objects, see `../moose/misc-authoring.md`.

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. Each entry cites the **source header** (`<file>:<line of class>`) and one **canonical example .i** (`<file>:<line of the sub-block>`).

## When to use this (vs alternatives)

Decide which top-level block first; then pick from the catalog.

1. Mass flux driven by `grad(T)` (Soret / thermophoresis): **`[Kernels]`** with `ThermoDiffusion` or `ADThermoDiffusion`. Always pair with a Fick's-law diffusion kernel — `CoefDiffusion`, `MatDiffusion`, or `ADMatDiffusion` — on the same variable. Without a regular diffusion partner the Soret term is unstable.
2. Sum-of-Arrhenius temperature dependence ($\sum_i D_{0,i} \exp(-Q_i/RT)$) for a material property: **`[Materials]`** with `ArrheniusMaterialProperty` / `ADArrheniusMaterialProperty`. Don't roll your own `ParsedMaterial` — the Arrhenius class also declares the temperature derivative `<name>_dT` which downstream kernels consume for Jacobians.
3. Sensor model (drift, noise, efficiency, delay, impulse-response) wrapping a `Postprocessor`: **`[Postprocessors]`** with `GeneralSensorPostprocessor` (impulse response from `R_function`) or `ThermocoupleSensorPostprocessor` (hard-coded first-order lag).
4. Volume of a closed cavity defined by a sideset (e.g. cavity-pressure couplings): **`[Postprocessors]`** with `InternalVolume`. Sign convention: interior surface = positive, exterior = negative; uses displaced mesh by default.
5. Equation-of-state for a fluid (gas, liquid, salt, water) consumed by a material or kernel: **`[FluidProperties]`** top-level block. The FP user-object is **passed by name** (`fp = my_water`) into a `FluidPropertiesMaterial*` or directly into navier-stokes/porous-flow inputs.
6. Reactive-transport ODE/PDE for a primary aqueous species: **`[Kernels]`** with `chemical_reactions` `PrimaryDiffusion` / `PrimaryTimeDerivative` / `PrimaryConvection`, plus `CoupledBEEquilibriumSub` etc. for secondary (equilibrium) species. Most users invoke these via the `[ReactionNetwork]` action — see `[Physics]` shorthand below.
7. Level-set transport / reinitialization on an FE field: **`[Kernels]`** with `level_set` `LevelSetAdvection` (transport) and `LevelSetOlssonReinitialization` (re-initialize signed-distance, typically inside a `LevelSetReinitializationProblem`).
8. Lagrange-multiplier-augmented scalar transport (NCP enforcement of bounds, LM-stabilized advection-diffusion): **`[Kernels]`** with `scalar_transport` `LMDiffusion`, `CoupledForceLM`, `LMTimeKernel`.
9. Wire a non-MOOSE PETSc solver into the multiapp tree: **`[Problem]`** of type `ExternalPETScProblem` (mesh `PETScDMDAMesh`, time-stepper `ExternalPetscTimeStepper`).

If the setup is heat-conduction-shaped, contact-shaped, solid-mechanics-shaped, optimization-shaped, stochastic-tools-shaped, or xfem-shaped — leave this file. Those each have their own dedicated guide.

## Catalog

### `[Kernels]` — misc Soret + reactive transport + level-set + LM scalar transport

##### `CoefDiffusion`
- Source: `modules/misc/include/kernels/CoefDiffusion.h:15`
- Example: `modules/combined/performance/simple_transient_diffusion/simple_transient_diffusion.i:16`
- Plain `coef * grad(u) . grad(test)` with `coef` as `Real` or `Function`. Exists as the Fick's-law partner for `ThermoDiffusion`. For new diffusion physics prefer framework `MatDiffusion` / `FunctionDiffusion`.
- Required: `variable`.
- Useful: `coef` (default 1), `function`.

##### `ThermoDiffusion`
- Source: `modules/misc/include/kernels/ThermoDiffusion.h:37`
- Example: `modules/misc/test/tests/kernels/thermo_diffusion/thermo_diffusion.i:46` (sub-block `[soret]`)
- Soret weak form `-div[ D C Q* / (R T^2) grad(T) ]`. Couples a temperature variable, reads `MaterialProperty<Real>` `mass_diffusivity` and `heat_of_transport` (default names — overridable). Off-diagonal Jacobian wrt `temp` is implemented.
- Required: `variable`, `temp`.
- Useful: `gas_constant` (default 8.3144621), `mass_diffusivity` / `heat_of_transport` property-name overrides.
- Always pair with a Fick's-law kernel (`CoefDiffusion`, `Diffusion`, `MatDiffusion`) on the same `variable`.

##### `ADThermoDiffusion`
- Source: `modules/misc/include/kernels/ADThermoDiffusion.h:14`
- Example: `modules/misc/test/tests/kernels/thermo_diffusion/ad_thermo_diffusion.i:46` (sub-block `[soret]`)
- AD twin using a single lumped `ADMaterialProperty<Real>` `soret_coefficient` (replaces the explicit $D Q^* / R T^2$ split). Use this in new code.
- Required: `variable`, `temperature`.
- Useful: `soret_coefficient` (property-name override).

##### `PrimaryDiffusion` / `PrimaryTimeDerivative` / `PrimaryConvection` (`chemical_reactions`)
- Source: `modules/chemical_reactions/include/kernels/PrimaryDiffusion.h:20`, `PrimaryTimeDerivative.h:20`, `PrimaryConvection.h:19`
- Example: `modules/chemical_reactions/test/tests/aqueous_equilibrium/2species_without_action.i:90` (TimeDerivative), `:94` (Diffusion), `:98` (Convection)
- Trio for the primary-species transport equation: `dC/dt + div(v C) - div(D grad C) = ...`. Couple secondary species through `CoupledBEEquilibriumSub` (`modules/chemical_reactions/include/kernels/CoupledBEEquilibriumSub.h:17`) and `CoupledDiffusionReactionSub`.
- Required (Convection): `variable`, `p` (pressure variable). Reads `MaterialProperty<Real>` `diffusivity` and `conductivity` (Darcy).

##### `LevelSetAdvection` / `LevelSetOlssonReinitialization` (`level_set`)
- Source: `modules/level_set/include/kernels/LevelSetAdvection.h:21`, `LevelSetOlssonReinitialization.h:18`
- Example: `modules/level_set/test/tests/reinitialization/parent.i:67` (advection); `modules/level_set/test/tests/reinitialization/reinit.i:38` (reinit)
- Advection: `psi_i v . grad(u)` with coupled vector `velocity` variables. Reinitialization: Olsson 2007 PDE, typically run inside a `LevelSetReinitializationProblem` sub-app.
- Required (Advection): `variable`, `velocity`.
- Required (Reinit): `variable`, `phi_0` (auxvariable carrying the level set at `tau=0`), `epsilon` (interface width).

##### `LMDiffusion` / `CoupledForceLM` / `LMTimeKernel` (`scalar_transport`)
- Source: `modules/scalar_transport/include/kernels/LMDiffusion.h:18`, `CoupledForceLM.h:17`, `LMKernel.h:19` (base)
- Example: `modules/scalar_transport/test/tests/ncp-lms/diagonal-ncp-lm-nodal-enforcement.i:96` (`LMDiffusion`), `:109` (`CoupledForceLM`)
- Add LM stabilization to a primal advection-diffusion, NCP bound enforcement on a coupled variable. Apply on the primal residual paired with a `[NodalKernels]` LM equation.
- Required: `variable` (primal), `lm_variable`. `LMDiffusion` reads `MaterialProperty<Real>` for the diffusivity.

### `[Materials]` — Arrhenius + misc helpers

##### `ArrheniusMaterialProperty` / `ADArrheniusMaterialProperty`
- Source: `modules/misc/include/materials/ArrheniusMaterialProperty.h:15`
- Example: `modules/misc/test/tests/ad_arrhenius_material_property/exact.i:31` (sub-block `[D]`); non-AD: `modules/misc/test/tests/arrhenius_material_property/exact.i`
- Templated `Material` declaring `<property_name>` and `<property_name>_dT`. Sums an arbitrary number of Arrhenius branches: $\sum_i D_{0,i} \exp(-Q_i / R T)$. Stateful (initialized at `initial_temperature`) so restarts are coherent.
- Required: `property_name`, `temperature`, `frequency_factor` (vector), `activation_energy` (vector). The two vectors must be the same length and non-empty.
- Useful: `gas_constant` (default `PhysicalConstants::ideal_gas_constant`), `initial_temperature`, `outputs`.

##### `Density` (deprecated, sunset 2025-12-31)
- Source: `modules/misc/include/materials/Density.h`
- Do not use in new inputs. For a deforming body use `solid_mechanics` `StrainAdjustedDensity`; otherwise `GenericConstantMaterial` / `ParsedMaterial`.

### `[Postprocessors]` — sensors, enclosed volumes

##### `InternalVolume`
- Source: `modules/misc/include/postprocessors/InternalVolume.h:25`
- Example: `modules/combined/test/tests/internal_volume/hex8.i:115` (sub-block `[internalVolume]`)
- Surface-integral evaluation of the volume enclosed by a sideset. Sign: interior surface positive, exterior negative — combine into one sideset to net out subtractions. Uses displaced mesh by default.
- Required: `boundary` (closed sideset).
- Useful: `component` (0..2, default 0), `scale_factor` (default 1), `addition` (FunctionName for time-dependent volume offsets — e.g. injected mass).

##### `GeneralSensorPostprocessor`
- Source: `modules/misc/include/postprocessors/GeneralSensorPostprocessor.h:20`
- Example: `modules/misc/test/tests/sensor_postprocessor/transient_general_sensor.i:63` (sub-block `[general_sensor_pp]`)
- Sensor wrapping an upstream `Postprocessor` (`input_signal`). Adds drift, efficiency, noise (seeded `MooseRandom`), uncertainty, delay, and a convolution-integral term weighted against the proportional output.
- Required: `input_signal` (PostprocessorName).
- Useful: `drift_function`, `efficiency_function`, `noise_std_dev_function`, `signalToNoise_function`, `delay_function`, `uncertainty_std_dev_function`, `R_function` (impulse response), `proportional_weight`, `integral_weight`, `seed`.

##### `ThermocoupleSensorPostprocessor`
- Source: `modules/misc/include/postprocessors/ThermocoupleSensorPostprocessor.h:18`
- Example: `modules/misc/test/tests/sensor_postprocessor/transient_thermocouple_sensor.i:63`
- Concrete subclass of `GeneralSensorPostprocessor` with first-order exponential lag $R(t-t')=e^{-(t-t')/\tau}/\tau$. Errors out if the user attempts to set `R_function`.
- Required: `input_signal`.
- Useful: same `*_function` parameters as the base, except `R_function`.

### `[AuxKernels]` — misc

##### `CoupledDirectionalMeshHeightInterpolation`
- Source: `modules/misc/include/auxkernels/CoupledDirectionalMeshHeightInterpolation.h:25`
- Example: `modules/misc/test/tests/coupled_directional_mesh_height_interpolation/coupled_directional_mesh_height_interpolation.i:42`
- Modulates a coupled scalar so that it ramps linearly from 0 at the negative-extreme end of the mesh to its full value at the positive-extreme end along a chosen axis. Useful for synthesizing a "stretch" displacement aux from a single magnitude.
- Required: `variable`, `coupled` (variable to modulate), `direction` (`x|y|z`).

### `[FluidProperties]` (top-level block, `fluid_properties` module)

The `[FluidProperties]` block hosts user-objects that implement equation-of-state queries (`p_from_v_e`, `T_from_p_h`, `mu_from_p_T`, …). They are not residual contributors — they are **passed by name** (`fp = my_air`) into a `FluidPropertiesMaterial*` (e.g. `FluidPropertiesMaterialVE`, `FluidPropertiesMaterialPT`) or directly into navier-stokes / porous-flow / thermal-hydraulics inputs. See `modules/fluid_properties/test/tests/ideal_gas/test.i` for the canonical FP→material→aux-output pattern.

##### `IdealGasFluidProperties`
- Source: `modules/fluid_properties/include/fluidproperties/IdealGasFluidProperties.h:22`
- Example: `modules/fluid_properties/test/tests/ideal_gas/test.i:111` (sub-block `[ideal_gas]`)
- Two-parameter ideal gas (gamma, molar_mass). Defaults are atmospheric air.
- Useful: `gamma`, `molar_mass`, `mu` (viscosity), `k` (conductivity).

##### `Water97FluidProperties`
- Source: `modules/fluid_properties/include/fluidproperties/Water97FluidProperties.h:38`
- Example: `modules/fluid_properties/test/tests/water/water.i:151`
- IAPWS-IF97 water/steam. Pure inputs are `(p, T)` with backwards equations in Region 3.
- No required parameters (it's purely a UO).

##### `SimpleFluidProperties`
- Source: `modules/fluid_properties/include/fluidproperties/SimpleFluidProperties.h:31`
- Example: `modules/navier_stokes/test/tests/postprocessors/rayleigh/natural_convection.i:180`
- Linearized incompressible-ish liquid: $\rho = \rho_0 \exp(P/K - \beta T)$, $e = c_v T$. Constants for `bulk_modulus`, `thermal_expansion`, `cp`, `cv`, `thermal_conductivity`, `viscosity`. Cheapest fluid for testing.

##### `FlibeFluidProperties`
- Source: `modules/fluid_properties/include/fluidproperties/FlibeFluidProperties.h:17`
- Example: `modules/navier_stokes/test/tests/finite_volume/wcns/channel-flow/2d-transient.i:243`
- LiF-BeF2 (FLiBe) molten salt. Hard-coded property correlations — no required parameters.

Other single-phase choices in the same directory: `HeliumFluidProperties`, `LeadFluidProperties`, `LeadBismuthFluidProperties`, `NaKFluidProperties`, `NitrogenFluidProperties`, `MethaneFluidProperties`, `CO2FluidProperties`, `HydrogenFluidProperties`, `StiffenedGasFluidProperties`, `TabulatedBicubicFluidProperties` (interpolate a CSV table). Two-phase: `TwoPhaseFluidProperties`, `StiffenedGasTwoPhaseFluidProperties`. For thermal-hydraulics-only `LinearFluidProperties` see `modules/thermal_hydraulics/include/fluidproperties/LinearFluidProperties.h`.

### `[Problem]` / `[Mesh]` / `[Executioner]` — external PETSc solver

##### `ExternalPETScProblem`
- Source: `modules/external_petsc_solver/include/problems/ExternalPETScProblem.h:22`
- Example: `modules/external_petsc_solver/test/tests/external_petsc_problem/petsc_transient_as_parent.i:13` (sub-block `[Problem]`)
- Plug a non-MOOSE PETSc solver (DMDA-based) under MOOSE's executioner so MOOSE can drive multi-app coupling, transfers, and output. Requires `PETScDMDAMesh` in `[Mesh]` and `ExternalPetscTimeStepper` (`modules/external_petsc_solver/include/timesteppers/ExternalPetscTimeStepper.h:15`) under `[Executioner]/[TimeStepper]`. The synced solution variable is declared in `[AuxVariables]` and named via `sync_variable`.

## Cross-cutting concerns

### Sub-module loading
- Each module's objects are registered into a per-module app — `MiscApp`, `ChemicalReactionsApp`, `FluidPropertiesApp`, `LevelSetApp`, `ScalarTransportApp`, `ExternalPetscSolverApp`. To use them in your input the corresponding library must be linked into your app (set `MISC := yes`, `CHEMICAL_REACTIONS := yes`, `FLUID_PROPERTIES := yes`, `LEVEL_SET := yes`, `SCALAR_TRANSPORT := yes`, `EXTERNAL_PETSC_SOLVER := yes` in the app's `Makefile`). The `combined` app (`modules/combined`) links every module — most stress / test inputs use that as their `app_type`.
- A few sub-modules also register their objects under a `[Modules/<name>]` action umbrella (e.g. `[Modules/FluidProperties]` is *not* used — `[FluidProperties]` is the top-level block; chemical_reactions exposes `[ReactionNetwork]` instead). When in doubt, look at the canonical test for the action syntax — don't guess.

### `[FluidProperties]` consumption pattern
- Always two steps. (a) Declare the FP user-object: `[FluidProperties][air] type = IdealGasFluidProperties; gamma = 1.4 [][]`. (b) Pass it by name into a consumer: a `FluidPropertiesMaterialVE` (`modules/fluid_properties/test/tests/ideal_gas/test.i:120`) or a navier-stokes / porous-flow input that takes `fp = air` directly.
- `FluidPropertiesMaterialVE` declares MaterialProperty<Real> outputs `pressure`, `temperature`, `cp`, `cv`, `c`, `mu`, `k`, `g` from `(v, e)` AuxVariables — pull them into `[AuxKernels]` via `MaterialRealAux` for output. Variants: `FluidPropertiesMaterialPT` from `(p, T)`, `FluidPropertiesMaterialPH` from `(p, h)`.
- The FP user-object is **stateless and thread-safe** — feel free to share one across multiple materials and kernels.

### `ThermoDiffusion` pairing
- Use `ADArrheniusMaterialProperty` (with `property_name = mass_diffusivity`) plus a parsed material for `heat_of_transport` to feed `ThermoDiffusion`. For the AD twin, write a single AD parsed material that produces `soret_coefficient`. The off-diagonal Jacobian for the temperature coupling is wired internally — you do *not* need to add `temp` to a `coupled_variables` list for AD.

### When to escalate to a dedicated module guide
- If your input grows beyond two `chemical_reactions` kernels and a couple of materials, switch to the `[ReactionNetwork]` action (`modules/chemical_reactions/include/actions`) — see the `*_physics.i` examples (e.g. `modules/chemical_reactions/test/tests/aqueous_equilibrium/co2_h2o_physics.i`).
- If your level-set setup is doing both transport and reinitialization with terminator UOs and SUPG stabilization, you want the multi-app pattern in `modules/level_set/test/tests/reinitialization/parent.i` — single-app inputs miss the reinit sub-app entirely.
- For thermal-hydraulics fluid pipes/junctions, leave `[FluidProperties]` and switch to thermal-hydraulics `[Components]`.

## Minimal scaffold

Steady 1-D thermo-diffusion (Soret) with the AD twin. The Fick's-law partner is `ADDiffusion`; `soret_coefficient` is supplied via `ADParsedMaterial`:

```hit
[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 100
[]

[Variables]
  [u]
    initial_condition = 1
  []
  [temp]
    initial_condition = 1
  []
[]

[Kernels]
  [diffC]
    type = ADDiffusion       # Fick's law partner — REQUIRED
    variable = u
  []
  [soret]
    type = ADThermoDiffusion
    variable = u
    temperature = temp
  []
  [diffT]
    type = ADDiffusion
    variable = temp
  []
[]

[Materials]
  [soret_coef]
    type = ADParsedMaterial
    property_name = soret_coefficient
    coupled_variables = 'temp u'
    expression = 'u / (temp * temp)'   # D Q* / (R T^2), with D=Q*/R=1
  []
[]

[BCs]
  [u_left]
    type = DirichletBC
    variable = u
    boundary = left
    value = 1
  []
  [t_left]
    type = DirichletBC
    variable = temp
    boundary = left
    value = 1
  []
  [t_right]
    type = DirichletBC
    variable = temp
    boundary = right
    value = 2
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
[]

[Outputs]
  exodus = true
[]
```

An `InternalVolume` postprocessor on a closed cavity with a time-dependent additive correction (e.g. injected gas):

```hit
[Functions]
  [injected_volume]
    type = PiecewiseLinear
    x = '0 1 2 3'
    y = '0 3 7 -3'
  []
[]

[Postprocessors]
  [cavity_volume]
    type = InternalVolume
    boundary = cavity_sideset    # closed sideset around the cavity
    component = 0
    scale_factor = 1.0
    addition = injected_volume
    execute_on = 'initial timestep_end'
  []
[]
```

A minimal `[FluidProperties]` block driving an `IdealGasFluidProperties` user-object into a `FluidPropertiesMaterialVE` for property output:

```hit
[FluidProperties]
  [air]
    type = IdealGasFluidProperties
    gamma = 1.4
    molar_mass = 0.029
  []
[]

[AuxVariables]
  [e]
    initial_condition = 6232.5
  []
  [v]
    initial_condition = 0.02493
  []
[]

[Materials]
  [fp_mat]
    type = FluidPropertiesMaterialVE
    e = e
    v = v
    fp = air                  # pass FP UO by name
  []
[]

# downstream: [AuxKernels] with MaterialRealAux pulls 'pressure', 'temperature', etc.
```
