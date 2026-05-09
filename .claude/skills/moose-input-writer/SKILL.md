---
name: moose-input-writer
description: Author or modify a MOOSE input file (`.i`) for moose, blackbear, or isopod from a free-form task description. Runs a clarify-first interview before writing, generates a complete runnable input following the catalog conventions, validates with `--check-input`, iterates up to 3 times. Stateless — if the target path exists, edits in place; otherwise creates fresh. Auto-triggers on phrasings like "write an input file for ...", "make a `.i` that ...", or invoke directly via `/moose-input-writer <description>`.
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
  - Skill
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

## Workflow

### Step 1 — orient and detect mode

- Read `INPUT-MAP.md` and the relevant catalog guides.
- Resolve the target file path: use the path the caller provided; if none, derive `./<derived_name>.i` in cwd. Derivation: lowercase the prompt, drop filler ("a", "an", "the", "with", "for", "problem", "case"), join with `_`, truncate to ~5 tokens. E.g. "thermomechanical contact problem with finite strain" → `thermomech_contact_finite_strain.i`.
- Stat the path. If it exists, set mode = `modify`; else mode = `create`.
- Detect the binary (cwd rule above). Verify it exists with `test -x <binary>`. If missing, report BLOCKED with: "Binary not built. Run `cd <app-dir> && METHOD=opt make -j8`."

### Step 2 — interview (create mode) or load (modify mode)

**Create mode.** Identify the 1–4 questions whose answers genuinely fork the file shape. Examples:
- Dimension (2D / 3D)
- Strain measure (small / finite / total Lagrangian / incremental)
- AD vs non-AD
- Steady vs transient
- Contact algorithm (mortar / node-face / penalty)
- Coupling style (full thermomech via `[Modules]`, or hand-wired kernels)

Pose them in **a single batched `AskUserQuestion` call** of up to 4 questions. Phrase each question with the recommended option first. Only ask a second batch if the first answers expose new ambiguity that genuinely changes the file shape — never to gather details that have sensible defaults.

For details with sensible defaults (mesh dimensions, time-step size, output frequency, exact Young's modulus value), pick a default. The user will iterate.

**Modify mode.** Read the existing `.i`. Skip the interview unless the requested change is itself ambiguous (e.g. user says "make it 3D" but the existing file uses a `FileMesh`).

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

If DONE_WITH_CONCERNS, add a `Concerns:` section listing things the user should verify (e.g. "I assumed a 1×1 GeneratedMesh — replace with your real mesh", "default Young's modulus is a placeholder").

If STUCK, add the verbatim final error and a `Tried:` list of edits you attempted.

## Rules

- **Catalog first.** When the catalog gives a decision tree (e.g. "FE vs FV vs Linear-FV"), follow it. Don't invent.
- **Mirror, don't invent.** Type names, block names, parameter spellings — copy from the catalog or `moose-params`, never guess.
- **Minimal style.** No comments. No headers. No `# ----` separators. The file should look like one a human would commit.
- **Surgical edits in modify mode.** If the user says "swap to mortar contact", change only the contact-related blocks; leave kernels, mesh, executioner alone.
- **No half-finished work.** A file the skill emits must pass `--check-input` or the report must be STUCK.
- **Always OK to stop.** Prefer BLOCKED ("can't tell which strain measure you want and no sensible default") or NEEDS_CONTEXT over guessing on a fork-the-file decision.
