---
name: moose-review-protocol
description: Shared workflow and output contract for the moose PR reviewer sub-agents (code/test/doc buckets and lens reviewers like ad) — inputs, the shared review loop, comment-writing rules, inline-vs-body policy, the findings JSON schema, the files_reviewed coverage ledger, and the lenient referenced-file existence rule. Preloaded by moose-code-reviewer, moose-test-reviewer, moose-doc-reviewer, moose-ad-reviewer, moose-dry-reviewer, and moose-completeness-reviewer; not useful on its own.
user-invocable: false
---

# MOOSE reviewer output protocol

What every reviewer sub-agent receives, writes, and must prove about its coverage. Your agent file supplies the domain bar — *what* to flag in your bucket; this file supplies the shared loop and the contract — *how* you work through the files and how the findings leave your hands.

**Precedence.** On the domain bar, your agent file wins outright: what counts as a finding in your bucket is its call alone, and this file never overrides it. On the shared review loop and the output contract, this file wins for the six reviewer sub-agents (`code`, `test`, `doc`, `ad`, `dry`, `completeness`). A reviewer agent file may add a bucket-specific step, say where it slots into the loop, and tighten a rule — it may not contradict one. If it appears to, treat the agent-side copy as stale and follow this file.

## Inputs (from the orchestrator's prompt)

| key | meaning |
|---|---|
| `pr_number` | PR number. Replaced by a free-text `context:` line in local mode — proceed without it. |
| `repo_root` | Absolute path to the working tree, already on the branch. |
| `diff_path` | Tempfile with the full diff. Read once; note hunk ranges (`@@ -a,b +c,d @@`) per file. |
| `files_path` | Tempfile, one repo-relative path per line — **your bucket only**. |
| `pr_meta` | Inline JSON: `title`, `body`, `author`, `baseRefName`, `headRefName`. Absent in local mode. |
| `issues_path` | Tempfile digesting the PR's linked GitHub issues — the author's spec; use it to judge whether findings about completeness or scope hold. May be absent (local mode, no linked issues, or digest failure): proceed without it, never block on it. |
| `out_path` | Absolute path where you MUST write your findings JSON. |

Only lines inside a hunk are eligible for inline comments.

## Workflow

This loop is for the six reviewer sub-agents only. The `moose-pr-reviewer` orchestrator preloads this file for the findings JSON shape, the ledger invariants, and the return-line grammar it parses — its own `## Workflow` and `## Inputs` are untouched by this section.

Every reviewer runs this loop. Your agent file owns the bar you walk in step 3 and names its **deltas** — the extra steps its bucket needs and where they slot in. The loop itself is this file's.

1. Read `diff_path` once, noting hunk ranges (`@@ -a,b +c,d @@`) per file.
2. Seed the `files_reviewed` ledger from `files_path` — one row per file, counts zeroed. See the ledger section below.
3. Review **every** file in ledger order, reading each **in full** from `repo_root` — a hunk in isolation misses surrounding context, and any rule that depends on a block's parent or on the rest of the file is unanswerable from hunks alone. Walk the **whole** bar your agent file defines on each file: never stop at the first finding, and never stop early because the review already has "enough". Update that file's row as you go — the last file gets the same scrutiny as the first.
4. Verify both ledger invariants, then write the findings JSON to `out_path`.
5. Return the `DONE` / `ERROR` line below.

## Comment writing

- One issue per comment; one short, matter-of-fact paragraph.
- **Required vs suggested — MOOSE's reviewing convention** (`framework/doc/content/framework/reviewing.md`). Phrase a must-fix finding in the imperative ("Mark this parameter `const` because …"); phrase an optional improvement as "I suggest …" / "Consider …". Minor objective fixes — typos, grammar, doc strings — are required, not suggestions. Every comment reads as one or the other; never an unmarked observation.
- **Never identify yourself, the review tooling, or the model.** Write as a reviewer stating the issue — no "as an automated check", no agent, tool, or model names, no meta-commentary about how the finding was produced.
- When a concrete drop-in fix applies, include a GitHub `suggestion` block (≤3 lines). It replaces the target line(s) wholesale, so it must carry the FULL replacement line(s) as they should appear on the new side, exact leading whitespace included:

      ```suggestion
      replacement lines here
      ```

- Multi-line range: include `start_line` and `start_side` alongside `line` and `side`.
- Comment on a deleted line: `"side": "LEFT"`.
- **Repetition rollup — stays inline.** If the *same* rule is violated more than 3 times in one file, comment inline at the first 3 sites, then post ONE more inline comment **at the 4th site** enumerating every remaining site: `"Same issue at lines 88, 104, 210."` Four inline comments, **no `body_findings` entry** — the rollup belongs on the diff where the author can act on it, not in a footnote. If the 4th site falls outside every hunk, fold the enumeration into your 3rd comment. Different rules at different lines are always separate comments, however many.

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

Write this shape to `out_path`. Set `agent` to your bucket (`code`, `test`, `doc`, or your lens slug, e.g. `ad`):

    {
      "agent": "<code|test|doc|ad|dry|completeness>",
      "inline_comments": [
        { "path": "<path A>", "line": 142, "side": "RIGHT", "body": "Typo: \"recieve\" -> \"receive\"." },
        { "path": "<path A>", "start_line": 40, "start_side": "RIGHT", "line": 45, "side": "RIGHT",
          "body": "<multi-line range finding>" },
        { "path": "<path B>", "line": 88, "side": "RIGHT", "body": "<finding>" }
      ],
      "body_findings": [
        { "path": "<path A>", "line": 200,
          "summary": "<finding, with the real path:line, for one of the four cases above>" }
      ],
      "files_reviewed": [
        { "path": "<path A>", "inline": 2, "body": 1 },
        { "path": "<path B>", "inline": 1, "body": 0 },
        { "path": "<path C>", "inline": 0, "body": 0 }
      ]
    }

*The arrays are as long as the findings require — on a large PR, routinely dozens.*

Empty `inline_comments`/`body_findings` arrays are valid — write the file even with zero findings.

## `files_reviewed` is a coverage ledger, not a summary

It MUST hold **exactly one row per line in `files_path`** — every file you were given, including the clean ones. A `0`/`0` row is a normal result meaning "I read this and it was clean." A file missing from the ledger means you did not review it.

Seed the ledger from `files_path` **before** reviewing — one row per file, counts zeroed — then increment as you go, never adding or removing rows. This is what stops a review from trailing off after the first few interesting files: an unreviewed file shows up as a missing row instead of vanishing silently.

Two invariants, both re-checked by the orchestrator:

- `files_reviewed` is set-equal to `files_path` — same paths, no extras, no duplicates.
- Summed `inline`/`body` == actual `inline_comments`/`body_findings` lengths.

Two cases that would otherwise break them:

- **A file the PR deletes** is in `files_path` but unreadable. Give it a `0`/`0` row anyway — reviewed-and-nothing-to-say, not a gap.
- **A finding about a file NOT in `files_path`** (a missing gold, a referenced page that doesn't exist) counts against the in-bucket file that raised it. Never add a row for a path you weren't assigned.

**There is no cap on findings.** Do not stop at a representative sample and do not ration comments across files — report what the bar produces, however many that is. The only compression allowed is the inline repetition rollup above.

## Referenced-file existence (lenient basename-exists)

Shared by the buckets that check file references — test (`design`, gold, `[Mesh] file`, MultiApp `input_files`) and doc (`!listing`, `!media`, `!include`, `.md` links). Your agent file names the reference forms your bucket extracts; this is how each one resolves.

Only check references **introduced or modified on an added/changed line in this PR's diff** — the reference must land on a RIGHT-side diff line. Never check pre-existing references on unchanged lines.

**Resolution = lenient basename-exists.** Take the reference's **basename** and check whether it appears anywhere in the one-time `git ls-files` index you built in step 1 (equivalently `Glob '**/<basename>'`). Flag **only** when the basename exists nowhere. If it exists anywhere in the repo, assume the path is fine — this keeps false positives near zero and still catches the real case: a referenced file that simply does not exist.

Do not resolve the literal path against `repo_root`, but for different reasons per bucket. MooseDocs paths are **virtual** — content-relative, not raw filesystem paths — so the literal path would not resolve at all. HIT paths (`[Mesh] file = '...'`, MeshGenerator `file = '...'`) are real filesystem paths, but they resolve **relative to the input file**, not to `repo_root`, so a literal check there is merely wrong about the base directory. Either way, the basename is what you match on.

ALWAYS skip (never flag, never check):

- External URLs: `http://`, `https://`, `mailto:`.
- Bare section anchors with no file part: `[#foo]`, `[text](#foo)`.
- Anything marked `optional=True` — allowed to be absent by design.
- Paths containing `${...}`, `!template` substitution, or HIT/CLI brace-expansion — can't statically resolve, so skip rather than guess.

This rule is lenient by design and governs only the checks that cite it. A check your agent file states in stricter terms — e.g. the test bucket's working-tree gold check — stands on its own and is not softened to a basename match.

## Return line

`DONE — wrote <out_path> (<N> inline, <M> body, <F>/<T> files)` where `F` is ledger rows and `T` is lines in `files_path` — or `ERROR — <reason>`.

## Hard rules

- Never call `gh pr review`, `gh api .../reviews`, or anything that posts to GitHub.
- Never run builds, tests, doc builds, formatters, or linters.
- Never edit any file in `repo_root`. The only file you write is `out_path`.
- Bash is limited to read-only inspection (`grep`, `git log -n`, `git blame`, `git ls-files`) on `repo_root`.
