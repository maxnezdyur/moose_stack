# blueprint.html format

Authoritative format for `/moose-blueprint` **step 6**. The inputs are the `moose-grill` plan,
the merged `moose-scout` findings, and the user's recorded decisions; the output is the single
deliverable `specs/blueprint.html`. The HTML skeleton and CSS come from this skill's own
`references/plan-template.html` (a pinned copy of the global blueprint template); this file
defines how to fill it.

## Hard rules (non-negotiable)

- **Pure formatter — never re-explore.** Codegraph already ran (`moose-grill` + `moose-scout`)
  to produce the plan. Step 6 only formats it — read only the local template; never invoke the
  generic blueprint skill's workflows (its Analyze / Explore / Design steps are generic grep,
  no codegraph, and its build workflow belongs to /moose-build's territory).
- **Fill every `{{placeholder}}`.** The only `{{...}}` allowed to remain in the output are the
  image-slot tokens *inside* `<!-- ... -->` comments (blueprint leaves these for manual fill).
- **Self-contained.** All CSS inline; **no external `http(s)` stylesheet/script links**. Math is
  rendered offline by `inline-katex.js` (see below) — never add a CDN `<script>`.
- **Preserve every `file:line` citation verbatim** from the Reuse decisions.
- **Status markers stay `[]` and status chips stay `idle`.** The build has not run at design time.
- **Standing gates are render-only.** The `#work-plan` gate strips copy `/moose-build`'s
  "Standing gates" text verbatim and never appear in the JSON island — a blueprint cannot add,
  remove, or alter a gate.

## Contract blocks (the machine interface)

`/moose-build` parses seven blocks, each identified by an exact `id` attribute. Attach each `id`
to the template container that carries that content — placement in the visual layout is free,
and content may additionally appear elsewhere (e.g. per-phase Testing Strategy), but the block
carrying the `id` is the authoritative, complete copy. If the template layout has no natural
home for a block, add a `Notes` subsection for it.

| id | Complete content required | Natural template home |
| --- | --- | --- |
| `#summary` | prose (what / why / user-facing knob) + **Repo** (`moose` \| `moose/modules/<m>` \| `blackbear` \| `isopod`) + **Object kind** (Kernel / BC / Material / Postprocessor / Action / UserObject / …) + **Predicted files to touch**, split new vs existing — source, `test/`, `unit/` (when unit tests were agreed), and doc paths | `Purpose`/`Problem`/`Solution` block |
| `#physics` | equation (LaTeX or plain math, every symbol defined) + **validParams shape** (param name, `Type`, description; `coupled("var")` entries) + one-line **residual / contribution form** (`computeQpResidual`, `computeValue`, `execute`, …) | `Notes` → "Physics & signature" |
| `#reuse-decisions` | one entry per scout finding: `file_path:line` — `ClassName`, what it does (one sentence), **Decision** (Reuse / Extend / Parallel — for Parallel include the user's justification), why; if none: the negative record ("Searched for X, Y, Z — nothing matched."); failed scouts noted as "Scout failed: <reason>" | `Notes` → "Reuse decisions" |
| `#test-plan` | one entry per test: name, Tester kind (`Exodiff` / `CSVDiff` / `RunException` / … — or `gtest` for unit tests under `unit/`), asserted behavior (an observable consequence, not "runs without error"), mutation rationale (if `<line of new code>` were no-op'd, this test fails because …) | a consolidated test table in `Notes` or the `Validation Commands` area |
| `#doc-plan` | **Needed:** yes / no; page path (`<repo>/doc/content/source/<area>/<NewClass>.md`); public surface (which params/behaviors are documented API) | the Docs phase, or `Notes` |
| `#out-of-scope` | explicit non-goals, one per line | `Notes` → "Out of scope" |
| `#work-plan` | work units + dependency edges + JSON island `#work-plan-data`, per [`work-plan-format.md`](work-plan-format.md) — units/waves/chips/read-only standing-gate strips | its own section, directly after `#summary` |

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
| Test plan (one per test) | the `#test-plan` table; echoed into each phase's `Testing Strategy` + the global `Validation Commands` |
| Doc plan | a build phase task ("author doc page X"); note in `Solution` if `Needed: yes` |
| Out of scope | `Notes` → "Out of scope" |

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

## Work plan (replaces the v1 "Implementation Phases" checklist)

The `#work-plan` block IS the build plan — author it per
[`work-plan-format.md`](work-plan-format.md): implement units from the grill plan's *Work
units*, test units from `#test-plan`, a doc unit when `#doc-plan` is `Needed: yes`; edges only
for hard dependencies; waves computed; chips `idle`; gate strips read-only. Do **not** also
author the template's per-phase task checklists — the unit cards (plus their optional `notes`)
replace them; drop the template's `#phases` section or leave it out entirely.

## Global Validation Commands

From the Test plan: the run commands / Testers that prove the feature end-to-end (e.g.
`./run_tests --re=<names>`) plus "build clean". Markers `[]`.

## Questionables

Surface each explicit open question, deferred item, or "parked pending …" decision from the
grill in the Questionables section. `QUESTIONABLE` defaults true in the blueprint skill, so
the section is included.
