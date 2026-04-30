---
name: moose-design-feature
description: Front door before /moose-build-feature. Takes a vague feature idea, grills the user against MOOSE-specific axes (object kind, inputs/outputs, physics/math), spawns an investigator to scout for reusable code, and writes a structured spec.md that /moose-build-feature consumes. Manual-invoke only.
disable-model-invocation: true
---

# /moose-design-feature

Convert a vague feature idea into a concrete `spec.md` for `/moose-build-feature`. Grills the user, scouts the codebase for reuse, halts on near-matches, and stops at a written spec — does NOT auto-build.

## Usage

```
/moose-design-feature <freeform idea>
```

Examples:
- `/moose-design-feature add a kernel for thermal-anisotropic conductivity in solid_mechanics`
- `/moose-design-feature postprocessor that integrates strain energy over a subdomain`

**Assumes the user already ran `/new-feature`** and is working inside that worktree. Refuses to run otherwise.

## Steps

### 1. Bootstrap

1. Read `$ARGUMENTS`. If empty, ask the user for the idea via `AskUserQuestion`.
2. Detect the worktree root: walk up from CWD until you find a `.git` file (not directory — submodule worktrees have a `.git` *file*) and a sibling `moose/`, `blackbear/`, `isopod/` layout. If detection fails, refuse with: *"Run /new-feature first; this skill only runs inside a feature worktree."*
3. Check for `<worktree-root>/spec.md`. If present, ask via `AskUserQuestion`:
   - **Resume** — load the existing spec, identify which sections are still incomplete, jump into grilling on those.
   - **Restart** — proceed as if no spec existed; the existing file gets overwritten at step 6.
   - **Cancel** — stop the skill.

### 2. Light grill — round 1

Grill the user across the three MOOSE-specific axes using `AskUserQuestion`. One or two questions per axis. Don't ask things the codebase can answer — `Grep`/`Glob` first.

| Axis | Sample probes |
|---|---|
| Object kind + base class | "Is this a `Kernel`, `IntegratedBC`, `Material`, `Postprocessor`, `Action`, `UserObject`, …?" "Which base class — e.g. `ADKernelGrad` vs `Kernel`?" |
| Inputs / outputs | "What `coupled` variables does it read?" "What materials does it consume?" "Does it write an AuxVariable, a Reporter, or just a residual contribution?" "What `validParams` does it need?" |
| Physics / math | "Write the equation in plain math or LaTeX. What residual term, what Jacobian entries?" Push back hard on hand-waving — vague math becomes vague code. |

For each grill round, ask 1–2 questions at a time. Don't dump all questions at once.

### 3. Scout — round 1

Decompose the feature into independent **search angles**, then spawn one background `investigator` per angle in a **single message with multiple `Agent` tool calls in parallel** (`run_in_background: true` on each). Use `subagent_type: "investigator"`.

**When to fan out (multiple investigators):**
- The feature touches more than one MOOSE object kind (e.g. a Kernel + a paired Material).
- The physics term has a distinct mathematical name *and* a distinct user-facing name (search both vocabularies separately — they live in different parts of the tree).
- The feature plausibly already exists in more than one repo (e.g. solid-mechanics in `moose/modules/solid_mechanics` *and* `blackbear`); give each repo its own investigator.
- A test-side angle is independent of the implementation-side angle (e.g. "are there existing `tests` specs that exercise this physics" vs "are there existing classes that compute it").

**When one investigator is enough:**
- Single object kind, single repo, single conceptual name with no obvious synonyms.
- Tiny features (one-liner extensions of an existing class).

**Cap at ~4 parallel investigators.** More than that and findings start overlapping; you also lose the ability to hold them all in context when they return. If you'd want more angles, queue the extras for round 2.

**Per-angle prompt template** — fill in the bracketed pieces and send each as a separate `Agent` call.

The template has three jobs:
1. Pin down the **operator / equation**, not just the keywords. Without this an investigator will report "diffusion kernel" as a match for Navier–Stokes momentum because the names overlap.
2. List **negative criteria** — what would NOT count as a match — so the investigator drops near-cousins instead of returning them.
3. Force **per-hit verification**: the investigator must open each candidate, read the residual line, and rate the match strength. Grep hits don't count.

```
Agent({
  subagent_type: "investigator",
  run_in_background: true,
  prompt: "Search angle: <one-line angle name, e.g. 'Kernel implementations of anisotropic conduction'>

           ## What the user wants (shared across all angles)

           **Plain-English target:** <one paragraph from the grill — what the feature does>

           **Operator / equation:** <full math, e.g. '∇·(K∇T) with rank-2 K' or
             '∂u/∂t + (u·∇)u = -∇p/ρ + ν∇²u (incompressible momentum)'>

           **Distinguishing properties:** <what makes this *different* from name-cousins —
             e.g. 'K is a rank-2 tensor, not a scalar'; 'momentum equation, not continuity';
             'requires ADReal templating'; 'integrates over a subdomain, not the full mesh'>

           ## What this angle covers

           **Scope:** <one of ~/projects/moose_stack/moose, /blackbear, /isopod, or the worktree>

           **Specifically search for:**
           - <angle-specific class names / synonyms>
           - <angle-specific Tester `type = X` references, if applicable>
           - <angle-specific base class hierarchy>

           Do NOT search outside this angle — a sibling investigator is covering <other angle>.

           ## What is NOT a match (negative criteria)

           - <e.g. 'Plain Diffusion / FunctionDiffusion: scalar coefficient, not tensor'>
           - <e.g. 'INSMass: continuity only, not momentum'>
           - <e.g. 'Non-AD-only kernels: we need ADReal templating'>
           - Any class that matches by name keywords but computes a different operator.

           ## Required verification per hit

           For each candidate, you MUST:
           1. Open the file and read the residual / contribution code
              (`computeQpResidual`, `computeValue`, `execute`, etc.).
           2. Quote the actual residual line(s) in your report.
           3. Rate the match:
              - **structural** — same base class AND same operator/equation as 'Operator /
                equation' above
              - **behavioral** — different base class but same operator/equation
              - **naming** — matches keywords but computes a different operator → DROP,
                do not return as a hit
           A grep hit is not a match. A hit you haven't opened and read is not a hit.

           ## Output

           For each match, return:
           - `<file_path>:<line>` of the residual / contribution code
           - The quoted residual line(s)
           - Match strength: **structural** or **behavioral**
           - One sentence on how it relates to the operator/equation above

           If nothing in this angle survives verification, say so explicitly — a clean
           'no match in this angle' is more useful than a list of naming false positives."
})
```

**Briefing the user:** before launching, tell them in one line which angles you're fanning out across (e.g. *"Scouting in parallel: Kernel side in moose, Material side in blackbear, test-side across both. I'll fold findings in as each returns."*). Then continue the grill loop while they run.

**Returning findings:** investigators land independently. As each notification arrives, merge its findings into a running list. Don't wait for all of them to land before continuing the grill — only block on them when you reach the reuse-halt check in step 4.

### 4. Reuse halt — when scout returns

When the investigator reports back, parse its findings:

- **Exact or near-exact match exists** → STOP the loop. Surface the match (file:line + one-line description). Use `AskUserQuestion` to force a decision before continuing:
  - **Reuse as-is** — abandon writing new code; spec captures only test/doc work
  - **Extend** — add a parameter, derived class, template specialization, virtual hook
  - **Write parallel** — user must give a one-sentence justification (recorded in spec)
  - **Abandon idea** — feature is already there, no work needed
- **Close but not direct** — record the related code; carry into the next grill round to ask "should we extend X or write fresh?"
- **No match** — record the negative result ("searched for X, Y, Z — nothing found") so the spec can prove the search happened.

### 5. Loop until converged

Repeat steps 2–4 with progressively tighter questions, each round informed by what scout already turned up. After each round, self-assess whether all six spec sections (see §6) can be filled in concretely. Each section needs at least one specific fact, not a placeholder.

When the skill judges itself ready, present a draft spec to the user via `AskUserQuestion`:
- **Looks good — write it** → go to step 6
- **Keep grilling about X** → user names a section that needs more depth; loop continues there
- **Cancel** → stop without writing

### 6. Write `<worktree-root>/spec.md`

Use this template. Fill every section concretely; do not leave `TODO`s.

```markdown
# <feature name>

## Summary
<one paragraph: what the feature does, why it's needed, the user-facing knob>

**Repo:** `moose` | `moose/modules/<m>` | `blackbear` | `isopod`
**Object kind:** Kernel / BC / Material / Postprocessor / Action / UserObject / …
**Predicted files to touch:**
- `<repo>/src/<area>/<NewClass>.C`
- `<repo>/include/<area>/<NewClass>.h`
- `<repo>/test/tests/<area>/<feature>/tests`
- `<repo>/test/tests/<area>/<feature>/<feature>.i`
- `<repo>/doc/content/source/<area>/<NewClass>.md` *(if doc plan = on)*

## Physics / math + signature
<equation in LaTeX or plain math, with each symbol defined>

**validParams shape:**
- `<param_name>` (`<Type>`) — <description>
- `coupled("<var_name>")` — <description>
- ...

**Residual / contribution form:**
<one-line description of computeQpResidual, computeValue, execute, etc.>

## Reuse decisions
<one entry per investigator finding>

### `<file_path>:<line>` — `<ClassName>`
**What it does:** <one sentence>
**Decision:** Reuse / Extend / Parallel
**Why:** <one sentence — for Parallel, justify why a new implementation is warranted>

<repeat for each finding; if no findings: "Searched for <terms>; nothing matched.">

## Test plan
- **<test_name>** — Tester=`<Exodiff|CSVDiff|RunException|...>`. Asserts: <observable consequence, not just "runs without error">. Mutation rationale: <if <line of new code> were no-op'd, this test fails because <reason>>.
- ... (one entry per test)

## Doc plan
**Needed:** yes / no
**Page:** `<repo>/doc/content/source/<area>/<NewClass>.md`
**Public surface:** <which params, behaviors are part of the documented API>

## Out of scope
- <explicit non-goal #1>
- <explicit non-goal #2>
- ...
```

### 7. Stop

Tell the user:

> Spec written to `<worktree-root>/spec.md`. Review it, edit if needed, then run:
>
> ```
> /moose-build-feature spec.md
> ```

Do **not** auto-invoke `/moose-build-feature`. The human review pass on the spec is load-bearing.

## Hard constraints

- **Never edit code.** This skill writes one file: `spec.md`. Nothing else.
- **Never commit, push, or invoke `/moose-build-feature`.** Hand-off is manual.
- **Never run builds, tests, or formatters.** Spec phase only.
- **Refuse outside a worktree.** No spec without `/new-feature` first.
- **No filler in the spec.** If a section can't be filled concretely, the loop is not done — keep grilling.
- **Investigator findings are advisory.** The user owns reuse decisions, recorded in the spec.

## Failure handling

- **Investigator returns BLOCKED or empty** → continue without scout for that round; note in spec under Reuse decisions: "Investigator failed: <reason>". Don't fabricate findings.
- **User abandons mid-grill** → no spec is written. Tell the user: "No spec saved. Re-run when ready."
- **Existing spec is malformed on resume** → fall back to restart with a warning.

## Canonical references

- `/moose-build-feature` — the consumer of this skill's output. Match its `{repo, kind, files-to-touch}` vocabulary so step 1 of that skill confirms cleanly.
- `moose-implementer` agent — has the "Reuse over redundancy" rule this skill operationalizes.
- `grill-me` skill — generic grilling reference; this skill is MOOSE-axis-specific so it doesn't invoke grill-me directly.
