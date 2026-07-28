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

If `<worktree-root>/specs/blueprint.html` already exists, `AskUserQuestion`: **Resume** (load it, grill only the sections whose contract blocks are empty or placeholder) / **Restart** (overwrite at step 6) / **Cancel**. A malformed blueprint on resume → restart with a warning.

## 2. Grill — delegate to `/moose-grill`

Invoke `Skill(moose-grill)` with the user's idea. It explores MOOSE's class hierarchy with codegraph and returns a structured plan: `Repo`, `Base class`, `Reference subclass(es)`, `Required overrides`, `validParams shape`, `Coupling`, `Residual / contribution math`, `Pitfalls considered`, `Predicted files to touch`, and — for multi-class features — `Work units` (one per class, with hard dependency edges; these seed `#work-plan`). Consume that plan directly — don't re-grill those axes, and don't ask the user things the codebase can answer. If it returns `Base class: undetermined`, fall back to a three-axis grill (object kind + base class, inputs/outputs, physics/math) for that round only.

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
| `#doc-plan` | **Needed:** yes/no, page path, public surface |
| `#out-of-scope` | explicit non-goals |
| `#work-plan` | work units + dep edges, rendered as computed waves with status chips + read-only standing-gate strips, plus the machine JSON island `#work-plan-data` — full spec in [`references/work-plan-format.md`](references/work-plan-format.md) |

Authoring — a pure formatter over the grill plan, scout findings, and user decisions; **never re-explores the codebase** (codegraph already ran via grill + scout; the blueprint skill's generic Explore/Design/Build workflows would bypass it):

1. Read the HTML skeleton from this skill's own [`references/plan-template.html`](references/plan-template.html) — a pinned copy of the global blueprint template; no cross-skill reads at authoring time. If it's missing, warn and author a plain self-contained HTML page instead — the seven contract blocks are the deliverable; the template is only the visual identity.
2. Fill it per [`references/blueprint-format.md`](references/blueprint-format.md) — the authoritative contract-block schema, template slot mapping, `.physics-pair` code↔math pairing, metadata header, and offline KaTeX rendering (`node <this skill's dir>/references/inline-katex.js <worktree-root>/specs/blueprint.html`; uses MOOSE's vendored KaTeX, degrades gracefully to plain-text LaTeX). The `#work-plan` block follows [`references/work-plan-format.md`](references/work-plan-format.md): implement units from the grill's Work units, test units from `#test-plan`, doc unit from `#doc-plan`; edges only for hard dependencies; it **replaces** the template's per-phase task checklists.
3. Save to `<worktree-root>/specs/blueprint.html`. Self-check: all seven contract `id`s present and non-placeholder, no `{{` outside image-slot comments, no external `http(s)` stylesheet/script links, every `file:line` citation verbatim, plus the work-plan checks from `work-plan-format.md` (JSON parses, deps resolve + acyclic, same-file units share an edge, chips all `idle`, gate strips verbatim and absent from the JSON).

## 7. Stop

Tell the user:

> Blueprint written to `<worktree-root>/specs/blueprint.html` — open it in a browser to review. Edit if needed, then run:
>
> ```
> /moose-build specs/blueprint.html
> ```

Never edit code, run builds/tests/formatters, commit, push, or auto-invoke `/moose-build`. This skill writes only into `<worktree-root>/specs/`; the hand-off is manual.
