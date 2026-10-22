#!/usr/bin/env python3
"""review-dedup.py -- drop the findings that another reviewer already raised on the PR.

Usage:
  review-dedup.py --all <all.json> --threads <P-threads.json>

<all.json> is the merged reviewer list that review-merge.sh builds: one object per bucket with
`inline_comments`. <P-threads.json> is what review-discussion.sh wrote: one entry per thread,
{path, line, side, status, author, body, replies}.

Finding paths and thread paths are both relative to the moose repository root, the form GitHub
uses. An inline finding is already raised when an open or resolved thread sits on the same
path, within 3 lines of the finding's range, and the two texts share their point: at least 3
content words, and at least 40 % of the shorter text's content words. An outdated thread never
counts, because its line no longer says what the comment was about. The file is rewritten in
place without those findings, and stdout gets one JSON array:
  [{"path": "<path>", "line": N, "by": "<thread author>", "status": "open|resolved"}]
"""
import argparse
import json
import re
import sys

NEAR = 3
MIN_SHARED = 3
MIN_OVERLAP = 0.4
FENCE = re.compile(r"```suggestion.*?```", re.S)
# Content words: lower-case tokens longer than 2 characters, minus these, with a plural s cut.
STOP = set("a an the of to in on and or is are be with from for by as at it its this that shows "
           "show no not instead my own new fresh".split())


def words(text: str) -> set:
    out = set()
    for w in re.findall(r"[a-z0-9]+", FENCE.sub(" ", text or "").lower()):
        if w in STOP or len(w) <= 2:
            continue
        out.add(w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w)
    return out


def same_point(a: str, b: str) -> bool:
    wa, wb = words(a), words(b)
    shared = wa & wb
    return len(shared) >= MIN_SHARED and len(shared) / float(min(len(wa), len(wb))) >= MIN_OVERLAP


def raised_by(finding: dict, threads: list):
    path = str(finding.get("path") or "")
    line = finding.get("line")
    if not isinstance(line, int):
        return None
    start = finding.get("start_line") if isinstance(finding.get("start_line"), int) else line
    lo, hi = min(start, line) - NEAR, max(start, line) + NEAR
    for t in threads:
        if t.get("status") not in ("open", "resolved"):
            continue
        if path != str(t.get("path") or ""):
            continue
        if not isinstance(t.get("line"), int) or not lo <= t["line"] <= hi:
            continue
        if same_point(str(finding.get("body") or ""), str(t.get("body") or "")):
            return t
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", required=True)
    ap.add_argument("--threads", required=True)
    args = ap.parse_args(argv)
    reviewers = json.load(open(args.all))
    threads = json.load(open(args.threads))
    dropped = []
    for r in reviewers:
        kept = []
        for f in r.get("inline_comments") or []:
            t = raised_by(f, threads)
            if t is None:
                kept.append(f)
            else:
                dropped.append({"path": f.get("path"), "line": f.get("line"), "by": t.get("author"),
                                "status": t.get("status")})
        if "inline_comments" in r:
            r["inline_comments"] = kept
    with open(args.all, "w") as fh:
        json.dump(reviewers, fh)
    print(json.dumps(dropped, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
