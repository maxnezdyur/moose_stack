---
name: moose-pr-review
description: Reviews an idaholab/moose pull request. Guards a clean moose/ tree, confirms the PR is open, then spawns the moose-pr-reviewer agent, which pulls the PR with gh pr checkout, runs the MOOSE code, test, doc, and lens reviewers, and posts one PENDING GitHub review that the user submits from the GitHub UI. Refuses blackbear and isopod PRs. Use for "/moose-pr-review <N or URL>", "review moose PR 12345".
disable-model-invocation: true
argument-hint: "<PR number | PR URL>"
effort: medium
---

# /moose-pr-review

Goal: one PENDING GitHub review on an `idaholab/moose` pull request, every finding a draft
comment the user reads and submits from the GitHub UI. This skill does the main-thread checks
and the hand-off. The `moose-pr-reviewer` agent owns the checkout, the bucket routing, the
reviewer fan-out, the merge, and the POST, so the diff and the per-reviewer JSON never enter
this conversation; only its summary block comes back.

`$ARGUMENTS` is the PR: a bare number, `idaholab/moose#N`, or a PR URL, normalized to the
number `<N>`. With no argument, ask for it with `AskUserQuestion`. Any other repo is refused
with "This skill only reviews idaholab/moose PRs."

## Checks before the hand-off

- From the meta-repo root, `git -C moose status --porcelain` prints nothing. The orchestrator's
  snapshot script runs `gh pr checkout`, which would clobber local work, so a dirty tree stops
  the run: say which files are dirty and let the user commit or stash them. This skill does not
  stash or force-checkout.
- `gh pr view <N> --repo idaholab/moose --json state,title,body,author,baseRefName,headRefName
  > /tmp/moose-pr-<N>-meta.json`. `state` is `OPEN`; otherwise ask once whether to review it
  anyway. Pass the file as `meta_path`; the orchestrator's snapshot script rewrites the meta
  JSON that the reviewers actually read (it adds `commits`).

## Hand-off and relay

Spawn exactly one `moose-pr-reviewer` (`subagent_type: "moose-pr-reviewer"`, foreground) with
`pr_number: <N>`, `repo_root: <absolute path to moose/>`, `meta_path: /tmp/moose-pr-<N>-meta.json`,
and "Run PR mode and return your summary block." Spawning the reviewers
directly would pull their routing back into this context; the orchestrator is the only child.

Print the summary block verbatim and end the turn. The pending review is the deliverable: do not
submit it, offer to submit it, or run `gh pr review` with a submit flag. The user submits from
the GitHub UI.
