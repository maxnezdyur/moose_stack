# Authoring inputs: Adaptivity & Restart/Checkpoint

Reach for this guide when you need to **add `[Adaptivity]`** to a `.i` file (refine the mesh during a solve based on error indicators or geometric regions), or when you need to **resume a simulation** from a checkpoint, recover from a crash, or seed initial conditions from a previous run's Exodus output. Both topics are "stuff that lives outside any physics block" — they configure the executioner / problem rather than contributing residuals.

If you only want a one-shot uniform refinement of the *initial* mesh, see [mesh.md](./mesh.md) (`uniform_refine` on `[Mesh]`). If you want to write the checkpoint files themselves, see [outputs.md](./outputs.md). If your initial condition is a parsed function instead of a previous run's solution, see [ics.md](./ics.md).

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. Each catalog entry cites both the **source header** (`<file>:<line of class>`) and one **canonical example .i** (`<file>:<line of the sub-block>`).

## When to use this (vs alternatives)

`[Adaptivity]`:

1. **Mesh-adaptive refinement during solve** (h-refinement / p-refinement / hp-refinement, splitting elements where an error indicator says the discretization is too coarse): use `[Adaptivity]` with a Marker (and usually an Indicator). Steady runs use `steps`; transient runs use `cycles_per_step` and `interval`.
2. **One-shot uniform refinement of the initial mesh** (no adaptive logic during the solve): set `[Mesh] uniform_refine = N` instead — see [mesh.md](./mesh.md). Don't put `UniformMarker` in `[Adaptivity]` for this; that re-runs adaptivity every `interval` steps.
3. **Refine *only* once before the first solve based on the IC** (e.g. resolve a sharp initial profile): use `initial_marker` and `initial_steps` inside `[Adaptivity]`, separate from the steady/transient `marker` and `steps`/`cycles_per_step`.
4. **Mark elements but skip the actual mesh modification** (diagnostic — write the marker field to Exodus, no h-refinement applied): omit `marker = ...` at the top level. Markers in `[Adaptivity/Markers]` are still computed and become aux-style fields.

Restart / Checkpoint:

1. **Crash-resume an in-progress transient at the *exact* state** (all stateful data — material props, postprocessors, time integrator state, dt history): produce checkpoints with `[Outputs] checkpoint = true`, re-launch with `--recover`. Bit-for-bit continuation modulo nonlinear-solve nondeterminism.
2. **Start a *new* simulation from a previous run's final state** (different mesh refinement, dt, physics, BCs — reuse only the variable values): write checkpoints, set `[Problem] restart_file_base = previous_out_cp/LATEST` in the new input. Copies variables by name; does **not** carry stateful materials or postprocessors unless they're restartable.
3. **Seed only specific variables from a previous Exodus output** (no checkpoint files, no stateful data — just per-variable nodal/elemental values): `[Mesh] file = previous.e` + `use_for_exodus_restart = true`, then per variable `initial_from_file_var = u`. Cheaper but loses all stateful data.
4. **Multi-stage workflow** (solve steady, start transient from that solution): same as case 2 — checkpoint the steady run, set `restart_file_base` in the transient, reset `start_time = 0`.

Restart fidelity: `--recover` (full state) > checkpoint+`restart_file_base` (variables + recoverable data) > Exodus `initial_from_file_var` (variables only).

## Catalog

### `[Adaptivity/Markers]` — decide which elements to refine/coarsen

Every Marker writes one of `refine | coarsen | do_nothing | dont_mark` per element. The top-level `[Adaptivity]` `marker` parameter selects which one drives mesh modification; the others (if defined) are computed and output but ignored by the refiner.

#### Geometric markers

##### `BoxMarker`
- Source: `framework/include/markers/BoxMarker.h:16`
- Example: `test/tests/markers/box_marker/box_marker_test.i:22` (sub-block `[box]`); also `test/tests/adaptivity/initial_marker/initial_marker.i:68`
- Marks elements inside an axis-aligned box one way and outside another. Cheap; perfect for `initial_marker` to pre-refine a known feature region.
- Required: `bottom_left` (RealVectorValue), `top_right`, `inside` (`coarsen|do_nothing|refine|dont_mark`), `outside`.

##### `OrientedBoxMarker`
- Source: `framework/include/markers/OrientedBoxMarker.h:23`
- Example: `test/tests/markers/oriented_box_marker/obm.i:37` (sub-block `[obm]`)
- Like `BoxMarker` but rotated by an explicit local frame.
- Required: `center`, `length`, `width`, `height`, `length_direction`, `width_direction`, `inside`, `outside`.

##### `BoundaryMarker`
- Source: `framework/include/markers/BoundaryMarker.h:17`
- Example: `test/tests/markers/boundary_marker/adjacent.i:47` (sub-block `[boundary]`)
- Marks all elements that touch a sideset (or are within `distance` of it).
- Required: `next_to` (BoundaryName list), `mark` (`coarsen|do_nothing|refine|dont_mark`).
- Useful: `distance` (default 0 — only direct neighbors).

#### Error-driven markers

##### `ErrorFractionMarker`
- Source: `framework/include/markers/ErrorFractionMarker.h:14`
- Example: `test/tests/markers/error_fraction_marker/error_fraction_marker_test.i:66` (sub-block `[marker]`); `test/tests/adaptivity/cycles_per_step/cycles_per_step.i:59`
- Refines the top fraction of elements by indicator value, coarsens the bottom fraction. The standard go-to for transient AMR.
- Required: `indicator` (name of an entry in `[Adaptivity/Indicators]`).
- Useful: `refine` (top fraction, e.g. 0.7), `coarsen` (bottom fraction, e.g. 0.1), `clear_extremes` (drop outliers before computing fractions).

##### `ErrorToleranceMarker`
- Source: `framework/include/markers/ErrorToleranceMarker.h:14`
- Example: `test/tests/markers/error_tolerance_marker/error_tolerance_marker_test.i:66` (sub-block `[marker]`)
- Refines elements whose indicator exceeds an absolute threshold; coarsens below another. Use when you have a meaningful error scale; otherwise prefer `ErrorFractionMarker`.
- Required: `indicator`.
- Useful: `refine` (default 1e9 — set this!), `coarsen` (default 0).

##### `ValueRangeMarker`
- Source: `framework/include/markers/ValueRangeMarker.h:14`
- Example: `test/tests/markers/value_range_marker/value_range_marker_test.i:49` (sub-block `[marker]`)
- Refines elements whose nodal-value range straddles `[lower_bound, upper_bound]`. No indicator needed — operates directly on a variable.
- Required: `variable`, `lower_bound`, `upper_bound`.
- Useful: `buffer_size` (widen the band), `invert`, `third_state`.

##### `ValueThresholdMarker`
- Source: `framework/include/markers/ValueThresholdMarker.h:14`
- Example: `test/tests/markers/value_threshold_marker/value_threshold_marker_test.i:49` (sub-block `[marker]`)
- Refines based on whether the variable crosses a single threshold value.
- Required: `variable`.
- Useful: `refine` (threshold for refinement), `coarsen`, `invert`, `third_state`.

#### Custom / utility markers

##### `ComboMarker`
- Source: `framework/include/markers/ComboMarker.h:17`
- Example: `test/tests/markers/combo_marker/combo_marker_test.i:56` (sub-block `[combo]`); `test/tests/adaptivity/hp_adaptivity/hp-adaptivity-new-system.i:92`
- Composes other markers: refines if any input marker refines, coarsens only if all input markers coarsen. Use to combine a geometric region with an error-driven mark, or to track multiple variables.
- Required: `markers` (list of MarkerName).

##### `UniformMarker`
- Source: `framework/include/markers/UniformMarker.h:14`
- Example: `test/tests/markers/uniform_marker/uniform_marker.i:58` (sub-block `[uniform]`)
- Marks every element the same way every cycle. Useful for testing the adaptivity pipeline; for one-shot initial uniform refinement prefer `[Mesh] uniform_refine` instead.
- Required: `mark` (`coarsen|do_nothing|refine|dont_mark`).

### `[Adaptivity/Indicators]` — compute a per-element error estimate

Indicators produce a scalar field consumed by error-driven markers (`ErrorFractionMarker`, `ErrorToleranceMarker`). They run on every adaptivity cycle.

##### `GradientJumpIndicator`
- Source: `framework/include/indicators/GradientJumpIndicator.h:14`
- Example: `test/tests/indicators/gradient_jump_indicator/gradient_jump_indicator_test.i:65` (sub-block `[error]`); `test/tests/adaptivity/cycles_per_step/cycles_per_step.i:55`
- Integrates the squared jump of `grad u . n` across interior faces — the standard Kelly-style indicator. The default choice for a smooth scalar field where steep gradients drive refinement.
- Required: `variable`.
- Useful: `variable_is_FV` (set true when `variable` is FV).

##### `LaplacianJumpIndicator`
- Source: `framework/include/indicators/LaplacianJumpIndicator.h:14`
- Example: `test/tests/indicators/laplacian_jump_indicator/biharmonic.i:64` (sub-block `[error]`)
- Same idea but uses the second-derivative jump — appropriate for biharmonic / 4th-order PDEs where the gradient is continuous but the Laplacian isn't.
- Required: `variable`.

##### `ValueJumpIndicator`
- Source: `framework/include/indicators/ValueJumpIndicator.h:22` (typedef at line 18)
- Example: `test/tests/indicators/value_jump_indicator/value_jump_indicator_test.i:11` (sub-block `[error]`)
- Integrates the squared jump of the variable itself. Use for *discontinuous* variables (`MONOMIAL`, FV) where the gradient jump is degenerate or the value jump is the meaningful signal.
- Required: `variable`. (For FV, set `variable_is_FV = true`.)

##### `AnalyticalIndicator`
- Source: `framework/include/indicators/AnalyticalIndicator.h:14`
- Example: `test/tests/indicators/analytical_indicator/analytical_indicator_test.i:59` (sub-block `[error]`)
- Element L2 norm of `(u - f)` against an analytic `Function`. For verification / MMS-driven refinement studies; not for production runs (you don't have an analytic solution).
- Required: `variable`, `function`.

(Note: `ContourMarker` is not registered in stock framework. If you want to refine on a level-set contour, use `ValueThresholdMarker` on the level-set variable.)

### Restart / Checkpoint patterns

These are not catalog entries — they're combinations of input-block knobs and CLI flags. Each pattern lists the producing-side input, the consuming-side input, and any required CLI flag.

#### Producing checkpoints

The shorthand:

```hit
[Outputs]
  checkpoint = true
[]
```

This expands to a `Checkpoint` output with default `num_files = 2`. Files land in `<file_base>_cp/`.

The explicit form gives full control:

- Source: `framework/include/outputs/Checkpoint.h:63`
- Example: `test/tests/outputs/checkpoint/checkpoint_block.i:53` (sub-block `[out]`); with intervals: `test/tests/outputs/checkpoint/checkpoint_interval.i:52`
- Useful params: `num_files` (default 2 — number of rolling checkpoints to keep on disk), `time_step_interval` (write every N steps), `wall_time_interval` (seconds), `execute_on`.

```hit
[Outputs]
  exodus = true
  [cp]
    type = Checkpoint
    num_files = 4
    time_step_interval = 10
    wall_time_interval = 3600   # also dump every hour of walltime
  []
[]
```

#### Consuming checkpoints — exact recovery (`--recover`)

CLI only; no input changes needed:

```
moose-opt -i input.i --recover                    # most recent checkpoint
moose-opt -i input.i --recover input_out_cp/0010  # explicit base
```

Defined at `framework/src/base/MooseApp.C:269` (`--recover <optional file base>`). Restores **all** restartable data — material stateful properties, time integrator history, postprocessor accumulators, RNG state. The simulation continues as if it had never stopped.

Add `--force-restart` (`framework/src/base/MooseApp.C:275`) to bypass the compatibility-check refusals that protect you from loading a checkpoint produced by a different binary; only use this when you know the schemas match.

#### Consuming checkpoints — variable-by-variable seed (`restart_file_base`)

Input-side, in the *new* simulation:

- Example: `test/tests/restart/restart_transient_from_steady/restart_from_steady.i:9`

```hit
[Problem]
  restart_file_base = steady_out_cp/LATEST
[]

[Executioner]
  type = Transient
  start_time = 0.0   # explicitly reset; see Cross-cutting concerns
  ...
[]
```

`LATEST` is a magic string (`framework/src/utils/MooseUtils.C:162`) that resolves to the newest numbered checkpoint in the directory. Variable names are matched by string; new variables in the consuming input that aren't in the checkpoint pick up their `[ICs]` (and you must set `[Problem] allow_initial_conditions_with_restart = true` to suppress the error).

#### Consuming an Exodus output as initial condition

When you don't have a checkpoint (e.g. published reference solution) but you do have an Exodus result file, seed individual variables:

- Example: `test/tests/restart/restart_diffusion/restart_diffusion_from_end_part2.i:2,9-10`; FV: `test/tests/fvics/file_ic/file_restart.i:5,12`

```hit
[Mesh]
  file = previous.e
  use_for_exodus_restart = true
[]

[Variables]
  [u]
    initial_from_file_var = u                # name of the variable in previous.e
    initial_from_file_timestep = LATEST      # or an integer 1-based step index
  []
[]
```

`use_for_exodus_restart` is on `FileMeshGenerator` (`framework/src/meshgenerators/FileMeshGenerator.C:31`). The mesh comes from the Exodus file too — in/out meshes must match. This pattern only seeds variable values; nothing stateful crosses over.

#### Parallel checkpoints with Nemesis

Set `nemesis = true` in `[Outputs]` alongside `checkpoint = true` for parallel runs to keep per-rank IO files. Restart from the same parallel layout (`mpiexec -n N` must match between producer and consumer) or use `--n-threads` / serial mesh modes carefully.

#### Subapp restart

A MultiApp subapp checkpointed by its parent restarts together with the parent on `--recover`. To restart a subapp *standalone* from a parent run, point the subapp's input at the parent-produced checkpoint with `[Problem] restart_file_base = parent_out_<subapp_name>0_cp/LATEST` (subapp checkpoints are nested under the parent's `_cp` directory). See `test/tests/restart/restart_subapp_not_parent/two_step_solve_sub_restart.i` for the canonical pattern.

## Cross-cutting concerns

### `marker` vs `initial_marker`
`marker` drives refinement during steady `steps` or transient `cycles_per_step`. `initial_marker` drives `initial_steps` *once*, before the first solve, off the IC. Independent — mix them (e.g. `BoxMarker` for `initial_marker`, `ErrorFractionMarker` for `marker`). Both must reference entries under `[Adaptivity/Markers]`. Omitting `marker` leaves run-time markers as diagnostic-only (computed/output, not applied to mesh).

### `steps` vs `cycles_per_step` vs `interval`
Steady executioners use `steps` — number of solve→adapt→solve passes. Transient executioners ignore `steps` and use `cycles_per_step` (refinement passes per timestep) plus `interval` (run adaptivity only every `interval` timesteps). For most transient AMR: `cycles_per_step = 1`, `interval = 1`, and let `max_h_level` cap runaway refinement.

### `recompute_markers_during_cycles`
When `cycles_per_step > 1`, the indicator field is by default frozen across cycles. Set `recompute_markers_during_cycles = true` to re-run indicators after each refinement pass — costlier but converges to an equilibrated mesh in fewer outer steps.

### `max_h_level`
Caps how many times an element may be split. Default `0` means no cap, which is rarely what you want — pathological indicators can refine until memory dies. Always set this in production inputs.

### `start_time` / `stop_time`
Adaptivity is active only when `start_time <= t <= stop_time`. Use to disable refinement during ramp-up or after a feature has settled. Independent from `[Executioner]` time bounds.

### h vs p vs hp refinement
Top-level `adaptivity_type = h | p | hp` (default `h`) — `framework/src/actions/SetAdaptivityOptionsAction.C:46`. p- and hp-refinement need `family = HIERARCHIC` variables; standard `LAGRANGE` Q1 won't p-refine. Canonical: `test/tests/adaptivity/hp_adaptivity/hp-adaptivity-new-system.i:87`.

### Checkpoint frequency vs cost
Each checkpoint serializes the full backup (variables + mesh + restartable user data + stateful materials) — for big problems, this dominates I/O. Tune: `num_files` (keep low, 2-4 — old ones auto-prune), `time_step_interval` (every 10-100 for cheap solves, 1-2 for expensive), `wall_time_interval` (crash insurance for long runs).

### `--recover` (exact resume) vs `restart_file_base` (variable copy)
`--recover` is bit-identical continuation — same input, same mesh, same physics, same time-integrator state; only the start step mutates. `restart_file_base` is a *new* simulation seeding variables from a checkpoint — different mesh refinement, BCs, kernels, dt, time scheme all fine; postprocessor accumulators reset; stateful materials reset unless explicitly restartable; `start_time` resets to whatever the new input says.

### Exodus restart loses stateful data
`initial_from_file_var` only reads variable nodal/elemental values. Stateful materials (plasticity history, damage, internal state vars) are not in Exodus — they reinitialize from `[Materials]` defaults. Use the checkpoint route for stateful continuity.

### Subapp restart caveat
Standalone-restarting a subapp requires `[Problem] force_restart = true` if its executioner type or transfer set changed since the checkpoint was written. Parent-led `--recover` of a coupled MultiApp doesn't need this.

### `force_preaux` for restart-aware UserObjects
Some UserObjects (e.g. `PropertyReadFile`) populate state *before* AuxKernels on a restarted step via `force_preaux = true` (`framework/src/userobjects/PropertyReadFile.C:76`). Author your own restart-driven UO that AuxKernels read? You may need the same.

## Minimal scaffold

A transient diffusion run with gradient-jump indicator + error-fraction marker + a geometric pre-refinement, plus checkpointing for crash recovery:

```hit
[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 2
    nx = 20
    ny = 20
  []
[]

[Variables]
  [u]
  []
[]

[Kernels]
  [time]
    type = ADTimeDerivative
    variable = u
  []
  [diff]
    type = ADDiffusion
    variable = u
  []
[]

[BCs]
  [left]
    type = ADDirichletBC
    variable = u
    boundary = left
    value = 0
  []
  [right]
    type = ADDirichletBC
    variable = u
    boundary = right
    value = 1
  []
[]

[Adaptivity]
  marker = err_frac
  initial_marker = init_box
  initial_steps = 2
  cycles_per_step = 1
  interval = 2
  max_h_level = 3
  [Indicators]
    [grad_jump]
      type = GradientJumpIndicator
      variable = u
    []
  []
  [Markers]
    [init_box]
      type = BoxMarker
      bottom_left = '0.4 0.4 0'
      top_right = '0.6 0.6 0'
      inside = refine
      outside = dont_mark
    []
    [err_frac]
      type = ErrorFractionMarker
      indicator = grad_jump
      refine = 0.7
      coarsen = 0.1
    []
  []
[]

[Executioner]
  type = Transient
  num_steps = 50
  dt = 0.01
  solve_type = NEWTON
[]

[Outputs]
  exodus = true
  [cp]
    type = Checkpoint
    num_files = 2
    time_step_interval = 10
    wall_time_interval = 3600
  []
[]
```

To resume after a crash: `moose-opt -i input.i --recover`. To start a new simulation seeded from this run's final state, in the new input add:

```hit
[Problem]
  restart_file_base = input_out_cp/LATEST
[]
```

and reset `[Executioner] start_time = 0.0`.
