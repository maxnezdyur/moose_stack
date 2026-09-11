---
name: moose-blueprint
description: Turns a feature idea into specs/blueprint.html for /moose-build. Grills the user through moose-grill, scouts moose, blackbear, and isopod for reusable code with moose-scout agents, halts on near-matches, and writes the seven-block blueprint. Use for "/moose-blueprint <idea>", "plan this MOOSE feature", "write a blueprint", "spec this kernel, material, or postprocessor".
disable-model-invocation: true
argument-hint: "<feature idea>"
effort: high
---

# /moose-blueprint

Goal: a `specs/blueprint.html` that a human can review in a browser and that `/moose-build`
can parse. The blueprint is the only file this skill writes; it edits no code, runs no builds,
tests, or formatters, does not commit or push, and does not invoke `/moose-build`. The human
review of the written blueprint is the hand-off.

`$ARGUMENTS` is the idea. When it is empty, ask for it with `AskUserQuestion`.

## Preconditions

This skill runs inside a `/new-feature` worktree: walk up from the cwd to a directory whose
`.git` is a file (a worktree, not a clone) beside `moose/`, `blackbear/`, and `isopod/`.
Outside one, refuse with "Run /new-feature first; this skill only runs inside a feature
worktree." That directory is `<worktree-root>` below. It owns its own `.claude/`, so it is
also `<meta-root>` for every script path here.

When `<worktree-root>/specs/blueprint.html` exists, ask with `AskUserQuestion`: Resume (keep
it, grill only the blocks that are empty or placeholders), Restart (overwrite at the write
step), or Cancel. Placeholder blocks are what Resume grills, so the validator's "is a
placeholder" lines are expected on an unfinished blueprint. A blueprint whose contract ids are
missing or whose `#work-plan-data` island does not parse is restarted with a warning.

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

Repeat grill, scout, halt with tighter questions until each of the seven contract blocks
(`references/blueprint-format.md`) can be filled with at least one specific fact. Then offer
with `AskUserQuestion`: write it, keep grilling about a named section, or cancel ("No blueprint
saved. Re-run when ready.").

Writing is formatting, not exploring: fill `references/plan-template.html` per
`references/blueprint-format.md` and `references/work-plan-format.md` from the grill plan, the
scout findings, and the user's decisions. The only file read outside this skill at write time
is `<meta-root>/.claude/skills/moose-build/references/standing-gates.md`, for the gate strips.
`mkdir -p <worktree-root>/specs`, save, render the math with
`node <meta-root>/.claude/skills/moose-blueprint/references/inline-katex.js <worktree-root>/specs/blueprint.html`,
then validate:

```
python3 <meta-root>/.claude/skills/moose-build/scripts/slice_blueprint.py --check <worktree-root>/specs/blueprint.html
```

Fix each reported problem and re-run until it prints `OK`.

## Done

Tell the user: "Blueprint written to `<worktree-root>/specs/blueprint.html`; open it in a
browser to review. Edit if needed, then run `/moose-build specs/blueprint.html`."
