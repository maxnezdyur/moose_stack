---
name: moose-code-standards
description: Applies MOOSE coding standards for C++ and Python in moose, blackbear, and isopod, covering typed name parameters, AD and non-AD variants, Actions and Physics, errors, and class descriptions. Use when writing, editing, or reviewing .C, .h, or .py source, or when planning a new MOOSE class before code exists.
user-invocable: false
---

# MOOSE code standards

The canonical standard is `moose/framework/doc/content/sqa/framework_scs.md` (relative to the meta-repo root). It is maintained upstream and shared by all three repos. Read it directly instead of working from remembered standards. `moose/AGENTS.md` is a second upstream standard for all three repos; read it as well and apply every code rule in it. The rules below are the additions that file does not carry.

## New classes

- A brand-new class registers no deprecated, legacy, or back-compat parameters, even when the sibling `validParams()` it mirrors carries them; it has no existing inputs to stay compatible with. When an existing Action still accepts an old name, translate old to new where the Action sets the object's parameters. Only a renamed or relocated existing type (`registerMooseObjectRenamed`) inherits real user inputs and may keep its deprecated params.

## Input parameters

- A coupled-object name reached through a string literal (`getMaterialPropertyByName`, `getVectorPostprocessorValueByName`, `getUserObjectByName`, `getPostprocessorValueByName`, `declareProperty`) is a typed name parameter instead: `MaterialPropertyName`, `VectorPostprocessorName`, `UserObjectName`, `PostprocessorName`, or `MooseFunctorName`, not `std::string`. It defaults to the current literal so existing inputs keep working. Parameterize the whole name, not a fragment or an index. Canonical pattern: `moose/framework/doc/content/syntax/Materials/index.md`, section "Property Names".
- The literal stays when it is a class-family contract name disambiguated by `base_name` (`stress`, `elastic_strain`, `Jacobian_mult`, `mechanical_strain`), a name an Action generates for its own objects, or a name no caller has a reason to vary. Fix existing couplings; do not add speculative knobs.
- One name, one quantity. A flag or enum does not reinterpret a named property or output, and a distinct component is a separately named property, not an extra vector-parameter slot.
- A new optional parameter on an existing object reproduces prior behavior exactly when unset, through the mechanism that actually does so (an `addParam` default for a literal; an `isParamValid` fallback when the old value came from another parameter), and its docstring states the fallback.
- A physical assumption baked into the math but invisible in the input file (implied Poisson ratio, implicit spring, assumed reference state) is stated in `addClassDescription` and on the doc page. Promote it to a parameter only when already changing that behavior.

## AD and non-AD variants

- A new leaf object wanted in both flavors is one class `template <bool is_ad>`: `FooTempl` in the non-AD-named header, a `using` pair, both names registered with `registerMooseObject` in the same `.C`, explicit instantiation of both, and `GenericReal` / `GenericMaterialProperty` aliases for flavor-agnostic members. Mechanic: `moose/framework/include/kernels/BodyForce.h` and `.C` (templated base) or `moose/framework/include/materials/GenericConstantMaterial.h` and `.C` (plain base). Narrative: `moose/framework/doc/content/automatic_differentiation/templated_objects.md`; its `declareGenericMaterialProperty` is a typo, the real API is `declareGenericProperty<T, is_ad>`.
- Separate classes stay legitimate when the base contracts diverge (different pure virtuals, `override final`), the template slot is spent on another axis (tensor or variable type), virtual dispatch forbids templating (property UserObjects), the non-AD side needs symbolic-Jacobian machinery (`DerivativeMaterialInterface`, `_Jacobian_mult`), the flavors compute genuinely different things, or the class is base-class infrastructure. There the sanctioned shape is the hand-written pair plus a `Generic*` switch (`moose/framework/include/kernels/GenericKernel.h`).
- Some objects are one-flavor by design: FV and functor objects are AD-only (`moose/framework/doc/content/finite_volumes/fv_design.md`); LinearFV is non-AD; hand-Jacobian helpers (`*OffDiag`) are dropped in the AD path, not duplicated.
- Converting an existing pair to a template deletes `ADFoo.h`; leave a one-line shim header including the new one so downstream apps keep compiling.
- Qualify math calls `std::` on concrete `Real` arguments. In scalar-templated or AD code call unqualified with a local `using std::sqrt;` (and the like) so MetaPhysicL's overloads resolve.
- A variant class stays structurally parallel to its counterpart; any difference the variant mechanism does not force needs a stated reason.
- A check with nothing AD-dependent about it goes above the `_use_ad` / `is_ad` branch, not inside one arm or copied into both. Only AD-specific rejections belong inside a branch.

### Actions and Physics

- An Action or Physics is not templated on `is_ad`. AD is a runtime `use_automatic_differentiation` bool held as `const bool _use_ad;`: default `false` on an existing Action lineage (flipping it changes gold files), `true` on a new PhysicsBase, omitted entirely for FV-only Physics.
- Select per-flavor object type strings with `Registry::getClassName<FooTempl<is_ad>>()` when the pair is a real template (compile-checked), not by string concatenation. Every reachable type string needs a registered AD twin across coord-system and formulation combinations; where one is missing, `paramError("use_automatic_differentiation", ...)` rather than letting a prefix fabricate an unregistered name.
- The AD path may build a smaller object graph: skip hand-Jacobian helper objects instead of prefixing them.
- An Action task is not swallowed by an empty branch in the `_current_task` dispatch. Select the variant inside the task's block and keep the guard adjacent to what it gates, so correctness does not depend on else-if ordering. Wholesale guard-clause skips and separate variant classes remain fine.

## Errors, assertions, and class descriptions

- `mooseAssert` is for invariants only a code bug can violate; `mooseError` and `paramError` are for anything reachable from user input or configuration. Put the assert directly before the use it protects. Reference: `moose/tutorials/darcy_thermo_mech/doc/content/workshop/cpp/standards.md`, section "Code Recommendations".
- The message describes the condition the adjacent guard actually tests. Derive it from your own check, not from the sibling class you mirrored.
- Error messages and class descriptions use the terminology sibling objects use for the same framework concept. `addClassDescription` is one concise sentence naming what the object computes and what distinguishes it from its siblings, with no "Creates a UserObject for..." plumbing. See `moose/framework/doc/content/framework/documenting.md`, section "MooseObject C++ Documentation".

## Comments and doc strings

`moose/AGENTS.md` sections 4 and 9 are the base rules. These rules add what review of our pull requests showed. They apply to code comments, Doxygen comments and parameter doc strings.

- Use the term and the notation that MOOSE source and documentation already use. Replace a word or phrase that reads as machine-drafted with the plain MOOSE wording. Keep a word that names an existing identifier. For example, write "recompute", not "refresh".
- Describe the code as it is now. Do not narrate edit history. Do not record dated measurements, debugging steps or guesses in a comment. Put them in a tracked file or a plot. Keep a measured value that is the source of a constant or a tolerance.
- When a sentence gives a reason, state the cause, the consequence and the link between them. Do the same when a stated result does not follow obviously from its condition. This rule does not require a reason on every sentence.
- Read each sentence literally. Rewrite a sentence whose literal meaning is not the intended meaning. Check the converse that a condition or a restriction implies. Remove a conjunction that states a contrast that does not exist.
- Check each general claim against every case that can occur in the scope the text sets. A general claim says or implies all, every, always, never or only. When the claim fails in one case, name the condition or the set where it holds. Do not use a frequency word that is stronger than the facts support.
- Use the term that names the exact object or relation. For example, write that a rank "owns" a node when you mean parallel ownership.
- Spell out, define or link an abbreviation or a term that a MOOSE developer would need to look up. Keep abbreviations in common MOOSE, libMesh and PETSc use, such as "qp" and "dof". Keep a proper name.
- After each commit, read again every comment that describes what the commit changed. Correct each statement that the commit made false. Correct a comment that contradicts the setting on its own line.
- Do not comment on a case that does what the reader expects.
- Reflow a comment or a doc string after you edit it. Leave no short fragment on its own line when it fits on the line before.
- Check the grammar of each sentence that you write or reword: each article, each preposition and each word form.
- Check each list and equation in a comment for a case whose absence makes it wrong. Add the missing case, or state that the list is partial.

## Syntax migrations

- A claim that the modern Action or Physics syntax cannot reproduce an old setup rests on reading the action's `validParams` and running the converted input (`--check-input` at minimum). Raise genuine gaps in the PR instead of leaving silent exceptions. Model migration guide: `moose/modules/navier_stokes/doc/content/syntax/Modules/NavierStokesFV/index.md`, section "How to transition to the Physics syntax".
