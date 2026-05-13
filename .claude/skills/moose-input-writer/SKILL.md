---
name: moose-input-writer
description: Author or modify a MOOSE input file (`.i`) for moose, blackbear, or isopod from a free-form task description. Runs a clarify-first interview before writing, generates a complete runnable input following the catalog conventions, validates with `--check-input`, iterates up to 3 times. Stateless — if the target path exists, edits in place; otherwise creates fresh. Auto-triggers on phrasings like "write an input file for ...", "make a `.i` that ...", or invoke directly via `/moose-input-writer <description>`.
---

# /moose-input-writer

Author and edit `.i` files for `moose`, `blackbear`, and `isopod` — strictly following the conventions in `.claude/contexts/moose-input/`.

This is a **skill**, not a subagent. It runs in the main conversation so `AskUserQuestion` actually reaches the user. Background/headless agents cannot interview, which is why this lives here.

## Usage

```
/moose-input-writer <freeform task description> [<target .i path>]
```

Examples:
- `/moose-input-writer thermomechanical contact problem with finite strain`
- `/moose-input-writer 2D heat conduction with a Dirichlet hot wall ./heat.i`
- `/moose-input-writer make this transient` (against an existing `.i` in cwd)

If `$ARGUMENTS` is empty, ask via `AskUserQuestion`: "What input file do you want me to write or modify?".

## First action — every run

1. Read `.claude/contexts/moose-input/INPUT-MAP.md` to orient.
2. Identify the catalog guides relevant to the task (e.g. for "thermomechanical contact w/ finite strain": `heat-transfer.md`, `solid-mechanics.md`, `contact.md`, `materials.md`, `mesh.md`, `executioner.md`). Read **only** those.
3. Detect mode and binary:
   - **Mode** — if the target file path exists, you are in **modify** mode (load it, treat task as edit). Otherwise **create** mode.
   - **Binary** — auto-detect from cwd: `moose/` → `moose/test/moose_test-opt`; `blackbear/` → `blackbear/blackbear-opt`; `isopod/` → `isopod/isopod-opt`. If cwd is the meta-repo root or anywhere else, default to `isopod/isopod-opt`.

Do not invent block names, type names, or parameters. The catalog plus `moose-params` is the source of truth.

## Tool policy

- `Read`, `Write`, `Edit`, `Glob`, `Grep` — for catalog and `.i` editing.
- `AskUserQuestion` — for the clarify-first interview.
- `Skill` — invoke `moose-params` for type/parameter verification.
- `Bash` — restricted (see Hard constraints).

## Hard constraints

You MAY run **only** these Bash commands while executing this skill:
- `<binary> -i <file> --check-input` (validation loop)
- `ls`, `test`, `stat`, `pwd` (to locate binaries and check file presence)

Forbidden: anything else. No `make`, `cmake`, `cp`, `mv`, `rm`, `> file` truncation, `git`, full solves, mesh generation, or shell pipelines beyond what's listed.

You do NOT:
- Generate mesh files. Use `[Mesh]` generators (`GeneratedMeshGenerator`, etc.) or expect the user to supply a file path.
- Generate `tests` spec files or gold outputs. That's `moose-test-writer`.
- Touch C++ source. If the task requires a new object that doesn't exist yet, report BLOCKED.
- Edit anything outside the target `.i` path (no catalog edits, no Makefile edits, no other inputs).
- Spawn agents.
- Add comments to the generated file. Style is **minimal — clean HIT, no inline comments, no header**.
- Fabricate types or parameters. If `moose-params` doesn't know a type, that type isn't real — pick a different one or BLOCK.
- Silently substitute for a spec-stated structural requirement (element type, mesh topology, coupling, contact, controllability). If you can't satisfy it directly, ask via `AskUserQuestion` or report BLOCKED. Do not paper over the deviation in `Concerns:`.

## Workflow

### Step 1 — orient and detect mode

- Read `INPUT-MAP.md` and the relevant catalog guides.
- **If `physics-spec.md` exists in cwd, read it in full.** It is the authoritative requirements document — every structural statement in it (element type, mesh topology, coupling style, contact algorithm, control wiring, BC placement) is a **hard constraint**, not a default you may override. Numeric placeholders (material constants, time step, mesh resolution) are fine to fill in with sensible defaults.
- Resolve the target file path: use the path the caller provided; if none, derive `./<derived_name>.i` in cwd. Derivation: lowercase the prompt, drop filler ("a", "an", "the", "with", "for", "problem", "case"), join with `_`, truncate to ~5 tokens. E.g. "thermomechanical contact problem with finite strain" → `thermomech_contact_finite_strain.i`.
- Stat the path. If it exists, set mode = `modify`; else mode = `create`.
- Detect the binary (cwd rule above). Verify it exists with `test -x <binary>`. If missing, report BLOCKED with: "Binary not built. Run `cd <app-dir> && METHOD=opt make -j2`."

### Step 2 — interview (create mode) or load (modify mode)

**Create mode — grill one question at a time until no structural assumption remains.**

Use `AskUserQuestion` with **exactly one question per call**. Wait for the answer. Then re-evaluate: do any *structural* forks remain unanswered? If yes, ask the next single question. Repeat until every writer-side axis below is explicitly answered. **Do not assume.** **Do not batch.** A "sensible default" is never an acceptable substitute for a structural decision.

Phrase each question with the recommended option first when one applies. Never spend a question on a numeric placeholder — those get filled silently after the interview converges.

**Writer-side axes that must converge before writing:**

1. **Mesh source** — in-input generators (`GeneratedMeshGenerator`, etc.) vs external file (`.e` / `.msh` via `FileMeshGenerator`). Required as a question whenever the spec implies non-trivial topology: mixed element types (e.g. 1D BAR sharing nodes with 3D HEX), conforming interfaces, embedded inclusions, non-rectangular geometry, or anything that won't come out of `GeneratedMeshGenerator`.
2. **AD vs non-AD** — default AD, but confirm if the spec requires hand-coded Jacobians or non-AD-only objects.
3. **Steady vs transient** — and if transient: time horizon and ramp shape (per spec) before defaulting `dt`.
4. **Strain measure** (when mechanics is active) — small / finite / total Lagrangian / incremental.
5. **Contact algorithm** (when contact is active) — mortar / node-face / penalty.
6. **Coupling style** (when multi-physics) — `[Physics]` shorthand actions, `[Modules]` action, or hand-wired kernels.
7. **FE vs FV vs Linear-FV** — when the catalog presents this as a decision tree for the active physics.
8. **Controls / stochastic wiring** — if the spec asks for `[Controls]`, parameter sweeps, or stochastic-tools coupling, ask which parameters must be controllable and confirm the path before wiring. Never defer this to `Concerns:`.
9. **Solver / preconditioner** — only ask if the user has stated a preference or if the default would obviously fail for the problem class. Otherwise default and move on (this one is fine to leave as writer's call).

**Convergence criterion.** Before you proceed to Step 3, every axis above is either (a) answered explicitly by the user this run, (b) locked by `physics-spec.md`, or (c) a non-applicable axis (e.g. no contact axis when contact isn't active). If even one structural axis is still ambiguous, ask the next single `AskUserQuestion`.

**Spec-driven runs.** When `physics-spec.md` is present, treat each axis above as already-answered if the spec gives a concrete answer; otherwise ask. The grill's job is then to:
1. Resolve any spec requirement you cannot directly express in HIT (e.g. spec says "1D BAR elements sharing nodes with 3D HEX" — that needs an external mesh; ask for the file path or BLOCK).
2. Fill structural gaps the spec leaves open ("writer's call" items that still fork the file shape).
3. Confirm any numeric placeholder where a wrong default would silently change the answer by an order of magnitude.

**Anti-pattern — silent substitution.** If you find yourself about to (a) replace a stated element type / mesh topology with a proxy, (b) skip a stated `[Controls]` requirement and note it under Concerns, (c) substitute a different coupling style, contact algorithm, or BC type than the spec specifies — **stop and ask, or BLOCK.** A `Concerns:` line that reads "X is a placeholder / not yet wired / replaced with Y" for a *spec-stated structural* requirement is a bug, not a deliverable.

**Numeric placeholders are not part of the grill.** Material constants (E, ν, α, k, ρ, cp), time-step size, output frequency, mesh resolution, exact sideset coordinates — pick sensible defaults silently and list them in `Concerns:`. Never burn an `AskUserQuestion` on these unless the user has signalled they want to specify.

**"I don't know — pick something sensible"** is a legitimate user answer for axis 9 (solver) and for clearly numeric placeholders. For axes 1–8 it is not — re-pose the question more concretely (e.g. offer two named options) rather than guessing.

**Modify mode.** Read the existing `.i`. Skip the interview unless the requested change is itself ambiguous (e.g. user says "make it 3D" but the existing file uses a `FileMesh`). When ambiguous, ask one question at a time the same way until the change is fully specified.

### Step 3 — verify types via `moose-params`

For every type you intend to use, invoke the `moose-params` skill with the exact type name. Confirm:
- The type is registered.
- You're providing every `required: 'Yes'` parameter.
- You're not inventing parameter names.

Use the lean (default) mode of `moose-params` for this; it gives required-with-descriptions plus optional names. Drill into a specific param (`/moose-params <Type> <Param>`) only when you need the cpp_type or default to make a decision.

### Step 4 — write or edit the file

**Style:** minimal. Clean HIT, no inline comments, no header block, no separator lines. Idiomatic spacing matching the catalog examples. Default to AD-named classes (e.g. `ADDirichletBC`, not `DirichletBC`) unless the user explicitly opted out of AD.

**Scope:** complete and runnable. Include `[Mesh]`, `[Variables]`, `[Kernels]`/`[Physics/...]`, `[Materials]` (if applicable), `[BCs]`, `[ICs]` (if needed for the problem), `[Executioner]`, `[Outputs]`, and a minimal `[Postprocessors]` if the catalog suggests one. No empty blocks.

In modify mode, make surgical edits — don't rewrite blocks the user didn't ask to change.

### Step 5 — validate (the loop)

Run: `<binary> -i <target_path> --check-input`

- **Pass (exit 0)** → proceed to Step 6.
- **Fail** → read the error message. Identify the cause (unknown type, missing required param, wrong block, type mismatch, etc.). Edit the file to fix. Re-run `--check-input`. **Cap: 3 attempts total.**

After 3 failed attempts, stop and report STUCK with the final error message verbatim and a one-line summary of each fix you tried.

### Step 6 — report

End the run with a structured report:

```
Status: DONE | DONE_WITH_CONCERNS | STUCK | BLOCKED | NEEDS_CONTEXT
File: <absolute path to .i>
Binary: <path used for --check-input>
Mode: create | modify
Interview answers: <one-line summary, only in create mode>
--check-input: PASS (after N attempts) | FAIL
```

If DONE_WITH_CONCERNS, add a `Concerns:` section listing **only numeric placeholders or factual notes** the user should verify — e.g. "default Young's modulus is a placeholder", "back sideset = z-min per GeneratedMesh convention". Structural deviations from a stated requirement do not belong here; if you would need to write one, you should have asked or BLOCKED in Step 2.

If STUCK, add the verbatim final error and a `Tried:` list of edits you attempted.

## Rules

- **Catalog first.** When the catalog gives a decision tree (e.g. "FE vs FV vs Linear-FV"), follow it. Don't invent.
- **Mirror, don't invent.** Type names, block names, parameter spellings — copy from the catalog or `moose-params`, never guess.
- **Minimal style.** No comments. No headers. No `# ----` separators. The file should look like one a human would commit.
- **Surgical edits in modify mode.** If the user says "swap to mortar contact", change only the contact-related blocks; leave kernels, mesh, executioner alone.
- **No half-finished work.** A file the skill emits must pass `--check-input` or the report must be STUCK.
- **Always OK to stop.** Prefer BLOCKED ("can't tell which strain measure you want and no sensible default") or NEEDS_CONTEXT over guessing on a fork-the-file decision.
- **Spec is law.** When `physics-spec.md` exists, its structural statements (element types, mesh topology, coupling, contact, controls) are hard requirements. Ask or BLOCK before deviating — never substitute and apologise in `Concerns:`.
