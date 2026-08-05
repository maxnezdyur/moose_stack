---
name: moose-blueprint
description: Takes a vague feature idea, grills the user against MOOSE-specific axes (object kind, inputs/outputs, physics/math), spawns `moose-scout` agents to scout for reusable code, and writes a structured, self-contained `specs/blueprint.html` that `/moose-build` consumes.
disable-model-invocation: true
---

# /moose-blueprint

Convert a vague feature idea into a concrete `specs/blueprint.html` for `/moose-build`: grill the user, scout the codebase for reuse, halt on near-matches, stop at a written blueprint. Does NOT auto-build — the human review pass on the blueprint is load-bearing.

## Usage

```
/moose-blueprint <freeform idea>
```

e.g. `/moose-blueprint postprocessor that integrates strain energy over a subdomain`. If the argument is empty, ask via `AskUserQuestion`.

Requires a `/new-feature` worktree: walk up from CWD to a `.git` **file** (submodule worktrees have a `.git` *file*, not directory) beside a `moose/`+`blackbear/`+`isopod/` layout; otherwise refuse: *"Run /new-feature first; this skill only runs inside a feature worktree."*

## 1. Bootstrap

If `<worktree-root>/specs/blueprint.html` already exists, `AskUserQuestion`: **Resume** (load it, grill only the sections whose contract blocks are empty or placeholder) / **Restart** (overwrite at step 6) / **Cancel**. A leftover `<!-- FILL:<id> -->` sentinel marks a section a previous run never finished — treat it as empty, and fill it in step 6 with the same one-call-per-section passes. A malformed blueprint on resume → restart with a warning.

## 2. Grill — delegate to `/moose-grill`

Invoke `Skill(moose-grill)` with the user's idea. It explores MOOSE's class hierarchy with codegraph and returns a structured plan: `Repo`, `Base class`, `Reference subclass(es)`, `Required overrides`, `validParams shape`, `Coupling`, `Residual / contribution math`, `Pitfalls considered`, `Predicted files to touch`. Multi-class decomposition into `#work-plan` units is THIS skill's job, not the grill's: derive one implement unit per class from the predicted files, draw hard dependency edges only (derives-from / consumes a property another new unit declares / same file), and confirm ambiguous edges with the user during the grill loop. Consume that plan directly — don't re-grill those axes, and don't ask the user things the codebase can answer. If it returns `Base class: undetermined`, fall back to a three-axis grill (object kind + base class, inputs/outputs, physics/math) for that round only.

## 3. Scout — parallel moose-scouts

Decompose the feature into independent **search angles** and spawn one background `moose-scout` per angle (`subagent_type: "moose-scout"`, `run_in_background: true`, all `Agent` calls in one message). Separate angles when the feature spans multiple object kinds, multiple repos, distinct vocabularies (mathematical vs user-facing name — they live in different parts of the tree), or independent implementation-side vs test-side questions; one scout suffices for a single-kind, single-repo, no-synonym or tiny feature. Cap at ~4 — beyond that findings overlap and you can't hold them all in context when they return; queue extras for the next round.

Build each prompt from [`references/scout-prompt.md`](references/scout-prompt.md). Every prompt must (1) pin the **operator/equation**, not just keywords — otherwise a scout reports "diffusion kernel" as a match for Navier–Stokes momentum; (2) give **negative criteria** so near-cousins get dropped, not returned; (3) require **per-hit verification** — open each candidate, quote its residual line, rate the match **structural** / **behavioral**, drop **naming**-only hits. A grep hit is not a match.

Tell the user in one line which angles are fanning out, then keep grilling while they run. Merge findings as each scout lands; block on them only at the reuse-halt check.

## 4. Reuse halt

When scouts report:

- **Exact or near-exact match** → STOP the loop. Surface it (file:line + one-line description) and force a decision via `AskUserQuestion`:
  - **Reuse as-is** — no new code; blueprint captures only test/doc work
  - **Extend** — add a parameter, derived class, template specialization, virtual hook
  - **Write parallel** — user must give a one-sentence justification (recorded in the blueprint)
  - **Abandon idea** — feature already exists, no work needed
- **Close but not direct** → record it; next round asks "extend X or write fresh?"
- **No match** → record the negative result ("searched for X, Y, Z — nothing found") so the blueprint proves the search happened.
- **Counterpart on the other side of an AD/non-AD pair** → if the plan restructures only one side, record the divergence, the unification follow-up, and the existing users that follow-up would migrate.

Scout findings are advisory — the user owns reuse decisions, recorded in the blueprint. If a scout returns BLOCKED or empty, continue without it that round and note "Scout failed: <reason>" under Reuse decisions; don't fabricate findings.

## 5. Loop until converged

Repeat grill→scout→halt with progressively tighter questions. Re-invoke `moose-grill` only if a scout finding contradicts the plan (e.g. reuse-halt found a better `IntegratedBC` base than the picked `Kernel`); otherwise carry the plan forward and grill the math/inputs gaps directly. Ready = every one of the seven contract blocks (below) can be filled with at least one specific fact — if a block would be a placeholder, keep grilling.

Then present a draft summary via `AskUserQuestion`: **Looks good — write it** / **Keep grilling about X** (user names the section) / **Cancel** (nothing written; tell the user "No blueprint saved. Re-run when ready.").

## 6. Write `<worktree-root>/specs/blueprint.html`

`mkdir -p <worktree-root>/specs`. The blueprint is the single deliverable — a self-contained HTML page that is both the human review artifact and the machine input to `/moose-build`.

**Machine contract** — `/moose-build` parses seven blocks, each an element with this exact `id` (placement in the visual layout is free; the ids are what's load-bearing):

| id | Content |
| --- | --- |
| `#summary` | prose (what/why/knob) + **Repo**, **Object kind**, **Predicted files to touch** (new vs existing) |
| `#physics` | equation with symbols defined + **validParams shape** + **residual / contribution form** |
| `#reuse-decisions` | per scout finding: `file:line` — class, what it does, Decision (Reuse / Extend / Parallel), why — or the negative-search record |
| `#test-plan` | per test: name, Tester kind, asserted behavior, mutation rationale |
| `#doc-plan` | **Needed:** yes/no, page path, public surface + **Existing coverage:** every page already documenting the feature and the placement/consolidation the user chose |
| `#out-of-scope` | explicit non-goals |
| `#work-plan` | work units + dep edges, rendered as computed waves with status chips + read-only standing-gate strips, plus the machine JSON island `#work-plan-data` — full spec in [`references/work-plan-format.md`](references/work-plan-format.md) |

Authoring is a **pure formatter** over the grill plan, scout findings, and user decisions. It **never re-explores the codebase** — codegraph already ran via grill + scout, and the generic blueprint skill's Explore/Design/Build workflows would bypass it. Follow [`references/blueprint-format.md`](references/blueprint-format.md) for the contract-block schema, template slot mapping, `.physics-pair` code↔math pairing, and metadata header.

### Write one section per tool call

**Never author the whole file in a single `Write`.** A blueprint written in one shot thins out: the later blocks lose the specificity the early ones got, and a long work plan gets truncated. Build the page in twelve passes instead. Each pass has the finished file on disk to check itself against.

**Pass 1 — skeleton (`Write`).** Read this skill's own [`references/plan-template.html`](references/plan-template.html), a pinned copy of the global blueprint template; make no cross-skill reads at authoring time. If it is missing, warn the user and author a plain self-contained HTML page instead — the seven contract blocks are the deliverable, the template is only the visual identity. Then write a complete, valid HTML file that contains:

- the `<head>`, the title, and **all** CSS inline — the template's own, `.physics-pair` from `blueprint-format.md`, and the work-plan CSS from `work-plan-format.md`;
- the filled header and metadata block;
- one empty stub per section below, carrying its exact `id`, its `<h2>`, and a single sentinel comment `<!-- FILL:<id> -->` as its whole body;
- no `#phases` section — the work plan replaces the template's per-phase checklists.

**Passes 2–11 — one `Edit` per section.** Each `Edit` replaces exactly one `<!-- FILL:<id> -->` sentinel with that section's finished content. The sentinel is unique, so every `old_string` matches once.

| # | Section | `id` | Filled from |
| --- | --- | --- | --- |
| 2 | Summary | `#summary` | grill plan — repo, object kind, predicted files |
| 3 | Relevant files | `#files` | predicted files, split existing vs new |
| 4 | Physics & signature | `#physics` | grill plan math, validParams, residual form — plus one `id="physics-uN"` anchor per implement unit |
| 5 | Reuse decisions | `#reuse-decisions` | scout findings + the user's decisions; `file:line` citations verbatim |
| 6 | Test plan | `#test-plan` | the agreed tests |
| 7 | Doc plan | `#doc-plan` | the agreed doc pages |
| 8 | Out of scope | `#out-of-scope` | recorded non-goals |
| 9 | Work plan — human view | `#work-plan` | waves, unit cards, gate strips, legend |
| 10 | Work plan — machine copy | `#work-plan-data` | the JSON island |
| 11 | Validation + Questionables | `#validation`, `#questionables` | test plan run commands; parked questions from the grill |

The order is load-bearing. `#physics` comes before the work plan so every `physics_ref` anchor already exists. `#test-plan` and `#doc-plan` come before it so the test and doc units have rows to point at.

Rules for these passes:

- One section per call. Never merge two sections into one `Edit`. Never re-`Write` the whole file after pass 1.
- Split a large section further — one `Edit` per wave, per unit card, or per reuse finding, each inserted before the sentinel, with the sentinel removed last. More calls is always allowed; fewer is not.
- Do not re-read the file to confirm an `Edit` landed. `Edit` fails loudly when it does not.
- Reading the file back to check that a reference resolves is fine. That is reading your own output, not re-exploring the codebase.

The `#work-plan` passes follow [`references/work-plan-format.md`](references/work-plan-format.md): implement units from the grill plan's predicted files (one per class), test units from `#test-plan`, a doc unit from `#doc-plan`; edges for hard dependencies only.

**Pass 12 — render and self-check.** Run the offline KaTeX pass:

```
node <this skill's dir>/references/inline-katex.js <worktree-root>/specs/blueprint.html
```

It uses MOOSE's vendored KaTeX and degrades to plain-text LaTeX when KaTeX is absent. Then verify: no `FILL:` sentinel remains, all seven contract `id`s are present and non-placeholder, no `{{` outside image-slot comments, no external `http(s)` stylesheet or script link, every `file:line` citation verbatim. Add the work-plan checks from `work-plan-format.md` — JSON parses, deps resolve and stay acyclic, same-file units share an edge, all chips `idle`, gate strips verbatim and absent from the JSON. Fix any failure with one more targeted `Edit`.

## 7. Stop

Tell the user:

> Blueprint written to `<worktree-root>/specs/blueprint.html` — open it in a browser to review. Edit if needed, then run:
>
> ```
> /moose-build specs/blueprint.html
> ```

Never edit code, run builds/tests/formatters, commit, push, or auto-invoke `/moose-build`. This skill writes only into `<worktree-root>/specs/`; the hand-off is manual.
