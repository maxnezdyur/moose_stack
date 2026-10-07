---
name: moose-grill
description: Grills a planned MOOSE C++ change against the real class hierarchy before code exists. Picks the base class from the real hierarchy, confirms overrides, validParams shape, and coupling with the user, captures the math verbatim, and prints a plan. With --unattended it asks nothing, settles every fork itself and lists the decisions taken. Use for "/moose-grill <plan>", "which base class should this derive from", "grill my kernel plan", or as the grill phase of /moose-blueprint.
argument-hint: "[--unattended] <planned C++ work>"
---

# /moose-grill

Stress-test a MOOSE C++ plan against the class hierarchy in this checkout, explored live with grep, Read, and moose-scout rather than remembered. The output is a printed plan with a confirmed base class, contract, coupling, and math that `/moose-blueprint` folds into `specs/blueprint.html`; a standalone run copies the plan wherever it is needed. This skill prints only. It writes no files and no code, and reading the codebase is its only source interaction.

The plan is `$ARGUMENTS`. When it is empty, ask "What MOOSE C++ work are you planning?" with `AskUserQuestion` first.

When `$ARGUMENTS` starts with `--unattended`, the rest is the plan and the grill asks nothing (the
"Unattended" section below). `/moose-blueprint` calls it this way when it runs as a background
session with nobody at the terminal, and without the flag when the user is there to grill.

## Rounds

The grill is a design tree: the base class decides the required overrides, which decide the `validParams` shape and coupling, which decide the pitfalls and the math. Each round asks every question whose prerequisites are settled, in one `AskUserQuestion` call (up to 4 questions, recommended answer as the first option); a question that depends on an answer still open this round waits for the next one. Round 1 is usually only the base-class pick, plus the repo or module when that is ambiguous; settling it unblocks the contract, coupling, and pitfall questions, which go out together as one batched round.

Facts come from the codebase, not from the user. While a round is out, spawn `moose-scout` agents (one angle each, all in one message) for lookups later rounds need, such as sibling `validParams` shapes, representative subclass reads, and existing similar objects; keep fast single greps inline. A scout still running is an unsettled prerequisite: only the questions downstream of it wait. The grill is done when no question remains and nothing is silently assumed.

## What each round settles

Candidates. Infer the object kind (Kernel, IntegratedBC, Material, Postprocessor, UserObject, Action, Constraint, ...) and grep the key virtual (`computeQpResidual` for kernels, `computeQpValue` for aux kernels, `execute` for postprocessors and user objects) under `framework/include` to find the base classes that declare it; then Read the base header for the declared virtuals and `grep -rl 'public <BaseClassName>' framework/include modules/*/include` for the subclasses. Hold plausible alternatives (`Kernel` vs `IntegratedBC`, AD vs non-AD) as candidates. When nothing fits, widen the search (another key virtual, another namespace) before forcing a pick; when it still does not fit, ask the user to name a base or run a free-form grill and print `Base class: undetermined (free-form grill)` so the caller knows the hierarchy did not cover the case.

Base class. Present each candidate with a one-line "use this when ..." derived from what one or two of its existing subclasses do, and confirm the pick. Record it with its repo-relative `path:line`; it is the spine of the rest of the grill.

Contract. Read the base header and one representative subclass (header and source): the required overrides and what each computes, the `validParams` shape from the base and a sibling (`addRequiredCoupledVar`, `addParam<MaterialPropertyName>`, ...), and optional overrides only where the plan calls for them. "Make it exactly like `<Class>`" means mirror its structure and public API only: deprecated parameters, compatibility shims, and known defects are dropped, and each omission is recorded under Pitfalls considered.

Coupling and pitfalls. Load the `moose-code-standards` skill for this round. Settle what the class consumes (variables, material properties, functors) and produces. For a dual-flavor object ask which shape applies: one `is_ad`-templated class (the default), a separate pair, AD-only, or dropped-in-AD (that skill's "AD and non-AD variants" section). Ask which object names, indices, or physical assumptions the design would hardcode; each becomes a typed name parameter or a documented assumption (its "Input parameters" section). Raise the base-class pitfalls the standards skill does not cover, such as `usingMooseObjectMembers` in templated bases, member initialization order, and `_qp` indexing, as "does this apply, and how does the plan avoid it?"; skip only the ones that clearly do not apply.

Math. Ask once: "Write the residual or contribution form in plain math or LaTeX; what does `computeQpResidual` (or the equivalent override) return?" Push back on hand-waving, because vague math becomes vague code. The hierarchy shows structure, not whether the physics is right: the user owns the math, and it goes into the plan verbatim and unvalidated.

## Unattended

The same rounds, with the user's chair empty. Each question that a round would have asked is
settled by you, from the codebase: pick the answer the evidence supports, the one that would have
been the recommended first option. Record it as a decision with the alternatives you rejected and
the evidence for the pick, as `file:line` where there is one. The math round has no user to push
back on: take the residual form from the plan text when it gives one, else write the form the base
class and the reference subclass imply, mark it `assumed`, and make it a decision. Spawn the same
scouts; wait for the ones a decision depends on.

Settle, do not hedge: a fork left open is useless to a blueprint written without a human. A fork
with no evidence either way is still settled, by the simpler option, and its decision line says
`no evidence; simpler`. The whole list goes to `/moose-blueprint`, which turns each line into one
question on the review page with your pick as the default, so the user sees every fork and changes
only the ones they disagree with.

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

### Decisions taken
- <question, 15 words at most> -- chose: <answer>; alternatives: <a>, <b>; because: <evidence, file:line>
```

`### Decisions taken` appears only in an unattended run: one line per fork settled without the
user, in the order the rounds met them. An interactive run has no such section, because the user
answered each fork as it came.
