---
name: moose-review-protocol
description: Shared output contract for the moose PR reviewer sub-agents (code/test/doc) — inputs, comment-writing rules, inline-vs-body policy, the findings JSON schema, and the files_reviewed coverage ledger. Preloaded by moose-code-reviewer, moose-test-reviewer, and moose-doc-reviewer; not useful on its own.
user-invocable: false
---

# MOOSE reviewer output protocol

What every reviewer sub-agent receives, writes, and must prove about its coverage. Your agent file supplies the domain bar — *what* to flag; this file supplies the contract — *how* it leaves your hands. If the two ever disagree, your agent file wins.

## Inputs (from the orchestrator's prompt)

| key | meaning |
|---|---|
| `pr_number` | PR number. Replaced by a free-text `context:` line in local mode — proceed without it. |
| `repo_root` | Absolute path to the working tree, already on the branch. |
| `diff_path` | Tempfile with the full diff. Read once; note hunk ranges (`@@ -a,b +c,d @@`) per file. |
| `files_path` | Tempfile, one repo-relative path per line — **your bucket only**. |
| `pr_meta` | Inline JSON: `title`, `body`, `author`, `baseRefName`, `headRefName`. Absent in local mode. |
| `out_path` | Absolute path where you MUST write your findings JSON. |

Only lines inside a hunk are eligible for inline comments.

## Comment writing

- One issue per comment; one short, matter-of-fact paragraph.
- **Never identify yourself, the review tooling, or the model.** Write as a reviewer stating the issue — no "as an automated check", no agent, tool, or model names, no meta-commentary about how the finding was produced.
- When a concrete drop-in fix applies, include a GitHub `suggestion` block (≤3 lines). It replaces the target line(s) wholesale, so it must carry the FULL replacement line(s) as they should appear on the new side, exact leading whitespace included:

      ```suggestion
      replacement lines here
      ```

- Multi-line range: include `start_line` and `start_side` alongside `line` and `side`.
- Comment on a deleted line: `"side": "LEFT"`.
- **Repetition rollup — stays inline.** If the *same* rule is violated more than 3 times in one file, comment inline at the first 3 sites, then post ONE more inline comment **at the 4th site** enumerating every remaining site: `"Same issue at lines 88, 104, 210."` Four inline comments, **no `body_findings` entry** — the rollup belongs on the diff where the author can act on it, not in a footnote. If the 4th site falls outside every hunk, fold the enumeration into your 3rd comment. This is the only compression allowed; it keeps a repetitive PR readable and is not a budget. Different rules at different lines are always separate comments, however many.

## Inline is the default — `body_findings` is the exception

Inline comments are the useful output: they land on the line the author must edit and can carry a `suggestion`. Body findings are a footnote the author has to hunt down. **Prefer inline wherever a line can carry the finding.**

The one hard constraint: inline `line` MUST land inside a diff hunk on the side you specify, or GitHub rejects the comment (422). That is a reason to *find the right hunk line*, not to retreat to `body_findings`. Before demoting anything, look for the natural anchor — your agent file names the ones typical of your bucket. Almost every finding about changed content has one.

Use `body_findings` ONLY when:

- The file has no hunk at all in this diff.
- The finding is about something **absent** — a file, block, or declaration that should exist and doesn't — with no changed line representing the omission.
- The finding is genuinely cross-file and no single line is the right place to raise it.
- The right line falls outside every hunk: the change made a pre-existing line wrong without touching it. Cite the real `path:line`. This is the escape hatch when a finding is genuine but cannot be posted inline.

Do not demote because you are unsure the line is in a hunk — you read the hunk ranges, so check. Do not force a comment onto an unrelated line either; if there is truly no anchor, the bullets above are why.

## Output JSON schema

Write this shape to `out_path`. Set `agent` to your bucket (`code`, `test`, or `doc`). The `//` notes are annotation — real output is plain JSON with no comments:

    {
      "agent": "<code|test|doc>",

      // ABRIDGED. Two entries establish the element shape; the real array is
      // however long the findings are — see the ledger counts below.
      "inline_comments": [
        { "path": "<path>", "line": 142, "side": "RIGHT", "body": "Typo: \"recieve\" -> \"receive\"." },
        { "path": "<path>", "start_line": 40, "start_side": "RIGHT", "line": 45, "side": "RIGHT",
          "body": "<multi-line range finding>" }
        // ... 5 further entries elided
      ],
      "body_findings": [
        { "path": "<path>", "line": 200,
          "summary": "<finding, with the real path:line, for one of the four cases above>" }
      ],
      "files_reviewed": [
        { "path": "<path A>", "inline": 4, "body": 1 },
        { "path": "<path B>", "inline": 3, "body": 0 },
        { "path": "<path C>", "inline": 0, "body": 0 }
      ]
    }

**The example's array lengths carry no information.** They are abridged; the ledger counts (7 inline, 1 body over 3 files) describe the full arrays. Do not reconcile the two here, and never treat the number of entries shown as a target, budget, or typical result. A real review emits as many entries as the bar produces — on a large PR, routinely dozens.

Empty `inline_comments`/`body_findings` arrays are valid — write the file even with zero findings.

## `files_reviewed` is a coverage ledger, not a summary

It MUST hold **exactly one row per line in `files_path`** — every file you were given, including the clean ones. A `0`/`0` row is a normal result meaning "I read this and it was clean." A file missing from the ledger means you did not review it.

Seed the ledger from `files_path` **before** reviewing — one row per file, counts zeroed — then increment as you go, never adding or removing rows. This is what stops a review from trailing off after the first few interesting files: an unreviewed file shows up as a missing row instead of vanishing silently.

Two invariants, both re-checked by the orchestrator:

- `files_reviewed` is set-equal to `files_path` — same paths, no extras, no duplicates.
- Summed `inline`/`body` == actual `inline_comments`/`body_findings` lengths. (The schema example above is abridged and deliberately violates this; your real output must not.)

Two cases that would otherwise break them:

- **A file the PR deletes** is in `files_path` but unreadable. Give it a `0`/`0` row anyway — reviewed-and-nothing-to-say, not a gap.
- **A finding about a file NOT in `files_path`** (a missing gold, a referenced page that doesn't exist) counts against the in-bucket file that raised it. Never add a row for a path you weren't assigned.

**There is no cap on findings.** Do not stop at a representative sample and do not ration comments across files — report what the bar produces, however many that is. The only compression allowed is the inline repetition rollup above.

## Return line

`DONE — wrote <out_path> (<N> inline, <M> body, <F>/<T> files)` where `F` is ledger rows and `T` is lines in `files_path` — or `ERROR — <reason>`.

## Hard rules

- Never call `gh pr review`, `gh api .../reviews`, or anything that posts to GitHub.
- Never run builds, tests, doc builds, formatters, or linters.
- Never edit any file in `repo_root`. The only file you write is `out_path`.
- Bash is limited to read-only inspection (`grep`, `git log -n`, `git blame`, `git ls-files`) on `repo_root`.
