---
name: moose-docs-smoke
description: Smoke-test the MooseDocs site for moose, blackbear, or isopod with a full build + serve + HTTP probe and report pass/fail. Auto-loads when the user wants to check that the website builds, smoke-test the docs, verify the doc site runs, confirm the docs are healthy before push, or sanity-check a doc edit didn't break the site.
---

# /moose-docs-smoke

Thin dispatcher — the work happens in the `moose-docs-smoke` agent.

## Usage

```
/moose-docs-smoke <moose|blackbear|isopod>
```

## What to do

Parse `$ARGUMENTS` (single token = repo, required; missing → ask which repo). Spawn the `moose-docs-smoke` agent (`Agent`, `subagent_type: "moose-docs-smoke"`, `run_in_background: true` — full builds take minutes) with the repo name, then relay its report verbatim: the `PASS:`/fail line, error lines, and the log path `/tmp/moose-docs-<repo>-smoke.log`.

Don't run the build/serve/probe steps on the main thread.
