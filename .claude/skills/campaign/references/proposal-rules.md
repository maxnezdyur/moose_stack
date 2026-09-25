# Proposal rules

How `/campaign propose` and the `campaign-loop` agent write entries under `## Proposed` in
`campaign.md`. The entry syntax is `<meta_repo>/campaign/formats/campaign.md`, "The proposed
entry". This file says what makes an entry worth running.

## Before you write

Read `campaign.md`, `LEDGER.md`, `FINDINGS.md` and `handoff.md` whole. Every entry must follow
from them:

- Its `because:` cites at least one `F<n>` or `D<nnn>` that exists. A proposal with nothing to
  cite is a guess; the first proposal of a campaign cites the baseline run it asks for, or says
  `because: -` only when the ledger is empty.
- It does not repeat a `## Do not repeat` line unless that line's retry condition now holds, and
  then its `because:` names the run the line came from.
- It does not repeat a run that already decided its hypothesis. A replay goes through
  `campaign replay`, not a new proposal.

## The entry

| part | rule |
|---|---|
| id | one per entry, from `<launcher> next-id <id>`; mint them one at a time and write each entry before minting the next, because `next-id` reads `## Proposed` |
| tag | says what differs from the baseline (`layer-1.25mm`, not `run2`) |
| group | the group of runs that answer one question together and share one figure, or `-` |
| estimate | `<n> core-h`: `ntasks × walltime` for SLURM, `np × expected hours` locally. Take the hours from the `core-h=` of the nearest similar run in the ledger, not from a guess |
| `tests:` | one checkable sentence that names a measure from `## Measures` and a number: `phase_shift_1hz_rad with the step at 1.25 mm is above 0.010 rad`. "Explore the 1.25 mm case" names no number and cannot be judged |
| `because:` | the findings and runs that motivate it |
| `cwd`, `cmd` | the exact command, one line, no shell variables, from the project root's relative `cwd` |
| `in:` | every input the command reads that `-i` and `!include` do not reach: meshes, data CSVs, restart files. A missing `in:` line makes the run non-replicable |
| `cluster` | only when this run differs from the frontmatter |

## The constraints check

Before you write an entry, compare its `cmd` with every row of `## Constraints`. An override on
the command line (`name=value`), a different `-i` file, a different `-np` or ntasks, an `env:`
line, or a `cluster:` that contradicts a row is a change to that knob. Such an entry is refused:
do not write it. When the next useful run needs a frozen knob changed, write nothing for it and
put the question in the report (`BLOCKED` for the agent): the constraints are the user's.

## How many

Propose the smallest set that can move the campaign toward `stop`: usually two to four entries.
A bracket needs one run on each side; a sweep that cannot change the next decision is waste.
Every entry must be affordable on its own within the remaining budget.

## The tick rule (within-budget only)

Read `<launcher> spent <id>`. The remaining budget is the budget minus the spent value for
core-hours and runs, and the wall days left since `created`. Tick unticked entries in id order
while all three hold:

- the sum of the estimates of every ticked, unrun entry, including this one, is at most the
  remaining core-hours;
- the count of those entries is at most the remaining runs;
- at least one wall day remains.

Stop at the first entry that does not fit and leave it and every later one unticked. Tick with
`<launcher> tick <id> <D>`, never by editing the checkbox. Under `propose-only` and `manual`
never tick; `campaign run` refuses an unticked entry, and that refusal is correct.

## Rejecting an entry

To withdraw an entry you wrote and nobody has ticked, delete it and append a Decisions line to
`handoff.md` that names the id and the reason. The id is never reused. Never delete a ticked
entry; the tick is the user's.
