---
feature: moosify-uel
updated: 2026-10-20
sessions: 1
---
# Handoff: moosify-uel

One page that carries this worktree from one session to the next. The plan is
[blueprint.md](blueprint.md) and the result is the newest
`.claude/cache/moose-build-<label>.json`; this file duplicates neither. It says where the work
stands, what to do next, and what not to try again. Keep it under about 150 lines and link to
evidence instead of pasting it.

## State

Built 2026-10-20, uncommitted. In `moose/`: `moosify_uel.i` and `gold/moosify_uel_short.csv` are staged; `tests` is modified, not staged. The face reactions are `save_in` + `NodalSum` (top -2160 N, bottom +2160 N); `SidesetReaction` was dropped because it read qp stress and missed the load by up to 12x. Both tests pass: `./run_tests --re=moosify_uel` in `moose/modules/combined`, 2 passed. Gate B sqa and ascii pass after the change. The full 1.05e5 s run converges (1,050 steps, 125 s); output in `specs/gallery/full_run/`.

## Next

- [ ] Decide the 2 held review findings (delete the header and the phi comments in `moosify_uel.i`, or keep them per Q13) - `specs/review-moosify-uel.md`
- [x] Optional: set `time_integration_scheme` on `top_heat_loss` to clear its warning - `moose/modules/combined/examples/thermomechanics/moosify_uel.i`
- [ ] Commit in `moose/`, then `/moose-ship`; the PR waits for #33820 or targets `next` with #33820 named as a dependency


## Do not repeat

_Append only. Never delete a line. One line per dead end, so the next session does not pay for it
twice._

- 2026-10-20: asserted top_reaction near -2160 N; SidesetReaction reads qp stress, 27124 to -6740 N on the 9x6x4 mesh, one refine cuts the error about 4x; evidence specs/blueprint.md Amendments; retry only on a much finer mesh
- 2026-10-20: SQA gate at scope moose/modules/combined; BLOCKED, no sqa_reports.yml there; run it at scope moose
- 2026-10-20: SidesetReaction for face reactions; superseded by save_in + NodalSum, which balances the load exactly; evidence specs/blueprint.md Amendments; retry only to show the qp-stress error

## Decisions

_Append only. Never delete a line._

- 2026-10-20: the user accepted all 14 blueprint defaults in chat
- 2026-10-20: held 2 review findings (delete input comments) because Q13 makes the header comment the example's documentation
- 2026-10-20: chose save_in + NodalSum over SidesetReaction for the face reactions, at the user's request; the CSVDiff now asserts the 2160 N balance
- 2026-10-20: the user wants no penalty-formulation tests; the abs_zero comment no longer mentions penalty

## Gotchas

_Append only. Never delete a line. Env, build and test quirks worth knowing: wall-clock times, gold
regeneration, flaky tests._

- `node` in the login shell is a lazy nvm function; pack-blueprint.py needs `PATH=$HOME/.nvm/versions/node/v24.19.0/bin:$PATH`
- The docs smoke build writes subchannel media PNGs into `moose/modules/subchannel/doc/content/media_scripts/`; restore or delete them after it
- Warp displacements by about 300, not 1e5: |u| reaches 3.7e-5 m and x1e5 inverts drawn elements (the real Jacobians stay positive)
- combined-opt must be rebuilt after the rows cherry-pick, or it rejects `formulation = rows`

## Map

_Rewritten every session. Files touched and why, tests and gold, every file in `specs/gallery/`
with its `gallery.md` section heading, the review file, the build record path._

| what | where | why |
|---|---|---|
| input | `moose/modules/combined/examples/thermomechanics/moosify_uel.i` | rows ties replace Global Strain, main.pdf face map, phi product, UMAT on both blocks, nodal reactions (save_in + NodalSum), outputs |
| spec | `moose/modules/combined/examples/thermomechanics/tests` | parent block with SQA fields, check_input and CSVDiff children; not yet staged |
| gold | `moose/modules/combined/examples/thermomechanics/gold/moosify_uel_short.csv` | PRP spreads 0, reactions -2160/+2160 N, top heat rates; recaptured after the reaction fix |
| gallery | `specs/gallery/prp_spread_rows_vs_penalty.png` | "Figure 1. Plane-remains-plane spread, rows tie against penalty tie" |
| gallery | `specs/gallery/deformed_temperature_t1000.png` | "Figure 2. Deformed block at t = 1000 s, colored by temperature" |
| gallery | `specs/gallery/gallery.md` | the figure page |
| full run | `specs/gallery/full_run/full.e`, `full.csv`, `open_full.py` | 0 to 1.05e5 s, converged; open_full.py opens it in ParaView, warp x300 |
| review | `specs/review-moosify-uel.md` | 3 findings: 1 applied, 2 held |
| build record | `.claude/cache/moose-build-moosify-uel.json` | final build report |
| blueprint | `specs/blueprint.md`, `specs/blueprint.html` | the plan, status built |
| reference | `~/Library/CloudStorage/OneDrive-IdahoNationalLaboratory/UEL/Reference Material/main.pdf` | the problem statement the input must solve |

## Sessions

_Append only. Never delete a line._

- YYYY-MM-DD HH:MM <session-id or label> <skill or mode>: one line of what it did
- 2026-10-20 2004a151 /moose-blueprint --unattended then /moose-build: blueprint (14 decisions, accepted), build GOAL_MET, Gate B PASS, review 1 applied 2 held
- 2026-10-20 2004a151 follow-up: reactions moved to save_in + NodalSum, gold recaptured, full run checked in ParaView
