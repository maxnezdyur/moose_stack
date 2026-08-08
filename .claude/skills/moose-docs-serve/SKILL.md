---
name: moose-docs-serve
description: Start a long-running MooseDocs preview server for moose, blackbear, or isopod and return the URL, pid, and log path. Auto-loads when the user wants to preview docs, view the website, serve docs, start the docs server, open the doc preview, or restart/stop a running docs server.
---

# /moose-docs-serve

Thin dispatcher — the work happens in the `moose-docs-serve` agent.

## Usage

```
/moose-docs-serve <moose|blackbear|isopod>          # start (or restart)
/moose-docs-serve <moose|blackbear|isopod> stop     # stop the running server
```

## What to do

Parse `$ARGUMENTS` (first token = repo, required — missing → ask which repo; optional second token = `stop`). Spawn the `moose-docs-serve` agent (`Agent`, `subagent_type: "moose-docs-serve"`) with the repo + optional `stop`, then relay its report verbatim — the URL must reach the user clickable (port may not be 8000).

The bundled `serve.sh` in this directory is the agent's implementation — don't run it on the main thread.
