# Authoring: Heat Transfer module

How to extend `modules/heat_transfer`: thermal conduction kernels, convective and radiative BCs, gap-flux models for mortar gap conduction, and the wiring actions (`ThermalContact`, `MortarGapHeatTransfer`). All paths below are relative to the moose repo root.

## When to use this (vs alternatives)

Decide along three axes — discretization, AD, and gap formulation — then pick the chain:

- **New volumetric heat-conduction term** (e.g. anisotropic, source, time derivative)
  - FE + AD: extend `ADKernel`/`ADKernelGrad` against `ADMaterialProperty<Real> "thermal_conductivity"` (see `modules/heat_transfer/include/kernels/ADHeatConduction.h`).
  - FE + non-AD: extend `Diffusion` like `HeatConductionKernel` (`modules/heat_transfer/include/kernels/HeatConduction.h:24`).
  - FV: extend `FVDiffusion`-style or see `modules/heat_transfer/include/fvkernels/`.
  - Pure kernel mechanics: see `kernel-authoring.md`. Use this guide for the HT material-property contracts.
- **New surface heat exchange (convection / radiation / source)**
  - Convection with environment: extend `ADConvectiveHeatFluxBC` pattern (functor-based) or `ConvectiveHeatFluxBC` (material-property based).
  - Surface radiation to far-field: extend `RadiativeHeatFluxBCBase` (templated AD/non-AD) — only `coefficient()` is virtual; see `FunctionRadiativeBC` for the canonical example.
  - Enclosure (view-factor) radiation: use `RadiationTransferAction` + `GrayLambert*` user objects, not a new BC.
  - Generic surface BC mechanics: see `bc-authoring.md`.
- **Heat transfer across a gap** (two surfaces in contact / near contact)
  - Modular, mortar-based, AD-only: write a `GapFluxModelBase` subclass and wire it into `ModularGapConductanceConstraint` (recommended; see scaffold below).
  - Legacy node-on-face: use `GapHeatTransfer` BC + `GapConductance` material via `ThermalContactAction` (`type=GapHeatTransferModel` -> ALL legacy plumbing, including `PenetrationLocator`).
- **Anisotropic / temperature-dependent material data**: extend `HeatConductionMaterial` template or write a new `Material` producing `thermal_conductivity` / `specific_heat` / `density`. See `material-authoring.md` for `Material` mechanics.
- **Action wiring** (input-side sugar that creates several objects): use `ThermalContactAction` for legacy gap heat transfer, `MortarGapHeatTransferAction` for modular gap. Authoring an Action: `action-authoring.md`.

Cross-link: `solid-mechanics-authoring.md` for thermal expansion (`ComputeThermalExpansionEigenstrain`); `contact-authoring.md` shares primary/secondary surface vocabulary and `PenetrationLocator`.

## Contract

### **HeatConductionKernel** (`modules/heat_transfer/include/kernels/HeatConduction.h:24`)
Purpose: `-div(k grad T)` weak form against `MaterialProperty<Real> "thermal_conductivity"`.
- **Required overrides**: `computeQpResidual()`, `computeQpJacobian()`.
- **Optional overrides**: none (extends `Diffusion`; reuses its grad-test machinery).
- **validParams() additions**: required coupled `temperature` is implicit through `Diffusion`; subclass adds the conductivity property name if you want to override the default `"thermal_conductivity"`.
- Pairs with `ADHeatConduction` (`modules/heat_transfer/include/kernels/ADHeatConduction.h`) for the AD path — extend the AD class for new physics in modern apps.

### **ConvectiveHeatFluxBC pattern** (`modules/heat_transfer/include/bcs/ConvectiveHeatFluxBC.h:18`, `ADConvectiveHeatFluxBC.h:18`)
Purpose: `q = htc * (T - T_inf)` integrated over a sideset.
- **Required overrides**: `computeQpResidual()` (and `computeQpJacobian()` non-AD).
- **Optional overrides**: `initialSetup()` to resolve which side a functor lives on (the AD variant uses this to fall back to the neighbor element).
- **validParams() additions**: in non-AD form, `MaterialPropertyName` for `_T_infinity`, `_htc`, `_htc_dT`. In AD form, accept either `ADMaterialProperty<Real>` or `Moose::Functor<ADReal>` for both `T_infinity` and `htc` (mutually exclusive — exactly one source per quantity). For variable-coupled flavors see `CoupledConvectiveHeatFluxBC`.

### **RadiativeHeatFluxBCBase** (`modules/heat_transfer/include/bcs/RadiativeHeatFluxBCBase.h:19`, templated on `is_ad`)
Purpose: `q = sigma * coeff * (T^4 - T_inf^4)` against a far-field temperature `Function`.
- **Required overrides**: `coefficient()` — pure virtual; returns the emissivity/view-factor product that scales the Stefan-Boltzmann term.
- **Optional overrides**: `computeQpResidual()` (rarely; the base does the T^4 - Tinf^4 algebra), `computeQpJacobian()` (non-AD only).
- **validParams() additions**: `_sigma_stefan_boltzmann` (defaulted), `_tinf` `FunctionName` (required). Subclasses add their own emissivity inputs. See `FunctionRadiativeBC` (one Function emissivity), `InfiniteCylinderRadiativeBC` (geometry factor), `GrayLambertNeumannBC` (enclosure radiation, supplies coefficient from a view-factor user object).

### **GapFluxModelBase** (`modules/heat_transfer/include/userobjects/GapFluxModelBase.h:19`)
Purpose: AD user-object plug-in that supplies `flux = h_gap * (T_secondary - T_primary)` (or radiation variant) to `ModularGapConductanceConstraint`. Inherits `InterfaceUserObjectBase` + `ADFunctorInterface`.
- **Required overrides**: `computeFlux() const` — pure virtual; return an `ADReal` flux at the cached `_qp` using `_gap_width`, `_adjusted_length`, `_normal_pressure`, and the cached `_secondary_point` / `_primary_point` `ElemPointArg`s.
- **Optional overrides**: `computeFluxInternal(const ModularGapConductanceConstraint &)` if you need to grab additional geometric state from the constraint. Do NOT override `finalize()` / `threadJoin()` — they're `final` and intentional no-ops.
- **validParams() additions**: subclass adds whatever it couples (e.g. `temperature`, `gap_conductivity`, emissivities). Convention: coupled temperatures use `adCoupledValue("temperature")` for secondary and `adCoupledNeighborValue("temperature")` for primary.
- Companion bases for common patterns: `GapFluxModelConductionBase` (provides `computeConductionFlux(secT, primT, k_mult)` and gap attenuation), `GapFluxModelRadiationBase` (provides `computeRadiationFlux`).

### **HeatConductionMaterial** (`modules/heat_transfer/include/materials/HeatConductionMaterial.h:22`, templated on `is_ad`)
Purpose: declares `thermal_conductivity`, `thermal_conductivity_dT`, `specific_heat` (and optionally `_dT`) as constants or `Function`s of `temperature`.
- **Required overrides**: `computeQpProperties()`.
- **Optional overrides**: nothing else; subclass to introduce composition-dependent or anisotropic forms (see `AnisoHeatConductionMaterial`).
- **validParams() additions**: `thermal_conductivity` (Real or Function-name), `specific_heat`, optional `temp` coupled var, optional `min_T` clip.

### **GapConductance** (`modules/heat_transfer/include/materials/GapConductance.h:17`, legacy node-on-face)
Purpose: `h_gap = h_conduction + h_contact + h_radiation` evaluated against `PenetrationLocator` data.
- **Required overrides**: `computeQpConductance()` if you replace the closure model; otherwise inherit the default that calls `h_conduction()`, `h_radiation()`, etc.
- **Optional overrides**: `h_conduction()`, `h_radiation()`, `dh_conduction()`, `dh_radiation()`, `gapK()`.
- **validParams() additions**: most users go through `ThermalContactAction`, which forwards parameters via `GapConductance::actionParameters()`.

### **ThermalContactAction** (`modules/heat_transfer/include/actions/ThermalContactAction.h:16`)
Purpose: legacy "one-line" gap-heat-transfer setup — adds `GapHeatTransfer` BC, `GapConductance` material, penetration aux variable + aux kernel, optional secondary-flux vector, and the relationship managers.
- **Required overrides**: `act()` (already implemented).
- **Optional overrides** (when subclassing for a custom variant): `addBCs`, `addMaterials`, `addAuxVariables`, `addAuxKernels`, `addDiracKernels`, `addSecondaryFluxVector`, `addRelationshipManagers`.
- **validParams() additions**: `primary`/`secondary` boundary pairs, `type` enum (`GapHeatTransferModel`), `quadrature` flag, `variable` (temperature). For modular mortar gap, prefer `MortarGapHeatTransferAction` (`modules/heat_transfer/include/actions/MortarGapHeatTransferAction.h:26`), which builds the mortar mesh, adds the LM variable, the `ModularGapConductanceConstraint`, and the requested `GapFluxModel*` user objects.

## Coupling & material properties

HT-specific naming conventions; mismatches here are the most common source of silent wrong answers.

- **`thermal_conductivity`** (`MaterialProperty<Real>` or `ADMaterialProperty<Real>`) — `W/(m·K)` (or app-consistent unit). Provided by `HeatConductionMaterial`. Anisotropic variants use `RankTwoTensor` / `RealTensorValue` and a different property name (`thermal_conductivity` is reserved for the scalar).
- **`specific_heat`** + **`density`** — both required for transient kernels. `HeatConductionTimeDerivative` consumes both via `rho * c_p * dT/dt`. `HeatCapacityConductionTimeDerivative` instead consumes a single combined `heat_capacity` property — DO NOT supply both `specific_heat`+`density` and `heat_capacity` for the same domain (double counting).
- **`thermal_conductivity_dT`** — required for non-AD Jacobians (`HeatConductionMaterial` produces it automatically; if you write your own non-AD material you must declare it). AD path doesn't need it.
- **Convective BC inputs**: non-AD takes `MaterialProperty<Real>` named via `T_infinity` and `htc` (plus `htc_dT`). AD takes either `ADMaterialProperty<Real>` OR `Moose::Functor<ADReal>` — choose one source per quantity.
- **Gap conductance vocabulary** (easy to swap):
  - `gap_conductivity` — bulk thermal conductivity of the gas in the gap, `W/(m·K)`.
  - `gap_conductance` — areal conductance `h_gap`, `W/(m^2·K)` = `gap_conductivity / gap_width` (after attenuation).
  - `gap_conductance` is what `GapHeatTransfer` BC consumes from a `MaterialProperty<Real>` named `gap_conductance`. `GapConductance` material declares it.
- **`PenetrationLocator` dependency**: legacy `GapHeatTransfer` BC + `GapConductance` material both query `_penetration_locator->_penetration_info` to find the paired primary point. Requires `ThermalContactAction` (or manual setup of `PenetrationAux` and the locator). Mortar gap path does NOT use `PenetrationLocator`; it uses the mortar mesh built by `MortarGapHeatTransferAction`.
- **Mortar mesh for modular gap**: `MortarGapHeatTransferAction` creates a lower-dimensional `secondary_subdomain`, an LM variable (the gap heat flux), and registers the `ModularGapConductanceConstraint` on the primary/secondary boundary pair. The constraint caches `_gap_width`, `_adjusted_length`, `_normal_pressure` into each `GapFluxModelBase` user object before invoking `computeFlux()`.
- **AD-only requirement**: `ModularGapConductanceConstraint` extends `ADMortarConstraint`. All `GapFluxModelBase` subclasses MUST be AD; there is no non-AD path.

## Registration & build

- `registerMooseObject("HeatTransferApp", YourClass);` at the top of every `.C`. The app name is `HeatTransferApp` (NOT `MooseApp` or `SolidMechanicsApp`); using the wrong name silently drops registration.
- Headers under `modules/heat_transfer/include/<category>/`, sources mirror under `modules/heat_transfer/src/<category>/`. Categories: `kernels`, `bcs`, `fvkernels`, `fvbcs`, `materials`, `functormaterials`, `constraints`, `userobjects`, `actions`, `auxkernels`, `postprocessors`, `vectorpostprocessors`, `interfacekernels`, `dirackernels`, `meshgenerators`, `physics`, `raybcs`, `linearfvbcs`, `linearfvkernels`.
- Module activation: in a downstream app's top-level `Makefile`, `HEAT_TRANSFER := yes` before `include $(FRAMEWORK_DIR)/build.mk`. The combined `moose-combined` target enables it by default. Test via `cd modules/heat_transfer && make -j N`.
- Doc page lives at `modules/heat_transfer/doc/content/source/<category>/YourClass.md` — required for SQA. See `moose-doc-standards`.

## Minimal scaffold

A minimal `GapFluxModelBase` subclass — the most common HT extension. This one is a constant-conductance plug-in that takes a single coupled temperature variable and a constant gap conductivity.

`modules/heat_transfer/include/userobjects/GapFluxModelConstant.h`:

```cpp
#pragma once

#include "GapFluxModelBase.h"

/**
 * Trivial gap flux model: q = (k / gap_width) * (T_secondary - T_primary).
 */
class GapFluxModelConstant : public GapFluxModelBase
{
public:
  static InputParameters validParams();

  GapFluxModelConstant(const InputParameters & parameters);

  virtual ADReal computeFlux() const override;

protected:
  /// Secondary surface temperature
  const ADVariableValue & _secondary_T;
  /// Primary (neighbor) surface temperature
  const ADVariableValue & _primary_T;
  /// Constant gap conductivity (W/(m·K))
  const Real _gap_conductivity;
};
```

`modules/heat_transfer/src/userobjects/GapFluxModelConstant.C`:

```cpp
#include "GapFluxModelConstant.h"

registerMooseObject("HeatTransferApp", GapFluxModelConstant);

InputParameters
GapFluxModelConstant::validParams()
{
  InputParameters params = GapFluxModelBase::validParams();
  params.addClassDescription(
      "Constant-conductivity gap flux model for ModularGapConductanceConstraint.");
  params.addRequiredCoupledVar("temperature", "Temperature variable on both sides of the gap");
  params.addRequiredParam<Real>("gap_conductivity",
                                "Thermal conductivity of the gap (W/(m*K))");
  return params;
}

GapFluxModelConstant::GapFluxModelConstant(const InputParameters & parameters)
  : GapFluxModelBase(parameters),
    _secondary_T(adCoupledValue("temperature")),
    _primary_T(adCoupledNeighborValue("temperature")),
    _gap_conductivity(getParam<Real>("gap_conductivity"))
{
}

ADReal
GapFluxModelConstant::computeFlux() const
{
  // _gap_width and _qp are populated by ModularGapConductanceConstraint before this call.
  return _gap_conductivity / _gap_width * (_secondary_T[_qp] - _primary_T[_qp]);
}
```

Wire it in input:

```
[UserObjects]
  [my_gap]
    type = GapFluxModelConstant
    temperature = T
    gap_conductivity = 0.025
    boundary = secondary_surface
  []
[]
[Constraints]
  [gap_constraint]
    type = ModularGapConductanceConstraint
    primary_boundary = primary_surface
    secondary_boundary = secondary_surface
    primary_subdomain = primary_lower
    secondary_subdomain = secondary_lower
    variable = lm
    secondary_variable = T
    gap_flux_models = 'my_gap'
  []
[]
```

(Or let `MortarGapHeatTransferAction` build the constraint, mortar mesh, and LM variable for you.)

## Common pitfalls

1. **`gap_conductance` vs `gap_conductivity` vs `gap_thermal_conductivity`** — `conductance` is areal (`W/(m^2·K)`), `conductivity` is bulk material (`W/(m·K)`). `GapConductance` material declares all three; `GapHeatTransfer` BC reads `gap_conductance`. Mortar `GapFluxModel*` typically takes `gap_conductivity` and divides by `_gap_width` itself. Mixing them gives a result wrong by a factor of the gap width (often orders of magnitude).
2. **Double-counting heat capacity** — `HeatConductionTimeDerivative` uses `density * specific_heat`; `HeatCapacityConductionTimeDerivative` uses `heat_capacity`; `SpecificHeatConductionTimeDerivative` uses `specific_heat` only (assumes density baked in elsewhere). Pick one per block.
3. **Mortar gap is AD-only** — `ModularGapConductanceConstraint` derives from `ADMortarConstraint`. A non-AD `GapFluxModel` subclass will not compile against this base. If you must stay non-AD, use the legacy `GapHeatTransfer` + `ThermalContactAction` path.
4. **`ThermalContactAction` "type" is the model, not the action** — `[ThermalContact/foo] type = GapHeatTransferModel` selects the legacy node-on-face model. It does NOT route to mortar; for mortar use `[MortarGapHeatTransfer/foo]` (a separate action).
5. **`JouleHeatingSource` vs `ADJouleHeatingSource`** — the non-AD form is deprecated; new code should use `ADJouleHeatingSource` with `electric_potential` and an AD `electrical_conductivity`. Mixing AD electrical conductivity with non-AD Joule heating breaks the Jacobian.
6. **Surface radiation BC vs enclosure radiation** — `RadiativeHeatFluxBCBase` subclasses model exchange with a far-field temperature `Function` (one-sided). Enclosure radiation (mutual surface-to-surface within a cavity) needs `RadiationTransferAction` plus view-factor user objects (`ViewFactorBase` subclasses) and `GrayLambertNeumannBC` — do NOT try to express this with multiple `RadiativeHeatFluxBC`s.
7. **Functor convective BC, primary-vs-neighbor side** — `ADConvectiveHeatFluxBC::initialSetup` decides whether each functor lives on the boundary side or the neighbor side. If a functor is defined on a subdomain that doesn't touch the sideset on the primary side, it silently switches to the neighbor; defining it on neither side errors at setup.

