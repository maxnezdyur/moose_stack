# Findings: ptr-depth-sensitivity

One section per finding. The heading is the claim with its number. Cite at least one run and one
measure. Never edit a section; refute it with a later one.

---
## F1. The nominal forward reproduces the paper's 1 Hz phase to 0.0021 rad rms
- date: 2026-09-19
- runs: D011
- measures: phase_rms_vs_paper_rad
- refutes: -
- closes: no

The frozen constraints reproduce the release phase along the scan line to 0.0021 rad rms, five
times below the noise floor. D011 is the baseline every shift measure subtracts.

## F2. A Cu-to-Ni step moves the 1 Hz phase by 0.084 rad at 0.5 mm and 0.031 rad at 1.0 mm
- date: 2026-09-20
- runs: D012, D013, D011
- measures: phase_shift_1hz_rad, phase_shift_10hz_rad
- refutes: -
- closes: no

The 1 Hz shift falls by a factor 2.7 per 0.5 mm, consistent with a diffusion length near 1.5 mm.
The 10 Hz shift is already at the noise floor at 1.0 mm (0.006 rad), so the 10 Hz maps say
nothing below 1 mm. Figure: `gallery/shift-vs-depth.png`. Next: bracket the 1 Hz crossing
between 1.0 and 2.0 mm.

## F3. At 2.0 mm the 1 Hz shift is 0.004 rad, below the noise floor
- date: 2026-09-22
- runs: D014, D013
- measures: phase_shift_1hz_rad
- refutes: -
- closes: no

The crossing of 0.010 rad lies between 1.0 mm (0.031) and 2.0 mm (0.004). Log-linear
interpolation puts it near 1.55 mm. D015 at 1.5 mm diverged, so the bracket is still 1.0 mm wide.
Next: rerun 1.5 mm with a looser `ksp_rtol`, then 1.25 mm.
