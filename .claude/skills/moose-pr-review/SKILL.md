---
name: moose-pr-review
description: Review a moose PR against MOOSE code/test/doc standards by orchestrating three sonnet sub-agents (one per axis) in parallel, then post the aggregated findings as a GitHub PENDING review (draft comments). Pulls the PR locally with `gh pr checkout`. Never submits the review — the user always submits from the GitHub UI.
user-invocable: true
---

# MOOSE PR Review (pending-only, multi-agent)

Review a moose PR with three sonnet sub-agents in parallel:

- [[moose-code-reviewer]] → C++/Python changes (preloads [[moose-code-standards]])
- [[moose-test-reviewer]] → test specs, `.i` inputs, golds (preloads [[moose-test-standards]])
- [[moose-doc-reviewer]] → `.md` pages and prose clarity (preloads [[moose-doc-standards]])

Each sub-agent owns its own context — loads its own standards, reads its own files. The orchestrator (this skill) only routes file lists and merges JSON, keeping main context lean. After merging, the orchestrator posts a **pending** review via `gh api`. **Never submits, never asks to.**

## Scope

Target repo: `idaholab/moose` only. Refuse non-moose URLs with a one-line message.

## Arguments

Free-text identifying the PR. Accept any of:

- `30123`
- `idaholab/moose#30123`
- `https://github.com/idaholab/moose/pull/30123`

If no argument, ask once for a PR number/URL, then proceed.

## Workflow

### 1. Parse and pre-flight

- Extract PR number. If the input names a non-moose repo, stop with: `This skill only reviews idaholab/moose PRs.`
- From the meta-repo root, `cd moose`.
- `git status --porcelain` — if any output, STOP and tell the user to commit or stash. **Never auto-stash, never `git checkout -f`.**
- `gh pr view <PR#> --json number,title,author,baseRefName,headRefName,headRepository,state,url` — confirm `state == "OPEN"` and the head repo is a fork of `idaholab/moose`. If closed/merged, ask the user once whether to proceed anyway.
- Save the JSON output to `/tmp/moose-pr-<PR#>-meta.json` for later (you'll pass its contents into each sub-agent prompt).

### 2. Pull and snapshot

- `gh pr checkout <PR#>` — required (the user explicitly wants the branch local).
- `gh pr diff <PR#> > /tmp/moose-pr-<PR#>.diff`
- `gh pr diff <PR#> --name-only > /tmp/moose-pr-<PR#>.files`

### 3. Classify files into buckets

Write three filtered file lists. Use `grep` against `/tmp/moose-pr-<PR#>.files`. A file may appear in zero or one bucket:

- `/tmp/moose-pr-<PR#>-code.files` — `.C`, `.h`, `.py` (anywhere; production and `test/src/` both count).
- `/tmp/moose-pr-<PR#>-test.files` — paths matching `test/tests/**/tests`, `test/tests/**/*.i`, or `test/tests/**/gold/**`.
- `/tmp/moose-pr-<PR#>-doc.files` — `**/*.md` (every markdown file, not just under `doc/content/` — the doc reviewer scopes structural checks itself).

Files matching none of the above are skipped (e.g. `.yml`, `.bib`, binary mesh files). That's fine — note in the summary how many were unrouted.

### 4. Launch the three sub-agents IN PARALLEL

**This is the critical context-isolation step.** Issue all three `Agent` tool calls in a SINGLE message so they run concurrently. Skip an agent whose bucket file is empty (zero lines).

Each prompt should be self-contained — the sub-agents do not see this conversation. Use this template:

```
You are reviewing PR #<PR#> in idaholab/moose against your preloaded standards.

Inputs:
  pr_number: <PR#>
  repo_root: <absolute path to moose/>
  diff_path: /tmp/moose-pr-<PR#>.diff
  files_path: /tmp/moose-pr-<PR#>-<bucket>.files
  pr_meta: <contents of /tmp/moose-pr-<PR#>-meta.json>
  out_path: /tmp/moose-pr-<PR#>-<bucket>.json

Follow your agent's workflow. Write findings JSON to out_path. Return one line.
```

Map bucket → `subagent_type`:

| bucket | subagent_type |
|---|---|
| `code` | `moose-code-reviewer` |
| `test` | `moose-test-reviewer` |
| `doc`  | `moose-doc-reviewer`  |

### 5. Collect findings

Read each `/tmp/moose-pr-<PR#>-<bucket>.json` that was written. If a sub-agent returned `ERROR — ...`, surface the error and ask the user once whether to proceed with partial findings or abort.

### 6. Merge into a single review payload

- `comments`: concatenate `inline_comments` from all three JSONs.
- `body`: build markdown with this structure:

```
Reviewed by `moose-pr-review` (code + test + doc sub-agents).

## Out-of-line findings

### Code
- <path>:<line> — <summary>
- ...

### Tests
- <path>:<line> — <summary>
- ...

### Docs
- <path>:<line> — <summary>
- ...
```

If a section has zero `body_findings`, write `- (none)` under it. If an entire sub-agent was skipped (empty bucket), write `- (no <bucket> files in this PR)`.

Write the full payload to `/tmp/moose-pr-<PR#>-payload.json`:

```json
{
  "body": "<the markdown body above>",
  "comments": [ /* merged inline_comments */ ]
}
```

### 7. Post the PENDING review

```bash
gh api -X POST repos/idaholab/moose/pulls/<PR#>/reviews \
  --input /tmp/moose-pr-<PR#>-payload.json
```

**No `event` field.** Omitting it leaves the review in PENDING state on GitHub. The user submits from the UI.

If `gh api` returns 422 for a specific comment (`line must be part of the diff` or similar):
- Drop that comment from `comments`.
- Append a bullet to the appropriate Out-of-line section with the comment's text and `path:line` reference.
- Retry the POST. Do not silently move the comment to a different line.

### 8. Print summary and stop

Print this block, then end the turn:

```
# PR #<PR#> — Pending Review Posted

**Files changed:** <count>     (unrouted: <count>)
**Inline comments:** <count>
**Out-of-line findings:** <count>

Submit when ready: https://github.com/idaholab/moose/pull/<PR#>/files

## Sub-agent results
- code: <K> inline, <M> body
- test: <K> inline, <M> body   (or "skipped — no files")
- doc:  <K> inline, <M> body
```

**Do NOT ask whether to submit.** **Do NOT call `gh pr review --approve|--comment|--request-changes`.** **Do NOT offer follow-ups about review state.**

## Hard rules

- Pending review is the deliverable. Never set `event` on the POST. Never call `gh pr review` with a submit-flag.
- Pre-flight refuses on dirty tree. No auto-stash, no force-checkout.
- Sub-agents own all heavy reads (standards docs, full file contents, full diff). The orchestrator only reads small JSON results and the file-name list.
- Sub-agents launch in ONE message (parallel). Sequential launches defeat the context-isolation point.
- A sub-agent producing zero findings is a valid result — include it in the summary with zero counts.
- Out of scope: physics/numerics correctness audits. Sub-agents already enforce this.
