---
name: moose-grill
description: Grills a planned MOOSE C++ change against the real class hierarchy before code exists. Picks the base class with codegraph, confirms overrides, validParams shape, and coupling with the user, captures the math verbatim, and prints a plan. Use for "/moose-grill <plan>", "which base class should this derive from", "grill my kernel plan", or as the grill phase of /moose-blueprint.
argument-hint: "<planned C++ work>"
---

# /moose-grill

Stress-test a MOOSE C++ plan against the class hierarchy in this checkout, explored live with codegraph rather than remembered. The output is a printed plan with a confirmed base class, contract, coupling, and math that `/moose-blueprint` folds into `specs/blueprint.html`; a standalone run copies the plan wherever it is needed. This skill prints only. It writes no files and no code, and reading the codebase is its only source interaction.

The plan is `$ARGUMENTS`. When it is empty, ask "What MOOSE C++ work are you planning?" with `AskUserQuestion` first.

## Rounds

The grill is a design tree: the base class decides the required overrides, which decide the `validParams` shape and coupling, which decide the pitfalls and the math. Each round asks every question whose prerequisites are settled, in one `AskUserQuestion` call (up to 4 questions, recommended answer as the first option); a question that depends on an answer still open this round waits for the next one. Round 1 is usually only the base-class pick, plus the repo or module when that is ambiguous; settling it unblocks the contract, coupling, and pitfall questions, which go out together as one batched round.

Facts come from the codebase, not from the user. While a round is out, spawn `moose-scout` agents (one angle each, all in one message) for lookups later rounds need, such as sibling `validParams` shapes, representative subclass reads, and existing similar objects; keep fast `codegraph_explore` calls inline. A scout still running is an unsettled prerequisite: only the questions downstream of it wait. The grill is done when no question remains and nothing is silently assumed.

## What each round settles

Candidates. Infer the object kind (Kernel, IntegratedBC, Material, Postprocessor, UserObject, Action, Constraint, ...) and query `codegraph_explore "<ObjectKind> base class <key virtual>"`, where the key virtual is `computeQpResidual` for kernels, `computeQpValue` for aux kernels, and `execute` for postprocessors and user objects; then `codegraph node <BaseClassName>` (CLI, via Bash) for the declared virtuals and subclasses. Hold plausible alternatives (`Kernel` vs `IntegratedBC`, AD vs non-AD) as candidates. When nothing fits, widen the search (another key virtual, another namespace) before forcing a pick; when it still does not fit, ask the user to name a base or run a free-form grill and print `Base class: undetermined (free-form grill)` so the caller knows the hierarchy did not cover the case.

Base class. Present each candidate with a one-line "use this when ..." derived from what one or two of its existing subclasses do, and confirm the pick. Record it with its repo-relative `path:line`; it is the spine of the rest of the grill.

Contract. Read the base plus one representative subclass with `codegraph node <Class>`: the required overrides and what each computes, the `validParams` shape from the base and a sibling (`addRequiredCoupledVar`, `addParam<MaterialPropertyName>`, ...), and optional overrides only where the plan calls for them. "Make it exactly like `<Class>`" means mirror its structure and public API only: deprecated parameters, compatibility shims, and known defects are dropped, and each omission is recorded under Pitfalls considered.

Coupling and pitfalls. Load the `moose-code-standards` skill for this round. Settle what the class consumes (variables, material properties, functors) and produces. For a dual-flavor object ask which shape applies: one `is_ad`-templated class (the default), a separate pair, AD-only, or dropped-in-AD (that skill's "AD and non-AD variants" section). Ask which object names, indices, or physical assumptions the design would hardcode; each becomes a typed name parameter or a documented assumption (its "Input parameters" section). Raise the base-class pitfalls the standards skill does not cover, such as `usingMooseObjectMembers` in templated bases, member initialization order, and `_qp` indexing, as "does this apply, and how does the plan avoid it?"; skip only the ones that clearly do not apply.

Math. Ask once: "Write the residual or contribution form in plain math or LaTeX; what does `computeQpResidual` (or the equivalent override) return?" Push back on hand-waving, because vague math becomes vague code. Codegraph shows structure, not whether the physics is right: the user owns the math, and it goes into the plan verbatim and unvalidated.

## Output

When every round is settled, print this plan to the terminal with these headings and field names:

```md
## Plan: <short feature name>

**Repo:** moose | moose/modules/<m> | blackbear | isopod
**Base class:** `<NewClass> : public <BaseClass>` (<repo-relative path:line>)
**Reference subclass(es):** `<ExistingClass>` (<path:line>)

### Required overrides
- `methodA() override` -- computes ...

### validParams shape
- `param_name` (Type) -- purpose
- `coupledVar("name")` -- purpose

### Coupling
- Reads variable: `<var>` (AD / non-AD)
- Reads material property: `<prop>` (declared by ...)
- Writes material property: `<prop>` (consumed by ...)

### Residual / contribution math
<verbatim from the math round>

### Pitfalls considered
- <pitfall> -- mitigation: ...

### Predicted files to touch
- <repo>/include/<area>/<NewClass>.h
- <repo>/src/<area>/<NewClass>.C
```
