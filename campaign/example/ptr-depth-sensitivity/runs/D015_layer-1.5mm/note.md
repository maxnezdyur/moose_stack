# D015 layer-1.5mm

Tested: a Cu-to-Ni step at 1.5 mm moves the 1 Hz phase above the 0.010 rad floor.
Showed: nothing. GMRES stalled at the layer interface and hit `ksp_max_it=2000` with
DIVERGED_ITS on the 1 Hz solve; exit 1 after 4.7 core-h. Failed. The Do-not-repeat line in
`handoff.md` records the retry condition; D016 is the retry with `ksp_rtol=1e-10`.
