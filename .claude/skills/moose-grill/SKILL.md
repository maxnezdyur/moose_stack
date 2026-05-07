---
name: moose-grill
description: Pre-coding grill for MOOSE C++ work that walks the user through the authoring-guide decision trees (kernel/material/postprocessor/etc.), challenges the base-class pick, surfaces pitfalls before code is written, and refines guide decision trees inline when the grill reveals an ambiguity. Use directly via /moose-grill or as the grill phase of /moose-design-feature.
disable-model-invocation: true
---

# /moose-grill

Pre-coding grill that stress-tests a MOOSE C++ plan against the authoring guides at `.claude/contexts/moose/*-authoring.md`. Picks the relevant guide(s), walks the decision tree, identifies base class + overrides + validParams + coupling + pitfalls, and refines a guide's decision tree inline when grilling reveals genuine ambiguity.

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

### 1. Bootstrap

1. Read `$ARGUMENTS`. If empty, ask the user via `AskUserQuestion`: "What MOOSE C++ work are you planning?" Capture their freeform plan.
2. Read `/Users/maxnezdyur/projects/moose_stack/.claude/contexts/moose/AUTHORING-MAP.md`.
3. Use the map's **Quick reference** table and **Decision tree** to pick the relevant 1–3 guides:
   - Most plans hit one framework guide (e.g., `kernel-authoring.md`) plus one module guide (e.g., `solid-mechanics-authoring.md`). Module guides extend framework guides; load both.
   - If the match is unambiguous, just announce the picks in one line and continue.
   - If multiple guides match equally well or none match, ask the user via `AskUserQuestion` which to load.

### 2. Walk the decision tree

For each loaded guide, walk its **When to use this** section as the spine of the grill:

1. Identify which branch the user's plan falls under by reading the bullets.
2. Confirm the branch with 1–2 questions at a time via `AskUserQuestion`. Don't dump them all at once. Wait for feedback.
3. If the user's answer doesn't fit any existing branch cleanly, jump to step 5 (**Decision-tree refinement**) instead of forcing the user into the closest branch.

The picked branch determines the **base class**. Capture it explicitly.

### 3. Walk the contract

Once the base class is picked:

1. Read the matching **Contract** entry for that base in the guide.
2. Confirm the **required overrides** — which virtuals will the user implement, and what does each compute? Use `AskUserQuestion` only if the answer isn't obvious from the plan.
3. Confirm the **validParams shape** — typical `addRequiredCoupledVar`, `addParam<MaterialPropertyName>`, etc.
4. Mention **optional overrides** only if the plan suggests they'll be needed.

### 4. Walk coupling and pitfalls

1. From the guide's **Coupling & material properties** section, identify what the new class will consume (variables, material properties, functors) and produce. Confirm AD vs non-AD picks.
2. Walk the guide's **Common pitfalls** for the picked base. For each pitfall, ask "does this apply to your plan?" or "how does your plan avoid this?" Skip pitfalls that obviously don't apply — but err on the side of asking.

### 5. Decision-tree refinement (inline)

When grilling reveals that a guide's **When to use this** section is genuinely ambiguous (the user has a real case the tree doesn't cleanly cover):

1. Propose a **one-line addition or clarification** to the relevant bullet.
2. Show the user the diff (just the changed bullet) via `AskUserQuestion`:
   - **Apply the refinement** — `Edit` the guide right then.
   - **Skip** — leave the guide as-is; mention it in the final summary so the user can revisit.
3. Don't batch refinements — capture them as they happen.

Only refine the **When to use this** section. If a pitfall is missing or the contract feels wrong, mention it in the final summary; don't auto-edit those sections.

### 6. Capture the math (free-text)

Before summarizing, ask the user once via `AskUserQuestion` (or accept text directly):

- "Write the residual / contribution form in plain math or LaTeX. What does `computeQpResidual` (or your equivalent) return?"

Push back on hand-waving — vague math becomes vague code. The authoring guides don't validate physics; the user owns this. Capture the math verbatim into the plan.

### 7. Converge and emit the plan

When all picks are clear, print this structured plan to terminal:

```md
## Plan: <short feature name>

**Repo:** moose | moose/modules/<m> | blackbear | isopod
**Authoring guide(s) consulted:** <guide-1>.md, <guide-2>.md
**Object kind / base class:** `<NewClass> : public <BaseClass>` (<repo-relative path:line>)

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
<verbatim from step 6>

### Pitfalls considered
- <pitfall summary> — mitigation: ...
- ...

### Decision-tree refinements applied
- `<guide>.md` — <one-line summary of the change>
- (or "None")

### Predicted files to touch
- <repo>/include/<area>/<NewClass>.h
- <repo>/src/<area>/<NewClass>.C
```

Print the plan. **Do NOT write any file** — that's `/moose-design-feature`'s job (it folds this plan into `spec.md`).

When invoked standalone (not from `/moose-design-feature`), the user can copy the plan into wherever they need it.

## Hard constraints

- **Never write code.** This skill produces a plan, not files.
- **Never write `spec.md`.** That's `/moose-design-feature`'s output.
- **Edit guides only when refining decision trees.** Other sections (Contract, Pitfalls, Scaffold, Coupling) are out of scope for inline edits.
- **Always show the diff before editing a guide.** No silent rewrites — confirm via `AskUserQuestion`.
- **One or two questions at a time.** Wait for feedback before continuing.
- **Don't grill the math against the guide.** The authoring guides don't cover residual/Jacobian math — that's on the user, captured verbatim.

## Failure handling

- **No guide clearly matches the plan** → ask the user which guide to load via `AskUserQuestion`. If still unclear, run a free-form grill and emit a plan with `Authoring guide(s) consulted: none` so the caller knows the authoring system didn't cover this case.
- **`AUTHORING-MAP.md` missing** → fall back to listing `.claude/contexts/moose/*-authoring.md` and asking the user which apply.
- **User abandons mid-grill** → no plan is emitted. Tell the user: "Grill cancelled — no plan saved."

## Canonical references

- `.claude/contexts/moose/AUTHORING-MAP.md` — entry point for guide discovery
- `.claude/contexts/moose/*-authoring.md` — the 15 authoring guides this skill consults
- `/moose-design-feature` — typical caller; folds this skill's plan into `spec.md`
- `grill-me` — generic grill reference; this skill specializes for the authoring-guide axis
