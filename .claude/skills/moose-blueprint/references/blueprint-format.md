# blueprint.md format

The blueprint is one markdown file, `<worktree-root>/specs/blueprint.md`. It is the contract:
agents read it whole (about 15 KB), the factory reads its frontmatter, its work-plan JSON and its
unticked clarification boxes, and `/moose-build` updates the status fields in its JSON block. The
human reads `specs/blueprint.html` instead: the packed copy of the hand-written review page
`specs/blueprint-page.html` (format: `page-format.md`), which the `render-blueprint.sh` hook packs
on every save of the page source. Never edit the packed HTML. `example-blueprint.md` here is a
complete, real blueprint for a large framework feature and `example-blueprint-page.html` is its
page; write yours in the same shape, at the length your feature needs (a one-class feature is a
fraction of it).

A worktree with a `blueprint.md` and no `blueprint-page.html` beside it gets the legacy pandoc
render of the markdown from the same hook (`blueprint.template.html`, `workplan.html`).

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

`status: approved` is legal only when every box under `## Needs clarification` is checked. The
user's answers from the page, applied by `/moose-blueprint` in Respond mode, are what ticks them.
Under `--auto` the skill ticks them itself, as `- [x] Qn · <question> — auto: **<answer>**
(<reason>)`, and the gate it grants records `by: auto`.

## Sections, in this order, with these exact `##` headings

| heading | content |
|---|---|
| `## Summary` | what, why, the user-facing knob; then `**Files.**` listing new and existing files to touch as `code` paths (source, `test/`, `unit/` when agreed, doc pages), each new class tagged with its unit id |
| `## Physics` | the equations in `$$ ... $$` with every symbol defined (a symbol table works well), validParams shape as a table (param, type, default, purpose), the residual or contribution form, and one `### <Uid> <ClassName>: <role>` subsection per implement unit so a builder can read only its own |
| `## Reuse decisions` | a table (where, what, decision), one row per scout finding; the decision column is bold and one of **Reuse as-is**, **Reuse (pattern)**, **Extend**, **Parallel** (with the user's one-sentence justification), **Rejected**, **No reuse**; then a `Negative searches:` line naming what was searched and found nothing; a failed scout is recorded as "Scout failed: <reason>" |
| `## Test plan` | one `### <name> (<Tester>)` per test with three bullets: `Requirement:` one sentence in MOOSE's `The system shall ...` form, copied verbatim into the spec's `requirement =`; `Asserts:` the observable consequence (never "runs without error"); `Mutation:` what fails if this line of new code were a no-op; a test against an analytic solution also states the expected behaviour of the error under refinement. `gtest` is the Tester for tests under `unit/` |
| `## Doc plan` | `Needed: yes` or `Needed: no`; the page paths; `Existing coverage:` every page already documenting the feature and the placement the user chose |
| `## Showcase` | optional; omit the heading entirely when the feature needs no figure. `Example:` the input to build, as a `code` path; then one bullet per figure, `<file>: <what it shows and which claim it proves>`, the file named exactly as it will land in `specs/gallery/` and spelled so the projector can link it (see below) |
| `## Proof` | what the pull request shows a reviewer that CI cannot: the kind, then one bullet per proof (see "Proof lines") |
| `## Verify` | the claim a fresh tester checks after the build (gate B7): the three lines under "Verify lines" |
| `## Out of scope` | explicit non-goals, one bullet each |
| `## Needs clarification` | one `- [ ] Qn · <question> — proposed: **<answer>**` per decision, `Q1`, `Q2`, … in the order the page asks them; the same `Qn` is the `doc-ask id` on the page and the proposed answer is its `checked` option. An answer from the page ticks the box and replaces `proposed:` with the answer: `- [x] Qn · <question> — <answer>` |
| `## Work plan` | exactly one fenced `json` block, below |
| `## Amendments` | append-only dated log |

Every `file:line` citation appears verbatim as the scout reported it.

### Verify lines

`/moose-build` gate B7 reads this section and sends fresh `moose-test-runner` testers at the built
binary to check it. Write it so that a tester who has seen none of the build can falsify it.

- `Claim:` one sentence: what the change does, as a MOOSE user sees it, with a number or an output
  that can be wrong. "The L2 error of `u` falls at rate 2 under uniform refinement." Not "adds a
  kernel".
- `Reproduce:` one command from the scope root, then `->` and the result that proves the claim.
  The command is `./<binary> -i <input> [<cli_args>]` or `run_tests --re=<spec name>`, on an input
  the work plan creates or one that exists. The result is a value, a CSV column, a console line or
  an error message, never "runs without error". For a fix, the command reproduces the bug at the
  base ref.
- `Must still work:` one bullet per neighbour behaviour that must not regress, each a
  `run_tests --re=<names>` command of existing tests: the sibling objects, the AD or non-AD twin,
  the tests of a base class the change touches.

### Proof lines

`/moose-build` captures each proof and `/moose-ship` puts it in the pull request, so a reviewer
sees the change work without running it. A proof shows the numbers or the picture of a real run.
CI already shows that the build, the tests and the precheck pass, so a test result, a gate result or
a green run is never a proof.

- `Kind:` one of `figure`, `convergence`, `comparison`, `output`, `none`. Take it from what the
  claim in `## Verify` asserts:

  | kind | the proof | before | after |
  |---|---|---|---|
  | `figure` | the `## Showcase` figures (a field, a refinement plot, a curve against the analytic solution) | the `-before` figure, for a fix | the showcase figures with the feature |
  | `convergence` | a table of the error norm against `h` or `dt` and the observed rate, from the postprocessor CSV of a refinement study (`Mesh/uniform_refine=<k>` or `Executioner/dt=<v>` per run) | the table at the base ref, for a fix | the table with the feature |
  | `comparison` | the new method against the method it replaces, on one input: nonlinear and linear iteration counts (`NumNonlinearIterations`, `NumLinearIterations`), wall time (`PerfGraphData`), and the result values side by side | the replaced method's numbers | the new method's numbers |
  | `output` | an excerpt of the CSV, the exodus values (`scripts/exodus-view`) or the console lines that show the claim, including a new error message | the output at the base ref, for a fix | the output with the feature |
  | `none` | a refactor, a dependency, a CI or a build change, or a docs-only change; CI covers it | | |

- `Precondition:` the state that the proof needs to show the claim, for example "at least three
  refinement levels", "the same mesh, tolerances and preconditioner for both methods" or "one rank,
  an opt binary". Write `none` when there is no such state. A proof captured without its
  precondition is weak.
- Then one bullet per proof, `<file>: <what it shows and which claim it proves>`. A text file lands
  in `specs/proof/`, an image in `specs/gallery/`. A `figure` kind names its `## Showcase` files,
  and any other kind may name one showcase file too; the build renders it once. A before and after
  pair is `<name>-before.<ext>` and `<name>-after.<ext>`. A text proof is a `.txt` or a `.md` file
  of at most 60 lines. A probe script is `specs/proof/<name>-probe.sh`; it runs the binary from the
  scope root through `scripts/conda-run.sh`, may carry its own input `specs/proof/<name>.i`, and
  prints only what the claim needs. Every gallery filename obeys the pattern below.
- A fix has a `before` proof that shows the problem. A new feature has a `before` only when it
  replaces something visible; a `comparison` takes the replaced method's numbers from the same
  binary instead.
- `Kind: none` takes one more line, `Why:` one sentence. A change whose output a user sees (a value,
  a message, a figure) is never `none`.

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
    { "id": "D1", "kind": "doc", "agent": "moose-docs-writer", "deps": [], "status": "idle" },
    { "id": "S1", "kind": "showcase", "agent": "moose-figure", "deps": ["U1"], "status": "idle",
      "example": "moose/test/tests/<area>/<feature>/showcase.i",
      "files": ["specs/gallery/field.png", "specs/gallery/convergence.png"] }
  ],
  "gates": {
    "A1": { "criterion": "C1", "status": "idle" },
    "B2": { "criterion": "C2/C3", "status": "idle" },
    "B3": { "criterion": "C4", "status": "idle" },
    "B4": { "criterion": "C5", "status": "idle" },
    "B5": { "criterion": "C6", "status": "idle" },
    "B6": { "criterion": "DG", "status": "idle" },
    "B7": { "criterion": "C7", "status": "idle" }
  }
}
```

- `kind` is `implement`, `test`, `doc`, or `showcase`; `agent` is `moose-implementer`,
  `moose-test-writer`, `moose-unit-test-writer`, `moose-docs-writer`, or `moose-figure`.
- A `showcase` unit exists only when the blueprint has a `## Showcase` section. Its `files` are the
  gallery outputs, one per bullet of that section and spelled the same, each a worktree-relative
  `specs/gallery/<name>` path; its `example` is that section's `Example:` input. `moose-figure`
  turns each bullet into one numbered section of the figure page, `specs/gallery/gallery.md`,
  which the projector transcludes into the feature note. It depends on the
  implement units whose code the figures show, and it gates nothing: a figure that fails to render
  is reported, not a build failure.
- A gallery filename must start with a letter or a digit and contain only letters, digits, dot,
  underscore, space and hyphen, at most 96 characters (`^[A-Za-z0-9][A-Za-z0-9._ -]{0,95}$`). The
  projector spells the name into a wikilink, an `img src` and a path, so it refuses anything else:
  parentheses, `+`, `,`, `#`, `%`, `@`, `!`, `=`, `[`, `]`, `|` and every non-ASCII character. A
  refused figure still renders and still passes every evidence check, and then appears nowhere on
  the note or the board. Write `sigma_xx_vs_t.png`, not `sigma_xx(t).png`.
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

Read the file back and confirm: the frontmatter fields above; the eleven `##` headings in order,
none a placeholder, with `## Showcase` present only when the feature has figures; `## Verify` has
`Claim:`, `Reproduce:` with its `->` result, and at least one `Must still work:` bullet; `## Proof`
has `Kind:` and `Precondition:`, a kind other than `none` has at least one bullet and `none` has
`Why:`, a `figure` kind has a `## Showcase` section and its bullets name those files, and a fix has
a `-before` proof; one fenced
`json` block that parses; every `deps` id exists and the graph has
no cycle; edge-free units list disjoint files; each `test` unit names a `###` test heading and
each `implement` unit a `###` physics subsection; each `showcase` unit's `files` match the
`## Showcase` bullets one for one; every `Requirement:` line is one sentence; and
`status: approved` only with every clarification box ticked; and every `Qn` here has a `doc-ask`
with the same id on the page and the same proposed answer `checked`. The hook has packed
`specs/blueprint.html` from the page (node is required; pandoc only for `doc-math`); when it has
not, run `pack-blueprint.py` by hand and fix what it reports.
