# FINDINGS.md format

One file per campaign, append only. One `## F<n>.` section per finding, numbered from 1. The loop
and you append. A finding is never edited. A finding that turns out to be wrong earns a later
finding that refutes it.

## The file

```
# Findings: ptr-depth-sensitivity

One section per finding. The heading is the claim with its number. Cite at least one run and one
measure. Never edit a section; refute it with a later one.

---
## F9. A flat 200 W/m·K start recovers copper at 446 ± 5 W/m·K
- date: 2026-09-25
- runs: D011
- measures: k_cu_mean, k_cu_std
- refutes: -
- closes: no

The blind start reaches the paper's copper level without a warm start. The nickel rows land at
80.9 ± 4.2. The straddling row stays at 141, which is the interface, not a defect.

## F10. Halving k_Ni moves the 1 Hz phase minimum by 0.071 rad
- date: 2026-09-25
- runs: D014, D011
- measures: phase_min_shift_rad
- refutes: -
- closes: no

Against the D011 baseline the minimum shifts by 0.071 rad, above the 0.05 rad threshold in the
hypothesis. The 10 Hz maps move by less than 0.01 rad, so the 1 Hz data carries the depth
information. Next: the same shift at k_Ni × 2 (D015 failed; retry with a tighter ksp_rtol).

## F12. Sensitivity falls below 1e-3 rad per W/m·K at 1.8 mm depth
- date: 2026-10-03
- runs: D024, D026, D027
- measures: sens_rad_per_wmk
- refutes: -
- closes: yes

D024 at 1.5 mm gives 2.1e-3. D026 at 2.0 mm gives 0.6e-3. D027 at 1.8 mm gives 1.0e-3. This meets
the stop condition: one run on each side of the threshold and one at it.
```

## The section

| part | rule |
|---|---|
| heading | `## F<n>. <claim>`; the claim states the number, not the topic. "F10. Halving k_Ni moves the minimum by 0.071 rad" is a finding; "F10. Results of D014" is a label. |
| `date` | the day it was written |
| `runs` | at least one `D<nnn>`; every run cited must have a `done` line in the ledger |
| `measures` | at least one name from `## Measures` in `campaign.md` |
| `refutes` | `F<n>` when this finding overturns an earlier one, else `-` |
| `closes` | `yes` when this finding meets the frontmatter `stop`, else `no` |
| body | at most about eight lines: what was observed, the numbers, what it implies. A `Next:` sentence is welcome. Link to a figure in `gallery/` by filename when one exists. |

## Rules

1. Number in order. `F<n>` is one more than the last section in the file.
2. Cite, do not paste. The numbers come from `qoi.json`; the evidence path is the run directory.
3. Never edit a section. A wrong finding stays, and a later one names it in `refutes`.
4. One finding per claim. Two claims are two sections.
5. `closes: yes` is the only way a campaign reaches `status: done`. The frontmatter `closed.finding`
   names it.

## What reads it

- The loop reads the whole file before it proposes and cites `F<n>` in every `because:`.
- The factory board shows the last finding's heading on the card and flags a `closes: yes`.
- `campaign status` prints the count of findings and the id of the closing one, if any.
