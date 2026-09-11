---
name: moose-review-protocol
description: Shared loop and output contract for the moose reviewer sub-agents (code, test, doc, ad, dry, completeness) and the moose-pr-reviewer orchestrator. Defines the inputs, the comment rules, the findings JSON with the kind field and the files_reviewed ledger, the referenced-file rule, and the return line. Preloaded by those agents; not useful on its own.
user-invocable: false
---

# MOOSE reviewer protocol

Your agent file supplies the bar: what counts as a finding in your bucket. This file supplies the shared loop and the output contract for the six reviewer agents (`code`, `test`, `doc`, `ad`, `dry`, `completeness`). The `moose-pr-reviewer` orchestrator preloads it for the JSON shape, the ledger invariants, and the return line it parses.

Every finding cites a `path:line` you read this session; label anything you could not verify.

Read-only review: no builds, tests, formatters, edits, or GitHub calls. The only file you write is `out_path`.

## Inputs (from the orchestrator's prompt)

| key | meaning |
|---|---|
| `repo_root` | Absolute path to the working tree, already on the branch. |
| `diff_path` | The full diff. Hunk headers (`@@ -a,b +c,d @@`) define the lines eligible for inline comments. |
| `files_path` | One repo-relative path per line: your bucket only. |
| `meta_path` | PR mode: JSON with `title`, `body`, `author`, `baseRefName`, `headRefName`, `commits`. Absent in local mode. |
| `issues_path` | PR mode: digest of the linked issues, the author's spec for scope and completeness judgments. May be absent; proceed without it. |
| `context` | Local mode: one line naming the branch and base. No PR exists. |
| `constraints` | Optional free text from the caller (for example a blueprint's out-of-scope list). |
| `out_path` | Absolute path for your findings JSON. |

## Loop and definition of done

Read `diff_path` once and build a file index in `repo_root` first from `git ls-files` plus `git ls-files --others --exclude-standard`, so untracked files the change adds are included (local mode never commits). Seed the `files_reviewed` ledger from `files_path`, one row per file with zeroed counts, then read every file in ledger order in full from `repo_root` and walk the whole bar on each; a hunk alone cannot show a block's parent or the rest of the file. Done means: every file in `files_path` read in full, the whole bar applied to each, every finding recorded with no cap and no rationing across files, both ledger invariants holding, the JSON written to `out_path`, and partial coverage visible as `F < T` in the return line.

## Comment rules

- One issue per comment, one short matter-of-fact paragraph, written as a reviewer stating the issue. No mention of tooling, agents, models, or how the finding was produced.
- MOOSE's convention (`framework/doc/content/framework/reviewing.md`): a must-fix reads in the imperative ("Mark this parameter `const` because ...") and carries `"kind": "required"`; an optional improvement reads "I suggest ..." or "Consider ..." and carries `"kind": "suggested"`. Minor objective fixes (typos, grammar, doc strings) are required. Every finding is one or the other.
- A concrete drop-in fix goes in a GitHub `suggestion` fence of at most 3 lines. It replaces the target lines wholesale, so it holds the full replacement lines with their exact leading whitespace.
- A multi-line range adds `start_line` and `start_side` beside `line` and `side`. A deleted line uses `"side": "LEFT"`.
- Rollup: when the same rule is violated more than 3 times in one file, comment inline at the first 3 sites and post one more inline comment at the 4th site listing every remaining site ("Same issue at lines 88, 104, 210."). The rollup gets no `body_findings` entry. If the 4th site is outside every hunk, fold the list into the 3rd comment. Different rules at different lines stay separate comments.

## Inline first, `body_findings` as the exception

Inline comments land on the line the author edits and can carry a suggestion; body findings are a footnote. An inline `line` must sit inside a diff hunk on the side you name, or GitHub rejects the comment (422): find the right hunk line (your agent file names the anchors typical of your bucket) rather than demoting. Use `body_findings` only when:

- the file has no hunk in this diff;
- the finding is about something absent (a file, block, or declaration) with no changed line representing the omission;
- the finding is cross-file and no single line is the right place;
- the right line is outside every hunk because the change made an untouched line wrong. Cite the real `path:line`.

## Findings JSON

This block is the single source of the shape. `scripts/review-merge.sh` (beside this file) reads it, strips `kind` from the GitHub payload, and renders `kind` as a label in local-mode markdown. Set `agent` to your bucket.

    {
      "agent": "<code|test|doc|ad|dry|completeness>",
      "inline_comments": [
        { "path": "<path A>", "line": 142, "side": "RIGHT", "kind": "required",
          "body": "Typo: \"recieve\" -> \"receive\"." },
        { "path": "<path A>", "start_line": 40, "start_side": "RIGHT", "line": 45, "side": "RIGHT",
          "kind": "suggested", "body": "<multi-line range finding>" },
        { "path": "<path B>", "line": 88, "side": "RIGHT", "kind": "required", "body": "<finding>" }
      ],
      "body_findings": [
        { "path": "<path A>", "line": 200, "kind": "required",
          "summary": "<finding with the real path:line, for one of the four body cases>" }
      ],
      "files_reviewed": [
        { "path": "<path A>", "inline": 2, "body": 1 },
        { "path": "<path B>", "inline": 1, "body": 0 },
        { "path": "<path C>", "inline": 0, "body": 0 }
      ]
    }

Field rules: `kind` is `required` or `suggested` on every inline comment and body finding and matches the phrasing. `side` and `start_side` are `RIGHT` or `LEFT`; `start_line` and `start_side` appear only on ranges. The arrays are as long as the findings require. Empty `inline_comments` and `body_findings` arrays are valid; write the file even with zero findings.

## The `files_reviewed` ledger

Exactly one row per line in `files_path`, including clean files: a `0`/`0` row means read and clean, a missing row means not reviewed. Never add or remove rows after seeding. Two invariants, checked by `review-merge.sh` (the orchestrator re-spawns a reviewer once when either fails):

- The ledger is set-equal to `files_path`: same paths, no extras, no duplicates.
- Summed `inline` and `body` equal the `inline_comments` and `body_findings` lengths.

Two edge cases: a file the change deletes is in `files_path` but unreadable; give it a `0`/`0` row. A finding about a file not in `files_path` (a missing gold, a referenced page that does not exist) counts against the in-bucket file that raised it; never add a row for a path you were not assigned.

## Referenced-file existence (lenient basename-exists)

Shared by the test bucket (`design`, gold, `[Mesh] file`, MultiApp `input_files`) and the doc bucket (`!listing`, `!media`, `!include`, `.md` links); your agent file names the forms it extracts. Check only references introduced or modified on a RIGHT-side diff line. Take the reference's basename and look it up in the file index; flag only when it exists nowhere in the repo. Do not resolve the literal path against `repo_root`: MooseDocs paths are virtual (content-relative) and HIT `file =` paths resolve relative to the input file. Skip external URLs (`http://`, `https://`, `mailto:`), bare anchors (`[#foo]`), anything marked `optional=True`, and paths containing `${...}`, `!template`, or brace expansion. This leniency governs only the checks that cite it; a stricter check in your agent file (the test bucket's working-tree gold check) stands as written.

## Return line

`DONE -- wrote <out_path> (<N> inline, <M> body, <F>/<T> files)` where `F` is ledger rows and `T` is lines in `files_path`, or `ERROR -- <reason>`.
