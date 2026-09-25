# LEDGER.md format

One file per campaign, append only. One entry per run, in launch order. The tool appends. You may
append a note line. Nobody edits a line that exists.

## The file

```
# Ledger: ptr-depth-sensitivity

One entry per run. `campaign run` writes the first line at launch. `reconcile` or `run` appends
`done`. `verdict` appends the verdict. Anyone may append `note`. No line is ever edited.

---
- D011 | flat-200-baseline | depth-sweep | 20260925T101502Z | local:np3 | tests: the flat start recovers Cu above 400 W/m·K
  - done 20260925T104411Z exit=0 core-h=0.4
  - verdict supported | k_cu_mean=446.2 | F9
- D014 | two-layer-kni-half | depth-sweep | 20260925T140310Z | teton:8812234 | tests: halving k_Ni shifts the 1 Hz phase minimum by more than 0.05 rad
  - done 20260925T161122Z exit=0 core-h=5.7
  - verdict supported | phase_min_shift_rad=0.071 | F10
- D015 | two-layer-kni-double | depth-sweep | 20260925T140315Z | teton:8812235 | tests: doubling k_Ni shifts it by more than 0.05 rad the other way
  - done 20260925T173006Z exit=1 core-h=6.1
  - verdict failed | - | -
  - note: solver diverged at eval 14; see runs/D015_two-layer-kni-double/run.log; retry only with ksp_rtol 1e-10
- D021 | replay-D014 | - | 20260926T080000Z | teton:8813990 | replay_of: D014
  - done 20260926T100912Z exit=0 core-h=5.6
  - verdict supported | phase_min_shift_rad=0.071 | F10
```

## The lines

The start line has six fields, separated by ` | `:

| field | value |
|---|---|
| id | `D` plus three digits |
| tag | the run tag |
| group | the group, or `-` |
| stamp | launch time, UTC, `YYYYMMDDTHHMMSSZ` |
| where | `local:np<N>` or `<cluster>:<job id>` |
| hypothesis | `tests: ` and the sentence from the proposal, or `replay_of: D<nnn>` |

The indented lines, each at most once except `note`:

| line | writer | format |
|---|---|---|
| `done` | `run` or `reconcile` | `- done <stamp> exit=<code> core-h=<n>` |
| `verdict` | `verdict` | `- verdict <word> \| <measure>=<value>[, ...] \| <F<n> or ->` |
| `note` | anyone | `- note: <one line>` |

A wrong `done` or `verdict` earns a `note` line that says so and names the correct value. The
manifest holds the corrected value; the ledger holds the history.

## What reads it

- `campaign status` prints the spent budget from `core-h=` and the run count from the start lines.
- The factory board reads the last three entries onto the card and counts verdicts by word.
- The loop reads the whole file before it proposes, so every proposal can cite a `D<nnn>`.

Parse a start line with `^- (D\d{3}) \| `. Parse an indented line with `^  - (done|verdict|note)`.
