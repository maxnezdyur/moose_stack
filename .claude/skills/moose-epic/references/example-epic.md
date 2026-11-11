---
epic: modal-damping
title: Rayleigh damping set from modal targets
repo: moose
issue: pending
created: 2026-11-10
---

<!-- Example only. The classes and the tests are invented to show the shape of the file. -->

## Goal

A structural-dynamics user gives two target modes and the damping ratio wanted at each. MOOSE
then computes the Rayleigh coefficients and applies them to a transient analysis. Today the user
computes the coefficients by hand from an eigenvalue run. The change touches three areas (a
reporter, a coefficient object, an action), and each one has a result of its own, so it goes in
as three pull requests that merge in order.

## Shared physics

Rayleigh damping is $C = \alpha M + \beta K$. The damping ratio of mode $i$ with circular
frequency $\omega_i$ is

$$\zeta_i = \frac{\alpha}{2 \omega_i} + \frac{\beta \omega_i}{2}.$$

Two targets $(\omega_a, \zeta_a)$ and $(\omega_b, \zeta_b)$ give a 2 by 2 linear system for
$\alpha$ and $\beta$.

| symbol | meaning | unit |
|---|---|---|
| $\alpha$ | mass-proportional coefficient | 1/s |
| $\beta$ | stiffness-proportional coefficient | s |
| $\omega_i$ | circular frequency of mode $i$ | rad/s |
| $\zeta_i$ | damping ratio of mode $i$ | - |

## Slices

| id | title | needs | a user can | tests prove it |
|---|---|---|---|---|
| s1 | Damping ratio of each mode | - | print the damping ratio of each mode for given $\alpha$ and $\beta$ | `ratios_csv`, `ratios_negative_frequency_error` |
| s2 | Coefficients from two target modes | s1: the mode-frequency accessor | get $\alpha$ and $\beta$ from two target modes and their ratios | `coefficients_two_modes`, `coefficients_equal_modes_error` |
| s3 | Action that applies the coefficients | s2: the coefficient reporter values | set damping for a transient analysis with one input block | `action_matches_hand_input`, `action_missing_reporter_error` |

## Seams

| seam | contract | owner | used by |
|---|---|---|---|
| mode-frequency accessor | The reporter of s1 gives the circular frequency of mode $i$ after the eigenvalue solve, for each $i$ below the number of converged modes. | s1 | s2 |
| coefficient reporter values | The object of s2 declares `alpha` and `beta` as reporter values that are final at the end of the eigenvalue solve. | s2 | s3 |

## Cross-slice decisions

- 2026-11-10: chose circular frequency over frequency in Hz for each interface between slices,
  because the eigenvalue solve gives $\omega^2$ and a conversion in two places invites a factor
  of $2\pi$ error.

## Related features

- `modal-damping-table`: a table of damping ratio against frequency for the documentation. It
  needs nothing from s3, so it is an ordinary feature that starts when s1 merges.

## Out of scope

- Modal damping (a ratio per mode with no Rayleigh form).
- Frequency-dependent material damping.
- Any change to `blackbear` or `isopod`.

## Amendments

- 2026-11-10: plan written with three slices.
