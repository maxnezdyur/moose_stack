---
id: <id>
project: <project>
title: <title>
question: <one sentence>
stop: >
  <a condition that names a measure and a number>
budget:
  core_hours: <n>
  wall_days: <n>
  max_runs: <n>
cluster: local
app: isopod
autonomy: propose-only
status: draft
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
---
# Campaign: <title>

## Hypothesis

_Rewrite as the campaign learns. A rewrite earns a Decisions line in `handoff.md` that cites the
finding that forced it._

## Constraints

_Rewrite. The knobs a run may not change. The loop refuses a proposal that changes one._

| knob | value | why |
|---|---|---|
| <knob> | <value> | <why> |

Out of scope:
- <non-goal>

## Measures

_Append only. `name` is the key in every `qoi.json`. Never delete or rename a row._

| name | unit | how | added |
|---|---|---|---|
| <name> | <unit> | `python scripts/<measure>.py {outputs}` or csv:<file>:<column>:last | <YYYY-MM-DD> |

## Proposed

_The queue. `- [ ]` proposed, `- [x]` approved. `campaign run D<nnn>` consumes a ticked entry._

- [ ] D001 <tag> | - | <n> core-h | tests: <measure> <comparison> <number> | because: <F<n> or D<nnn>>
  - cwd: <dir>
  - cmd: <command>
