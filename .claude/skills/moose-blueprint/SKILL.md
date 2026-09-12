---
name: moose-blueprint
description: Turns a feature idea into specs/blueprint.md for /moose-build (the HTML view renders itself). Grills the user through moose-grill, scouts moose, blackbear, and isopod for reusable code with moose-scout agents, halts on near-matches, and writes the seven-block blueprint. Use for "/moose-blueprint <idea>", "plan this MOOSE feature", "write a blueprint", "spec this kernel, material, or postprocessor".
disable-model-invocation: true
argument-hint: "<feature idea>"
effort: high
---

# /moose-blueprint

Goal: a `specs/blueprint.md` that agents read whole and that the render hook turns into
`specs/blueprint.html` for the human to review in a browser. The blueprint is the only file this
skill writes; it edits no code, runs no builds,
tests, or formatters, does not commit or push, and does not invoke `/moose-build`. The human
review of the written blueprint is the hand-off.

`$ARGUMENTS` is the idea. When it is empty, ask for it with `AskUserQuestion`.

## Preconditions

This skill runs inside a `/new-feature` worktree: walk up from the cwd to a directory whose
`.git` is a file (a worktree, not a clone) beside `moose/`, `blackbear/`, and `isopod/`.
Outside one, refuse with "Run /new-feature first; this skill only runs inside a feature
worktree." That directory is `<worktree-root>` below. It owns its own `.claude/`, so it is
also `<meta-root>` for every script path here.

When `<worktree-root>/specs/blueprint.md` exists, ask with `AskUserQuestion`: Resume (keep
it, grill only the sections that are empty or placeholders), Restart (overwrite at the write
step), or Cancel. A blueprint whose headings are missing or whose fenced JSON does not parse
is restarted with a warning.

## Grill

`Skill(moose-grill)` with the idea. It returns the base class, required overrides, validParams
shape, coupling, residual math, pitfalls, and predicted files. Consume that plan as given and
do not ask the user what the codebase can answer. If it returns `Base class: undetermined`,
grill three axes yourself for that round: object kind and base class, inputs and outputs,
physics and math. Re-invoke it only when a scout finding contradicts the plan (a better base
class, for example); otherwise carry the plan forward and grill the remaining gaps directly.

Decomposition into work-plan units is this skill's job: one `implement` unit per new class
from the predicted files, edges only for hard dependencies (derives from, consumes a property
another new unit declares, or touches the same file), and ambiguous edges confirmed with the
user during the grill.

## Scout

Spawn one `moose-scout` per independent search angle (`subagent_type: "moose-scout"`,
`run_in_background: true`, all `Agent` calls in one message), at most four per round; queue
further angles for the next round. Each brief carries the artifact kind (`cpp`, `test`,
`unit`, `doc`), the operator or equation in full, the distinguishing properties that separate
it from name-cousins (coefficient rank, AD vs non-AD, subdomain vs whole mesh), the scope (a
repo or the worktree), negative criteria (what does not count, including grill findings already
ruled out), and the sibling angles other scouts cover. An angle briefed by keywords alone comes
back with naming false positives. Tell the user in one line which angles are running, keep
grilling while they run, and merge findings as they land.

## Reuse halt

An exact or near match stops the loop: surface `file:line` and one line of what it does, then
decide with `AskUserQuestion` between reuse as-is, extend, write parallel (the user gives a
one-sentence justification that goes in the blueprint), or abandon the idea. A close but
indirect match is recorded and the next round asks extend or write fresh. No match is recorded
as a negative result naming what was searched. When the plan restructures only one side of an
AD/non-AD pair, record the divergence, the unification follow-up, and the existing users that
follow-up would migrate. Findings are advisory; the user owns every reuse decision. A scout
that returns BLOCKED or nothing is noted as "Scout failed: <reason>" under reuse decisions and
never filled in from memory.

## Converge and write

Repeat grill, scout, halt with tighter questions until each section of
`references/blueprint-format.md` can be filled with at least one specific fact and every
`## Needs clarification` item is answered. Then offer
with `AskUserQuestion`: write it, keep grilling about a named section, or cancel ("No blueprint
saved. Re-run when ready.").

Writing is formatting, not exploring: write `<worktree-root>/specs/blueprint.md` per
`references/blueprint-format.md`, in the shape of `references/example-blueprint.md`, from the
grill plan, the scout findings, and the user's decisions. The only file read outside this skill
at write time is `<meta-root>/.claude/skills/moose-build/references/standing-gates.md`, whose
rows seed the `gates` object of the work-plan JSON. `mkdir -p <worktree-root>/specs` and save;
the `render-blueprint.sh` hook writes `specs/blueprint.html` (pandoc, MathML). Then run the
"Checks before you stop" list in `blueprint-format.md` against the file you wrote and fix what
fails.

## Done

Tell the user: "Blueprint written to `<worktree-root>/specs/blueprint.md`; open
`specs/blueprint.html` in a browser to review. Edit the markdown if needed (the page re-renders
on save), then run `/moose-build`."
