---
name: moose-pr-review
description: Review a moose PR against MOOSE code/test/doc standards. Does the user-facing pre-flight (dirty-tree guard, PR-state check) on the main thread, then hands off to the moose-pr-reviewer orchestrator agent, which fans out the reviewer sub-agents (code/test/doc buckets plus triggered lenses like ad) in parallel, merges findings, and posts a GitHub PENDING review (draft comments). Pulls the PR locally with `gh pr checkout`. Never submits the review — the user always submits from the GitHub UI.
user-invocable: true
---

# MOOSE PR Review (pre-flight + nested orchestrator)

Thin main-thread skill: it does only the parts that need the user (pre-flight), then spawns ONE `moose-pr-reviewer` agent that owns checkout, file classification, the parallel reviewer fan-out, JSON merge, 422 retry handling, and the PENDING POST. The diff, file lists, and per-reviewer JSON never enter this conversation — only the orchestrator's summary block returns.

```
main thread (this skill)        →  parse + dirty-tree guard + PR-state check
  └─ moose-pr-reviewer (agent)  →  checkout, classify files, merge, post pending review
       ├─ moose-code-reviewer   →  C++/Python  (preloads moose-code-standards)
       ├─ moose-test-reviewer   →  tests/.i/gold  (preloads moose-test-standards)
       ├─ moose-doc-reviewer    →  .md + prose  (preloads moose-doc-standards)
       ├─ moose-ad-reviewer     →  AD/Jacobian lens  (only when the diff touches AD or residual/Jacobian code)
       └─ moose-dry-reviewer    →  reuse lens  (only when the PR adds new code files or registers new objects)
```

Target repo: `idaholab/moose` only — refuse anything else with `This skill only reviews idaholab/moose PRs.` Accept a bare number, `idaholab/moose#N`, or a PR URL; if no argument, ask once for one.

## Pre-flight (main thread — needs the user)

1. Extract the PR number.
2. From the meta-repo root, `cd moose`; `git status --porcelain` — any output → STOP and tell the user to commit or stash. Never auto-stash or force-checkout: the orchestrator will `gh pr checkout` and would clobber local work.
3. `gh pr view <PR#> --json number,title,author,baseRefName,headRefName,headRepository,state,url` — confirm `state == "OPEN"` and the head repo is a fork of `idaholab/moose`. If closed/merged, ask once whether to proceed anyway. If `baseRefName` is `devel`, warn the user: idaholab PRs must target `next` (CIVET's precheck rejects `devel`) — suggest `gh pr edit <PR#> --base next`.
4. Save the JSON to `/tmp/moose-pr-<PR#>-meta.json` — the orchestrator reads it and forwards it into each reviewer.

## Hand off

Spawn exactly one `moose-pr-reviewer` via `Agent` (`subagent_type: "moose-pr-reviewer"`, foreground) — never the three reviewers directly, which would pull their routing back into main context, the thing this design removes. Prompt:

```
Orchestrate the review of moose PR #<PR#>.

  pr_number: <PR#>
  repo_root: <absolute path to the moose/ submodule>
  meta_path: /tmp/moose-pr-<PR#>-meta.json

Follow your workflow: checkout, classify files into code/test/doc buckets
plus any triggered lens buckets, spawn the reviewers as nested children in
parallel, merge their JSON, post a PENDING review (no event field), and
return your summary block.
```

The orchestrator can't reach the user; it resolves partial reviewer failures autonomously and notes them in its summary. A reviewer producing zero findings is a valid result. Physics/numerics correctness audits are out of scope — the reviewers enforce this.

## Relay and stop

Print the orchestrator's summary block verbatim, then end the turn. The PENDING review is the deliverable: neither you nor the orchestrator ever submits — no `event` field on the POST, no `gh pr review --approve|--comment|--request-changes` — and don't ask whether to submit or offer follow-ups about review state. The user submits from the GitHub UI.

## References

- The `moose-pr-reviewer` agent definition — the orchestrator: checkout, classify, fan-out, merge, post. Trust its workflow. (It also has a local mode used by `/moose-build`'s clean-context review — no PR, no GitHub; this skill never triggers it.)
- The `moose-code-reviewer` / `moose-test-reviewer` / `moose-doc-reviewer` / `moose-ad-reviewer` / `moose-dry-reviewer` agent definitions — the nested reviewers (restricted tools, no `Agent`, so the tree bottoms out at depth 2).
