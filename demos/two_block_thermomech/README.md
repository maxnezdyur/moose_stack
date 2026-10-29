# Two-block thermomechanical demo

This demo is the problem in `main.pdf` ("Thermomechanical analysis of a two-material block in Abaqus/CAE"), solved in MOOSE.

## Contents

| File | Purpose |
|---|---|
| `two_block.i` | The MOOSE input. |
| `umat/two_block_umat.f` | A stand-in UMAT. Replace it with the group's UMAT. |
| `two_block_uel.i` | The same problem through a coupled temperature-displacement UEL. |
| `uel/two_block_uel.f90` | The stand-in UEL: HEX8 with ux, uy, uz and T per node. |
| `run_uel.sh` | Runs the UEL model and the small-strain UMAT model it is compared with. |
| `build_umat.sh` | Compiles a UMAT into the plugin that `AbaqusUMATStress` loads. |
| `run_all.sh` | Runs the demo. |
| `make_figs.py` | Builds the stills with figkit (inl-deckkit). |
| `plot_history.py` | Plots the history of the main results from the CSV files. |
| `OUTLINE.md` | The presentation outline for the group. |

## Procedure

1. Build `combined-opt` on a `moose` branch that has idaholab/moose#33820 and #34249.
2. Compile the UMAT:

   ```bash
   scripts/conda-run.sh -C moose -- demos/two_block_thermomech/build_umat.sh
   ```

3. Run the demo on 4 processes:

   ```bash
   scripts/conda-run.sh -C moose -- demos/two_block_thermomech/run_all.sh 4
   ```

4. Plot the results:

   ```bash
   python3 demos/two_block_thermomech/plot_history.py
   ```

To use a different UMAT, compile it with `build_umat.sh <file.f>`. Then set `plugin` and `constant_properties` in the two `AbaqusUMATStress` blocks.

## Model

- Units are SI (m, s, Pa, W, K) and temperature is in degrees C. The formula for phi uses x in cm, so the input uses `100 x`.
- The mesh is one 18 x 12 x 8 cm box with 1 cm elements (18 x 12 x 16 HEX8). Block A is z < 0 and block B is z > 0. The two blocks share nodes, so the interface is fully bonded.
- The face names come from Table 1 of the PDF: `Bottom`, `Top`, `Left`, `Right`, `Front`, `Back`. The input also adds an `Interface` side set.
- The unknowns are `disp_x`, `disp_y`, `disp_z` and `T`. The solver solves them together in one Newton solve. Z is `STATEV(1)` of the UMAT. MOOSE stores Z between time steps.
- phi is an auxiliary variable. It goes to the UMAT as `PREDEF(1)`. It also drives the heat source phi^2 in block A only.
- Symmetric faces use `DirichletBC`. PRP on `Right` and `Front` uses `EqualValueBoundaryConstraint`. The constraint uses `formulation = exact` (idaholab/moose#34249).
- The top face has a `Pressure` p(t) and a `ConvectiveFluxFunction` h(t) (T - T_inf(t)). All other faces are adiabatic.
- An `AnalysisStepUserObject` holds the three steps (0, 500, 1e5 s) and makes the solver land on each step boundary.
- Each load switches at `t <= t_step`. The solve is implicit, so the last increment of a step must still see the loads of that step.

## UEL model

- `two_block_uel.i` runs the problem through `AbaqusUserElement` (idaholab/moose#29382), one per block with different PROPS.
- The UEL computes the internal force, the heat capacity, the conduction, the heat source and the full 32 x 32 element Jacobian.
- MOOSE adds the face loads, the symmetry BCs, the exact PRP constraints and the steps, as in `two_block.i`.
- Compile the UEL with `build_umat.sh uel/two_block_uel.f90`.
- `AbaqusUserElement` zeroes its external fields before every residual, so `phi` is recomputed on every linear and nonlinear evaluation.
- The UEL is small strain. `run_uel.sh` therefore runs `two_block.i` with `strain = SMALL` for the comparison.

## Assumptions to confirm with the group

- The UMAT is a stand-in: a Maxwell visco-elastic solid with thermal expansion. Z is the accumulated viscous strain, and Z makes the material stiffer to creep. The PDF gives no viscosity, so the values in the input are placeholders.
- The PDF gives no initial temperature. The input starts at 20 C.
- p is applied as a compressive pressure of 1e5 Pa. Table 3 gives Fz = -p with p = -1e5, which is a tensile load if read literally.
- phi is set to zero at t = 1e5 s, as the Step 3 text says. The phi formula says 5e6 s, which the analysis never reaches. To use the formula, set `phi_off_time=5e6` on the command line.
- The Bottom, Left and Back faces are symmetric (zero normal displacement), so they already stay plane. The PRP constraint goes only on Right and Front.
- `AbaqusUMATStress` sends `KSTEP = 1` for every step. It sends the step time in `TIME(1)`. A UMAT that branches on `KSTEP` needs a small MOOSE change.

## Outputs

- Exodus: `disp_*`, `T`, all six stress components, `vonmises_stress`, `Z`, `phi`, the heat flux vector (`heat_flux_*`) and the nodal reaction forces (`rf_*`).
- CSV: the temperatures, the reaction force on each face, the total heat flux out of the top face, the interface stresses, the maximum Z, and the PRP check (`prp_*_spread`).
- `*_center_line_*.csv`: T, stress_xx and stress_zz through the thickness at the end of the run.
