# Bayesian calibration of Johnson-Cook constants from Taylor-impact scans

Status: PLAN (2026-07-03). Forward model, contact treatment, F-bar stabilization, and
scan-processing machinery are built and validated (marlin `slug_runs` @ 7733edb,
moose `exp-dyn` @ 4e369560ad). This spec covers the objective function, the
Python Bayesian-inference stack, and the campaign design for calibrating against
N scanned specimens.

## 1. Goal

Given a set of scanned post-test Taylor specimens `<ID>_<velocity>.stl` (currently
one: CuH04_235.9; more incoming), infer a posterior distribution over Johnson-Cook
constants (+ anvil friction as a nuisance) for the marlin/NEML2 multiplicative
finite-strain model, using full deformed-profile data. Deliverables: posterior
samples with diagnostics, posterior-predictive profile overlays per shot,
calibrated parameter file with credible intervals.

Literature anchors: Rivera et al. 2022 (CMS 210:111524, GP + emcee over 1300
Taylor FE runs), Walters et al. 2018 (JAP 124:205105, Higdon PCA-GP framework,
single shot constrains only A), Ojal et al. 2022 (A-B-n non-uniqueness), Rodionov
et al. 2023 (friction as nuisance; multi-velocity sharpening).

## 2. What exists already (reuse, do not rebuild)

- `rz_profile_compare.py`: axis-corrected scan profile via per-slice circle fits
  (Kasa), outer-boundary sim contour extraction, metrics. This IS the objective
  kernel; refactor into a library, keep the CLI.
- Scan QA findings machinery (this session): per-slice fit RMS = heteroscedastic
  noise estimate; end-cap detection; volume audit -> truncation length + true-length
  estimate (CuH04: 0.32 mm cut, L_true ~= 22.40 mm).
- Validated forward models (RZ, run-to-rebound, dt = 5e-9, 8x80 mesh):
  - F2 "fine": `rz_slug_thermal_mult_cal.i` (NEML2 multiplicative + F-bar), ~2 h/run.
  - F1 "fast": `rz_slug_thermal_simo.i` (native Simo-Hughes twin), ~40 min/run.
    Cross-code agreement at identical constants: 0.04 mm on length, RMS identical.
- 16 completed full runs (13 sweep + 3 full-fidelity) = free DOE seed points.
- Hardware: 10 cores / 32 GB local (8 concurrent single-core runs); INL HPC sbatch
  scaffolding in meta-repo `scripts/` for scale-out.
- MOOSE stochastic_tools has a complete in-stack alternative (AffineInvariantDES,
  GP trainers, SamplerFullSolveMultiApp batch mode). NOT used here per the
  requirement for a Python stack and because the objective needs STL processing;
  it remains the fallback if the Python driver becomes a bottleneck.

## 3. Data pipeline: scan -> calibration target

Per STL, `scan_qa.py` produces a `CalTarget` (JSON + NPZ) and a QA report page:

1. Parse metadata from filename: specimen ID, temper, impact velocity.
2. Foot-end detection (larger near-end radius), slice in 0.25 mm bins, Kasa
   circle fit per slice -> axis centerline c(x), radius R(x), fit RMS s(x).
3. Artifact audit:
   - end-cap detection at the rear (closed cut face) -> truncation flag;
   - volume audit: V_scan = pi * integral R^2 dx vs V0 = pi r0^2 L0 ->
     missing length dL = (V0 - V_scan)/(pi R_rear^2), true length
     L_est = extent + dL, with sigma_L from r0/L0 tolerance + fit noise;
   - axis-wander report (tilt/bend magnitude), out-of-round check
     (fit RMS >> noise floor => flag slice range as untrusted).
4. Emit target: zs grid (from foot plane), R_exp(zs), sigma(zs) = max(fit RMS,
   scanner floor ~20 um), trusted mask (drop zs < 0.6 mm foot-lip mixing zone and
   the last ~1 mm before a cut), L_est +/- sigma_L, foot max radius about the
   fitted axis, rear radius.

Gate G-scan: every new STL gets this report reviewed once before entering the
likelihood (today's CuH04 audit is the template: rear "4.15" was axis wander,
truth 3.91).

## 4. Forward model wrapper

`forward.py`: `run(theta, shot, fidelity) -> SimResult`

- theta -> HIT CLI overrides (all constants are already top-level HIT variables);
  shot -> velocity `v=...` (and geometry if it ever varies); unique workdir;
  subprocess `marlin-opt`; parse rebound/blowup from the CSV
  (physical arrest: |vel| < 1 m/s and max_ep < ~8; runaway: ep or |vel| explodes).
- Returns: profile r(zs) from the outer-boundary contour, L, foot_r, rear_r,
  arrest time, feasibility flag, wall time.
- Ledger (`runs.parquet` + run dirs): theta, shot, fidelity, git SHAs, seed,
  metrics, status. Content-hash caching so re-entrant campaigns never re-run.
- Fidelity ladder:
  - F1 = Simo twin as-is (~40 min). DOE workhorse.
  - F1c = coarse probe (4x40 mesh, dt 1e-8) — ONLY if validated in Phase 0
    against F1 on the 13 existing sweep points (expected ~5-10 min/run; accept if
    profile deviation << scan sigma; else drop this rung).
  - F2 = NEML2 mult + F-bar (~2 h). Confirmation/posterior-predictive only.
  The 0.04 mm F1/F2 agreement justifies calibrating on F1; a delta-GP correction
  (Section 6) absorbs the residual if Phase 0 shows it matters.

## 5. Parameters, priors, feasibility

Calibrated theta (log-space where positive):

| param | role | prior | note |
|---|---|---|---|
| A | initial yield | lognormal, med 99.7 MPa, sd 0.2 dec | A-B-n trio degenerate (Ojal); expect the posterior to constrain a combination |
| B | hardening coef | lognormal, med 262.8 MPa, sd 0.2 dec | |
| n | hardening exp | uniform [0.1, 0.5] | |
| C | rate coef | uniform [0.01, 0.05] | weakly informed per shot |
| ipe | temper pre-strain | uniform [0.1, 0.5] per temper | shared across shots of one temper |
| mu | anvil friction | uniform [0.03, 0.3] | nuisance, shared across all shots (same rig) |
| m | thermal exp | FIXED 0.98 | invisible without temperature-varied tests (Walters) |

Feasibility: the adiabatic-extrusion runaway kills soft/slippery corners
(strength < ~0.85x AND mu < ~0.1 at 236 m/s). Failed runs enter the ledger as
infeasible; a GP classifier on feasibility gates the sampler (likelihood -> -inf)
and the acquisition avoids wasting runs there. Do NOT silently drop them.

## 6. Emulator

Higdon/Walters-style PCA-GP, per shot-family:

- Stack DOE profiles on the common zs grid (interpolated, trusted mask applied),
  center/scale, SVD -> keep k modes for 99.5% variance (expect k = 3-5).
- Inputs: (theta, v). Outputs: one GP per PCA weight + one GP each for L and
  foot_r. Matern-5/2, ARD, scikit-learn `GaussianProcessRegressor` (10-D-max
  input, ~10^2-10^3 points: sklearn is sufficient; GPyTorch only if point counts
  explode).
- Bi-fidelity option: delta-GP on (F2 - F1) trained on ~15-25 paired runs,
  applied additively. Activate only if Phase-0 paired runs show |delta| exceeding
  ~1/3 of scan sigma anywhere.
- Validation gates: 5-fold CV; holdout RMSE per output < min(scan sigma,
  0.1 mm) on profile modes reconstructed to physical space; emulator error added
  to the likelihood variance (sigma_GP^2 from the GP predictive variance).

## 7. Likelihood and objective

Per shot s, independent Gaussian blocks:

- Profile: r_GP(zs_i; theta, v_s) vs R_exp,s(zs_i) with variance
  sigma_s(zs_i)^2 + sigma_GP^2 + sigma_d^2, on the trusted mask. Decimate the
  0.25 mm grid to ~40 quasi-independent stations (scan noise is correlated at
  fine scales; full-grid iid Gaussian would overweight the profile).
- Length: L(theta, v_s) vs L_est,s, variance sigma_L,s^2 + sigma_GP^2.
- Foot max radius: same pattern (captures the lip that PCA modes may smooth).
- sigma_d = global model-discrepancy jitter, HalfNormal(0.15 mm) hyperprior,
  MARGINALIZED in the MCMC (the lightweight alternative to Kennedy-O'Hagan; the
  Taylor-calibration literature uniformly skips full KOH and instead monitors
  posterior pileup at prior bounds as the inadequacy alarm - we adopt that
  diagnostic explicitly).
- Joint log-likelihood = sum over shots. Optional per-shot velocity nuisance
  v_s ~ N(v_nominal, 0.5 m/s) if shot records justify it (cheap: v is already an
  emulator input).

The deterministic objective (for MAP / quick fits) is the same expression
maximized; expose it as `objective.py::neg_log_posterior(theta)` so
scipy.optimize can reuse it unchanged.

## 8. Inference

- Sampler: emcee (affine-invariant ensemble; matches Rivera; trivially parallel;
  pure-Python). 2 x n_dim x 8 walkers, init from MAP +/- prior scatter
  (MAP via scipy differential_evolution on the emulator, seconds).
- Diagnostics: arviz R-hat/ESS, corner plot, prior-vs-posterior overlays,
  posterior pileup check at bounds.
- Posterior predictive: ~20 draws re-run through the REAL forward model
  (F1; plus F2 at the median) -> credible-band profile overlays per shot. This is
  the honesty gate on the emulator.

## 9. Active-learning refinement loop

1. Round 0: DOE = Sobol over priors, 96 F1 runs (12 batches of 8, ~2.5 days
   local; or one HPC job array, hours) + the 16 existing runs re-scored.
2. Fit emulator -> MCMC -> posterior v1.
3. Acquisition: draw 16 theta from the posterior (thinned), run F1, retrain,
   re-sample. Repeat until posterior quantiles move < 5% between rounds
   (expect 1-3 rounds; this is the cheap Bayesian analogue of
   BiFidelityActiveLearningGPDecision).
4. Final: posterior predictive (Section 8), F2 confirmation at the median,
   write `johnson_cook_neml2_mult_thermal_cal.i` from the median with credible
   intervals in comments.

## 10. Verification gates (in order; each blocks the next)

- G0 synthetic self-calibration: manufacture a "scan" from an F1 run at known
  theta* + realistic noise (axis tilt + slice noise + rear truncation applied to
  the contour!); the pipeline must recover theta* within the posterior. Tests
  objective, emulator, sampler, AND the scan-QA corrections end-to-end.
- G1 fidelity audit: score F1c (if used) and the delta(F2-F1) on existing runs.
- G2 single-shot CuH04 posterior: expect A-ish combination constrained, B-n-C
  wide (literature says so); document the degenerate directions (posterior
  correlations + PCA of the posterior).
- G3 multi-shot joint posterior as scans arrive; report contraction vs G2.

## 11. Software layout

`marlin/python/taylor_cal/` (package, pip-installable -e):

```
taylor_cal/
  scan_qa.py      # STL -> CalTarget + QA report (from rz_profile_compare internals)
  targets.py      # CalTarget dataclass, (de)serialization
  forward.py      # HIT override builder, subprocess runner, blowup detection
  ledger.py       # parquet run ledger + content-hash cache
  emulator.py     # PCA + sklearn GPs + feasibility classifier + CV gates
  objective.py    # log-likelihood / neg-log-posterior
  inference.py    # priors, emcee driver, arviz diagnostics
  campaign.py     # DOE, batch scheduling (local pool of 8 / sbatch emitter), AL loop
  report.py       # overlays, corner, QA pages
  cli.py          # taylor-cal qa|doe|fit|sample|predict
```

Dependencies to add (pip, into `moose-cylinder-equal-val` or a fresh env):
`emcee corner scikit-learn arviz pandas pyarrow` (SALib optional for Sobol
indices). All pure-Python/BLAS; no conflict with the sim env (the driver only
shells out to marlin-opt).

## 12. Milestones

| # | deliverable | est. effort |
|---|---|---|
| M1 | package skeleton + scan_qa on CuH04 reproducing today's audit | short |
| M2 | forward.py + ledger; re-score 16 existing runs into the ledger | short |
| M3 | G0 synthetic self-calibration pass | medium (the real test) |
| M4 | Round-0 DOE (96 F1 runs) + emulator + G2 single-shot posterior | ~3 days wall, mostly unattended |
| M5 | AL rounds + posterior predictive + F2 confirmation | ~1-2 days wall |
| M6 | multi-shot (G3) as new STLs land | repeat M4-M5 scale |

## 13. Risks / open questions

- Single scan today: G2 will be honest about degeneracy; the campaign is designed
  so each new STL is one `scan_qa` call away from joining the likelihood.
- Specimen geometry tolerance (r0, L0) enters the volume audit: get nominal-vs-
  measured pre-test dimensions from shot records if available; else sigma_L
  carries it.
- Rate-form specificity: constants calibrated through F1 transfer to NEML2 at
  the 0.04 mm level (verified); the F2 confirmation run guards this each campaign.
- Profile phase misalignment (Francom-style elastic FDA) deferred: our profiles
  share a physical foot-plane origin, so warping is second-order; revisit if
  posterior-predictive residuals show systematic axial shift.
- If local compute becomes the bottleneck, `campaign.py` emits sbatch arrays
  (INL HPC) using the meta-repo scripts as templates.
