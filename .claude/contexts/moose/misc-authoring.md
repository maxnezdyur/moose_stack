# Authoring: Misc module

`modules/misc` is a small catchall — not a coherent physics module. It currently hosts five themes only: a generalized sensor postprocessor framework, an Arrhenius material property, Soret/thermo-diffusion kernels (plus a `CoefDiffusion` partner), an enclosed-volume postprocessor, and a `GravityVectorInterface` mixin / `PhysicalConstants` header. Most "miscellaneous" requests should route OUT of here to a real module.

## When to use this (vs alternatives)

Decision tree — start by asking whether the request actually belongs in misc:

- **Sensor model with noise / drift / delay / efficiency / uncertainty** (thermocouple, strain gauge, pressure transducer, RTD, photodiode, ...)
  - Subclass `GeneralSensorPostprocessor` (`modules/misc/include/postprocessors/GeneralSensorPostprocessor.h:20`) and override only `getRVector()` for your impulse-response kernel. The base implements the noise/drift/efficiency/uncertainty math and the convolution-integral plumbing.
  - Canonical example: `ThermocoupleSensorPostprocessor` (`modules/misc/include/postprocessors/ThermocoupleSensorPostprocessor.h:18`) — only overrides `getRVector` with `exp(-(t-t')/τ)/τ`.
  - General postprocessor mechanics: see `postprocessor-authoring.md`.
- **Sum-of-Arrhenius material property** $\sum_i D_{0,i} \exp(-Q_i/RT)$
  - Use `ArrheniusMaterialProperty` / `ADArrheniusMaterialProperty` directly (`modules/misc/include/materials/ArrheniusMaterialProperty.h:14`). Vectors of `frequency_factor` and `activation_energy` already accept arbitrary $i$ — no new class needed for most cases.
  - If you need a fundamentally different temperature dependence, subclass it or write a new `Material` (see `material-authoring.md`).
- **Soret / thermo-diffusion (mass flux driven by ∇T)**
  - Non-AD with explicit Jacobian and off-diagonal: `ThermoDiffusion` (`modules/misc/include/kernels/ThermoDiffusion.h:37`).
  - AD with a single lumped `soret_coefficient`: `ADThermoDiffusion` (`modules/misc/include/kernels/ADThermoDiffusion.h:14`).
  - **Always pair with a Fick's-law diffusion kernel on the same variable** (`CoefDiffusion`, framework `MatDiffusion`, etc.) — see Pitfalls.
- **Enclosed-volume postprocessor on a closed sideset**
  - Use `InternalVolume` directly (`modules/misc/include/postprocessors/InternalVolume.h:25`). It already supports `component`, `scale_factor`, an additive `Function`, and uses the displaced mesh by default. Subclass only if you need a different integrand; otherwise just supply the sideset.
- **Gravity vector input on a component or kernel** — inherit `GravityVectorInterface` (`modules/misc/include/interfaces/GravityVectorInterface.h:18`) so users can specify either `gravity_vector` or `gravity_direction`+`gravity_magnitude`.
- **NIST physical constant** (Avogadro, Boltzmann, ideal gas, Stefan-Boltzmann, eV→J, cal→J, g) — `#include "PhysicalConstants.h"` (`modules/misc/include/utils/PhysicalConstants.h:12`). Header-only namespace; no class needed.

Routes OUT of misc:
- Anything heat-transfer-shaped (conduction kernels, gap, radiation) → `heat-transfer-authoring.md`.
- Density of a deforming body → solid-mechanics `StrainAdjustedDensity`. The misc `Density` is deprecated (sunset 2025-12-31).
- Plain coefficient-times-grad-grad diffusion → framework `MatDiffusion` / `FunctionDiffusion`. Only use misc `CoefDiffusion` when you specifically want the partner of `ThermoDiffusion` in legacy code.
- Generic constant or parsed material → framework `GenericConstantMaterial` / `ParsedMaterial`.
- Mesh-height interpolation auxkernel — already exists (`CoupledDirectionalMeshHeightInterpolation`); for new aux behavior see `auxkernel-authoring.md`.

## Contract

### **GeneralSensorPostprocessor** (`modules/misc/include/postprocessors/GeneralSensorPostprocessor.h:20`)
Purpose: sensor model that wraps an input-signal `Postprocessor` with drift, efficiency, noise (seeded `MooseRandom`), uncertainty, delay, and a convolution-integral term. Output combines proportional and integral contributions weighted by `proportional_weight` / `integral_weight`.
- **Required override (in subclass)**: `getRVector()` — returns the impulse-response vector $R(t-t')$ used in the integral term. Default base behavior pulls `R_function`.
- **Optional overrides**: `initialize()` (the base does the steady-state vs. transient bookkeeping; override only if your sensor has its own time logic).
- **validParams() additions**: required `PostprocessorName "input_signal"`; optional `FunctionName` parameters `drift_function`, `efficiency_function`, `noise_std_dev_function`, `signalToNoise_function`, `delay_function`, `uncertainty_std_dev_function`, `R_function`; `Real` weights and an `unsigned int seed`.
- State: declares restartable `_time_values`, `_input_signal_values`, `_integrand`, `_R_function_values`, `_t_step_old` — subclasses inherit these; do not redeclare.

### **ThermocoupleSensorPostprocessor** (`modules/misc/include/postprocessors/ThermocoupleSensorPostprocessor.h:18`)
Concrete subclass — example of the only override pattern that should normally be needed. Constructor errors out if the user tries to set `R_function` (the kernel is hard-coded to a first-order exponential lag).

### **ArrheniusMaterialProperty / ADArrheniusMaterialProperty** (`modules/misc/include/materials/ArrheniusMaterialProperty.h:14`)
Templated `Material` (`is_ad` template flag) declaring two `GenericMaterialProperty<Real, is_ad>`: `<property_name>` and `<property_name>_dT`. Sums an arbitrary number of Arrhenius branches.
- **Required overrides**: `computeQpProperties()`, `initQpStatefulProperties()` (already provided by the template — only override in a subclass if you need different functional form).
- **validParams() additions**: required `property_name`, coupled `temperature`, `frequency_factor` and `activation_energy` vectors (must be the same length, both non-empty); optional range-checked `gas_constant` (defaults to `PhysicalConstants::ideal_gas_constant`) and `initial_temperature`.
- Stateful: `_diffusivity` / `_diffusivity_dT` are stateful — initialized at `initial_temperature` so restarts and time-stepping are coherent.

### **ThermoDiffusion** (`modules/misc/include/kernels/ThermoDiffusion.h:37`)
Non-AD Soret kernel. Weak form: $-\nabla\cdot[D C Q^* / (RT^2) \nabla T]$. Couples temperature variable, reads `mass_diffusivity` and `heat_of_transport` `MaterialProperty<Real>` (default names — overridable by string param).
- **Required overrides (in subclass)**: `computeQpResidual()`, `computeQpJacobian()`. Off-diagonal Jacobian wrt `temp` is implemented and accounts for the $\nabla T / T^2$ chain rule — preserve that pattern in subclasses.
- **validParams() additions**: required `coupledVar "temp"`; optional `Real gas_constant` (default 8.3144621) and string property names for `mass_diffusivity` / `heat_of_transport`.

### **ADThermoDiffusion** (`modules/misc/include/kernels/ADThermoDiffusion.h:14`)
AD Soret kernel using a lumped `ADMaterialProperty<Real> "soret_coefficient"` instead of $D Q^* / RT^2$ split. Simpler residual: `_soret_coeff[_qp] * _grad_temp[_qp] * _grad_test[_i][_qp]`. Use this in new code unless you need the explicit decomposition.

### **InternalVolume** (`modules/misc/include/postprocessors/InternalVolume.h:25`)
`SideIntegralPostprocessor` computing enclosed volume by surface integral on a closed sideset. Sign convention: interior surface → positive, exterior surface → negative. Uses displaced mesh by default (`use_displaced_mesh = true`).
- **Required overrides (in subclass)**: `computeQpIntegral()`, `getValue()` already provided — override only if you change the integrand.
- **validParams() additions**: range-checked `component` (0..2), `scale_factor`, optional `addition` `FunctionName` for time-dependent volume offsets.

### **CoefDiffusion** (`modules/misc/include/kernels/CoefDiffusion.h:15`)
Plain `coef * grad(u) · grad(test)` kernel where `coef` is a `Real` or a `Function`. Exists primarily as the Fick's-law partner for `ThermoDiffusion`. For new code prefer framework `MatDiffusion` / `FunctionDiffusion` unless you specifically need this pairing.

### **GravityVectorInterface** (`modules/misc/include/interfaces/GravityVectorInterface.h:18`)
Mixin for objects needing a gravity vector. Adds `gravity_magnitude` (default `PhysicalConstants::acceleration_of_gravity`), `gravity_direction`, and `gravity_vector` parameters with mutual-exclusion checks. Exposes `gravityVector()` and `gravityMagnitude()` accessors.

### **PhysicalConstants** (`modules/misc/include/utils/PhysicalConstants.h:12`)
Header-only `namespace PhysicalConstants` with NIST-cited constants: `avogadro_number`, `boltzmann_constant`, `cal_to_J`, `eV_to_J`, `ideal_gas_constant`, `stefan_boltzmann_constant`, `acceleration_of_gravity`. No class — just include the header.

## Coupling & material properties

Misc-specific contracts — these are the strings/types other misc objects expect:

- `ThermoDiffusion` reads two `MaterialProperty<Real>`: `"mass_diffusivity"` (typically supplied by `ArrheniusMaterialProperty` with `property_name = mass_diffusivity`) and `"heat_of_transport"`. Names are overridable via string params.
- `ADThermoDiffusion` reads a single lumped `ADMaterialProperty<Real> "soret_coefficient"` instead — supply this from any AD material; `ADArrheniusMaterialProperty` is one option but you can also use a simple parsed material.
- `GeneralSensorPostprocessor` (and subclasses) consume one `PostprocessorValue` named `input_signal`. The signal flow is `Postprocessor → input_signal → sensor → output Postprocessor`. The sensor declares restartable state (`_time_values`, `_input_signal_values`, `_integrand`, `_R_function_values`, `_t_step_old`) — restart-safe out of the box.
- `ArrheniusMaterialProperty` declares both the property and its temperature derivative (`<property_name>` and `<property_name>_dT`). If your downstream object needs the derivative for off-diagonal Jacobians, request it by name.

## Registration & build

Standard `registerMooseObject("MiscApp", ClassName);` in the `.C` file. Templated AD/non-AD pairs register both type aliases (`Density` / `ADDensity`, `ArrheniusMaterialProperty` / `ADArrheniusMaterialProperty`).

Module flag in your app's `Makefile`: `MISC := yes`.

The interface `GravityVectorInterface` is not registered (no `registerMooseObject`) — it's a mixin, just `#include` and inherit.

Note: `Density` and `ADDensity` are registered with `registerMooseObjectDeprecated("MiscApp", Density, "12/31/2025 24:00")` (`modules/misc/src/materials/Density.C:12-13`). Do not extend or copy this pattern in new code; use solid-mechanics `StrainAdjustedDensity` or framework `GenericConstantMaterial`/`ParsedMaterial` instead.

## Minimal scaffold

A strain-gauge postprocessor — only override `getRVector()` for a different impulse response (e.g. critically-damped second-order: $R(t)=(t/τ^2)e^{-t/τ}$). Header + .C, ~25-30 lines each.

`include/postprocessors/StrainGaugeSensorPostprocessor.h`:

```cpp
#pragma once

#include "GeneralSensorPostprocessor.h"

/**
 * Strain-gauge sensor: critically-damped second-order impulse response.
 */
class StrainGaugeSensorPostprocessor : public GeneralSensorPostprocessor
{
public:
  static InputParameters validParams();
  StrainGaugeSensorPostprocessor(const InputParameters & parameters);

protected:
  virtual std::vector<Real> getRVector() override;
};
```

`src/postprocessors/StrainGaugeSensorPostprocessor.C`:

```cpp
#include "StrainGaugeSensorPostprocessor.h"

registerMooseObject("MiscApp", StrainGaugeSensorPostprocessor);

InputParameters
StrainGaugeSensorPostprocessor::validParams()
{
  InputParameters params = GeneralSensorPostprocessor::validParams();
  params.addClassDescription("Strain-gauge sensor with critically-damped second-order response.");
  return params;
}

StrainGaugeSensorPostprocessor::StrainGaugeSensorPostprocessor(const InputParameters & parameters)
  : GeneralSensorPostprocessor(parameters)
{
  if (isParamSetByUser("R_function"))
    mooseError("R_function is fixed for StrainGaugeSensorPostprocessor; use "
               "GeneralSensorPostprocessor to supply your own.");
}

std::vector<Real>
StrainGaugeSensorPostprocessor::getRVector()
{
  _R_function_values.clear();
  for (const auto i : index_range(_time_values))
  {
    const Real dt = _t - _time_values[i];
    _R_function_values.push_back(dt / (_delay_value * _delay_value) * std::exp(-dt / _delay_value));
  }
  return _R_function_values;
}
```

## Common pitfalls

- **`ThermoDiffusion` alone is unstable.** The Soret kernel must be paired with a Fick's-law diffusion kernel (`CoefDiffusion`, framework `MatDiffusion`, etc.) on the same variable. The header docstring at `modules/misc/include/kernels/ThermoDiffusion.h:27-29` calls this out — coupled diffusion terms (Nernst, Ettingshausen, Dufour also) need a regular diffusion partner or you get non-physical instability.
- **`Density` is deprecated (sunset 2025-12-31).** Use solid-mechanics `StrainAdjustedDensity` for deforming bodies, or `GenericConstantMaterial`/`ParsedMaterial` otherwise. Do not write new code that registers `Density`.
- **`CoefDiffusion` overlaps with framework `MatDiffusion` / `FunctionDiffusion`.** For new diffusion physics use the framework classes; reach for `CoefDiffusion` only when you specifically need the legacy `ThermoDiffusion` partner.
- **Sensor framework is sensor-agnostic.** `GeneralSensorPostprocessor` does not assume thermocouples — don't hard-code thermocouple-only validation, parameter names, or units in subclasses. The `ThermocoupleSensorPostprocessor` subclass is just one impulse-response choice.
- **Don't re-set `R_function` in a sensor subclass.** The base accepts `R_function` as a fallback; if your subclass implements `getRVector()` with a fixed kernel (as `ThermocoupleSensorPostprocessor` does), error in the constructor when `isParamSetByUser("R_function")` to avoid silent contradictions.
- **`ArrheniusMaterialProperty` requires equal-length, non-empty vectors.** `frequency_factor.size() == activation_energy.size() > 0` is enforced in the constructor — surface this as a `paramError` in any subclass that overrides validation.

