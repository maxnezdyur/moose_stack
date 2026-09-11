---
name: moose-docs
description: Serves, stops, or smoke-tests the MooseDocs site for moose, blackbear, isopod, or one moose module through scripts/docs.sh and relays the URL, pid, log path, and PASS/FAIL line. Use for "preview the docs", "serve docs", "start/stop/restart the docs server", "open the doc preview", "smoke-test the docs", "does the website build", "did my doc edit break the site", "check the docs before push".
argument-hint: "<moose|blackbear|isopod|moose/modules/<m>> serve|stop|smoke [--diff devel]"
allowed-tools: Bash(bash *)
effort: low
---

# moose-docs

One script does the work. Run it from the meta-repo root or the feature worktree root you are in:

    bash .claude/skills/moose-docs/scripts/docs.sh <scope> <serve|stop|smoke> [--diff <base>]

`$ARGUMENTS` maps onto that line in order. When the scope or the action is missing, ask once
with AskUserQuestion (both questions in one call). The script exports `MOOSE_DIR` and
`PYTHONPATH`, probes the docs env, reads the executable from the scope's `config.yml`, and
branches on hostname for conda. This skill does not edit pages, fix errors, build binaries,
activate environments, or stage files. Page-authoring rules are the `moose-doc-standards` skill.

## Scope

| Scope | Doc dir | Executable |
|---|---|---|
| `moose` | `moose/modules/doc` | `moose/modules/combined/combined-opt` |
| `blackbear` | `blackbear/doc` | `blackbear/blackbear-opt` |
| `isopod` | `isopod/doc` | `isopod/isopod-opt` |
| `moose/modules/<m>` | `moose/modules/<m>/doc` | `moose/modules/<m>/<m>-opt` |

A module scope builds only that module's pages and takes minutes; the full moose site takes
much longer. When the site-level binary is missing but the module binary exists, the script
falls back to the module scope and says so in its output.

## Actions

`serve` runs a full build (no `--fast`, so `!syntax` blocks render), detached with `nohup` on
the first free port from 8000, and returns within seconds. Re-running `serve` for a scope that
already has a server restarts it. The server outlives this session; `stop` ends it. Pages are
incomplete until the build finishes; the log shows progress.

`smoke` builds and serves on a free port, waits for the port to bind (`SMOKE_TIMEOUT`, default
600 s), probes `/` with curl, greps the log for `ERROR|CRITICAL|Traceback`, and kills the server
before returning. Warnings (red citations, Levenshtein hints, missing images) do not fail the
smoke; it asks whether the site builds, not whether the page is good. `--diff <base>` keeps
only error lines that name a file in the branch diff or an untracked file; use it when the
question is "did my edit break the site". With `--diff` and an empty branch diff every error
is filtered out and the smoke reports PASS; check the diff first. A smoke takes minutes: run it
with `run_in_background: true` and wait on it with Monitor.

Exit codes: 0 pass, 1 fail, 2 blocked or usage error.

## Reply

Only you see the command output; put what the user needs in your reply. For `serve`: the URL
(the port is often not 8000), the pid, the log path, and the stop command. For `smoke`: the
`PASS|FAIL|BLOCKED: <scope> ...` line, every error line the script printed, and the log path.

`BLOCKED` means the docs env or the executable is missing. Relay the script's hint verbatim
and stop; the user decides whether to build or activate. A `FAIL` that names a timeout means
the build did not bind within `SMOKE_TIMEOUT`; rerun with a larger value. An error that says a
file "does not exist in the repository" while the file exists on disk means the file is
untracked: MooseDocs resolves `!listing` and links against git-tracked files. Report it as
that; do not stage the file.
