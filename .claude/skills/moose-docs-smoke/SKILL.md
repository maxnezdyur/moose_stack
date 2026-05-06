---
name: moose-docs-smoke
description: Smoke-test the MooseDocs site for moose, blackbear, or isopod with a full build + serve + HTTP probe and report pass/fail. Auto-loads when the user wants to check that the website builds, smoke-test the docs, verify the doc site runs, confirm the docs are healthy before push, or sanity-check a doc edit didn't break the site.
context: fork
agent: general-purpose
model: haiku
effort: low
allowed-tools:
  - Bash(bash *)
  - Bash(cat *)
  - Bash(tail *)
  - Read
---

# /moose-docs-smoke

Finite health check for one of the three top-level MooseDocs sites in moose_stack. Runs `moosedocs.py build --serve` (full build, no `--fast`), waits for the server to bind, probes `/`, and reports pass/fail. Server is killed before the skill returns.

| Repo | Doc dir |
|---|---|
| `moose` | `moose/modules/doc/` |
| `blackbear` | `blackbear/doc/` |
| `isopod` | `isopod/doc/` |

## Usage

```
/moose-docs-smoke <moose|blackbear|isopod>
```

Override the build timeout (default 600s) with `SMOKE_TIMEOUT=N` in the env.

## Pass criteria (all must hold)

1. `moosedocs.py` exits 0
2. `curl http://localhost:<port>/` returns HTTP 200
3. Zero `ERROR` / `CRITICAL` / `Traceback` lines in the moosedocs log

Warnings (red citations, Levenshtein hints, missing images) are printed but do **not** fail the smoke. Treat this as the "did the public site break?" gate, not a doc-quality audit.

## What to do

1. Parse `$ARGUMENTS`. The first (and only) token is the repo (required, must be `moose`, `blackbear`, or `isopod`).
2. Run the bundled script:

   ```bash
   bash <skill-dir>/smoke.sh <repo>
   ```

   where `<skill-dir>` is the directory containing this `SKILL.md`.

3. The script handles meta-repo lookup, env probe, binary probe, port allocation, spawning moosedocs, polling the port, the HTTP probe, the error-log grep, and cleanup of the server process.

4. Surface the script's output verbatim. On pass it prints one line: `PASS: <repo> docs (<N>s, http 200, 0 errors)`. On fail it prints the failure reason, error lines (up to 20), and the log path. Don't paraphrase — pass the log path through so the user can read it.

## Prereqs the script enforces (so you don't have to)

- **Conda env**: `python3 -c "import yaml, MooseDocs"` must succeed. On failure the script tells the user to activate moose-dev (or equivalent).
- **Binary**: full build needs the repo's executable for `appsyntax`. The script checks for `moose/test/moose_test-opt`, `blackbear/blackbear-opt`, or `isopod/isopod-opt` and prints the exact `make -C ... -j` command if missing.

## Files

- `/tmp/moose-docs-<repo>-smoke.log` — moosedocs stdout+stderr (kept after the run for debugging)

## Notes

- Full builds take minutes (especially moose, which renders every module's pages). Default timeout 600s; bump `SMOKE_TIMEOUT` for slow machines.
- The skill always kills the server before exiting (success or failure). It does not leave a long-running process behind. For long-running preview, use `/moose-docs-serve` instead.
- Same port-probing logic as `/moose-docs-serve`: starts at 8000 and walks up if taken, so smoke and serve can run side-by-side without colliding.
