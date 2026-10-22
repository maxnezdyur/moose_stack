#!/usr/bin/env python3
"""Check every ```suggestion fence in a merged moose review before it can be posted.

Usage: suggestion-check.py --all <all.json> --root <repo>

<repo> is the checkout the review read (the snapshot meta file's `root`: moose/ in PR mode, the
scope submodule in local mode); every finding path is relative to it.

<all.json> is the bucket array that review-merge.sh builds. Each inline comment whose body
carries a suggestion fence is applied to a copy of <repo>/<path> over its range, and the fence
is kept only when:

  1. the comment is on the RIGHT side and holds exactly one fence;
  2. start_line..line lies inside the file;
  3. the replacement changes the file;
  4. the replacement does not repeat the line just above or below the range (the usual sign of
     an off-by-one range, which GitHub would apply without complaint and leave a duplicate);
  5. the patched file still parses, as far as a cheap check can tell without a build: .py with
     ast; .json with json; C++ (.C .h .K) by the balance of (), [] and {} outside comments,
     strings and character literals; HIT (.i and files named `tests`) by the balance of block
     openers `[name]` against closers `[]` / `[../]`. A file whose original fails the check, or
     a type with no check, skips this step.

A fence that fails any step is removed and its prose stays, so the posted comment never offers
an "Apply" button that breaks the file. A body finding cannot carry an applicable suggestion,
so its fence is removed as well. The file is rewritten in place and one JSON line goes to
stdout: {"checked": N, "kept": K, "dropped": [{"path", "line", "reason"}]}.

This script reads the checkout and never writes it.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

FENCE = re.compile(r"```suggestion[^\n]*\n(.*?)^```[ \t]*$", re.S | re.M)
CPP = {".c", ".h", ".k", ".cpp", ".hpp", ".cc"}
PAIRS = {")": "(", "]": "[", "}": "{"}
# C++ comments, string literals and character literals, so a brace inside one does not count.
# Raw strings (R"(...)") are rare in MOOSE and are not handled; a file that holds one may fail
# the original check, which skips the parse step for it.
CPP_SKIP = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', re.S)
HIT_OPEN = re.compile(r"^\s*\[(?!\s*(?:\.\./)?\s*\])[^\]]+\]")
HIT_CLOSE = re.compile(r"^\s*\[\s*(?:\.\./)?\s*\]")


def strip_fence(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", FENCE.sub("", text)).rstrip()


def cpp_problem(text: str) -> str:
    stack = []
    body = CPP_SKIP.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    line = 1
    for ch in body:
        if ch == "\n":
            line += 1
        elif ch in "([{":
            stack.append((ch, line))
        elif ch in PAIRS:
            if not stack or stack[-1][0] != PAIRS[ch]:
                return "unbalanced %r at line %d" % (ch, line)
            stack.pop()
    if stack:
        return "unclosed %r from line %d" % stack[-1]
    return ""


def hit_problem(text: str) -> str:
    depth = 0
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.split("#", 1)[0]
        if HIT_CLOSE.match(line):
            depth -= 1
            if depth < 0:
                return "block closer at line %d has no opener" % n
        elif HIT_OPEN.match(line):
            depth += 1
    if depth:
        return "%d unclosed block(s)" % depth
    return ""


def problem(path: str, text: str) -> str | None:
    """The parse error of `text` as the file `path`, "" when it passes, None when unchecked."""
    p = Path(path)
    suffix = p.suffix.lower()
    try:
        if suffix == ".py":
            ast.parse(text, path)
            return ""
        if suffix == ".json":
            json.loads(text)
            return ""
    except (SyntaxError, ValueError) as exc:
        return str(exc)
    if suffix in CPP:
        return cpp_problem(text)
    if suffix == ".i" or p.name == "tests":
        return hit_problem(text)
    return None


def check(comment: dict, root: Path) -> str:
    """"" when the suggestion may stay, else the reason to drop it."""
    body = str(comment.get("body") or "")
    fences = FENCE.findall(body)
    if len(fences) != 1:
        return "more than one suggestion fence"
    if (comment.get("side") or "RIGHT") != "RIGHT" or (comment.get("start_side") or "RIGHT") != "RIGHT":
        return "a suggestion must replace lines on the RIGHT side"
    try:
        end = int(comment["line"])
        start = int(comment.get("start_line") or end)
    except (KeyError, TypeError, ValueError):
        return "no line range"
    target = root / str(comment.get("path") or "")
    if not target.is_file():
        return "file not found in the checkout"
    original = target.read_text()
    lines = original.split("\n")
    if original.endswith("\n"):
        lines = lines[:-1]
    if not 1 <= start <= end <= len(lines):
        return "range %d-%d is outside the file (%d lines)" % (start, end, len(lines))
    repl = fences[0].split("\n")
    if repl and repl[-1] == "":
        repl = repl[:-1]
    patched_lines = lines[: start - 1] + repl + lines[end:]
    if patched_lines == lines:
        return "the replacement changes nothing"
    above = lines[start - 2] if start >= 2 else None
    below = lines[end] if end < len(lines) else None
    if repl and above is not None and above.strip() and repl[0] == above:
        return "the replacement repeats line %d above the range (off by one?)" % (start - 1)
    if repl and below is not None and below.strip() and repl[-1] == below:
        return "the replacement repeats line %d below the range (off by one?)" % (end + 1)
    patched = "\n".join(patched_lines) + ("\n" if original.endswith("\n") else "")
    before = problem(str(comment["path"]), original)
    if before:  # the original does not parse either, so a parse error proves nothing
        return ""
    after = problem(str(comment["path"]), patched)
    if after:
        return "the patched file does not parse: %s" % (after,)
    return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", required=True)
    ap.add_argument("--root", required=True)
    args = ap.parse_args(argv)
    root = Path(args.root)
    doc = json.loads(Path(args.all).read_text())
    checked, kept, dropped = 0, 0, []
    for bucket in doc:
        for c in bucket.get("inline_comments") or []:
            if "```suggestion" not in str(c.get("body") or ""):
                continue
            checked += 1
            why = check(c, root)
            if why:
                c["body"] = strip_fence(str(c["body"]))
                dropped.append({"path": c.get("path"), "line": c.get("line"), "reason": why})
            else:
                kept += 1
        for f in bucket.get("body_findings") or []:
            key = "body" if "body" in f else "summary"
            if "```suggestion" in str(f.get(key) or ""):
                checked += 1
                f[key] = strip_fence(str(f[key]))
                dropped.append({"path": f.get("path"), "line": f.get("line"),
                                "reason": "a body finding cannot carry an applicable suggestion"})
    Path(args.all).write_text(json.dumps(doc))
    print(json.dumps({"checked": checked, "kept": kept, "dropped": dropped}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
