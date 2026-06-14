---
name: moose-pr-review
description: Review a moose PR against MOOSE code/test/doc standards. Does the user-facing pre-flight (dirty-tree guard, PR-state check) on the main thread, then hands off to the moose-pr-reviewer orchestrator agent, which fans out three reviewer sub-agents in parallel, merges findings, and posts a GitHub PENDING review (draft comments). Pulls the PR locally with `gh pr checkout`. Never submits the review — the user always submits from the GitHub UI.
user-invocable: true
---

# MOOSE PR Review (pre-flight + nested orchestrator)

Review a moose PR with three sonnet reviewers in parallel — but keep all the orchestration glue out of the main conversation. This skill is thin: it does only the parts that need the user (pre-flight checks), then spawns ONE `moose-pr-reviewer` agent that owns the heavy work.

```
main thread (this skill)        →  parse + dirty-tree guard + PR-state check
  └─ moose-pr-reviewer (agent)  →  checkout, classify files, merge, post pending review
       ├─ moose-code-reviewer   →  C++/Python  (preloads moose-code-standards)
       ├─ moose-test-reviewer   →  tests/.i/gold  (preloads moose-test-standards)
       └─ moose-doc-reviewer    →  .md + prose  (preloads moose-doc-standards)
```

The orchestrator and the three reviewers each own their own context. The diff, file lists, and per-reviewer JSON never reach this conversation — only the orchestrator's final summary block does.

## Scope

Target repo: `idaholab/moose` only. Refuse non-moose URLs with a one-line message.

## Arguments

Free-text identifying the PR. Accept any of:

- `30123`
- `idaholab/moose#30123`
- `https://github.com/idaholab/moose/pull/30123`

If no argument, ask once for a PR number/URL, then proceed.

## Workflow

### 1. Parse and pre-flight (main thread — this needs the user)

- Extract the PR number. If the input names a non-moose repo, stop with: `This skill only reviews idaholab/moose PRs.`
- From the meta-repo root, `cd moose`.
- `git status --porcelain` — if any output, **STOP** and tell the user to commit or stash. Never auto-stash, never `git checkout -f`.
- `gh pr view <PR#> --json number,title,author,baseRefName,headRefName,headRepository,state,url` — confirm `state == "OPEN"` and the head repo is a fork of `idaholab/moose`. If closed/merged, ask the user once whether to proceed anyway.
- Save the JSON to `/tmp/moose-pr-<PR#>-meta.json` (the orchestrator reads it and forwards it into each reviewer).

These are the only steps that talk to the user. Everything past this point is non-interactive and runs in the orchestrator agent.

### 2. Hand off to the orchestrator

Spawn the `moose-pr-reviewer` agent **once** via `Agent` (`subagent_type: "moose-pr-reviewer"`, foreground). Prompt:

```
Orchestrate the review of moose PR #<PR#>.

  pr_number: <PR#>
  repo_root: <absolute path to the moose/ submodule>
  meta_path: /tmp/moose-pr-<PR#>-meta.json

Follow your workflow: checkout, classify files into code/test/doc buckets,
spawn the three reviewers as nested children in parallel, merge their JSON,
post a PENDING review (no event field), and return your summary block.
```

The orchestrator does the checkout, bucketing, parallel reviewer fan-out, JSON merge, 422 retry handling, and the PENDING POST. It cannot ask the user, so it resolves partial-reviewer-failures autonomously and notes them in its summary.

### 3. Relay the summary and stop

Print the orchestrator's returned summary block verbatim, then end the turn.

**Do NOT ask whether to submit.** **Do NOT call `gh pr review --approve|--comment|--request-changes`.** **Do NOT offer follow-ups about review state.**

## Hard rules

- Pending review is the deliverable. The orchestrator never sets `event` on the POST and never calls `gh pr review` with a submit flag. Neither do you.
- Pre-flight refuses on a dirty tree. No auto-stash, no force-checkout.
- Spawn exactly ONE `moose-pr-reviewer`; it spawns the three reviewers as its own children. Do not spawn the reviewers from here — that would pull their routing back into main context, which is the thing this design removes.
- The orchestrator and reviewers own all heavy reads (standards, full file contents, full diff) and the POST. This skill only handles pre-flight and relays the summary.
- A reviewer producing zero findings is a valid result — it appears in the summary with zero counts.
- Out of scope: physics/numerics correctness audits. The reviewers already enforce this.

## Canonical references

- `.claude/agents/moose-pr-reviewer.md` — the orchestrator: checkout, classify, fan-out, merge, post. Trust its workflow.
- `.claude/agents/moose-{code,test,doc}-reviewer.md` — the three nested reviewers (restricted tools, no `Agent`, so the tree bottoms out at depth 2).
