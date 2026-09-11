# `#work-plan` format (seventh contract block)

The work plan is a decomposition, not a schedule. It names the units of work and the hard
dependencies between them. `/moose-build` passes both to `moose-feature-loop`, which decides
what to dispatch each iteration from the criteria still unmet; nothing here orders the run.

## Units and edges

- A unit is one dispatchable piece of work: `implement` (one class or one coherent cluster),
  `test` (one `#test-plan` row), or `doc` (the `#doc-plan` pages). Its payload is
  self-contained so the agent never re-reads the whole blueprint.
- An edge (`deps`) is a hard dependency only: derives from a new class, consumes a property or
  API another new unit declares, or touches the same file. Two units that edit one file share an
  edge because the loop runs edge-free units concurrently and they must own disjoint files.
  Style preference, "feels related", and ordering habit are not edges.
- Standing gates are not units and never deps. `/moose-build` owns them in
  `<meta-root>/.claude/skills/moose-build/references/standing-gates.md`; the blueprint renders
  them read-only so the reviewer sees the whole run.

Derivation: `implement` units come from the grill plan's predicted files, one per class
(a single-class feature has one unit, `U1`), with edges drawn by `/moose-blueprint` and
ambiguous ones confirmed with the user; `test` units come from `#test-plan` rows (dep = the
implement units whose code the test exercises); one `doc` unit exists when `#doc-plan` says
`Needed: yes`.

## JSON island

A non-displayed script element inside the `#work-plan` section:

```html
<script type="application/json" id="work-plan-data">
{
  "version": 1,
  "units": [
    { "id": "U1", "kind": "implement", "agent": "moose-implementer", "deps": [],
      "payload": { "class": "NewClass", "base": "BaseClass",
                   "files": ["src/.../NewClass.C", "include/.../NewClass.h"],
                   "physics_ref": "#physics-u1",
                   "notes": "optional unit-specific instruction a file list cannot carry" } },
    { "id": "T1", "kind": "test", "agent": "moose-test-writer", "deps": ["U1"],
      "payload": { "test_plan_ref": "<test name from #test-plan>" } },
    { "id": "D1", "kind": "doc", "agent": "moose-docs-writer", "deps": [],
      "payload": { "doc_plan_ref": "#doc-plan" } }
  ],
  "note": "Gates are absent on purpose: /moose-build appends its standing gates. Status lives in the rendered chips, not here."
}
</script>
```

- `agent` is one of `moose-implementer`, `moose-test-writer`, `moose-unit-test-writer`,
  `moose-docs-writer`.
- `physics_ref` names an anchor inside `#physics`; give each unit's physics paragraph
  `id="physics-uN"`. `test_plan_ref` is the test's `<code>` name in `#test-plan`, verbatim.
- The JSON is declarative: no status and no ordering (both are derived). It must `JSON.parse`.

## Rendered view

Inside the same `#work-plan` section, above the island (the template carries the markup with
a comment on every slot):

- One `.group` per unit kind, in this order: `Implementation -- <k> units`, then
  `Tests & docs -- <k> units`. Each holds one `.unit` card per unit: id, status chip,
  class or test name, agent, a `deps:` line, and a collapsed `<details class="unote">` only
  when the JSON has `notes`. Inside a group a unit follows the units it depends on; the `deps:`
  line carries the real constraint.
- A `.gatebar` strip after the implementation group (gate A) and after the tests and docs
  group (gate B), each labeled `Standing gate <A|B> -- appended by /moose-build, not editable
  here`, with one line per `standing-gates.md` row belonging to that gate: row id, criterion,
  check, verbatim as the file reads at write time.
- A legend line: the unit-kind dots and the four chip states.

Card skeleton:

```html
<div class="unit implement">
  <div class="uhead"><span class="uid">U1</span><span class="chip">idle</span></div>
  <div class="uname">NewClass</div>
  <div class="uagent">moose-implementer</div>
  <div class="udeps kv">deps: -</div>
  <details class="unote"><summary>notes</summary><p>...</p></details>
</div>
```

## Status chips

Chips are the work plan's status markers and carry the same contract as `[]`: every chip is
`idle` at design time, and `/moose-build` edits the chip spans in place as work runs, so the
blueprint stays the live browser-side ledger.

| State | Markup |
| --- | --- |
| idle | `<span class="chip">idle</span>` |
| running | `<span class="chip wip">running</span>` |
| done | `<span class="chip done">done</span>` |
| failed | `<span class="chip failed">failed</span>` |

Every unit card carries its chip in `.uhead` beside the uid (the adjacent uid keeps each edit
target unique); every gate check line starts with one.

## Validation

`slice_blueprint.py --check` covers the seven ids, island parsing, unknown deps, cycles,
edge-free units that share a file, and `test_plan_ref` resolution. It does not check
`physics_ref` anchors or the gate strips.
