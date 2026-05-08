# Authoring inputs: MultiApps + Transfers (multi-scale / multi-physics coupling)

Reach for this guide when you need to set up a parent-app + sub-app(s) coupling in a `.i` file by **picking from the catalog** of registered MultiApp drivers and Transfer objects. The two blocks always come as a pair: a `[MultiApps]` block defines what runs as a sub-app, a `[Transfers]` block defines what data crosses between parent and sub. If you only need a postprocessor *inside* one app (no sub-apps), see [postprocess.md] (not in this guide). If you need a stochastic / sampler-driven sweep see the stochastic-tools cross-link.

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. Each catalog entry cites both the **source header** (`<file>:<line of class>`) and one **canonical example .i** (`<file>:<line of the sub-block>`).

## When to use this (vs alternatives)

Decide **MultiApp type** first (steady? transient? per-element?), then choose **transfer flavor** (field, postprocessor, reporter), then set the **direction** (`from_multi_app` / `to_multi_app` / both for siblings).

1. Sub-app should run a **complete solve every time the parent invokes it** (steady, eigenvalue, optimization sub-iteration, sampling sweep): use `FullSolveMultiApp`. Typical with `Steady` parent or `execute_on = initial/timestep_end` + a `Steady`/`SteadyWithNull` sub-Executioner.
2. Sub-app must **advance in time alongside the parent** (lockstep transient, sub-cycling, fixed-point Picard): use `TransientMultiApp`. Sub must use a `Transient` Executioner. Turn on `sub_cycling = true` if the sub needs smaller `dt` than the parent; pair with `interpolate_transfers = true` so transfers don't step-jump.
3. Sub-app needs **one instance per element** (for a 1D-in-cell or per-cell ROM): use `CentroidMultiApp` (positions = element centroids, block-restrictable) or `QuadraturePointMultiApp` (positions = each qp). These are `TransientMultiApp` subclasses; positions are auto-generated.
4. Sub-app is a **sampler-driven Monte Carlo / quadrature sweep** (UQ, surrogate training): use `SamplerFullSolveMultiApp` or `SamplerTransientMultiApp` (stochastic_tools — see stochastic-tools.md). Pair with `SamplerParameterTransfer` (push parameters) + `SamplerReporterTransfer` / `SamplerPostprocessorTransfer` (pull results).
5. Sub-app drives an **optimization loop**: see optimization.md — typical pattern is a `FullSolveMultiApp` for the forward solve and another for the adjoint, driven by an `OptimizeSolve` Executioner.

Then for **what data to send**:

- **Field of values** (variable on a mesh -> variable on a mesh): pick from `MultiAppGeneralFieldNearestLocationTransfer` / `MultiAppGeneralFieldShapeEvaluationTransfer` / `MultiAppGeneralFieldUserObjectTransfer`. These three are the modern recommended path; older `MultiAppNearestNodeTransfer`, `MultiAppShapeEvaluationTransfer` (a.k.a. `MultiAppMeshFunctionTransfer`), `MultiAppUserObjectTransfer` are deprecated. Use `MultiAppCopyTransfer` only when both meshes are identical (zero interpolation).
- **Single scalar number** (postprocessor -> postprocessor): `MultiAppPostprocessorTransfer`. To spread one parent PP across many sub-apps as a field: `MultiAppPostprocessorInterpolationTransfer`. To push a PP into a `[AuxScalars]` variable (or vice versa): `MultiAppPostprocessorToAuxScalarTransfer` / `MultiAppScalarToAuxScalarTransfer`.
- **Reporter / vector / arbitrary structured data**: `MultiAppReporterTransfer` (preferred for new inputs — supersedes `MultiAppVectorPostprocessorTransfer`). Use `MultiAppCloneReporterTransfer` if you want the parent reporter declared automatically from a sub-app reporter.

## Catalog

### `[MultiApps]` — sub-app drivers

#### Steady-style

##### `FullSolveMultiApp`
- Source: `framework/include/multiapps/FullSolveMultiApp.h:19`
- Example: `test/tests/multiapps/full_solve_multiapp/parent.i:49` (sub-block `[full_solve]`)
- Each parent step (or just `initial`) drives one full sub-app solve to completion. Sub-app Executioner can be `Steady`, `Transient` (runs to its own end-time), `Eigenvalue`, etc.
- Required: `app_type` (or it inherits parent's), `input_files`, plus one of `positions` / `positions_file` / `positions_objects` (defaults to `(0,0,0)` if all omitted).
- Useful: `execute_on` (default `TIMESTEP_BEGIN` — set `initial` for a one-shot pre-solve), `cli_args`, `keep_solution_during_restore`, `ignore_solve_not_converge`.

##### `SamplerFullSolveMultiApp` (stochastic_tools — see [stochastic-tools.md])
- Source: `modules/stochastic_tools/include/multiapps/SamplerFullSolveMultiApp.h:21`
- Example: `modules/stochastic_tools/test/tests/surrogates/load_store/train.i:26` (sub-block `[quad_sub]`)
- Spawns one full-solve sub-app per sampler row. Positions are taken from the sampler; do NOT supply `positions`.
- Required: `input_files`, `sampler`.
- Useful: `mode` (`normal | batch-reset | batch-restore | batch-no-restore` — controls how many sub-apps live concurrently), `cli_args`, `min_procs_per_app`, `max_procs_per_app`.

#### Transient

##### `TransientMultiApp`
- Source: `framework/include/multiapps/TransientMultiApp.h:23`
- Example: `test/tests/multiapps/transient_multiapp/dt_from_multi.i:54` (sub-block `[sub]`); positions-from-file: `test/tests/multiapps/positions_from_file/dt_from_multi.i:54`
- Sub-app advances one time step every parent time step (lockstep) by default. Sub must use a `Transient` Executioner.
- Required: `app_type`, `input_files`, positions (or default to origin).
- Useful: `execute_on` (default `TIMESTEP_BEGIN`; set to `TIMESTEP_END` for after-solve transfers), `sub_cycling` (let sub take its own smaller `dt`), `interpolate_transfers` (interpolate parent values across the sub's sub-steps), `output_sub_cycles`, `detect_steady_state`, `tolerate_failure`, `catch_up`, `max_catch_up_steps`.

##### `SamplerTransientMultiApp` (stochastic_tools)
- Source: `modules/stochastic_tools/include/multiapps/SamplerTransientMultiApp.h:21`
- Example: `modules/stochastic_tools/test/tests/vectorpostprocessors/stochastic_results/parent.i:38` (sub-block `[sub]`)
- Transient analog of `SamplerFullSolveMultiApp` — one transient sub-app per sampler row, advancing in lockstep with the parent transient.
- Required: `input_files`, `sampler`.
- Useful: `mode`, `cli_args`, `min_procs_per_app`.

#### Per-element / per-quadrature-point

##### `CentroidMultiApp`
- Source: `framework/include/multiapps/CentroidMultiApp.h:18`
- Example: `test/tests/multiapps/centroid_multiapp/centroid_multiapp.i:71` (sub-block `[sub]`)
- Auto-generates one sub-app at the centroid of every element (block-restrictable). Inherits from `TransientMultiApp` — sub must be transient.
- Required: `input_files`. Do NOT supply `positions` — they're computed.
- Useful: `block` (subdomain restriction), `output_in_position`, `cli_args`, `execute_on`.

##### `QuadraturePointMultiApp`
- Source: `framework/include/multiapps/QuadraturePointMultiApp.h:18`
- Example: `test/tests/multiapps/quadrature_point_multiapp/quadrature_point_multiapp.i:49` (sub-block `[sub]`)
- One sub-app at every quadrature point. Same as `CentroidMultiApp` but finer (typically used with low-order ROMs at qps for material-point sub-physics).
- Required: `input_files`. No `positions`.
- Useful: `block`, `cli_args` (commonly used to set per-qp postprocessor names — see the example), `run_in_position`.

### `[Transfers]` — data movement between parent and sub-app(s)

#### Field transfers (general — modern path)

##### `MultiAppGeneralFieldNearestLocationTransfer`
- Source: `framework/include/transfers/MultiAppGeneralFieldNearestLocationTransfer.h:20`
- Example: `test/tests/transfers/general_field/nearest_node/regular/main.i:67` (sub-block `[to_sub]`)
- Sets each target dof to the value at the nearest source location (nearest-node-style). Robust to non-conforming meshes; works between siblings; parallel-aware.
- Required: `from_multi_app` and/or `to_multi_app`, `source_variable`, `variable`.
- Useful: `execute_on` (default inherits MultiApp's), `displaced_source_mesh`, `displaced_target_mesh`, `from_blocks` / `to_blocks`, `from_boundaries` / `to_boundaries`, `bbox_factor`, `greedy_search`.

##### `MultiAppGeneralFieldShapeEvaluationTransfer`
- Source: `framework/include/transfers/MultiAppGeneralFieldShapeEvaluationTransfer.h:19`
- Example: `test/tests/transfers/general_field/shape_evaluation/regular/main.i:66` (sub-block `[to_sub]`)
- Evaluates the source variable's FE shape function at each target point — interpolating, not nearest. Most accurate for FE source variables.
- Required: `from_multi_app` and/or `to_multi_app`, `source_variable`, `variable`.
- Useful: `execute_on`, `displaced_source_mesh`, `displaced_target_mesh`, `from_blocks` / `to_blocks`.

##### `MultiAppGeneralFieldUserObjectTransfer`
- Source: `framework/include/transfers/MultiAppGeneralFieldUserObjectTransfer.h:20`
- Example: `test/tests/transfers/general_field/user_object/regular/main.i:83` (sub-block `[to_sub]`)
- Source values come from a `SpatialUserObject` (e.g. `LayeredAverage`, `NearestPointLayeredAverage`) instead of a variable — the UO does any custom averaging / projection.
- Required: `from_multi_app` and/or `to_multi_app`, `source_user_object`, `variable`.
- Useful: `execute_on`, `displaced_target_mesh`, `from_blocks` / `to_blocks`, `skip_bounding_box_check`.

##### `MultiAppCopyTransfer`
- Source: `framework/include/transfers/MultiAppCopyTransfer.h:23`
- Example: `test/tests/transfers/multiapp_copy_transfer/aux_to_aux/from_sub.i:15` (sub-block `[from_sub]`)
- Direct dof-to-dof copy. Both meshes must be identical (same node/element ordering). Fastest possible field transfer; zero interpolation.
- Required: `from_multi_app` xor `to_multi_app`, `source_variable`, `variable`.
- Useful: `execute_on`, `displaced_source_mesh`, `displaced_target_mesh`.

#### Specialized field transfers

##### Deprecated field transfers (use General-Field replacements above)
- `MultiAppShapeEvaluationTransfer` (alias `MultiAppMeshFunctionTransfer`) — `framework/include/transfers/MultiAppShapeEvaluationTransfer.h:19` -> use `MultiAppGeneralFieldShapeEvaluationTransfer`.
- `MultiAppNearestNodeTransfer` — `framework/include/transfers/MultiAppNearestNodeTransfer.h:24` -> use `MultiAppGeneralFieldNearestLocationTransfer`.
- `MultiAppUserObjectTransfer` — `framework/include/transfers/MultiAppUserObjectTransfer.h:28` -> use `MultiAppGeneralFieldUserObjectTransfer`.
- All three were deprecated 12/31/2024 and emit `mooseDeprecated` warnings. Same required params as their replacements.

##### `MultiAppGeometricInterpolationTransfer` (alias `MultiAppInterpolationTransfer`)
- Source: `framework/include/transfers/MultiAppGeometricInterpolationTransfer.h:28`
- Example: `test/tests/transfers/multiapp_interpolation_transfer/tosub_parent.i:103` (sub-block `[tosub]`)
- Inverse-distance / radial-basis interpolation between point clouds. Requires `parallel_type = replicated` on both meshes.
- Required: `from_multi_app` xor `to_multi_app`, `source_variable`, `variable`.
- Useful: `interp_type` (`inverse_distance | radial_basis`), `num_points`, `power`, `radius`.

##### `MultiAppProjectionTransfer`
- Source: `framework/include/transfers/MultiAppProjectionTransfer.h:23`
- Example: `test/tests/transfers/multiapp_projection_transfer/tosub_parent.i:88` (sub-block `[tosub]`)
- L2 projection from source variable to target variable — solves a small mass-matrix system. Conservative for elemental targets; smooths jumps. Slower than nearest/shape; pick when conservation matters.
- Required: `from_multi_app` xor `to_multi_app`, `source_variable`, `variable`.
- Useful: `proj_type` (`l2 | h1`), `fixed_meshes`, `displaced_source_mesh`, `displaced_target_mesh`.

#### Postprocessor / Reporter / scalar

##### `MultiAppPostprocessorTransfer`
- Source: `framework/include/transfers/MultiAppPostprocessorTransfer.h:20`
- Example: `test/tests/transfers/multiapp_postprocessor_transfer/parent.i:74` (sub-block `[pp_transfer]`); sibling: `test/tests/transfers/multiapp_postprocessor_transfer/between_multiapp/main.i:69`
- One scalar (Postprocessor) -> one scalar (Postprocessor). When pulling from many sub-apps, use `reduction_type` to fold them.
- Required: `from_multi_app` and/or `to_multi_app`, `from_postprocessor`, `to_postprocessor`.
- Useful: `reduction_type` (`average | sum | minimum | maximum`), `execute_on`, `subapp_index`.

##### `MultiAppPostprocessorInterpolationTransfer`
- Source: `framework/include/transfers/MultiAppPostprocessorInterpolationTransfer.h:20`
- Example: `test/tests/transfers/multiapp_postprocessor_interpolation_transfer/parent.i:64` (sub-block `[pp_transfer]`)
- Each sub-app's postprocessor is treated as a value at the sub-app's position; the parent variable is interpolated from those scattered values.
- Required: `from_multi_app`, `postprocessor`, `variable`.
- Useful: `num_points`, `power`, `interp_type` (`inverse_distance | radial_basis`), `radius`.

##### `MultiAppReporterTransfer`
- Source: `framework/include/transfers/MultiAppReporterTransfer.h:18`
- Example: `test/tests/transfers/multiapp_reporter_transfer/main.i:58` (sub-block `[vpp_to_vpp]`)
- General reporter -> reporter transfer. Reporters subsume postprocessors, vector-postprocessors, and arbitrary scalar/vector data, so this is the modern catch-all. `from_reporters`/`to_reporters` are paired-by-position lists.
- Required: `from_multi_app` and/or `to_multi_app`, `from_reporters`, `to_reporters`.
- Useful: `subapp_index`, `distribute_reporter_vector`, `execute_on`.

##### `MultiAppCloneReporterTransfer`
- Source: `framework/include/transfers/MultiAppCloneReporterTransfer.h:18`
- Example: `test/tests/transfers/multiapp_reporter_transfer/clone.i:47` (sub-block `[multi_vpp]`); also `[multi_rep]:53` in the same file.
- Pulls reporters from sub-apps without you having to declare them in the parent; the clone transfer auto-creates them.
- Required: `from_multi_app`, `from_reporters`.
- Useful: `subapp_index`.

##### `MultiAppVectorPostprocessorTransfer`
- Source: `framework/include/transfers/MultiAppVectorPostprocessorTransfer.h:20`
- Example: `test/tests/transfers/multiapp_vector_pp_transfer/parent.i:61` (sub-block `[send]`)
- Older path: VectorPostprocessor <-> Postprocessor across many sub-apps. Prefer `MultiAppReporterTransfer` for new inputs.
- Required: `from_multi_app` xor `to_multi_app`, `vector_postprocessor`, `postprocessor`, `vector_name`.

##### `MultiAppScalarToAuxScalarTransfer`
- Source: `framework/include/transfers/MultiAppScalarToAuxScalarTransfer.h:18`
- Example: `test/tests/transfers/multiapp_scalar_to_auxscalar_transfer/from_sub/parent.i:40` (sub-block `[from_sub]`)
- `[Variables]` scalar -> `[AuxVariables]` scalar (or v.v.). For `addCoupledVar`-style scalar coupling between apps.
- Required: `from_multi_app` xor `to_multi_app`, `source_variable`, `to_aux_scalar`.

##### `MultiAppPostprocessorToAuxScalarTransfer`
- Source: `framework/include/transfers/MultiAppPostprocessorToAuxScalarTransfer.h:18`
- Example: `test/tests/transfers/multiapp_postprocessor_to_scalar/parent.i:72` (sub-block `[pp_transfer]`)
- Postprocessor -> `[AuxScalars]` scalar variable. Use when you want a sub-app PP exposed as a scalar AuxVariable in the receiver.
- Required: `from_multi_app` xor `to_multi_app`, `from_postprocessor`, `to_aux_scalar`.

##### `MultiAppVariableValueSamplePostprocessorTransfer`
- Source: `framework/include/transfers/MultiAppVariableValueSamplePostprocessorTransfer.h:19`
- Example: `test/tests/multiapps/centroid_multiapp/centroid_multiapp.i:80` (sub-block `[incoming_x]`)
- Samples the parent variable at each sub-app's position and pushes the value into a sub-app postprocessor. The natural pair for `CentroidMultiApp` / `QuadraturePointMultiApp`.
- Required: `to_multi_app`, `source_variable`, `postprocessor`.

##### `MultiAppVariableValueSampleTransfer`
- Source: `framework/include/transfers/MultiAppVariableValueSampleTransfer.h:19`
- Example: `test/tests/transfers/multiapp_variable_value_sample_transfer/parent.i:64` (sub-block `[sample_transfer]`)
- Like the Postprocessor-sample version above but writes into a sub-app variable directly.
- Required: `to_multi_app`, `source_variable`, `variable`.

#### Stochastic — sampler-driven (stochastic_tools — see [stochastic-tools.md])

##### `SamplerParameterTransfer`
- Source: `modules/stochastic_tools/include/transfers/SamplerParameterTransfer.h:21`
- Example: `modules/stochastic_tools/test/tests/vectorpostprocessors/stochastic_results/parent.i:46` (sub-block `[runner]`)
- Pushes one sampler row per sub-app into named parameters (HIT paths) of the sub-app, replacing them on each invocation. The standard way to drive parameter sweeps.
- Required: `to_multi_app`, `sampler`, `parameters` (list of HIT paths).

##### `SamplerPostprocessorTransfer`
- Source: `modules/stochastic_tools/include/transfers/SamplerPostprocessorTransfer.h:25`
- Example: `modules/stochastic_tools/test/tests/vectorpostprocessors/stochastic_results/parent.i:53` (sub-block `[data]`)
- Pulls one Postprocessor per sub-app into a `StochasticResults` VectorPostprocessor — one row per sample.
- Required: `from_multi_app`, `sampler`, `to_vector_postprocessor`, `from_postprocessor`.

##### `SamplerReporterTransfer`
- Source: `modules/stochastic_tools/include/transfers/SamplerReporterTransfer.h:24`
- Example: `modules/stochastic_tools/test/tests/surrogates/load_store/train.i:42` (sub-block `[data]`)
- Like `SamplerPostprocessorTransfer` but for arbitrary reporter values; data lands in a `StochasticReporter` in the parent.
- Required: `from_multi_app`, `sampler`, `stochastic_reporter`, `from_reporter`.

## Cross-cutting concerns

### Direction parameters: `from_multi_app` vs `to_multi_app` vs sibling
- `to_multi_app = subname` -> parent pushes data **into** the named sub-app.
- `from_multi_app = subname` -> parent pulls data **out of** the named sub-app.
- Both set on the same Transfer -> **sibling transfer** between two sub-apps. There is no `between_multi_app` parameter — supplying both `from_multi_app` and `to_multi_app` is the supported sibling syntax (`test/tests/transfers/multiapp_postprocessor_transfer/between_multiapp/main.i:69`).
- A few specialty transfers (`MultiAppVariableValueSamplePostprocessorTransfer`, sampler transfers) only make sense in one direction.

### `execute_on` timing
- `[MultiApps]` `execute_on` controls **when the sub-app runs** (`INITIAL`, `TIMESTEP_BEGIN`, `TIMESTEP_END`, `MULTIAPP_FIXED_POINT_BEGIN/END`, `FINAL`, `POST_ADAPTIVITY`, `NONLINEAR`, `LINEAR`).
- `[Transfers]` `execute_on` controls **when data moves**, defaulting to the MultiApp's `execute_on` (the framework cross-checks unless `check_multiapp_execute_on = false`).
- Common pattern: parent solves, sub runs at `TIMESTEP_END`, parent->sub transfers fire just before, sub->parent just after. Picard fixed-point coupling uses `MULTIAPP_FIXED_POINT_BEGIN/END`. For one-shot pre-computations set both to `initial`.

### Positions / how many sub-apps
- `positions = 'x1 y1 z1 x2 y2 z2 ...'` -> N sub-apps (one per triple); `input_files` is matched 1:1 or a single input is reused.
- `positions_file = file.txt` -> read triples from disk; `positions_objects = pos_obj` -> a `[Positions]` UO computes them dynamically.
- Omit all three -> single sub-app at `(0,0,0)` (correct for 1-to-1 multi-physics on one mesh).
- `CentroidMultiApp` / `QuadraturePointMultiApp` compute positions from the parent mesh — do NOT supply positions.
- `output_in_position = true` translates each sub-app's Exodus output by its position vector; `run_in_position = true` actually moves the sub-app's mesh into world space.

### `cli_args` for parameter sweeps
- `cli_args = 'BCs/left/value=1.0;Materials/d/prop_values=0.5'` injects HIT-path overrides into each sub-app, exactly as if typed after `-i sub.i`. Pass one set -> applied to all; N sets (or `cli_args_files`) -> one per position. See `quadrature_point_multiapp.i:54` for per-qp postprocessor configuration.
- For sampler-driven sweeps, prefer `SamplerParameterTransfer` — it re-applies parameters every sample without recreating sub-apps.

### `sub_cycling` and `interpolate_transfers` (TransientMultiApp only)
- `sub_cycling = true` -> the sub-app picks its own (typically smaller) `dt`; it catches up to the parent's current time via N internal steps before transfers fire.
- `interpolate_transfers = true` -> when sub-cycling, the parent's transferred values are linearly interpolated across sub-cycles instead of held constant. Almost always wanted when the parent source changes across one parent step.
- Canonical: `test/tests/multiapps/sub_cycling/parent.i:54`. Related knobs: `detect_steady_state`, `tolerate_failure`, `catch_up` + `max_catch_up_steps`.

### Sub-app `[Outputs]` independence
- Each sub-app has its own `[Outputs]` block — files come out per sub-app, named `<parent_out>_<sub>_<idx>.e`. Sub `[Postprocessors]`/`[Reporters]` are visible to the parent only through a Transfer.
- Suppress with `[Outputs] none = true` in the sub `.i`, or `output_sub_cycles = false` on the parent MultiApp to hide sub-cycle frames.

### Reporter-based vs PP-based coupling
- `[Reporters]` + `MultiAppReporterTransfer` is the modern general-purpose coupling — scalars, vectors, mixed structured data, broadcast-or-distributed semantics.
- `[Postprocessors]` + `MultiAppPostprocessorTransfer` is still the simplest single-scalar coupling and is well-tested.
- VectorPostprocessors + `MultiAppVectorPostprocessorTransfer` still work but for new inputs prefer reporters.
- Field transfers (variable-to-variable) are orthogonal — they always go through `MultiAppGeneralField*Transfer` / `MultiAppCopyTransfer`.

### Restart / reset
- `keep_solution_during_restore = true` preserves the sub's nonlinear solution across parent timestep restores (fixed-point / recover); default `false`.
- `reset_apps` + `reset_time` destroy and recreate listed sub-apps (model "new material" insertion); `move_apps` + `move_time` + `move_positions` relocate them.

## Minimal scaffold

Parent `.i` (transient parent + per-sub field transfer pulled back at end of step):

```hit
[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 2
    nx = 10
    ny = 10
  []
[]

[Variables]
  [u]
  []
[]

[AuxVariables]
  [u_from_sub]
  []
[]

[Kernels]
  [diff]
    type = ADDiffusion
    variable = u
  []
  [td]
    type = ADTimeDerivative
    variable = u
  []
[]

[BCs]
  [all]
    type = ADDirichletBC
    variable = u
    boundary = 'left right top bottom'
    value = 0
  []
[]

[Executioner]
  type = Transient
  num_steps = 5
  dt = 0.1
  solve_type = NEWTON
[]

[MultiApps]
  [sub]
    type = TransientMultiApp
    input_files = sub.i
    positions = '0.25 0.25 0  0.75 0.75 0'
    execute_on = TIMESTEP_END
    output_in_position = true
  []
[]

[Transfers]
  # Push parent u into sub's incoming aux var
  [push_u]
    type = MultiAppGeneralFieldShapeEvaluationTransfer
    to_multi_app = sub
    source_variable = u
    variable = u_from_parent
    execute_on = TIMESTEP_END
  []
  # Pull sub's solution back into parent aux
  [pull_u]
    type = MultiAppGeneralFieldNearestLocationTransfer
    from_multi_app = sub
    source_variable = v
    variable = u_from_sub
    execute_on = TIMESTEP_END
  []
[]

[Outputs]
  exodus = true
[]
```

Sub `.i` (each sub-app does its own transient solve every parent step):

```hit
[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 2
    nx = 5
    ny = 5
    xmax = 0.2
    ymax = 0.2
  []
[]

[Variables/v]
[]

[AuxVariables/u_from_parent]
[]

[Kernels]
  [diff]
    type = ADDiffusion
    variable = v
  []
  [src]
    type = ADCoupledForce
    variable = v
    v = u_from_parent
  []
[]

[BCs/all]
  type = ADDirichletBC
  variable = v
  boundary = 'left right top bottom'
  value = 0
[]

[Executioner]
  type = Transient
  num_steps = 1
  dt = 0.1
  solve_type = NEWTON
[]

[Outputs]
  exodus = true
[]
```

Variant — postprocessor coupling instead of field coupling: replace the parent `[Transfers]` block with two `MultiAppPostprocessorTransfer` entries (one with `to_multi_app`, one with `from_multi_app` + `reduction_type = average`), and declare matching PPs in both apps.
