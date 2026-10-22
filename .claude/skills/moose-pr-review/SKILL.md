---
name: moose-pr-review
description: Reviews an idaholab/moose pull request. Refuses blackbear and isopod PRs and the user's own PRs, guards a clean moose/ tree, confirms the PR is open, reads the CIVET status, handles an existing pending review, then spawns the moose-pr-reviewer agent, which pulls the PR with gh pr checkout, reads the existing discussion, runs the MOOSE code, test, doc, and lens reviewers, and posts one PENDING GitHub review that the user submits from the GitHub UI. Use for "/moose-pr-review <N or URL> [--prove]", "review moose PR 12345".
argument-hint: "<PR number | PR URL> [--prove]"
effort: medium
---

# /moose-pr-review

Goal: one PENDING GitHub review on an `idaholab/moose` pull request, every finding a draft
comment the user reads and submits from the GitHub UI. This skill does the main-thread checks
and the hand-off. The `moose-pr-reviewer` agent owns the checkout, the discussion read, the
bucket routing, the reviewer fan-out, the merge, the optional prove step, and the POST, so the
diff and the per-reviewer JSON never enter this conversation; only its summary block comes back.

`$ARGUMENTS` is the PR: a bare number, `#N`, `moose#N`, `idaholab/moose#N`, or a PR URL,
normalized to the number `<N>`. With no argument, ask for it with `AskUserQuestion`. `--prove`
turns on the prove step (see the hand-off).

## Refusals

- **Another repository.** A URL or `owner/repo#N` that names any repository other than
  `idaholab/moose` (a `blackbear` or `isopod` PR, or a fork) is refused. A bare number is checked
  too: run `gh pr view <N> --repo idaholab/moose --json url --jq .url`, and refuse when the call
  fails or the URL is not under `https://github.com/idaholab/moose/pull/`. Say "This skill only
  reviews idaholab/moose PRs." and stop. The scripts hard-code `idaholab/moose`, so a review of
  another repository would post on the wrong PR.
- **Your own PR.** Read the login with `gh api user --jq .login`. When it equals the PR's
  `author.login`, say "This is your PR. Use /moose-build and /moose-ship." and stop. GitHub
  does not allow a review on your own PR, and a self-review is not a review.

## Checks before the hand-off

- From the meta-repo root, `git -C moose status --porcelain` prints nothing. The orchestrator's
  snapshot script runs `gh pr checkout --force`, which would clobber local work, so a dirty tree
  stops the run: say which files are dirty and let the user commit or stash them. This skill does
  not stash or force-checkout.
- `gh pr view <N> --repo idaholab/moose --json state,title,body,author,baseRefName,headRefName,headRefOid
  > /tmp/moose-pr-<N>-meta.json`. `state` is `OPEN`; otherwise ask once whether to review it
  anyway. `baseRefName` is normally `next`; another base is not an error, but name it in the
  report. Pass the file as `meta_path`. The orchestrator replaces it with the snapshot script's
  own `/tmp/moose-review-pr-<N>-meta.json`, which adds `commits` and `head_sha`, and the reviewers
  read that file.
- **CI.** moose CI is CIVET, not GitHub Actions. Run
  `<meta-root>/scripts/civet_triage.py --repo idaholab/moose --pr <N>` and record its overall
  verdict (`green`, `pending`, `infra`, `yours`, `unclear`) and each failed job for the report. Do
  not use `gh pr checks`. Red CI does not stop the review: a review of a broken change is still
  useful. Do not diagnose the failures here; when the user wants the cause, point to the
  `civet-ci-failures` skill. A triage that cannot read GitHub is a line in the report, not a stop.
- **Pending review.** GitHub allows one pending review per user on a PR. Look for one of yours:

      gh api --paginate repos/idaholab/moose/pulls/<N>/reviews \
        --jq '.[] | select(.state=="PENDING" and .user.login=="<login>") | {id, html_url}'

  When one exists, ask with `AskUserQuestion`: keep it (stop here; nothing is posted), or delete
  it and post the new review. Record a "delete" answer as `replace_pending: <id>`. The post
  script deletes it only after the review is ready, and only when it is still pending.

## Hand-off and relay

Spawn exactly one `moose-pr-reviewer` (`subagent_type: "moose-pr-reviewer"`, foreground) with:

    pr_number: <N>
    repo_root: <absolute path to moose/>
    meta_path: /tmp/moose-pr-<N>-meta.json
    replace_pending: <id>          # omit when empty
    prove: true                    # only with --prove
    Run PR mode and return your summary block.

Spawning the reviewers directly would pull their routing back into this context; the
orchestrator is the only child.

The prove step writes one failing input file per `code` and `ad` comment and runs it with
`./run_tests` in a scratch clone of the PR head (the `moose-comment-verifier` agent). Each run
builds libmoose and the scope binary from scratch, so it takes tens of minutes; that is why it
is opt-in. Refuted comments are dropped before the post. The tests stay local, in
`<meta-root>/specs/verify/pr-<N>/`.

Handle the two retry results of the post:

- `stale-head`: the author pushed during the review. The orchestrator's next snapshot resets the
  local PR branch to the new head. Spawn the orchestrator once more with the same input. A second
  `stale-head` is a fact for the report: say that the PR is moving and stop.
- `pending-exists`: a pending review appeared after the check. Report its URL and post nothing
  more.

## Report

Print the summary block verbatim. Then add:

- CI: the triage's overall verdict and each failed job, or why the triage could not run. For a
  red verdict, name the `civet-ci-failures` skill as the next step.
- Discussion: each open thread that another reviewer started and the author has not answered
  (the orchestrator's `open and unanswered` list), as `path:line by <author>`, for the user to
  raise at submission. Say so when the discussion could not be read.
- The base branch, when it is not `next`.

End the turn. The pending review is the deliverable: do not submit it, offer to submit it, or run
`gh pr review` with a submit flag. The user submits from the GitHub UI.
