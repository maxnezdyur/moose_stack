---
title: Arc-length continuation
feature: arclength-method
repo: moose
scope: moose
object_kind: "Problem (ArcLengthProblem : FEProblem) + NonlinearSystem subclass + Postprocessor + VectorPostprocessor"
status: approved
created: 2026-08-24
---

## Summary

Add a general arc-length continuation capability to the MOOSE framework by wrapping PETSc's
`SNESNEWTONAL` solver (Riks-family arc-length Newton, PETSc 3.25.2). An unknown scalar load
multiplier $\lambda$ scales a user-designated "load" portion of the residual, so the solver can
trace equilibrium paths past limit points (snap-through, snap-back) where prescribed-load stepping
diverges.

**Problem.** MOOSE has no path-following capability (scout-verified negative across framework,
modules, blackbear, isopod). Structural snap-through and aggressively ramped source terms (nuclear
fuel) both hit limit points where load-controlled Newton has no equilibrium to converge to. The one
mention of Riks in the stack is a not-implemented comment
(`moose/modules/solid_mechanics/include/userobjects/AbaqusUserElement.h:41`). PETSc has shipped a
maintained arc-length SNES since 3.22; nothing in MOOSE references it.

**Solution.** No new Executioner: `[Executioner] type = Steady` drives one `SNESSolve` that traces
the whole path internally. The load is designated with the replacing tag parameters
`vector_tags = 'arc_length_load'` (and `matrix_tags = 'arc_length_load_jac'` for follower loads) on
ordinary residual objects; any Kernel, IntegratedBC, non-preset NodalBC, DiracKernel, or NodalKernel
works with zero new physics classes. Continuation is controlled from the `[Problem]` block. The
load-displacement curve is recorded per increment by a new `ARCLENGTH_INCREMENT` execute flag feeding
an `ArcLengthHistory` VectorPostprocessor, with `ArcLengthLoadParameter` exposing $\lambda$.

**Files.** New: `framework/{include,src}/systems/ArcLengthNonlinearSystem.{h,C}` (U1),
`framework/{include,src}/problems/ArcLengthProblem.{h,C}` (U2),
`framework/{include,src}/postprocessors/ArcLengthLoadParameter.{h,C}` (U3),
`framework/{include,src}/vectorpostprocessors/ArcLengthHistory.{h,C}` (U4), three tests inputs under
`test/tests/problems/arc_length/`, three doc pages. Existing: `framework/include/base/Moose.h` and
`Moose.C` (the execute flag).

## Physics

Continuation problem (proportional loading; MOOSE sign convention, every tagged object assembles
the same signed contribution it would assemble normally):

$$\mathbf{R}(\mathbf{u},\lambda) = \mathbf{F}_{\mathrm{int}}(\mathbf{u}) + \lambda\,\mathbf{R}_{\mathrm{load}}(\mathbf{u}) = \mathbf{0}$$

$$\mathbf{J}(\mathbf{u},\lambda) = \frac{\partial \mathbf{F}_{\mathrm{int}}}{\partial \mathbf{u}} + \lambda\,\frac{\partial \mathbf{R}_{\mathrm{load}}}{\partial \mathbf{u}}$$

with the arc-length constraint enforced per continuation increment by `SNESNEWTONAL`:

$$N(\Delta\mathbf{u},\Delta\lambda) = \Delta\mathbf{u}^{\top}\Delta\mathbf{u} + \psi^{2}\,\Delta\lambda^{2}\,\mathbf{Q}^{\top}\mathbf{Q} - \Delta s^{2} = 0$$

| symbol | meaning |
|---|---|
| $\mathbf{u}$ | all nonlinear DOFs (full-vector norm in v1; multiphysics weighting via variable scaling) |
| $\lambda$ | scalar load multiplier, an unknown of the solve; $0 \to \lambda_{\max}$, not monotonic, $\Delta\lambda$ changes sign at limit points |
| $\mathbf{F}_{\mathrm{int}}$ | assembled residual of every non-load object |
| $\mathbf{R}_{\mathrm{load}}$ | assembled residual of the objects routed to the load vector tag |
| $\mathbf{Q} = \partial\mathbf{R}/\partial\lambda = \mathbf{R}_{\mathrm{load}}$ | tangent load vector, supplied by a callback |
| $\psi^2$ | load-term weighting (`psi_squared`); $\psi = 0$ gives the cylindrical constraint |
| $\Delta s$ | arc-length increment (`step_size`), fixed per run in v1 |

One `SNESSolve` executes the whole continuation: increments in the outer loop (`al.c:372`), Newton
corrections in the inner loop (`al.c:388`), exit when $\lambda \ge \lambda_{\max}$ (`al.c:564`).
The bordered algebra lives inside PETSc; MOOSE supplies only $\mathbf{R}$, $\mathbf{J}$, and
$\mathbf{Q}$.

### U1 ArcLengthNonlinearSystem: tag ownership and routing

No physics of its own. Creates the load vector tag (GHOSTED, so it survives standard assembly) and
the load matrix tag. Overrides `postAddResidualObject(ResidualObject &)` (virtual no-op at
`NonlinearSystemBase.h:877`) to validate routing: a load-tagged object that still carries the default
`nontime` vector tag (the user wrote `extra_vector_tags` instead of the replacing `vector_tags`) is a
hard error, because the load would double-count.

### U2 ArcLengthProblem: SNES wiring, tangent load, Jacobian combine

PETSc adds the callback vector to the MOOSE residual at each function evaluation (`al.c:378-380`),
so the standard residual path assembles only $\mathbf{F}_{\mathrm{int}}$ and the callback supplies
$\mathbf{Q}$:

```cpp
PetscErrorCode
arcLengthTangentLoad(SNES snes, Vec X, Vec Q, void * ctx)
{
  // Q is the FULL external load at the END of the step, not lambda-scaled;
  // PETSc composes lambda internally (al.c:267-276, :378-380).
  problem.computeLoadResidual(X, Q);
  return PETSC_SUCCESS;
}
```

$$\mathbf{R} = \underbrace{\mathbf{F}_{\mathrm{int}}(\mathbf{u})}_{\text{MOOSE residual (non-load tags)}} + \underbrace{\lambda\,\mathbf{R}_{\mathrm{load}}(\mathbf{u})}_{\text{callback vector } \mathbf{Q}}$$

```cpp
void
ArcLengthProblem::computeJacobianSys(...)
{
  FEProblem::computeJacobianSys(...);                 // J = J_std
  computeJacobianTag(u, J_load, _load_matrix_tag);    // assemble the load matrix tag
  jacobian.add(_lambda, J_load);                      // J += lambda * J_load
}
```

validParams, `ArcLengthProblem`:

| param | type | default | PETSc mapping |
|---|---|---|---|
| `load_vector_tag` | TagName | `arc_length_load` | tag users put in `vector_tags` on load objects |
| `load_matrix_tag` | TagName | `arc_length_load_jac` | tag users put in `matrix_tags` on follower-load objects |
| `step_size` | Real | required | $\Delta s$, `-snes_newtonal_step_size` |
| `max_continuation_steps` | unsigned int | 100 | `-snes_newtonal_max_continuation_steps`; exceeding it is a failed solve |
| `lambda_max` | Real | 1.0 | `-snes_newtonal_lambda_max` |
| `lambda_min` | Real | 0.0 | `-snes_newtonal_lambda_min` |
| `psi_squared` | Real | 1.0 | $\psi^2$, `-snes_newtonal_psisq`; 0 = cylindrical |
| `correction_type` | MooseEnum `exact\|normal` | exact | `SNESNewtonALSetCorrectionType` (code default is EXACT, `al.c:708`) |

Guardrails at init: `solve_type = NEWTON` required; a user-supplied `-snes_type` is a hard error;
at least one residual object routed to the load tag; `-snes_newtonal_scale_rhs` forced false.

### U3 ArcLengthLoadParameter

`getValue()` returns the problem's cached $\lambda$. Base `GeneralPostprocessor`; default
`execute_on = 'ARCLENGTH_INCREMENT TIMESTEP_END'`.

### U4 ArcLengthHistory

`execute()` appends one row (increment index, $\lambda$, each listed postprocessor value) to
declared vectors; CSV output is the load-displacement curve. Param `postprocessors`
(`std::vector<PostprocessorName>`), sampled per increment; executes on `ARCLENGTH_INCREMENT` (locked).

**AD.** Solve-level machinery, no AD templating in the new classes. Load objects keep their own AD
or non-AD flavor; AD follower loads give an exact $\partial\mathbf{R}_{\mathrm{load}}/\partial\mathbf{u}$.

## Reuse decisions

| where | what | decision |
|---|---|---|
| `moose/petsc/src/snes/impls/al/al.c`; `petscsnes.h:1470-1500` | `SNESNEWTONAL`: complete arc-length Newton in the pinned PETSc 3.25.2 (symbols verified in `libpetsc.dylib`) | **Reuse as-is.** Wrap, do not reimplement. |
| `NonlinearEigenSystem.C:133,161,620` | The eigen A/B split: per-object tag routing, separate assembly, scalar scaling | **Reuse (pattern)** for U1's tag ownership and `postAddResidualObject` routing. |
| `TaggingInterface.C:26,61,63` | Replacing `vector_tags` / `matrix_tags` on every residual object | **Reuse as-is.** Exclusion by replacement is the mechanism. |
| `FEProblemBase.C:7604,692`; `FEProblemBase.h:1794` | `associateVectorToTag` / `computeResidualTags({tag})` / `disassociateVectorFromTag` | **Reuse as-is** for the tangent-load callback body. |
| `PetscSupport.C:623-630`; `PetscOutput.C:245-255`; `NonlinearSystem.C:269-273,371-390` | Raw-SNES mutation precedents (callbacks with a MOOSE object as ctx) | **Reuse (pattern).** |
| `libmesh/src/solvers/petsc_nonlinear_solver.C:949,954,986,1113` | Where libMesh binds callbacks and launches the solve | **Reuse as-is.** No libMesh change. |
| `LStableDirk3.C:150`; `ImplicitEuler.C:68` | Runtime-scalar combination of tagged residual vectors | **Reuse (pattern)**; documents the final combine that never sums the load tag. |
| `StressDivergenceTensorsTruss.C:91,34`; `TrussMaterial.C:88` | Truss elements: geometrically nonlinear residual, material-only tangent | **Rejected as test scaffold.** v1 needs NEWTON with an assembled tangent. |
| `GeneralizedPlaneStrain.C:48-58` | Scalar-augmented system | **No reuse.** Same shape, different operator; recorded so nobody re-investigates. |

Negative searches: path-following, Riks, Crisfield, arc-length across framework, modules, blackbear,
isopod: nothing.

## Test plan

Each requirement sentence is copied verbatim into the `requirement =` field of its tests spec block.

### arch_snapthrough (CSVDiff)

- Requirement: The system shall trace the equilibrium path of a shallow finite-strain arch under a
  dead apex load through the limit point to `lambda_max`, recording a non-monotonic $\lambda$ history.
- Asserts: gold CSV from `ArcLengthHistory`; the $(\lambda, \text{apex displacement})$ curve matches.
- Mutation: with load control instead of continuation the solve diverges at the limit point and no
  CSV row past it exists.

### bratu_source (CSVDiff)

- Requirement: The system shall apply the $\lambda$-scaled load Jacobian for a solution-dependent
  volumetric source routed to both load tags and converge along the path up to `lambda_max`.
- Asserts: Bratu problem on the unit square, `lambda_max` just below the fold ($\lambda^* \approx 6.81$);
  gold CSV of $\lambda$ per increment.
- Mutation: dropping the follower Jacobian term makes Newton fail before the fold.

### no_load_error (RunException)

- Requirement: The system shall report an error at initialization, naming the load tag, when no
  residual object is routed to the load vector tag.
- Asserts: `errors.i`, `expect_err = "ArcLengthProblem requires at least one residual object routed to the load vector tag"`.
- Mutation: without U2's check PETSc aborts later with an opaque `PetscCheck` (`al.c:261`).

### pjfnk_error (RunException)

- Requirement: The system shall report an error at initialization when `solve_type` is not NEWTON.
- Asserts: `errors.i` + `cli_args = 'Executioner/solve_type=PJFNK'`.
- Mutation: the matrix-free operator meets the untested NEWTONAL path silently.

### snes_type_override_error (RunException)

- Requirement: The system shall report an error when the user supplies `-snes_type` in
  `petsc_options_iname`, because the problem owns the SNES type.
- Mutation: the option silently replaces `newtonal` at `SNESSetFromOptions`.

### double_tag_error (RunException)

- Requirement: The system shall report an error at object registration when a load-tagged object
  also keeps the default `nontime` vector tag.
- Mutation: the load assembles at full strength in $\mathbf{F}_{\mathrm{int}}$ and $\lambda$-scaled
  in $\mathbf{Q}$: silently wrong physics.

## Doc plan

Needed: yes. Pages: `framework/doc/content/source/problems/ArcLengthProblem.md`,
`.../vectorpostprocessors/ArcLengthHistory.md`, `.../postprocessors/ArcLengthLoadParameter.md`.
Existing coverage: none.

## Out of scope

- Per-timestep continuation ("Mode B", $\lambda: 0 \to 1$ within each real time step). Future work.
- $\Delta s$ adaptivity and cutback (PETSc's implementation has a fixed step).
- Restart or recover of mid-path state; tests carry `recover = false`.
- Scaling prescribed-value Dirichlet BCs by $\lambda$ (displacement control); penalty BCs are the workaround.
- DOF-subset or per-variable weighted constraint norms.
- Native MOOSE Riks/Crisfield solver (rejected alternative).
- Branch switching, bifurcation detection, stability monitoring.
- VI solves (PETSc rejects, `al.c:332`), MFEM, eigen problems, MultiApp fixed-point interactions.
- libMesh modifications (confirmed unnecessary).

## Needs clarification

- [x] Is `Q` the full end-of-step load or the $\lambda$-scaled load? Full load; PETSc scales (`al.c:267-276`).
- [x] Does `correction_type` default to `exact` or `normal`? `exact` (`al.c:708`; the header comment is wrong).

## Work plan

```json
{
  "version": 2,
  "units": [
    { "id": "U1", "kind": "implement", "agent": "moose-implementer", "deps": [], "status": "done",
      "class": "ArcLengthNonlinearSystem", "base": "NonlinearSystem",
      "files": ["moose/framework/include/systems/ArcLengthNonlinearSystem.h",
                "moose/framework/src/systems/ArcLengthNonlinearSystem.C"] },
    { "id": "U2", "kind": "implement", "agent": "moose-implementer", "deps": ["U1"], "status": "done",
      "class": "ArcLengthProblem", "base": "FEProblem",
      "files": ["moose/framework/include/problems/ArcLengthProblem.h",
                "moose/framework/src/problems/ArcLengthProblem.C",
                "moose/framework/include/base/Moose.h",
                "moose/framework/src/base/Moose.C"] },
    { "id": "U3", "kind": "implement", "agent": "moose-implementer", "deps": ["U2"], "status": "running",
      "class": "ArcLengthLoadParameter", "base": "GeneralPostprocessor",
      "files": ["moose/framework/include/postprocessors/ArcLengthLoadParameter.h",
                "moose/framework/src/postprocessors/ArcLengthLoadParameter.C"] },
    { "id": "U4", "kind": "implement", "agent": "moose-implementer", "deps": ["U2"], "status": "running",
      "class": "ArcLengthHistory", "base": "GeneralVectorPostprocessor",
      "files": ["moose/framework/include/vectorpostprocessors/ArcLengthHistory.h",
                "moose/framework/src/vectorpostprocessors/ArcLengthHistory.C"] },
    { "id": "T1", "kind": "test", "agent": "moose-test-writer", "deps": ["U1", "U2", "U3", "U4"], "status": "idle",
      "test": "arch_snapthrough" },
    { "id": "T2", "kind": "test", "agent": "moose-test-writer", "deps": ["U1", "U2"], "status": "idle",
      "test": "no_load_error" },
    { "id": "T3", "kind": "test", "agent": "moose-test-writer", "deps": ["T2"], "status": "idle",
      "test": "pjfnk_error", "notes": "Shares errors.i and the tests spec with T2 (same-file edge)." },
    { "id": "T4", "kind": "test", "agent": "moose-test-writer", "deps": ["T2"], "status": "idle",
      "test": "snes_type_override_error", "notes": "Same-file edge with T2." },
    { "id": "T5", "kind": "test", "agent": "moose-test-writer", "deps": ["U1", "U2", "U3", "U4"], "status": "idle",
      "test": "bratu_source" },
    { "id": "T6", "kind": "test", "agent": "moose-test-writer", "deps": ["T2"], "status": "idle",
      "test": "double_tag_error", "notes": "Same-file edge with T2." },
    { "id": "D1", "kind": "doc", "agent": "moose-docs-writer", "deps": [], "status": "idle" }
  ],
  "gates": {
    "A1": { "criterion": "C1", "status": "done" },
    "B2": { "criterion": "C2/C3", "status": "idle" },
    "B3": { "criterion": "C4", "status": "idle" },
    "B4": { "criterion": "C5", "status": "idle" },
    "B5": { "criterion": "C6", "status": "idle" },
    "B6": { "criterion": "DG", "status": "idle" }
  }
}
```

## Amendments

- 2026-08-24: created from `/moose-blueprint`.
- 2026-09-12: converted to the markdown format as the reference example.
