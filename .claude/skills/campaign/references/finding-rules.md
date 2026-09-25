# Finding rules

How `/campaign learn` and the `campaign-loop` agent judge a run, write a finding, and update the
handoff. The section syntax is `<meta_repo>/campaign/formats/findings.md`; the verdict words are
in `formats/manifest.md`, "Verdicts".

## Judge the verdict

Read the run's `manifest.yaml` (`hypothesis`, `exit`, `qoi`) and its `note.md`. Judge against the
hypothesis as written, never against a softer reading of it.

| verdict | when |
|---|---|
| `failed` | `exit` is not 0, the job was lost, or `qoi` lacks the measure the hypothesis names because the run did not produce it |
| `supported` | the named measure meets the stated number |
| `refuted` | the named measure misses the stated number |
| `inconclusive` | the run completed but the measure cannot decide the hypothesis: a NaN, a value inside the noise the campaign states, or a comparison whose baseline is missing |

The number decides. A measure 0.0101 against "above 0.010" is supported; say in the finding when
it sits inside a stated noise floor.

## Order

1. Write the finding, when the run supports one (below).
2. Record the verdict: `<launcher> verdict <id> <D> <word> --finding F<n> --by loop`, with
   `--finding` omitted when the run feeds no finding.
3. For `failed` and `inconclusive`, add one ledger note with
   `<launcher> note <id> <D> "<why>; see runs/<D>_<tag>/run.log; retry only with <condition>"`,
   and for `failed` one Do-not-repeat line in `handoff.md` (below).

Every verdict ends up citing a finding, or it is `failed` or `inconclusive` with its note line
and, for `failed`, its Do-not-repeat line. A `supported` or `refuted` run with no finding is not
done.

## A good finding

```
## F4. The 1 Hz shift at 1.5 mm is 0.012 rad, so the crossing lies between 1.5 and 2.0 mm
- date: 2026-09-26
- runs: D016, D014
- measures: phase_shift_1hz_rad
- refutes: -
- closes: no

D016 at 1.5 mm gives 0.012 rad, above the 0.010 floor; D014 at 2.0 mm gave 0.004. The bracket is
now 0.5 mm wide. Next: 1.75 mm closes it (one run on each side within 0.5 mm).
```

- The heading is the claim with its number. "F4. Results of D016" is a label, not a finding.
- One claim per section. Two claims are two findings.
- `runs:` cites every run whose number the body uses, and every one has a `done` ledger line.
  `measures:` names only rows of `## Measures`.
- Cite, do not paste: numbers come from `qoi.json` and are quoted to the digits it holds; the
  evidence is the run directory. A figure is named by its file in `gallery/`.
- `refutes: F<n>` when this overturns an earlier finding. The earlier finding is never edited.
- `closes: yes` only when this finding meets the frontmatter `stop` as written: every measure and
  every number in the stop sentence is in the heading or the body, backed by a cited run. A
  finding that nearly meets it says `closes: no` and names the missing run in `Next:`.
- A failed run writes no finding. Two refuted runs that bracket nothing may share one finding
  that says so.

## Closing and refuting

- On `closes: yes`, run `<launcher> close <id> F<n>`; it sets `status: done` and `closed`. Never
  edit the frontmatter by hand.
- A finding that contradicts `## Hypothesis` (it predicts a depth, a sign, a scaling the finding
  rules out) forces a rewrite of `## Hypothesis` and one Decisions line:
  `- <date>: rewrote the hypothesis from "<old claim>" to "<new claim>" because F<n> <what it showed>.`
  The loop then stops with `REFUTED`; the next pass waits for the user.

## The handoff after learn

The file is `<dir>/handoff.md`; the disciplines are
`<meta_repo>/.claude/skills/handoff/references/handoff-rules.md`.

| section | write |
|---|---|
| `## State` | rewrite: findings and runs so far, spent over budget, the open bracket or question, what is ticked and what awaits a tick, and `campaign status <id>` as the command that shows it |
| `## Next` | rewrite: ordered `- [ ]` steps with exact commands (`campaign run D017`, `/campaign <id> propose`) |
| `## Do not repeat` | append, one per failed run |
| `## Decisions` | append: a hypothesis rewrite, a withdrawn proposal, a group abandoned |
| `## Gotchas` | append: queue waits, wall times per run, a measure script quirk |
| `## Map` | rewrite: runs (first to last directory), measure scripts, figures with their `gallery.md` headings, the method file |
| `## Sessions` | append one line per skill run or loop invocation |

A good Do-not-repeat line has four parts after the date: what was tried verbatim, why it failed,
the evidence path, and the condition under which it is worth trying again.

```
- 2026-09-22: ran the 1.5 mm layer with the D69 `ksp_rtol=1e-12`; failed because GMRES stalled at the layer interface, DIVERGED_ITS after 2000 its; evidence runs/D015_layer-1.5mm/run.log; retry only with ksp_rtol=1e-10 or a Schur split.
```

"D015 failed" names nothing and saves nobody a run.
