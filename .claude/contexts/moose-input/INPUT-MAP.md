# MOOSE Input-File Authoring Map

Index for the MOOSE input-file authoring system. Each linked file tells subagents — about to write or edit a `.i` input file — which top-level block to edit, which registered object to pick, and how the pieces wire together. Citations are repo-relative paths from `/Users/maxnezdyur/projects/moose_stack/moose`.

If you're writing or editing C++ to add a *new* MOOSE object (kernel, BC, material, ...), see [`../moose/AUTHORING-MAP.md`](../moose/AUTHORING-MAP.md). This file covers the *picking* side: choosing existing registered objects in `.i` files.

## Quick reference: "I want to configure ___"

| Task | Guide |
|---|---|
| Pick a kernel (FE / FV / Linear-FV / DG / HDG / Nodal / Dirac / Scalar / Interface) | [kernels.md](./kernels.md) |
| Pick a BC (FE strong/weak, FV, Linear-FV, Constraint) | [bcs.md](./bcs.md) |
| Set initial conditions (FE / FV / Scalar) | [ics.md](./ics.md) |
| Declare a material property (constant, parsed, functor, derivative-parsed) | [materials.md](./materials.md) |
| Declare `[Variables]` / `[AuxVariables]` (FE family/order, FV, Scalar, Vector, Array) | [variables.md](./variables.md) |
| Build the mesh (`[Mesh]`, mesh generators, file-mesh) | [mesh.md](./mesh.md) |
| Compute a derived field for output | [kernels.md](./kernels.md) (AuxKernels) or [postprocess.md](./postprocess.md) |
| Reduce a field to a scalar / vector / typed reporter value | [postprocess.md](./postprocess.md) |
| Configure the executioner / time stepping / PETSc options / `[Problem]` | [executioner.md](./executioner.md) |
| Configure preconditioning (SMP / FSP / FDP / VCP) | [preconditioning.md](./preconditioning.md) |
| Couple sub-apps with `[MultiApps]` + `[Transfers]` | [multiapps.md](./multiapps.md) |
| Set up outputs (Exodus, CSV, Checkpoint, Console, Debug) | [outputs.md](./outputs.md) |
| Set up adaptive refinement / restart from checkpoint | [adaptivity-restart.md](./adaptivity-restart.md) |
| Define a `[Functions]` / `[Controls]` / `[GlobalParams]` entry | [functions-controls.md](./functions-controls.md) |
| Set up a heat-conduction simulation (incl. ThermalContact, gap heat transfer) | [heat-transfer.md](./heat-transfer.md) |
| Set up solid mechanics (small/finite strain, eigenstrain, `[Physics/SolidMechanics]`) | [solid-mechanics.md](./solid-mechanics.md) |
| Set up contact (mortar / node-face / penalty / CZM via `[Contact]`) | [contact.md](./contact.md) |
| Set up optimization (TAO driver, OptimizationReporter, ParameterMesh, SIMP) | [optimization.md](./optimization.md) |
| Set up UQ / surrogate / sensitivity (samplers, surrogates, trainers, `SamplerFullSolveMultiApp`) | [stochastic-tools.md](./stochastic-tools.md) |
| Set up XFEM with cutter UOs | [xfem.md](./xfem.md) |
| Pick a sensor / Arrhenius / ThermoDiffusion / fluid property | [misc.md](./misc.md) |
| Understand HIT syntax (brace paths, vectors, `!include`, `${var}`, `type=`, `active=`, `GlobalParams` precedence) | [hit-syntax.md](./hit-syntax.md) |

## Decision tree

Start here when you're not sure which guide to load:

1. **Is the task module-specific?** (heat conduction, solid mechanics, contact, optimization, UQ / stochastic tools, XFEM, sensors)
   - **Yes** → load that module's recipe first (e.g. [solid-mechanics.md](./solid-mechanics.md), [contact.md](./contact.md)). Module recipes call out which `[Physics/...]` shorthand to prefer and which cross-cutting block guides you'll still need (almost always [materials.md](./materials.md), [bcs.md](./bcs.md), [executioner.md](./executioner.md)).
   - **No** → continue.
2. **What top-level block are you editing?**
   - `[Mesh]` (geometry, file mesh, mesh generators, sidesets, subdomains) → [mesh.md](./mesh.md)
   - `[Variables]` / `[AuxVariables]` (family, order, FV, scalar, vector, array) → [variables.md](./variables.md)
   - `[Kernels]` / `[FVKernels]` / `[LinearFVKernels]` / `[DGKernels]` / `[HDGKernels]` / `[NodalKernels]` / `[DiracKernels]` / `[ScalarKernels]` / `[InterfaceKernels]` / `[AuxKernels]` → [kernels.md](./kernels.md)
   - `[BCs]` / `[FVBCs]` / `[LinearFVBCs]` / `[Constraints]` → [bcs.md](./bcs.md)
   - `[ICs]` / `[FVICs]` → [ics.md](./ics.md)
   - `[Materials]` (stored, functor, derivative-parsed, AD vs non-AD) → [materials.md](./materials.md)
   - `[Executioner]` / `[Problem]` (Steady, Transient, Eigenvalue, time integrators, time steppers, PETSc options) → [executioner.md](./executioner.md)
   - `[Preconditioning]` (SMP, FSP, FDP, VCP) → [preconditioning.md](./preconditioning.md)
   - `[MultiApps]` / `[Transfers]` → [multiapps.md](./multiapps.md)
   - `[Outputs]` / `[Debug]` → [outputs.md](./outputs.md)
   - `[Postprocessors]` / `[VectorPostprocessors]` / `[Reporters]` / `[UserObjects]` → [postprocess.md](./postprocess.md)
   - `[Functions]` / `[Controls]` / `[GlobalParams]` → [functions-controls.md](./functions-controls.md)
   - `[Adaptivity]` / restart-checkpoint patterns → [adaptivity-restart.md](./adaptivity-restart.md)
3. **HIT mechanics question** (path syntax, vector params, `!include`, `${var}`, `active=`, override precedence) → [hit-syntax.md](./hit-syntax.md).

## Cross-cutting decisions

These choices recur across every input file. Each block guide treats its own slice; the cross-cutting heuristics:

### AD vs non-AD
- Default to `AD*`-named classes for new inputs. Off-diagonal Jacobians wire automatically.
- `[FVKernels]` / `[FVBCs]` / `[HDGKernels]` are **always** AD (no non-AD twin).
- `[LinearFVKernels]` / `[LinearFVBCs]` are non-AD by construction (they assemble matrix + RHS without Newton).
- Mixing AD kernels with non-AD `[Materials]` breaks the AD chain — use `AD*`-prefixed material classes when consumers are AD.

### FE vs FV vs Linear-FV vs DG vs HDG
Pick the variable type in `[Variables]` first; the kernel/BC blocks follow:
- Default Lagrange `MooseVariable` → `[Kernels]` + `[BCs]`.
- `MooseVariableFVReal` (`type = MooseVariableFVReal` or `fv = true`) → `[FVKernels]` + `[FVBCs]`.
- `MooseLinearVariableFVReal` → `[LinearFVKernels]` + `[LinearFVBCs]`.
- `L2_LAGRANGE` / `MONOMIAL` discontinuous → `[DGKernels]` (interior facets) + DG-aware BCs.
- HDG variable trio (primal + face + optional gradient) → `[HDGKernels]`, share the trio via `[GlobalParams]`.

### Steady vs Transient vs Eigenvalue vs Optimize
- The `[Executioner]` `type` picks the temporal regime. Steady has no time derivatives; Transient needs a `*TimeKernel` / `*TimeDerivativeNodalKernel`; Eigenvalue uses `MassMatrix` + tagged matrices; `Optimize` (in `[Executioner]`) drives forward + adjoint sub-apps via `[MultiApps]` — see [optimization.md](./optimization.md).

### Physics shorthand vs hand-rolled blocks
- `[Physics/HeatConduction/FE]`, `[Physics/SolidMechanics/QuasiStatic]`, `[Contact]`, `[Physics/NavierStokes/...]` are **actions** that expand into the equivalent `[Variables]` + `[Kernels]` + `[BCs]` + `[Materials]`. Prefer them for standard cases.
- Drop to hand-rolled blocks when you need fine-grained control the action doesn't expose (custom material wiring, per-component kernel overrides, non-default variable scaling).
- For C++ action authoring, see [`../moose/action-authoring.md`](../moose/action-authoring.md).

### Postprocessor vs VectorPostprocessor vs Reporter vs UserObject
Same hierarchy as the C++ side ([`../moose/AUTHORING-MAP.md`](../moose/AUTHORING-MAP.md#postprocessor-vs-vectorpostprocessor-vs-reporter-vs-userobject)):
- One scalar consumed by Outputs / Controls / Terminator → `[Postprocessors]`.
- Named `std::vector<Real>` columns → `[VectorPostprocessors]`.
- Arbitrary typed values (struct, nested vector) → `[Reporters]`.
- Result consumed by other MOOSE objects (kernels, materials, transfers) but not Outputs → narrow `[UserObjects]`.

All four live in [postprocess.md](./postprocess.md).

## Cross-context shared types / vocabulary

Terms that recur across input guides:

- **`displacements`** — solid-mechanics global parameter listing displacement variables. Set once in `[GlobalParams]`; consumed by stress-divergence kernels, strain materials, contact, and many BCs.
- **`base_name`** — namespace prefix on material property names. Threads through `[Materials]`, `[Kernels]`, and `[AuxKernels]` so multi-physics can carry parallel stress/strain fields.
- **`eigenstrain_names`** — list parameter on the strain calculator (`ComputeEigenstrainBase` family) listing eigenstrain material props to subtract before forming the elastic strain.
- **`primary` / `secondary`** — canonical mortar/contact surface naming. Legacy `master` / `slave` are forbidden — do not use them in new inputs.
- **`exec_on`** — execute-flag parameter (`INITIAL` / `TIMESTEP_BEGIN` / `NONLINEAR` / `LINEAR` / `TIMESTEP_END` / `FINAL`) controlling when an object runs. Defaults differ per object type — check the registered class.
- **`block` / `boundary`** — subdomain / sideset restriction. Both accept lists. `block` for subdomain restriction; `boundary` for sideset/nodeset selection.
- **`controllable`** — flagged on a parameter in C++ via `declareControllable`. Toggle at runtime via `[Controls]` — see [functions-controls.md](./functions-controls.md).
- **`functor`** — any object evaluable on demand at points/faces/cells: a variable name, a `Function` name, *or* a functor mat-prop name. FV inputs lean on this heavily.

## When working in `moose/`

If you cd into a specific module's `examples/` or `test/tests/` directory, load the corresponding module recipe (e.g. [solid-mechanics.md](./solid-mechanics.md) under `modules/solid_mechanics/`) plus the per-block guides for whatever blocks you're editing. The block guides ([kernels.md](./kernels.md), [bcs.md](./bcs.md), [materials.md](./materials.md), ...) are always in scope — every `.i` file ultimately lists registered objects from those catalogs, regardless of which physics shorthand is on top.
