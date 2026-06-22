# spec.md → blueprint.html mapping

Authoritative mapping consumed by `/moose-design-feature` **step 6b**. It says *what spec
content goes into which template slot*. The HTML skeleton, CSS, and formatting rules come
from the `blueprint` skill's **Plan Template** (`~/.claude/skills/blueprint/SKILL.md`), read
at runtime — this file does not duplicate them.

## Hard rules (non-negotiable)

- **Pure formatter — never re-explore.** Codegraph already ran (`moose-grill` + `moose-scout`)
  to produce the spec. Step 6b only formats it. It must **never** run the blueprint skill's
  `workflows/create-plan.md` steps 1–3 (Analyze / Explore / Design — generic grep, no codegraph)
  nor `workflows/build-plan.md`. Read the template + Instructions only.
- **Fill every `{{placeholder}}`.** The only `{{...}}` allowed to remain in the output are the
  image-slot tokens *inside* `<!-- ... -->` comments (blueprint leaves these for manual fill).
- **Self-contained.** All CSS inline; **no external `http(s)` stylesheet/script links**. Math is
  rendered offline by `inline-katex.js` (see below) — never add a CDN `<script>`.
- **Preserve every `file:line` citation verbatim** from the Reuse decisions section.
- **Status markers stay `[]`.** The build has not run at design time.

## Section mapping

| `spec.md` source | `blueprint` template target |
| --- | --- |
| `# <feature name>` (H1) | `{{PLAN_TITLE}}` |
| Summary prose | `Purpose` (one-line intent) + `Problem` (why needed / what's missing) + `Solution` (the object + approach) |
| Summary → **Repo** + **Object kind** | stated in `Solution`; also reflected in the title |
| Summary → **Predicted files to touch** | `Relevant Files` — split: files that already exist and are reused/templated (the Reuse-decision files, with their `file:line`) → **Existing**; brand-new files this feature creates → **New** |
| Physics / math + signature → equation | `Notes` → "Physics & signature" subsection. Keep LaTeX/plain math verbatim; define each symbol. |
| Physics → **validParams shape** | `Notes` → "Physics & signature" → params list/table |
| Physics → **Residual / contribution form** | `Notes` → "Physics & signature" |
| Reuse decisions (one per finding) | `Notes` → "Reuse decisions" subsection: `file:line`, class, what it does, Decision, Why — citations verbatim. Cited files also appear under Relevant Files → Existing. |
| Test plan (one per test) | each phase's `Testing Strategy` + the global `Validation Commands` (Tester kind + asserted behavior + mutation rationale) |
| Doc plan | a build phase task ("author doc page X"); note in `Solution` if `Needed: yes` |
| Out of scope | `Notes` → "Out of scope" subsection |

## Code ↔ math pairing (Physics & signature)

When the spec's Physics section supplies **both** a MOOSE pseudocode form (a `computeQpResidual` /
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
`validParams`, registration, ctor member-init, or plumbing. If the spec gives only one half (math
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

- `created` = `date -u +%Y-%m-%dT%H:%M:%SZ` at generation time; `modified` = same (initial)
- `commits` = — (none at design time)
- `agent name` = e.g. `Claude via /moose-design-feature`
- `session id` = current session id
- `back refs` = `specs/spec.md` (this blueprint is rendered from it)
- `forward refs` = —

## Implementation Phases (derived, forward-looking BUILD checklist)

Author the phases from the spec's **Predicted files** + **Test plan** as the plan the eventual
`/moose-build` will follow. Include only the phases the spec needs:

1. **Implementation** — one task per source file (`.C` / `.h` / `.py`).
2. **Regression tests** — one task per `tests` spec / `.i` / gold file.
3. **Docs** — one task per doc page (only if Doc plan `Needed: yes`).

Each phase's `Testing Strategy` = the relevant entries from the spec's Test plan (Tester kind +
asserted behavior + mutation rationale). All markers stay `[]`.

## Global Validation Commands

From the Test plan: the run commands / Testers that prove the feature end-to-end (e.g.
`./run_tests --re=<names>`) plus "build clean". Markers `[]`.

## Questionables

If the spec has explicit open questions (e.g. an `OPEN QUESTION` heading, deferred items, or
"parked pending …"), surface each in the Questionables section. `QUESTIONABLE` defaults true in
the blueprint skill, so the section is included.
