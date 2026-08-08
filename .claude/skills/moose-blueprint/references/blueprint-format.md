# blueprint.html format

Authoritative format for `/moose-blueprint` **step 6**. The inputs are the `moose-grill` plan,
the merged `moose-scout` findings, and the user's recorded decisions; the output is the single
deliverable `specs/blueprint.html`. The HTML skeleton comes from this skill's own
`references/plan-template.html` (a pinned copy of the global blueprint template) — it ships **no
CSS**, so authoring the whole `<style>` block is part of step 6: a `:root` palette defining
`--bg`, `--surface`, `--line`, `--muted`, `--impl`, `--test`, `--test-bg`, `--doc`, `--gate`,
`--gate-bg`, `--mock` (the snippets below and in `work-plan-format.md` consume all eleven), plus
rules for the template's own classes — `.meta`, `.files`, `.tag`, `.phase`, `.checklist`,
`.status`, `.loop`, `.qa-answer`. `.status` is the marker `/moose-build` flips, so style it to
read as a marker at a glance. This file defines how to fill the skeleton.

## Hard rules (non-negotiable)

- **Pure formatter — never re-explore.** Codegraph already ran (`moose-grill` + `moose-scout`)
  to produce the plan. Step 6 only formats it — read only the local template and `/moose-build`'s
  `standing-gates.md` (below); never invoke the generic blueprint skill's workflows (its Analyze /
  Explore / Design steps are generic grep, no codegraph, and its build workflow belongs to
  /moose-build's territory).
- **Fill every `{{placeholder}}`.** The only `{{...}}` allowed to remain in the output are the
  image-slot tokens *inside* `<!-- ... -->` comments (blueprint leaves these for manual fill).
- **Self-contained.** All CSS inline; **no external `http(s)` stylesheet/script links**. Math is
  rendered offline by `inline-katex.js` (see below) — never add a CDN `<script>`.
- **Preserve every `file:line` citation verbatim** from the Reuse decisions.
- **Status markers stay `[]` and status chips stay `idle`.** The build has not run at design time.
- **Standing gates are render-only.** Read
  `.claude/skills/moose-build/references/standing-gates.md` (from this file:
  `../../moose-build/references/standing-gates.md`) at authoring time — every time — and render
  the `#work-plan` gate strips from what it says right now, **verbatim**. It is the gates' one
  home and it grows; a retyped snapshot goes stale and the reviewer then reviews gates that no
  longer exist. Gates never appear in the JSON island, and a blueprint cannot add, remove,
  reorder, or alter a gate.

## Contract blocks (the machine interface)

`/moose-build` parses seven blocks, each identified by an exact `id` attribute. Attach each `id`
to the template container that carries that content — placement in the visual layout is free,
and content may additionally appear elsewhere (e.g. per-phase Testing Strategy), but the block
carrying the `id` is the authoritative, complete copy. If the template layout has no natural
home for a block, add a `Notes` subsection for it.

| id | Complete content required |
| --- | --- |
| `#summary` | prose (what / why / user-facing knob) + **Repo** (`moose` \| `moose/modules/<m>` \| `blackbear` \| `isopod`) + **Object kind** (Kernel / BC / Material / Postprocessor / Action / UserObject / …) + **Predicted files to touch**, split new vs existing — source, `test/`, `unit/` (when unit tests were agreed), and doc paths |
| `#physics` | equation (LaTeX or plain math, every symbol defined) + **validParams shape** (param name, `Type`, description; `coupled("var")` entries) + one-line **residual / contribution form** (`computeQpResidual`, `computeValue`, `execute`, …) |
| `#reuse-decisions` | one entry per scout finding: `file_path:line` — `ClassName`, what it does (one sentence), **Decision** (Reuse / Extend / Parallel — for Parallel include the user's justification), why; if none: the negative record ("Searched for X, Y, Z — nothing matched."); failed scouts noted as "Scout failed: <reason>" |
| `#test-plan` | one entry per test: name, Tester kind (`Exodiff` / `CSVDiff` / `RunException` / … — or `gtest` for unit tests under `unit/`), asserted behavior (an observable consequence, not "runs without error"), mutation rationale (if `<line of new code>` were no-op'd, this test fails because …) |
| `#doc-plan` | **Needed:** yes / no; page path (`<repo>/doc/content/source/<area>/<NewClass>.md`); public surface (which params/behaviors are documented API); **Existing coverage:** every page already documenting the feature, plus the placement/consolidation the user chose |
| `#out-of-scope` | explicit non-goals, one per line |
| `#work-plan` | work units + dependency edges + JSON island `#work-plan-data`, per [`work-plan-format.md`](work-plan-format.md) — grouped unit cards / chips / read-only standing-gate strips |

## Template slot mapping

| Content | `blueprint` template target |
| --- | --- |
| Feature name | `{{PLAN_TITLE}}` |
| Summary prose | `Purpose` (one-line intent) + `Problem` (why needed / what's missing) + `Solution` (the object + approach) |
| Repo + Object kind | stated in `Solution`; also reflected in the title |
| Predicted files to touch | `Relevant Files` — split: files that already exist and are reused/templated (the Reuse-decision files, with their `file:line`) → **Existing**; brand-new files this feature creates → **New** |
| Equation | `Notes` → "Physics & signature". Keep LaTeX/plain math verbatim; define each symbol. |
| validParams shape | `Notes` → "Physics & signature" → params list/table |
| Residual / contribution form | `Notes` → "Physics & signature" |
| Reuse decisions (one per finding) | `Notes` → "Reuse decisions": `file:line`, class, what it does, Decision, Why — citations verbatim. Cited files also appear under Relevant Files → Existing. |
| Test plan (one per test) | the `#test-plan` block, placement per **Contract blocks** |
| Doc plan | the `doc` unit in `#work-plan`; note in `Solution` if `Needed: yes` |
| Out of scope | `Notes` → "Out of scope" |
| Work plan | its own section, directly after `#summary` |

## Code ↔ math pairing (Physics & signature)

When the physics content supplies **both** a MOOSE pseudocode form (a `computeQpResidual` /
`computeQpJacobian` / contribution expression, e.g. `_test[_i][_qp] * (...)`) **and** a math form,
render them together as a `.physics-pair` block so the reader sees implementation ↔ equation:

```html
<div class="physics-pair">
  <div class="pp-code"><div class="pp-label">intended computeQpResidual()</div>
    <pre><code>R_k = _test[_i][_qp] * (...);</code></pre></div>
  <div class="pp-math"><div class="pp-label">residual form</div>
    $$ R_k = \psi_i\,[\,\rho\,c_p\,(\mathbf{n}\cdot\mathbf{v})\,n_k + \dots\,] $$</div>
</div>
```

with this CSS in the `<style>` block:

```css
.physics-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; align-items: stretch; margin: 1rem 0; }
@media (max-width: 760px) { .physics-pair { grid-template-columns: 1fr; } }
.physics-pair .pp-label { font-size: .68rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 700; margin-bottom: .35rem; }
.physics-pair pre { margin: 0; height: 100%; }
.physics-pair .pp-math { border: 1px solid var(--line); border-radius: 8px; background: var(--surface); padding: .7rem .9rem; display: flex; flex-direction: column; justify-content: center; }
```

**When it makes sense:** residual / Jacobian / contribution-computing overrides only. **Never** pair
`validParams`, registration, ctor member-init, or plumbing. If only one half exists (math
without a code sketch, or vice versa), render that half normally — **do not fabricate** the other.

## KaTeX rendering (self-contained, no install)

Write math as `$$…$$` (display) / `\(…\)` (inline) **in prose, never inside `<pre>`/`<code>`**. After
authoring + saving the HTML, run:

```
node <skill-dir>/references/inline-katex.js <worktree-root>/specs/blueprint.html
```

It `require()`s MOOSE's vendored KaTeX 0.13.5 (`<worktree>/moose/framework/doc/content/contrib/katex/`,
no npm install), pre-renders each equation to static HTML, and base64-inlines the woff2 fonts —
leaving one offline, self-contained file that renders even with JS disabled, matching the MOOSE docs.
Graceful degrade: if KaTeX isn't found, LaTeX is left as plain text (still a valid blueprint).

## Metadata header

- Every field except `created` is an append-only comma-separated list — append on resume, never overwrite
- `created` = `date -u +%Y-%m-%dT%H:%M:%SZ` at generation time; `modified` = same (initial)
- `commits` = — (none at design time)
- `agent name` = e.g. `Claude via /moose-blueprint`
- `session id` = current session id
- `back refs` = —
- `forward refs` = —

## Work plan (replaces the template's "Implementation Phases" checklist)

The `#work-plan` block IS the build plan — author it per
[`work-plan-format.md`](work-plan-format.md), which owns unit derivation, edges, cards, chips,
and gate strips. Do **not** also author the template's per-phase task checklists: drop the
template's `#phases` section entirely.

## Global Validation Commands

From the Test plan: the run commands / Testers that prove the feature end-to-end (e.g.
`./run_tests --re=<names>`) plus "build clean". Markers `[]`.

## Questionables

Surface each explicit open question, deferred item, or "parked pending …" decision from the
grill in the Questionables section. `QUESTIONABLE` defaults true in the blueprint skill, so
the section is included.
