---
name: moose-grill
description: Pre-coding grill for MOOSE C++ work that picks the base class by exploring MOOSE's class hierarchy with codegraph, challenges the pick, confirms the contract (overrides + validParams + coupling), and surfaces pitfalls before code is written. Use directly via /moose-grill or as the grill phase of /moose-blueprint.
---

# /moose-grill

Stress-test a MOOSE C++ plan against MOOSE's **actual class hierarchy**, explored live with codegraph: pick the base class, confirm overrides + `validParams` + coupling, surface pitfalls — grounded in the real source rather than a static guide. Composes with `/moose-blueprint` (which delegates its base-class grilling here) or runs standalone.

## Usage

```
/moose-grill <freeform plan>
```

e.g. `/moose-grill add a kernel for thermal-anisotropic conduction in solid_mechanics`. If `$ARGUMENTS` is empty, ask via `AskUserQuestion`: "What MOOSE C++ work are you planning?"

## Flow

**Find candidates.** Infer the object kind (Kernel, IntegratedBC, Material, Postprocessor, UserObject, Action, Constraint, …), then pull candidate base classes with codegraph: `codegraph_explore "<ObjectKind> base class <key virtual>"` (`computeQpResidual` for kernels, `computeQpValue` for aux, `execute` for postprocessors) to surface the base plus representative implementations, then `codegraph node <BaseClassName>` (CLI, via Bash) for the declared virtuals and subclasses. Hold plausible alternatives (`Kernel` vs `IntegratedBC`, AD vs non-AD) as candidates.

**Pick the base class.** Present each candidate with a one-line "use this when …" derived from what its existing subclasses actually do (read 1–2 via codegraph). Confirm via `AskUserQuestion`, 1–2 questions at a time — the back-and-forth is the point of a grill; don't dump everything at once. If nothing fits cleanly, widen the search (different key virtual, different namespace) before forcing a pick. Capture the pick with its repo-relative `path:line` — it's the spine of the rest of the grill.

**Walk the contract.** Read the base plus one representative subclass (`codegraph node <Class>`): required overrides and what each computes; `validParams` shape from the base and a sibling (`addRequiredCoupledVar`, `addParam<MaterialPropertyName>`, …); optional overrides only where the plan suggests they're needed.

**Mirror structure, not debt.** Treat "make it exactly like `<Class>`" as mirroring structure and public API only — drop deprecated parameters, compatibility shims, and known defects — and record each omission under **Pitfalls considered**.

**Walk coupling + pitfalls.** What the new class consumes (variables, material properties, functors) and produces; confirm AD vs non-AD picks — for a dual-flavor object, which shape applies: one `is_ad`-templated class (the default), a separate pair, AD-only, or dropped-in-AD (moose-code-standards § AD and non-AD variants). Ask which object names, indices, or physical assumptions the design would hardcode — those become typed name parameters or documented assumptions (moose-code-standards § Input parameters). Surface the pitfalls that apply to this base class — AD vs non-AD residual typing, `usingMooseObjectMembers`, member init order, `_qp` indexing, registration — asking "does this apply / how does your plan avoid it?" Skip ones that obviously don't apply, but err toward asking.

**Capture the math verbatim.** Ask once: "Write the residual / contribution form in plain math or LaTeX — what does `computeQpResidual` (or your equivalent) return?" Push back on hand-waving — vague math becomes vague code. Codegraph shows structure, not whether the physics is right; the user owns the math, and it goes into the plan verbatim, unvalidated.

## Output — the plan

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
<verbatim from the math step>

### Pitfalls considered
- <pitfall summary> — mitigation: ...
- ...

### Predicted files to touch
- <repo>/include/<area>/<NewClass>.h
- <repo>/src/<area>/<NewClass>.C
```

Print only — never write files or code; folding the plan into `specs/blueprint.html` is `/moose-blueprint`'s job, and standalone users copy it where they need it. Reading the codebase (codegraph, or `Grep`/`Glob` fallback) is the only source interaction.

## Fallbacks

- **No base class matches** → widen the codegraph search; if still unclear, ask the user to name one, or run a free-form grill and emit `Base class: undetermined (free-form grill)` so the caller knows the hierarchy didn't cover this case.
- **codegraph unavailable** (no `.codegraph/` index) → `Grep`/`Glob` over `*/include/**` and `*/src/**` for the base class and subclasses; same flow.
- **User abandons mid-grill** → no plan emitted: "Grill cancelled — no plan saved."
