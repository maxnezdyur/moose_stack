---
name: moose-docs-smoke
description: Smoke-test the MooseDocs site for moose, blackbear, or isopod with a full build + serve + HTTP probe and report pass/fail. Auto-loads when the user wants to check that the website builds, smoke-test the docs, verify the doc site runs, confirm the docs are healthy before push, or sanity-check a doc edit didn't break the site.
context: fork
agent: general-purpose
model: haiku
allowed-tools:
  - Bash(bash *)
  - Bash(cat *)
  - Bash(tail *)
  - Read
---

# /moose-docs-smoke

Finite health check of a MooseDocs site: `moosedocs.py build --serve` (full build, no `--fast`), wait for the server to bind, probe `/`, report pass/fail. The server is always killed before the skill returns — for a long-running preview use `/moose-docs-serve` instead.

| Repo | Doc dir |
|---|---|
| `moose` | `moose/modules/doc/` |
| `blackbear` | `blackbear/doc/` |
| `isopod` | `isopod/doc/` |

## Usage

```
/moose-docs-smoke <moose|blackbear|isopod>
```

Build timeout defaults to 600s; override with `SMOKE_TIMEOUT=N` in the env (full builds take minutes, especially moose).

## Pass criteria (all must hold)

1. `moosedocs.py` exits 0
2. `curl http://localhost:<port>/` returns HTTP 200
3. Zero `ERROR` / `CRITICAL` / `Traceback` lines in the moosedocs log

Warnings (red citations, Levenshtein hints, missing images) are printed but do not fail the smoke — this is the "did the public site break?" gate, not a doc-quality audit.

## What to do

Parse `$ARGUMENTS` (single token = repo, required), then run the bundled script, where `<skill-dir>` is the directory containing this SKILL.md:

```bash
bash <skill-dir>/smoke.sh <repo>
```

The script handles meta-repo lookup, env probe (`python3 -c "import yaml, MooseDocs"` — on failure it says to activate moose-dev), binary probe (full build needs the repo's executable for `appsyntax`: `moose/test/moose_test-opt`, `blackbear/blackbear-opt`, or `isopod/isopod-opt`; if missing it prints the exact `make -C ... -j` command), port allocation (same 8000-and-up walk as `/moose-docs-serve`, so the two can run side-by-side), spawning, polling, the HTTP probe, the log grep, and server cleanup.

Surface the script's output verbatim. On pass it prints one line: `PASS: <repo> docs (<N>s, http 200, 0 errors)`. On fail it prints the reason, error lines (up to 20), and the log path — pass the path through so the user can read it.

## Files

- `/tmp/moose-docs-<repo>-smoke.log` — moosedocs stdout+stderr (kept after the run for debugging)
