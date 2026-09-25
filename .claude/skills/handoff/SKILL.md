---
name: handoff
description: 'Writes or updates the cross-session memory of one feature worktree (specs/handoff.md) or one campaign (campaigns/<id>/handoff.md): State, Next, Do not repeat, Decisions, Gotchas, Map, Sessions. Use for "/handoff [<note>]", "write the handoff", "save this for the next session", "hand this off". Manual invoke only.'
disable-model-invocation: true
argument-hint: "[<note>]"
effort: low
---

# /handoff

Carries this session into the next one through one file, `<worktree-root>/specs/handoff.md`, or
`campaigns/<id>/handoff.md` inside a campaign (below). It sits
beside `specs/blueprint.md` (the plan) and points at the newest build record (the result), and it
duplicates neither: it says where the work stands, what to do next, and what not to try again. This
skill writes that one file and nothing else. It edits no code, runs no build, no tests and no
formatter, and never commits.

`$ARGUMENTS` is an optional note to fold in (a gotcha, a decision, a dead end). With no argument,
write the handoff from this conversation alone.

## Preconditions

This skill runs inside a `/new-feature` worktree or inside a campaign. Check the campaign first:
walk up from the cwd to a directory whose parent is named `campaigns` and that holds
`campaign.md`. Otherwise walk up to the directory whose `.git` is a file (a worktree, not a clone)
beside `moose/`, `blackbear/`, and `isopod/`. Outside both, refuse with "No feature worktree or
campaign here; /handoff only runs inside a /new-feature worktree or a campaigns/<id>/ directory."

In a worktree, that directory is `<worktree-root>`, it owns its own `.claude/`, and `<feature>` is
its basename. The file is `<worktree-root>/specs/handoff.md`.

In a campaign, the directory is `<dir>` and `<id>` is its basename. The file is
`<dir>/handoff.md`, and these differences apply:

- Seed from the same template, resolved under `<meta_repo>/.claude/skills/handoff/references/`
  (`<meta_repo>` is the `meta_repo` key of `~/.config/moose-factory/config.toml`, fallback
  `$HOME/projects/moose_stack`). Substitute `campaign:` for the `feature:` key and `<id>` for
  every `<feature>`, and replace the paragraph under `# Handoff:` with: "One page that carries
  this campaign from one session to the next. The question and the queue are in `campaign.md`,
  the record is `LEDGER.md` and `FINDINGS.md`; this file duplicates neither."
- `## Map` lists the runs (first and last `runs/` directory), the measure scripts, and every
  figure in `gallery/` with its `gallery.md` section heading.
- The State paragraph's command is `campaign status <id>`.
- Never edit `campaign.md`, `LEDGER.md`, `FINDINGS.md`, or a run directory: `/campaign` owns them.

## Write

The steps below name the worktree file; in a campaign read `<dir>/handoff.md` and seed as above.
When `<worktree-root>/specs/handoff.md` is absent, seed it from
`<worktree-root>/.claude/skills/handoff/references/handoff-template.md` (fall back to
`~/projects/moose_stack/.claude/skills/handoff/references/handoff-template.md` in a worktree whose
pipeline is frozen), substitute `feature` and `updated`, set `sessions: 1`, and fill what this
session knows. When it is present, read it whole, then:

| Section | Discipline |
|---|---|
| `## State` | rewrite: one paragraph, what is green, what is red, the exact command that shows it |
| `## Next` | rewrite: ordered `- [ ]` steps, each with its exact command or file |
| `## Do not repeat` | append: `- YYYY-MM-DD: tried X; failed because Y; evidence <path>; retry only if Z` |
| `## Decisions` | append: `- YYYY-MM-DD: chose A over B because C` |
| `## Gotchas` | append: env, build and test quirks (times, gold regeneration, flaky tests) |
| `## Map` | rewrite: files touched and why, tests and gold, every file in `specs/gallery/` with its `gallery.md` section heading, the review file, the build record path |
| `## Sessions` | append: `- YYYY-MM-DD HH:MM <session-id or label> <skill or mode>: one line of what it did` |

Then bump `sessions` by one and set `updated` to today's date. Append exactly one `## Sessions` line
per run of this skill. Never delete or edit a line that is already in an append-only section: a line
that turned out to be wrong earns a second line saying so. Keep the whole file under about 150 lines
and link to evidence rather than pasting it; the full rules, including what a good Do-not-repeat line
looks like, are in `references/handoff-rules.md`. Write the file with Edit or Write, in one pass, and
never reorder the seven headings: `session-context.sh`, `/moose-build` and the factory board all read
them by name.

## Report

Three lines plus the diff. Say which sections were rewritten, how many lines were appended and to
which sections, and the new `sessions` count. Then show the change: `git -C <worktree-root> diff --
specs/handoff.md` for a feature, or `git -C <dir> diff -- handoff.md` for a campaign, when the file is tracked, otherwise print each rewritten heading followed by every
appended line verbatim. Close with the one-line reminder that the next session reads State and Next
automatically, from the SessionStart hook and from
`~/projects/moose-factory/Features/<feature>.md` (in a campaign, from the hook's campaign block).
