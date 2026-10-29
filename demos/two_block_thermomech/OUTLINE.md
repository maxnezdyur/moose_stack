# MOOSE in place of Abaqus: the two-block demo

Outline for the group that uses the UEL/UMAT work. The demo is `main.pdf` ("Thermomechanical analysis of a two-material block in Abaqus/CAE"), run end to end in MOOSE.

## 1. The message

- MOOSE runs every part of `main.pdf` with your compiled UMAT, without changes to the UMAT.
- Most of the model runs on MOOSE `devel` today. One part needs the open PRs: the exact plane-remains-plane (PRP) constraint.
- The demo input is one file, `two_block.i`, with about 500 lines. It reads like an Abaqus deck: one block per keyword.

## 2. The problem (one slide, Figure 1 of the PDF)

- Two blocks of 18 x 12 x 4 cm, stacked and fully bonded. Block A is at the bottom and generates heat; block B is on top.
- Coupled temperature-displacement: ux, uy, uz and T in one Newton solve. State variable Z goes in and out of the UMAT.
- Three steps: ramp (0-500 s), quasi-steady creep (500 s-1e5 s), cooling (1e5-1.05e5 s).

## 3. Abaqus keyword to MOOSE block (the main slide)

| Abaqus | MOOSE in `two_block.i` | Status |
|---|---|---|
| `*User Material` (UMAT) | `AbaqusUMATStress`, one block per section, same plugin, different PROPS | devel |
| `*Depvar` (STATEV, Z) | `num_state_vars = 1`; output as `Z` with `MaterialStdVectorAux` | devel |
| `*Field` / UHFIELD (phi) | `ParsedFunction` -> `FunctionAux`, into the UMAT as `PREDEF(1)` through `external_fields` | devel |
| `*Coupled Temperature-Displacement` | `[Physics/SolidMechanics/QuasiStatic]` with `temperature = T`, plus the heat conduction kernels | devel |
| NLGEOM=YES | `strain = FINITE`; the UMAT gets DFGRD0, DFGRD1 and DROT | devel |
| HETVAL / DFLUX (q = phi^2 in A) | `HeatSource` with `block = A` | devel |
| `*Film` / FILM, h(t) and T_inf(t) | `ConvectiveFluxFunction` | devel |
| `*Dsload` pressure p(t) | `Pressure` with a function | devel |
| Symmetry BCs | `DirichletBC` | devel |
| Partitioned part (shared mesh) | `SubdomainBoundingBoxGenerator`: two blocks, one mesh | devel |
| `*Tie` (separate parts) | `EqualValueBoundaryConstraint`, `formulation = exact` | #34249 |
| PRP (`*Equation` on a face) | `EqualValueBoundaryConstraint`, `formulation = exact` | #34249 |
| `*Step` x 3 | `AnalysisStepUserObject` (lands on each step time) + `FunctionDT` (dt per step) | devel |
| Field output U, S, NT, HFL | Exodus: `disp_*`, `stress_*`, `T`, `heat_flux_*` | devel |
| History output RF per face | Nodal reactions from tagged residuals (`TagVectorAux` + `NodalSum`) | devel |
| Total heat flux on top face | `SideDiffusiveFluxIntegral` | devel |

## 4. Live demo (about 10 minutes)

1. Show `two_block.i` beside Table 3 of the PDF. Point at the `[BCs]` and `[Constraints]` blocks.
2. Show the UMAT. It is a standard Fortran UMAT with the Abaqus argument list. `build_umat.sh` compiles it. Nothing in it knows about MOOSE.
3. Run it: `run_all.sh 4`. The run takes 221 steps in about 7 min on 6 laptop cores, with 2-4 Newton iterations per step and no cutbacks.
4. Show the results in ParaView or in the browser viewer:
   - T in block A and block B over time: the heat-up, the steady state, the cooling.
   - stress_xx at the interface: the CTE mismatch (B has 5 times the CTE of A) and the stiffness mismatch.
   - Z grows in Step 2 (creep), and the stresses relax.
   - The deformed shape: the Right and Front faces stay plane.
5. Show the CSV: Rz on the Bottom face equals p x A = 2160 N while the pressure is on, and drops to zero in Step 3.

## 5. Results from the demo run (exact PRP, stand-in UMAT)

![Thermal history](figs/fig_history_thermal.png)

| | End of Step 1 (500 s) | End of Step 2 (100,000 s) | End of Step 3 (105,000 s) |
|---|---|---|---|
| Max T, block A [C] | 252 | 504 | 166 |
| Max T, block B [C] | 242 | 504 | 165 |
| Mean stress_xx at the interface [MPa] | 152 | 4 | -203 |
| Max von Mises [MPa] | 157 | 4 | 203 |
| Rz on the Bottom face [N] | 2163 | 2168 | 0 |
| Max Z [-] | 2.0e-5 | 2.6e-3 | 3.0e-3 |
| PRP spread on Right and Front [m] | 0 | 0 | 0 |

- Rz on the Bottom face is p x A = 1e5 Pa x 0.0216 m2 = 2160 N while the pressure is on. It is zero after the pressure is removed in Step 3. The force balance holds.
- Early on, h(t) is small, so the top face is almost adiabatic and block A heats up. Later, h(t) grows, and the film at T_inf = 500 C heats the block. The heat flux out of the top face becomes negative.
- In Step 2 the thermal stress relaxes by creep, and Z grows. In Step 3 the cooling gives a reversed stress (-203 MPa).
- In Step 3, T_inf drops to 20 C while h(t) is near 62 W/m2K. The cooling time constant of the block is about 4,100 s, so T falls from 504 C to 166 C in 5,000 s. A lumped estimate gives 160 C.
- After Step 1 the heat source is small: phi = 100 gives about 9 W for all of block A. In Steps 2 and 3 the film drives the temperature.
- These numbers come from the stand-in UMAT. With your UMAT they become the comparison points against Abaqus.

## 6. What the open PRs add beyond this problem

- idaholab/moose#29382: Abaqus `.inp` input and `*User Element` (UEL). Includes UEL state variables, UEL energy and PNEWDT.
- idaholab/moose#33820: `RBE2Constraint` (rigid) and `RBE3Constraint` (distributing). These are exact multipoint constraints.
- idaholab/moose#34249: `formulation = exact` for `LinearNodalConstraint`, `EqualValueBoundaryConstraint` and `EqualValueEmbeddedConstraint`. These give `*Equation`, `*Tie` and PRP.
- idaholab/moose#34250: `InclinedNoDisplacementConstraint`, an exact roller on a skewed support.
- idaholab/moose#33778 and #33780: modal output. Every mode is a step, and the output gives the frequency in Hz.
- idaholab/moose#33524: arc-length continuation (Riks).

## 7. What MOOSE adds beyond Abaqus

- Open source. No license queue, and it runs on INL HPC with thousands of cores.
- One input file is the full model, and it is easy to keep under version control.
- It couples to other MOOSE physics and apps (BlackBear, NEML2, optimization) in the same solve.
- Mesh adaptivity, and automatic differentiation for MOOSE-native materials.

## 8. Known gaps (be honest)

- `AbaqusUMATStress` always sends `KSTEP = 1`. It sends the step time correctly in `TIME(1)`. A UMAT that branches on `KSTEP` needs a small MOOSE change. This change is a good first follow-up PR.
- The demo UMAT is a stand-in visco-elastic model (Z = accumulated viscous strain). The PDF gives no viscosity, so its values are placeholders.
- Turn off automatic scaling when you use the nodal reaction forces. Scaling changes the tagged residual.

## 9. Questions for the group

- Can we have your UMAT and an Abaqus result for this problem (T, S, RF at the end of each step)? We will do a side-by-side comparison.
- Does your UMAT read `KSTEP`?
- What is the initial temperature? The demo uses 20 C.
- Does phi go to zero at 1e5 s (Step 3 text) or at 5e6 s (the phi formula)? The demo uses 1e5 s.
- Table 3 gives Fz = -p with p = -1e5 Pa. Is the load compressive? The demo applies 1e5 Pa compression.
- Do you use the `.inp`/UEL path (#29382), or do you write MOOSE inputs?

## 10. Next steps

1. Get their UMAT and their Abaqus results, and run the comparison.
2. Open a PR so that `AbaqusUMATStress` sends the step number from `AnalysisStepUserObject` as KSTEP.
3. Merge #33820 and #34249. Then the PRP and tie features are on `devel`.
