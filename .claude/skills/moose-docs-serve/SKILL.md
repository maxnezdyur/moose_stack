---
name: moose-docs-serve
description: Start a long-running MooseDocs preview server for moose, blackbear, or isopod and return the URL, pid, and log path. Auto-loads when the user wants to preview docs, view the website, serve docs, start the docs server, open the doc preview, or restart/stop a running docs server.
context: fork
agent: general-purpose
model: haiku
effort: low
allowed-tools:
  - Bash(bash *)
  - Bash(cat *)
  - Bash(tail *)
  - Bash(kill *)
  - Read
---

# /moose-docs-serve

Start (or stop) a long-running MooseDocs preview server for one of the three top-level doc sites in moose_stack:

| Repo | Doc dir |
|---|---|
| `moose` | `moose/modules/doc/` |
| `blackbear` | `blackbear/doc/` |
| `isopod` | `isopod/doc/` |

Full build, no `--fast` (so `!syntax` blocks render). Background process. Auto-picks the first free port from 8000.

## Usage

```
/moose-docs-serve <moose|blackbear|isopod>          # start (or restart)
/moose-docs-serve <moose|blackbear|isopod> stop     # stop the running server
```

Re-invoking while a server is already running for that repo kills the old one and starts fresh — covers "I edited config and want to bounce it".

## What to do

1. Parse `$ARGUMENTS`. The first token is the repo (required, must be `moose`, `blackbear`, or `isopod`). The optional second token is `stop`.
2. Run the bundled script with those arguments:

   ```bash
   bash <skill-dir>/serve.sh <repo> [stop]
   ```

   where `<skill-dir>` is the directory containing this `SKILL.md`.

3. The script handles everything: meta-repo lookup, env probe, binary probe, free-port allocation, kill-and-restart, and spawning moosedocs in the background.

4. Surface what the script prints. On success it returns the URL, pid, and log path; on failure it prints the reason and exits non-zero. Don't paraphrase — pass the URL through verbatim so the user can click it.

## Prereqs the script enforces (so you don't have to)

- **Conda env**: `python3 -c "import yaml, MooseDocs"` must succeed. On failure the script tells the user to activate moose-dev (or equivalent).
- **Binary**: full build needs the repo's executable for `appsyntax`. The script checks for `moose/test/moose_test-opt`, `blackbear/blackbear-opt`, or `isopod/isopod-opt` and prints the exact `make -C ... -j` command if missing. **Do not auto-build** — surface the build command and let the user decide.

## Files

- `/tmp/moose-docs-<repo>-serve.pid` — running server's pid
- `/tmp/moose-docs-<repo>-serve.log` — moosedocs stdout+stderr

## Notes

- The page will be incomplete until moosedocs finishes building (full builds take minutes for moose). The server is up immediately; reload as the build progresses.
- The server is detached from the shell session (`nohup` + `disown`) so it survives Claude Code exiting. Stop it explicitly with the `stop` subcommand.
- If port 8000 is taken, the script picks 8001, 8002, ... up to 8099. The actual URL is in the script's output — read it, don't assume 8000.
