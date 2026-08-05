---
name: moose-code-standards
description: MOOSE coding standards (C++ and Python). Auto-loads when writing or editing C++/Python source in moose, blackbear, or isopod. Preloaded into the moose-implementer, moose-code-reviewer, and moose-unit-test-writer agents.
user-invocable: true
---

# MOOSE Code Standards

One canonical source, maintained upstream and shared by all three repos — read it directly rather than working from remembered standards:

**`moose/framework/doc/content/sqa/framework_scs.md`** (relative to the meta-repo root)

If the file is missing (submodule not checked out), report that and stop — do not substitute remembered standards.

## ASCII only — code, not docs

Every byte of **code** you write — C++, Python, `tests` specs, `.i` inputs — must be 7-bit ASCII, comments included. CIVET's precheck runs here and rejects non-ASCII, and it sneaks in invisibly via AI prose and paste: smart quotes, em/en dashes, NBSP, unicode math (`×`, `°`, Greek letters). Use `'`/`"`, `--`, plain spaces, and spelled-out or LaTeX-in-comments math instead. Scan before reporting done: `grep -nP '[^\x00-\x7F]' <file>` must return nothing.

**`.md` documentation and `.bib` are exempt** — `idaholab/moose` scoped this rule to code comments in `c12859fc3f` (May 2026, refs #32497) precisely so docs can spell names correctly (Nédélec). If the same task has you writing a doc page, switch to `moose-doc-standards`; do not carry this rule into `.md`.

## New classes

- Never register deprecated, legacy, or back-compat parameters on a brand-new class — it has no existing inputs to stay compatible with, even when the sibling `validParams()` being mirrored carries them. If an existing Action still accepts an old name, translate old → new where it sets the object's parameters. Only a renamed or relocated existing type (`registerMooseObjectRenamed`) inherits real user inputs and may keep its deprecated params.

## Input parameters

- A coupled-object name reached through a string literal (`getMaterialPropertyByName`, `getVectorPostprocessorValueByName`, `getUserObjectByName`, `getPostprocessorValueByName`, `declareProperty`) is a typed name parameter instead — `MaterialPropertyName`, `VectorPostprocessorName`, `UserObjectName`, `PostprocessorName`, `MooseFunctorName`, never `std::string` — defaulting to the current literal so existing inputs keep working. Parameterize the whole name, never a fragment or index. Canonical pattern: `moose/framework/doc/content/syntax/Materials/index.md` § Property Names.
- Exceptions — leave the literal alone: class-family contract names disambiguated by `base_name` (`stress`, `elastic_strain`, `Jacobian_mult`, `mechanical_strain`), names an Action generates for its own objects, and anything no caller has a reason to vary (fix existing couplings; don't add speculative knobs).
- One name, one quantity: never let a flag or enum reinterpret a named property or output, and never encode a distinct component as an extra vector-parameter slot — declare separately named properties instead.
- A new optional parameter on an existing object reproduces prior behavior exactly when unset — via the mechanism that actually does (an `addParam` default for a literal; an `isParamValid` fallback when the old value came from another parameter) — and its docstring states the fallback.
- A physical assumption baked into the math but invisible in the input file (implied Poisson ratio, implicit spring, assumed reference state) is stated in `addClassDescription` and the doc page; promote it to a parameter only when already changing that behavior.

## AD and non-AD variants

- New leaf object wanted in both flavors → one class `template <bool is_ad>`: `FooTempl` in the non-AD-named header, `using` pair, both names `registerMooseObject`ed in the same `.C`, explicit instantiation of both, `GenericReal`/`GenericMaterialProperty` aliases for flavor-agnostic members. Mechanic: `moose/framework/include/kernels/BodyForce.h`/`.C` (templated base) or `moose/framework/include/materials/GenericConstantMaterial.h`/`.C` (plain base). Narrative: `moose/framework/doc/content/automatic_differentiation/templated_objects.md` — but its `declareGenericMaterialProperty` is a typo; the real API is `declareGenericProperty<T, is_ad>`.
- Separate classes stay legitimate when: the base contracts diverge (different pure virtuals, `override final`); the template slot is spent on another axis (tensor/variable type); virtual dispatch forbids templating (property UserObjects); the non-AD side needs symbolic-Jacobian machinery (`DerivativeMaterialInterface`, `_Jacobian_mult`); the flavors compute genuinely different things; or it's base-class infrastructure — there the sanctioned shape is the hand-written pair plus a `Generic*` switch (`moose/framework/include/kernels/GenericKernel.h`).
- Some objects are one-flavor by design: FV/functor objects are AD-only (`moose/framework/doc/content/finite_volumes/fv_design.md`); LinearFV is non-AD; hand-Jacobian helpers (`*OffDiag`) are dropped in the AD path, never duplicated.
- Converting an existing pair to a template deletes `ADFoo.h` — leave a one-line shim header including the new one so downstream apps keep compiling.
- Qualify math calls `std::` on concrete `Real` arguments; in scalar-templated/AD code call unqualified with a local `using std::sqrt;` (etc.) so MetaPhysicL's overloads resolve.
- Keep a variant class structurally parallel to its counterpart; justify any difference the variant mechanism does not force.
- A check with nothing AD-dependent about it goes above the `_use_ad` / `is_ad` branch, not inside one arm or copied into both; only AD-specific rejections belong inside a branch.
### Actions and Physics

- Never template an Action/Physics on `is_ad`. AD is a runtime `use_automatic_differentiation` bool held as `const bool _use_ad;` — default `false` on an existing Action lineage (flipping it changes gold files), `true` on a new PhysicsBase, omitted entirely for FV-only Physics.
- Select per-flavor object type strings with `Registry::getClassName<FooTempl<is_ad>>()` when the pair is a real template (compile-checked) over string concatenation. Verify every reachable type string has a registered AD twin across coord-system/formulation combinations; where one doesn't, `paramError("use_automatic_differentiation", ...)` — never let a prefix fabricate an unregistered name.
- The AD path may build a smaller object graph — skip hand-Jacobian helper objects instead of prefixing them.
- Never swallow an Action task with an empty branch in the `_current_task` dispatch — select the variant inside the task's block, keeping the guard adjacent to what it gates: correctness must never depend on else-if ordering. Wholesale guard-clause skips and separate variant classes remain fine.

## Errors and assertions

- `mooseAssert` for invariants only a code bug can violate; `mooseError`/`paramError` for anything reachable from user input or configuration. Put the assert directly before the use it protects. Reference: `moose/tutorials/darcy_thermo_mech/doc/content/workshop/cpp/standards.md` § Code Recommendations.
- The message must describe the condition the adjacent guard actually tests — re-derive it from your own check, never carry wording from the sibling class you mirrored.

## Control flow

- Branch on the variable that directly records a fact — the pointer/optional, `isParamValid`, a set flag — never a numeric proxy like a zero-norm tensor meaning "not set". If no such variable exists, add one.

## Comments

- Method-level documentation (purpose, contract, `@param`/`@return`) goes on the header declaration, not free comments above the `.C` definition; comments in the body carry implementation rationale only.
- A body comment is a one- or two-line statement of fact — the constraint or rationale the code cannot show. A comment can be too long: paragraph-length explanation moves to the header Doxygen or the doc page, and narration of what the next line does is deleted, not shortened.
- A commit that renames a symbol or changes semantics updates the comments describing it in the same commit; before rewording any comment, verify its claim is still true of the code.

## User-facing text

- Error messages and class descriptions use established MOOSE and domain terminology — match how sibling objects word theirs; never invent new phrasings for framework concepts.
- `addClassDescription` is one concise sentence naming what the object computes and what distinguishes it from its siblings — no "Creates a UserObject for..." plumbing. See `moose/framework/doc/content/framework/documenting.md` § MooseObject C++ Documentation.

## Syntax migrations

- Never claim the modern Action/Physics syntax can't reproduce an old setup without checking — read the action's `validParams` and run the converted input (`--check-input` minimum); raise genuine gaps in the PR instead of leaving silent exceptions. Model migration guide: `moose/modules/navier_stokes/doc/content/syntax/Modules/NavierStokesFV/index.md` § How to transition to the Physics syntax.
