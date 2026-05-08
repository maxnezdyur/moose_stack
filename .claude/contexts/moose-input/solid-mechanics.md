# Authoring inputs: Solid Mechanics

Reach for this guide when you need to assemble a `.i` file for a continuum solid — displacements + strain + stress + mechanical BCs + per-component output. SM input is spread across `[Physics/SolidMechanics/...]`, `[Variables]`, `[Kernels]`, `[BCs]`, `[Materials]`, `[AuxKernels]`, `[Postprocessors]`. Each catalog entry cites a **source header** (`<file>:<class line>`) and one **canonical example .i** under `modules/solid_mechanics/test/tests/...`. AD twins (`ADFoo`) live in the same header — same params. If you're writing a new C++ class, see `../moose/solid-mechanics-authoring.md`. For kernel mechanics, see [kernels.md](./kernels.md).

## When to use this (vs alternatives)

Decide **action vs hand-rolled**, then **strain measure**, then **AD vs non-AD**, then **stress chain**.

1. **Action shorthand** (default): `[Physics/SolidMechanics/QuasiStatic/<name>]` (static) or `[Physics/SolidMechanics/Dynamic/<name>]` (Newmark / HHT). The action expands to displacement variables (with `add_variables = true`), `StressDivergenceTensors`-family kernels, the strain calculator, and output AuxKernels in one block.
2. **Hand-rolled `[Variables]` + `[Kernels]` + `[Materials]`**: when you need fine control — overlapping subdomains with different chains, custom Jacobian wiring, multi-`base_name` partitions. The half-step `[Kernels]/SolidMechanics` (`CommonSolidMechanicsAction`) auto-wires kernels only.
3. **Strain measure**: `SMALL` (linear, total) for elasticity; `FINITE` (large-deformation, incremental) for plasticity / hyperelasticity / large rotations; `SMALL` + `incremental = true` for small-strain plasticity. Mismatching the strain calculator and stress material (`ComputeSmallStrain` + `ComputeFiniteStrainElasticStress`) compiles but produces wrong stress.
4. **AD vs non-AD**: prefer `AD*` for new inputs. The whole chain must agree — `ADComputeIsotropicElasticityTensor` -> `ADComputeSmallStrain` -> `ADComputeLinearElasticStress` -> `ADStressDivergenceTensors`. The Physics action threads AD via `use_automatic_differentiation = true`.
5. **Multi-physics (per-phase / per-grain)**: thread `base_name` through every SM material AND the kernel; the action exposes `base_name` and `strain_base_name`.

For non-stress-divergence volumetric residuals (heat source, body force, custom coupling), see [kernels.md](./kernels.md). For non-mechanical BCs, use framework BCs.

## Catalog

### `[Physics/SolidMechanics/QuasiStatic/<name>]` — quasi-static action

##### `QuasiStaticSolidMechanicsPhysics`
- Source: `modules/solid_mechanics/include/physics/QuasiStaticSolidMechanicsPhysics.h:15` (extends `QuasiStaticSolidMechanicsPhysicsBase` at `modules/solid_mechanics/include/physics/QuasiStaticSolidMechanicsPhysicsBase.h:15`)
- Example: `modules/solid_mechanics/test/tests/ad_simple_linear/linear-hand-coded.i:13` (sub-block `[Physics/SolidMechanics/QuasiStatic/all]`); finite + planar: `modules/solid_mechanics/test/tests/2D_geometries/finite_planestrain.i:15`; eigenstrain wiring: `modules/solid_mechanics/test/tests/ad_linear_elasticity/thermal_expansion.i:19`.
- Sets up `[Variables]` (when `add_variables = true`), the `StressDivergenceTensors`-family kernels, the matching strain calculator, and (when `generate_output` is set) `RankTwoAux`/`RankTwoScalarAux` AuxKernels.
- Required: `displacements` (typically supplied via `[GlobalParams]`).
- Useful: `strain` (`SMALL|FINITE`), `incremental` (default true for FINITE), `add_variables`, `eigenstrain_names`, `automatic_eigenstrain_names`, `temperature`, `base_name`, `strain_base_name`, `use_automatic_differentiation`, `use_displaced_mesh`, `use_finite_deform_jacobian`, `volumetric_locking_correction`, `extra_vector_tags`, `block`, `decomposition_method` (`TaylorExpansion|EigenSolution|HughesWinget`), `generate_output`, `material_output_order`, `material_output_family`, `planar_formulation` (`NONE|WEAK_PLANE_STRESS|PLANE_STRAIN|GENERALIZED_PLANE_STRAIN`), `out_of_plane_strain`, `scalar_out_of_plane_strain`, `out_of_plane_pressure_function`, `global_strain`.

### `[Physics/SolidMechanics/Dynamic/<name>]` — dynamic action

##### `DynamicSolidMechanicsPhysics`
- Source: `modules/solid_mechanics/include/physics/DynamicSolidMechanicsPhysics.h:14` (extends `QuasiStaticSolidMechanicsPhysics`)
- Example: `modules/solid_mechanics/test/tests/dynamics/dynamic_physics/dynamic_physics_2d_planar.i:25` (sub-block `[Physics/SolidMechanics/Dynamic/all]`).
- Same as the quasi-static action plus inertial-force kernels and (when `vel_*`/`accel_*` aux variables are present) Newmark integration AuxKernels. Adds Rayleigh damping when either coefficient is set.
- All quasi-static params, plus: `newmark_beta` (default 0.25), `newmark_gamma` (default 0.5), `hht_alpha` (default 0), `mass_damping_coefficient` (Rayleigh-eta, MaterialPropertyName), `stiffness_damping_coefficient` (Rayleigh-zeta), `density` (default `density`), `velocities`, `accelerations`, `static_initialization`.

### `[Kernels]` — solid-mechanics residuals

##### `StressDivergenceTensors` / `ADStressDivergenceTensors`
- Source: `modules/solid_mechanics/include/kernels/StressDivergenceTensors.h:24` / `modules/solid_mechanics/include/kernels/ADStressDivergenceTensors.h:19`
- Example: `modules/solid_mechanics/test/tests/ad_simple_linear/linear-ad.i:27` (sub-block `[stress_x]`)
- `div(sigma)` in Cartesian coords — one kernel per displacement component (`component = 0,1,2`). Almost always invoked via the Physics action.
- Required: `variable`, `component`, `displacements`.
- Useful: `temperature`, `eigenstrain_names`, `base_name`, `volumetric_locking_correction`, `use_finite_deform_jacobian` (non-AD), `extra_vector_tags`.

##### `StressDivergenceRZTensors` / `ADStressDivergenceRZTensors` / `StressDivergenceRSphericalTensors` / `ADStressDivergenceRSphericalTensors`
- Source: `modules/solid_mechanics/include/kernels/StressDivergenceRZTensors.h` / `StressDivergenceRSphericalTensors.h`
- Example: `modules/solid_mechanics/test/tests/2D_geometries/2D-RZ_test.i` (search `type = StressDivergenceRZTensors`)
- Axisymmetric (RZ): `component = 0` (radial), `component = 1` (axial). Spherical: `component = 0` only. Same params as Cartesian.

##### `InertialForce` / `ADInertialForce`
- Source: `modules/solid_mechanics/include/kernels/InertialForce.h:24`
- Example: `modules/solid_mechanics/test/tests/dynamics/wave_1D/wave_rayleigh_newmark.i:70` (sub-block `[inertia_x]`)
- `M * accel` plus mass-Rayleigh damping. Driven by Newmark `accel`/`vel` aux vars — do NOT pair with a TimeDerivative kernel on displacement.
- Required: `variable`.
- Useful: `velocity`, `acceleration` (AuxVariableNames), `beta`, `gamma`, `eta` (mass Rayleigh), `alpha` (HHT), `density` (default `density`).

##### `Gravity` / `ADGravity`
- Source: `modules/solid_mechanics/include/kernels/Gravity.h:21`
- Example: `modules/solid_mechanics/test/tests/gravity/gravity_test.i:28` (sub-block `[gravity_y]`)
- Body force `-rho * g * psi`. One kernel per direction.
- Required: `variable`, `value` (signed gravity component).
- Useful: `density` (default `density`), `function`, `alpha` (HHT).

##### `WeakPlaneStress` / `ADWeakPlaneStress`
- Source: `modules/solid_mechanics/include/kernels/WeakPlaneStress.h:17` / `ADWeakPlaneStress.h:17`
- Weak-form residual on the auxiliary out-of-plane strain variable used by `planar_formulation = WEAK_PLANE_STRESS`. Almost always added by the Physics action.
- Required: `variable` (the out-of-plane strain scalar).
- Useful: `out_of_plane_stress_variable`, `temperature`, `eigenstrain_names`, `base_name`.

##### `MaterialVectorBodyForce` / `PoroMechanicsCoupling`
- Source: `modules/solid_mechanics/include/kernels/MaterialVectorBodyForce.h:19` / `PoroMechanicsCoupling.h`
- `MaterialVectorBodyForce`: body force whose magnitude per component is set by a vector material property (spatially-varying gravity). Required: `variable`, `component`, `body_force` (RealVectorValue MaterialPropertyName).
- `PoroMechanicsCoupling`: Biot pore-pressure coupling `-alpha * grad(p)`. Required: `variable`, `component`, `porepressure`. Useful: `coefficient` (default `biot_coefficient`).

### `[BCs]` — mechanical boundary conditions

##### `Pressure` / `ADPressure`
- Source: `modules/solid_mechanics/include/bcs/Pressure.h:26`
- Example: `modules/solid_mechanics/test/tests/pressure/pressure_test.i:79` (sub-block `[Pressure]/[Side1]`); AD: `modules/solid_mechanics/test/tests/ad_pressure/pressure_test.i:80`
- Pressure normal load. Most users invoke the **Pressure action** sub-block which expands to one `Pressure` BC per displacement component automatically.
- Required (BC form): `variable`, `boundary`, `component`. (Action form: `boundary` + `factor`/`function` + `displacements`.)
- Useful: `factor`, `function`, `use_automatic_differentiation` (action sub-block).

##### `CoupledPressureBC` / `DisplacementAboutAxis` / `PenaltyInclinedNoDisplacementBC` (+ AD twin)
- Source: `modules/solid_mechanics/include/bcs/CoupledPressureBC.h:19` / `DisplacementAboutAxis.h:26` / `PenaltyInclinedNoDisplacementBC.h:26`
- Example: `modules/solid_mechanics/test/tests/coupled_pressure/coupled_pressure_test.i:118` (CoupledPressure); `modules/solid_mechanics/test/tests/cohesive_zone_model/stretch_rotate_large_deformation.i:90` (DisplacementAboutAxis).
- `CoupledPressureBC`: pressure whose magnitude is a coupled FE/aux variable (sub-app fluid pressure). Required: `variable`, `boundary`, `component`, `pressure`.
- `DisplacementAboutAxis`: rigid rotation about a user axis on a sideset (twist tests, hinged ends). Required: `variable`, `boundary`, `component`, `function`, `angle_units`, `axis_origin`, `axis_direction`.
- `PenaltyInclinedNoDisplacementBC`: penalty enforcement of zero normal displacement on an inclined sideset. The companion action `[BCs/InclinedNoDisplacementBC]` expands to one BC per displacement component. Required: `variable`, `boundary`, `component`, `penalty`, `displacements`.

##### `PresetDisplacement`
- Source: `modules/solid_mechanics/include/bcs/PresetDisplacement.h:22`
- Example: `modules/solid_mechanics/test/tests/dynamics/prescribed_displacement/3D_QStatic_1_Ramped_Displacement.i:228`
- Sets nodal displacement and self-consistently updates Newmark `vel_*` / `accel_*`. Use instead of `DirichletBC` on dynamics problems.
- Required: `variable`, `boundary`, `function`, `velocity`, `acceleration`, `beta`.

##### `PresetVelocity` / `PresetAcceleration`
- Source: `modules/solid_mechanics/include/bcs/PresetVelocity.h:14` / `PresetAcceleration.h:20`
- Example: `modules/solid_mechanics/test/tests/smeared_cracking/cracking_xyz.i:56` (velocity); `modules/solid_mechanics/test/tests/dynamics/acceleration_bc/AccelerationBC_test.i:191` (acceleration).
- Prescribed nodal velocity / acceleration on a sideset (integrates to displacement via Newmark for the acceleration form). Required: `variable`, `boundary`, `function` (+ `velocity`, `acceleration`, `beta` for `PresetAcceleration`).

##### `Torque` / `ADTorque`
- Source: `modules/solid_mechanics/include/bcs/Torque.h:25`
- Integrated moment about a user axis on a sideset; per displacement component.
- Required: `variable`, `boundary`, `component`, `moment`, `axis_origin`, `axis_direction`.
- Useful: `factor`, `polar_moment_of_inertia` (PostprocessorName).

##### `StickyBC` / `DashpotBC`
- Source: `modules/solid_mechanics/include/bcs/StickyBC.h:19` / `DashpotBC.h`
- Example: `modules/solid_mechanics/test/tests/stickyBC/push_down.i:33` (StickyBC).
- `StickyBC`: pins displacement at its current value once a threshold is exceeded (one-shot contact / collapse). Required: `variable`, `boundary`, `min_value` or `max_value`.
- `DashpotBC`: linear viscous traction `c * du/dt . n` (radiation / absorbing boundary). Required: `variable`, `boundary`, `component`, `coefficient`, `disp_x`, `disp_y`, optionally `disp_z`.

### `[Materials]` — elasticity, strain, stress, eigenstrain

#### Elasticity tensors

##### `ComputeIsotropicElasticityTensor` / `ADComputeIsotropicElasticityTensor`
- Source: `modules/solid_mechanics/include/materials/ComputeIsotropicElasticityTensor.h:19`
- Example: `modules/solid_mechanics/test/tests/ad_simple_linear/linear-ad.i:73` (sub-block `[elasticity]`)
- Constant isotropic stiffness from any two of `youngs_modulus`/`poissons_ratio`/`bulk_modulus`/`shear_modulus`/`lambda`. Outputs `_elasticity_tensor`.
- Required: any two moduli (most common: `youngs_modulus + poissons_ratio`).
- Useful: `base_name`, `block`.

##### `ComputeElasticityTensor` / `ADComputeElasticityTensor`
- Source: `modules/solid_mechanics/include/materials/ComputeElasticityTensor.h:18`
- Example: `modules/solid_mechanics/test/tests/ad_pressure/pressure_test.i:104` (sub-block `[Elasticity_tensor]`)
- General elasticity tensor from a `fill_method` enum + flat `C_ijkl` vector. Use for orthotropic / fully anisotropic stiffness.
- Required: `C_ijkl`, `fill_method` (`antisymmetric|symmetric9|symmetric21|general_isotropic|symmetric_isotropic|symmetric_isotropic_E_nu|antisymmetric_isotropic|axisymmetric_rz|general|principal|orthotropic`).
- Useful: `euler_angle_1/2/3` (rotate stiffness into a material frame), `base_name`, `block`.

##### `ComputeVariableIsotropicElasticityTensor` / `CompositeElasticityTensor`
- Source: `modules/solid_mechanics/include/materials/ComputeVariableIsotropicElasticityTensor.h:19` / `CompositeElasticityTensor.h`
- Example: `modules/solid_mechanics/test/tests/j_integral_vtest/j_int_fgm_sif.i:116` (variable-isotropic).
- `ComputeVariableIsotropicElasticityTensor`: isotropic stiffness whose `youngs_modulus` / `poissons_ratio` are coupled material properties (FGMs, damage-coupled stiffness). Required: `youngs_modulus`, `poissons_ratio` (both MaterialPropertyName), `args`.
- `CompositeElasticityTensor`: combines several elasticity tensors by weight functions (phase-field, multi-phase). Required: `tensors`, `weights`, `args`.

#### Strain calculators (pick one; match to the stress chain)

##### `ComputeSmallStrain` / `ADComputeSmallStrain`
- Source: `modules/solid_mechanics/include/materials/ComputeSmallStrain.h:17`
- Example: `modules/solid_mechanics/test/tests/ad_simple_linear/linear-ad.i:80` (sub-block `[strain]`)
- Total small-strain (`epsilon = sym(grad u)`). Pair with `ComputeLinearElasticStress`. Subtracts every entry in `eigenstrain_names`.
- Required: `displacements` (typically via `[GlobalParams]`).
- Useful: `eigenstrain_names`, `base_name`, `volumetric_locking_correction`, `global_strain`.

##### `ComputeIncrementalSmallStrain` / `ADComputeIncrementalSmallStrain`
- Source: `modules/solid_mechanics/include/materials/ComputeIncrementalStrain.h:18`
- Example: `modules/solid_mechanics/test/tests/recompute_radial_return/isotropic_plasticity_incremental_strain.i` (search `type = ComputeIncrementalSmallStrain`)
- Small strain in incremental form (`_strain_increment` published). Pair with `ComputeMultipleInelasticStress` for small-strain plasticity.
- Required: `displacements`. Useful: `eigenstrain_names`, `base_name`.

##### `ComputeFiniteStrain` / `ADComputeFiniteStrain`
- Source: `modules/solid_mechanics/include/materials/ComputeFiniteStrain.h:18`
- Example: `modules/solid_mechanics/test/tests/ad_elastic/finite_elastic.i` (search `type = ADComputeFiniteStrain`)
- Large-deformation incremental strain via Taylor / EigenSolution / HughesWinget polar decomposition. Pair with `ComputeFiniteStrainElasticStress` or `ComputeMultipleInelasticStress`.
- Required: `displacements`.
- Useful: `eigenstrain_names`, `base_name`, `decomposition_method`, `volumetric_locking_correction`.

##### `ComputeGreenLagrangeStrain` / `ADComputeGreenLagrangeStrain`
- Source: `modules/solid_mechanics/include/materials/ComputeGreenLagrangeStrain.h`
- Example: `modules/solid_mechanics/test/tests/ad_elastic/green-lagrange.i`
- Total Lagrangian Green-Lagrange strain. Pair with a stress material that consumes `_total_strain` (hyperelastic).

##### `ComputePlane{Small|Incremental|Finite}Strain` / `ComputeAxisymmetricRZ{Small|Incremental|Finite}Strain` / `ComputeRSpherical{Small|Incremental|Finite}Strain`
- Source: `modules/solid_mechanics/include/materials/ComputePlaneSmallStrain.h:20` / `ComputePlaneFiniteStrain.h:19` / `ComputeAxisymmetricRZSmallStrain.h:18` / `ComputeAxisymmetricRZFiniteStrain.h:19` / `ComputeRSphericalSmallStrain.h`
- Example: `modules/solid_mechanics/test/tests/generalized_plane_strain/generalized_plane_strain_squares.i:225` (plane); `modules/solid_mechanics/test/tests/ad_elastic/rz_small_elastic.i` (RZ).
- Coord-system specializations. Pair with the matching `StressDivergence*Tensors` kernel and `[Mesh]/coord_type = RZ` or `RSPHERICAL`. Plane variants accept `out_of_plane_strain` (weak-plane-stress) or `scalar_out_of_plane_strain` (generalized-plane-strain).

#### Stress materials (pick one; match the strain calculator)

##### `ComputeLinearElasticStress` / `ADComputeLinearElasticStress`
- Source: `modules/solid_mechanics/include/materials/ComputeLinearElasticStress.h:17`
- Example: `modules/solid_mechanics/test/tests/ad_simple_linear/linear-ad.i:83` (sub-block `[stress]`)
- `sigma = C : eps_mech` (total-strain Hooke). Use with `ComputeSmallStrain` ONLY.
- Required: nothing (consumes `_elasticity_tensor`, `_mechanical_strain`). Useful: `base_name`.

##### `ComputeFiniteStrainElasticStress` / `ADComputeFiniteStrainElasticStress`
- Source: `modules/solid_mechanics/include/materials/ComputeFiniteStrainElasticStress.h:19`
- Example: `modules/solid_mechanics/test/tests/2D_geometries/finite_planestrain.i:53` (sub-block `[elastic_stress]`)
- Incremental Cauchy stress integrated through the finite-strain rotation. Use with `ComputeFiniteStrain` or any incremental strain calculator.
- Required: nothing. Useful: `base_name`.

##### `ComputeMultipleInelasticStress` / `ADComputeMultipleInelasticStress`
- Source: `modules/solid_mechanics/include/materials/ComputeMultipleInelasticStress.h:30`
- Example: `modules/solid_mechanics/test/tests/recompute_radial_return/isotropic_plasticity_incremental_strain.i:91` (sub-block `[radial_return_stress]`)
- Driver for plasticity / creep / damage. Takes a list of `inelastic_models` (`StressUpdateBase` materials) and applies them in series — concurrent fixed-point or alternating (`cycle_models = true`).
- Required: `inelastic_models` (list of MaterialNames).
- Useful: `tangent_operator` (`elastic|nonlinear`), `max_iterations`, `relative_tolerance`, `absolute_tolerance`, `cycle_models`, `combined_inelastic_strain_weights`, `damage_model`, `base_name`.

##### `ComputeMultiPlasticityStress`
- Source: `modules/solid_mechanics/include/materials/ComputeMultiPlasticityStress.h:25`
- Example: `modules/solid_mechanics/test/tests/weak_plane_shear/small_deform_harden1.i:150`
- Alternative plasticity driver consuming a list of `SolidMechanicsPlasticModel` UserObjects (Mohr-Coulomb, Drucker-Prager, weak-plane). Heavier setup but lets multiple yield surfaces interact via closest-point projection.
- Required: `plastic_models` (UserObjectNames).
- Useful: `max_NR_iterations`, `tangent_operator`, `min_stepsize`, `deactivation_scheme`.

##### `ComputeLinearViscoelasticStress`
- Source: `modules/solid_mechanics/include/materials/ComputeLinearViscoelasticStress.h`
- Example: `modules/solid_mechanics/test/tests/visco/visco_small_strain.i:110`
- Linear viscoelasticity. Pair with `ComputeSmallStrain`, a `LinearViscoelasticityBase` model, and a `LinearViscoelasticityManager` UserObject.

#### Eigenstrains (subtracted by the strain calculator via `eigenstrain_names`)

##### `ComputeEigenstrain` / `ADComputeEigenstrain`
- Source: `modules/solid_mechanics/include/materials/ComputeEigenstrain.h`
- Example: `modules/solid_mechanics/test/tests/ad_linear_elasticity/thermal_expansion.i:36`
- Constant eigenstrain (six entries, Voigt order via `eigen_base`).
- Required: `eigenstrain_name`, `eigen_base`. Useful: `prefactor` (Function or MaterialPropertyName), `base_name`.

##### `ComputeVariableEigenstrain`
- Source: `modules/solid_mechanics/include/materials/ComputeVariableEigenstrain.h:19`
- Example: `modules/combined/test/tests/eigenstrain/variable.i:94`
- Eigenstrain `eigen_base * prefactor(args)` with a derivative-aware prefactor (chemical-strain / phase-field).
- Required: `eigen_base`, `prefactor` (MaterialPropertyName), `args`, `eigenstrain_name`.

##### `ComputeVolumetricEigenstrain` / `ADComputeVolumetricEigenstrain`
- Source: `modules/solid_mechanics/include/materials/ComputeVolumetricEigenstrain.h`
- Diagonal volumetric eigenstrain whose magnitude is a (functor) material property — swelling, irradiation growth.
- Required: `eigenstrain_name`, `volumetric_materials`.

##### `ComputeThermalExpansionEigenstrain` / `ComputeMeanThermalExpansionFunctionEigenstrain` / `ComputeDilatationThermalExpansionFunctionEigenstrain` (each + AD twin)
- Source: `modules/solid_mechanics/include/materials/ComputeThermalExpansionEigenstrain.h:19` / `ComputeMeanThermalExpansionFunctionEigenstrain.h:19` / `ComputeDilatationThermalExpansionFunctionEigenstrain.h:19`
- Example: `modules/solid_mechanics/test/tests/radial_disp_aux/cylinder_2d_axisymmetric.i:84` (constant-alpha); `modules/solid_mechanics/test/tests/thermal_expansion_function/small_const.i:85` (mean-alpha-from-Function); `modules/solid_mechanics/test/tests/thermal_expansion_function/dilatation.i:71` (dL/L Function).
- Three flavours of thermal expansion: constant `alpha * (T - T_ref) * I`; mean-secant `alpha_bar(T)` via Function (tabulated nuclear data); tabulated dilatation `dL/L(T)` via Function.
- Required (all): `eigenstrain_name`, `temperature`, `stress_free_temperature`, plus `thermal_expansion_coeff` (constant) OR `thermal_expansion_function` + `thermal_expansion_function_reference_temperature` (mean) OR `dilatation_function` (dilatation).

#### Return-mapping models (consumed by `ComputeMultipleInelasticStress`)

These materials are NOT used as `_stress` producers — they are listed under `inelastic_models` of `ComputeMultipleInelasticStress`. They inherit `RadialReturnStressUpdate` (J2 isotropic radial-return) or `StressUpdateBase` directly.

##### `IsotropicPlasticityStressUpdate` / `ADIsotropicPlasticityStressUpdate`
- Source: `modules/solid_mechanics/include/materials/IsotropicPlasticityStressUpdate.h:33`
- Example: `modules/solid_mechanics/test/tests/recompute_radial_return/isotropic_plasticity_incremental_strain.i:86`
- J2 plasticity with linear isotropic hardening (`yield_stress + hardening_constant * eqv_plastic_strain`) or a hardening function.
- Required: `yield_stress` OR `yield_stress_function`; `hardening_constant` OR `hardening_function`.
- Useful: `relative_tolerance`, `absolute_tolerance`, `max_inelastic_increment`, `internal_solve_full_iteration_history`, `base_name`.

##### `PowerLawCreepStressUpdate` / `ADPowerLawCreepStressUpdate`
- Source: `modules/solid_mechanics/include/materials/PowerLawCreepStressUpdate.h:25`
- Example: `modules/solid_mechanics/test/tests/ad_return_mapping/ad_return_mapping_derivative.i:78`
- Norton power-law creep `eps_dot = A * sigma^n * exp(-Q/RT)` (Arrhenius optional).
- Required: `coefficient`, `n_exponent`.
- Useful: `activation_energy`, `gas_constant`, `temperature`, `start_time`, `relative_tolerance`, `max_inelastic_increment`.

##### `LinearViscoelasticStressUpdate`
- Source: `modules/solid_mechanics/include/materials/LinearViscoelasticStressUpdate.h:25`
- Example: `modules/solid_mechanics/test/tests/visco/gen_maxwell_relax.i:115`
- Linear viscoelastic update used as an inelastic model inside `ComputeMultipleInelasticStress` (when stacking viscoelasticity with plasticity).

##### `IsotropicPowerLawHardeningStressUpdate` / `Hill{Creep|Plasticity}StressUpdate` / `TemperatureDependentHardeningStressUpdate`
- Source: `modules/solid_mechanics/include/materials/IsotropicPowerLawHardeningStressUpdate.h` / `HillCreepStressUpdate.h` / `HillPlasticityStressUpdate.h` / `TemperatureDependentHardeningStressUpdate.h`
- `IsotropicPowerLawHardening...`: J2 plasticity with `sigma_y = K * (eps_p)^n`. `Hill*`: anisotropic creep / plasticity using Hill's quadratic yield (pair with `HillConstants`). `TemperatureDependentHardening...`: J2 with hardening curves tabulated at multiple temperatures.

### `[AuxKernels]` — output stress / strain components

##### `RankTwoAux` / `ADRankTwoAux`
- Source: `modules/solid_mechanics/include/auxkernels/RankTwoAux.h:22`
- Example: `modules/solid_mechanics/test/tests/visco/visco_small_strain.i:49` (sub-block `[stress_xx]`)
- One Cartesian component `(i,j)` of any RankTwoTensor material property (`stress`, `total_strain`, `mechanical_strain`, `creep_strain`, `plastic_strain`, `eigenstrain`).
- Required: `variable`, `rank_two_tensor`, `index_i`, `index_j`. Useful: `selected_qp`, `execute_on`.

##### `RankFourAux` / `ADRankFourAux`
- Source: `modules/solid_mechanics/include/auxkernels/RankFourAux.h:21`
- Example: `modules/solid_mechanics/test/tests/elasticitytensor/composite.i:93`
- One component `(i,j,k,l)` of a RankFourTensor (e.g. `_elasticity_tensor`).
- Required: `variable`, `rank_four_tensor`, `index_i`, `index_j`, `index_k`, `index_l`.

##### `RankTwoScalarAux` / `ADRankTwoScalarAux`
- Source: `modules/solid_mechanics/include/auxscalarkernels/RankTwoScalarAux.h:20`
- Example: `modules/solid_mechanics/test/tests/recompute_radial_return/affine_plasticity.i:209` (sub-block `[vonmises]`)
- Derived scalar from a RankTwoTensor: `vonmisesStress`, `effectiveStrain`, `hydrostatic`, `MaxPrincipal`, `MinPrincipal`, `firstInvariant`, `secondInvariant`, `thirdInvariant`, `volumetricStrain`, `triaxialityStress`.
- Required: `variable`, `rank_two_tensor`, `scalar_type`. Useful: `selected_qp`, `point1`, `point2`.

##### `MaterialRankTwoTensorAux` / `ADMaterialRankTwoTensorAux`
- Source: `framework/include/auxkernels/MaterialRankTwoTensorAux.h:23`
- Example: `modules/solid_mechanics/test/tests/notched_plastic_block/cmc_planar.i:172`
- Like `RankTwoAux` but bypasses nodal patch recovery (used by Physics-action automatic material output).
- Required: `variable`, `property`, `i`, `j`.

##### `CylindricalRankTwoAux` / `NewmarkAccelAux` / `NewmarkVelAux` / `AccumulateAux` / `ElasticEnergyAux`
- Source: `modules/solid_mechanics/include/auxkernels/CylindricalRankTwoAux.h` / `NewmarkAccelAux.h:14` / `NewmarkVelAux.h:14` / `AccumulateAux.h:19` / `ElasticEnergyAux.h`
- `CylindricalRankTwoAux`: component of stress/strain in a cylindrical (r, theta, z) frame; required `variable`, `rank_two_tensor`, `index_i`, `index_j`, `cylindrical_axis_point1`, `cylindrical_axis_point2`.
- `NewmarkAccelAux` / `NewmarkVelAux`: update Newmark `accel`/`vel` aux variables from displacement each step (required with `InertialForce` / `PresetDisplacement` when not on a dynamics-aware time integrator).
- `AccumulateAux`: `u += accumulate_from_variable * dt` (total dose, accumulated damage).
- `ElasticEnergyAux`: `0.5 * sigma : eps` per element.

### `[Postprocessors]` — integrals / scalars

##### `MaterialTensorIntegral` / `ADMaterialTensorIntegral`
- Source: `modules/solid_mechanics/include/postprocessors/MaterialTensorIntegral.h:20`
- Example: `modules/solid_mechanics/test/tests/generalized_plane_strain/plane_strain.i:88` (sub-block `[react_z]`)
- Volume integral of one component `(i,j)` of a RankTwoTensor material property.
- Required: `rank_two_tensor`, `index_i`, `index_j`. Useful: `block`.

##### `MaterialTensorAverage` / `ADMaterialTensorAverage`
- Source: `modules/solid_mechanics/include/postprocessors/MaterialTensorAverage.h:19`
- Volume-averaged component (integral / volume).

##### `SidesetReaction` / `ADSidesetReaction`
- Source: `modules/solid_mechanics/include/postprocessors/SidesetReaction.h:19`
- Example: `modules/solid_mechanics/test/tests/postprocessors/sideset_reaction/sideset_reaction.i:21`
- Net reaction force on a sideset by integrating `sigma . n . direction`. Pair with `[Problem]/extra_tag_vectors` for a residual-tagged reaction.
- Required: `boundary`, `direction`, `stress_tensor` (default `stress`).

##### `Mass` / `MaterialTimeStepPostprocessor` / `CriticalTimeStep` / `TorqueReaction`
- Source: `modules/solid_mechanics/include/postprocessors/Mass.h:18` / `MaterialTimeStepPostprocessor.h:18` / `CriticalTimeStep.h:23` / `TorqueReaction.h`
- Example: `modules/solid_mechanics/test/tests/torque_reaction/torque_reaction.i:117` (TorqueReaction).
- `Mass`: volume integral of `density` (default `density`).
- `MaterialTimeStepPostprocessor`: reports the most-restrictive `material_timestep_limit` (set by inelastic models via `max_inelastic_increment`); plug into `[Executioner]/IterationAdaptiveDT/time_step_postprocessor`.
- `CriticalTimeStep`: CFL-style explicit-dynamics critical timestep `h_min / c_wave`.
- `TorqueReaction`: net torque about an axis by integrating `(r - r_0) x (sigma . n)` over a sideset.

### `[NodalKernels]` — explicit-dynamics nodal mass / damping

##### `NodalTranslationalInertia` / `NodalRotationalInertia` / `NodalGravity`
- Source: `modules/solid_mechanics/include/nodalkernels/NodalTranslationalInertia.h`
- Lumped translational / rotational mass (and gravity) at each node — alternative to `InertialForce` for explicit / lumped-mass schemes.
- Required: `variable`, `velocity`, `acceleration`, `beta`, `gamma`, `mass`.

## Cross-cutting concerns

### `displacements` is everywhere
Every SM object that consumes the kinematics (kernels, strain materials, BC actions like `[BCs]/Pressure`, the Physics actions) takes `displacements`. Set it once in `[GlobalParams]` to avoid threading it through every block.

### `base_name` namespacing
For multi-physics on overlapping subdomains (per-grain crystal plasticity, per-phase phase-field, fiber + matrix in composites), set `base_name = phase_a` on every SM material AND the matching kernel — `_stress` becomes `phase_a_stress`, `_mechanical_strain` becomes `phase_a_mechanical_strain`. The Physics action exposes `base_name` (default for everything it sets up) AND `strain_base_name` (override the strain calculator alone, when one strain feeds multiple stress chains). Forgetting `base_name` on either side of a property handshake produces a "Material property not found" error.

### `eigenstrain_names` plumbing
The strain calculator subtracts every property listed in its `eigenstrain_names` from total strain to get `_mechanical_strain`. Workflow: (1) instance an eigenstrain material with `eigenstrain_name = my_thermal`; (2) list `my_thermal` in `eigenstrain_names` on the strain calculator (or on the Physics action). Set `automatic_eigenstrain_names = true` on the Physics action to auto-collect every eigenstrain in scope. Forgetting to wire the name leaves total and mechanical strain identical — silent bug.

### Coupling with heat transfer
Pass a temperature variable through the Physics action via `temperature` (or directly into `ComputeThermalExpansionEigenstrain` / `PowerLawCreepStressUpdate`). The temperature comes from `[Variables]` (solved together) or `[AuxVariables]` (transferred from a sub-app).

### `add_variables = true` and `generate_output`
Inside the Physics action, `add_variables = true` declares `disp_x/y/z` (matching `displacements`). `generate_output = 'vonmises_stress hydrostatic_stress strain_xx stress_xy'` declares the matching `[AuxVariables]` AND the corresponding `RankTwoAux`/`RankTwoScalarAux` AuxKernels in one shot. Override `material_output_order`/`material_output_family` for orders higher than CONSTANT-MONOMIAL. Available keys cover: stress/strain components (`stress_xx`/`yy`/...; `strain_*`, `mechanical_strain_*`, `total_strain_*`, `creep_strain_*`, `plastic_strain_*`, `elastic_strain_*`); invariants (`vonmises_stress`, `hydrostatic_stress`, `effective_plastic_strain`, `firstinv_stress`/`secondinv_stress`/`thirdinv_stress`, `triaxiality_stress`, `{max,mid,min}_principal_stress`); cylindrical/spherical (`hoop_stress`, `radial_stress`, `axial_stress`, `spherical_hoop_stress`, `spherical_radial_stress`).

### AD chain integrity
The chain `ADComputeIsotropicElasticityTensor` -> `ADComputeSmallStrain` -> `ADComputeLinearElasticStress` -> `ADStressDivergenceTensors` propagates dual numbers end-to-end. Mixing one non-AD piece silently drops AD information from there forward — Newton convergence degrades but solves often "look fine". The Physics action does the wiring for you when `use_automatic_differentiation = true`.

### Strain / stress chain pairing rules
- `ComputeSmallStrain` -> `ComputeLinearElasticStress`.
- `ComputeIncrementalSmallStrain` -> `ComputeMultipleInelasticStress`.
- `ComputeFiniteStrain` -> `ComputeFiniteStrainElasticStress` OR `ComputeMultipleInelasticStress`.
- `ComputeGreenLagrangeStrain` -> hyperelastic stress.
- `ComputePlane*Strain` / `ComputeAxisymmetricRZ*Strain` / `ComputeRSpherical*Strain` -> the corresponding finite/small stress (no special "plane" stress class).

Mismatched pairings compile but produce wrong stress.

### Multi-block, legacy
For different strain measures on different subdomains, instantiate the Physics action twice with `block = '...'` and distinct sub-block names; the action shares displacement variables across sub-blocks. Pre-rename inputs use `[TensorMechanics]` (still accepted via `LegacyTensorMechanicsAction`); the half-shorthand `[Kernels]/SolidMechanics` (`CommonSolidMechanicsAction`) auto-wires kernels only — used by `modules/solid_mechanics/test/tests/pressure/pressure_test.i:54` and `modules/solid_mechanics/test/tests/visco/visco_small_strain.i:42`. Do not propagate the `tensor_mechanics` prefix to new objects.

## Minimal scaffold

Static elasticity using the Physics action — small strain, isotropic, Dirichlet + pressure BCs, von-Mises + `stress_xx` output, reaction-force postprocessor:

```hit
[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 3
    nx = 4
    ny = 4
    nz = 4
  []
[]

[GlobalParams]
  displacements = 'disp_x disp_y disp_z'
[]

[Physics/SolidMechanics/QuasiStatic]
  [all]
    strain = SMALL
    add_variables = true
    use_automatic_differentiation = true
    generate_output = 'vonmises_stress hydrostatic_stress strain_xx stress_xx'
  []
[]

[BCs]
  [fix_x]
    type = DirichletBC
    variable = disp_x
    boundary = left
    value = 0
  []
  [fix_y]
    type = DirichletBC
    variable = disp_y
    boundary = bottom
    value = 0
  []
  [fix_z]
    type = DirichletBC
    variable = disp_z
    boundary = back
    value = 0
  []
  [Pressure]
    [top_load]
      boundary = top
      function = '1e5 * t'
      use_automatic_differentiation = true
    []
  []
[]

[Materials]
  [elasticity]
    type = ADComputeIsotropicElasticityTensor
    youngs_modulus = 2.1e11
    poissons_ratio = 0.3
  []
  [stress]
    type = ADComputeLinearElasticStress
  []
[]

[Postprocessors]
  [react_y_top]
    type = ADSidesetReaction
    boundary = top
    direction = '0 1 0'
    stress_tensor = stress
  []
[]

[Executioner]
  type = Transient
  solve_type = NEWTON
  end_time = 1.0
  dt = 0.5
[]

[Outputs]
  exodus = true
[]
```

The same problem **without** the Physics action — hand-rolled `[Variables]`, `[Kernels]`, `[AuxVariables]`, `[AuxKernels]`. Replace the `[Physics/SolidMechanics/QuasiStatic]` block above with the following; keep `[Mesh]`, `[GlobalParams]`, `[BCs]`, `[Executioner]`, `[Outputs]` unchanged. Also append a strain calculator under `[Materials]`:

```hit
[Variables]
  [disp_x]
  []
  [disp_y]
  []
  [disp_z]
  []
[]

[AuxVariables]
  [vonmises_stress]
    family = MONOMIAL
    order = CONSTANT
  []
[]

[Kernels]
  [stress_x]
    type = ADStressDivergenceTensors
    variable = disp_x
    component = 0
  []
  [stress_y]
    type = ADStressDivergenceTensors
    variable = disp_y
    component = 1
  []
  [stress_z]
    type = ADStressDivergenceTensors
    variable = disp_z
    component = 2
  []
[]

[AuxKernels]
  [vonmises]
    type = ADRankTwoScalarAux
    variable = vonmises_stress
    rank_two_tensor = stress
    scalar_type = vonmisesStress
    execute_on = timestep_end
  []
[]

# Append to [Materials]:
#   [strain]
#     type = ADComputeSmallStrain
#   []
```

For **finite-strain plasticity**, replace the action's `strain` with `FINITE` and the `[Materials]` block with the inelastic-stress chain:

```hit
[Materials]
  [elasticity]
    type = ComputeIsotropicElasticityTensor
    youngs_modulus = 2.1e11
    poissons_ratio = 0.3
  []
  [plasticity_model]
    type = IsotropicPlasticityStressUpdate
    yield_stress = 2.5e8
    hardening_constant = 1e9
  []
  [stress]
    type = ComputeMultipleInelasticStress
    inelastic_models = 'plasticity_model'
    tangent_operator = elastic
  []
[]
```
