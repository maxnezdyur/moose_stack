---
id: ptr-depth-sensitivity
project: ptr-update
title: PTR depth sensitivity of the 1 Hz and 10 Hz scans
question: How deep below the scanned surface can a conductivity step still move the measured phase above the camera noise floor?
stop: >
  A finding states the depth at which phase_shift_1hz_rad for a Cu-to-Ni step falls below
  0.010 rad, with one run above that depth and one below it, both within 0.5 mm of it.
budget:
  core_hours: 60
  wall_days: 14
  max_runs: 30
cluster: teton
app: isopod
autonomy: propose-only
status: active
created: 2026-09-18
updated: 2026-09-24
---
# Campaign: PTR depth sensitivity of the 1 Hz and 10 Hz scans

## Hypothesis

The 1 Hz scan carries depth information to about 1.5 mm in copper, the thermal diffusion length
at that frequency, and the 10 Hz scan to about 0.5 mm. Below the diffusion length a k step
moves the surface phase by less than the 0.010 rad noise floor measured on the 260520 scan, so
the inversion cannot see it. The October experiment should place the buried interface no deeper
than the depth this campaign finds.

## Constraints

| knob | value | why |
|---|---|---|
| physics | `forward_and_adjoint_3dfrs7_tri.i`, 3-D complex pair | the paper model |
| mesh | `tri3d_slices.e`, `uniform_refine=0` | the paper mesh; refinement is a different question |
| beam | σ = 25 µm, `std_excitation_inv=2.5e-5` | the manuscript's measured value |
| frequencies | 1 Hz and 10 Hz, the clean 14 scan offsets | what the camera measured |
| solver | `ksp_type=gmres pc_type=asm ksp_rtol=1e-12 ksp_atol=1e-13 ksp_max_it=2000` | the D69 recipe |
| ranks | NP = 3, `OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1` | the D69 recipe |
| k levels | Cu 446, Ni 81 W/m·K | the release result, not the handbook |

Out of scope:
- Inversion runs. This campaign is forward only; sensitivity is measured on synthetic phase.
- Lateral (x, y) resolution. One question at a time.

## Measures

| name | unit | how | added |
|---|---|---|---|
| phase_rms_vs_paper_rad | rad | `python scripts/phase_rms.py {outputs}` against `release_13x13/provenance/paper_phase_1hz.csv` | 2026-09-18 |
| phase_shift_1hz_rad | rad | `python scripts/phase_shift.py --freq 1 --baseline D011 {outputs}`, max over the scan line | 2026-09-18 |
| phase_shift_10hz_rad | rad | `python scripts/phase_shift.py --freq 10 --baseline D011 {outputs}`, max over the scan line | 2026-09-18 |

## Proposed

- [x] D016 layer-1.5mm-rtol10 | depth-sweep | 3 core-h | tests: phase_shift_1hz_rad with the step at 1.5 mm is above 0.010 rad | because: F3, D015
  - cwd: PTR/release_13x13/inverse_simulation
  - cmd: mpiexec -np 3 ../../../isopod/isopod-opt -w -i truth_layer.i layer_depth_mm=1.5 ksp_rtol=1e-10 tag=layer-1.5mm-rtol10
  - in: PTR/release_13x13/inverse_simulation/tri3d_slices.e
- [ ] D017 layer-1.25mm | depth-sweep | 3 core-h | tests: phase_shift_1hz_rad with the step at 1.25 mm is above 0.010 rad | because: F3
  - cwd: PTR/release_13x13/inverse_simulation
  - cmd: mpiexec -np 3 ../../../isopod/isopod-opt -w -i truth_layer.i layer_depth_mm=1.25 tag=layer-1.25mm
  - in: PTR/release_13x13/inverse_simulation/tri3d_slices.e
