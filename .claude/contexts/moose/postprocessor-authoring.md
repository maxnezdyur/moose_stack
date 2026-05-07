# Authoring: Postprocessors, VectorPostprocessors, and Reporters

These three systems all *produce values for the rest of the simulation to consume* (other UOs, AuxKernels, output, controls, multiapps). Postprocessor produces a single `Real`; VectorPostprocessor produces named `std::vector<Real>` columns; Reporter produces arbitrary typed values and is the modern generalization that supersedes both.

## When to use this (vs alternatives)

Decision tree:

- **Need a single scalar value (one number per timestep) consumable by other objects?**
  - No mesh loop needed — derive from `GeneralPostprocessor` (e.g. arithmetic on other PPs, control-system coupling, a function evaluated at a fixed point). (`framework/include/postprocessors/GeneralPostprocessor.h:21`)
  - Volume / element-loop scalar (integral, average, extreme value over elements) — derive from `ElementIntegralPostprocessor` or `ElementPostprocessor`. (`framework/include/postprocessors/ElementIntegralPostprocessor.h:20`, `framework/include/postprocessors/ElementPostprocessor.h:15`)
  - Sideset / boundary integral — `SideIntegralPostprocessor` / `SidePostprocessor`. (`framework/include/postprocessors/SideIntegralPostprocessor.h:20`, `framework/include/postprocessors/SidePostprocessor.h:18`)
  - Internal-side (interior face) loop — `InternalSidePostprocessor`. (`framework/include/postprocessors/InternalSidePostprocessor.h:15`)
  - Interface (between two subdomains) — `InterfacePostprocessor`. (`framework/include/postprocessors/InterfacePostprocessor.h:21`)
  - Per-node scalar reduction — `NodalPostprocessor`. (`framework/include/postprocessors/NodalPostprocessor.h:16`)
- **Need a 1-D vector / table of named columns (e.g. samples along a line, histogram)?** Use a `VectorPostprocessor`. The mixin `VectorPostprocessor` (`framework/include/vectorpostprocessors/VectorPostprocessor.h:34`) is combined with one of the UO scope mixins:
  - General — `GeneralVectorPostprocessor`. (`framework/include/vectorpostprocessors/GeneralVectorPostprocessor.h:21`)
  - Element loop — `ElementVectorPostprocessor`. (`framework/include/vectorpostprocessors/ElementVectorPostprocessor.h:15`)
  - "Sampler" pattern (one row per sample point with `x,y,z,id,...` columns) — derive *also* from `SamplerBase`. (`framework/include/vectorpostprocessors/SamplerBase.h:37`) Concrete sampler examples: `NodalValueSampler` (`framework/include/vectorpostprocessors/NodalValueSampler.h:18`), `LineValueSampler` (`framework/include/vectorpostprocessors/LineValueSampler.h:16`).
- **Need arbitrary typed values (a struct, a `std::vector<std::vector<Real>>`, an `nlohmann::json`, multiple values per object)?** Use a **Reporter** / `GeneralReporter`. Reporter is the modern superset of PP and VPP — every `Postprocessor` is in fact registered as a `ReporterValue<PostprocessorValue>` under the hood, and every VPP column lives in the same `ReporterData` store. (`framework/include/reporters/Reporter.h:47`, `framework/include/reporters/GeneralReporter.h:18`)
- **Just want to terminate a run when a condition is hit?** Wrong tool — use a `Terminator` (see [userobject-authoring.md](./userobject-authoring.md)).
- **Want to display a value as a field in Exodus?** Wrong tool — use an [AuxKernel](./auxkernel-authoring.md). PPs/VPPs/Reporters are scalars/tables, not field variables.
- **Need a side-effect-only computation (transfer to another app, accumulate state) with no exposed value?** Use a [UserObject](./userobject-authoring.md) directly.

Pick the smallest scope that covers what you must read: General (no mesh loop, cheapest) → Nodal → Element → Side / InternalSide / Interface.

## Contract

### **Postprocessor** (`framework/include/postprocessors/Postprocessor.h:23`)

Purpose: abstract base for the single-`Real` producer. Inherits `OutputInterface`, `NonADFunctorInterface`, `Moose::FunctorBase<Real>` — every Postprocessor *is a functor* and can be consumed wherever a `Functor<Real>` is accepted (functor evaluation returns the constant value at the last execute).

- **Pure virtual**: `PostprocessorValue getValue() const` (`Postprocessor.h:46`). `PostprocessorValue` is a typedef for `Real`.
- The "current value" — what consumers see — is `_current_value` (`Postprocessor.h:80`), a `const Real &` bound at construction to the PP's auto-declared Reporter slot. Consumers reading the PP get this slot, not the result of `getValue()`. The problem calls `getValue()` once when the UO executes and copies the return into `_current_value`.
- You almost never derive directly from `Postprocessor`; pick a scope subclass below.

### **GeneralPostprocessor** (`framework/include/postprocessors/GeneralPostprocessor.h:21`)

Purpose: scalar producer with no mesh loop. Inherits `GeneralUserObject` + `Postprocessor`.

- **Required override**: `getValue()` (returning the scalar).
- **Optional overrides**: `initialize()`, `execute()`, `finalize()` — same lifecycle as `GeneralUserObject`. Default `finalize()` is empty.
- Dependency resolution between GeneralPostprocessors is automatic.

### **ElementPostprocessor** (`framework/include/postprocessors/ElementPostprocessor.h:15`)

Purpose: arbitrary per-element reduction. Inherits `ElementUserObject` + `Postprocessor`.

- **Required overrides**: `execute()` (called for each element), `getValue()`, `initialize()`, `threadJoin(const UserObject &)`, optionally `finalize()`.
- `_current_elem`, `_qrule`, `_q_point`, `_JxW`, `_coord` are available from `ElementUserObject`.

### **ElementIntegralPostprocessor** (`framework/include/postprocessors/ElementIntegralPostprocessor.h:20`)

Purpose: convenient base for the *very common* "integrate something over the volume" pattern. Implements `initialize/execute/threadJoin/getValue/finalize` for you. (`framework/src/postprocessors/ElementIntegralPostprocessor.C:21-65`)

- **Required override**: `Real computeQpIntegral()` returning the integrand value at quadrature point `_qp`. The base multiplies by `_JxW[_qp] * _coord[_qp]` and sums into `_integral_value`. (`ElementIntegralPostprocessor.C:52-58`)
- **Optional override**: `Real computeIntegral()` if you need to skip the standard JxW loop.
- `finalize()` already calls `gatherSum(_integral_value)`. (`ElementIntegralPostprocessor.C:62-65`)

### **ElementIntegralVariablePostprocessor** (`framework/include/postprocessors/ElementIntegralVariablePostprocessor.h:21`)

Refinement of the above: pulls a coupled variable for you (`_u`, `_grad_u`, `_use_abs_value`). Override `computeQpIntegral()` to use those.

### **SidePostprocessor** (`framework/include/postprocessors/SidePostprocessor.h:18`)

Per-face reduction over one or more sidesets. Inherits `SideUserObject` + `Postprocessor`. Same override pattern as `ElementPostprocessor` (`execute()`, `getValue()`, `threadJoin`).

### **SideIntegralPostprocessor** (`framework/include/postprocessors/SideIntegralPostprocessor.h:20`)

Convenience for "integrate something over a sideset". Provides `_qp_integration` flag (qp loop vs FaceInfo loop, for FV).

- **Required override**: `Real computeQpIntegral()`.
- **Optional override**: `Real computeFaceInfoIntegral(const FaceInfo *)` for finite-volume face traversal; the default `mooseError`s.

### **InternalSidePostprocessor** (`framework/include/postprocessors/InternalSidePostprocessor.h:15`)

Loop over interior faces. Inherits `InternalSideUserObject` + `Postprocessor`. Useful for jump norms, flux balances across interior boundaries.

### **InterfacePostprocessor** (`framework/include/postprocessors/InterfacePostprocessor.h:21`)

For interfaces between two subdomains. Computes the primary-side area for you (`_interface_primary_area`); already provides `initialize/execute/threadJoin/finalize` to maintain it. Override `execute()` (and call the base) for your extra work.

### **NodalPostprocessor** (`framework/include/postprocessors/NodalPostprocessor.h:16`)

Per-node reduction (e.g. extreme nodal value). Inherits `NodalUserObject` + `Postprocessor`. `execute()` is called once per node; access `_current_node`. Override `getValue()`, `initialize()`, `threadJoin()`.

### **VectorPostprocessor** (mixin) (`framework/include/vectorpostprocessors/VectorPostprocessor.h:34`)

Purpose: produces one or more named `std::vector<Real>` columns ("vectors"). Always combined with a UO scope mixin (`GeneralVectorPostprocessor`, `ElementVectorPostprocessor`, `NodalVectorPostprocessor`, `SideVectorPostprocessor`, `InternalSideVectorPostprocessor`, `InterfaceVectorPostprocessor`).

- **Required**: in the constructor, declare each column with `VectorPostprocessorValue & declareVector("col_name")` (`VectorPostprocessor.h:74`). `VectorPostprocessorValue` is a typedef for `std::vector<Real>`. Store the returned reference and `push_back` / resize during `execute()`.
- **Lifecycle**: same as the underlying UO — `initialize()` clears, `execute()` appends, `threadJoin()` merges per-thread state, `finalize()` MPI-reduces.
- **Parallel mode**: by default the columns are *replicated* (gathered to root and broadcast to all). Set `_parallel_type = DISTRIBUTED` (input param `parallel_type`) when each rank should keep its own slice. Inspect via `isDistributed()` (`VectorPostprocessor.h:63`). `containsCompleteHistory()` returns whether successive executes accumulate (history) versus overwrite.

### **SamplerBase** (`framework/include/vectorpostprocessors/SamplerBase.h:37`)

Purpose: standardize the "row-per-sample-point" VPP shape with `x,y,z,id,<variable columns>`. Use as a **second base class** alongside a VPP scope class (e.g. `class MySampler : public NodalVariableVectorPostprocessor, protected SamplerBase`).

- **Constructor must call**: `setupVariables(variable_names)` (`SamplerBase.h:60`).
- **Required override hooks** (call the base versions):
  - `initialize()` — call `SamplerBase::initialize()`.
  - `threadJoin(const SamplerBase & y)` — call `SamplerBase::threadJoin(y)`.
  - `finalize()` — call `SamplerBase::finalize()`.
- `addSample(const Point & p, Real id, const std::vector<Real> & values)` (`SamplerBase.h:77`) is what you call inside your `execute()`. Sort key controlled by `sort_by` input.

### **Reporter** (`framework/include/reporters/Reporter.h:47`)

Purpose: abstract base for arbitrary-typed value producers. Inherits `OutputInterface`. *Not* a `MooseObject` itself — combine with a UO scope class. `GeneralReporter` is the only ready-made combination in the framework; for Element/Side/Nodal Reporters subclass directly (e.g. `ElementReporter` — `framework/include/reporters/ElementReporter.h`).

- **Required (in the constructor only)**: declare each value with `T & declareValue<T>("param_name")` or `declareValueByName<T>(value_name)` (`Reporter.h:122-138`). The returned reference is your write target. Optionally pass a `ReporterMode` and a `ReporterContext` template (e.g. `ReporterBroadcastContext`, `ReporterScatterContext`).
- **Storage names**: `ReporterName(object, value)` (`framework/include/reporters/ReporterName.h:30`); accessed as `object/value` in input.
- **No `getValue()` and no auto-functor wrapper** — Reporters are read by *consumers* via `ReporterInterface::getReporterValue<T>("name")`.
- `declareLateValues()` (`Reporter.h:79`) is a hook for values that depend on what *other* Reporters declared (resolved during the `declare_late_reporters` task).
- **`shouldStore()`** controls whether the value is stored on a given execute flag (defaults to true; `GeneralReporter` overrides to honor `execute_on` more strictly).

### **GeneralReporter** (`framework/include/reporters/GeneralReporter.h:18`)

Purpose: ready-made `Reporter + GeneralUserObject` combination. Threading is finalized off (`threadJoin()` is `final` and empty).

- **Required overrides**: `initialize()`, `execute()`, `finalize()` (typically empty bodies on at least one of these are common for "static" reporters like `ConstantReporter` — `framework/include/reporters/ConstantReporter.h:14`).
- Declare values **in the constructor**, then populate them in `execute()` / `finalize()`.

### **ReporterMode** (`framework/include/reporters/ReporterMode.h:34`)

Modes describe parallel availability of a value at *both* producer and consumer side. Mismatches are reconciled (or rejected) by `ReporterContext`.

- `REPORTER_MODE_ROOT` — value correct only on the root rank. Default.
- `REPORTER_MODE_REPLICATED` — value correct **and identical** on every rank.
- `REPORTER_MODE_DISTRIBUTED` — value correct on every rank but **different per rank** (used for partition-local vectors).
- `REPORTER_MODE_UNSET` — let the context decide.

## Coupling & material properties

- `coupledValue`, `coupledGradient`, `getMaterialProperty<...>`, `getADMaterialProperty<...>` work in any mesh-loop variant (Element/Side/InternalSide/Interface/Nodal). They are *not* available in `GeneralPostprocessor` / `GeneralVectorPostprocessor` / `GeneralReporter` because there is no element/qp context.
- `getFunctor<Real>("f")` works in all variants and is the modern cross-cutting consumption channel.
- `getPostprocessorValue("pp")` and `getReporterValue<T>("rep")` work in all variants.
- **Threading & threadJoin**: `ElementPostprocessor`, `SidePostprocessor`, `InternalSidePostprocessor`, `NodalPostprocessor`, and the corresponding VPPs are threaded over the mesh loop. You **must** override `threadJoin(const UserObject & y)`, downcast `y` to your concrete type, and merge the per-thread state (sum partial integrals, take min/max of partial extremes, append per-thread vectors). `ElementIntegralPostprocessor::threadJoin` (`framework/src/postprocessors/ElementIntegralPostprocessor.C:45-49`) is the textbook example. `GeneralPostprocessor`, `GeneralVectorPostprocessor`, and `GeneralReporter` are *not* threaded — `GeneralReporter::threadJoin` is `final` and empty (`GeneralReporter.h:25`).
- **MPI gather in `finalize()`**: this is where you reduce across ranks. Use `gatherSum(x)`, `gatherMin(x)`, `gatherMax(x)`, `gatherProxyValueMax(...)`, `_communicator.sum(x)`, `_communicator.allgather(...)`. Doing MPI in `execute()` or `getValue()` is wrong — `getValue()` is `const` and called potentially after `finalize()`; doing collective communication there will hang.
- **ReporterContext mediation**: when a producer declares mode `ROOT` and a consumer asks for `REPLICATED`, `ReporterContext::finalize()` performs the broadcast. `ReporterBroadcastContext`, `ReporterScatterContext`, `ReporterGatherContext`, `VectorPostprocessorContext` (`VectorPostprocessor.h:118`) are pre-built specializations.

## Registration & build

- All three are MooseObjects and register the same way: in the `.C` file, `registerMooseObject("MooseApp", MyPostprocessor);` (or the app's namespace, e.g. `"BlackbearApp"`, `"IsopodApp"`). Same call for VPPs and Reporters.
- The **base** `Postprocessor` constructor *automatically* declares a Reporter value of type `PostprocessorValue` under the name `<object_name>/value` (see `Postprocessor::declareValue` — `Postprocessor.h:87`). That is why `getReporterValue<PostprocessorValue>("my_pp/value")` works on any Postprocessor and why `_current_value` is a `const Real &` bound to that Reporter slot.
- Consumer interfaces:
  - `PostprocessorInterface::getPostprocessorValue(...)` for PPs.
  - `VectorPostprocessorInterface::getVectorPostprocessorValue(...)` (and `getScatterVectorPostprocessorValue` for distributed scatter) for VPPs.
  - `ReporterInterface::getReporterValue<T>(...)` for Reporters (and is the lower-level path that PPs and VPPs ride on).
- Tests live under `test/tests/postprocessors`, `test/tests/vectorpostprocessors`, `test/tests/reporters` in `moose/`. Each new object should ship with at least a CSV gold file or `RunApp` test.

## Minimal scaffolds

### 1. ElementIntegralPostprocessor — integrate `u * k` over the domain

```cpp
// MyEnergyPP.h
#pragma once
#include "ElementIntegralPostprocessor.h"
#include "MooseVariableInterface.h"

class MyEnergyPP : public ElementIntegralPostprocessor,
                   public MooseVariableInterface<Real>
{
public:
  static InputParameters validParams();
  MyEnergyPP(const InputParameters & params);

protected:
  Real computeQpIntegral() override;
  const VariableValue & _u;
  const MaterialProperty<Real> & _k;
};
```

```cpp
// MyEnergyPP.C
#include "MyEnergyPP.h"
registerMooseObject("MooseApp", MyEnergyPP);

InputParameters
MyEnergyPP::validParams()
{
  auto p = ElementIntegralPostprocessor::validParams();
  p.addRequiredCoupledVar("variable", "Field to integrate");
  p.addRequiredParam<MaterialPropertyName>("conductivity", "k(x)");
  return p;
}

MyEnergyPP::MyEnergyPP(const InputParameters & params)
  : ElementIntegralPostprocessor(params),
    MooseVariableInterface<Real>(this, false),
    _u(coupledValue("variable")),
    _k(getMaterialProperty<Real>("conductivity")) {}

Real
MyEnergyPP::computeQpIntegral() { return _u[_qp] * _k[_qp]; }
```

`initialize`, `execute`, `threadJoin`, `getValue`, `finalize` (with `gatherSum`) are inherited.

### 2. GeneralReporter — emit two vectors of doubles per timestep

```cpp
// MyHistoryReporter.h
#pragma once
#include "GeneralReporter.h"

class MyHistoryReporter : public GeneralReporter
{
public:
  static InputParameters validParams();
  MyHistoryReporter(const InputParameters & params);

  void initialize() override {}
  void execute() override;
  void finalize() override {}

protected:
  std::vector<Real> & _times;
  std::vector<Real> & _energies;
  const PostprocessorValue & _energy_pp;
};
```

```cpp
// MyHistoryReporter.C
#include "MyHistoryReporter.h"
registerMooseObject("MooseApp", MyHistoryReporter);

InputParameters
MyHistoryReporter::validParams()
{
  auto p = GeneralReporter::validParams();
  p.addRequiredParam<PostprocessorName>("energy_pp", "PP to log");
  return p;
}

MyHistoryReporter::MyHistoryReporter(const InputParameters & params)
  : GeneralReporter(params),
    _times(declareValue<std::vector<Real>>("times", REPORTER_MODE_REPLICATED)),
    _energies(declareValue<std::vector<Real>>("energies", REPORTER_MODE_REPLICATED)),
    _energy_pp(getPostprocessorValue("energy_pp")) {}

void
MyHistoryReporter::execute()
{
  _times.push_back(_t);
  _energies.push_back(_energy_pp);
}
```

Consumers read `my_history/times` and `my_history/energies`.

## Common pitfalls

1. **Forgetting `threadJoin()` in a threaded subclass.** Element/Side/Nodal PPs and VPPs are threaded; if you don't sum/extract per-thread state, you silently get only the master thread's result. The downcast pattern is `static_cast<const MyClass &>(y)`, then merge fields. (See `ElementIntegralPostprocessor.C:45-49`.)
2. **MPI calls outside `finalize()`.** `gatherSum` / `_communicator.sum` in `execute()` deadlocks under threading; in `getValue()` it deadlocks because `getValue()` is `const` and may be called multiple times by consumers after the UO has run. Always reduce in `finalize()`.
3. **Declaring Reporter values *after* the constructor.** `declareValue<T>` and `declareValueByName<T>` must be called in the constructor (or in `declareLateValues()` for the late-binding case). Calling in `initialize()` or `execute()` will fail because `ReporterData` is locked after the `add_reporters` task.
4. **Confusing `PostprocessorValue` (a typedef for `Real`) with the auto-registered Reporter slot.** A `Postprocessor` always exposes a Reporter named `<name>/value`. If you declare *another* Reporter value also called `value`, you'll collide. Use a different value name.
5. **Reading `getValue()` to get the "current" PP value.** `getValue()` is intended only for the problem to call when the UO is executed. Other consumers should use `_current_value` (or, equivalently, `getReporterValue<PostprocessorValue>(...)`) — calling `getValue()` may run a stale or incorrect reduction. (`Postprocessor.h:39-63`)
6. **VPP columns being parallel-distributed by default.** A `VectorPostprocessor`'s columns are **replicated** by default — every rank carries a full copy after `finalize()`. If you set `parallel_type = DISTRIBUTED`, consumers must opt into a distributed read (`isDistributed()` is your check; many output / consumer paths still assume replicated). Conversely, if you forget to think about parallelism and `push_back` from each rank in `execute()`, your "replicated" output will contain duplicates — you need an explicit `_communicator.gather`/`sum` in `finalize()` or rely on `SamplerBase` which handles this.
7. **Forgetting that `GeneralReporter` is unthreaded.** `threadJoin` is `final` and empty (`GeneralReporter.h:25`); if your "general" Reporter actually needs per-element state, you picked the wrong base — derive from `ElementReporter` (or roll your own `Reporter + ElementUserObject`).

