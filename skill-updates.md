# Skill updates needed

Observations from the `opt-dirichlet-control` build (2026-08-04).

## 1. Fix the docs smoke script for module-only builds

The `moose-docs-smoke` script (`smoke.sh`) cannot gate a branch that only builds one module:

- For scope `moose`, `smoke.sh:33` requires `moose/test/moose_test-opt`. A feature worktree
  usually builds only a module binary (for example `modules/optimization/optimization-opt`),
  so the script fails at the binary precheck before it builds any docs.
- The precheck binary is not the one the site build uses: `moose/modules/doc/config.yml:127`
  declares `executable: ${MOOSE_DIR}/modules/combined`, a multi-hour build.
- Per-module doc configs work with the module binary. Example:
  `moose/modules/optimization/doc/config.yml:19` declares
  `executable: ${MOOSE_DIR}/modules/optimization`. A module-level
  `moosedocs.py build -f <changed pages + linked target pages>` validated the branch pages in
  about 2 minutes (`CRITICAL:0 ERROR:0 WARNING:0`).
- The `moose-docs-builder` agent may invoke docs only through `smoke.sh`, so it returned
  `BLOCKED` and the check had to run on the main thread.
- The env probe `python3 -c "import yaml, MooseDocs"` fails unless `MOOSE_DIR` and
  `PYTHONPATH=$MOOSE_DIR/python` are exported first.

Changes to make:

1. Add a module scope to `smoke.sh` (for example `smoke.sh moose/modules/optimization`):
   cd to the module's `doc/` directory, use its config and its binary.
2. When the full-site binaries are missing, fall back to the per-module config and report
   the substitution.
3. Export `MOOSE_DIR` and `PYTHONPATH` inside the script before the env probe.
4. Permit `moose-docs-builder` to run a direct module-level `moosedocs.py build -f ...` when
   `smoke.sh` cannot run.
5. Document in the skill: MooseDocs resolves `!listing` and shortcut links against
   git-tracked files. Stage new test inputs before the doc build, or the build reports
   phantom "does not exist in the repository" errors.

## 2. Input files: nearly commentless

New policy for every skill and agent that authors MOOSE `.i` files
(`moose-input-writer`, `moose-test-writer`, `moose-test-standards`, and the prompts that
`/moose-build` and `moose-feature-loop` send to writers):

1. Do not put comments on the first lines of an `.i` file. No header comment blocks.
2. Keep `.i` files nearly commentless. Prefer zero comments.
3. When an explanation is necessary (a non-obvious tolerance, a mutation guard), put it in
   the `tests` spec next to the parameter it justifies, not in the `.i` file.
