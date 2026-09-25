---
campaign: ptr-depth-sensitivity
project: ptr-update
status: active
posture: needs-you
flags: [proposal-pending]
autonomy: propose-only
cluster: teton
runs: 5
supported: 3
refuted: 1
inconclusive: 0
failed: 1
core_hours: 14.1
core_hours_budget: 60
wall_days: 7
wall_days_budget: 14
findings: 3
last_finding: "F3. At 2.0 mm the 1 Hz shift is 0.004 rad, below the noise floor"
closes: false
proposals_ticked: 1
proposals_pending: 1
session: none
handoff_sessions: 3
updated: 2026-09-24T18:02:11-04:00
tags: [factory-campaign]
---
# ptr-depth-sensitivity

<!-- factory:head:begin -->
[[Home]] - **active** - teton - 5 runs: 3 supported, 1 refuted, 1 failed - 14.1 / 60 core-h, day 7 of 14 - needs you

> **Next:** D017 awaits your tick; D016 is ticked and will run on the next start
> `~/projects/moose_stack/factory/factory start ptr-depth-sensitivity`

## Gates

_Both are yours. The tick lives in `campaign.md`, through `Specs/ptr-depth-sensitivity/`, and is read back by `campaign run`. The budget is the frontmatter._

- [x] D016 layer-1.5mm-rtol10 - 3 core-h - tests: phase_shift_1hz_rad with the step at 1.5 mm is above 0.010 rad - because F3, D015
- [ ] D017 layer-1.25mm - 3 core-h - tests: phase_shift_1hz_rad with the step at 1.25 mm is above 0.010 rad - because F3
- budget: 14.1 of 60 core-h, 5 of 30 runs, day 7 of 14. Raise it in `campaign.md` and append a Decisions line.
<!-- factory:head:end -->

## Notes


<!-- factory:body:begin -->
## Open the campaign

- Campaign: [campaign.md](file:///Users/maxnezdyur/projects/ptr-update/campaigns/ptr-depth-sensitivity/campaign.md)
- Ledger: [LEDGER.md](file:///Users/maxnezdyur/projects/ptr-update/campaigns/ptr-depth-sensitivity/LEDGER.md), findings: [FINDINGS.md](file:///Users/maxnezdyur/projects/ptr-update/campaigns/ptr-depth-sensitivity/FINDINGS.md)
- Workspace: [ptr-update.code-workspace](file:///Users/maxnezdyur/projects/ptr-update/moose_stack.code-workspace)
- Vault: `obsidian://open?vault=moose-factory&file=Campaigns/ptr-depth-sensitivity`

```
~/projects/moose_stack/campaign/campaign status ptr-depth-sensitivity
cd ~/projects/ptr-update && claude --bg --name ptr-depth-sensitivity "/campaign ptr-depth-sensitivity"
```

## Where it stands

| property | value |
|---|---|
| question | How deep below the scanned surface can a conductivity step still move the measured phase above the camera noise floor? |
| stop | phase_shift_1hz_rad for a Cu-to-Ni step falls below 0.010 rad, bracketed within 0.5 mm |
| status | active, propose-only |
| cluster | teton (D011 ran locally) |
| runs | 5 of 30: 3 supported, 1 refuted, 1 failed |
| core-hours | 14.1 / 60 |
| wall | day 7 of 14, created 2026-09-18 |
| findings | 3, none closes |
| last finding | F3. At 2.0 mm the 1 Hz shift is 0.004 rad, below the noise floor |
| code | ptr-update eb8109b, moose d96c576, isopod aa4173f, moose-dev-openmpi/2026.05.08 |

## Ledger (last 3 of 5)

- D013 layer-1.0mm - teton:8811208 - done exit=0 3.1 core-h - **supported** phase_shift_1hz_rad=0.031 - F2
- D014 layer-2.0mm - teton:8812234 - done exit=0 3.0 core-h - **refuted** phase_shift_1hz_rad=0.004 - F3
- D015 layer-1.5mm - teton:8812235 - done exit=1 4.7 core-h - **failed** - note: GMRES stalled at the layer interface, DIVERGED_ITS after 2000 its; retry only with ksp_rtol=1e-10

## Findings

- F1. The nominal forward reproduces the paper's 1 Hz phase to 0.0021 rad rms - D011
- F2. A Cu-to-Ni step moves the 1 Hz phase by 0.084 rad at 0.5 mm and 0.031 rad at 1.0 mm - D012, D013, D011
- F3. At 2.0 mm the 1 Hz shift is 0.004 rad, below the noise floor - D014, D013

## Handoff

**State.** Three findings, five runs, 14.1 of 60 core-h spent. The 1 Hz crossing is bracketed between 1.0 mm and 2.0 mm (F3). D015 at 1.5 mm diverged in GMRES. D016 repeats it with `ksp_rtol=1e-10` and is ticked; D017 at 1.25 mm awaits a tick.

**Next.**
- Run D016 - `campaign run D016`
- Collect and judge it - `campaign collect D016 && campaign verdict D016`
- If D016 is supported, tick D017; if refuted, propose 1.75 mm instead - `campaign.md`
- Refresh the figure - `python scripts/plot_shift.py` writes `gallery/shift-vs-depth.png`

**Do not repeat (last 3).**
- 2026-09-22: ran the 1.5 mm layer with the D69 `ksp_rtol=1e-12`; failed because GMRES stalled at the layer interface, DIVERGED_ITS after 2000 its; evidence runs/D015_layer-1.5mm/run.log; retry only with ksp_rtol=1e-10 or a Schur split.

_Sessions: 3. Updated 2026-09-22. Run `/handoff` in the project to change this block._

## Gallery

![[Gallery/ptr-depth-sensitivity/gallery.md]]

## Session

- Lease: **free**. `~/projects/moose_stack/factory/factory start ptr-depth-sensitivity` takes it.
- Live sessions with cwd under `~/projects/ptr-update`: none

## Flags

- `proposal-pending` - one entry under `## Proposed` is unticked and autonomy is propose-only

## Timeline

- 2026-09-22 12:40 verdict - D014 refuted, D015 failed; F3 written
- 2026-09-22 11:30 dispatched - D014, D015 to teton
- 2026-09-20 10:02 verdict - D012, D013 supported; F2 written
- 2026-09-19 14:31 verdict - D011 supported; F1 written
- 2026-09-18 15:10 adopted - board adopted this campaign from ~/projects/ptr-update/campaigns
<!-- factory:body:end -->
