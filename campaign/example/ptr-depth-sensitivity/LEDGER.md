# Ledger: ptr-depth-sensitivity

One entry per run. `campaign run` writes the first line at launch. `reconcile` or `run` appends
`done`. `verdict` appends the verdict. Anyone may append `note`. No line is ever edited.

---
- D011 | nominal-baseline | - | 20260919T141502Z | local:np3 | tests: the nominal forward reproduces the paper's 1 Hz phase within 0.005 rad rms
  - done 20260919T142214Z exit=0 core-h=0.4
  - verdict supported | phase_rms_vs_paper_rad=0.0021 | F1
- D012 | layer-0.5mm | depth-sweep | 20260920T090311Z | teton:8811207 | tests: phase_shift_1hz_rad with the step at 0.5 mm is above 0.010 rad
  - done 20260920T094052Z exit=0 core-h=2.9
  - verdict supported | phase_shift_1hz_rad=0.084, phase_shift_10hz_rad=0.031 | F2
- D013 | layer-1.0mm | depth-sweep | 20260920T090318Z | teton:8811208 | tests: phase_shift_1hz_rad with the step at 1.0 mm is above 0.010 rad
  - done 20260920T094411Z exit=0 core-h=3.1
  - verdict supported | phase_shift_1hz_rad=0.031, phase_shift_10hz_rad=0.006 | F2
- D014 | layer-2.0mm | depth-sweep | 20260922T113040Z | teton:8812234 | tests: phase_shift_1hz_rad with the step at 2.0 mm is above 0.010 rad
  - done 20260922T120806Z exit=0 core-h=3.0
  - verdict refuted | phase_shift_1hz_rad=0.004, phase_shift_10hz_rad=0.001 | F3
- D015 | layer-1.5mm | depth-sweep | 20260922T113044Z | teton:8812235 | tests: phase_shift_1hz_rad with the step at 1.5 mm is above 0.010 rad
  - done 20260922T122917Z exit=1 core-h=4.7
  - verdict failed | - | -
  - note: GMRES stalled at the layer interface, DIVERGED_ITS after 2000 its; see runs/D015_layer-1.5mm/run.log; retry only with ksp_rtol=1e-10
