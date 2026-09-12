# blueprint.md format

The blueprint is one markdown file, `<worktree-root>/specs/blueprint.md`. It is the source of
truth: agents read it whole (about 15 KB), the user edits it by hand, and `/moose-build` updates
the status fields in its JSON block. `specs/blueprint.html` is a generated view: the
`render-blueprint.sh` hook runs pandoc with `blueprint.template.html` and `workplan.html` from
this directory whenever `blueprint.md` is written (MathML for equations, so the page is
self-contained and renders in Safari). Never edit the HTML. `example-blueprint.md` here is a
complete, real blueprint; write yours in the same shape.

## Frontmatter

```yaml
---
title: <feature name as a heading>
feature: <worktree name, kebab-case>
repo: moose | moose/modules/<m> | blackbear | isopod
scope: moose | blackbear | isopod         # build scope (a module scope maps to moose)
object_kind: "<Kernel, BC, Material, Postprocessor, Action, UserObject, ...>"   # quote it if it contains ': '
status: draft | approved | building | built
created: YYYY-MM-DD
---
```

`status: approved` is legal only when every box under `## Needs clarification` is checked.

## Sections, in this order, with these exact `##` headings

| heading | content |
|---|---|
| `## Summary` | what, why, the user-facing knob; then `**Files.**` listing new and existing files to touch as `code` paths (source, `test/`, `unit/` when agreed, doc pages), each new class tagged with its unit id |
| `## Physics` | the equations in `$$ ... $$` with every symbol defined (a symbol table works well), validParams shape as a table (param, type, default, purpose), the residual or contribution form, and one `### <Uid> <ClassName>: <role>` subsection per implement unit so a builder can read only its own |
| `## Reuse decisions` | a table (where, what, decision), one row per scout finding; the decision column is bold and one of **Reuse as-is**, **Reuse (pattern)**, **Extend**, **Parallel** (with the user's one-sentence justification), **Rejected**, **No reuse**; then a `Negative searches:` line naming what was searched and found nothing; a failed scout is recorded as "Scout failed: <reason>" |
| `## Test plan` | one `### <name> (<Tester>)` per test with three bullets: `Requirement:` one sentence in MOOSE's `The system shall ...` form, copied verbatim into the spec's `requirement =`; `Asserts:` the observable consequence (never "runs without error"); `Mutation:` what fails if this line of new code were a no-op. `gtest` is the Tester for tests under `unit/` |
| `## Doc plan` | `Needed: yes` or `Needed: no`; the page paths; `Existing coverage:` every page already documenting the feature and the placement the user chose |
| `## Out of scope` | explicit non-goals, one bullet each |
| `## Needs clarification` | `- [ ]` per open question from the grill; when answered, tick it and append the answer |
| `## Work plan` | exactly one fenced `json` block, below |
| `## Amendments` | append-only dated log |

Every `file:line` citation appears verbatim as the scout reported it.

## The work-plan JSON

```json
{
  "version": 2,
  "units": [
    { "id": "U1", "kind": "implement", "agent": "moose-implementer", "deps": [], "status": "idle",
      "class": "NewClass", "base": "BaseClass",
      "files": ["moose/framework/include/.../NewClass.h", "moose/framework/src/.../NewClass.C"] },
    { "id": "T1", "kind": "test", "agent": "moose-test-writer", "deps": ["U1"], "status": "idle",
      "test": "test_name", "notes": "optional" },
    { "id": "D1", "kind": "doc", "agent": "moose-docs-writer", "deps": [], "status": "idle" }
  ],
  "gates": {
    "A1": { "criterion": "C1", "status": "idle" },
    "B2": { "criterion": "C2/C3", "status": "idle" },
    "B3": { "criterion": "C4", "status": "idle" },
    "B4": { "criterion": "C5", "status": "idle" },
    "B5": { "criterion": "C6", "status": "idle" },
    "B6": { "criterion": "DG", "status": "idle" }
  }
}
```

- `kind` is `implement`, `test`, or `doc`; `agent` is `moose-implementer`, `moose-test-writer`,
  `moose-unit-test-writer`, or `moose-docs-writer`.
- An edge in `deps` is a hard dependency only: derives from a new class, consumes a property
  another new unit declares, or touches the same file. Two units that edit one file must share
  an edge, because edge-free units run concurrently. Style preference or ordering habit is not
  an edge. The graph is acyclic.
- A `test` unit's `test` matches a `### <name>` heading in the test plan verbatim. An `implement`
  unit's `class` matches its `### <Uid> <ClassName>` subsection in the physics section.
- `status` is `idle`, `running`, `done`, or `failed`. Everything is `idle` at design time.
  `/moose-build` flips unit and gate statuses by editing this block; nothing else in the file
  changes during a build except `status:` in the frontmatter and the amendments log.
- `gates` carries the standing gates from
  `<meta-root>/.claude/skills/moose-build/references/standing-gates.md` (ids and criteria as
  that file lists them at write time). A blueprint never adds, removes, or alters a gate; the
  rendered page draws them as strips.

## Math and code

Display math in `$$ ... $$` on its own line, inline math in `$ ... $`. Code in fenced blocks
with a language (`cpp`, `python`, `text` for HIT input). Do not put math inside code fences.
Tables are pipe tables; a literal `|` inside a cell is `\|`.

## Checks before you stop

Read the file back and confirm: the frontmatter fields above; the nine `##` headings in order,
none a placeholder; one fenced `json` block that parses; every `deps` id exists and the graph has
no cycle; edge-free units list disjoint files; each `test` unit names a `###` test heading and
each `implement` unit a `###` physics subsection; every `Requirement:` line is one sentence; and
`status: approved` only with every clarification box ticked. When pandoc is installed the hook
has written `specs/blueprint.html`; when it is not, say so (the markdown is still the blueprint).
