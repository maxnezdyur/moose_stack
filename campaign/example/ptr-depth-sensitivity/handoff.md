---
campaign: ptr-depth-sensitivity
updated: 2026-09-22
sessions: 3
---
# Handoff: ptr-depth-sensitivity

One page that carries this campaign from one session to the next. The question and the queue are
in `campaign.md`, the record is `LEDGER.md` and `FINDINGS.md`; this file duplicates neither.

## State

Three findings, five runs, 14.1 of 60 core-h spent. The 1 Hz crossing is bracketed between 1.0 mm
and 2.0 mm (F3). D015 at 1.5 mm diverged in GMRES. D016 repeats it with `ksp_rtol=1e-10` and is
ticked; D017 at 1.25 mm awaits a tick. `campaign status ptr-depth-sensitivity` shows it.

## Next

- [ ] Run D016 - `campaign run D016`
- [ ] Collect and judge it - `campaign collect D016 && campaign verdict D016`
- [ ] If D016 is supported, tick D017; if refuted, propose 1.75 mm instead - `campaign.md`
- [ ] Refresh the figure - `python scripts/plot_shift.py` writes `gallery/shift-vs-depth.png`

## Do not repeat

- 2026-09-22: ran the 1.5 mm layer with the D69 `ksp_rtol=1e-12`; failed because GMRES stalled at the layer interface, DIVERGED_ITS after 2000 its; evidence runs/D015_layer-1.5mm/run.log; retry only with ksp_rtol=1e-10 or a Schur split.

## Decisions

- 2026-09-18: chose forward-only synthetic sensitivity over inversion runs because one inversion costs 40 core-h and the question is about the data, not the optimizer.
- 2026-09-18: chose the release k levels (446, 81) over the handbook (390, 90) because the experiment will be judged against the release result.
- 2026-09-20: chose to bracket the 1 Hz crossing before touching 10 Hz because F2 shows 10 Hz is blind below 1 mm.

## Gotchas

- A 3-D forward at NP=3 takes 7 min locally and 4 min on one teton node at 48 ranks; the queue wait on `general` was 20 to 40 min.
- `truth_layer.i` writes `phase_1hz.csv` and `phase_10hz.csv` next to the input; `scripts/phase_shift.py` reads them from the run's `outputs.dir`.

## Map

| what | where | why |
|---|---|---|
| forward input | `PTR/release_13x13/inverse_simulation/truth_layer.i` | the paper physics with `layer_depth_mm` |
| measures | `scripts/phase_rms.py`, `scripts/phase_shift.py` | the three `## Measures` rows |
| figure | `gallery/shift-vs-depth.png`, section "Figure 1. 1 Hz and 10 Hz shift against layer depth" | F2 and F3 |
| runs | `runs/D011_nominal-baseline` .. `runs/D015_layer-1.5mm` | the ledger's evidence |

## Sessions

- 2026-09-18 15:10 max /campaign new: wrote campaign.md, the constraints table and the three measures
- 2026-09-19 14:12 loop propose+run: D011 locally, F1, proposed D012 and D013
- 2026-09-22 11:28 loop propose+run: D014 and D015 on teton, F3, proposed D016 and D017
