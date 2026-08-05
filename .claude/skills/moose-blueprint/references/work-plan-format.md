# `#work-plan` format (seventh contract block)

Authoritative spec for the work-plan block `/moose-blueprint` authors and `/moose-build` consumes.

The work plan is a **decomposition, not a schedule**. It names the units of work and the hard
dependencies between them. `/moose-build` passes both to `moose-feature-loop`, which decides what
to dispatch each iteration from the criteria still unmet. Nothing here orders the run.

## Model

- **Unit** — one dispatchable piece of work: `implement` (one class / coherent cluster),
  `test` (one test-plan entry), or `doc` (the doc-plan pages). Each unit carries a
  **self-contained payload** so its agent never re-reads the whole blueprint.
- **Edge** (`deps`) — a *hard* dependency only: derives-from a new class, consumes a
  property/API another new unit declares, or **touches the same file** (two units editing one
  file MUST share an edge — the loop runs edge-free units concurrently, so they have to own
  disjoint files). Style preference, "feels related", or ordering habit are NOT edges.
- **Standing gates** — NOT part of the plan. `/moose-build` owns them and runs them around the
  loop; the blueprint renders them read-only (below) so the reviewer sees the whole run. A
  blueprint can never add, remove, reorder, or edit a gate. Never encode a gate as a dep.

Derivation (owned by `/moose-blueprint`): `implement` units from the grill plan's predicted
files, one per class (single-class features get one unit, `U1`), with edges drawn by the
blueprint skill and ambiguous ones confirmed with the user; `test` units from `#test-plan`
rows (dep = the implement unit(s) whose code the test exercises); one `doc` unit when
`#doc-plan` is `Needed: yes`.

## Machine copy — the JSON island

A real (non-displayed) script element inside the `#work-plan` section:

```html
<script type="application/json" id="work-plan-data">
{
  "version": 1,
  "units": [
    { "id": "U1", "kind": "implement", "agent": "moose-implementer", "deps": [],
      "payload": { "class": "NewClass", "base": "BaseClass",
                   "files": ["src/.../NewClass.C", "include/.../NewClass.h"],
                   "physics_ref": "#physics-u1",
                   "notes": "optional unit-specific instruction a file list can't carry" } },
    { "id": "T1", "kind": "test", "agent": "moose-test-writer", "deps": ["U1"],
      "payload": { "test_plan_ref": "<test name from #test-plan>" } },
    { "id": "D1", "kind": "doc", "agent": "moose-docs-writer", "deps": [],
      "payload": { "doc_plan_ref": "#doc-plan" } }
  ],
  "note": "Gates are intentionally absent: /moose-build appends its standing gates. Status lives in the rendered chips, not here."
}
</script>
```

- `agent` ∈ `moose-implementer` | `moose-test-writer` | `moose-unit-test-writer` | `moose-docs-writer`.
- `physics_ref` points at an anchor `id` inside `#physics` (give each unit's physics paragraph
  an `id="physics-uN"`). `test_plan_ref` is the test's name in `#test-plan`, verbatim.
- The JSON is **declarative only** — no status, no ordering (both derived). It must `JSON.parse`.

## Human view — unit groups + cards + gate strips

Render inside the same `#work-plan` section, above the island:

- One `.group` container per unit kind, in this order: `Implementation — <k> units`, then
  `Tests & docs — <k> units`. Each holds one `.unit` card per unit: id, **status chip**,
  class/test name, agent, `deps:` line, and — only when the JSON has `notes` — a collapsed
  `<details class="unote">`. Order the cards inside a group so a unit follows what it depends
  on; the `deps:` line carries the real constraint.
- A `.gatebar` strip after the implementation group (**gate A**) and after the tests & docs
  group (**gate B**), each labeled `Standing gate <A|B> — appended by /moose-build, not editable
  here`, listing that gate's checks verbatim from `/moose-build`'s "Standing gates" section (copy
  the current text at authoring time — the build skill is the source of truth).
- A legend line: unit-kind dots + the four chip states.

Card skeleton:

```html
<div class="unit implement">
  <div class="uhead"><span class="uid">U1</span><span class="chip">idle</span></div>
  <div class="uname">NewClass</div>
  <div class="uagent">moose-implementer</div>
  <div class="udeps kv">deps: —</div>
  <details class="unote"><summary>notes</summary><p>…</p></details>
</div>
```

## Status chips

Chips replace the `[]`/`[wip]`/`[x]`/`[f]` markers for work-plan content and carry the same
contract: **everything starts idle at design time**; `/moose-build` updates chips in place as it
works, so the blueprint stays the live browser-side ledger.

| State | Markup |
| --- | --- |
| idle | `<span class="chip">idle</span>` |
| running | `<span class="chip wip">running</span>` |
| done | `<span class="chip done">done</span>` |
| failed | `<span class="chip failed">failed</span>` |

Every unit card gets a chip (in `.uhead`, beside the uid — the adjacent uid keeps edit targets
unique); every gate check line gets one as its first element.

## CSS

Add to the `<style>` block (alongside the template's own CSS; uses/extends its variables —
define `--impl/--test/--doc/--gate/--gate-bg/--mock` variants if the template lacks them):

```css
.legend { display:flex; flex-wrap:wrap; gap:.9rem; align-items:center; font-size:.78rem; color:var(--muted); margin:.6rem 0 1rem; }
.dot { display:inline-block; width:.65em; height:.65em; border-radius:50%; margin-right:.35em; }
.groups { display:flex; flex-direction:column; gap:.55rem; margin:1rem 0; }
.group { border:1px solid var(--line); border-radius:10px; padding:.7rem .9rem .85rem; }
.group-label { font-size:.7rem; text-transform:uppercase; letter-spacing:.07em; color:var(--muted); font-weight:700; margin-bottom:.55rem; }
.units { display:grid; grid-template-columns:repeat(auto-fill, minmax(12.5rem, 1fr)); gap:.55rem; }
.unit { border-radius:8px; padding:.5rem .65rem .55rem; border:1px solid var(--line); border-left:3.5px solid var(--muted); background:var(--surface); }
.uhead { display:flex; justify-content:space-between; align-items:center; gap:.4rem; }
.unit .uid { font:.7rem/1 ui-monospace, Menlo, monospace; color:var(--muted); }
.unit .uname { font-weight:650; font-size:.88rem; margin:.15rem 0 .1rem; }
.unit .uagent { font-size:.74rem; color:var(--muted); }
.unit .udeps { font-size:.7rem; margin-top:.3rem; }
.unit.implement { border-left-color:var(--impl); }
.unit.test { border-left-color:var(--test); }
.unit.doc { border-left-color:var(--doc); }
.chip { display:inline-block; font-size:.6rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase; border-radius:999px; padding:.12em .5em; border:1px solid var(--line); color:var(--muted); background:transparent; white-space:nowrap; }
.chip.wip { color:var(--gate); border-color:var(--gate); background:var(--gate-bg); }
.chip.done { color:var(--test); border-color:var(--test); background:var(--test-bg); }
.chip.failed { color:var(--mock); border-color:var(--mock); }
.unit details.unote { margin-top:.35rem; font-size:.75rem; color:var(--muted); }
.unit details.unote summary { cursor:pointer; font-size:.66rem; font-weight:700; text-transform:uppercase; letter-spacing:.06em; }
.gatebar { border:1.5px solid var(--gate); background:var(--gate-bg); border-radius:10px; padding:.55rem .9rem; font-size:.85rem; }
.gatebar .glabel { font-size:.7rem; text-transform:uppercase; letter-spacing:.07em; color:var(--gate); font-weight:800; }
.gatebar li .chip { margin-right:.4rem; background:var(--bg); }
.arrow { text-align:center; color:var(--muted); font-size:.85rem; line-height:1; }
```

## Self-check (blueprint side)

1. JSON island parses; every `deps` id exists; graph is acyclic.
2. No two edge-free units list the same file.
3. Every `#test-plan` row has a test unit; every test unit's `test_plan_ref` resolves.
4. Every `physics_ref` anchor exists in `#physics`.
5. All chips `idle`; both gate strips present, text matching `/moose-build`; gates absent from JSON.
