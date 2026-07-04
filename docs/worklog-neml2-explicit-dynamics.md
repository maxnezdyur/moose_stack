# Worklog: NEML2 explicit dynamics — verification, validation, calibration, element technology

Session 2026-07-01 → 2026-07-03 (Claude session 01CCuKo2gP6Duy91irEj5f1y).
Branches: moose `exp-dyn` @ ee98fc112d, marlin `slug_runs` @ b7aec04, meta-repo `exp-dyn`.
43 commits; every one carries the session trailer for provenance.

## 1. WCCM method-section deck (marlin: bc1e9fb..6c88aeb, 10 commits)

Native-PowerPoint 15-slide method section on the INL 2022 hex template via a
python-pptx builder (`examples/impact/slide_assets/deck_build/`): LaTeX-rendered
transparent-PNG equations (one per file, reusable), ParaView-style pyvista 3D
result renders, log-scale error ladder replaced by a words-and-numbers
verification slide, footer wordmark fixed by rel swap. Author names on slide 1
remain placeholders.

## 2. NEML2 nodal-force path: capability extensions (moose)

- bfe8b2ea6e — axisymmetric (RZ) support: `NEML2SmallStrainRZ` (hoop strain
  u_r/r from cached quadrature radii) + `NEML2StressDivergenceRZ` (hoop term
  psi*sigma_tt/r); machine-precision vs native RZ kernels.
- 94ec574fb1 — old-time gathering fix: conventional TIME gatherers returned
  t == t~1 under explicit rewind (NaN in rate models); old time is now t - dt.
- 0118a863e2 / b5a421a04c — total-Lagrangian support, Cartesian + RZ:
  `NEML2DeformationGradient(RZ)` (F = I + grad_0 u, hoop stretch 1 + u_r/r) and
  full-stress (PK1/R2) dispatch in the stress-divergence kernels.
- c528214a32 — `NEML2CentralDifference` silently discarded NodalKernels (empty
  algebraic node range) + range-lifetime bug; node loop kept when NodalKernels
  are active.
- 800a3af72e — `identity_seeded_state`: manage_state_advance history seeding
  for multiplicative state (Fp = I; zero is singular).
- 4e369560ad — F-bar volumetric correction for the batched path
  (`stabilize_strain` on the deformation-gradient gatherer): two batched
  reductions against cached JxW*coord weights; kernels' own flag is
  Jacobian-only, so explicit needs only the strain side.
- 3d75bf02ee — port of `HourglassCorrectionQuad4` + test suite from
  dschwen/hourglass_correction_29852 (co-authored; two API-drift fixes; WIP
  beam test parked).
- beb36261c8 — reduced integration for the batched path: `NEML2HourglassCorrection`
  (batched LS-affine Flanagan-Belytschko control, QUAD4/RZ/HEX8) on new
  `NEML2FEInterpolation` primitives (nodal values, node coordinates), plus
  `HourglassCorrectionHex8` (per-element 3D kernel, formula-identical).
  Scheduling lesson recorded: residual-adding UOs must be post-kernels.
- ee98fc112d — regular-MOOSE HEX8 reduced-integration suite: analytic mode
  norms (sqrt(128), 12 digits), rotated-affine zero residual, finite-strain
  Lagrangian explicit dynamics test.

## 3. Verification suite: machine-precision matched pairs (marlin tests)

Pattern throughout: the same NEML2 model through (a) the advance-state
nodal-force path and (b) the conventional material-property coupling with the
Lagrangian kernel system; shared gold, custom exodiff floors.

- a655c3f / 1207ea8 / aefe50c / 562f9b6 / 82ed8b0 — thermo-mechanical RZ chain
  (adiabatic dT formulation): beta=0 equivalence bit-identical, forward-Euler
  heating identity to 8e-15, cross-path agreement 1e-13..1e-15 at 136 K rise.
- e396114 — total-Lagrangian Johnson-Cook pair (additive GL chain):
  disp 1e-15 / force 4e-13 relative; large kinematics shifts the solution
  4-12% of peak, so the pair discriminates.
- 5ce46f4 — multiplicative Fe*Fp Johnson-Cook pair (Simo-style return map,
  Fp = (I + dEp)Fp_n): disp 5e-15 / force 4e-13 across two different Fp
  initialization mechanisms. Composition pitfalls documented (ComposedModel
  hides internally-consumed variables; Newton tolerances at the yield kink).
- 9aab8be / 1ab3b2e — F-bar matched pair: 2e-14/8e-13 relative, F-bar moves
  the solution 10% of peak (the batched path was genuinely locking).
- moose explicit_dynamics suite: hourglass matched pairs RZ + HEX8 at
  1e-16/1e-17 relative (in beb36261c8).

## 4. Contact and regularization (marlin)

- 08f8594 — `PenaltyRigidWallNodalKernel`: node-wise one-sided rigid wall.
  Sideset-traction contact alone lets the crushed first element row collapse
  and the mesh fold through the anvil plane (14 mm penetration). Bounce test:
  restitution 1.000.
- d4cb46c — `RigidWallCoulombFrictionNodalKernel`: regularized Coulomb anvil
  friction. Frictionless contact lets the near-melt foot layer extrude
  radially without bound (element edges 476 -> 11 um, CFL death at ~44 us).
  Slip velocity needs dofValuesOlder() under explicit central difference.
- a044cf4 — `max_homologous_temperature` on JohnsonCookFlowRate: T* cap 0.95
  keeps a ~20 MPa flow-stress floor near melt; regularizes the adiabatic
  heat-soften-strain runaway (the stand-in for element erosion).

## 5. CuH04_235.9 validation campaign (marlin: cccd286, df53a0a, 76a4cf2, 7733edb)

Full-scale RZ Taylor impact (O 0.3 in x 1.5 in full-hard Cu, 235.9 m/s,
run-to-rebound, dt 5e-9) against the experimental scan CuH04_235.9.stl.

- Additive GL/SVK chain: documented negative result — SVK compression
  pathology pancakes the foot (length -51%, foot -49%); motivated the
  multiplicative model (literature: SVK loses ellipticity in compression).
- Scan QA (7733edb): per-slice Kasa circle fits revealed the specimen is
  slightly bent/tilted in the scan frame (0.36 mm axis wander; apparent
  4.15 mm rear radius is really 3.91) and truncated by an end cap
  (volume audit: 15 mm^3 = 0.32 mm of bar; true length ~22.40 mm).
- Calibration sweep (df53a0a): 11 Simo-Hughes runs, one-at-a-time then
  combined. Calibrated set: A/B x0.90 of literature, n 0.30, initial plastic
  strain 0.25, anvil friction mu 0.2. Result vs corrected scan: length +0.5%,
  foot in the 8.6-8.9 band, rear -2.6%, volume closure +0.4%, profile RMS
  0.17 mm. Cross-code: NEML2 vs native Simo-Hughes agree to 0.04 mm.
  Stability envelope mapped: strength < ~0.85x or mu < ~0.1 tips into the
  adiabatic-extrusion runaway at this dt.

## 6. Bayesian calibration infrastructure

- specs/bayesian-jc-calibration.md (meta a6b5d9c) — objective function
  (heteroscedastic profile likelihood from scan QA + volume-corrected length +
  foot radius, marginalized discrepancy jitter), PCA-GP emulator + emcee,
  active-learning campaign, verification gates G0-G3, literature grounding
  (Rivera 2022, Walters 2018, Ojal 2022).
- marlin/python/taylor_cal (97bdd40) — M1-M3 implemented and gated:
  scan_qa reproduces the CuH04 audit to the digit; forward/ledger ingests all
  16 existing runs with correct blowup/marginal classification; PCA-GP + emcee
  passes the G0-lite synthetic-recovery gate (95% coverage, 3/4 dims
  contracted). Next milestone is compute: 96-run Sobol DOE.

## 7. Element technology study (b7aec04 + bracket runs)

Reduced integration (1 qp, hourglass control, no F-bar) vs full integration
(4 qp, F-bar) on the calibrated CuH04 run:

| | full + F-bar | reduced + hourglass |
|---|---|---|
| final length | 22.517 mm | 22.502 mm |
| foot radius | 8.838 mm | 8.870 mm |
| profile RMS vs scan | 0.170 mm | 0.174 mm |
| arrest | 102.5 us | 102.6 us |
| step cost | 0.13 s | 0.05 s (2.6x) |

Scheme-vs-scheme profile difference: 9 um RMS / 40 um max. Hourglass penalty
sensitivity over 0.025 / 0.05 / 0.1 (4x range): profiles identical to 0.1 um —
the coefficient is a non-knob at this severity. Localized extremes (peak dT
339 vs 629 K at the rim corner) differ by quadrature sampling only.
Reduced integration is the recommended production configuration for the
batched path, including the calibration DOE.

## Open items

- Slide 1 author names/session/date placeholders.
- Bayesian campaign M4+: Round-0 DOE (96 runs, ~2.5 days local or one HPC
  array), single-shot posterior (expect A-B-n degeneracy per literature),
  multi-shot as new scans arrive. Consider switching the DOE forward model to
  the reduced-integration variant (2.6x cheaper).
- Specimen records worth checking: pre-test diameter/length of shot
  CuH04_235.9_003 (the scan's 3.91 mm rear vs nominal 3.81 suggests either
  2.7% rear swelling or a diameter tolerance question).
- Upstream candidates (idaholab): the explicit old-time fix (94ec574fb1), the
  NodalKernel range fix (c528214a32), F-bar and hourglass for the batched path.
