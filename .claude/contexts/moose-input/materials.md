# Authoring inputs: Materials (declared properties consumed by kernels)

Reach for this guide when you need to add an entry under `[Materials]` (or `[FunctorMaterials]`) in a `.i` file by **picking from the catalog** of registered MOOSE materials. Most kernel parameters that look like names (`diffusivity`, `density`, `thermal_conductivity`, `youngs_modulus`, `D`, `coeff`, `eigenstrain_names`) are `MaterialPropertyName`s — the matching property must be **declared** here. If the property does not yet exist (i.e. you're writing C++), see `../moose/material-authoring.md`. If you only need to wire a value into a single kernel without ever sampling it elsewhere, often a `Function` plus a `Functor`-aware kernel param avoids `[Materials]` entirely — see [functions.md](./functions.md) and [kernels.md](./kernels.md).

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. Each entry cites both the **source header** (`<file>:<line of class>`) and one **canonical example .i** (`<file>:<line of the sub-block>`). AD twins (`ADFoo`) live in the same header as the templated class — same required params, same patterns.

## When to use this (vs alternatives)

Decide **which kind of property storage** you need before you pick a class.

1. **Stored material property** (most common): write into `[Materials]`. Property is computed at quadrature points each residual evaluation, then read by `getMaterialProperty<T>` / `getADMaterialProperty<T>` in kernels, BCs, AuxKernels. Required for stress/strain/elasticity tensors that participate in solid mechanics.
2. **Functor material property** (preferred for FV, increasingly for FE): write into `[FunctorMaterials]` (or use a `*FunctorMaterial` class inside `[Materials]` — both are valid). Property is *evaluated on demand* at any spatial location (qp, face, node, elem centroid) instead of stored. FV kernels (`FVDiffusion`, `FVAdvection`) consume functors; functors freely interoperate with `Function`, `Variable`, and other functor mat-props.
3. **Aux variable** (no property needed, just an output / postprocessing field): use `[AuxKernels]` instead — see [kernels.md](./kernels.md). Don't fake it with a `GenericConstantMaterial` plus `MaterialRealAux`.
4. **Block-defaulted constant inside Physics shorthand**: many `[Physics/SolidMechanics/QuasiStatic/...]` and `[Physics/HeatConduction/FE]` blocks auto-add elasticity/strain/stress/conduction materials. If you set `add_variables = true` and use the action, you usually only add `ComputeIsotropicElasticityTensor` (or analogue) yourself. Hand-rolled `[Materials]` blocks remain valid and are required for non-trivial wiring.

Then decide **AD vs non-AD**: if the consuming kernel is `AD*`, the producing material must be `AD*` too. Mixing breaks the AD chain silently — kernel will compile and run but the off-diagonal Jacobian entries vanish, killing Newton convergence. Default to `AD*` for new inputs.

Then decide **stateful vs not**: if any consumer calls `getMaterialPropertyOld` / `getMaterialPropertyOlder` (e.g. return-mapping plasticity, viscoelastic state, `OldMaterialAuxKernel`), the producing material must declare the property as stateful via `declarePropertyOld` in C++ — none of the *Generic* / *Parsed* materials below do. For solid mechanics, the radial-return / inelastic family (`ComputeMultipleInelasticStress` + `*StressUpdate`) handles statefulness internally.

## Catalog

### Generic numeric (scalar / vector / tensor / functor)

These are the workhorses for "I just need property X to equal a constant / function / parsed expression". Pick by *what type the consumer wants* (Real, RealVectorValue, RankTwoTensor, RankFourTensor, functor-Real) and *whether the value depends on (x,y,z,t)*.

##### `GenericConstantMaterial` / `ADGenericConstantMaterial`
- Source: `framework/include/materials/GenericConstantMaterial.h:23`
- Example: `test/tests/materials/generic_materials/generic_constant_material.i:55` (sub-block `[dm1]`)
- Declares one or more *Real* material properties, each set to a constant.
- Required: `prop_names` (list of property names), `prop_values` (matching list of Reals).
- Useful: `block`, `boundary`, `outputs`, `output_properties`.

##### `GenericConstantArray`
- Source: `framework/include/materials/GenericConstantArray.h:14`
- Example: `test/tests/auxkernels/array_var_component/array_var_component.i:40` (sub-block `[dc]`)
- Declares one *RealEigenVector* (array) material property, e.g. for `ArrayDiffusion`'s `diffusion_coefficient`.
- Required: `prop_name` (singular), `prop_value` (vector of Reals).

##### `GenericConstantRankTwoTensor` / `ADGenericConstantRankTwoTensor`
- Source: `framework/include/materials/GenericConstantRankTwoTensor.h`
- Example: `test/tests/materials/generic_materials/generic_constant_rank_two_tensor.i`
- Declares one `RankTwoTensor` mat prop set to a 9-entry constant.
- Required: `tensor_name`, `tensor_values` (9 Reals, row-major).

##### `GenericConstantSymmetricRankTwoTensor` / `ADGenericConstantSymmetricRankTwoTensor`
- Source: `framework/include/materials/GenericConstantSymmetricRankTwoTensor.h:19`
- Example: `test/tests/materials/generic_materials/generic_constant_symmetric_rank_two_tensor.i:11` (sub-block `[tensor]`)
- Declares a `SymmetricRankTwoTensor` mat prop from 6 Mandel-form values.
- Required: `tensor_name`, `tensor_values` (6 entries; off-diagonals get the Mandel sqrt-2 factor).

##### `GenericConstantVectorMaterial` / `ADGenericConstantVectorMaterial`
- Source: `framework/include/materials/GenericConstantVectorMaterial.h:15`
- Example: `test/tests/kernels/conservative_advection/no_upwinding_1D.i:25` (sub-block `[v]`)
- Declares one or more `RealVectorValue` mat props from constant `(x y z)` triples.
- Required: `prop_names`, `prop_values` (3 * N Reals).

##### `GenericFunctionMaterial` / `ADGenericFunctionMaterial`
- Source: `framework/include/materials/GenericFunctionMaterial.h:28`
- Example: `test/tests/auxkernels/material_rate_real/material_rate_real.i:62` (sub-block `[mat]`)
- Like `GenericConstantMaterial` but each scalar property comes from a `Function` (so it can be space- or time-varying).
- Required: `prop_names`, `prop_values` (matching list of `Function` names).

##### `GenericFunctionVectorMaterial` / `ADGenericFunctionVectorMaterial`
- Source: `framework/include/materials/GenericFunctionVectorMaterial.h:28`
- Example: `test/tests/functions/generic_function_material/generic_function_vector_material_test.i:51` (sub-block `[gfm]`)
- Vector mat prop where each component is a `Function`.
- Required: `prop_names`, `prop_values` (3 * N Function names).

##### `GenericFunctionRankTwoTensor` / `ADGenericFunctionRankTwoTensor`
- Source: `framework/include/materials/GenericFunctionRankTwoTensor.h`
- Example: `test/tests/materials/generic_materials/generic_function_rank_two_tensor.i`
- 9-entry `RankTwoTensor` mat prop where each entry is a `Function`.
- Required: `tensor_name`, `tensor_functions` (9 Function names, row-major).

##### `GenericFunctorMaterial` / `ADGenericFunctorMaterial`
- Source: `framework/include/functormaterials/GenericFunctorMaterial.h:20`
- Example: `test/tests/mesh/preparedness/test.i:297` (sub-block `[all_channels_porosity]`)
- Declares **functor** Real properties — values can be a literal number, a `Function` name, a `Variable` name, or another functor mat-prop name. The standard "wire any value into an FV kernel's `coeff` / `velocity` / `functor` slot" tool. Lives under `[FunctorMaterials]` *or* `[Materials]` (both work).
- Required: `prop_names`, `prop_values` (mix of constants, function names, variable names, functor names).
- Useful: `block`, `outputs`, `define_dot` (define a time derivative), `define_grad` (define a gradient).

##### `GenericVectorFunctorMaterial` / `ADGenericVectorFunctorMaterial`
- Source: `framework/include/functormaterials/GenericVectorFunctorMaterial.h`
- Example: `test/tests/mesh/preparedness/test.i:308` (sub-block `[effective_solid_thermal_conductivity_solid_only]`)
- Vector functor mat prop. `prop_values` are taken in groups of 3 (x,y,z) per `prop_names` entry.

##### `MaterialFunctorConverter` / `VectorMaterialFunctorConverter`
- Source: `framework/include/materials/MaterialFunctorConverter.h:18`
- Example: `test/tests/materials/functor_conversion/conversion.i:62` (sub-block `[convert_to_reg]`)
- Bridges functor-property world to stored-property world — read a functor in, declare a regular `Real` (or AD) mat prop out. Use when an old kernel insists on `getMaterialProperty<Real>` but your value originally lives as a functor / `Variable`.
- Required: `functors_in`, plus exactly one of `reg_props_out` / `ad_props_out` / `reg_true_props_out`.

##### `ParsedMaterial` / `ADParsedMaterial`
- Source: `framework/include/materials/ParsedMaterial.h:21`
- Example: `test/tests/materials/parsed/parsed_material_with_functors.i:60` (sub-block `[hm]`)
- Declares one *Real* mat prop set by a parsed math expression of coupled variables, postprocessors, functors, and constants.
- Required: `property_name`, `expression`.
- Useful: `coupled_variables`, `material_property_names`, `functor_names`, `functor_symbols`, `postprocessor_names`, `constant_names` / `constant_expressions`, `outputs`.

##### `DerivativeParsedMaterial` / `ADDerivativeParsedMaterial`
- Source: `framework/include/materials/DerivativeParsedMaterial.h:20`
- Example: `test/tests/materials/derivative_material_interface/construction_order.i:54` (sub-block `[free_energy_a]`)
- Same as `ParsedMaterial` but also declares symbolic derivatives w.r.t. each entry in `coupled_variables` — required by Cahn-Hilliard / Allen-Cahn `SplitCHParsed` etc. that look up `dF/dc` via the `DerivativeMaterialInterface`.
- Required: `property_name`, `expression`, `coupled_variables`.
- Useful: `derivative_order` (default 3, often set globally via `[GlobalParams]`), `material_property_names`, `constant_names`, `outputs`.

##### `PiecewiseLinearInterpolationMaterial`
- Source: `framework/include/materials/PiecewiseLinearInterpolationMaterial.h:20`
- Example: `test/tests/materials/piecewise_linear_interpolation_material/piecewise_linear_interpolation_material.i:40` (sub-block `[m1]`)
- 1D table lookup — declare a Real property by piecewise-linear interpolation of a coupled variable through `(x_i, y_i)` knots. Common for "k(T)" tables.
- Required: `property`, `variable`, plus either `xy_data` or both `x` and `y`.
- Useful: `extrapolation` (default false, clamps at endpoints), `block`, `outputs`.

### Coupled / variable-driven

##### `CoupledValueFunctionMaterial` / `ADCoupledValueFunctionMaterial`
- Source: `framework/include/materials/CoupledValueFunctionMaterial.h:20`
- Example: `test/tests/materials/coupled_value_function/order.i:57` (sub-block `[cvf]`)
- Declares a Real mat prop by sampling a `Function` whose `(x,y,z,t)` slots are remapped from coupled variables — i.e. evaluate `f(v1, v2, v3, v4)` where `v1..v4` are aux/nonlinear vars. The N-D analog of `PiecewiseLinearInterpolationMaterial` via a `PiecewiseMultilinear` function.
- Required: `function`, `prop_name`.
- Useful: `v` (1-4 coupled variables), `parameter_order` (which coupled var maps to which function slot).

##### `CoupledGradientMaterial`
- Source: `framework/include/materials/CoupledGradientMaterial.h`
- Example: `test/tests/materials/coupled_gradient_material/`
- Declares vector mat prop equal to `grad(v)` of a coupled variable (so other materials can consume the gradient as a functor or stored property).
- Required: `variable`, `grad_prop_name`.

### Stateful (old/older property) interactions

None of the *Generic* / *Parsed* materials above declare stateful (`_old`/`_older`) versions — they recompute every step. Stateful behavior comes from materials that explicitly opt in via `declarePropertyOld` in C++; in inputs you simply **consume** them via a kernel, BC, or AuxKernel that takes `getMaterialPropertyOld`.

##### `MaterialDerivativeTestKernel` (consumer, not material)
- Source: `framework/include/kernels/MaterialDerivativeTestKernel.h:17`
- Example: `test/tests/materials/derivative_material_interface/`
- Use this kernel to **verify** that a `DerivativeParsedMaterial` declares the right derivative properties. Pair with any `Parsed`/`DerivativeParsed` material above; the kernel reads `dF/du` and contributes it as a residual so a Jacobian-check test can compare AD vs analytic.

##### `OldMaterialAuxKernel`-style consumers
- For `[Materials]` authors, the only thing to remember: a property consumed via `getMaterialPropertyOld` must have been declared by a material that calls `declarePropertyOld` (or the framework will store the previous-step value automatically once any consumer asks for `_old`). Use `[AuxKernels]` -> `MaterialRealAux` with `selected_qp` *and* a state argument when you want to dump `_old` to an Exodus field for visualization. See `test/tests/auxkernels/old_older_material_aux/old_mat_in_aux.i:62` for the pattern.

### Solid mechanics — elasticity tensors

Each entry declares the rank-four `elasticity_tensor` (or block-namespaced via `base_name`) consumed by `ComputeStressBase` derivatives.

##### `ComputeIsotropicElasticityTensor` / `ADComputeIsotropicElasticityTensor`
- Source: `modules/solid_mechanics/include/materials/ComputeIsotropicElasticityTensor.h:19`
- Example: `modules/solid_mechanics/test/tests/recompute_radial_return/isotropic_plasticity_incremental_strain.i:81` (sub-block `[elasticity_tensor]`)
- Isotropic 4th-order elasticity tensor from any *two* of: `youngs_modulus`+`poissons_ratio`, `bulk_modulus`+`shear_modulus`, `lambda`+`shear_modulus`.
- Required: a valid pair (the class will error if you supply an invalid combination).
- Useful: `block`, `base_name` (namespace e.g. for multi-material blocks), `outputs`.

##### `ComputeElasticityTensor`
- Source: `modules/solid_mechanics/include/materials/ComputeElasticityTensor.h:18`
- Example: `modules/solid_mechanics/test/tests/auxkernels/ranktwoscalaraux.i:60` (sub-block `[elasticity_tensor]`)
- Generic anisotropic elasticity tensor from explicit constants + a fill method (orthotropic / cubic / symmetric9 / symmetric21 / general). This is the entry to use for orthotropic and anisotropic crystals — there is no separate `ComputeOrthotropicElasticityTensor`.
- Required: `C_ijkl`, `fill_method`.
- Useful: `euler_angle_1` / `euler_angle_2` / `euler_angle_3` (or `rotation_matrix`) for crystal orientation, `base_name`.

##### `ComputeVariableIsotropicElasticityTensor`
- Source: `modules/solid_mechanics/include/materials/ComputeVariableIsotropicElasticityTensor.h:19`
- Example: `modules/combined/test/tests/thermal_elastic/thermal_elastic.i:286` (sub-block defining `youngs_modulus` material)
- Like `ComputeIsotropicElasticityTensor` but `youngs_modulus` and `poissons_ratio` are *material property names* (e.g. set by another `ParsedMaterial` of temperature) instead of constants — for thermal-softening / damage / variable-stiffness problems.
- Required: `youngs_modulus`, `poissons_ratio`, `args` (coupled vars whose changes affect the moduli).

##### `CompositeElasticityTensor`
- Source: `modules/solid_mechanics/include/materials/CompositeElasticityTensor.h`
- Example: `modules/solid_mechanics/test/tests/elasticitytensor/composite.i`
- Sum of weighted tensors — for two-phase / interpolated composites driven by a switching function.
- Required: `tensors`, `weights`, `args`.

### Solid mechanics — strain calculators

Pick exactly **one** strain calculator per `block` per `base_name`. The choice of `Small` vs `Incremental` vs `Finite` must match the stress class you pair it with (see next section).

##### `ComputeSmallStrain` / `ADComputeSmallStrain`
- Source: `modules/solid_mechanics/include/materials/ComputeSmallStrain.h:17`
- Example: `modules/solid_mechanics/test/tests/auxkernels/tensorelasticenergyaux.i` (search `type = ComputeSmallStrain`)
- Total small-strain (linear) strain `eps = 0.5 (grad u + grad u^T)`. Pair with `ComputeLinearElasticStress`.
- Required: `displacements`.
- Useful: `eigenstrain_names`, `base_name`, `volumetric_locking_correction`, `outputs`.

##### `ComputeIncrementalStrain` / `ADComputeIncrementalStrain`
- Source: `modules/solid_mechanics/include/materials/ComputeIncrementalStrain.h:18`
- Example: `modules/solid_mechanics/test/tests/ad_elastic/incremental_small_elastic-noad.i:78` (sub-block `[strain]`)
- Small-strain rate-form (incremental) — required for return-mapping plasticity / `ComputeMultipleInelasticStress` at small strains.
- Required: `displacements`.
- Useful: `eigenstrain_names`, `base_name`.

##### `ComputeFiniteStrain` / `ADComputeFiniteStrain`
- Source: `modules/solid_mechanics/include/materials/ComputeFiniteStrain.h:18`
- Example: `modules/solid_mechanics/test/tests/auxkernels/ranktwoscalaraux.i:66` (sub-block `[strain]`)
- Polar-decomposition incremental finite strain. Pair with `ComputeFiniteStrainElasticStress` or `ComputeMultipleInelasticStress`.
- Required: `displacements`.
- Useful: `eigenstrain_names`, `base_name`, `volumetric_locking_correction`.

##### `ComputePlaneSmallStrain` / `ADComputePlaneSmallStrain`
- Source: `modules/solid_mechanics/include/materials/ComputePlaneSmallStrain.h:20`
- Example: `modules/solid_mechanics/test/tests/generalized_plane_strain/out_of_plane_pressure.i:188` (sub-block in `[Materials]` at line 183)
- 2D plane-strain (or plane-stress with `out_of_plane_strain`) small strain.
- Required: `displacements`.
- Useful: `out_of_plane_strain` (scalar or aux var name), `eigenstrain_names`.

##### `ComputeAxisymmetricRZSmallStrain` / `ADComputeAxisymmetricRZSmallStrain`
- Source: `modules/solid_mechanics/include/materials/ComputeAxisymmetricRZSmallStrain.h:18`
- Example: `modules/solid_mechanics/test/tests/ad_elastic/rz_small_elastic-noad.i:64` (sub-block `[strain]`)
- 2D RZ-axisymmetric small strain. Mesh must be `coord_type = RZ` in `[Problem]`.
- Required: `displacements` (must be 2 components: `disp_r disp_z`).

##### `ComputePlaneFiniteStrain` / `ADComputePlaneFiniteStrain`
- Source: `modules/solid_mechanics/include/materials/ComputePlaneFiniteStrain.h:19`
- Example: `modules/solid_mechanics/test/tests/material_limit_time_step/creep/nafems_test5a_lim.i:227` (sub-block in `[Materials]` at line 219)
- 2D plane finite strain.
- Required: `displacements`.

### Solid mechanics — stress

Pair exactly one stress class with the matching strain class on each block.

##### `ComputeLinearElasticStress` / `ADComputeLinearElasticStress`
- Source: `modules/solid_mechanics/include/materials/ComputeLinearElasticStress.h:17`
- Example: `modules/solid_mechanics/test/tests/isotropic_elasticity_tensor/youngs_modulus_poissons_ratio_test.i` (search `type = ComputeLinearElasticStress`)
- `sigma = C : eps` — pairs with `ComputeSmallStrain`.
- Required: (none beyond the elasticity tensor + strain it consumes).
- Useful: `base_name`.

##### `ComputeFiniteStrainElasticStress` / `ADComputeFiniteStrainElasticStress`
- Source: `modules/solid_mechanics/include/materials/ComputeFiniteStrainElasticStress.h:19`
- Example: `modules/solid_mechanics/test/tests/thermal_expansion_function/finite_const.i:82` (sub-block `[small_stress]`)
- Hyperelastic stress for `ComputeFiniteStrain`. The default for nonlinear elasticity without inelastic models.
- Required: (none).
- Useful: `base_name`.

##### `ComputeMultipleInelasticStress` / `ADComputeMultipleInelasticStress`
- Source: `modules/solid_mechanics/include/materials/ComputeMultipleInelasticStress.h:30`
- Example: `modules/solid_mechanics/test/tests/recompute_radial_return/isotropic_plasticity_incremental_strain.i:91` (sub-block `[radial_return_stress]`)
- Glue layer that runs one or more *return-mapping* (`*StressUpdate`) sub-models. Pair with `ComputeIncrementalStrain` or `ComputeFiniteStrain`. Internally stateful.
- Required: `inelastic_models` (list of names of `*StressUpdate` materials in the same `[Materials]` block).
- Useful: `tangent_operator` (`elastic|nonlinear`, default `nonlinear`), `combined_inelastic_strain_weights`, `base_name`.

##### `IsotropicPlasticityStressUpdate` / `ADIsotropicPlasticityStressUpdate`
- Source: `modules/solid_mechanics/include/materials/IsotropicPlasticityStressUpdate.h:33`
- Example: `modules/solid_mechanics/test/tests/recompute_radial_return/isotropic_plasticity_incremental_strain.i:86` (sub-block `[isotropic_plasticity]`)
- J2 plasticity with linear isotropic hardening. Sub-model fed to `ComputeMultipleInelasticStress`. Stateful.
- Required: `yield_stress` (or `yield_stress_function`), `hardening_constant` (or `hardening_function`).

##### `PowerLawCreepStressUpdate` / `ADPowerLawCreepStressUpdate`
- Source: `modules/solid_mechanics/include/materials/PowerLawCreepStressUpdate.h:25`
- Example: `modules/solid_mechanics/test/tests/recompute_radial_return/cp_affine_plasticity.i:295` (sub-block in `[Materials]` at line 283)
- Norton-Bailey power-law creep `eps_dot = A sigma^n exp(-Q/RT)`. Sub-model for `ComputeMultipleInelasticStress`.
- Required: `coefficient`, `n_exponent`, `activation_energy`.
- Useful: `temperature` (mat-prop name or coupled var), `base_name`.

##### `LinearViscoelasticStressUpdate`
- Source: `modules/solid_mechanics/include/materials/LinearViscoelasticStressUpdate.h:25`
- Example: `modules/solid_mechanics/test/tests/visco/gen_kv_creep.i:115` (sub-block in `[Materials]` at line 102)
- Linear-viscoelastic strain update; consumes a `LinearViscoelasticityBase` derivative (e.g. `GeneralizedKelvinVoigtModel`, `GeneralizedMaxwellModel`) declared in the same `[Materials]` block. Stateful via internal driving strain history.
- Required: (none beyond pairing).

### Solid mechanics — eigenstrains

An eigenstrain is a strain *contribution subtracted before computing stress*. Always wired in by name through `eigenstrain_names = '<name>'` on the strain calculator. Multiple eigenstrains stack — list each `eigenstrain_name` in the `eigenstrain_names` list on the strain class.

##### `ComputeThermalExpansionEigenstrain` / `ADComputeThermalExpansionEigenstrain`
- Source: `modules/solid_mechanics/include/materials/ComputeThermalExpansionEigenstrain.h:19`
- Example: `modules/solid_mechanics/test/tests/radial_disp_aux/cylinder_2d_cartesian.i:80` (sub-block in `[Materials]` at line 70)
- Constant-CTE thermal expansion `eps_th = alpha (T - T_ref) I`.
- Required: `temperature`, `stress_free_temperature`, `thermal_expansion_coeff`, `eigenstrain_name`.

##### `ComputeMeanThermalExpansionFunctionEigenstrain` / `ADComputeMeanThermalExpansionFunctionEigenstrain`
- Source: `modules/solid_mechanics/include/materials/ComputeMeanThermalExpansionFunctionEigenstrain.h:19`
- Example: `modules/solid_mechanics/test/tests/thermal_expansion_function/finite_const.i:86` (sub-block `[thermal_expansion_strain1]`)
- Mean-CTE form `eps_th = alpha_mean(T) (T - T_ref) - alpha_mean(T0) (T0 - T_ref)`. Use when handbook data is mean-from-reference.
- Required: `temperature`, `stress_free_temperature`, `thermal_expansion_function`, `thermal_expansion_function_reference_temperature`, `eigenstrain_name`.

##### `ComputeInstantaneousThermalExpansionFunctionEigenstrain` / `ADComputeInstantaneousThermalExpansionFunctionEigenstrain`
- Source: `modules/solid_mechanics/include/materials/ComputeInstantaneousThermalExpansionFunctionEigenstrain.h`
- Example: `modules/solid_mechanics/test/tests/thermal_expansion_function/finite_const.i:95` (sub-block `[thermal_expansion_strain2]`)
- Instantaneous-CTE form (integrated over T history). Use when handbook data is `dL/L / dT`.
- Required: same shape as the mean-form.

##### `ComputeVariableEigenstrain`
- Source: `modules/solid_mechanics/include/materials/ComputeVariableEigenstrain.h:19`
- Example: `modules/combined/test/tests/eigenstrain/variable.i:95` (sub-block in `[Materials]` at line 72)
- Eigenstrain = (prefactor material prop) * (constant tensor). Used to drive eigenstrains from a phase-field or coupled-variable derived prefactor — paired with a `DerivativeParsedMaterial` that declares the prefactor and its derivatives w.r.t. coupled variables.
- Required: `prefactor` (material prop name), `eigen_base` (9 entries), `eigenstrain_name`, `args` (coupled vars).

### Heat transfer

##### `HeatConductionMaterial` / `ADHeatConductionMaterial`
- Source: `modules/heat_transfer/include/materials/HeatConductionMaterial.h:22`
- Example: `modules/heat_transfer/test/tests/convective_flux_function/convective_flux_function.i:56` (sub-block `[thermal]`); AD: `modules/heat_transfer/test/tests/postprocessors/ad_convective_ht_side_integral.i:84` (sub-block `[pronghorn_solid_material]`)
- Declares `thermal_conductivity` and (optionally) `specific_heat` mat props from constants or temperature-dependent functions.
- Required: at least one of `thermal_conductivity` / `thermal_conductivity_temperature_function` / `specific_heat` / `specific_heat_temperature_function`.
- Useful: `temp` (coupled variable, required if any `_temperature_function` is set), `block`, `outputs`.

##### `AnisoHeatConductionMaterial` / `ADAnisoHeatConductionMaterial`
- Source: `modules/heat_transfer/include/materials/AnisoHeatConductionMaterial.h:21`
- Example: `modules/heat_transfer/test/tests/heat_conduction/anisotropic_thermal_conductivity/`
- Tensor-valued thermal conductivity for anisotropic conduction.
- Required: `thermal_conductivity` (9 entries), `temp` (if function-driven).

##### `GapConductance` (typically auto-injected)
- Source: `modules/heat_transfer/include/materials/GapConductance.h:17`
- Example: usually injected by `[ThermalContact]` action — see `modules/heat_transfer/test/tests/gap_heat_transfer_htonly/gap_heat_transfer_htonly_test.i`.
- Computes the gap conductance between two surfaces (gas conduction + radiation) for `GapHeatTransfer`. Prefer the `[ThermalContact]` action to a hand-rolled `[Materials]` entry — the action wires the matching BC automatically.

##### `SideSetHeatTransferMaterial`
- Source: `modules/heat_transfer/include/materials/SideSetHeatTransferMaterial.h:17`
- Example: `modules/heat_transfer/test/tests/sideset_heat_transfer/`
- Interface material for cohesive-style side-set heat transfer (interface kernels need this on both sides).
- Required: `conductivity`, `gap_length`, `Tbulk`, `h_master`, `h_slave`, `emissivity_master`, `emissivity_slave`.

### Phase field (high-traffic only)

The phase-field module has 50+ materials for free-energy formulations, KKS, grand-potential, GB anisotropy, etc. The vast majority are author-once-and-cite. List below covers the three most-used in everyday inputs; for the rest, search `modules/phase_field/test/tests/` for the closest example.

##### `DerivativeParsedMaterial` (re-used heavily here)
- See entry under "Generic numeric" above.
- The phase-field convention: every free-energy contribution is a `DerivativeParsedMaterial` named by physical role (`F_chem`, `F_grad`, ...) that lists `coupled_variables = '<order params, conserved fields>'`. `DerivativeSumMaterial` then sums them into a single `F` consumed by `SplitCHParsed` / `AllenCahn` etc.

##### `BarrierFunctionMaterial`
- Source: `modules/phase_field/include/materials/BarrierFunctionMaterial.h:23`
- Example: `modules/phase_field/test/tests/MultiPhase/orderparameterfunctionmaterial.i:81` (sub-block in `[Materials]` at line 63)
- Standard double-well barrier `g(eta) = eta^2 (1-eta)^2` (or the lower / upper variants). Declares `g(eta)` as the property `function_name` (default `g`) plus its derivatives via `DerivativeMaterialInterface`.
- Required: `eta` (order parameter).
- Useful: `g_order` (`SIMPLE|LOW`), `function_name`, `well_only` (bool).

##### `SwitchingFunctionMaterial`
- Source: `modules/phase_field/include/materials/SwitchingFunctionMaterial.h:23`
- Example: `modules/phase_field/test/tests/MultiPhase/orderparameterfunctionmaterial.i:65` (sub-block in `[Materials]` at line 63)
- Standard switching function `h(eta) = 3 eta^2 - 2 eta^3` (or higher-order). Pairs with two phase free-energy `DerivativeParsedMaterial`s.
- Required: `eta`.
- Useful: `h_order` (`SIMPLE|HIGH|LOW`), `function_name` (default `h`).

### Fluid properties

##### `FluidPropertiesMaterialPT`
- Source: `modules/fluid_properties/include/materials/FluidPropertiesMaterialPT.h:18`
- Example: `modules/fluid_properties/test/tests/materials/fluid_properties_material/test_pt.i:128` (sub-block `[fp_mat]`)
- Wires a `[FluidProperties]` user object (e.g. `IdealGasFluidProperties`, `Water97FluidProperties`) into mat props (`rho`, `mu`, `cp`, `cv`, `k`, ...) at every qp using pressure + temperature variables.
- Required: `pressure`, `temperature`, `fp` (UserObject name from `[FluidProperties]`).
- Useful: `block`, `outputs`.

For more involved single-phase / multi-phase / FlibeFluid hookups, see the `[FluidProperties]` user-object guide in [misc.md](./misc.md).

## Cross-cutting concerns

### Property-name conventions
- Defaults follow the consumer: `ADHeatConduction` looks up `thermal_conductivity` and `specific_heat`; `MatDiffusion` looks up `D`; `Gravity` looks up `density`; `JouleHeatingSource` looks up `electrical_conductivity`. Override on the consuming kernel (e.g. `diffusion_coefficient = my_diff`) **or** rename in the material's `prop_names`.
- For solid mechanics, use `base_name = foo` on **both** the strain calculator *and* the stress calculator *and* the elasticity tensor when you need parallel material chains on the same block (e.g. dual-network composites). Properties get prefixed `foo_stress`, `foo_strain`, etc.

### AD vs non-AD compatibility
- A `getMaterialProperty<Real>` consumer cannot read a property declared by `declareADProperty<Real>` (or vice-versa). The framework will *register but not populate* the wrong-flavor copy and silently give zeros. If your kernel is `AD*`, use the `AD*` material class. The `MaterialFunctorConverter` is the explicit bridge.
- AD parsed materials (`ADParsedMaterial`, `ADDerivativeParsedMaterial`) carry full AD wrt every `coupled_variables` entry — no off-diagonal Jacobian wiring needed.

### `coupled_variables` for derivative materials
- `DerivativeParsedMaterial` *requires* `coupled_variables` to be the union of every variable that appears in `expression`. Missing one means the corresponding `dF/dv` is silently zero. This is a Newton convergence killer in phase-field models — always cross-check.
- `derivative_order` (often pinned in `[GlobalParams]`) controls which `d^n F` properties get declared. Default 3. Phase-field with both `SplitCHParsed` and `AllenCahn` typically needs `derivative_order >= 2`.

### Block restriction
- `block = '<subdomain_names>'` restricts where the property is declared — *every* block that a consumer touches must declare a non-conflicting copy of the property name (or the consumer must restrict its `block` parameter to match). Mixing block-restricted and unrestricted materials with the same `property_name` is an error.
- For solid mechanics with multiple subdomains, replicate the elasticity-tensor + strain + stress trio per block (use different sub-block names but the same property names — the `block` parameter disambiguates).

### Outputs
- `outputs = exodus` (or whatever output is named) on a material entry exports its declared properties as element-averaged or qp-projected aux fields. Default: only the property names listed; use `output_properties = 'a b'` to filter when one material declares many properties.
- Tensor-valued properties (`RankTwoTensor`, `RankFourTensor`) need `RankTwoAux`/`RankFourAux` to extract scalar components for ParaView. Listing them in `outputs` alone won't help — the framework picks individual components only when you also specify which.

### `prop_names` / `prop_values` semantics for `GenericConstantMaterial`
- The two lists must have the same length; index `i` of `prop_values` becomes the constant value of `prop_names[i]`. For vector / tensor variants the rule is "3 (or 9, or 6) values per name".
- `prop_values` accepts FParser strings if you want simple arithmetic at parse time (e.g. `'1.0 2*3.14 1e-3'`).

### Functor vs stored decision
- Choose **functor** (e.g. `ADGenericFunctorMaterial`) when: the consumer is FV; the value will be queried at faces / nodes / centroids; you want to swap a constant for a `Function` or `Variable` at input time; you don't need `_old` / `_older`.
- Choose **stored** (e.g. `ADGenericConstantMaterial`) when: the consumer is FE and uses `getADMaterialProperty`; the value is stateful; you need element-qp storage for return-mapping or tensor algebra.
- Mixed FE+FV problems often declare both — the same constant doubled up as `GenericConstantMaterial` (for FE) and `GenericFunctorMaterial` (for FV).

### `base_name` namespacing in solid mechanics
- Setting `base_name = X` on an elasticity-tensor / strain / stress material renames its declared properties to `X_elasticity_tensor`, `X_total_strain`, `X_stress`, etc. Match the same `base_name` on the consuming `StressDivergenceTensors` kernel (or the Physics shorthand). Used for parallel deformation chains, multi-phase stress, and crystal plasticity per-grain quantities.

## Minimal scaffold

A `[Materials]` block declaring (a) a constant `D` for `MatDiffusion`, (b) a parsed reaction rate, and (c) a functor density consumed by an FV kernel:

```hit
[Materials]
  [const_diff]
    type = ADGenericConstantMaterial
    prop_names = 'D'
    prop_values = '1.0e-3'
    block = 'fuel'
  []

  [parsed_rate]
    type = ADParsedMaterial
    property_name = 'rate'
    coupled_variables = 'T c'
    expression = 'A0 * exp(-Ea / (R * T)) * c'
    constant_names       = 'A0      Ea     R'
    constant_expressions = '1.0e6   75000  8.314'
    outputs = exodus
  []

  [rho_functor]
    type = ADGenericFunctorMaterial
    prop_names  = 'rho cp'
    prop_values = '7800 500'   # constants, but could be Function or Variable names
  []
[]
```

A solid-mechanics chain (small-strain isotropic elasticity, optional thermal eigenstrain), authored under `[Materials]` rather than via Physics shorthand:

```hit
[Materials]
  [elasticity_tensor]
    type = ADComputeIsotropicElasticityTensor
    youngs_modulus = 2.1e11
    poissons_ratio = 0.3
  []

  [strain]
    type = ADComputeSmallStrain
    displacements = 'disp_x disp_y'
    eigenstrain_names = 'thermal_eigenstrain'
  []

  [thermal_eigenstrain]
    type = ADComputeThermalExpansionEigenstrain
    temperature = T
    stress_free_temperature = 293.15
    thermal_expansion_coeff = 1.2e-5
    eigenstrain_name = thermal_eigenstrain
  []

  [stress]
    type = ADComputeLinearElasticStress
  []
[]
```
