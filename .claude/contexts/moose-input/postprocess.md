# Authoring inputs: Postprocessors, VectorPostprocessors, Reporters, UserObjects

Reach for this guide when you need a derived scalar / vector / generic quantity in a `.i` file — for output, for feeding into another object, or for caching a computation other kernels/materials/BCs read. These four blocks form a hierarchy: `[Postprocessors]` (one `Real` per object) → `[VectorPostprocessors]` (named `std::vector<Real>` columns) → `[Reporters]` (arbitrary typed values + vectors) → `[UserObjects]` (general engine; emits values *consumed by* other objects, not output directly). If you want the value to enter the residual see [kernels.md](./kernels.md). If you want a derived field on every node/element see AuxKernels in [kernels.md](./kernels.md).

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. Each catalog entry cites the **source header** (`<file>:<line of class>`) and one **canonical example .i** (`<file>:<line of the sub-block>`).

## When to use this (vs alternatives)

Decide on the top-level block first, then pick the entry from the catalog.

1. Single scalar per execution (integral, max, point sample, CFL): **`[Postprocessors]`**. Output to `csv` / Exodus global / screen automatically. Consumed by `postprocessor =` params on `BodyForce`, `Receiver`, `ParsedFunction`, `ParsedPostprocessor`, etc.
2. Named columns of `Real` (line sample, histogram, sideset table, fit history): **`[VectorPostprocessors]`**. Each VPP declares one or more named vectors → separate CSV columns/files.
3. Heterogeneous typed data (mixed scalars, vectors, strings, dof-id-types; framework diagnostics): **`[Reporters]`**. Most general value producer; what you read back via `ReporterPointSource`, `ParsedScalarReporter`.
4. Spatial / aggregation engine queried by other objects (layered averages, nearest-point lookups, external-solution interpolation): **`[UserObjects]`**. Not output directly — pair with `SpatialUserObjectAux` / `SpatialUserObjectVectorPostprocessor`, or a kernel/material that calls `getUserObject<T>(...)`.

Output-only vs feedback-into-residual: none of these blocks contribute to residuals. To push a value back into the solve, name the PP in a kernel param (`BodyForce`'s `postprocessor`, `ParsedFunction`'s `symbol_values`), or use `ReporterPointSource` to inject point sources from a Reporter/VPP. For a UO, write a kernel/material that calls `getUserObject<T>(...)`.

## Catalog

### `[Postprocessors]`

#### Variable / field reductions

##### `ElementIntegralVariablePostprocessor`
- Source: `framework/include/postprocessors/ElementIntegralVariablePostprocessor.h:21`
- Example: `test/tests/postprocessors/element_integral_var_pps/initial_pps.i:113` (sub-block `[initial_u]`)
- Volume integral `int_Omega u dV` of a field variable.
- Required: `variable`. Useful: `block`.

##### `ElementAverageValue`
- Source: `framework/include/postprocessors/ElementAverageValue.h:20`
- Example: `test/tests/postprocessors/element_average_value/element_average_value_test.i:58` (sub-block `[average]`)
- Volume-averaged value `int u dV / int dV`.
- Required: `variable`. Useful: `block`.

##### `ElementL2Norm`
- Source: `framework/include/postprocessors/ElementL2Norm.h:14`
- Example: `test/tests/postprocessors/element_l2_norm/element_l2_norm.i:37` (sub-block `[L2_norm]`)
- `sqrt(int u^2 dV)` — norm of the variable, not error vs analytic.
- Required: `variable`.

##### `ElementH1SemiError`
- Source: `framework/include/postprocessors/ElementH1SemiError.h:21`
- Example: `test/tests/postprocessors/element_h1_error_pps/element_h1_error_pp_test.i:100` (sub-block `[h1_semi]`)
- `sqrt(int |grad u - grad f|^2 dV)` — H1 seminorm of the error vs a `Function`.
- Required: `variable`, `function`.

##### `NodalSum`
- Source: `framework/include/postprocessors/NodalSum.h:17`
- Example: `test/tests/postprocessors/nodal_sum/nodal_sum.i:46` (sub-block `[nodal_sum]`)
- Sum of nodal DoFs of a continuous variable (use sparingly — depends on mesh density).
- Required: `variable`. Useful: `boundary`, `block`, `unique_node_execute`.

##### `NodalMaxValue`
- Source: `framework/include/postprocessors/NodalMaxValue.h:18`
- Example: `framework/contrib/hit/test/input.i:141`
- Maximum over all nodal values; for richer min/max prefer `NodalExtremeValue`.
- Required: `variable`. Useful: `boundary`, `block`.

##### `SideAverageValue`
- Source: `framework/include/postprocessors/SideAverageValue.h:20`
- Example: `test/tests/postprocessors/side_average_value/side_average_value_test.i:56` (sub-block `[average]`)
- `int_S u dA / int_S dA` over a sideset.
- Required: `variable`, `boundary`.

##### `SideIntegralVariablePostprocessor`
- Source: `framework/include/postprocessors/SideIntegralVariablePostprocessor.h:22`
- Example: `test/tests/postprocessors/side_integral/side_integral_test.i:56` (sub-block `[integral]`)
- `int_S u dA` over a sideset.
- Required: `variable`, `boundary`.

##### `PointValue`
- Source: `framework/include/postprocessors/PointValue.h:20`
- Example: `test/tests/postprocessors/point_value/point_value.i:45` (sub-block `[value]`)
- Value of a variable at a single point in space.
- Required: `variable`, `point`.

##### `AverageNodalVariableValue`
- Source: `framework/include/postprocessors/AverageNodalVariableValue.h:14`
- Example: `test/tests/postprocessors/avg_nodal_var_value/avg_nodal_var_value.i:103` (sub-block `[node1]`)
- Average over nodes (typically a `boundary` containing one node — the "value at node X" idiom).
- Required: `variable`. Useful: `boundary`, `block`.

#### Material reductions

##### `ElementIntegralMaterialProperty`
- Source: `framework/include/postprocessors/ElementIntegralMaterialProperty.h:20`
- Example: `test/tests/postprocessors/element_integral_material_property/element_integral_material_property.i:48` (sub-block `[prop_integral]`)
- Volume integral of a `Real` material property. AD twin: `ADElementIntegralMaterialProperty`.
- Required: `mat_prop`. Useful: `block`.

##### `SideIntegralMaterialProperty`
- Source: `framework/include/postprocessors/SideIntegralMaterialProperty.h:21`
- Example: `test/tests/postprocessors/side_integral/side_integral_material_property.i:3` (sub-block `[integral]`)
- Sideset integral of a `Real` material property.
- Required: `property`, `boundary`.

#### Norms / errors (vs analytic)

##### `ElementL2Error`
- Source: `framework/include/postprocessors/ElementL2Error.h:16`
- Example: `test/tests/postprocessors/element_h1_error_pps/element_h1_error_pp_test.i:107` (sub-block `[l2_error]`); MMS sweep: `test/tests/postprocessors/mms_slope/mms_slope_test.i:105`
- `sqrt(int (u - f)^2 dV)` — L2 norm of the error vs a `Function`. The MMS-convergence workhorse.
- Required: `variable`, `function`.

##### `NodalL2Error`
- Source: `framework/include/postprocessors/NodalL2Error.h:17`
- Example: search `test/tests/postprocessors` for `type = NodalL2Error`.
- Discrete L2 of `(u - f)` evaluated at nodes — cheaper than the integrated form on Lagrange variables.
- Required: `variable`, `function`.

##### `ElementH1Error`
- Source: `framework/include/postprocessors/ElementH1Error.h:21`
- Example: `test/tests/postprocessors/element_h1_error_pps/element_h1_error_pp_test.i:93` (sub-block `[h1_error]`)
- Full H1 norm `(|u-f|^2 + |grad u - grad f|^2)^{1/2}`. Subclass of `ElementW1pError` (the Wp,p variant exists too).
- Required: `variable`, `function`.

##### `ElementVectorL2Error`
- Source: `framework/include/postprocessors/ElementVectorL2Error.h:21`
- Example: `test/tests/postprocessors/element_vec_l2_error_pps/element_vec_l2_error.i:127` (sub-block `[integral]`)
- L2 error for a vector-of-scalars solution `(u_x, u_y, u_z)` against `(f_x, f_y, f_z)`.
- Required: `var_x`, `function_x` (+ `var_y`/`function_y`, `var_z`/`function_z` in higher D).

#### Time / dt

##### `TimePostprocessor`
- Source: `framework/include/postprocessors/TimePostprocessor.h:17`
- Example: `test/tests/materials/derivative_material_interface/postprocessors.i:25` (sub-block `[time]`)
- Reports current simulation time `t` as a PP (so a `ParsedFunction` / `Receiver` / `BodyForce` can pull it through `pp_names`).
- Required: none.
- Useful: `execute_on` — set to `TIMESTEP_BEGIN` (or `LINEAR/NONLINEAR`) if any consumer reads it inside the residual.

##### `ChangeOverTimePostprocessor`
- Source: `framework/include/postprocessors/ChangeOverTimePostprocessor.h:18`
- Example: `test/tests/postprocessors/change_over_time/change_over_time.i:66` (sub-block `[change_over_time]`)
- `pp(t) - pp(t_prev)` (or vs initial). Steady-state indicator.
- Required: `postprocessor`. Useful: `change_with_respect_to_initial`, `compute_relative_change`.

##### `TimeExtremeValue`
- Source: `framework/include/postprocessors/TimeExtremeValue.h:16`
- Example: `test/tests/postprocessors/time_extreme_value/time_extreme_value.i:52` (sub-block `[max_nl_dofs]`)
- Running min/max/abs-max of another PP across all timesteps so far.
- Required: `postprocessor`.
- Useful: `value_type` (`max|min|abs_max|abs_min`), `output_type` (`extreme_value|time` — return the *time* the extremum occurred at).

#### Composite / parsed

##### `ParsedPostprocessor`
- Source: `framework/include/postprocessors/ParsedPostprocessor.h:18`
- Example: `test/tests/postprocessors/parsed_postprocessor/parsed_pp.i:50` (sub-block `[parsed]`)
- FParser expression of other PP names — ratios, sums, polynomials.
- Required: `expression`, `pp_names`. Useful: `constant_names`, `constant_expressions`, `use_t`.

##### `FunctionValuePostprocessor`
- Source: `framework/include/postprocessors/FunctionValuePostprocessor.h:21`
- Example: `test/tests/postprocessors/function_value_pps/function_value_pps.i:71` (sub-block)
- Evaluates a `Function` at `(t, point)` and stores it as a PP.
- Required: `function`. Useful: `point` (default `(0,0,0)`), `time` (default current).

##### `ScalarVariable`
- Source: `framework/include/postprocessors/ScalarVariable.h:17`
- Example: `test/tests/postprocessors/scalar_variable/scalar_variable_pps.i:73` (sub-block `[reporter]`)
- Lifts a `[Variables]` SCALAR variable into a PP so it shows up in CSV/`pp_names` consumers.
- Required: `variable` (SCALAR), `component` if vector scalar.

##### `Receiver`
- Source: `framework/include/postprocessors/Receiver.h:18`
- Example: `test/tests/postprocessors/receiver_default/defaults.i:37` (sub-block `[receiver]`)
- Stores a value set externally (by a Transfer, a Control, or `default`). The canonical way for a parent app to push a number into a sub-app.
- Required: none.
- Useful: `default` (initial value), `initialize_old_value`.

##### `LinearCombinationPostprocessor`
- Source: `framework/include/postprocessors/LinearCombinationPostprocessor.h:24`
- Example: `test/tests/postprocessors/postprocessor_comparison/postprocessor_comparison.i:14` (sub-block `[pp_to_compare]`)
- `sum_i c_i * pp_i + b` — affine combination of PPs.
- Required: `pp_names`, `pp_coefs`.
- Useful: `b` (constant offset, default 0).

### `[VectorPostprocessors]`

#### Sampling along geometry

##### `LineValueSampler`
- Source: `framework/include/vectorpostprocessors/LineValueSampler.h:16`
- Example: `test/tests/vectorpostprocessors/line_value_sampler/line_value_sampler.i:73` (sub-block `[line_sample]`)
- Samples one or more variables along a line at `num_points` evenly spaced points; emits an `id`/`x`/`y`/`z` set plus one column per variable.
- Required: `variable`, `start_point`, `end_point`, `num_points`.
- Useful: `sort_by` (`x|y|z|id`), `warn_discontinuous_face_values`.

##### `PointValueSampler`
- Source: `framework/include/vectorpostprocessors/PointValueSampler.h:15`
- Example: `test/tests/vectorpostprocessors/point_value_sampler/point_value_sampler.i:55` (sub-block `[point_sample]`)
- Samples variables at an explicit list of points (irregular).
- Required: `variable`, `points`.
- Useful: `sort_by`.

##### `ElementsAlongLine`
- Source: `framework/include/vectorpostprocessors/ElementsAlongLine.h:17`
- Example: `test/tests/vectorpostprocessors/elements_along_line/1d.i:37` (sub-block `[elems]`)
- Returns IDs of the elements crossed by a line segment — useful for mesh-aware probing.
- Required: `start`, `end`.

##### `NodalValueSampler`
- Source: `framework/include/vectorpostprocessors/NodalValueSampler.h:18`
- Example: `test/tests/vectorpostprocessors/nodal_value_sampler/nodal_value_sampler.i:55` (sub-block `[nodal_sample]`)
- Variable values at every node in a `block` and/or on a `boundary`.
- Required: `variable`.
- Useful: `boundary`, `block`, `sort_by`, `unique_node_execute`.

##### `SidesetInfoVectorPostprocessor`
- Source: `framework/include/vectorpostprocessors/SidesetInfoVectorPostprocessor.h:17`
- Example: `test/tests/vectorpostprocessors/sideset_info/sideset_info.i:58` (sub-block `[side_info]`)
- Per-sideset metrics — area, centroid, bounding box, normal — as a table.
- Required: `boundary`, `meta_data_types`.

#### Histograms / collections

##### `HistogramVectorPostprocessor`
- Source: `framework/include/vectorpostprocessors/HistogramVectorPostprocessor.h:24`
- Example: `test/tests/vectorpostprocessors/histogram_vector_postprocessor/histogram_vector_postprocessor.i:49` (sub-block `[histo]`)
- Builds a histogram (counts + bin centers + lower/upper bounds) of values held by another VPP.
- Required: `vpp`, `num_bins`.
- Useful: `min_value`, `max_value`.

##### `VectorOfPostprocessors`
- Source: `framework/include/vectorpostprocessors/VectorOfPostprocessors.h:20`
- Example: `test/tests/vectorpostprocessors/vector_of_postprocessors/vector_of_postprocessors.i:49` (sub-block `[min_max]`)
- Concatenates several PPs into a single named vector — convenient for transfer & for plotting a small fixed list.
- Required: `postprocessors`.

##### `ConstantVectorPostprocessor`
- Source: `framework/include/vectorpostprocessors/ConstantVectorPostprocessor.h:14`
- Example: `test/tests/vectorpostprocessors/constant_vector_postprocessor/constant_vector_postprocessor.i:37` (sub-block `[constant]`)
- Hard-coded vector(s) — input data, transfer source, or feed for `HistogramVectorPostprocessor` / `ReporterPointSource`.
- Required: `value` (single vector) OR `vector_names` + `value` (multi-column).

#### Material samplers

##### `LineMaterialRealSampler`
- Source: `framework/include/vectorpostprocessors/LineMaterialRealSampler.h:19`
- Example: `test/tests/vectorpostprocessors/line_material_sampler/line_material_real_sampler.i:63` (sub-block `[mat]`)
- Quadrature-point sampling of a `Real` material property along a line.
- Required: `start`, `end`, `property`.
- Useful: `sort_by`.

##### `LineMaterialRankTwoSampler`
- Source: `modules/solid_mechanics/include/vectorpostprocessors/LineMaterialRankTwoSampler.h:21`
- Example: `modules/solid_mechanics/test/tests/line_material_rank_two_sampler/rank_two_sampler.i:57` (sub-block `[stress_xx]`)
- One `(i,j)` component of a `RankTwoTensor` material property along a line — companion is `LineMaterialRankTwoScalarSampler` for invariants.
- Required: `start`, `end`, `property`, `index_i`, `index_j`.

### `[Reporters]`

##### `ConstantReporter`
- Source: `framework/include/reporters/ConstantReporter.h:14`
- Example: `test/tests/reporters/constant_reporter/constant_reporter.i:14` (sub-block `[constant]`)
- Static typed scalars + vectors (Real, integer, string, dof_id_type, plus vector forms) — the canonical way to publish constants for `ReporterPointSource`, `ParsedReporter`, transfers.
- Required: at least one `<type>_names` + `<type>_values` pair (e.g. `real_names`/`real_values`, `real_vector_names`/`real_vector_values` — semicolons separate vectors).

##### `AccumulateReporter`
- Source: `framework/include/reporters/AccumulateReporter.h:18`
- Example: `test/tests/reporters/accumulated_reporter/accumulate_reporter.i:51` (sub-block `[accumulate]`)
- Appends per-timestep values of any list of Reporter/PP/VPP names to a growing vector — produces a time history.
- Required: `reporters` (list of `obj/value` reporter names; PP `foo` ↔ `foo/value`, VPP `foo` column `bar` ↔ `foo/bar`).

##### `MeshInfo`
- Source: `framework/include/reporters/MeshInfo.h:24`
- Example: `test/tests/reporters/mesh_info/mesh_info.i:42` (sub-block `[mesh_info]`)
- Mesh diagnostics — element counts per type, node counts, sideset/subdomain inventory.
- Useful: `items` (subset of metrics).

##### `IterationInfo`
- Source: `framework/include/reporters/IterationInfo.h:18`
- Example: `test/tests/reporters/iteration_info/iteration_info.i:47` (sub-block `[iteration_info]`)
- Time / timestep / nonlinear / linear iteration counts as a reporter — drop into JSON for solver diagnostics.
- Useful: `items`.

##### `PerfGraphReporter`
- Source: `framework/include/reporters/PerfGraphReporter.h:20`
- Example: `test/tests/reporters/perf_graph_reporter/perf_graph_reporter.i:41` (sub-block `[perf_graph]`)
- Serializes the `PerfGraph` timing tree into a Reporter for JSON output.
- Useful: `execute_on = FINAL`.

### `[UserObjects]`

UserObjects do not output directly. To inspect a UO value, pair it with `[AuxKernels] type = SpatialUserObjectAux` or `[VectorPostprocessors] type = SpatialUserObjectVectorPostprocessor`. Other objects consume them via `getUserObject<T>(name)`.

#### Layered / nearest-point

##### `LayeredAverage`
- Source: `framework/include/userobjects/LayeredAverage.h:19`
- Example: `test/tests/userobjects/layered_average/layered_average.i:53` (sub-block `[average]`); displaced 1D: `test/tests/userobjects/layered_average/layered_average_1d_displaced.i:71`
- Volume average of a variable in `num_layers` slabs along an axis. Spatially queryable per-element.
- Required: `variable`, `direction` (`x|y|z`), `num_layers`.
- Useful: `block`, `bounds` (custom layer edges instead of equispaced), `sample_type` (`direct|interpolate`), `cumulative`.

##### `LayeredIntegral`
- Source: `framework/include/userobjects/LayeredIntegral.h:20`
- Example: `test/tests/userobjects/layered_integral/layered_integral_test.i:65` (sub-block `[layered_integral]`)
- Volume integral per layer (LayeredAverage without dividing by layer volume).
- Required: `variable`, `direction`, `num_layers`.
- Useful: `bounds`, `cumulative`.

##### `LayeredSideAverage`
- Source: `framework/include/userobjects/LayeredSideAverage.h:19`
- Example: `test/tests/userobjects/layered_side_integral/layered_side_average.i:54` (sub-block `[layered_side_average]`)
- Average over a *sideset*, binned into layers along an axis (e.g. heat flux profile up a wall).
- Required: `variable`, `direction`, `num_layers`, `boundary`.

##### `NearestPointLayeredAverage`
- Source: `framework/include/userobjects/NearestPointLayeredAverage.h:24`
- Example: `test/tests/userobjects/nearest_point_layered_average/nearest_point_layered_average.i:54` (sub-block `[npla]`); points-from-UO variant: `test/tests/userobjects/nearest_point_layered_average/points_from_uo.i:57`
- A list of `LayeredAverage` profiles, one per nearest-point pin — for axially-binned, radially-pinned reactor geometry.
- Required: `variable`, `direction`, `num_layers`, plus `points` OR `points_file` OR `positions_object`.

##### `NearestPointAverage`
- Source: `framework/include/userobjects/NearestPointAverage.h:21`
- Example: `test/tests/userobjects/nearest_point_average/nearest_point_average.i:65` (sub-block `[npa]`)
- Single average per nearest-point bucket (no layering).
- Required: `variable`, plus `points` OR `points_file`.
- Useful: `block`.

#### Solution from external

##### `SolutionUserObject`
- Source: `framework/include/userobjects/SolutionUserObject.h:20`
- Example: `test/tests/userobjects/solution_user_object/read_exodus_initial.i:39` (sub-block `[soln]`)
- Reads a variable from an external Exodus / XDA / XDR file and exposes it for spatial sampling — typical for ICs / restart-from-other-mesh / one-way coupling.
- Required: `mesh`, `system_variables`.
- Useful: `timestep` (read a specific step), `transformation_order` (interpolation order), `execute_on`. Pair with `SolutionFunction` (Functions block) or `SolutionAux` (AuxKernels) to apply the result.

#### Geometric / search base classes

Not user-instantiated; these are the C++ inheritance points for custom UserObjects. See `../moose/userobject-authoring.md` for writing one.

##### `GeneralUserObject` / `ElementUserObject` / `NodalUserObject` / `InternalSideUserObject`
- Source: `framework/include/userobjects/GeneralUserObject.h:22`, `ElementUserObject.h:27`, `NodalUserObject.h:24`, `InternalSideUserObject.h:23`.
- Bases for: globally-scoped UOs (`General`); element-loop UOs (`Element`, block-restrictable, couples vars/mat props); node-loop UOs (`Nodal`, block+boundary restrictable); internal-side-loop UOs (`InternalSide`, for jump indicators / DG-style edge accumulation).

## Cross-cutting concerns

### `execute_on`
- All four blocks accept `execute_on` with any combination of `INITIAL`, `LINEAR`, `NONLINEAR`, `TIMESTEP_BEGIN`, `TIMESTEP_END`, `FINAL`, `CUSTOM`. If a value is consumed *inside* the residual (a `BodyForce` reading a PP, a `ParsedMaterial` reading a Reporter), include `LINEAR` or `NONLINEAR` — otherwise the value lags the current iterate. For one-shot diagnostics (`MeshInfo`, mesh-volume check) `INITIAL` is enough; for perf timing use `FINAL`.
- A PP/Reporter declared on `TIMESTEP_END` is *not* available inside that step's residual.

### `outputs` filter
- Every PP/VPP/Reporter accepts `outputs = '<name1> <name2>'` to route to specific outputs (`outputs = csv` keeps it out of Exodus globals; `outputs = none` silences entirely). Output names come from sub-blocks in `[Outputs]`. Use `show`/`hide` inside `[Outputs]` for filtering at the receive side.

### Consumers (PP/Reporter into a kernel)
- `BodyForce`, `MatBodyForce`, `HeatSource` take a `postprocessor` param. `ParsedFunction` / `ParsedAux` / `ParsedPostprocessor` / `ParsedMaterial` accept `pp_names = '...'` plus symbols inside `expression`. For scalar-variable feedback into the residual, prefer `ScalarVariable` + `[ScalarKernels]` — see [kernels.md](./kernels.md).
- To pull Reporter / VPP values back as point sources, use `[DiracKernels] type = ReporterPointSource` (kernels.md). Wire `value_name = vpp/column` plus `x_coord_name`/`y_coord_name`/`z_coord_name` (or `point_name`). Producer is typically a `ConstantReporter` with `real_vector_names = 'x y z weight'`, or a `ConstantVectorPostprocessor`.
- For Reporter-driven Functions: `ConstantFunction`, `PiecewiseConstantFromCSV`, or `ParsedFunction`'s `symbol_values`.

### `csv = true` shorthand
- `[Outputs] csv = true` dumps every PP and VPP to CSV (PPs combined; each VPP per-timestep at `<base>_<vppname>_<step>.csv`). Use `[Outputs/csv] type = CSV ...` for `execute_on`, `time_data`, `align_columns`. Reporters need `[Outputs/json] type = JSON` — they do not round-trip through CSV by default.

### `outputs = none` to silence
- Set `outputs = none` on internal PPs/VPPs/Reporters that exist only to feed another object. Keeps CSV clean and Exodus globals readable.

### `force_preaux` / `force_postaux`
- All four blocks inherit from `UserObjectBase` and sort into PRE_IC / PRE_AUX / POST_AUX groups by dependency analysis. Override with `force_preaux = true` (run before AuxKernels) or `force_postaux = true` (run after) when auto-detection misses a dependency; setting both errors out. Common case: a UO that *reads* an aux variable needs `force_postaux = true`.

## Minimal scaffold

A diffusion problem that publishes one PP (volume integral), one VPP (line sample), and one Reporter (constants for downstream consumers); JSON + CSV output:

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

[Kernels]
  [diff]
    type = ADDiffusion
    variable = u
  []
  [src]
    type = ADBodyForce
    variable = u
    function = 1
    postprocessor = scale  # PP feeds back into the residual
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

[Postprocessors]
  [u_integral]
    type = ElementIntegralVariablePostprocessor
    variable = u
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [scale]
    type = Receiver
    default = 1.0
    execute_on = 'INITIAL LINEAR'   # consumed inside the residual
  []
[]

[VectorPostprocessors]
  [centerline]
    type = LineValueSampler
    variable = u
    start_point = '0 0.5 0'
    end_point   = '1 0.5 0'
    num_points  = 21
    sort_by     = x
  []
[]

[Reporters]
  [constants]
    type = ConstantReporter
    real_names  = 'k rho'
    real_values = '1.0 0.0'
    outputs = none
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
[]

[Outputs]
  exodus = true
  csv = true
  [json]
    type = JSON
  []
[]
```
