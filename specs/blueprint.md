---
title: Two-block thermomechanics with rows ties
feature: moosify-uel
repo: moose/modules/combined
scope: moose
object_kind: "Example input (no new C++): EqualValueBoundaryConstraint rows ties + AbaqusUMATStress"
status: built
created: 2026-10-20
---

## Summary

Turn `moosify_uel.i`, a copy of Daniel Schwen's `moosify_nnl.i` (dschwen/moose `moosify`,
a6b13f0335), into a MOOSE model of the problem in `main.pdf` (OneDrive `UEL/Reference Material/`):
two stacked 18 x 12 x 4 cm blocks, heat generated in Block A, convection and pressure on the top
face, a UMAT for the stress.

**Problem.** The input does not parse on this branch: `[Physics/SolidMechanics/GlobalStrain]`
uses `active_directions`, which only exists in Daniel's Global Strain code (no hit under
`moose/modules/solid_mechanics/src`). Global Strain also makes the two PRP directions one
homogeneous cell stretch; main.pdf Table 3 wants each PRP face to stay its own plane. The heat
source has a transcription error: the input adds the two factors of $\phi$
(`3000 - 2.9 * t - x^2 / 0.0081 + 1`) where main.pdf multiplies them. Main.pdf section 7 asks
for reaction forces at the faces, the top heat flux and the heat flux field; the input has one
reaction and no flux field. Z has no output.

**Solution.** No new C++. One `EqualValueBoundaryConstraint` with `formulation = rows` (from the
cherry-picked 00e6cc777f) on the normal displacement of each PRP face (right: `disp_x`, front:
`disp_y`); Dirichlet 0 on the symmetric faces (left, back, bottom); the Global Strain block, the
`global_strain` SCALAR variable and the right/front Dirichlet BCs go. $\phi$ follows main.pdf
section 6. Outputs: a normal reaction per face, top conductive and convective heat rate, the
time-integrated top heat loss, the heat flux vector, the full stress tensor, and Z as an aux. The
placeholder UMAT stays `elastic_incremental` until NNL delivers the viscoplastic law.

**Dependency.** The rows formulation is idaholab/moose#33820 (open), closing #33821 (open). The
PR for this branch waits for #33820 or targets `next` with #33820 named as a dependency.

**Files.** New: `moose/modules/combined/examples/thermomechanics/moosify_uel.i` (T1),
`moose/modules/combined/examples/thermomechanics/gold/moosify_uel_short.csv` (T2). Existing:
`moose/modules/combined/examples/thermomechanics/tests` (T1, T2).

## Physics

Heat (main.pdf eq. 1, 2), both blocks, source in Block A only:

$$\rho c_p \frac{\partial T}{\partial t} = \nabla\cdot(k\nabla T) + \dot q, \qquad \dot q = \begin{cases}\phi^2 & \text{Block A}\\ 0 & \text{Block B}\end{cases}$$

$$\phi(x,t) = \begin{cases}(3000 - 2.9t)\left(1 - \dfrac{x^2}{81}\right) & 0 < t \le 1000\\[4pt] 100\left(1 - \dfrac{x^2}{81}\right) & 1000 < t < t_{\mathrm{off}}\\[4pt] 0 & t \ge t_{\mathrm{off}}\end{cases}$$

Top face (convection), all other faces adiabatic:

$$-k\nabla T\cdot\mathbf n = h(t)\,\big(T - T_\infty(t)\big), \qquad h(t) = 200\sin\!\left(\frac{\pi t}{10^6}\right)$$

Mechanics, quasi-static finite strain, thermal eigenstrain $\alpha(T - 20)$:

$$\nabla\cdot\boldsymbol\sigma = \mathbf 0, \qquad \boldsymbol\sigma\cdot\mathbf n = -p(t)\,\mathbf e_z \text{ on top}, \qquad p = 10^5\ \mathrm{Pa}\ (t < 10^5),\ 0\ \text{after}$$

PRP tie, rows formulation, for every secondary node $s$ of the face and the auto-picked primary
node $p$ (one DofMap constraint row per node, no residual, no penalty,
`moose/framework/src/constraints/NodalConstraint.C:36-43`):

$$u_x^{(s)} = u_x^{(p)}\ \text{on right}, \qquad u_y^{(s)} = u_y^{(p)}\ \text{on front}$$

| symbol | meaning |
|---|---|
| $x$ | coordinate in cm in main.pdf; the mesh is in m, so $x^2/81$ is written `x^2 / 0.0081` (Q4) |
| $t_{\mathrm{off}}$ | source shut-off time, $5\times10^6$ s from the main.pdf formula (Q5) |
| $h(t)$ | film coefficient, W/m^2/K, $t$ in s (Q6) |
| $T_\infty$ | 500 C for $t < 10^5$ s, 20 C after |
| $p$ | top pressure, a compressive traction $-10^5$ Pa in $z$ (Q2) |
| $\rho, c_p, k, E, \nu, \alpha$ | main.pdf Table 2; A: 8000, 500, 80, 200 GPa, 0.30, 1e-6; B: 3000, 800, 200, 400 GPa, 0.15, 5e-6 |

Steps (`AnalysisStepUserObject`, `step_start_times = '0 500 100000'`): heat-up 0 to 500 s,
quasi-steady 500 to 1e5 s, cooling 1e5 to 1.05e5 s; `dt = 100`.

Boundary map (GeneratedMeshGenerator 3D: back = 0, bottom = 1, right = 2, top = 3, left = 4,
front = 5, `moose/framework/doc/content/source/meshgenerators/GeneratedMeshGenerator.md:12`).
In a 3D generated mesh `bottom` is $y_{\min}$ and `back` is $z_{\min}$; main.pdf Table 1 puts
Bottom at $z = -4$ and Front at $y = -6$. The input renames the sidesets to main.pdf's faces with a
`RenameBoundaryGenerator` so every BC reads as Table 3:

| main.pdf face | plane | generated name | role |
|---|---|---|---|
| Bottom | $z = -0.04$ | `back` | $u_z = 0$ |
| Top | $z = 0.04$ | `front` | pressure, convection |
| Left | $x = -0.09$ | `left` | $u_x = 0$ |
| Right | $x = 0.09$ | `right` | PRP tie on `disp_x` |
| Front | $y = -0.06$ | `bottom` | PRP tie on `disp_y` |
| Back | $y = 0.06$ | `top` | $u_y = 0$ |

The starting input uses the generated names as if they were main.pdf's: it pins `disp_z` on
`bottom` ($y_{\min}$), `disp_y` on `back` ($z_{\min}$), and puts the pressure and the convection on
`top` ($y_{\max}$). The rename fixes that; T2 asserts it through the reactions. No PRP face meets a
symmetric face that pins the same component (right/left on `disp_x`, front/back on `disp_y`), so
the auto-picked primary node is never pinned; `addTieRows` has no check for that case
(`NodalConstraint.C:396-405`).

Input shape after the change (excerpt):

```text
[Mesh]
  [faces]
    type = RenameBoundaryGenerator
    input = block_b
    old_boundary = 'back bottom top front'
    new_boundary = 'pdf_bottom pdf_front pdf_back pdf_top'
  []
[]
[Constraints]
  [right_prp]
    type = EqualValueBoundaryConstraint
    variable = disp_x
    secondary = right
    formulation = rows
  []
  [front_prp]
    type = EqualValueBoundaryConstraint
    variable = disp_y
    secondary = pdf_front
    formulation = rows
  []
[]
```

The temporary `pdf_` names avoid a merge: RenameBoundaryGenerator merges into a target name that
already exists (`moose/framework/src/meshgenerators/RenameBoundaryGenerator.C`, the
"merge with said boundary" branch), so a direct `back -> bottom` swap would join two faces. The
builder may drop the prefix in a second rename once the swap is done.

Materials: `AbaqusUMATStress` with `elastic_incremental` on both blocks (Q7), `constant_properties`
`'2e11 0.3'` (A) and `'4e11 0.15'` (B), `num_state_vars = 1` so `state_var[0]` is Z (Q8). The
placeholder never writes STATEV, so Z stays 0 until the NNL UMAT replaces the plugin. The UMAT's
RPL is not fed back into the heat equation (Q9).

Outputs:

| output | object | notes |
|---|---|---|
| normal reaction, six faces | `save_in = 'reaction_x reaction_y reaction_z'` on the Physics, one `NodalSum` per face | the discrete nodal reaction; balances the 2160 N load exactly (Q10, amended) |
| top conductive heat rate, W | `ADSideDiffusiveFluxIntegral`, `variable = temperature`, `diffusivity = thermal_conductivity` | `moose/framework/src/postprocessors/SideDiffusiveFluxIntegral.C:33-36` |
| top convective heat rate, W | `ADConvectiveHeatTransferSideIntegral` (kept) | `moose/modules/heat_transfer/src/postprocessors/ConvectiveHeatTransferSideIntegral.C:72` |
| total top heat loss, J | `TimeIntegratedPostprocessor` of the convective rate | `moose/framework/src/postprocessors/TimeIntegratedPostprocessor.C:67-73` |
| PRP flatness, right and front | `NodalExtremeValue` max and min, `DifferencePostprocessor` | spread is 0 to round-off with the tie |
| heat flux vector | three `DiffusionFluxAux` (`component = x y z`), CONSTANT MONOMIAL | `moose/framework/src/auxkernels/DiffusionFluxAux.C:22-26` (Q11) |
| stress tensor | `generate_output` adds `stress_xy stress_xz stress_yz` | main.pdf section 7 asks for $S_{ij}$ |
| Z | `MaterialStdVectorAux`, `property = state_var`, `index = 0`, CONSTANT MONOMIAL | `moose/modules/solid_mechanics/test/tests/uel/tensile_umat_moose_umat.i:55-60` |

## Reuse decisions

| where | what | decision |
|---|---|---|
| `moose/framework/src/constraints/EqualValueBoundaryConstraint.C:24-28`; `NodalConstraint.C:36-43` | Ties every node of a boundary to one primary node; `formulation = rows`, primary optional | **Reuse as-is** for both PRP faces (Q1). |
| `moose/test/tests/constraints/equal_value_boundary_constraint/tests:137-156` | The `[rows]` block on a 2D diffusion input | **Reuse (pattern)** for the spec; no 3D solid-mechanics rows input exists. |
| `moose/modules/solid_mechanics/src/materials/abaqus/AbaqusUMATStress.C:80` | `state_var` (`std::vector<Real>`), sized by `num_state_vars` | **Reuse as-is** for Z. |
| `moose/modules/solid_mechanics/test/tests/uel/tensile_umat_moose_umat.i:55-60` | `MaterialStdVectorAux` on `state_var`, `index = 0` | **Reuse (pattern)** for the Z aux. |
| `moose/modules/solid_mechanics/src/postprocessors/SidesetReaction.C:21-25,42` | Traction integral of the stress on a side | **Rejected** (amended): qp-stress traction missed the 2160 N load by up to 12x on this mesh. |
| `moose/framework/src/postprocessors/SideDiffusiveFluxIntegral.C:16,80-85`; `TimeIntegratedPostprocessor.C:24-28` | Side flux integral (AD), time integral | **Reuse as-is.** |
| `moose/framework/src/auxkernels/DiffusionFluxAux.C:35-38` | Flux component aux; picks the AD or non-AD property | **Reuse as-is** for the heat flux vector. |
| `moose/modules/combined/test/tests/umat/tests:1-4`; `gap_heat_transfer_umat.i:116-117` | UMAT test in combined: `capabilities = 'library_mode=dynamic & installation_type=in_tree'`, plugin path into solid_mechanics | **Reuse (pattern)** for the spec. |
| Daniel's `[Physics/SolidMechanics/GlobalStrain]` with `active_directions` (a6b13f0335) | Homogeneous stretch of the PRP directions | **Rejected.** His code stays off this branch; the rows tie keeps each face its own plane. |
| `moose/framework/src/auxkernels/MaterialStdVectorAux.C:36` | `size() >= _index` is off by one: index 0 on an empty vector reads out of bounds | **No reuse** of `num_state_vars = 0` with a Z aux; follow-up fix out of scope. |

Negative searches: a 3D solid-mechanics input with `formulation = rows` on a displacement
(`moose/modules`, `moose/test/tests`): none. `save_in` on constraints: none; `save_in` on the stress
divergence kernels gives the nodal reaction on every face, tied faces included. A use of the UMAT's RPL in `AbaqusUMATStress`: none past the call
(`AbaqusUMATStress.C:352`).

## Test plan

The spec blocks go in `moose/modules/combined/examples/thermomechanics/tests` under one parent
carrying `issues = '#33821'` and `design = 'source/constraints/EqualValueBoundaryConstraint.md
source/materials/abaqus/AbaqusUMATStress.md'`, and
`capabilities = 'library_mode=dynamic & installation_type=in_tree'`, `valgrind = NONE`.

### moosify_uel_check (RunApp)

- Requirement: The system shall provide a coupled thermomechanical two-block example in which a
  UMAT computes the stress and degree of freedom constraint rows keep each plane-remains-plane face
  planar.
- Asserts: `check_input = True` constructs every object, the UMAT plugin load and both rows ties
  included; the old input fails here on `active_directions`.
- Mutation: restoring the Global Strain block fails the parse on this branch.

### moosify_uel_prp_tie (CSVDiff)

- Requirement: The system shall keep the normal displacement of each plane-remains-plane face of
  the two-block example uniform while the heat source ramps up.
- Asserts: `cli_args = 'Executioner/end_time=1000 Executioner/dt=250 Outputs/file_base=moosify_uel_short'`,
  four steps across the 500 s step boundary; gold `moosify_uel_short.csv`; the `right_spread` and
  `front_spread` columns are 0 (abs_zero 1e-12); the nodal reactions balance the applied load: top
  $-10^5 \times 0.18 \times 0.12 = -2160$ N, bottom $+2160$ N; the top conductive and convective rates match.
- Mutation: `Constraints/right_prp/enable=false` gives a nonzero `right_spread` (thermal bulge of
  Block A), and a face map error moves the top reaction off -2160 N.

## Doc plan

Needed: no. The input carries a header comment that maps main.pdf's faces to the sidesets and
names the placeholder UMAT. Existing coverage:
`moose/framework/doc/content/source/constraints/EqualValueBoundaryConstraint.md` (the rows
formulation, from 00e6cc777f) and
`moose/modules/solid_mechanics/doc/content/source/materials/abaqus/AbaqusUMATStress.md` (Q14).

## Showcase

Example: `moose/modules/combined/examples/thermomechanics/moosify_uel.i`

- `prp_spread_rows_vs_penalty.png`: the right-face `disp_x` spread against time for the rows tie
  and a penalty tie (`formulation = penalty`, `penalty = 1e14`), with nonlinear iterations per step
  below; proves the rows tie holds the plane exactly at no Newton cost.
- `deformed_temperature_t1000.png`: the deformed block at $t = 1000$ s (displacement x 1000),
  colored by temperature; proves the right and front faces stay planes while Block A bulges.

## Out of scope

- Daniel's Global Strain changes (active directions, global strain in the strain calculators) and
  his `elastic.i` plugin change; the "nnl" names.
- The NNL viscoplastic UMAT and its Z evolution law; `elastic_incremental` stays the placeholder.
- Feeding the UMAT's mechanical dissipation (RPL) into the heat equation (needs C++).
- The off-by-one bounds check in `MaterialStdVectorAux::getRealValue` (follow-up issue).
- A temperature-dependent film coefficient $h(T)$; main.pdf uses $h(t)$ only.
- A MooseDocs example page.
- Running the full 1.05e5 s in the test suite; only the showcase runs it.

## Needs clarification

- [x] Q1 · Which object ties each PRP face? — Reuse EqualValueBoundaryConstraint with formulation = rows, as-is
- [x] Q2 · Which sign does the top pressure take? — Compressive: traction -1e5 Pa in z, as main.pdf's prose says
- [x] Q3 · Which figures must the showcase render? — prp_spread_rows_vs_penalty.png and deformed_temperature_t1000.png
- [x] Q4 · Does x^2/81 assume x in cm? — Yes: mesh in m, expression x^2 / 0.0081
- [x] Q5 · When does the heat source shut off? — At 5e6 s, the main.pdf formula: on for the whole run
- [x] Q6 · What time scale does h(t) use? — Literal: 200 sin(pi t / 1e6), t in s
- [x] Q7 · Which constitutive model does Block B use? — The UMAT on both blocks, as main.pdf section 4 says
- [x] Q8 · How does Z get an aux before the NNL UMAT exists? — num_state_vars = 1 and a MaterialStdVectorAux on state_var[0]
- [x] Q9 · Does mechanical dissipation feed back into the heat equation? — No: eq. 1 has only phi^2
- [x] Q10 · How are the face reactions computed? — save_in + NodalSum on all six faces (amended 2026-10-20 from SidesetReaction, see Amendments)
- [x] Q11 · Does the input output the heat flux vector field? — Yes: three DiffusionFluxAux components
- [x] Q12 · How is the example tested? — check_input plus a short CSVDiff run that asserts the PRP spread
- [x] Q13 · Which issue goes in the spec and the PR? — #33821
- [x] Q14 · Does the example get a MooseDocs page? — No: a header comment in the input

## Work plan

```json
{
  "version": 2,
  "units": [
    { "id": "T1", "kind": "test", "agent": "moose-test-writer", "deps": [], "status": "done",
      "test": "moosify_uel_check",
      "notes": "Rewrites moosify_uel.i per the Physics section (face rename, rows ties, phi product, UMAT on both blocks, outputs) and adds the parent spec block plus this child.",
      "files": ["moose/modules/combined/examples/thermomechanics/moosify_uel.i",
                "moose/modules/combined/examples/thermomechanics/tests"] },
    { "id": "T2", "kind": "test", "agent": "moose-test-writer", "deps": ["T1"], "status": "done",
      "test": "moosify_uel_prp_tie",
      "notes": "Same-file edge with T1 (tests). Gold captured by moose-test-runner.",
      "files": ["moose/modules/combined/examples/thermomechanics/tests",
                "moose/modules/combined/examples/thermomechanics/gold/moosify_uel_short.csv"] },
    { "id": "S1", "kind": "showcase", "agent": "moose-figure", "deps": ["T1"], "status": "done",
      "example": "moose/modules/combined/examples/thermomechanics/moosify_uel.i",
      "files": ["specs/gallery/prp_spread_rows_vs_penalty.png",
                "specs/gallery/deformed_temperature_t1000.png"] }
  ],
  "gates": {
    "A1": { "criterion": "C1", "status": "done" },
    "B2": { "criterion": "C2/C3", "status": "done" },
    "B3": { "criterion": "C4", "status": "done" },
    "B4": { "criterion": "C5", "status": "done" },
    "B5": { "criterion": "C6", "status": "done" },
    "B6": { "criterion": "DG", "status": "done" }
  }
}
```

## Amendments

- 2026-10-20: created by `/moose-blueprint --unattended` from `specs/scope.md`, main.pdf and three
  scout rounds; 14 decisions, all open.
- 2026-10-20: the user accepted every proposed answer in chat (14 kept, 0 changed, 0 not opened); no comments. Status set to approved.
- 2026-10-20: build. The `moosify_uel_prp_tie` Asserts line drops "the top reaction is near -2160 N":
  SidesetReaction integrates the qp stress, which differs from the applied load on this mesh
  (27124 to -6740 N; one uniform refinement shrinks the error about 4x). The gold records the
  reactions; the spreads are the assertion. Figure 2 magnifies x1e5, not x1000 (max displacement
  2.0e-7 m at t = 1000 s).
- 2026-10-20: review moosify-uel (specs/review-moosify-uel.md): 3 findings, 1 applied (the abs_zero
  reason in tests), 2 held (deleting the moosify_uel.i header and the phi comments would undo Q13).
- 2026-10-20: reactions. SidesetReaction integrates qp stress and missed the 2160 N load by up to
  12x on this mesh (4x less per refinement). The nodal residual (save_in + NodalSum) balances it
  exactly: bottom +2160 N, top -2160 N, tied and symmetric faces below 0.21 N. The user asked for the
  fix; the six reactions are now NodalSum, the gold is recaptured, and the CSVDiff again asserts the
  load balance. A pressure moved off the top face and a disabled right tie both fail the CSVDiff. The
  abs_zero comment no longer mentions penalty.
