---
name: civet-ci-failures
description: Triage a red CIVET run on a moose, blackbear, or isopod pull request. First decides whether each failed job is caused by the branch or by CIVET's own environment (a conda, container, or download break that fails on everyone's PRs), then reads the failing tests and build errors for the jobs that are the branch's own. Use for "why is CI red", "CIVET failed", "fix the CI failure", "is this failure mine", a `ci-red` card on the factory board, a civet.inl.gov job URL, or before any amend that answers a CIVET failure.
---

# CIVET failures

A red job is a claim about the environment as often as about the branch. Decide which before you touch code: a fix for a failure the branch did not cause wastes a push, and a push cancels the event in flight.

Run both scripts from the meta-repo root or a worktree root. Both need an authenticated `gh` and nothing else. `--repo` is always `idaholab/<app>`: `origin` is a personal fork and CIVET posts no statuses there.

## 1. Applicability

    scripts/civet_triage.py --repo idaholab/moose --pr <N>

It compares each failed job with the same job on the 20 most recently updated open PRs and on the `next` and `devel` tips, inside a 48 hour window. Dependency cascades (`Won't run due to failed dependencies`) are already excluded.

| Job verdict | Meaning | Action |
|---|---|---|
| `widespread` | At least two other authors' heads fail the same job, and at least half of the heads that ran it since the first failure. The user's own other PRs do not count: they are often stacked and share commits. | Not the branch. Change no code. Report it and stop. |
| `isolated` | The job passes elsewhere in the same period. | The branch. Go to step 2 for this job. |
| `unclear` | Too few other heads ran it. | Go to step 2. Let the log decide. |

The overall verdict is `infra` (all widespread), `yours` (any isolated), `unclear`, `pending`, or `green`.

A verdict is evidence, not proof. Overrule it in these cases:

- The diff touches what the job builds. A PR that edits `conda/`, `apptainer/`, a `versioner` input, a submodule pointer, or `scripts/update_and_rebuild_*` can break the same Conda or container job that is also broken for everyone. Check `git diff --stat devel...HEAD` against the job name before you accept `widespread`.
- `Precheck` is `isolated` almost by definition: it checks this branch's formatting, ASCII, and spec fields.
- The same failed job on `next` or `devel` (listed under "also fails on") makes `widespread` strong. Two other PRs alone make it weak; say so.
- An `unclear` job that fails on one other author's PR is a lead, not a verdict. Read its log.
- `Failed but allowed` jobs arrive as success and are listed on the last line. They are never a reason to change code.

When the event is incomplete, the verdict covers only the jobs that have finished.

## 2. Cause, for jobs that are not widespread

    scripts/civet_ci_failures.py --repo idaholab/moose --pr <N> --errors
    scripts/civet_ci_failures.py --job <civet job url>
    scripts/civet_ci_failures.py --job <url> --step 04_Test --grep '<pattern>' --context 5

This reads the CIVET step logs and reports build errors, failing tests, clustered error signatures, and the reproduce command each step logged. `references/reading-the-report.md` holds the traps in reading that report, the remediation table by failure reason, and the poll loop for watching an event.

`civet.inl.gov` answers HTTP 403 from outside the INL network. `could not read logs: HTTP Error 403` means the machine is off the network, not that the recipe is private. Do not work around it. Report the job URLs and ask the user to open them or to connect to the network.

Even with a readable log, classify the cause before you fix it. A `curl`, `git clone`, `conda`/`mamba` solve, or container build error is environmental even on an `isolated` job; a compiler diagnostic or a failing test in files the diff touches is the branch.

## 3. What to do with the result

- `infra`, or an environmental cause in the log: change nothing and push nothing. State which jobs, how many other PRs share them, and that a re-run is needed after the environment recovers. Invalidating the event or re-pushing is the user's decision.
- The branch: reproduce with the logged command (through `scripts/conda-run.sh` on the local machine, bare inside the container on INL HPC; check `hostname`), fix, and hand the amend to `/moose-ship`. Batch the fixes into one push, because every push restarts the whole matrix.
- Mixed: fix only the branch's own failures, and name the widespread ones as left alone.
- Unreadable or unexplained: say what you found and what you could not determine. Do not apply a remedy on a hunch.

`scripts/civet_ci_failures.py` is a verbatim copy of `python/civet_ci_failures/civet_ci_failures.py` from idaholab/moose#33756 (merge commit `ec47809f1e`), kept in the meta-repo until every worktree's `moose/` carries it. `scripts/civet_triage.py` is local. The factory board runs the same triage: see `factory ci <feature>`.
