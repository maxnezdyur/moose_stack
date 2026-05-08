# Authoring inputs: Functions, Controls, GlobalParams

Reach for this guide when you need to drive a `.i` file with **time/space-dependent values** (`[Functions]`), **runtime mutation of object parameters** (`[Controls]`), or **shared parameters across blocks** (`[GlobalParams]`). Functions are read by kernels (`BodyForce`), BCs (`FunctionDirichletBC`), aux kernels (`FunctionAux`), ICs (`FunctionIC`), materials (`GenericFunctionMaterial`), postprocessors, and integrators. Controls *set* parameters on already-constructed objects between steps. GlobalParams sets defaults that propagate into every sub-block — it is plumbing, not a catalog.

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. Each catalog entry cites the **source header** (`<file>:<line of class>`) and one **canonical example .i** (`<file>:<line>`).

## When to use this (vs alternatives)

Decide **which top-level block** first.

1. Need a value that depends on `(t, x, y, z)` and is consumed by name elsewhere: **`[Functions]`**. `ParsedFunction` is the default; reach for `PiecewiseLinear` for a CSV / time-table; `CompositeFunction` or `LinearCombinationFunction` for arithmetic over existing functions.
2. Need a derived field that lives **at quadrature points** as a material property — used inside kernels/BCs without a name collision with `Function` infrastructure: use **`[Materials]/ParsedMaterial`** or **`ADParsedFunctorMaterial`**, not a `Function`. See [materials.md](./materials.md). Functions are evaluated globally and don't carry block restriction the same way as materials.
3. Need a quantity that consumers query as a **functor** (`coeff` in `FVDiffusion`, `functor` in `FunctorAux`): a `Function` *is* a functor, so the same name works both ways. Pick `Function` when the value is purely `(t,x,y,z)`-dependent and you also want it usable in `FunctionDirichletBC`.
4. Need to **change a kernel/BC parameter at runtime** (turn a body force off after t=1, ramp a Dirichlet value, drive a coefficient from a postprocessor): **`[Controls]`**. Controls run at execute-on hooks and *write* the parameter; the target param must be declared `controllable = true` in C++ (verify by grepping `declareControllable`).
5. The "control" is just `if(t<1, A, B)` baked into a forcing function: skip `[Controls]` and put the conditional inside a `ParsedFunction` consumed by the kernel. Controls are needed only when you must mutate the parameter itself (or `enable`/`disable` whole objects).
6. Shared parameter that every sub-block of every type-block accepts (e.g. `displacements`, `use_displaced_mesh`, `use_automatic_differentiation`): **`[GlobalParams]`**. Anything set there applies to every sub-block whose `validParams()` registers that name; sub-block override always wins. Not for control-flow logic; not for unrelated objects.

If the residual contribution itself doesn't exist, see [kernels.md](./kernels.md). If the BC is missing, see [bcs.md](./bcs.md).

## Catalog

### `[Functions]` — analytic, tabulated, image, composite

#### Constant / parsed

##### `ConstantFunction`
- Source: `framework/include/functions/ConstantFunction.h:17`
- Example: `test/tests/functions/constant_function/constant_function_test.i:20` (sub-block `[icf]`)
- Returns a single scalar regardless of `(t,x,y,z)`. Cheap; prefer over `ParsedFunction` when there's no expression.
- Required: `value`.
- Useful: `value` is `controllable`.

##### `ParsedFunction` (alias for `MooseParsedFunction`)
- Source: `framework/include/functions/MooseParsedFunction.h:24` (registered as `ParsedFunction` at `framework/src/functions/MooseParsedFunction.C:18`)
- Example: `test/tests/functions/parsed/function.i:24` (sub-block `[sin_fn]`); nested: `test/tests/functions/constant_function/constant_function_test.i:15`
- Parsed math expression of `t,x,y,z` plus optional named symbols (other functions, scalar variables, postprocessors).
- Required: `expression` (was `value` in legacy inputs).
- Useful: `symbol_names`, `symbol_values` (one entry per `symbol_name` — function name, postprocessor name, scalar var, or numeric literal). Supports `if(cond, a, b)`, `min`, `max`, `pi`, `sin`, `cos`, `exp`, etc.

##### `ParsedVectorFunction` (alias for `MooseParsedVectorFunction`)
- Source: `framework/include/functions/MooseParsedVectorFunction.h:20` (registered at `framework/src/functions/MooseParsedVectorFunction.C:13`)
- Example: `test/tests/functions/parsed/vector_function.i:16` (sub-block `[conductivity]`)
- Three-component vector function (e.g. velocity field, anisotropic conductivity).
- Required: at least one of `expression_x`, `expression_y`, `expression_z` (defaults to 0 if omitted).
- Useful: same `symbol_names`/`symbol_values` mechanism as `ParsedFunction`.

#### Tabulated (1D, time / space)

##### `PiecewiseLinear`
- Source: `framework/include/functions/PiecewiseLinear.h:18`
- Example: `test/tests/functions/piecewise_linear/piecewise_linear.i:14`
- Linear interpolation between `(x_i, y_i)` pairs. Default abscissa is **time** unless `axis` is set.
- Required: one of `xy_data` / (`x` and `y`) / `data_file` / (`json_uo` for JSON).
- Useful: `axis = x|y|z` (use coordinate instead of `t`), `extrap = true` (linear extrapolation past endpoints — default is to clamp), `scale_factor`, `format = rows|columns` (CSV layout).

##### `PiecewiseConstant`
- Source: `framework/include/functions/PiecewiseConstant.h:17`
- Example: `test/tests/functions/piecewise_constant/piecewise_constant.i:42` (sub-block `[a]`)
- Step function — value held constant between abscissa points.
- Required: same data sources as `PiecewiseLinear`.
- Useful: `direction = left|right|left_inclusive|right_inclusive` (which side to take at the discontinuity), `axis`, `scale_factor`.

##### `PiecewiseBilinear`
- Source: `framework/include/functions/PiecewiseBilinear.h:48`
- Example: `test/tests/utils/2d_linear_interpolation/2d_linear_interpolation_test.i:139` (sub-block `[u]`)
- 2D bilinear interpolation from a CSV; the **first row** is one axis, the **first column** is the other (typically `time`).
- Required: `data_file`.
- Useful: `axis = 0|1|2` (which spatial coord pairs with the column axis), `xaxis`/`yaxis` for transposed layout, `radial = true` (treat axis as cylindrical radius).

##### `PiecewiseMultilinear`
- Source: `framework/include/functions/PiecewiseMultilinear.h:24`
- Example: `test/tests/functions/piecewise_multilinear/oneDa.i:130` (sub-block `[end1_fcn]`)
- N-dimensional linear interpolation (up to 4D: `x,y,z,t`) on a structured grid read from a custom text file. Use when `PiecewiseBilinear` is too rigid.
- Required: `data_file`. The file declares `AXIS X|Y|Z|T` blocks, knot positions, then a flattened `DATA` block.

##### `PiecewiseLinearFromVectorPostprocessor` (registered as `VectorPostprocessorFunction`)
- Source: `framework/include/functions/PiecewiseLinearFromVectorPostprocessor.h:20`
- Example: `test/tests/functions/piecewise_linear_from_vectorpostprocessor/vector_postprocessor_function.i:37` (sub-block `[point_value_function_u]`)
- Reads `(argument, value)` pairs **from a VectorPostprocessor** every step — useful for transferring sampled lines/points between MultiApps.
- Required: `vectorpostprocessor_name`, `argument_column`, `value_column`.
- Useful: `component = x|y|z|time` (which coord to use as the lookup), `error_on_missing_data`.

##### `PiecewiseConstantFromCSV`
- Source: `framework/include/functions/PiecewiseConstantFromCSV.h:18`
- Example: `test/tests/functions/piecewise_constant_from_csv/piecewise_constant.i:51` (sub-block `[element]`)
- Per-element / per-node / per-block / nearest-neighbor lookup from a CSV via a `PropertyReadFile` user object. The data is **not** interpolated — each element/node returns a value indexed by id.
- Required: `read_prop_user_object` (PropertyReadFile UO name), `read_type` (`element|node|voronoi|block`), `column_number` (0-based).

#### Image / external

##### `ImageFunction`
- Source: `framework/include/functions/ImageFunction.h:19`
- Example: `test/tests/functions/image_function/image.i:35` (sub-block `[image_func]`)
- Samples a 2D/3D image (PNG stack) at the spatial point — used to seed ICs from CT/microstructure data.
- Required: `file` (single image) or `file_base` + `file_suffix` + `file_range` (stack).
- Useful: `component` (RGB channel), `threshold` + `upper_value` / `lower_value` (binarize), `flip_x|flip_y|flip_z`, `shift`, `scale`.

#### Composite

##### `CompositeFunction`
- Source: `framework/include/functions/CompositeFunction.h:19`
- Example: `test/tests/bcs/function_dirichlet_bc/test.i:40` (sub-block `[fn_composite]`)
- Returns `scale_factor * prod(functions)` — multiplicative combination of named functions.
- Required: `functions` (list of function names).
- Useful: `scale_factor` (default 1).

##### `LinearCombinationFunction`
- Source: `framework/include/functions/LinearCombinationFunction.h:18`
- Example: `test/tests/functions/linear_combination_function/lcf1.i:61` (sub-block `[the_linear_combo]`)
- Returns `sum(w_i * functions_i)` — weighted sum of named functions.
- Required: `functions`, `w` (same length).

##### `MooseParsedFunction` (composition via `symbol_values`)
- Source: `framework/include/functions/MooseParsedFunction.h:24`
- Example: `test/tests/functions/parsed/function.i:33` (sub-block `[fn]` with `symbol_names = 's c'`, `symbol_values = 'sin_fn cos_fn'`)
- Use the parser itself as the composition layer when `Composite` / `LinearCombination` aren't expressive enough (e.g. `s/c`, `if(...)`, nonlinear blends). The named symbols can resolve to other Functions, postprocessors, or scalar variables.

#### Time-only idioms (no dedicated `SinFunction`)

The framework does **not** ship a `SinFunction` / `CosFunction` — use `ParsedFunction` with `expression = 'sin(2*pi*f*t)'`. Repository-canonical examples include `test/tests/controls/libtorch_nn_control/read_control.i:8` (`expression = "sin(${pi}/${period}*t)"`) and `test/tests/functions/parsed/function.i:24-30`.

For tabulated time-only data (e.g. an experimental forcing curve), use `PiecewiseLinear` with default `axis` (time) and supply `x = '0 1 2 3'` (times) + `y = '...'`.

### `[Controls]` — runtime parameter mutation and object enable/disable

Controls operate on the parameter system at `execute_on` hooks. Two flavors:
- **Value writers** (`RealFunctionControl`, `BoolFunctionControl`, `LibtorchNeuralNetControl`) push a value into a controllable parameter selected by a `parameter` glob like `block/object_name/param`.
- **Toggle controls** (`TimePeriod`, `ConditionalFunctionEnableControl`, `TimesEnableControl`) flip the synthetic `enable` parameter on a list of `enable_objects` / `disable_objects` (referenced as `<System>::<name>`, e.g. `Kernel::diff0`).

##### `TimePeriod`
- Source: `framework/include/controls/TimePeriod.h:18`
- Example: `test/tests/controls/time_periods/kernels/kernels.i:58` (sub-block `[diff]`)
- Enable/disable a list of MooseObjects between `start_time` and `end_time`. Inserts those times into the TimeStepper sync list automatically.
- Required: `enable_objects` and/or `disable_objects` (`Kernel::name` / `BC::name` / `*::name` globs), `start_time`, `end_time`.
- Useful: `set_sync_times = false` (skip auto-sync), `reverse_on_false` (re-enable outside the window).

##### `RealFunctionControl`
- Source: `framework/include/controls/RealFunctionControl.h:20`
- Example: `test/tests/controls/real_function_control/real_function_control.i:69` (sub-block `[func_control]`); multi-target glob: `test/tests/controls/real_function_control/multi_real_function_control.i:92`
- Evaluates a `Function` at the current time (point `(0,0,0)`) and writes the result to one or more `Real` parameters selected by a glob.
- Required: `function`, `parameter` (e.g. `Kernels/diff/coef`, `*/*/coef`).
- Useful: `execute_on` (default `TIMESTEP_BEGIN`; use `INITIAL TIMESTEP_BEGIN` to seed t=0), `implicit = true`.

##### `BoolFunctionControl`
- Source: `framework/include/controls/BoolFunctionControl.h:19`
- Example: `test/tests/controls/bool_function_control/bool_function_control.i:33` (sub-block `[solve_ctrl]`)
- Like `RealFunctionControl` but truthifies the function result and writes a `bool`. Common idiom: turn `Problem/solve` on/off, switch a kernel's `enable`.
- Required: `function`, `parameter`.

##### `ConditionalFunctionEnableControl`
- Source: `framework/include/controls/ConditionalFunctionEnableControl.h:19`
- Example: `test/tests/controls/conditional_functional_enable/conditional_function_enable.i:97` (sub-block `[u_threshold]`)
- Evaluates `conditional_function`; when **truthy**, enables `enable_objects` and disables `disable_objects` (and vice-versa when false). The function may reference postprocessors / scalar variables via `symbol_values`, so the toggle can depend on the running solution — not just `t`.
- Required: `conditional_function`, `enable_objects` and/or `disable_objects`.

##### `LibtorchNeuralNetControl` (libtorch build only)
- Source: `framework/include/libtorch/controls/LibtorchNeuralNetControl.h:25`
- Example: `test/tests/controls/libtorch_nn_control/read_control.i:97` (sub-block `[src_control]`)
- Drives `parameters` from the forward pass of a Torch network whose inputs are postprocessor `responses`. Used for RL-trained controllers in stochastic_tools workflows. Skip if your build doesn't include libtorch.
- Required: `parameters`, `responses`.
- Useful: `filename` (load a `.pt`), `num_neurons_per_layer`, `activation_function`, `torch_script_filename`.

### `[GlobalParams]` — shared parameter defaults

`[GlobalParams]` is **not a catalog**. Any parameter set inside applies to every sub-block of every type-block (`[Variables]`, `[Kernels]`, `[BCs]`, `[Materials]`, `[AuxKernels]`, ...) whose `validParams()` registers a parameter with that name. The sub-block's own setting always wins; `[GlobalParams]` only fills in missing values.

Common idioms:
- `displacements = 'disp_x disp_y'` — solid-mechanics convention. Every solid-mechanics kernel, BC, material, and PhysicsBlock that needs the displacement vector reads it from here, so you set it once. Example: `modules/solid_mechanics/test/tests/ad_simple_linear/linear-ad.i:1`.
- `use_displaced_mesh = true` — turn on displaced-mesh evaluation for every object that supports it (kernels, BCs, materials, postprocessors).
- `gravity = '0 -9.81 0'` for porous-flow / Navier-Stokes inputs.
- `block = 'mat1 mat2'` to restrict everything to a subdomain group (rare; usually you want this per sub-block).

Anti-pattern: putting parameters in `[GlobalParams]` that are only valid for one sub-block. The framework will accept it, but the value will silently fail to apply to objects that don't register the name (and you'll waste an afternoon hunting "why is it 1.0 not 2.0?"). When in doubt, set the parameter on the specific sub-block.

## Cross-cutting concerns

### Function evaluation contexts
- A `Function` is evaluated as `f(t, Point(x,y,z))`. Most callers pass `(_t, _q_point[_qp])` (kernels, materials), `(_t, *_current_node)` (nodal BCs/ICs), or `(_t, Point(0,0,0))` (postprocessors / `RealFunctionControl`). When `axis` is set on a piecewise function, only that one coordinate is read — `t` is ignored.
- `Function` derives from `FunctorBase<Real>` (`framework/include/functions/Function.h:29`) so any kernel/BC parameter typed `MooseFunctorName` accepts a Function name interchangeably with a variable name or a functor material property name. This is how `FVDiffusion`'s `coeff` happily takes either.
- `Function` also exposes `gradient(t, p)` and `timeDerivative(t, p)`. Parsed and piecewise functions implement these analytically; image/data-table ones may fall back to finite differences (set `enable_time_derivatives = true` if needed).

### `controllable = true` declaration on parameters
- A parameter is mutable by `[Controls]` only if its `validParams()` calls `params.declareControllable("name")`. Examples: `BodyForce::value` (`framework/src/kernels/BodyForce.C:31`), `Reaction::rate` (`framework/src/kernels/Reaction.C:24`), most `*BC` `value` params, `Problem/solve`.
- If a control glob matches a non-controllable parameter, MOOSE will error at construction with `parameter '...' is not controllable`. To verify before authoring: `grep -r "declareControllable" framework/src modules/<X>/src` for the param name.
- The `RealControlParameterReporter` postprocessor (`Postprocessors/coef`, see `real_function_control.i:62`) is the standard way to *observe* the live value of a controlled parameter in CSV output.

### `[Controls]` `execute_on` hooks
- Default for value writers is `TIMESTEP_BEGIN`. To make the control fire at `t=0` (so the first solve sees the controlled value rather than the input default), use `execute_on = 'INITIAL TIMESTEP_BEGIN'`. To respond to a state change between nonlinear iterations, use `LINEAR` or `NONLINEAR`.
- Toggle controls (`TimePeriod`, `ConditionalFunctionEnableControl`) typically use `TIMESTEP_BEGIN` so the enable/disable state is set before the residual is evaluated. `ConditionalFunctionEnableControl` examples often use `INITIAL TIMESTEP_END` to read the current solution before deciding.

### `[GlobalParams]` precedence and overrides
- Lookup order: explicit sub-block value → `[GlobalParams]` value → `validParams()` default. So `[GlobalParams] use_displaced_mesh = true` plus a single `[Kernels/diff] use_displaced_mesh = false` cleanly overrides for that one kernel.
- Vector parameters: `[GlobalParams] displacements = 'disp_x disp_y'` and a sub-block `displacements = 'disp_x'` *replaces* the whole vector — there is no merge.
- Parameter names that exist in multiple unrelated objects are still resolved by name only. If `displacements` happens to be a parameter on an object that has nothing to do with mechanics, it will get the GlobalParams value too. Watch for collisions; rename if needed.

### How Functions are consumed
- **`BodyForce` / `ADBodyForce` / `HeatSource` / `FVBodyForce`** — `function = my_fn` multiplies the body-force value.
- **`FunctionDirichletBC` / `ADFunctionDirichletBC` / `FunctionNeumannBC`** — `function = my_fn` evaluated at boundary nodes/QPs.
- **`FunctionAux`** — `function = my_fn` written to an aux variable (the simplest way to *visualize* a function).
- **`FunctionIC`** — `function = my_fn` for initial conditions.
- **`GenericFunctionMaterial` / `ADGenericFunctionMaterial`** — wraps function values into material properties (use when downstream code expects a `MaterialPropertyName`).
- **HDG / mixed kernels** — `source = my_fn` on `DiffusionLHDGKernel` etc. (functor parameter; Function is accepted).
- **`Postprocessors/FunctionValuePostprocessor`** — sample the function at a point + time.

## Minimal scaffold

A 1D diffusion problem driven by a `ParsedFunction` body force, with a `RealFunctionControl` ramping the diffusion coefficient, and `[GlobalParams]` declaring a (here trivial) shared default:

```hit
[GlobalParams]
  use_displaced_mesh = false
[]

[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 20
    xmax = 1
  []
[]

[Variables]
  [u]
  []
[]

[Functions]
  [forcing_fn]
    type = ParsedFunction
    expression = 'sin(pi*x)*exp(-t)'
  []
  [coef_ramp]
    type = ParsedFunction
    expression = '0.1 + 0.9*min(t, 1.0)'   # 0.1 -> 1.0 over the first second
  []
[]

[Kernels]
  [diff]
    type = ADCoefDiffusion
    variable = u
    coef = 0.1                              # initial value; mutated by the Control
  []
  [td]
    type = ADTimeDerivative
    variable = u
  []
  [src]
    type = ADBodyForce
    variable = u
    function = forcing_fn
  []
[]

[BCs]
  [all]
    type = ADDirichletBC
    variable = u
    boundary = 'left right'
    value = 0
  []
[]

[Controls]
  [coef_control]
    type = RealFunctionControl
    parameter = 'Kernels/diff/coef'
    function = coef_ramp
    execute_on = 'INITIAL TIMESTEP_BEGIN'
  []
[]

[Postprocessors]
  [coef_seen]
    type = RealControlParameterReporter
    parameter = 'Kernels/diff/coef'
  []
[]

[Executioner]
  type = Transient
  num_steps = 10
  dt = 0.1
  solve_type = NEWTON
[]

[Outputs]
  csv = true
  exodus = true
[]
```

Two notes on this scaffold:
1. `coef` on `ADCoefDiffusion` is declared `controllable` — a `RealFunctionControl` glob like `Kernels/*/coef` would also match. If the parameter you want to control isn't controllable, the input fails at construction (see "controllable = true" above).
2. `[GlobalParams] displacements = 'disp_x disp_y'` is the canonical mechanics idiom — every solid-mechanics kernel/BC/material reads it transparently; see `modules/solid_mechanics/test/tests/ad_simple_linear/linear-ad.i:1` for the standard 2D form.
