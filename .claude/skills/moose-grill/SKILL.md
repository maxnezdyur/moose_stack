---
name: moose-grill
description: Pre-coding grill for MOOSE C++ work that picks the base class by exploring MOOSE's class hierarchy with codegraph, challenges the pick, confirms the contract (overrides + validParams + coupling), and surfaces pitfalls before code is written. Use directly via /moose-grill or as the grill phase of /moose-design-feature.
---

# /moose-grill

Pre-coding grill that stress-tests a MOOSE C++ plan against MOOSE's **actual class hierarchy**, explored live with codegraph. Picks the relevant base class, confirms which virtuals to override and the `validParams` shape, checks coupling, and surfaces pitfalls — all grounded in the real source rather than a static guide.

Designed to compose with `/moose-design-feature`: that skill delegates its base-class-and-contract grilling to this one. Also runs standalone when the user just wants to think through a plan.

## Usage

```
/moose-grill <freeform plan>
```

Examples:
- `/moose-grill add a kernel for thermal-anisotropic conduction in solid_mechanics`
- `/moose-grill new gap flux model that depends on contact pressure`
- `/moose-grill custom OptimizationReporter for shape-design parameters`

If `$ARGUMENTS` is empty, the skill prompts via `AskUserQuestion`.

## Steps

### 1. Bootstrap — find candidate base classes

1. Read `$ARGUMENTS`. If empty, ask the user via `AskUserQuestion`: "What MOOSE C++ work are you planning?" Capture their freeform plan.
2. Infer the MOOSE object kind from the plan (Kernel, IntegratedBC, Material, Postprocessor, UserObject, Action, Constraint, etc.).
3. Use codegraph to pull the candidate base class(es) and their existing subclasses:
   - `codegraph_explore "<ObjectKind> base class <key virtual>"` (e.g. `computeQpResidual` for kernels, `computeQpValue` for aux, `execute` for postprocessors) to surface the base plus representative implementations.
   - `codegraph_search "<BaseClassName>"`, then `codegraph_node <BaseClassName>` to read the base's declared virtuals and its subclasses/callers.
   - If two base classes plausibly fit (e.g. `Kernel` vs `IntegratedBC`, AD vs non-AD), hold both as candidates for step 2.

### 2. Pick the base class

1. Present the candidate base class(es) to the user, each with a one-line "use this when ..." derived from what its existing subclasses actually do (read 1–2 of them via codegraph).
2. Confirm the pick with 1–2 questions at a time via `AskUserQuestion`. Don't dump them all at once. Wait for feedback.
3. If the user's case fits none of the candidates cleanly, widen the codegraph search (different key virtual, different namespace) before forcing a pick.

The chosen base class is the spine of the rest of the grill. Capture it explicitly, with its `repo-relative path:line` from codegraph.

### 3. Walk the contract

Once the base class is picked, read it via codegraph (`codegraph_node <BaseClass>`) plus one representative subclass:

1. **Required overrides** — which pure-virtual / virtual methods must the user implement, and what does each compute? Confirm via `AskUserQuestion` only if the plan doesn't already make it obvious.
2. **validParams shape** — read the base's and a sibling's `validParams` to see the typical `addRequiredCoupledVar`, `addParam<MaterialPropertyName>`, etc. Confirm the new object's params.
3. **Optional overrides** — mention only if the plan suggests they'll be needed.

### 4. Walk coupling and pitfalls

1. From a representative subclass (read via codegraph), identify what the new class will consume (variables, material properties, functors) and produce. Confirm AD vs non-AD picks.
2. Surface the pitfalls that apply to this base class — drawn from MOOSE conventions and from reading how existing subclasses handle them (AD vs non-AD residual typing, `usingMooseObjectMembers`, member init order, `_qp` indexing, registration). For each, ask "does this apply to your plan?" or "how does your plan avoid this?" Skip pitfalls that obviously don't apply — but err on the side of asking.

### 5. Capture the math (free-text)

Before summarizing, ask the user once via `AskUserQuestion` (or accept text directly):

- "Write the residual / contribution form in plain math or LaTeX. What does `computeQpResidual` (or your equivalent) return?"

Push back on hand-waving — vague math becomes vague code. Source exploration shows structure, not whether the physics is right; the user owns this. Capture the math verbatim into the plan.

### 6. Converge and emit the plan

When all picks are clear, print this structured plan to terminal:

```md
## Plan: <short feature name>

**Repo:** moose | moose/modules/<m> | blackbear | isopod
**Base class:** `<NewClass> : public <BaseClass>` (<repo-relative path:line>)
**Reference subclass(es):** `<ExistingClass>` (<path:line>)

### Required overrides
- `methodA() override` — computes ...
- `methodB() override` — computes ...

### validParams shape
- `param_name` (Type) — purpose
- `coupledVar("name")` — purpose
- ...

### Coupling
- Reads variable: `<var>` (AD / non-AD)
- Reads material property: `<prop>` (declared by ...)
- Writes material property: `<prop>` (consumed by ...)

### Residual / contribution math
<verbatim from step 5>

### Pitfalls considered
- <pitfall summary> — mitigation: ...
- ...

### Predicted files to touch
- <repo>/include/<area>/<NewClass>.h
- <repo>/src/<area>/<NewClass>.C
```

Print the plan. **Do NOT write any file** — that's `/moose-design-feature`'s job (it folds this plan into `spec.md`).

When invoked standalone (not from `/moose-design-feature`), the user can copy the plan into wherever they need it.

## Hard constraints

- **Never write code.** This skill produces a plan, not files.
- **Never write `spec.md`.** That's `/moose-design-feature`'s output.
- **Never edit source.** Reading via codegraph (or `Grep`/`Glob` fallback) is the only codebase interaction.
- **One or two questions at a time.** Wait for feedback before continuing.
- **Don't grill the math against the source.** codegraph shows structure, not whether the residual/Jacobian math is correct — that's on the user, captured verbatim.

## Failure handling

- **No base class clearly matches the plan** → widen the codegraph search; if still unclear, ask the user to name the base class, or run a free-form grill and emit a plan with `Base class: undetermined (free-form grill)` so the caller knows the hierarchy didn't cover this case.
- **codegraph unavailable** (no `.codegraph/` index) → fall back to `Grep`/`Glob` over `*/include/**` and `*/src/**` to locate the base class and its subclasses, then proceed the same way.
- **User abandons mid-grill** → no plan is emitted. Tell the user: "Grill cancelled — no plan saved."

## Canonical references

- `/moose-design-feature` — typical caller; folds this skill's plan into `spec.md`.
- `grill-me` — generic grill reference; this skill specializes for the MOOSE base-class axis.
- codegraph (`codegraph_explore`, `codegraph_node`, `codegraph_search`) — the live source of base-class / subclass / contract facts this skill grills against.
