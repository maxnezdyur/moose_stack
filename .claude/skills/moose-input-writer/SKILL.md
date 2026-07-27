---
name: moose-input-writer
description: Author or modify a MOOSE input file (`.i`) for moose, blackbear, or isopod from a free-form task description. Runs a clarify-first interview before writing, generates a complete runnable input following MOOSE input conventions, validates with `--check-input`, iterates up to 3 times. Stateless — if the target path exists, edits in place; otherwise creates fresh. Auto-triggers on phrasings like "write an input file for ...", "make a `.i` that ...", or invoke directly via `/moose-input-writer <description>`.
---

# /moose-input-writer

Author or edit `.i` files for `moose`, `blackbear`, and `isopod`. Runs in the main conversation (not a subagent) so `AskUserQuestion` actually reaches the user — the clarify-first interview is the point.

## Usage

```
/moose-input-writer <freeform task description> [<target .i path>]
```

If `$ARGUMENTS` is empty, ask what to write. If no target path is given, derive `./<name>.i` from the prompt (lowercase, drop filler words, join ~5 tokens with `_` — "thermomechanical contact problem with finite strain" → `thermomech_contact_finite_strain.i`). If the target exists you are in **modify** mode: load it, treat the task as a surgical edit, and skip the interview unless the change itself is ambiguous.

## Ground truth

- **Types and parameters** — verify every type via the `moose-params` skill before use: confirm it is registered, supply every `required: 'Yes'` parameter, never invent parameter names. If `moose-params` doesn't know a type, that type isn't real — pick another or BLOCK. Drill into a single param (`/moose-params <Type> <Param>`) only when a cpp_type or default drives a decision.
- **Block structure** — mirror existing example inputs (`Grep`/`Glob` over `*/test/tests/**/*.i` and module test dirs); don't invent block layouts. Use `codegraph_explore "<TypeName>"` to understand what an object does or to choose between candidates.
- **Binary** (for `--check-input`), by cwd: `moose/` → `moose/test/moose_test-opt`; `blackbear/` → `blackbear/blackbear-opt`; `isopod/` → `isopod/isopod-opt`; anywhere else → `isopod/isopod-opt`. Verify with `test -x`; if missing, report BLOCKED with: "Binary not built. Run `cd <app-dir> && METHOD=opt make -j2`."

## Scope

Bash is for validation only: `<binary> -i <file> --check-input`, plus `ls`/`test`/`stat`/`pwd`. No builds, solves, mesh generation, git, or file operations through the shell — this skill writes one `.i` and proves it parses, nothing more.

Also out of scope: mesh files (use `[Mesh]` generators or ask for a file path), `tests` specs and gold outputs (that's `moose-test-writer`), C++ source (if the task needs an object that doesn't exist, report BLOCKED), edits to any file other than the target `.i`, and spawning agents.

## Interview (create mode)

Ask via `AskUserQuestion`, one question at a time, until every structural fork below is resolved — by the user, by `physics-spec.md`, or by not applying to the problem. Structural forks change the shape of the file; a "sensible default" on one is a guess that wastes the run, so for axes 1–8 "pick something sensible" is not an acceptable answer — re-pose with two named options instead.

1. **Mesh source** — generators vs external file (`FileMeshGenerator`). Must be asked whenever the topology won't come out of `GeneratedMeshGenerator`: mixed element types (e.g. 1D BAR sharing nodes with 3D HEX), conforming interfaces, embedded inclusions, non-rectangular geometry.
2. **AD vs non-AD** — default AD; confirm only if the spec implies hand-coded Jacobians or non-AD-only objects.
3. **Steady vs transient** — and if transient, horizon and ramp shape before defaulting `dt`.
4. **Strain measure** (mechanics active) — small / finite / total Lagrangian / incremental.
5. **Contact algorithm** (contact active) — mortar / node-face / penalty.
6. **Coupling style** (multiphysics) — `[Physics]` shorthand actions, `[Modules]` action, or hand-wired kernels.
7. **FE vs FV vs Linear-FV** — when the physics supports more than one discretization.
8. **Controls / stochastic wiring** — which parameters must be controllable; confirm the path before wiring.
9. **Solver / preconditioner** — writer's call; ask only if the user stated a preference or the default would clearly fail.

Numeric placeholders (material constants, dt, output frequency, mesh resolution, sideset coordinates) are never interview questions — fill sensible defaults silently and list them under `Concerns:`, unless a wrong default would silently change the answer by an order of magnitude, in which case confirm it.

**`physics-spec.md` in cwd is law.** Read it in full; every structural statement (element type, mesh topology, coupling style, contact algorithm, control wiring, BC placement) is a hard constraint and counts as an answered axis. If a spec requirement can't be expressed directly in HIT, ask or BLOCK — never substitute a proxy, skip a stated `[Controls]` requirement, or swap the specified algorithm and note the deviation under `Concerns:`. That section is for numeric placeholders and factual notes only.

## Write

Minimal style: clean HIT, no comments, no header, no separator lines — the file should look like one a human would commit. Complete and runnable: `[Mesh]`, `[Variables]`, kernels/physics, `[Materials]`, `[BCs]`, `[Executioner]`, `[Outputs]`, plus `[ICs]`/`[Postprocessors]` where warranted; no empty blocks. AD-named classes (`ADDirichletBC`, not `DirichletBC`) unless the user opted out. In modify mode, touch only the blocks the change requires.

## Validate

`<binary> -i <target> --check-input`. On failure, read the error, fix, re-run — 3 attempts total. Then report STUCK with the final error verbatim and a `Tried:` list of attempted fixes.

## Report

```
Status: DONE | DONE_WITH_CONCERNS | STUCK | BLOCKED | NEEDS_CONTEXT
File: <absolute path to .i>
Binary: <path used for --check-input>
Mode: create | modify
Interview answers: <one-line summary, create mode only>
--check-input: PASS (after N attempts) | FAIL
```

`Concerns:` (with DONE_WITH_CONCERNS) lists numeric placeholders and factual notes only — e.g. "default Young's modulus is a placeholder", "back sideset = z-min per GeneratedMesh convention". A file the skill emits must pass `--check-input` or the report must be STUCK; prefer BLOCKED/NEEDS_CONTEXT over guessing on any fork-the-file decision.
