# Mesh-independent line heat sink (RayKernel)

## Pivot from prior design

The original spec built `ADLineDiracKernelBase` + `ADLineHeatSink` (DiracKernel-based, framework + heat_transfer). It did *not* deliver mesh independence in the meaningful sense: a fixed-order Gauss-Legendre rule on the user's polyline drops most of its points into 2 elements regardless of refinement, leaving every other crossed element with zero residual contribution. The line-integral *value* converges, but the *spatial distribution into the mesh* does not. For any non-trivial coupling strength `h` this manifests as spurious local cooling in a handful of elements.

The right primitive already exists: the `ray_tracing` module integrates per element-segment as a ray traces through the mesh, calling `onSegment()` for **every** element the ray crosses (`moose/modules/ray_tracing/src/raytracing/TraceRay.C:1019-1359, :2097-2105`), with built-in segment Gauss quadrature reinit'd via the standard `_fe_problem.reinitElemPhys` path (`moose/modules/ray_tracing/src/userobjects/RayTracingStudy.C:778-811`). `ADRayKernel` exposes `_u[_qp]`, `_test[_i][_qp]`, `_JxW[_qp]` exactly like a standard volumetric kernel (`moose/modules/ray_tracing/include/raykernels/ADRayKernel.h:62-71`), and `ADLineSourceRayKernel` (`moose/modules/ray_tracing/src/raykernels/LineSourceRayKernel.C:60-71`) is a working precedent for residual contribution along a ray.

This spec replaces the DiracKernel design with a single `ADRayKernel`-derived heat sink driven by a `RepeatableRayStudy`.

## Summary

Add `ADLineHeatSinkRayKernel` (a concrete `ADRayKernel`) that, on each segment of a ray that the `ray_tracing` module traces through the mesh, contributes `h·(T − T_sink)·ψ_i · JxW` to the residual of a temperature variable `T`. The polyline geometry is supplied by a `RepeatableRayStudy` user object. AD provides the Jacobian.

Mesh independence is by construction: the trace fires per crossed element, sub-segments shrink as the mesh refines, and the per-segment Gauss rule integrates the residual contribution accurately within each element.

User-facing knobs:
- A polyline: `start_points` / `end_points` on a `RepeatableRayStudy` (existing object — no new geometry input needed).
- The heat-sink coefficients `h` and `T_sink` on the `ADLineHeatSinkRayKernel`.

**Repo:** `moose/modules/heat_transfer` (concrete kernel) + dependency on `moose/modules/ray_tracing`.
**Object kind:** AD RayKernel (`ADRayKernel`-derived) + existing `RepeatableRayStudy`.

**Files to add:**
- `moose/modules/heat_transfer/include/raykernels/ADLineHeatSinkRayKernel.h`
- `moose/modules/heat_transfer/src/raykernels/ADLineHeatSinkRayKernel.C`
- `moose/modules/heat_transfer/test/tests/raykernels/line_heat_sink/line_heat_sink.i`
- `moose/modules/heat_transfer/test/tests/raykernels/line_heat_sink/tests`
- `moose/modules/heat_transfer/test/tests/raykernels/line_heat_sink/gold/*.csv`
- `moose/modules/heat_transfer/doc/content/source/raykernels/ADLineHeatSinkRayKernel.md`

**Files to remove (revert from prior design):**
- `moose/framework/include/dirackernels/ADLineDiracKernelBase.h`
- `moose/framework/src/dirackernels/ADLineDiracKernelBase.C`
- `moose/framework/doc/content/source/dirackernels/ADLineDiracKernelBase.md`
- `moose/modules/heat_transfer/include/dirackernels/ADLineHeatSink.h`
- `moose/modules/heat_transfer/src/dirackernels/ADLineHeatSink.C`
- `moose/modules/heat_transfer/doc/content/source/dirackernels/ADLineHeatSink.md`
- `moose/modules/heat_transfer/test/tests/dirackernels/line_heat_sink/` (entire directory)

**Pre-flight check:** confirm `heat_transfer/Makefile` (or app registration) already pulls in `ray_tracing`; if not, add the dependency. Search: `grep -r "ray_tracing" moose/modules/heat_transfer/{Makefile,*.mk,src/base}`.

## Physics / math + signature

### Continuous form

For a polyline `Γ` made of segments `Γ_s = [p_s, p_{s+1}]` and a temperature field `T`:

```
R_j = ∫_Γ h · (T(x) − T_sink) · ψ_j(x) dℓ
```

### Discrete (per-element-segment Gauss-Legendre, set up by the framework)

For each element `K` the ray crosses, the trace produces a sub-segment `[a_K, b_K] ⊂ Γ ∩ K` of length `ℓ_K = ‖b_K − a_K‖`. `RayTracingStudy::reinitSegment` lays a Gauss-Legendre rule of order `_segment_qrule->get_order()` on `[a_K, b_K]`, mapped into physical space, with `_assembly.qPoints()` and `_assembly.JxW()` populated; `_fe_problem.reinitElemPhys(K, q_points, tid)` reinits shape functions on `K` at those q-points. The kernel then assembles:

```
R_j |_K = Σ_{qp} JxW[qp] · h · (T(x_qp) − T_sink) · ψ_j(x_qp)
```

summed over all elements the ray crosses. AD generates the Jacobian.

### Mesh independence

By construction. Refining the mesh increases the number of `(K, [a_K, b_K])` sub-segments; each gets its own Gauss rule. No element on the line is skipped (`TraceRay` walks element-by-element). The total integrated source `Σ_K ℓ_K = polyline length` is invariant under refinement to within quadrature accuracy.

### `validParams` shape

**`ADLineHeatSinkRayKernel`** (extends `ADRayKernel::validParams()`):
- `addRequiredParam<Real>("h", "Heat transfer coefficient (W/(m·K)) for the line sink.")`
- `addRequiredParam<Real>("T_sink", "Temperature of the line sink (K).")`
- `variable` (inherited): the temperature variable `T`. Accessed via `_u[_qp]`.
- `study` (inherited from `RayKernelBase`): the `RepeatableRayStudy` that defines the polyline.

The `RepeatableRayStudy` user object (existing — no new code) takes:
- `start_points` and `end_points` (`std::vector<Point>` each) — the polyline as a sequence of chord endpoints.
- `execute_on = PRE_KERNELS` (set automatically when residual-contributing RayKernels are attached).

### Required overrides

**`ADLineHeatSinkRayKernel`**:
- `ADReal computeQpResidual() override { return _test[_i][_qp] * _h * (_u[_qp] - _T_sink); }`

That is the entire physics-bearing override. Residual loop, JxW multiplication, AD Jacobian, segment quadrature, per-element reinit are all inherited.

### Coupling

- Reads variable: `T = _u` (AD, via `ADRayKernel::_u` / `_var.adSln()`).
- Reads no material properties (v1).
- Writes no material properties.
- No block restriction at the kernel level — restriction is geometric (the ray's path) and is handled by the study.

## Reuse decisions

### `moose/modules/ray_tracing/src/raykernels/LineSourceRayKernel.C:60-71` — `ADLineSourceRayKernel`

**What it does:** Per-segment residual `(ψ_i, −factor)` along a ray, where `factor` is `value × postprocessor × function`. Templated `<is_ad>` via `GenericRayKernel`. Already AD.

**Decision:** Model on it; do not extend it.

**Why:** Its `factor` is purely spatial/temporal (no `_u` dependence). A sink term needs `_u[_qp]`. Cleanest move: clone the skeleton (header layout, registration macro, AD wiring), swap the integrand for `_h * (_u[_qp] - _T_sink)`. Trying to retrofit `LineSourceRayKernel` to optionally read `_u` would muddy a well-defined object.

### `moose/modules/ray_tracing/include/raykernels/ADRayKernel.h:62-71` — `ADRayKernel` base

**What it does:** Provides `_u`, `_grad_u`, `_test`, `_phi` analogous to a volumetric AD kernel; residual loop at `src/raykernels/ADRayKernel.C:81-92`; AD Jacobian assembled via `addJacobian` at `:109`.

**Decision:** Direct base class.

**Why:** Provides every member a sink term needs and writes into the residual via the standard tagging interface. No subclass plumbing required beyond `computeQpResidual`.

### `moose/modules/ray_tracing/include/userobjects/RepeatableRayStudy.h:19-47` — `RepeatableRayStudy`

**What it does:** Takes user `start_points` / `end_points`, builds rays at init, re-claims starting elements on `meshChanged()`.

**Decision:** Reuse as-is from input. No new study class.

**Why:** Exactly the polyline-endpoints pattern. It already handles the trace lifecycle, distributed mesh, adaptivity (`RepeatableRayStudyBase::meshChanged()` invalidates starting elems and re-claims), and execution scheduling. A custom study would duplicate this with no benefit for v1.

### `moose/modules/ray_tracing/src/userobjects/RayTracingStudy.C:778-811` — `reinitSegment`

**What it does:** For each `(elem, segment)`, builds a Gauss rule on `[start, end]` (order from `_segment_qrule`, set at `:267-268` from the system's `getMinQuadratureOrder`), maps to physical, calls `_fe_problem.reinitElemPhys(elem, q_points, tid)` so `_assembly.qPoints()/JxW()/phi/test` are valid.

**Decision:** Reuse as-is (transitively via `IntegralRayKernelBase`).

**Why:** This is the entire reason RayKernels are the right tool. Re-implementing it would re-implement what `XFEMElementPairLocator` does for cut surfaces, just for codim-2 lines. Free.

### Negative findings

- **No existing `RayKernel` reads `_u` for a sink-style residual.** `LineSourceRayKernel` uses spatial/PP factors; `VariableIntegralRayKernel` reads `coupledValue` but writes to ray data, not the residual. `ADLineHeatSinkRayKernel` is the first variable-aware-residual line kernel — pattern is sound (verified against `ADRayKernel.C:81-92` residual loop), but no copy-paste template exists for the exact use case.
- **No mesh-independence test for ray-traced sinks exists in the stack.** All existing RayKernel tests assert the *value* of an integral, not invariance under refinement. The mesh-independence sweep in this spec is novel for the ray_tracing test suite.

## Test plan

All tests under `moose/modules/heat_transfer/test/tests/raykernels/line_heat_sink/`. Three sub-tests in one `tests` spec.

### `mesh_independence_h_sweep` — Tester `CSVDiff`, parametrized

Five runs with `Mesh/gen/nx ∈ {8, 16, 32, 64, 128}` (and proportional `ny`, `nz`). Same `.i`: 3D unit cube, `ADHeatConduction` + `ADLineHeatSinkRayKernel` with a single straight ray from `(0, 0.371, 0.371)` to `(1, 0.371, 0.371)`, `h = 1.0`, `T_sink = 0`, prescribed steady `T(x) = x` via Dirichlet BCs on x=0/x=1 faces, insulated elsewhere. Postprocessor: `ElementIntegralVariablePostprocessor` of an aux variable `sink_density` populated by an `ADLineHeatSinkRayKernel` mirror configured to write to an aux (or simpler: a `Postprocessor` reading the `nl_residual_l2` of `T` against a known reference). All five runs CSVDiff against the same gold value `0.5 × h × line_length = 0.5` (analytic, since `T_avg_along_line = 0.5` for `T(x) = x` on the chord).

**Asserts:** integrated sink magnitude is invariant under volume-mesh refinement to `abs_zero = 1e-10`. This is the primary correctness gate.

**Mutation rationale:** the original DiracKernel design fails this test as `nx` grows because Dirac points cluster into 2 elements regardless of mesh. The RayKernel design must pass at all five resolutions to within quadrature accuracy.

### `analytic_segment_integral` — Tester `CSVDiff`

Single run on a coarse fixed mesh. Same straight ray. Prescribe `T(x) = x` exactly. Postprocess `∫_Γ h · (T − T_sink) dℓ = 0.5` analytically. CSVDiff against gold = 0.5 within `rel_err = 1e-6`.

**Mutation rationale:** if the per-segment quadrature order is too low for a linear `T`, this test catches it. (`_segment_qrule` defaults to the system's `getMinQuadratureOrder`, which should be ≥ 2 for first-order Lagrange — verify.) Also catches an off-by-`L/2` weight bug in any custom segment-handling code.

### `ad_jacobian` — Tester `PetscJacobianTester`

Same input as `analytic_segment_integral`. `ratio_tol = 1e-6`. Asserts AD Jacobian matches FD.

**Mutation rationale:** if `computeQpResidual` is rewritten to use a non-AD coupled-value access, residual still looks plausible but Jacobian is wrong; this catches it.

### Test-spec metadata

Each sub-test:
- `requirement = "..."` SQA field.
- `mesh_mode = REPLICATED` for the sweep (parallel ray claim + point-locator nondeterminism otherwise — mirror what existing RayKernel tests do).
- `design = "/raykernels/ADLineHeatSinkRayKernel.md"`.
- `issues = "#NNNN"` placeholder until issue is filed.
- Capability gate: `ray_tracing=true` (in case modules are conditionally built).

## Doc plan

### `moose/modules/heat_transfer/doc/content/source/raykernels/ADLineHeatSinkRayKernel.md`

Public surface:
- Class purpose: line-integrated Newton-cooling sink for a temperature variable, applied along a ray defined by a `RepeatableRayStudy`. Mesh-independent by construction.
- The `h` and `T_sink` parameters (with units).
- The `study` parameter — link to `RepeatableRayStudy` and explain the `start_points` / `end_points` pattern.
- One math block: `R_j = ∫_Γ h·(T − T_sink)·ψ_j dℓ`.
- Worked input snippet showing `[UserObjects/study]` with one straight ray and `[RayKernels/sink]` with `h`, `T_sink`, `variable = T`.
- Restrictions:
  - `COORD_XYZ` only (`ADRayKernel.C:54-56`).
  - Not usable in eigenvalue solves (`RayTracingStudy.C:212-214`).
  - Trace re-runs every Newton iteration (`execute_on = PRE_KERNELS` is mandatory and automatic).
- Cross-link to `ADLineSourceRayKernel` as the source counterpart.

## Out of scope

- **Non-AD twin.** AD-only for v1; non-AD users have other paths.
- **Material- or Function-valued `h` / `T_sink`.** `Real` constants only in v1.
- **Closed/looped or branching polylines.** Open polyline (sequence of chords) only — same as `RepeatableRayStudy`'s native input.
- **Function- or BSpline-defined curves.** v1 uses straight chords between user vertices, same as the underlying study.
- **Eigenvalue, RZ, and RSPHERICAL coordinate systems.** Hard-blocked by `ADRayKernel`. If needed, reach for a different approach (e.g., the prior DiracKernel design with proper sub-segmentation), but that is not v1.
- **Caching the trace across Newton iterations.** RayKernels with residual contributions must use `PRE_KERNELS`, which re-traces every residual/Jacobian eval. If this becomes a bottleneck for static geometry, a future `cache_trace_topology` shortcut would skip intersection computation while still re-evaluating per-segment quadrature. Not v1.
- **Generalizing to other physics (mass, momentum sinks).** The pattern (`ADRayKernel` + `_u[_qp]`-aware integrand) is reusable, but each new physics gets its own concrete class. No shared base proposed for v1 — `ADRayKernel` is already the shared base.
