# blueprint.html format

Inputs: the `moose-grill` plan, the merged `moose-scout` findings, and the user's recorded
decisions. Output: `<worktree-root>/specs/blueprint.html`, one self-contained page filled from
`plan-template.html`. The template ships its own `<style>` block and labels every slot with an
HTML comment; fill the slots and every `{{...}}` token. Tokens inside `<!-- -->` comments
(image slots) may remain; any other `{{` left in a contract block fails the check.

## Contract blocks

`/moose-build` reads seven blocks through `slice_blueprint.py`, each by its exact `id`. The
template already places them; the element carrying the `id` is the complete, authoritative
copy, and content may repeat elsewhere.

| id | Complete content required |
| --- | --- |
| `#summary` | prose (what, why, user-facing knob) + `Repo:` (`moose` \| `moose/modules/<m>` \| `blackbear` \| `isopod`) + `Object kind:` (Kernel, BC, Material, Postprocessor, Action, UserObject, ...) + predicted files to touch as `<code>` paths, split new vs existing: source, `test/`, `unit/` when unit tests were agreed, and doc paths |
| `#physics` | the equation with every symbol defined + validParams shape (param name, `Type`, description; `coupled("var")` entries) + a one-line residual or contribution form (`computeQpResidual`, `computeValue`, `execute`, ...) |
| `#reuse-decisions` | a table with a Decision column, one row per scout finding: `file_path:line`, `ClassName`, what it does in one sentence, Decision (Reuse, Extend, or Parallel with the user's justification), why. No finding: one row with the negative record ("Searched for X, Y, Z; nothing matched"). A failed scout: "Scout failed: <reason>" |
| `#test-plan` | a table, one row per test: name in `<code>`, Tester kind (`Exodiff`, `CSVDiff`, `RunException`, ..., or `gtest` for tests under `unit/`), asserted behavior (an observable consequence, not "runs without error"), mutation rationale (if this line of new code were a no-op, this test fails because ...) |
| `#doc-plan` | `Needed: yes` or `Needed: no`; page path in `<code>` (`<repo>/doc/content/source/<area>/<NewClass>.md`); public surface (which params and behaviors are documented API); `Existing coverage:` every page already documenting the feature and the placement or consolidation the user chose |
| `#out-of-scope` | explicit non-goals, one `<li>` each |
| `#work-plan` | unit cards, chips, gate strips, and the `#work-plan-data` JSON island per [`work-plan-format.md`](work-plan-format.md) |

The parser reads the `Repo:`, `Object kind:`, and `Needed:` labels literally, takes test names
and file paths from `<code>`, and reads the reuse and test blocks as tables. Keep the template's
labels and columns.

## Rules

- Every `file:line` citation appears verbatim as the scout reported it.
- The page is self-contained: no external `http(s)` stylesheet or script, and no CDN math
  script; `inline-katex.js` strips any such link it finds.
- Status markers: `[]` idle, `[wip]` running, `[x]` done, `[f]` failed; chips use the same four states. Everything is idle at design time; `/moose-build` flips them.
- Gate strips are render-only. Read
  `<meta-root>/.claude/skills/moose-build/references/standing-gates.md` at write time and
  render each row for the strip's gate verbatim (id, criterion, check). Gates never appear in
  the JSON island, and a blueprint does not add, remove, reorder, or alter a gate.
- The template has no per-phase task checklist; `#work-plan` is the build plan.

## Physics pairing

When `#physics` holds both a MOOSE pseudocode form (a `computeQpResidual`,
`computeQpJacobian`, or contribution expression) and its math form, render them side by side in
the template's `.physics-pair` block so the reader sees implementation beside equation. Pair only
residual, Jacobian, and contribution overrides; `validParams`, registration, constructor
member-init, and plumbing are never paired. When only one half exists, render that half alone
and do not invent the other.

## Math

Write `$$...$$` (display) and `\(...\)` (inline) in prose only, never inside `<pre>`, `<code>`,
`<script>`, or `<style>`. After saving, run:

```
node <meta-root>/.claude/skills/moose-blueprint/references/inline-katex.js <worktree-root>/specs/blueprint.html
```

It renders each equation with MOOSE's vendored KaTeX
(`<worktree-root>/moose/framework/doc/content/contrib/katex/`, no npm install) and inlines the
fonts, so the page renders offline and matches the MOOSE docs. When KaTeX is absent, the LaTeX
stays as plain text and the blueprint is still valid. It is safe to re-run after a resume.

## Metadata

`created` = `date -u +%Y-%m-%dT%H:%M:%SZ` at first write and is never overwritten. `modified`
starts equal to `created`; `commits`, `back refs`, and `forward refs` start as `-` (nothing
exists at design time); `agent name` is `Claude via /moose-blueprint`. On resume, append to the
`modified`, `commits`, and `agent name` lists (comma-separated). There is no session id field.

## Validation commands

From `#test-plan`: the `./run_tests --re=<names>` commands that prove the feature end to end,
plus build clean. Markers `[]`.

## Questionables

One `<details>` per open question, deferred item, or parked decision from the grill, with the
assumption or rationale in the answer. When there are none, one entry that says so.
