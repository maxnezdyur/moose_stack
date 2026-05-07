# Authoring: Solid Mechanics module

The `solid_mechanics` module assembles a continuum solid via a strain calculator + an elasticity tensor + a stress material, all wired into displacement equations by `StressDivergenceTensors`-family kernels. New physics is added by extending one of the established `Compute*` chains (strain, stress, eigenstrain) or by writing a `StressUpdateBase` plug-in for `ComputeMultipleInelasticStress`.

## When to use this (vs alternatives)

Decision tree:
- Need a new strain measure (small/finite/incremental/Lagrangian variant, generalized plane-strain, shell, beam)? -> recipe: extend **ComputeStrainBase** or **ComputeIncrementalStrainBase**
- Need a new constitutive (stress) model that is path-independent and acts on total strain? -> extend **ComputeStressBase**
- Need a path-dependent (plasticity / creep / damage) model? -> write a **StressUpdateBase** subclass and plug into **ComputeMultipleInelasticStress** via the `inelastic_models` parameter; usually inherit **RadialReturnStressUpdate** for J2-style return mapping
- Need a thermal / swelling / misfit eigenstrain? -> extend **ComputeEigenstrainBase** (or **ComputeThermalExpansionEigenstrainBase** for thermal)
- Need a new kinematic kernel (rare)? -> usually you do not write a new `StressDivergenceTensors`; see [kernel-authoring.md](./kernel-authoring.md) for kernel mechanics. Inertial body forces / gravity already exist as `InertialForce` / `Gravity`.
- Need a new Physics shorthand? -> extend **QuasiStaticSolidMechanicsPhysics** (or **DynamicSolidMechanicsPhysics**) if you need extra setup logic; for one-off tweaks, prefer driving the existing Physics from input.
- Looking for the AD-vs-non-AD pattern? -> see [material-authoring.md](./material-authoring.md) for general guidance; SM uses templ-AD heavily (`FooTempl<bool is_ad>` with `Foo` and `ADFoo` typedefs).

## Contract

### Common chains to extend

#### **ComputeStrainBase** (modules/solid_mechanics/include/materials/ComputeStrainBase.h:21)
- Required overrides: `computeProperties()` (sets `_mechanical_strain` and `_total_strain`); subtract eigenstrains by iterating `_eigenstrains` (one entry per name in `eigenstrain_names`).
- Optional overrides: `initQpStatefulProperties()` for stateful kinematics; `displacementIntegrityCheck()` if your formulation requires special displacement-dimensionality rules.
- Members published: `_mechanical_strain`, `_total_strain` (RankTwoTensor MaterialProperties); `_base_name`, `_eigenstrain_names`, `_eigenstrains`, optional `_global_strain` pointer, `_volumetric_locking_correction`.

#### **ComputeIncrementalStrainBase** (modules/solid_mechanics/include/materials/ComputeIncrementalStrainBase.h:17)
- Same as above, plus declare and populate `_strain_increment`, `_rotation_increment`, `_deformation_gradient`, `_strain_rate`. Helper `subtractEigenstrainIncrementFromStrain()` is provided.
- Concrete examples: `ComputeFiniteStrain` (modules/solid_mechanics/include/materials/ComputeFiniteStrain.h:18) — computes `_strain_increment` and `_rotation_increment` from `Fhat` via Taylor / EigenSolution / HughesWinget decomposition.

#### **ComputeStressBase** (modules/solid_mechanics/include/materials/ComputeStressBase.h:22)
- Inherits `ComputeGeneralStressBase`. Required override: `computeQpStress()` (sets `_stress` and `_Jacobian_mult`).
- Use for path-independent constitutive laws that take total strain as input (linear elasticity, hyperelasticity).

#### **StressUpdateBase** (modules/solid_mechanics/include/materials/StressUpdateBase.h:45)
- Templated `StressUpdateBaseTempl<bool is_ad, R2 = RankTwoTensor, R4 = RankFourTensor>`. `compute = false` is set internally — these materials are driven by `ComputeMultipleInelasticStress`, not by MOOSE's normal material loop.
- Required override: `updateState(...)` taking trial stress + elastic strain increment and returning admissible stress, inelastic strain increment, and (when computing Jacobian) a tangent operator.
- Required virtuals: `requiresIsotropicTensor()` (return `true`/`false`), optionally `isIsotropic()`, `getTangentCalculationMethod()` returning `TangentCalculationMethod::ELASTIC`, `FULL`, or `PARTIAL` (defined in StressUpdateBase.h:25-30).

#### **RadialReturnStressUpdate** (modules/solid_mechanics/include/materials/RadialReturnStressUpdate.h:30)
- Templated `RadialReturnStressUpdateTempl<bool is_ad>` inheriting both `StressUpdateBaseTempl` and `SingleVariableReturnMappingSolutionTempl`.
- Required overrides: `computeStressInitialize(effective_trial_stress, elasticity_tensor)`, `computeResidual(effective_trial_stress, scalar)`, `computeDerivative(effective_trial_stress, scalar)`, `computeStressFinalize(plastic_strain_increment)`.
- Used for any J2 / radial-return model (von Mises plasticity, power-law creep, Norton creep). Concrete examples: `IsotropicPlasticityStressUpdate` (modules/solid_mechanics/include/materials/IsotropicPlasticityStressUpdate.h:33), `PowerLawCreepStressUpdate` (modules/solid_mechanics/include/materials/PowerLawCreepStressUpdate.h:25).
- Hard-codes `requiresIsotropicTensor() == true` and `isIsotropic() == true`. Provides `_three_shear_modulus`, `_effective_inelastic_strain[_old]`, substepping, time-step limiting (`_max_inelastic_increment`).

#### **ComputeEigenstrainBase** (modules/solid_mechanics/include/materials/ComputeEigenstrainBase.h:19)
- Templated `ComputeEigenstrainBaseTempl<bool is_ad>`. Required: `computeQpEigenstrain()` setting `_eigenstrain` (a `GenericMaterialProperty<RankTwoTensor, is_ad>`); the property is published as `<base_name>_<eigenstrain_name>`. Helper `computeVolumetricStrainComponent(volumetric_strain)` computes diagonal log-strain components for volumetric eigenstrains.
- Subclass `ComputeThermalExpansionEigenstrainBase` (modules/solid_mechanics/include/materials/ComputeThermalExpansionEigenstrainBase.h:26) for thermal-expansion variants and override `computeThermalStrain()` returning a `ValueAndDerivative<is_ad>` (linear thermal strain `dL/L` and its temperature derivative). Do NOT override `computeQpEigenstrain` or `computeProperties` here — they are `final` in this subclass.

#### **ComputeMultipleInelasticStress** (modules/solid_mechanics/include/materials/ComputeMultipleInelasticStress.h:30)
- The driver that takes a list of `StressUpdateBase` instances via the `inelastic_models` parameter, applies them in series (with optional cyclic iteration via `cycle_models`), and writes `_stress` + `_Jacobian_mult`. New plasticity/creep models do not extend this — they extend `StressUpdateBase` and get pulled in via input.

#### **QuasiStaticSolidMechanicsPhysics** (modules/solid_mechanics/include/physics/QuasiStaticSolidMechanicsPhysics.h:15)
- Action that sets up displacement variables, kernels (`StressDivergenceTensors` family), strain calculators, and output materials in one input block. Selects `ComputeSmallStrain` / `ComputeIncrementalStrain` / `ComputeFiniteStrain` (and AD variants) based on `strain` and `incremental` parameters; switches planar formulation via `planar_formulation`; threads `base_name`, `strain_base_name`, `eigenstrain_names`, `generate_output`, `material_output_order`, `material_output_family`, `automatic_eigenstrain_names`, `block`, `add_variables`, `use_displaced_mesh`.

### Multi-physics namespacing: `_base_name`
Most SM materials and kernels accept a `base_name` parameter that prefixes property names — e.g. with `base_name = grain1`, `_stress` is published as `grain1_stress`, `_mechanical_strain` becomes `grain1_mechanical_strain`. Use this when running multiple SM physics on overlapping subdomains (per-phase stress for phase-field, fiber/matrix in composites, multi-grain crystal plasticity). Recipe: thread `base_name` through `validParams` (it is already added by the SM base classes), prefix every property name you `declareProperty`/`getMaterialProperty` with `_base_name`. The Physics action exposes both `base_name` (default for everything it sets up) and `strain_base_name` (override just for the strain calculator — useful when you want one strain shared across multiple stress chains).

### Eigenstrain plumbing
A strain calculator subtracts every property listed in its `eigenstrain_names` parameter from total strain to produce mechanical strain. Recipe to add a new eigenstrain to a Physics block:
1. Author a `ComputeEigenstrainBase` (or AD) subclass that publishes `<base_name>_<eigenstrain_name>` (the base class handles the prefix).
2. Add the material to your input with the desired `eigenstrain_name`.
3. List that name in the Physics action's `eigenstrain_names` (or set `automatic_eigenstrain_names = true` to let the action collect all eigenstrains in scope). The action then wires the strain calculator's `eigenstrain_names` for you.

## Coupling & material properties

Standard MOOSE patterns ([material-authoring.md](./material-authoring.md), [kernel-authoring.md](./kernel-authoring.md)) apply. SM-specific:
- `RankTwoTensor` / `RankFourTensor` are the lingua franca of stress/strain (framework/include/utils/). Both have AD specializations: `ADRankTwoTensor` = `GenericRankTwoTensor<true>`, `ADRankFourTensor` = `GenericRankFourTensor<true>`. Use `GenericMaterialProperty<RankTwoTensor, is_ad>` in templated classes.
- `_base_name` thread-through: every property name you declare or get should be qualified, e.g. `declareProperty<RankTwoTensor>(_base_name + "stress")`. Forgetting one side breaks multi-block / multi-phase setups silently.
- AD vs non-AD: SM has both split classes (`ComputeFiniteStrain` vs `ADComputeFiniteStrain`) and templ-AD classes (`StressUpdateBaseTempl<bool is_ad>`). Prefer AD for new code unless you are extending a non-AD chain that is not yet AD-ified.
- Tangent operators: `StressUpdateBase` returns one of `TangentCalculationMethod::ELASTIC` (cheap, J = C), `FULL` (each model returns its full tangent and they are combined with `J = J_1 * C^-1 * J_2 * C^-1 * ...`), or `PARTIAL` (`J = (J_1 + J_2 + ...)^-1 * C`). AD versions usually return `ELASTIC` and let the AD machinery differentiate the residual.
- `TangentCalculationMethod` enum lives in StressUpdateBase.h:25.

## Registration & build

- `registerMooseObject("SolidMechanicsApp", YourClass);` in the .C. For templated `Templ<bool is_ad>` classes, register both: `registerMooseObject("SolidMechanicsApp", FooStressUpdate); registerMooseObject("SolidMechanicsApp", ADFooStressUpdate);` and explicitly instantiate `template class FooStressUpdateTempl<false>; template class FooStressUpdateTempl<true>;` at the bottom of the .C.
- The module is built only when `SOLID_MECHANICS := yes` is set in the parent app's `Makefile` (downstream apps like blackbear / isopod opt in).
- File locations: `modules/solid_mechanics/include/{materials,kernels,actions,physics,...}/` and the matching `src/...` under the module. Documentation pages live in `modules/solid_mechanics/doc/content/source/...` mirroring source paths.

## Minimal scaffolds

### Scaffold 1 — RadialReturnStressUpdate subclass with custom hardening

Header (`include/materials/PowerHardeningPlasticityStressUpdate.h`):

```cpp
#pragma once
#include "RadialReturnStressUpdate.h"

template <bool is_ad>
class PowerHardeningPlasticityStressUpdateTempl : public RadialReturnStressUpdateTempl<is_ad>
{
public:
  static InputParameters validParams();
  PowerHardeningPlasticityStressUpdateTempl(const InputParameters & parameters);

  using Material::_qp;
  using RadialReturnStressUpdateTempl<is_ad>::_three_shear_modulus;

  virtual void computeStressInitialize(const GenericReal<is_ad> & effective_trial_stress,
                                       const GenericRankFourTensor<is_ad> & C) override;
  virtual GenericReal<is_ad> computeResidual(const GenericReal<is_ad> & trial,
                                             const GenericReal<is_ad> & scalar) override;
  virtual GenericReal<is_ad> computeDerivative(const GenericReal<is_ad> & trial,
                                               const GenericReal<is_ad> & scalar) override;
  virtual void computeStressFinalize(const GenericRankTwoTensor<is_ad> & dep) override;

protected:
  virtual void initQpStatefulProperties() override;

  const Real _sigma_y0;     // initial yield
  const Real _K;            // hardening modulus
  const Real _n;            // hardening exponent
  GenericMaterialProperty<RankTwoTensor, is_ad> & _plastic_strain;
  const MaterialProperty<RankTwoTensor> & _plastic_strain_old;
  GenericMaterialProperty<Real, is_ad> & _eqv_plastic_strain;
  const MaterialProperty<Real> & _eqv_plastic_strain_old;
};
typedef PowerHardeningPlasticityStressUpdateTempl<false> PowerHardeningPlasticityStressUpdate;
typedef PowerHardeningPlasticityStressUpdateTempl<true> ADPowerHardeningPlasticityStressUpdate;
```

Source (`src/materials/PowerHardeningPlasticityStressUpdate.C`) sketch — 3 critical methods:

```cpp
template <bool is_ad>
GenericReal<is_ad>
PowerHardeningPlasticityStressUpdateTempl<is_ad>::computeResidual(
    const GenericReal<is_ad> & trial, const GenericReal<is_ad> & scalar)
{
  const auto p = _eqv_plastic_strain_old[_qp] + scalar;
  const auto sigma_y = _sigma_y0 + _K * MathUtils::pow(p, _n);
  return trial - _three_shear_modulus * scalar - sigma_y;   // f = 0
}
template <bool is_ad>
GenericReal<is_ad>
PowerHardeningPlasticityStressUpdateTempl<is_ad>::computeDerivative(
    const GenericReal<is_ad> & /*trial*/, const GenericReal<is_ad> & scalar)
{
  const auto p = _eqv_plastic_strain_old[_qp] + scalar;
  const auto dH = _K * _n * MathUtils::pow(p, _n - 1.0);
  return -_three_shear_modulus - dH;                        // df/d(scalar)
}
```

Plug into input via:
```
[Materials]
  [hardener]
    type = ADPowerHardeningPlasticityStressUpdate
    sigma_y0 = 250e6
    K = 1e9
    n = 0.3
  []
  [stress]
    type = ADComputeMultipleInelasticStress
    inelastic_models = 'hardener'
  []
[]
```

### Scaffold 2 — function-driven volumetric eigenstrain

Header (`include/materials/FunctionVolumetricEigenstrain.h`):

```cpp
#pragma once
#include "ComputeEigenstrainBase.h"
#include "Function.h"

class FunctionVolumetricEigenstrain : public ComputeEigenstrainBase
{
public:
  static InputParameters validParams();
  FunctionVolumetricEigenstrain(const InputParameters & parameters);

protected:
  virtual void computeQpEigenstrain() override;
  const Function & _vol_function;
};
```

Source (`src/materials/FunctionVolumetricEigenstrain.C`):

```cpp
#include "FunctionVolumetricEigenstrain.h"
registerMooseObject("SolidMechanicsApp", FunctionVolumetricEigenstrain);

InputParameters
FunctionVolumetricEigenstrain::validParams()
{
  auto params = ComputeEigenstrainBase::validParams();
  params.addRequiredParam<FunctionName>("volumetric_function",
                                        "Spatial/temporal volumetric strain (dV/V).");
  return params;
}

FunctionVolumetricEigenstrain::FunctionVolumetricEigenstrain(const InputParameters & parameters)
  : ComputeEigenstrainBase(parameters), _vol_function(getFunction("volumetric_function"))
{
}

void
FunctionVolumetricEigenstrain::computeQpEigenstrain()
{
  const Real ev = _vol_function.value(_t, _q_point[_qp]);
  _eigenstrain[_qp].zero();
  const Real diag = computeVolumetricStrainComponent(ev);    // logarithmic
  _eigenstrain[_qp].addIa(diag);
}
```

Wire it into input: list `eigenstrain_name` in the material, then list it in the strain calculator's `eigenstrain_names` (or in the Physics block's `eigenstrain_names`).

## Common pitfalls

- **Mismatched strain/stress chain.** Pairing `ComputeSmallStrain` with `ComputeFiniteStrainElasticStress` (or any incremental-only stress with a total-strain calculator) compiles fine but produces silently wrong stresses. Match: `ComputeSmallStrain` -> `ComputeLinearElasticStress`; `ComputeIncrementalStrain` / `ComputeFiniteStrain` -> `ComputeFiniteStrainElasticStress` or `ComputeMultipleInelasticStress`.
- **Eigenstrain not subtracted.** Authoring a new `ComputeEigenstrainBase` and forgetting to add its `eigenstrain_name` to the strain calculator's `eigenstrain_names` (or to the Physics block) means it is computed but never subtracted — total and mechanical strain become identical. Set `automatic_eigenstrain_names = true` on the Physics action to avoid this on Physics-driven inputs.
- **`_base_name` half-applied.** Using `_base_name` only when declaring a property but not when fetching it (or vice versa) leads to "Material property not found" errors in multi-block / multi-phase setups. Thread it through every name on both sides.
- **Anisotropic elasticity tensor with RadialReturn.** `RadialReturnStressUpdate::requiresIsotropicTensor() == true` and `ComputeMultipleInelasticStress` asserts isotropy when any sub-model requires it. Pair with `ComputeIsotropicElasticityTensor` (not `ComputeElasticityTensor` driven by an anisotropic `C_ijkl`); for anisotropic inelasticity use `AnisotropicReturnPlasticityStressUpdateBase` / `AnisotropicReturnCreepStressUpdateBase`.
- **`tensor_mechanics` legacy alias.** Older inputs use `[TensorMechanics]` blocks, `tensor_mechanics_temperature`, etc.; the module was renamed to `solid_mechanics` and the upstream registrations now live under `SolidMechanicsApp`. Some legacy class names (e.g. `LegacyDynamicTensorMechanicsAction`) survive for backward compatibility — do not propagate the prefix to new objects.
- **`ComputeMultipleInelasticStress` non-convergence warning.** When the outer iteration over `inelastic_models` does not converge in `max_iterations`, MOOSE issues a `Maximum iterations hit in ComputeMultipleInelasticStress` warning and continues with the last iterate. If you see this, either tighten your sub-model tolerances, raise `max_iterations`, or set `cycle_models = true` so models run in alternation rather than concurrently.
- **Forgetting `initQpStatefulProperties`.** Stateful properties on a `RadialReturnStressUpdate` subclass (plastic strain, internal hardening variable) need `initQpStatefulProperties()` to set t=0 values, otherwise the first step starts with garbage. Also override `propagateQpStatefulProperties()` if you support substepping or `updateState` may be skipped.
- **AD-Templ AD variant not registered.** Templated `FooTempl<bool is_ad>` classes need both `registerMooseObject(..., FooBar)` AND `registerMooseObject(..., ADFooBar)` plus explicit `template class FooBarTempl<false>; template class FooBarTempl<true>;` instantiations at the bottom of the .C, or the AD variant silently won't link.

