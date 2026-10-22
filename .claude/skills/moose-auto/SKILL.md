---
name: moose-auto
description: Runs MOOSE features end to end with no human gate before ship. For each task it scaffolds a worktree with /new-feature, then dispatches one background session through factory start that runs /moose-blueprint --auto (which settles every fork and approves its plan as "auto") and then /moose-build --auto. Each run ends at a green, reviewed worktree with one suggested commit; /moose-ship stays Max's gate. Use for "/moose-auto <task> [<task> ...]", "run these autonomously", "auto blueprint and build", "build these without asking me". Manual invoke only.
disable-model-invocation: true
argument-hint: "<name>: <idea> [; <name>: <idea> ...]  |  --from <issues.json> <ID> [<ID> ...]"
effort: medium
allowed-tools:
  - Bash
  - Read
  - Write
  - Skill
  - AskUserQuestion
---

# /moose-auto

Start one autonomous pipeline per task. Each pipeline is one background session in its own
feature worktree: `/moose-blueprint --auto`, then `/moose-build --auto`. No session asks Max
anything. Each one stops at a suggested commit, a `STALLED(...)`, or a `BLOCKED(...)`, and the card
on the board shows which. `ship` and `pr_ready` stay Max's gates. This skill writes no code and
never commits.

`$FACTORY` is `~/projects/moose_stack/factory/factory`, by absolute path. A worktree has no
`factory/`.

## Tasks

`$ARGUMENTS` names the tasks in one of two forms:

- `<name>: <idea>`, separated by `;`. The idea is one paragraph, or an issue URL.
- `--from <issues.json> <ID> ...`. Read the file: a JSON list of `{id, title, body}`. Each ID picks
  one entry. The idea is the title, a blank line, then the body.

A name is kebab-case and matches `^[a-z0-9][a-z0-9-]*$`, because it becomes a branch on four
repositories. With `--from`, make the name from the ID and the title: `<id>-<3 to 5 title words>`,
lower case, joined with `-`. Example: `33902-fix-the-nodal-bc-sign`.

With no tasks, ask for them with `AskUserQuestion`. Then show the list (name and one-line idea) and
ask one time to start them all. This is the only question; after the yes, ask nothing.

## Preflight

Do these once, before the first task. Stop at the first failure and report it.

1. `$FACTORY doctor`. Report a failed line; continue unless it names the vault.
2. `$FACTORY config`. Read `max_concurrent_sessions` and `max_builds_per_day`.
3. Count the live background sessions (`claude agents --json`). When the new tasks would pass
   `max_concurrent_sessions`, start only as many as fit and list the rest as not started.

## Per task

Run these steps for one task at a time. A failed step skips that task, never the rest.

1. `Skill(new-feature)` with `<name>`. Its preflight refuses a branch that exists on any of the
   four repositories; that is a failed step, and the reason goes in the report. A worktree that
   exists already is skipped with "exists": Max runs `/moose-build --auto` in it by hand.
2. `$FACTORY board`, so the card exists. `new-feature` runs it too; a second run is harmless.
3. Write the idea to `~/projects/moose-worktrees/<name>/specs/auto-idea.md`. The session reads it
   there, so the idea needs no shell quoting.
4. Write the session prompt to `~/projects/moose-worktrees/<name>/specs/auto-prompt.md`: the text
   below, with `<name>` replaced by the feature name. Keep the first line as written: `factory
   start` recognises an autonomous run by it and lets it start below the approved lane.

   ```text
   Autonomous run for <name>. No human is present. Ask nothing.
   1. Read specs/auto-idea.md. Run /moose-blueprint --auto with that idea.
   2. If it printed AUTO_APPROVED, run /moose-build --auto. Otherwise stop.
   3. Run ~/projects/moose_stack/factory/factory board. End with one line: the final status of the build, or the BLOCKED line.
   ```

5. Dispatch it. `factory start` takes the lease, checks the caps and the disk floor, launches the
   background session in the worktree, and records it on the card:

   ```sh
   $FACTORY start <name> --prompt "$(cat ~/projects/moose-worktrees/<name>/specs/auto-prompt.md)"
   ```

   A refusal is a failed step: report its first line. Record the short id that the command prints.

## Report

One table: name, worktree path, short id, and "started" or the reason it was skipped. Then the
commands to follow the runs: `$FACTORY attach <name>`, `$FACTORY logs <name>`, and
`$FACTORY board`. Say that each card carries the `auto` flag once its plan is approved, that the
auto answers are under `## Needs clarification` in each blueprint, and that `specs/blueprint.html`
still shows every decision, so a changed answer goes back through `/moose-blueprint` Respond and a
fresh `/moose-build`.

## Rules

- Never grant `ship`, `pr_ready` or `teardown`, and never tell a session to.
- Never pass `--force` to `factory start` or anything else.
- Never run `/moose-ship`. Shipping an auto build is Max's decision, made after he reads the
  blueprint the `auto` flag points at.
