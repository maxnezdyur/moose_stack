# MOOSE Authoring Map

Index for the MOOSE C++ authoring-guide system. Each linked file tells subagents — about to write or edit MOOSE code — when to pick which base class, what to override, how to wire it up, and what goes wrong. Citations are repo-relative paths from `/Users/maxnezdyur/projects/moose_stack/moose`.

## Quick reference: "I want to add a new ___"

| Task | Guide |
|---|---|
| Volumetric residual term (FE / FV / DG / HDG / Nodal / Dirac / Scalar / Interface / Linear-FV) | [kernel-authoring.md](./kernel-authoring.md) |
| Boundary condition (FE strong/weak, FV, Linear-FV) | [bc-authoring.md](./bc-authoring.md) |
| Initial condition (FE / FV / Scalar / Vector / Array) | [ic-authoring.md](./ic-authoring.md) |
| Material property (stored or functor; AD or non-AD; stateful) | [material-authoring.md](./material-authoring.md) |
| Aux variable computation (visualization / output only) | [auxkernel-authoring.md](./auxkernel-authoring.md) |
| Postprocessor / VectorPostprocessor / Reporter | [postprocessor-authoring.md](./postprocessor-authoring.md) |
| UserObject (general / element / side / interface / mortar / nodal / domain) | [userobject-authoring.md](./userobject-authoring.md) |
| Action / PhysicsBase / ActionComponent (input scaffolding) | [action-authoring.md](./action-authoring.md) |
| Strain calculator, stress material, eigenstrain, return-mapping, Physics | [solid-mechanics-authoring.md](./solid-mechanics-authoring.md) |
| Conduction kernel, gap flux model, radiative BC, ThermalContact wiring | [heat-transfer-authoring.md](./heat-transfer-authoring.md) |
| Mortar / node-face contact, CZM, augmented Lagrange | [contact-authoring.md](./contact-authoring.md) |
| OptimizationReporter, forward+adjoint, ParameterMesh, SIMP | [optimization-authoring.md](./optimization-authoring.md) |
| Sampler, Distribution, Surrogate+Trainer, StochasticReporter, MultiApp wiring | [stochastic-tools-authoring.md](./stochastic-tools-authoring.md) |
| Cutter UO, mesh cut, crack growth, XFEM interface constraint, near-tip enrichment | [xfem-authoring.md](./xfem-authoring.md) |
| Sensor postprocessor, Arrhenius material, ThermoDiffusion+CoefDiffusion | [misc-authoring.md](./misc-authoring.md) |

## Decision tree

Start here when you're not sure which guide to load:

1. **Is the task module-specific?** (e.g., a stress material, a gap flux model, a mortar contact UO, an OptimizationReporter, a custom Sampler, a crack cutter, a sensor postprocessor)
   - **Yes** → load that module's guide first; load the matching object-type guide if you need cross-cutting patterns (AD, off-diagonal Jacobian, etc.)
   - **No** → continue.
2. **What kind of object is it?**
   - Computes a residual at quadrature points / faces / nodes inside the domain → **[kernel-authoring.md]**
   - Computes a residual on a boundary → **[bc-authoring.md]**
   - Sets the variable's value at simulation start → **[ic-authoring.md]**
   - Computes/stores a property other objects consume in the residual → **[material-authoring.md]**
   - Computes a value just for output (no residual contribution) → **[auxkernel-authoring.md]**
   - Reduces a field to a single scalar/vector for output / Controls / Terminator → **[postprocessor-authoring.md]**
   - Reduces a field for downstream **MOOSE objects** (not just output) → **[userobject-authoring.md]**
   - Adds whole-block input scaffolding (`[Physics/.../X]` block expands into N objects) → **[action-authoring.md]**

## Cross-cutting decisions

These choices recur across object types. Each guide treats its own slice; the cross-cutting heuristics:

### AD vs non-AD
- **AD** is the default for new code. It propagates derivatives automatically — no hand-coded off-diagonal Jacobian to maintain.
- **Non-AD** when: the AD chain breaks (a coupled value enters via a UserObject that drops AD seeds), or perf-critical hot loops where AD overhead dominates, or you're matching a legacy class's interface.
- **AD-only** in some places: mortar gap heat transfer (`ModularGapConductanceConstraint`), most modern mortar contact constraints, FV is internally AD.

### FE vs FV vs Linear-FV vs DG vs HDG
- **FE** for a `MooseVariable` (Lagrange / Hermite / etc.) → `Kernel` family.
- **FV** for a `MooseVariableFV` (cell-centered) → `FVKernel` family. Always AD internally.
- **Linear-FV** for a `LinearSystem` (matrix-assembled, no Newton) → `LinearFVKernel`.
- **DG** for explicit element-wise discontinuous Galerkin → `DGKernel`.
- **HDG** for hybridizable DG with face multipliers → `HDGKernel` / `IPHDGKernel`.

### Material vs AuxKernel vs FunctorMaterial
- **Material** if the value enters the residual (consumed by a kernel/BC), stored at quadrature.
- **FunctorMaterial** if the value should be evaluable on demand at faces / cells / arbitrary points without being stored — preferred for FV consumers and lazy multi-call patterns.
- **AuxKernel** if the value is purely for output / postprocessing and never read by a kernel.

### Postprocessor vs VectorPostprocessor vs Reporter vs UserObject
- **Postprocessor** for one scalar (`Real`) consumed by Outputs / Controls / Terminator.
- **VectorPostprocessor** for one or more named `std::vector<Real>` columns.
- **Reporter** for arbitrary typed values (struct, nested vector, etc.) with named access — supersedes both above.
- **UserObject (narrow)** when the result is consumed by other MOOSE objects (kernels, materials, transfers) and not by Outputs. Postprocessor is a UserObject under the hood.

### Action vs PhysicsBase vs ActionComponent
- **Action**: small input-block expansion ("add these 3 objects when this block is parsed").
- **PhysicsBase**: whole-physics shorthand (variables + kernels + ICs + BCs + outputs scaffolded by `add*` virtuals).
- **ActionComponent**: geometric/physical component (`CylinderComponent`, `PinComponent`) that wires mesh + ICs + BCs + physics together for a region.

## Cross-context shared types

Types defined in `framework/include/utils/` (or framework/) and used across all modules:
- **`RankTwoTensor`** / **`RankFourTensor`** — solid mechanics, but framework-owned. AD specializations: `ADRankTwoTensor`, `ADRankFourTensor`.
- **`Moose::Functor<T>`** / **`FunctorBase<T>`** — functor-material values, FV kernel inputs.
- **`Real`** / **`ADReal`** — the AD-vs-non-AD switch.
- **`MaterialPropertyName`** / **`VariableName`** / **`FunctionName`** / **`ReporterName`** / **`UserObjectName`** — typed input-parameter strings; use these instead of bare `std::string`.
- **`SubdomainName`** / **`BoundaryName`** — same idea for mesh restriction parameters.

Geometric infrastructure that shows up across modules:
- **`PenetrationLocator`** / **`NearestNodeLocator`** (framework geomsearch) — consumed by [contact-authoring.md] (node-face formulations) and [heat-transfer-authoring.md] (`GapHeatTransfer`).
- **`CrackFrontDefinition`** (defined in solid_mechanics) — consumed by [xfem-authoring.md] mesh cutters and by SM domain-integral computation.
- **`MultiApp`** / **`Transfer`** (framework) — specialized by [stochastic-tools-authoring.md] (`SamplerFullSolveMultiApp`) and used heavily by [optimization-authoring.md] for forward/adjoint sub-app coupling.

## Vocabulary that recurs across guides

- **primary / secondary** — canonical mortar/node-face surface naming. Legacy `master` / `slave` are aliases to AVOID. Same naming used by contact, heat-transfer gap, and XFEM interface kernels.
- **`base_name`** — solid_mechanics multi-physics namespace prefix on material property names; thread it through every `declareProperty` and `getMaterialProperty`.
- **`eigenstrain_names`** — solid_mechanics list parameter on the strain calculator listing eigenstrain properties to subtract.
- **`exec_on`** — execute-flag parameter controlling when an object runs (INITIAL / TIMESTEP_BEGIN / NONLINEAR / LINEAR / TIMESTEP_END / FINAL). Different defaults per object type — check the base.

## When working in `moose/`

If you cd into a specific module directory, load the corresponding module-authoring file plus any framework-authoring files for the object type you're writing. The framework guides are always in scope — every concrete MOOSE object subclasses a framework base, so the framework patterns (AD, registration, `validParams`, coupling) always apply.
