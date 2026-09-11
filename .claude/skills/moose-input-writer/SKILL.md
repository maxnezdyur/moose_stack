---
name: moose-input-writer
description: Writes or edits one MOOSE input file (.i) for moose, blackbear, or isopod from a task description. Resolves the structural forks with the user first, verifies every object type through moose-params, and proves the file parses with --check-input. Use for "write an input file for ...", "make a .i that ...", "add a BC to this input", or /moose-input-writer <task> [<target .i>].
argument-hint: "<task> [<target .i>]"
effort: high
disallowed-tools: Agent
---

# moose-input-writer

Usage: `/moose-input-writer <task> [<target .i>]`. With no arguments, ask what to write. With no
target path, derive `./<name>.i` from the task (lowercase, filler words dropped, about five tokens
joined with `_`). When the target exists, edit it in place: touch only the blocks the change needs
and skip the interview unless the change itself is ambiguous.

This skill produces one `.i` that passes `--check-input`, nothing else. It does not write mesh
files (use `[Mesh]` generators or ask for a path), `tests` specs or gold (the `moose-test-writer`
agent does that), or C++ (an object that does not exist means BLOCKED). It edits no file other
than the target. Bash is for `--check-input` and read-only file checks only: no builds, solves,
mesh generation, or git.

## Ground truth

Every type in the file is verified through the `moose-params` skill before use: it must be
registered, and every parameter it lists as required must be supplied. Parameter names are never
invented. A type `moose-params` reports as `NO_NODE` is not real; pick another or BLOCK. Look up
a single parameter (`--param`) only when its cpp_type or default drives a decision. Mirror block
layout from existing inputs under `*/test/tests/**/*.i` and module test dirs; use
`codegraph_explore "<TypeName>"` to learn what an object does or to choose between candidates.

## Interview (create mode)

Structural forks change the shape of the file, so a guessed default on one wastes the run. Resolve
each fork by the user, by `physics-spec.md`, or by not applying, before writing: mesh source
(generators vs `FileMeshGenerator`, whenever the topology is not a `GeneratedMeshGenerator`
box), AD vs non-AD (default AD), steady vs transient (with horizon and ramp), strain measure,
contact algorithm, coupling style (`[Physics]`, `[Modules]`, or hand-wired kernels), FE vs FV vs
linear FV, and controls or stochastic wiring. Solver and preconditioner are the writer's call
unless the user stated a preference or the default would clearly fail. Resolve independent
forks in one `AskUserQuestion` round (up to 4 per call). "Pick something sensible" is not an
answer on a structural fork; re-pose it with two named options.

Numeric placeholders (material constants, dt, output frequency, mesh resolution, sideset
coordinates) are not interview questions: fill sensible defaults and list them under Concerns,
unless a wrong default would change the answer by an order of magnitude, in which case confirm it.

If `physics-spec.md` exists in cwd, read it in full; every structural statement in it (element
type, mesh topology, coupling style, contact algorithm, control wiring, BC placement) is a
constraint and counts as a resolved fork. A spec requirement that HIT cannot express directly is a
question or a BLOCK, not a proxy, a skipped `[Controls]` block, or a swapped algorithm.

## Write

Complete and runnable: `[Mesh]`, `[Variables]`, kernels or physics, `[Materials]`, `[BCs]`,
`[Executioner]`, `[Outputs]`, plus `[ICs]` and `[Postprocessors]` where warranted; no empty
blocks. AD-named classes (`ADDirichletBC`, not `DirichletBC`) unless the user opted out. Style
follows the near-commentless `.i` policy in the `moose-test-standards` skill: no header or
separator lines, and the comment density of the inputs you mirrored.

## Validate

Binary: the one that registers the objects used, per the binary table in `moose-params`; `test -x`
it, and if it is missing report BLOCKED with "Binary not built; see docs/local.md". Run
`bash <meta-root>/scripts/conda-run.sh -C <app-dir> -- <binary> -i <target> --check-input`
locally, or the bare command on INL HPC hosts. On failure read the error, fix, and re-run, three
attempts total; then report STUCK with the final error verbatim and the fixes tried.

## Report

One line: `STATUS: DONE | DONE_WITH_CONCERNS | STUCK | BLOCKED | NEEDS_CONTEXT; FILE: <path>;
BINARY: <path>; MODE: create | modify; CHECK_INPUT: PASS after N attempts | FAIL`. Concerns list
numeric placeholders and factual notes only ("default Young's modulus is a placeholder"). A file
this skill emits passes `--check-input` or the status is STUCK; on any fork-the-file decision,
BLOCKED or NEEDS_CONTEXT beats a guess.
