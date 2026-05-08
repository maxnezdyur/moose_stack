# Authoring inputs: Stochastic Tools (UQ, surrogates, sensitivity)

Reach for this guide when writing a `.i` file that propagates input distributions through a model, fits / evaluates a surrogate, runs a sensitivity study, or wires up Bayesian / active-learning loops. The stochastic_tools module brings several **top-level blocks unique to ST** — `[Distributions]`, `[Samplers]`, `[Trainers]`, `[Surrogates]`, `[Likelihood]`, `[VariableMappings]`, `[StochasticTools]` — plus ST-specific `type=...` choices inside `[MultiApps]`, `[Transfers]`, `[Controls]`, `[Reporters]`. For sub-app physics (kernels, BCs, postprocessors) see [kernels.md](./kernels.md), [bcs.md](./bcs.md), [postprocess.md](./postprocess.md). For C++ authoring see `../moose/stochastic-tools-authoring.md`. Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`.

## When to use this (vs alternatives)

Pick the workflow first:

1. **Forward UQ** — `[Distributions]` + `[Samplers]` + `SamplerFullSolveMultiApp` + `SamplerParameterTransfer` + `SamplerReporterTransfer` + `StochasticReporter` + `StatisticsReporter`. Full forward solve once per row.
2. **Sensitivity analysis**
   - **Sobol indices**: `Sobol` sampler (built on two MC base samplers `sampler_a`/`sampler_b`) + `SobolReporter`. Paired — neither works alone.
   - **Morris elementary effects** (cheap screening): `MorrisSampler` + `MorrisReporter`. Paired.
   - **PC-derived Sobol** (analytic, no extra runs): fit `PolynomialChaos`, read from `PolynomialChaosReporter`.
3. **Surrogate offline-online** — full solve too expensive to run 1000s of times.
   - Training input: cheap-ish sampler + `SamplerFullSolveMultiApp` + `[Reporters/storage] type = StochasticReporter` + `[Trainers]` (`response = storage/data:pp:value`) + `[Outputs] type = SurrogateTrainerOutput` → `*.rd/` checkpoint.
   - Evaluation input: bigger sampler + `[Surrogates] filename = '...rd'` + `[Reporters] type = EvaluateSurrogate`. No MultiApp, no Transfers.
   - Combined `train_and_evaluate.i` is fine for iteration; split for production.
4. **Reduced-basis / POD** — QoI is a field. Add `[VariableMappings] type = PODMapping`, use `SerializedSolutionTransfer` + `ParallelSolutionStorage`, end-to-end with `PODFullSolveMultiApp` + `PODReducedBasisSurrogate`.
5. **Bayesian / MCMC** — `[Likelihood]` + MCMC sampler (`IndependentGaussianMH`, `AffineInvariantStretchSampler`, `AffineInvariantDES`, `ParallelSubsetSimulation`, `AdaptiveImportanceSampler`) + matching decision reporter.
6. **Active learning** — substitute surrogate predictions for full solves on the fly. `ActiveLearningMonteCarloSampler` + `ActiveLearningGPDecision` + `ActiveLearningGaussianProcess` + acquisition function (`Ufunction`/`EI`/`UpperConfidenceBound`).

The load-bearing decision is `EvaluateSurrogate` (seconds) vs `SamplerFullSolveMultiApp` (hours per row).

## Catalog

### `[Distributions]` — random-variable definitions

Each entry implements `pdf(x)`, `cdf(x)`, `quantile(p)`. Samplers call `quantile(u)` for `u ~ U(0,1)`.

##### `Normal`
- Source: `modules/stochastic_tools/include/distributions/Normal.h:17`
- Example: `modules/stochastic_tools/test/tests/distributions/normal.i:5`
- Required: `mean`, `standard_deviation`.

##### `Uniform`
- Source: `modules/stochastic_tools/include/distributions/Uniform.h:17`
- Example: `modules/stochastic_tools/test/tests/distributions/uniform.i:5`
- Required: `lower_bound`, `upper_bound`.

##### `Beta`
- Source: `modules/stochastic_tools/include/distributions/Beta.h:17`
- Example: `modules/stochastic_tools/test/tests/distributions/beta.i:5`
- Required: `alpha`, `beta`.

##### `Logistic`
- Source: `modules/stochastic_tools/include/distributions/Logistic.h:17`
- Example: `modules/stochastic_tools/test/tests/distributions/logistic.i:5`
- Required: `location`, `shape`.

##### `Lognormal`
- Source: `modules/stochastic_tools/include/distributions/Lognormal.h:17`
- Example: `modules/stochastic_tools/test/tests/distributions/lognormal.i:5`
- Required: `location` (mean of log), `scale` (std of log). Registered as `Lognormal` (legacy `LognormalDistribution` is deprecated).

##### `JohnsonSB`
- Source: `modules/stochastic_tools/include/distributions/JohnsonSB.h:17` (subclass of `Normal`)
- Example: `modules/stochastic_tools/test/tests/distributions/johnsonsb.i:5`
- Required: `a`, `b` (lower/upper support), `alpha_1`, `alpha_2`.

##### `Weibull`
- Source: `modules/stochastic_tools/include/distributions/Weibull.h:17`
- Example: `modules/stochastic_tools/test/tests/distributions/weibull.i:5`
- Required: `shape`, `scale`, `location`.

##### `TruncatedNormal`
- Source: `modules/stochastic_tools/include/distributions/TruncatedNormal.h:17` (subclass of `Normal`)
- Example: `modules/stochastic_tools/test/tests/distributions/truncated_normal.i:5`
- Required: `mean`, `standard_deviation`, `lower_bound`, `upper_bound`.

##### `Gamma`
- Source: `modules/stochastic_tools/include/distributions/Gamma.h:17`
- Example: `modules/stochastic_tools/test/tests/distributions/gamma.i:5`
- Required: `shape`, `scale`.

### `[Samplers]` — generators of parameter rows

Every sampler returns an `(N_rows x N_cols)` matrix; columns map 1:1 to `distributions` or external-file columns. `execute_on = PRE_MULTIAPP_SETUP` is typical when paired with `MultiAppSamplerControl`.

##### `MonteCarlo`
- Source: `modules/stochastic_tools/include/samplers/MonteCarloSampler.h:17` (registered as `MonteCarlo`)
- Example: `modules/stochastic_tools/test/tests/samplers/monte_carlo/monte_carlo_uniform.i:13`
- Plain pseudo-random draws. Required: `num_rows`, `distributions`. Useful: `seed`, `min_procs_per_row`.

##### `LatinHypercube`
- Source: `modules/stochastic_tools/include/samplers/LatinHypercubeSampler.h:21` (registered as `LatinHypercube`)
- Example: `modules/stochastic_tools/test/tests/samplers/latin_hypercube/latin_hypercube.i:18`
- Stratified MC — `num_rows` equiprobable bins per marginal. Lower variance than `MonteCarlo` at the same count. Required: `num_rows`, `distributions`. Useful: `seed`.

##### `CSVSampler`
- Source: `modules/stochastic_tools/include/samplers/CSVSampler.h:17`
- Example: `modules/stochastic_tools/test/tests/samplers/csv/csv_sampler.i:5`
- Reads pre-computed matrix from CSV; bypasses `[Distributions]`. Required: `samples_file`. Useful: `column_names`/`column_indices`.

##### `Quadrature`
- Source: `modules/stochastic_tools/include/samplers/QuadratureSampler.h:19` (registered as `Quadrature`)
- Example: `modules/stochastic_tools/test/tests/surrogates/poly_chaos/main_2d_quad.i:24`
- Tensor-product Gauss quadrature in distribution space. Use for `PolynomialChaosTrainer` projection. Required: `distributions`, `order`. Useful: `sparse_grid` (Smolyak), `grid_type`.

##### `MorrisSampler`
- Source: `modules/stochastic_tools/include/samplers/MorrisSampler.h:18`
- Example: `modules/stochastic_tools/test/tests/samplers/morris/morris.i:11`
- Morris EE trajectories — `trajectories * (n_dim + 1)` rows; consecutive pairs perturb one input. Required: `distributions`, `trajectories`, `levels`. Pair with `MorrisReporter`.

##### `Sobol`
- Source: `modules/stochastic_tools/include/samplers/SobolSampler.h:23` (registered as `Sobol`)
- Example: `modules/stochastic_tools/test/tests/reporters/sobol/sobol_main.i:25`
- Variance-decomposition matrix `[M2, N_1..N_n, M1]` from two base MC samplers. Required: `sampler_a`, `sampler_b` (independent MCs, same `distributions`). Pair with `SobolReporter`.

##### `IndependentGaussianMH` (MCMC)
- Source: `modules/stochastic_tools/include/samplers/IndependentGaussianMH.h:17` (`PMCMCBase`)
- Example: `modules/stochastic_tools/test/tests/samplers/mcmc/main_imh.i:27`
- Parallel-proposal Metropolis-Hastings with independent Gaussian proposals. Required: `prior_distributions`, `num_parallel_proposals`, `std_prop`, `initial_values`, `seed_inputs`. Pair with `IndependentMHDecision` + `[Likelihood]`.

##### `AffineInvariantStretchSampler` / `AffineInvariantDES` (MCMC)
- Source: `modules/stochastic_tools/include/samplers/AffineInvariantStretchSampler.h:17` / `AffineInvariantDES.h:17`
- Example: `modules/stochastic_tools/test/tests/samplers/mcmc/main_des.i`
- Affine-invariant ensemble samplers (Goodman-Weare stretch; DE-snooker). Pair with `AffineInvariantStretchDecision` / `AffineInvariantDifferentialDecision`.

##### `PMCMCBase` (base — not used directly)
- Source: `modules/stochastic_tools/include/samplers/PMCMCBase.h:19`
- All parallel-MCMC samplers inherit. Common params: `prior_distributions`, `num_parallel_proposals`, `seed`. Always paired with a `*Decision` reporter + `[Likelihood]`.

##### Other samplers (one-line catalog)
- `CartesianProduct` (`CartesianProductSampler.h:18`) — tensor grid; common in surrogate training. Example: `tests/surrogates/nearest_point/train.i:7`.
- `Cartesian1D` (`Cartesian1DSampler.h`) — 1D version.
- `InputMatrix` (`InputMatrixSampler.h:17`) — inline `inputs = '...'` matrix.
- `DirectPerturbationSampler` (`DirectPerturbationSampler.h:17`) — one-at-a-time perturbations; paired with `DirectPerturbationReporter`.
- `NestedMonteCarlo` (`NestedMonteCarloSampler.h:17`) — double-loop nested MC.
- `AdaptiveImportanceSampler` (`AdaptiveImportanceSampler.h:18`) — adaptive IS for rare events.
- `ParallelSubsetSimulation` (`ParallelSubsetSimulation.h:18`) — subset simulation for failure probabilities.
- `ActiveLearningMonteCarloSampler` — consults an AL decision reporter to skip rows.

### `[Surrogates]` — fast model surrogates (evaluation side)

Loaded from a trainer's `*.rd/` directory (`filename = '...'`) or attached to a same-input trainer (`trainer = name`). Query through `EvaluateSurrogate`. All entries below take `trainer` OR `filename` as required.

##### `PolynomialChaos`
- Source: `modules/stochastic_tools/include/surrogates/PolynomialChaos.h:19`
- Example: `modules/stochastic_tools/test/tests/surrogates/poly_chaos/main_2d_quad.i:71`; load-from-file: `tests/surrogates/load_store/train_and_evaluate.i:77`
- Spectral expansion in orthogonal polynomials matched to each marginal. Best for smooth distributions, dimension < ~10. `PolynomialChaosReporter` reads Sobol indices analytically.

##### `GaussianProcessSurrogate`
- Source: `modules/stochastic_tools/include/surrogates/GaussianProcessSurrogate.h:18`
- Example: `modules/stochastic_tools/test/tests/surrogates/gaussian_process/GP_squared_exponential_testing.i:38` (sub-block `[GP_avg]`)
- Kriging / GP regression. Returns mean *and* std (set `evaluate_std = true` on `EvaluateSurrogate`). Good for moderate sample counts when surrogate uncertainty matters.

##### `NearestPointSurrogate`
- Source: `modules/stochastic_tools/include/surrogates/NearestPointSurrogate.h:14`
- Example: `modules/stochastic_tools/test/tests/surrogates/nearest_point/evaluate.i:24` (sub-block `[surrogate]`)
- Nearest-neighbor lookup in normalized space. Baseline / smoke-test.

##### `PolynomialRegressionSurrogate`
- Source: `modules/stochastic_tools/include/surrogates/PolynomialRegressionSurrogate.h:14`
- Example: `modules/stochastic_tools/test/tests/surrogates/polynomial_regression/evaluate.i:24`
- OLS or ridge polynomial fit up to `max_degree`. Cheap, deterministic.

##### `LibtorchANNSurrogate`
- Source: `modules/stochastic_tools/include/libtorch/surrogates/LibtorchANNSurrogate.h:19`
- Example: `modules/stochastic_tools/test/tests/surrogates/libtorch_nn/evaluate.i:14`
- Feed-forward NN from a `.pt` checkpoint via libtorch. Requires MOOSE built `libtorch=true`.

### `[Trainers]` — surrogate fitting (training side)

Each trainer ingests sampler rows + a reporter response (`response = storage/data:pp:value`) and writes restartable model data. Output via `[Outputs] type = SurrogateTrainerOutput trainers = '...' execute_on = FINAL` — produces the `*.rd/` directory the matching `SurrogateModel` reloads. All trainers below need `sampler` and `response` as required.

##### `PolynomialChaosTrainer`
- Source: `modules/stochastic_tools/include/trainers/PolynomialChaosTrainer.h:22`
- Example: `modules/stochastic_tools/test/tests/surrogates/poly_chaos/main_2d_quad.i:78`
- Spectral coefficients via Gauss quadrature projection (with `Quadrature` sampler) or least-squares regression. Also requires `distributions`, `order`.

##### `GaussianProcessTrainer`
- Source: `modules/stochastic_tools/include/trainers/GaussianProcessTrainer.h:23`
- Example: `modules/stochastic_tools/test/tests/surrogates/gaussian_process/GP_squared_exponential_training.i:61`
- Fits a GP. Requires a `[Covariance]` block referenced via `covariance_function`. Hyperparameter tuning via `tune_parameters`, `num_iters`, `learning_rate` (Adam). Useful: `standardize_params`, `standardize_data`.

##### `NearestPointTrainer`
- Source: `modules/stochastic_tools/include/trainers/NearestPointTrainer.h:14`
- Example: `modules/stochastic_tools/test/tests/surrogates/nearest_point/train.i:24`
- Stores all training points, no fit step.

##### `PolynomialRegressionTrainer`
- Source: `modules/stochastic_tools/include/trainers/PolynomialRegressionTrainer.h:19`
- Example: `modules/stochastic_tools/test/tests/surrogates/polynomial_regression/train.i:24`
- OLS or ridge regression up to `max_degree`. Also requires `regression_type` (`ols|ridge`), `max_degree`.

##### `LibtorchANNTrainer`
- Source: `modules/stochastic_tools/include/libtorch/surrogates/LibtorchANNTrainer.h:23`
- Example: `modules/stochastic_tools/test/tests/surrogates/libtorch_nn/train.i:24`
- Feed-forward NN. Also requires `num_epochs`, `num_neurons_per_layer`, `activation_function`. Hyperparams: `num_batches`, `learning_rate`.

##### `ActiveLearningGaussianProcess`
- Source: `modules/stochastic_tools/include/surrogates/ActiveLearningGaussianProcess.h:30`
- Example: `modules/stochastic_tools/test/tests/reporters/ActiveLearningGP/main_adam.i:83`
- GP trainer that re-fits incrementally inside an active-learning loop. Like `GaussianProcessTrainer` + `tune_parameters`, `num_iters`, `learning_rate` required.

### `[Likelihood]` — Bayesian likelihoods

Singular block name `[Likelihood]` (not `[Likelihoods]`). Consumed by MCMC decision reporters.

##### `Gaussian`
- Source: `modules/stochastic_tools/include/likelihoods/Gaussian.h:18`
- Example: `modules/stochastic_tools/test/tests/likelihoods/gaussian_derived/main.i:64`
- Independent Gaussian observation likelihood. Required: `noise` (Reporter name like `pp/value`), `file_name`. Useful: `log_likelihood = true`.

##### `TruncatedGaussian`
- Source: `modules/stochastic_tools/include/likelihoods/TruncatedGaussian.h:17` (subclass of `Gaussian`)
- Example: same `main.i` invoked with `Likelihood/gaussian/type='TruncatedGaussian'` cli_args
- Required: `noise`, `file_name`, `lower_bound`, `upper_bound`.

##### `ExtremeValue`
- Source: `modules/stochastic_tools/include/likelihoods/ExtremeValue.h:17` (subclass of `Gaussian`)
- Example: same `main.i` with `Likelihood/gaussian/type='ExtremeValue'`
- Gumbel / extreme-value likelihood for tail data. Required: `noise`, `file_name`.

### `[VariableMappings]` — reduced-basis projection

Top-level block defining a linear mapping between a full FE solution vector and a low-dim coordinate vector — for POD-RB workflows.

##### `PODMapping`
- Source: `modules/stochastic_tools/include/variablemappings/PODMapping.h:23`
- Example: `modules/stochastic_tools/test/tests/variablemappings/pod_mapping/pod_mapping_main.i:38`
- Truncated SVD of a snapshot matrix in `solution_storage` (a `ParallelSolutionStorage` reporter). `num_modes_to_compute` is the rank per variable. Inspect singulars with `SingularTripletReporter`. Required: `solution_storage`, `variables`, `num_modes_to_compute`. Useful: `extra_slepc_options`.

### `[Reporters]` — ST-specific data containers / reductions

##### `StochasticReporter`
- Source: `modules/stochastic_tools/include/reporters/StochasticReporter.h:137`
- Example: `modules/stochastic_tools/test/tests/reporters/stochastic_reporter/stats.i:44` (sub-block `[storage]`)
- Sampler-row-indexed container. `SamplerReporterTransfer` declares per-row slots inside (`storage/data:pp:value`). Set `parallel_type = ROOT` for downstream serial consumers.

##### `StatisticsReporter`
- Source: `modules/stochastic_tools/include/reporters/StatisticsReporter.h:124`
- Example: `modules/stochastic_tools/test/tests/reporters/statistics/statistics_main.i:38`
- Reduces sampler-row vectors to scalars. Required: `reporters`, `compute` (`min|max|sum|mean|stddev|norm2|ratio|stderr|median`). Useful: `ci_method` (`percentile|bca`), `ci_levels`, `ci_replicates`.

##### `SobolReporter`
- Source: `modules/stochastic_tools/include/reporters/SobolReporter.h:23`
- Example: `modules/stochastic_tools/test/tests/reporters/sobol/sobol_main.i:61`
- First-order and total Sobol indices per input dimension. Must pair with a `Sobol` sampler. Required: `reporters`. Useful: `ci_levels`, `ci_replicates`, `execute_on = FINAL`.

##### `MorrisReporter`
- Source: `modules/stochastic_tools/include/reporters/MorrisReporter.h:17`
- Example: `modules/stochastic_tools/test/tests/reporters/morris/morris_main.i:46`
- Morris (mu, mu*, sigma) from `MorrisSampler` rows. Required: `reporters`.

##### `EvaluateSurrogate`
- Source: `modules/stochastic_tools/include/reporters/EvaluateSurrogate.h:20`
- Example: `modules/stochastic_tools/test/tests/surrogates/gaussian_process/GP_squared_exponential_testing.i:27`
- Queries a `[Surrogates]` model at every row. Required: `model`, `sampler`. Useful: `evaluate_std = true` (GP only), `parallel_type = ROOT`, `execute_on = FINAL`.

##### `ActiveLearningGPDecision`
- Source: `modules/stochastic_tools/include/reporters/ActiveLearningGPDecision.h:17`
- Example: `modules/stochastic_tools/test/tests/reporters/ActiveLearningGP/main_adam.i:64`
- AL decision module: queries the GP `(mu, sigma)` per row, applies the acquisition, emits a `flag_sample` bool the multi-app reads. Required: `sampler`, `flag_sample`, `inputs`, `gp_mean`, `gp_std`, `n_train`, `al_gp` (trainer), `gp_evaluator` (surrogate), `learning_function` (`Ufunction|EI|UpperConfidenceBound|...`), `learning_function_threshold`.

##### `PolynomialChaosReporter`
- Source: same reporters dir
- Example: `modules/stochastic_tools/test/tests/surrogates/load_store/train_and_evaluate.i:58`
- Statistics and Sobol indices analytically from a `PolynomialChaos` surrogate — no resampling. Required: `pc_name`. Useful: `include_data = true`.

### `[MultiApps]` (ST types)

##### `SamplerFullSolveMultiApp`
- Source: `modules/stochastic_tools/include/multiapps/SamplerFullSolveMultiApp.h:21`
- Example: `modules/stochastic_tools/test/tests/multiapps/sampler_full_solve_multiapp/parent_full_solve.i:21`
- One full forward solve per sampler row. Most common ST multi-app. Required: `sampler`, `input_files`. Useful: `mode` (`normal|batch-reset|batch-restore|batch-keep-solution`), `min_procs_per_app`, `should_run_reporter` (AL skip), `ignore_solve_not_converge`.
- Mode choice: `batch-restore` fastest for repeatable initial state (default for big studies); `batch-reset` if the sub-app holds mutable state; `batch-keep-solution` for adaptive samplers.

##### `SamplerTransientMultiApp`
- Source: `modules/stochastic_tools/include/multiapps/SamplerTransientMultiApp.h:21`
- Example: `modules/stochastic_tools/test/tests/multiapps/sampler_transient_multiapp/parent_transient.i:27`
- Sub-apps step in lockstep with the parent's transient executioner. Pair with parent `[Executioner] type = Transient` and `auto_create_executioner = false` on `[StochasticTools]`. Required: `sampler`, `input_files`.

### `[Transfers]` (ST types)

##### `SamplerParameterTransfer` (parent → sub-app)
- Source: `modules/stochastic_tools/include/transfers/SamplerParameterTransfer.h:21`
- Example: `modules/stochastic_tools/examples/parameter_study/main.i:46`
- Per-row, writes values into named **controllable** sub-app parameters via the sub-side `SamplerReceiver`. Required: `to_multi_app`, `sampler`, `parameters` (path list, e.g. `'Materials/k/prop_values BCs/left/value'`). Useful: `to_control = 'stochastic'` (matches the sub-side Controls sub-block name), `check_multiapp_execute_on = false`.

##### `SamplerReporterTransfer` (sub-app → parent)
- Source: `modules/stochastic_tools/include/transfers/SamplerReporterTransfer.h:24`
- Example: `modules/stochastic_tools/examples/parameter_study/main.i:52`
- Pulls named sub-app reporter values back into a parent `StochasticReporter`, indexed by row. Reporter names use `<reporter>/<value>` form (e.g. `T_avg/value`). Required: `from_multi_app`, `sampler`, `stochastic_reporter`, `from_reporter`.

##### `SamplerPostprocessorTransfer` (legacy)
- Source: `modules/stochastic_tools/include/transfers/SamplerPostprocessorTransfer.h:25`
- Example: `modules/stochastic_tools/test/tests/transfers/sampler_postprocessor/parent.i:55`
- Older variant pulling Postprocessors into a `StochasticResults` VectorPostprocessor. Prefer the reporter version. Required: `from_multi_app`, `sampler`, `to_vector_postprocessor`, `from_postprocessor`.

##### `SerializedSolutionTransfer` (POD)
- Source: `modules/stochastic_tools/include/transfers/SerializedSolutionTransfer.h`
- Example: `modules/stochastic_tools/test/tests/variablemappings/pod_mapping/pod_mapping_main.i:54`
- Pulls full sub-app solution vectors into `ParallelSolutionStorage` — feeds the POD snapshot matrix. Required: `from_multi_app`, `sampler`, `parallel_storage`, `solution_container`, `variables`.

### `[Controls]` (ST types)

##### `SamplerReceiver` (sub-app side)
- Source: `modules/stochastic_tools/include/controls/SamplerReceiver.h:21`
- Example: `modules/stochastic_tools/test/tests/surrogates/poly_chaos/sub.i:67` (sub-block `[stochastic]`)
- Receiving end of `SamplerParameterTransfer`. Place in the sub-app `.i`. No required params; the sub-block name (any name) must match the parent's `to_control` if set. Only `SamplerParameterTransfer` can write into it (private API).

##### `MultiAppSamplerControl` (parent side, pre-construction)
- Source: `modules/stochastic_tools/include/controls/MultiAppSamplerControl.h:25`
- Example: `modules/stochastic_tools/test/tests/surrogates/gaussian_process/GP_squared_exponential_training.i:35`
- Splices row values into the sub-app's `cli_args` on `PRE_MULTIAPP_SETUP` (before construction). Use for params consumed at constructor time (mesh `nx`, file paths, FE `order`). Required: `multi_app`, `sampler`, `param_names`.
- `param_names` accepts dotted paths (`Materials/conductivity/prop_values`) and top-level `var = ...` names (see `mcmc/main_imh.i:64`).

### `[StochasticTools]` action

Top-level meta-block that expands to a default mesh + problem + executioner so a parent ST input doesn't need its own `[Mesh]` / `[Executioner]` when it's only orchestrating sub-apps.

- Source: `modules/stochastic_tools/include/actions/StochasticToolsAction.h:19`
- Example: `modules/stochastic_tools/test/tests/multiapps/sampler_full_solve_multiapp/parent_full_solve.i:1`
- Params (all default `true`): `auto_create_mesh` (1-element `GeneratedMeshGenerator`), `auto_create_problem`, `auto_create_executioner` (creates `Steady`). Set `auto_create_executioner = false` when supplying your own `[Executioner] type = Transient` (paired with `SamplerTransientMultiApp` or MCMC).

## Cross-cutting concerns

### Standard parent-side shape (forward UQ)

```hit
[StochasticTools]                  # placeholder mesh + Steady executioner
[Distributions/...]                # one per uncertain parameter
[Samplers/sampler]                 # MonteCarlo / LatinHypercube / Quadrature / ...
[MultiApps/runner]                 # SamplerFullSolveMultiApp
[Transfers/parameters]             # SamplerParameterTransfer (parent -> sub)
[Transfers/results]                # SamplerReporterTransfer  (sub -> parent)
[Reporters/results]                # StochasticReporter
[Reporters/stats]                  # StatisticsReporter
```

The sub-app input must include `[Controls/<name>] type = SamplerReceiver` and Postprocessors / Reporters / VectorPostprocessors declaring every QoI named in `from_reporter`. QoIs don't need to be controllable — only mutated parameters do.

### Two ways to push parameters into sub-apps

1. **`SamplerParameterTransfer` + `SamplerReceiver`** (runtime). `parameters = 'BCs/left/value Materials/k/prop_values'` mutates **controllable** params per-row after sub-app construction. Default for numeric inputs.
2. **`MultiAppSamplerControl` + `cli_args`** (construction-time, runs on `PRE_MULTIAPP_SETUP`). Required for params consumed at constructor time — mesh `nx`/`ny`, FE `order`, file paths, anything in `[Mesh]`.

The two compose; one parent can use both.

### Train/evaluate split

- **Training**: `[StochasticTools]` + `[Distributions]` + `[Samplers]` + `SamplerFullSolveMultiApp` + transfers + `[Reporters/storage]` + `[Trainers]` + `[Outputs] type = SurrogateTrainerOutput`. Produces `<file_base>_<trainer>.rd/`.
- **Evaluation**: separate input with `[Samplers]` (larger) + `[Surrogates] filename = '...'` + `[Reporters] type = EvaluateSurrogate`. No MultiApp, no Transfers.
- Combined `train_and_evaluate.i` is fine for iteration; split for production.

### `from_reporter` and reporter naming

`<name>/<value>` pairs: `[Postprocessors/T_avg]` → `T_avg/value`; `[VectorPostprocessors/vpp] vector_names = 'vec'` → `vpp/vec`; `[Reporters/constant] integer_names = 'int'` → `constant/int`. Parent references the slot as `<storage>/<transfer>:<reporter>:<value>` — e.g. `results/results:T_avg:value` when both storage block and transfer are named `results`. Type auto-detected.

### `parameters = '...'` paths

Dotted-path: `BCs/left/value`, `Materials/k/prop_values` (vector — one matrix column per element), `Kernels/source/value`, `Executioner/nl_rel_tol`. Position-binds: column 0 → first parameter. `len(paths) == sampler.num_cols`.

### `mode = batch-*` requires `StochasticToolsTransfer`

`SamplerFullSolveMultiApp` modes `batch-reset`/`batch-restore`/`batch-keep-solution` recycle one sub-app across rows (much faster than `normal`) and drive transfers via `*FromMultiapp`/`*ToMultiapp` hooks on `StochasticToolsTransfer`. A plain `MultiAppCopyTransfer` is silently dropped. All ST transfers already derive from it.

### `parallel_type = ROOT`

Set on `StochasticReporter` / `EvaluateSurrogate` when a downstream serial consumer (CSV/JSON, postprocessing) needs the full vector on rank 0. Without it, each rank holds only its local rows.

## Minimal scaffold

Forward UQ for 2D transient diffusion with two uncertain parameters (diffusivity, source). Two files.

### Parent: `main.i`

```hit
[StochasticTools]
[]

[Distributions]
  [k_dist]
    type = Uniform
    lower_bound = 0.5
    upper_bound = 2.5
  []
  [q_dist]
    type = Normal
    mean = 100
    standard_deviation = 25
  []
[]

[Samplers/sampler]
  type = LatinHypercube
  num_rows = 200
  distributions = 'k_dist q_dist'
  seed = 1980
  execute_on = PRE_MULTIAPP_SETUP
[]

[MultiApps/runner]
  type = SamplerFullSolveMultiApp
  sampler = sampler
  input_files = 'sub.i'
  mode = batch-restore
[]

[Transfers/parameters]
  type = SamplerParameterTransfer
  to_multi_app = runner
  sampler = sampler
  parameters = 'Materials/constant/prop_values Kernels/source/value'
[]
[Transfers/results]
  type = SamplerReporterTransfer
  from_multi_app = runner
  sampler = sampler
  stochastic_reporter = results
  from_reporter = 'T_avg/value q_left/value'
[]

[Reporters/results]
  type = StochasticReporter
  parallel_type = ROOT
[]
[Reporters/stats]
  type = StatisticsReporter
  reporters = 'results/results:T_avg:value results/results:q_left:value'
  compute = 'mean stddev'
  ci_method = 'percentile'
  ci_levels = '0.05 0.95'
  ci_replicates = 1000
[]

[Outputs/out]
  type = JSON
  execute_on = FINAL
[]
```

### Sub: `sub.i`

```hit
[Mesh]
  type = GeneratedMesh
  dim = 2
  nx = 10
  ny = 10
[]

[Variables/T]
  initial_condition = 300
[]

[Kernels]
  [time]
    type = ADTimeDerivative
    variable = T
  []
  [diff]
    type = ADMatDiffusion
    variable = T
    diffusivity = diffusivity
  []
  [source]
    type = ADBodyForce
    variable = T
    value = 100               # mutated per-row by SamplerParameterTransfer
  []
[]

[BCs/left]
  type = ADDirichletBC
  variable = T
  boundary = left
  value = 300
[]
[BCs/right]
  type = ADNeumannBC
  variable = T
  boundary = right
  value = -100
[]

[Materials/constant]
  type = ADGenericConstantMaterial
  prop_names = 'diffusivity'
  prop_values = 1             # mutated per-row by SamplerParameterTransfer
[]

[Executioner]
  type = Transient
  num_steps = 4
  dt = 0.25
[]

[Postprocessors]
  [T_avg]
    type = ElementAverageValue
    variable = T
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [q_left]
    type = ADSideDiffusiveFluxAverage
    variable = T
    boundary = left
    diffusivity = diffusivity
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Controls/stochastic]         # receives parameters from SamplerParameterTransfer
  type = SamplerReceiver
[]
```

Parameter paths bind by position: column 0 → `Materials/constant/prop_values` (`k_dist`), column 1 → `Kernels/source/value` (`q_dist`). Each row's `T_avg/value` and `q_left/value` flow back via `SamplerReporterTransfer`; `StatisticsReporter` yields mean/stddev with bootstrap percentile CIs. To convert to Sobol: replace `[Samplers/sampler]` with two MC base samplers + a `Sobol` sampler + a `SobolReporter`. To convert to a surrogate fit: add `[Trainers]` + `SurrogateTrainerOutput`, then write a separate `evaluate.i` that loads the `*.rd/` via `[Surrogates]` + `EvaluateSurrogate`.
