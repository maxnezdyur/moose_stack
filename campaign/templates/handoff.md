---
campaign: <campaign>
updated: <YYYY-MM-DD>
sessions: 0
---
# Handoff: <campaign>

One page that carries this campaign from one session to the next. The question and the queue are
in `campaign.md`, the record is `LEDGER.md` and `FINDINGS.md`; this file duplicates neither. It
says where the campaign stands, what to run next, and what not to try again. Keep it under about
150 lines and link to evidence instead of pasting it.

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

_Rewritten every session. The inputs, scripts and figures in play and why; the run directories
that carry the evidence._

| what | where | why |
|---|---|---|
| input | `<path>` | <why> |

## Sessions

_Append only. Never delete a line._

- YYYY-MM-DD HH:MM <session-id or label> <skill or mode>: one line of what it did
