---
feature: <feature>
updated: <YYYY-MM-DD>
sessions: 0
---
# Handoff: <feature>

One page that carries this worktree from one session to the next. The plan is
[blueprint.md](blueprint.md) and the result is the newest
`.claude/cache/moose-build-<label>.json`; this file duplicates neither. It says where the work
stands, what to do next, and what not to try again. Keep it under about 150 lines and link to
evidence instead of pasting it.

## State

_Rewritten every session. One paragraph: what is green, what is red, and the exact command that
shows it._

## Next

_Rewritten every session. Ordered steps, each with its exact command or file._

- [ ] <step> - `<command or file>`

## Do not repeat

_Append only. Never delete a line. One line per dead end, so the next session does not pay for it
twice._

- YYYY-MM-DD: tried X; failed because Y; evidence <path>; retry only if Z

## Decisions

_Append only. Never delete a line._

- YYYY-MM-DD: chose A over B because C

## Gotchas

_Append only. Never delete a line. Env, build and test quirks worth knowing: wall-clock times, gold
regeneration, flaky tests._

- <quirk>

## Map

_Rewritten every session. Files touched and why, tests and gold, the review file, the build record
path._

| what | where | why |
|---|---|---|
| source | `<path>` | <why> |

## Sessions

_Append only. Never delete a line._

- YYYY-MM-DD HH:MM <session-id or label> <skill or mode>: one line of what it did
