# Authoring inputs: Outputs and Debug

Reach for this guide when you need to declare what files MOOSE writes (visualization, tabular, restart) or turn on diagnostic prints during development. The `[Outputs]` block selects from the catalog of registered `Output` classes; `[Debug]` is a thin shorthand that *adds* hidden Outputs (material-prop dump, residual norms) without you having to type them. If you need a derived field to *put into* an output, see [postprocess.md](./postprocess.md) (`[Postprocessors]`/`[VectorPostprocessors]`/`[Reporters]`) or [auxkernels via kernels.md](./kernels.md). If you're tuning *when* the solve runs (not when output happens), see [executioner.md](./executioner.md).

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. Each catalog entry cites the **source header** (`<file>:<line of class>`) and one **canonical example .i** (`<file>:<line of the sub-block>`).

## When to use this (vs alternatives)

Decide on **shorthand vs explicit sub-block** first, then pick the entry from the catalog.

1. You only need defaults: use the **top-level shorthand** — `[Outputs] exodus = true` (or `csv = true`, `console = true`, `nemesis = true`, `vtk = true`, `xda = true`, `xdr = true`, `tecplot = true`, `json = true`, `dofmap = true`, `checkpoint = true`). One line, default file base, default `execute_on`. Multiple shorthands stack — `exodus = true` and `csv = true` together produce both.
2. You need to override anything (`hide`, `sync_times`, `interval`, `refinements`, `execute_on`, etc.): use an **explicit sub-block** — `[Outputs/exo] type = Exodus ... []`. The block name (`exo`) is the file-base suffix and the handle that `outputs = exo` filters reference from `[Postprocessors]`.
3. You want both the default **plus** an extra customized writer: combine them — `exodus = true` next to `[Outputs/exo_hidden] type = Exodus hide = 'pid' []` writes two `.e` files with different file-base suffixes.
4. You want diagnostics that don't fit a normal Output (residual norms, material props on every block, action-graph dump, top-residual table): use the **`[Debug]` block** — every flag there auto-adds a hidden Output. Don't write `[Outputs/x] type = MaterialPropertyDebugOutput` directly; it works but is brittle and bypasses the per-system wiring `[Debug]` does for you.
5. You need recovery from a crash or branched runs: add a **`Checkpoint`** — either `checkpoint = true` (system-managed, walltime-driven) or an explicit sub-block with `time_step_interval` / `num_files`.

The shorthand `exodus = true` is exactly equivalent to a sub-block `[Outputs/exodus] type = Exodus []` — same defaults, same file base, same execute_on.

## Catalog

### `[Outputs]` — visualization (mesh + field data)

##### `Exodus`
- Source: `framework/include/outputs/Exodus.h:24`
- Example: `test/tests/outputs/exodus/exodus.i:54` (sub-block `[out]`); shorthand: `test/tests/outputs/checkpoint/checkpoint.i:52` (`exodus = true`)
- ExodusII (`.e`) — the default visualization format; opens in Paraview/VisIt; supports nodal + elemental + global + material output, sidesets, time history.
- Required: `type = Exodus` (sub-block only).
- Useful: `file_base`, `execute_on` (default `INITIAL TIMESTEP_END`), `interval` / `time_step_interval`, `start_time`, `end_time`, `sync_times`, `sync_only`, `hide`, `show`, `output_material_properties`, `show_material_properties`, `elemental_as_nodal`, `discontinuous`, `output_dimension`, `refinements` (oversampling), `position`, `additional_execute_on`, `overwrite` (overwrite single file each step).

##### `Nemesis`
- Source: `framework/include/outputs/Nemesis.h:24`
- Example: `test/tests/outputs/nemesis/nemesis.i:44` (`nemesis = true`); explicit hide variant: `test/tests/outputs/variables/nemesis_hide.i:109`
- Per-rank ExodusII pieces (`.e.<nproc>.<rank>`) — preferred over `Exodus` on large parallel runs; recombined by `epu`. Does *not* inherit the oversampling/`refinements` machinery.
- Required: `type = Nemesis`.
- Useful: same `execute_on` / `interval` / `hide` / `show` / `sync_times` family as `Exodus`.

##### `XDA` / `XDR`
- Source: `framework/include/outputs/XDA.h:18` (registered as both `XDA` and `XDR`)
- Example: `test/tests/outputs/xda/xda.i:43` (`xda = true`); binary variant: `test/tests/outputs/xda/xdr.i`
- libMesh-native ASCII (`XDA`) / binary (`XDR`) solution dumps. Niche — used mostly for round-tripping into another libMesh tool. Prefer `Exodus` for visualization.
- Required: `type = XDA` (or `XDR`).

##### `VTK`
- Source: `framework/include/outputs/VTKOutput.h:18` (alias `VTK`)
- Example: `test/tests/outputs/vtk/vtk_serial.i:57` (`vtk = true`); explicit: `test/tests/outputs/iterative/iterative_vtk.i:53`
- VTK `.pvtu`/`.vtu` series. Requires libMesh built with VTK support (skipped otherwise).
- Required: `type = VTK`.
- Useful: `execute_on`, `refinements`, `hide`, `show`.

##### `Tecplot`
- Source: `framework/include/outputs/Tecplot.h:18`
- Example: `test/tests/outputs/tecplot/tecplot.i:43` (`tecplot = true`); explicit binary: `test/tests/outputs/tecplot/tecplot_binary.i:44`
- Tecplot `.dat` (ASCII) or `.plt` (binary). Requires libMesh built with Tecplot support.
- Required: `type = Tecplot`.
- Useful: `binary` (default false), `ascii_append`.

##### `OversampledExodus` (pattern, not a class)
- Source: `framework/include/outputs/SampledOutput.h:39` — the base class that gives `Exodus`, `XDA`, `VTK`, `Tecplot` their oversampling support.
- Example: `test/tests/outputs/sampled_output/oversample.i:43` (sub-block `[out]`)
- "OversampledExodus" is just `type = Exodus` plus `refinements = N` and/or `position = '...'` and/or `file = ...`. There is no class literally named `OversampledExodus`; reach for the parameter trio on any `Sampled`-derived output.
- Useful: `refinements` (extra uniform refinements for output mesh), `position` (offset displacement), `file` (sample onto a separate mesh), `sampling_blocks`.

### `[Outputs]` — tabular (postprocessors, vector postprocessors, reporters)

##### `CSV`
- Source: `framework/include/outputs/CSV.h:20`
- Example: `test/tests/outputs/csv/csv.i:89` (sub-block `[csv]`); shorthand: `test/tests/outputs/reporters/reporter.i:52` (`csv = true`)
- One `.csv` for all scalar Postprocessors + scalar variables; one `<base>_<vpp>_<step>.csv` per VectorPostprocessor.
- Required: `type = CSV`.
- Useful: `file_base`, `align`, `delimiter` (default `,`), `precision`, `sort_columns`, `create_final_symlink`, `create_latest_symlink`, `time_data` (write `time` column), `execute_on`, `time_column`, `hide`, `show`.

##### `JSON` (alias for `JSONOutput`)
- Source: `framework/include/outputs/JSONOutput.h:15`
- Example: `test/tests/outputs/json/basic/json.i:22` (`json = true`); reporter-aware: `test/tests/outputs/hide_via_reporters_block/reporter.i:31`; postprocessors-as-reporters: `test/tests/outputs/pp_as_reporter/pp_as_reporter.i:21`
- Single `.json` carrying every `[Reporter]` value (and optionally Postprocessors and VectorPostprocessors as reporters). The standard way to round-trip MOOSE results into Python.
- Required: `type = JSON`.
- Useful: `postprocessors_as_reporters` (default false), `vectorpostprocessors_as_reporters`, `one_file_per_timestep`, `distributed`, `execute_on`, `execute_system_information_on`, `hide`, `show`.

##### Reporter-aware outputs
- Both `JSON` (above) and `CSV` walk the `[Reporters]` system. To emit only specific reporters, use `show = 'reporter_name'` / `hide = ...` from the output sub-block, or set `outputs = my_json_block` *inside* the `[Reporters]` entry.
- Reporter entry → output filter example: `test/tests/outputs/hide_via_reporters_block/reporter.i:31`.

##### `JSONIO` (helper, not an Output)
- Source: `framework/include/outputs/JsonIO.h` (this header defines the `nlohmann::json` helpers used by `to_json`/`from_json` overloads inside MOOSE — it's a serialization utility, *not* an output type you put in `[Outputs]`).
- If you actually want a JSON file in `[Outputs]`, use **`type = JSON`** (the alias for `JSONOutput`).

### `[Outputs]` — console / debug writers (not the `[Debug]` shorthand)

##### `Console`
- Source: `framework/include/outputs/Console.h:18`
- Example: `test/tests/outputs/console/console.i:101` (sub-block `[screen]`); shorthand: implicit — every run gets a default `Console` even with no `[Outputs]` block.
- Screen output: residual history, postprocessor table, performance log, system info. There's *always* one default `Console` unless you set `[Outputs] console = false`.
- Required: `type = Console`.
- Useful: `output_screen` (default true), `output_file` (write a `.txt` mirror), `fit_mode`, `verbose`, `perf_log` (deprecated — use `[Outputs/perf_graph]`), `print_linear_residuals`, `print_nonlinear_residuals`, `system_info`, `start_step`, `additional_execute_on`, `solve_log`, `setup_log`, `time_precision`, `time_format`.

##### `DOFMap` (alias for `DOFMapOutput`)
- Source: `framework/include/outputs/DOFMapOutput.h:20`
- Example: `test/tests/outputs/dofmap/simple.i:58` (`dofmap = true`); explicit screen-only: `test/tests/outputs/dofmap/simple_screen.i:59`
- Dumps the global DOF → element/node map (one `.txt` per run by default) — diagnosing partitioning, multi-system coupling, AuxSystem ordering.
- Required: `type = DOFMap`.
- Useful: `output_screen` (default false), `output_file` (default true), `execute_on`.

##### `MaterialPropertyDebugOutput`
- Source: `framework/include/outputs/MaterialPropertyDebugOutput.h:23`
- Example: `test/tests/outputs/debug/show_material_props.i:78` (sub-block `[debug]`)
- Lists every declared material property by block / boundary / sideset on initial setup. **Prefer the shorthand**: `[Debug] show_material_props = true` (next section).
- Required: `type = MaterialPropertyDebugOutput`.

##### `VariableResidualNormsDebugOutput`
- Source: `framework/include/outputs/VariableResidualNormsDebugOutput.h:24`
- Example: `test/tests/outputs/debug/show_var_residual_norms.i:206` (sub-block `[debug]`)
- Per-variable L2 residual norm at every nonlinear iteration — first stop when Newton stalls. **Prefer**: `[Debug] show_var_residual_norms = true`.
- Required: `type = VariableResidualNormsDebugOutput`.

##### `TopResidualDebugOutput`
- Source: `framework/include/outputs/TopResidualDebugOutput.h:72`
- Example: `test/tests/outputs/debug/show_top_residuals.i:47` (sub-block `[debug]`)
- Tabulates the top-N largest entries of the residual vector with their (var, node, point) — finds the bad DOF when Newton diverges. **Prefer**: `[Debug] show_top_residuals = N`.
- Required: `type = TopResidualDebugOutput`, `num_residuals`.

##### `PerfGraphOutput`
- Source: `framework/include/outputs/PerfGraphOutput.h:18`
- Example: `test/tests/outputs/perf_graph/perf_graph.i:51` (sub-block `[pgraph]`)
- Prints the timing/perf-graph tree. Shorthand `[Outputs] perf_graph = true` exists.
- Required: `type = PerfGraphOutput`.
- Useful: `level` (detail depth, default 1), `heaviest_branch`, `heaviest_sections`, `execute_on` (default `FINAL`).

### `[Outputs]` — restart

##### `Checkpoint`
- Source: `framework/include/outputs/Checkpoint.h:63`
- Example: `test/tests/outputs/checkpoint/checkpoint_interval.i:53` (sub-block `[out]`); shorthand: `test/tests/outputs/checkpoint/checkpoint_block.i:54`
- Writes a complete `<file_base>_cp/<step>` snapshot (mesh + solution + restartable data) usable by `--recover` or `Problem/restart_file_base = ...`.
- Required: `type = Checkpoint`.
- Useful: `num_files` (rolling window, default 2), `time_step_interval` (default 1), `wall_time_interval` (seconds), `execute_on`, `file_base`. The two-file rolling default is intentional — keeps two valid recovery points without unbounded disk use.
- Shorthand `checkpoint = true` enables a *system-managed* checkpoint that triggers on signals + walltime; the explicit form is better when you want fixed-cadence checkpoints in version control.

### Top-level shorthand summary

Inside `[Outputs]` (no sub-block), these scalar params each spawn a default-configured Output of the matching type:

| Shorthand | Equivalent sub-block |
| --- | --- |
| `exodus = true` | `type = Exodus` |
| `nemesis = true` | `type = Nemesis` |
| `vtk = true` | `type = VTK` |
| `xda = true` / `xdr = true` | `type = XDA` / `type = XDR` |
| `tecplot = true` | `type = Tecplot` |
| `csv = true` | `type = CSV` |
| `json = true` | `type = JSON` |
| `console = true` (default) / `console = false` | `type = Console` |
| `dofmap = true` | `type = DOFMap` |
| `checkpoint = true` | system-managed `Checkpoint` |
| `perf_graph = true` | `type = PerfGraphOutput` |

Mixing is allowed: `exodus = true` + `csv = true` + a `[Outputs/cp] type = Checkpoint []` sub-block gives three distinct outputs.

### `[Debug]` — diagnostic shorthand (top-level params, not sub-blocks)

The `[Debug]` block has **no sub-blocks** — every param toggles a built-in diagnostic. Source: `framework/src/actions/SetupDebugAction.C:26`. Example: `test/tests/outputs/exodus/exodus.i:59` (the canonical `[Debug] show_var_residual_norms = true` placement).

Useful params:
- `show_var_residual_norms = true` — adds a `VariableResidualNormsDebugOutput` per nonlinear system.
- `show_top_residuals = <N>` — adds a `TopResidualDebugOutput` (N>0 enables; default 0).
- `show_material_props = true` — adds a `MaterialPropertyDebugOutput`.
- `show_actions = true` — print the action-graph executed by the parser; pairs well with `show_action_dependencies`.
- `show_execution_order = '<exec_flags>'` — print which objects fire on which exec flags (e.g. `'INITIAL NONLINEAR TIMESTEP_END'`).
- `show_reporters = true` — declared/requested Reporter dump.
- `show_functors = true` — registered functors and their consumers.
- `show_block_restriction = '<scope>'` — list active objects per subdomain (`scope` is a `MultiMooseEnum`; see `BlockRestrictionDebugOutput`).
- `show_mesh_meta_data = true` — print mesh meta-data names.
- `show_mesh_generators = true` — verbose `[Mesh]` generator pipeline.
- `show_controllable = true` — list every controllable parameter.
- `output_process_domains = true` — adds a `pid` AuxVariable showing rank ownership (visualize partitioning in Exodus).
- `error_on_residual_nan = true` — error out (in `dbg`/`devel` builds) on first NaN/Inf residual contribution.

Use `[Debug]` in preference to writing the equivalent `[Outputs]` sub-block — it wires per-system Outputs and leaves your `[Outputs]` block focused on user-facing files.

## Cross-cutting concerns

### `hide` / `show` filters
- `hide = '<list>'` and `show = '<list>'` on an Output sub-block (or top-level inside `[Outputs]`) drop / restrict variables, postprocessors, vector postprocessors, and reporters by name. Names are looked up across all four categories — the same string filters everywhere. Example: `test/tests/outputs/exodus/hide_variables.i:91` (`hide = 'aux2 v num_aux'`).
- `show` is exclusive: listing `show = 'u'` outputs *only* `u`. The two are mutually exclusive in practice; pick one.

### Per-Postprocessor / Per-Reporter `outputs = ...`
- From inside a `[Postprocessors/foo]` (or `[VectorPostprocessors/foo]`, `[Reporters/foo]`) entry, set `outputs = exo` (or `outputs = 'exo csv'`, or `outputs = none`) to route that single object to specific output sub-blocks. The names must match the *sub-block names* in `[Outputs]`. Example: `test/tests/outputs/output_interface/indicator.i:47` and `test/tests/outputs/output_interface/marker.i:47`.
- This is the inverse of `hide`/`show` and is the cleanest way to keep Indicators/Markers out of the headline `Exodus` while still streaming them to a debug `.e`.

### `execute_on` vs `output_on`
- `execute_on` on an Output is a list of `ExecFlagEnum` values (`INITIAL`, `LINEAR`, `NONLINEAR`, `TIMESTEP_BEGIN`, `TIMESTEP_END`, `FINAL`, `FAILED`, `CUSTOM`, `NONE`, `ALWAYS`). The Output writes a frame whenever one of those flags fires — *not* on every residual evaluation. Setting `execute_on = 'NONLINEAR'` means "every nonlinear iteration", which is rare (debug only); `TIMESTEP_END` is the standard.
- The legacy alias `output_on` is honored on a few output types but is deprecated; prefer `execute_on`.
- `additional_execute_on = '<flags>'` *adds* flags to the per-class default without replacing it. Example use: `test/tests/outputs/console/additional_execute_on.i:53` (Console keeps its defaults plus `INITIAL`). Reach for this when you want "the default plus initial".

### Time / step filtering
- `interval` / `time_step_interval` (default 1) — write every Nth call; pairs with `execute_on = TIMESTEP_END`. `time_step_interval` is the modern name; `interval` still works.
- `start_time` / `end_time` — clamp the time window during which the output writes anything.
- `sync_times = '<list>'` — exact simulation times the executioner must hit, with an output frame emitted at each. Example: `test/tests/outputs/intervals/sync_times.i:54`.
- `sync_only = true` — combined with `sync_times`, writes *only* at those times, suppressing the regular `execute_on` cadence.
- `minimum_time_interval` — debounce: skip outputs that would land within this Δt of the previous one.

### `file_base` and CLI override
- Default `file_base` is `<input_basename>_<output_block_name>` (e.g. input `foo.i` with `[Outputs/exo] type = Exodus []` → `foo_exo.e`). The shorthand `exodus = true` produces just `foo.e` (no suffix).
- Override per-output: `[Outputs/exo] file_base = my_run`.
- Override globally on the command line: `--file-base my_run` — beats every per-output `file_base` set in the input. Useful for parametric sweeps.

### `Checkpoint` numbers and recovery
- `num_files = 2` (default) keeps a rolling window: at most two intact checkpoints on disk at any time. `num_files = 0` keeps every checkpoint.
- Recovery: `moose-opt -i foo.i --recover` picks the latest valid checkpoint. To restart a *new* simulation from a checkpoint, set `[Problem] restart_file_base = foo_cp/LATEST` (no `--recover` flag; this is a fresh run with seeded state).
- `wall_time_interval = <seconds>` makes the system-managed checkpoint write at walltime cadence regardless of step count — protective against long-step crashes.

### Material-property output
- `output_material_properties = true` on `[Outputs/exo]` exports every declared material property MOOSE knows how to render (scalars, RealVectorValue, RankTwoTensor). Per-property control via `show_material_properties = '<names>'`. The `[Materials]` entry that declares the property must call `outputs(...)` (set `outputs = exo` from the *Materials* sub-block) for fine-grained routing — see [materials.md](./materials.md).

### Multiple outputs of the same type
- Two `Exodus` blocks are fine; give them distinct sub-block names so `file_base` differs:

  ```hit
  [Outputs]
    [exo_full]
      type = Exodus
    []
    [exo_lite]
      type = Exodus
      hide = 'pid aux_debug'
      file_base = lite
    []
  []
  ```

## Minimal scaffold

Shorthand-only — the 90% case. Two formats, default everything:

```hit
[Outputs]
  exodus = true
  csv = true
[]

[Debug]
  show_var_residual_norms = true
[]
```

Explicit sub-blocks with filtering and a checkpoint:

```hit
[Outputs]
  file_base = run01
  [exo]
    type = Exodus
    execute_on = 'INITIAL TIMESTEP_END'
    hide = 'pid aux_debug'
    sync_times = '0.1 0.5 1.0'
  []
  [csv]
    type = CSV
    execute_on = 'TIMESTEP_END FINAL'
    create_final_symlink = true
  []
  [cp]
    type = Checkpoint
    time_step_interval = 10
    num_files = 4
  []
[]

[Postprocessors]
  [u_avg]
    type = ElementAverageValue
    variable = u
    outputs = csv          # only goes to [csv], stays out of [exo]
  []
[]

[Debug]
  show_material_props = true
  show_top_residuals = 5
[]
```
