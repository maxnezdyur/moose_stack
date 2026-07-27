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

Start (or stop) a long-running MooseDocs preview server. Full build, no `--fast` (so `!syntax` blocks render), backgrounded, first free port from 8000.

| Repo | Doc dir |
|---|---|
| `moose` | `moose/modules/doc/` |
| `blackbear` | `blackbear/doc/` |
| `isopod` | `isopod/doc/` |

## Usage

```
/moose-docs-serve <moose|blackbear|isopod>          # start (or restart)
/moose-docs-serve <moose|blackbear|isopod> stop     # stop the running server
```

Re-invoking while a server runs for that repo kills the old one and starts fresh — covers "I edited config and want to bounce it".

## What to do

Parse `$ARGUMENTS` (first token = repo, required; optional second token = `stop`), then run the bundled script, where `<skill-dir>` is the directory containing this SKILL.md:

```bash
bash <skill-dir>/serve.sh <repo> [stop]
```

The script handles everything: meta-repo lookup, env probe (`python3 -c "import yaml, MooseDocs"` — on failure it says to activate moose-dev), binary probe (full build needs the repo's executable for `appsyntax`: `moose/test/moose_test-opt`, `blackbear/blackbear-opt`, or `isopod/isopod-opt`; if missing it prints the exact `make -C ... -j` command), free-port allocation, kill-and-restart, and backgrounding.

Surface the script's output verbatim — the URL must reach the user clickable, and the port may not be 8000 (script walks 8000–8099). If the binary is missing, do not auto-build; relay the build command and let the user decide.

## Files

- `/tmp/moose-docs-<repo>-serve.pid` — running server's pid
- `/tmp/moose-docs-<repo>-serve.log` — moosedocs stdout+stderr

## Notes

- The server is up immediately but pages are incomplete until the build finishes (minutes for moose); reload as it progresses.
- Detached (`nohup` + `disown`) — survives Claude Code exiting. Stop explicitly with the `stop` subcommand.
