# Authoring: Stochastic Tools module

The `stochastic_tools` module is MOOSE's framework for forward UQ, surrogate fitting/evaluation, Bayesian inference, and active learning. It glues a `Sampler` (which generates parameter rows) to a `SamplerFullSolveMultiApp` (which runs sub-apps per row), with `Transfer`s that push parameters in and pull QoI reporters out, optional `SurrogateTrainer`/`SurrogateModel` pairs, and a `StochasticReporter` that aggregates per-row outputs.

## When to use this (vs alternatives)

Decision tree, leading with most common UQ task:

1. **Forward UQ / propagating input distributions through a model.**
   - Pick a `Sampler` (`MonteCarloSampler`, `LatinHypercubeSampler`, `QuadratureSampler`, `CartesianProductSampler`, …) driven by `Distribution`s.
   - Run sub-apps with `SamplerFullSolveMultiApp` (mode `normal`/`batch-reset`/`batch-restore`/`batch-keep-solution`).
   - Inject the row into each sub-app via either: (a) `MultiAppSamplerControl` + `cli_args` (parameters consumed at sub-app construction, e.g. mesh sizes, file names), or (b) `SamplerParameterTransfer` + `SamplerReceiver` (controllable runtime parameters).
   - Pull QoIs via `SamplerReporterTransfer` into a `StochasticReporter`; reduce with `StatisticsReporter` (mean/stddev/percentile) or `SobolReporter` (paired with `SobolSampler`).
2. **Sensitivity analysis.**
   - Variance-based / Sobol indices: `SobolSampler` + `SobolReporter` (must be used as a pair).
   - Morris elementary effects: `MorrisSampler` + `MorrisReporter`.
   - One-at-a-time perturbation: `DirectPerturbationSampler` + `DirectPerturbationReporter`.
   - Polynomial-Chaos-derived Sobol indices (analytic, no extra runs): fit a `PolynomialChaos` and read indices from `PolynomialChaosReporter`.
3. **Surrogate fitting + later evaluation.**
   - Training pass: a `SurrogateTrainer` (e.g. `PolynomialChaosTrainer`, `GaussianProcessTrainer`, `NearestPointTrainer`, `PolynomialRegressionTrainer`, `PODReducedBasisTrainer`) consumes sampler rows + reporter responses and writes restartable model data.
   - Evaluation pass (separate input): the paired `SurrogateModel` (`PolynomialChaos`, `GaussianProcessSurrogate`, …) loads the data and is queried by `EvaluateSurrogate` or another StochasticReporter consumer.
4. **Bayesian inference / MCMC.**
   - `IndependentGaussianMH`, `AffineInvariantStretchSampler`, `AffineInvariantDES`, `ParallelSubsetSimulation`, `AdaptiveImportanceSampler`, `PMCMCBase`-derived samplers, paired with the matching decision reporter (`IndependentMHDecision`, `AffineInvariantStretchDecision`, `AffineInvariantDifferentialDecision`, `PMCMCDecision`, `AdaptiveMonteCarloDecision`) + a `Likelihood`.
5. **Active learning** (replace expensive sub-app runs with surrogate predictions on the fly).
   - `ActiveLearningMonteCarloSampler` / `BayesianActiveLearningSampler` / `AISActiveLearning` + an `ActiveLearningReporterBase`-derived reporter (`ActiveLearningGPDecision`, `BayesianActiveLearner`, …) + `ActiveLearningGaussianProcess` surrogate + an acquisition function (`ExpectedImprovement`, `UFunction`, `UpperConfidenceBound`, …).
6. **Optimization / inverse problems** — different module, same MultiApp infrastructure: see [optimization-authoring.md].
7. **Just need a Reporter / VPP that aggregates sub-app data?** — see [postprocessor-authoring.md].

Cross-link: `Sampler` is a [`UserObject`](userobject-authoring.md) subclass; the `[StochasticTools]`/`[Distributions]` block wiring is described in [action-authoring.md].

## Contract

### **Sampler** (framework + ST subclasses) `framework/include/samplers/Sampler.h:44`

Required overrides:
- `Real computeSample(dof_id_type row_index, dof_id_type col_index)` — the only pure virtual; returns one matrix entry. Called once per `(row, col)` per `execute_on` cycle. (`Sampler.h:203`)

Optional overrides:
- `void sampleSetUp(SampleMode)` / `sampleTearDown(SampleMode)` — pre/post the row loop. Use to pre-compute row caches (e.g. `LatinHypercubeSampler::sampleSetUp` builds the probability grid, then `computeSample` is a pure lookup). (`Sampler.h:212-213`)
- `void executeSetUp()` / `executeTearDown()` — around the per-execute generator advance, used by adaptive samplers that resize between executes. (`Sampler.h:270-271`)
- `LocalRankConfig constructRankConfig(bool batch_mode) const` — only override if you need custom row partitioning (e.g. `SobolSampler` keeps the A/B blocks aligned across ranks). (`Sampler.h:286`)
- `bool isAdaptiveSamplingCompleted() const` — required for adaptive samplers used with `SamplerFullSolveMultiApp` mode `batch-keep-solution`. (`Sampler.h:129`)

Constructor must call `setNumberOfRows()` and `setNumberOfCols()`; optionally `setNumberOfRandomSeeds()` if you need >1 generator stream. Use `getRand(index)` / `getRandl(...)` inside `computeSample` to pull from generators. (`Sampler.h:165-184`)

Consumers iterate `for (i = getLocalRowBegin(); i < getLocalRowEnd(); ++i) row = getNextLocalRow();` — never `getGlobalSamples()` in a hot path.

### **Distribution** `framework/include/distributions/Distribution.h:18`

Required overrides:
- `Real pdf(const Real & x) const` — probability density. (`Distribution.h:27`)
- `Real cdf(const Real & x) const` — cumulative. (`Distribution.h:32`)
- `Real quantile(const Real & y) const` — inverse CDF; this is what samplers actually call. (`Distribution.h:37`)
- `Real median() const` — has a default that calls `quantile(0.5)`; override if there's a closed form. (`Distribution.h:42`)

Concrete examples: `Normal`, `Uniform`, `Lognormal`, `Beta`, `Gamma`, `Weibull`, `TruncatedNormal`, `JohnsonSB`, `StudentT`, `KernelDensity1D`, `Logistic`, `FDistribution`. The `*Distribution.h` variants (`NormalDistribution.h`, etc.) are deprecated stochastic_tools-only forwarders kept for backwards compat.

### **SurrogateModel** + **SurrogateTrainer** pair

**`SurrogateTrainer`** at `modules/stochastic_tools/include/trainers/SurrogateTrainer.h:55`. Required override is one of:
- `train()` — body of the per-row loop; reads `getSamplerData()` / `getPredictorData()` and any `getTrainingData<T>(reporter_name)` references registered in the constructor. (`SurrogateTrainer.h:74`)
- Optionally `preTrain()` / `postTrain()` for global init + MPI reductions. (`SurrogateTrainer.h:69, 79`)

`SurrogateTrainerBase` (`SurrogateTrainer.h:32`) is the lower-level escape hatch when you need full control of the loop (`PODReducedBasisTrainer` does this). Both inherit `RestartableModelInterface`: declare every persistent piece of model state via `declareModelData<T>(name, …)` in the constructor — that's what gets dumped to the `*.rd/` directory and reloaded by the `SurrogateModel`.

**`SurrogateModel`** at `modules/stochastic_tools/include/surrogates/SurrogateModel.h:18`. Required overrides (at least one):
- `Real evaluate(const std::vector<Real> & x) const` — scalar output. (`SurrogateModel.h:33`)
- `void evaluate(const std::vector<Real> & x, std::vector<Real> & y) const` — vector output. (`SurrogateModel.h:43`)
- `Real evaluate(const std::vector<Real> & x, Real & std) const` — with predicted standard deviation, GP-style. (`SurrogateModel.h:53`)
- `void evaluate(const std::vector<Real> & x, std::vector<Real> & y, std::vector<Real> & std) const` — vector + uncertainty. (`SurrogateModel.h:58`)

The default implementations call `evaluateError()` and `mooseError`; only override the signatures your model can actually compute. Constructor uses `getModelData<T>(name)` from `RestartableModelInterface` to bind the *same* declared names from the trainer. The action `LoadSurrogateDataAction` wires this up automatically when the input has `[Surrogates]` blocks pointing at a `*.rd` directory.

### **StochasticReporter** `modules/stochastic_tools/include/reporters/StochasticReporter.h:137`

Sampler-row-indexed value container. Subclasses should:
- Declare per-row reporter values via `declareStochasticReporter<T>(name, sampler)` (`StochasticReporter.h:153`) — these are `std::vector<T>` sized to `sampler.getNumberOfLocalRows()` and gathered/all-gathered automatically by `StochasticReporterContext::finalize()` based on consumer mode.
- Override `execute()` to fill the vector (or subclass `ActiveLearningReporterBase` / `StatisticsReporter` for ready-made loops).
- For "clone the reporter shape from a producer" use cases (e.g. transfers), override `declareStochasticReporterClone(...)`.

Concrete consumers: `StatisticsReporter` (mean/stddev/percentiles), `SobolReporter` (variance decomposition; pair with `SobolSampler`), `MorrisReporter`, `DirectPerturbationReporter`, `PolynomialChaosReporter`, `EvaluateSurrogate`, `ConditionalSampleReporter`, `StochasticMatrix`, `MappingReporter`.

### **SamplerFullSolveMultiApp** + **MultiAppSamplerControl** + **SamplerReceiver**

**Parent-side**: `SamplerFullSolveMultiApp` (`modules/stochastic_tools/include/multiapps/SamplerFullSolveMultiApp.h:21`). Modes (`StochasticTools::MultiAppMode`):
- `normal` — one sub-app instance per row, kept alive.
- `batch-reset` — recycle a single sub-app, fully re-initialize between rows.
- `batch-restore` — recycle a sub-app, restore from a backup taken at first solve (fastest for repeatable initial state).
- `batch-keep-solution` — like `batch-restore` but keeps the previous solution as the initial guess (used by adaptive / active-learning loops, requires `Sampler::isAdaptiveSamplingCompleted`).

In all `batch-*` modes, transfers must derive from `StochasticToolsTransfer` so they expose the `*FromMultiapp` / `*ToMultiapp` callbacks the multiapp drives directly (see next section).

`MultiAppSamplerControl` (`modules/stochastic_tools/include/controls/MultiAppSamplerControl.h:25`) runs on `PRE_MULTIAPP_SETUP` to splice each row into the sub-app's `cli_args` *before* the sub-app exists. Use this for parameters that must be set on the command line (mesh `nx`/`ny`, input file names, anything consumed in the constructor).

**Sub-app side**: drop a `[Controls]` block with a `SamplerReceiver` (`modules/stochastic_tools/include/controls/SamplerReceiver.h:21`); `SamplerParameterTransfer` calls `SamplerReceiver::transfer(map<param_name, vector<Real>>)` to mutate `Controls`-controllable parameters on each row. `SamplerReceiver::transfer` is private and only `SamplerParameterTransfer` is friended — that pairing is the only legal way to write into the receiver.

### **SamplerReporterTransfer** + **SamplerParameterTransfer** + **StochasticToolsTransfer**

`StochasticToolsTransfer` (`modules/stochastic_tools/include/transfers/StochasticToolsTransfer.h:21`) is the base that exposes batch-mode hooks: `initializeFromMultiapp`/`executeFromMultiapp`/`finalizeFromMultiapp` (and `*ToMultiapp`). The multiapp drives these directly for each row in `batch-*` modes; `setGlobalMultiAppIndex`/`setGlobalRowIndex`/`setCurrentRow` are how it injects per-row context.

When to use which transfer:
- **`SamplerParameterTransfer`** (`transfers/SamplerParameterTransfer.h:21`) — push `parameters` from each sampler row into a sub-app `SamplerReceiver`. Runtime, per-execute. Use for everything that's a controllable param at runtime.
- **`MultiAppSamplerControl`** (a `Control`, not a `Transfer`) — push row data via `cli_args` *before* sub-app construction. Use for parameters consumed at constructor time (mesh size, FE order, file paths).
- **`SamplerReporterTransfer`** (`transfers/SamplerReporterTransfer.h:24`) — pull named sub-app reporters back into a parent `StochasticReporter`, indexed by sampler row. Also writes a `converged` reporter the multiapp consumes to skip failed rows.
- **`SamplerPostprocessorTransfer`** — older postprocessor-only variant, prefer the reporter version.
- **`SerializedSolutionTransfer`** / **`PODSamplerSolutionTransfer`** / **`PODResidualTransfer`** — full solution-vector transfers used by the POD-RB workflow (`PODFullSolveMultiApp`).

Batch-mode requirement: any transfer used with `SamplerFullSolveMultiApp` in a `batch-*` mode *must* derive from `StochasticToolsTransfer`. A plain `MultiAppTransfer` will be silently skipped.

### **ActiveLearningReporterBase** `modules/stochastic_tools/include/reporters/ActiveLearningReporterBase.h:24`

Templated on the QoI type `T` (typically `Real` or `std::vector<Real>`). Per-row sub-app-vs-surrogate decision logic is encapsulated in:

- `bool needSample(const std::vector<Real> & row, dof_id_type local_ind, dof_id_type global_ind, T & val)` — return `true` if this row needs a real sub-app run; return `false` and write `val` directly to substitute a surrogate prediction. (`ActiveLearningReporterBase.h:90`)
- `preNeedSample()` — called once before the row loop; use to refit the surrogate from the previous batch's results. (`ActiveLearningReporterBase.h:77`)
- `getGlobalInputData()` / `getGlobalOutputData()` — gather full sample/QoI history for refitting. (`ActiveLearningReporterBase.h:59, 68`)

The base's overridden `declareStochasticReporterClone` enforces *exactly one* declared reporter value of type `T` and that the producer sampler matches the configured one. The reporter exposes a `need_sample` boolean vector that `SamplerFullSolveMultiApp` reads to skip rows. Pair with `ActiveLearningGaussianProcess` + an acquisition (`ExpectedImprovement`, `UFunction`, `UpperConfidenceBound`, `ProbabilityofImprovement`, `BayesianPosteriorTargeted`, `CoefficientOfVariation`).

## Coupling & material properties

`Sampler` row drives sub-app inputs in one of two ways: `cli_args` injection at construction (`MultiAppSamplerControl`) or controllable-parameter mutation at runtime (`SamplerParameterTransfer` + `SamplerReceiver`). Both indices into the row come from the parent's `cli_args`/`parameters` lists by position. A `Distribution` is consumed by a `Sampler` via `getDistributionByName` in the sampler constructor — no other object should hold distribution refs. A `Trainer` ingests sampler rows (via `getSamplerData()`/`getPredictorData()`) plus reporter responses (via `getTrainingData<T>(reporter_name)`); the resulting model data is declared restartable in the trainer's constructor and loaded by a paired `SurrogateModel` later via `getModelData<T>(name)`. The split is intentional — training is one-shot and expensive; evaluation is reusable and cheap.

## Registration & build

Use `registerMooseObject("StochasticToolsApp", YourClass);` (or `registerMooseObjectAliased(...)` if you want a short input-block name; or `registerMooseObjectReplaced(...)` for backwards compat — see `MonteCarloSampler.C:13-17`). The module flag is `STOCHASTIC_TOOLS := yes` in `modules/modules.mk:40`; consumers gate on `STOCHASTIC_TOOLS == yes` (`modules/modules.mk:218`). Trainer model data uses MOOSE's restart system: declare every persistent member via `declareModelData<T>(...)` in the constructor of a `RestartableModelInterface` subclass — these are written to a `*.rd/` directory at the end of the run and loaded by `getModelData<T>(...)` in the matching `SurrogateModel`.

## Minimal scaffold

A small custom **Sampler** subclass (the most common ST extension task — here, a scrambled-Halton quasi-random sampler skeleton).

`include/samplers/HaltonSampler.h`:

```cpp
#pragma once
#include "Sampler.h"

class HaltonSampler : public Sampler
{
public:
  static InputParameters validParams();
  HaltonSampler(const InputParameters & parameters);

protected:
  virtual Real computeSample(dof_id_type row_index, dof_id_type col_index) override;

  /// Distributions, one per column
  std::vector<Distribution const *> _distributions;
  /// Prime base for each column
  std::vector<unsigned int> _bases;
};
```

`src/samplers/HaltonSampler.C`:

```cpp
#include "HaltonSampler.h"
#include "Distribution.h"

registerMooseObject("StochasticToolsApp", HaltonSampler);

InputParameters
HaltonSampler::validParams()
{
  InputParameters params = Sampler::validParams();
  params.addClassDescription("Quasi-random Halton sequence sampler.");
  params.addRequiredParam<dof_id_type>("num_rows", "Number of rows.");
  params.addRequiredParam<std::vector<DistributionName>>(
      "distributions", "Distributions; column count = number of distributions.");
  return params;
}

static Real haltonValue(dof_id_type i, unsigned int base)
{
  Real f = 1.0, r = 0.0;
  while (i > 0) { f /= base; r += f * (i % base); i /= base; }
  return r;
}

HaltonSampler::HaltonSampler(const InputParameters & parameters) : Sampler(parameters)
{
  static const std::vector<unsigned int> primes = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29};
  for (const auto & n : getParam<std::vector<DistributionName>>("distributions"))
    _distributions.push_back(&getDistributionByName(n));
  if (_distributions.size() > primes.size())
    paramError("distributions", "Built-in prime table only supports ", primes.size(), " dims.");
  _bases.assign(primes.begin(), primes.begin() + _distributions.size());
  setNumberOfRows(getParam<dof_id_type>("num_rows"));
  setNumberOfCols(_distributions.size());
}

Real
HaltonSampler::computeSample(dof_id_type row_index, dof_id_type col_index)
{
  // +1 because Halton is undefined at i=0
  return _distributions[col_index]->quantile(haltonValue(row_index + 1, _bases[col_index]));
}
```

Keys: constructor calls `setNumberOfRows`/`setNumberOfCols`; `computeSample` uses `_distributions[col]->quantile(u)` to map a quasi-random `u in [0,1)` through the marginal. Halton is deterministic — no `getRand()` calls and no seed bookkeeping needed.

## Common pitfalls

1. **Confusing the framework `Sampler` base with the legacy `SamplerBase` VPP mixin.** `framework/include/vectorpostprocessors/SamplerBase.h` is a *VectorPostprocessor* helper for emitting tabular data — unrelated to UQ. New samplers always derive from `framework/include/samplers/Sampler.h`.
2. **`SobolSampler` + `SobolReporter` are required as a pair.** The reporter assumes the matrix layout (`[M2, N_1..N_n, (N_-1..N_-n,) M1]`) the sampler produces; using one without the other gives silently wrong indices. Same pairing rule for `MorrisSampler`/`MorrisReporter`, `DirectPerturbationSampler`/`DirectPerturbationReporter`, MCMC samplers and their decision reporters.
3. **Trainer/SurrogateModel split is intentional.** Don't try to evaluate inside the trainer — training is one-shot, evaluation is reusable from a `*.rd/` checkpoint via the paired `SurrogateModel`. Forgetting to declare a member with `declareModelData<T>(...)` means it won't survive the round-trip.
4. **Batch mode requires `StochasticToolsTransfer`-derived transfers.** A `MultiAppCopyTransfer` or other plain `MultiAppTransfer` will be silently dropped in `batch-reset`/`batch-restore`/`batch-keep-solution` because the multiapp drives `*FromMultiapp` / `*ToMultiapp` hooks the base class doesn't have.
5. **`PODReducedBasisSurrogate` returns fields, not scalars.** Its `evaluate` overrides write a libMesh solution vector through `PODSamplerSolutionTransfer`; `EvaluateSurrogate` won't work on it. Use `PODFullSolveMultiApp` end-to-end.
6. **`cli_args` injection happens *before* sub-app construction.** Anything consumed in the sub-app constructor (mesh `nx`, file paths, `[Mesh]` parameters, `[Variables]` order) must come through `MultiAppSamplerControl`, not `SamplerParameterTransfer`. The `Control` runs on `PRE_MULTIAPP_SETUP`; the `Transfer` runs on `TIMESTEP_BEGIN`/`MULTIAPP_FIXED_POINT_BEGIN` — far too late for construction-time params. The matching error is usually "parameter not controllable" or a sub-app silently using the default value.

