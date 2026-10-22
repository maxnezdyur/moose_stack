#!/usr/bin/env python3
"""Prove step of a PR-mode review: pick the comments to verify, then apply the verdicts.

Usage:
  review-prove-apply.py select --label <label> [--cap 30] [--group-size 4]
  review-prove-apply.py apply  --label <label> --out <dir>

`select` runs after review-merge.sh --mode pr. It reads the merged findings
(/tmp/moose-review-<label>.json) and the payload (/tmp/moose-review-<label>-payload.json), and
writes /tmp/moose-verify-<label>/findings.json (every payload comment, selected or not, with the
reason) and one group-<k>.json per verifier. Only `code` and `ad` comments are selected: they
claim a behaviour that an input file or a unit test can show. A group holds comments of one
scope (`test` for the framework, or `modules/<m>`), because each group builds one binary. It
prints {"dir","selected","skipped","groups":[{"group","path","count","files","scope"}]}.

`apply` runs after the verifiers. It reads each out-<k>.json and rewrites the payload that
review-post.sh posts:
  - a `refuted` comment is dropped, so it never reaches GitHub;
  - a `confirmed-caveat` comment gains its caveat as the last sentence of its prose;
  - a suggestion fence whose check was `does-not-fix` or `breaks-tests` is removed, prose kept.
A comment that was not selected, or has no result, is posted unchanged and listed as not
verified. The first `apply` keeps the payload as <payload>.orig.json, and every later `apply`
starts from that copy, so a rerun gives the same payload. It writes <dir>/verify.md and copies
the tests to <dir>/tests/ (the orchestrator passes <meta-root>/specs/verify/<label>). The repro
tests stay local: nothing from them goes into the payload.

It prints {"checked","confirmed","caveat","by_reading","refuted","unverified","not_checked",
"suggestions":{"fixes","does_not_fix","breaks"},"verify_md","payloads":[{"repo","payload",
"inline","dropped","post"}]}. `payloads` holds one entry, or none when merge wrote no payload.

Exit 0 on success, 2 on a usage or input error.
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

# Buckets whose findings claim a behaviour a test can show. test, doc, dry and newobj findings are
# about the text of the change or about an absent file, so a test proves nothing about them.
# Earlier buckets win the cap.
BEHAVIOURAL = ("code", "ad")
FENCE = re.compile(r"\n?```suggestion[^\n]*\n(.*?)\n```[ \t]*", re.S)
REPO = "moose"
VERDICTS = ("confirmed", "confirmed-caveat", "confirmed-by-reading", "refuted", "unverified")


def fail(msg: str) -> "None":
    print("error: " + msg, file=sys.stderr)
    sys.exit(2)


def load(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        fail("cannot read %s: %s" % (path, exc))


def prefix(label: str) -> Path:
    return Path("/tmp/moose-review-%s" % label)


def vdir(label: str) -> Path:
    return Path("/tmp/moose-verify-%s" % label)


def payload_path(label: str, repo: str) -> Path:
    return Path("%s-payload.json" % prefix(label))


def repos_of(label: str) -> list:
    meta = load(Path("%s-meta.json" % prefix(label)))
    if meta.get("mode") != "pr" or not meta.get("head_sha"):
        fail("the meta file is not a PR snapshot; the prove step runs in PR mode only")
    return [REPO]


def scope_of(path: str) -> str:
    """The test scope that builds the code at `path`: `modules/<m>`, else `test` (the framework)."""
    parts = Path(path).parts
    if len(parts) >= 2 and parts[0] == "modules":
        return "modules/%s" % parts[1]
    return "test"


def inline_of(merged: list, repo: str) -> list:
    """The merged inline comments, in the order review-merge.sh wrote them to the payload."""
    return [dict(c, bucket=doc.get("bucket")) for doc in merged
            for c in (doc.get("inline_comments") or [])]


def first_sentence(body: str) -> str:
    prose = FENCE.sub("", body).strip().split("\n")[0]
    m = re.match(r"(.+?[.!?])(\s|$)", prose)
    return (m.group(1) if m else prose)[:160]


def select(args) -> int:
    merged = load(Path("%s.json" % prefix(args.label)))
    rows = []
    for repo in repos_of(args.label):
        pp = payload_path(args.label, repo)
        base = Path(str(pp).replace(".json", ".orig.json"))
        if not base.is_file() and not pp.is_file():
            continue  # review-merge.sh wrote no payload: nothing to post, nothing to prove
        payload = load(base if base.is_file() else pp)
        inline = inline_of(merged, repo)
        comments = payload.get("comments") or []
        if len(inline) != len(comments):
            fail("%s: %d merged comments but %d in the payload; run review-merge.sh again"
                 % (repo, len(inline), len(comments)))
        for n, (src, c) in enumerate(zip(inline, comments), 1):
            fence = FENCE.search(c.get("body") or "")
            rows.append({
                "id": "c%d" % n, "repo": repo, "index": n - 1, "scope": scope_of(c["path"]),
                "path": c["path"], "line": c.get("line"),
                "start_line": c.get("start_line"), "body": c.get("body") or "",
                "suggestion": fence.group(1) if fence else None,
                "bucket": src.get("bucket"), "kind": str(src.get("kind") or "").lower(),
            })
    order = {b: i for i, b in enumerate(BEHAVIOURAL)}
    # Required comments win the cap over suggested ones, then earlier buckets.
    kinds = {"required": 0, "suggested": 1}
    wanted = [r for r in rows if r["kind"] in kinds and r["bucket"] in order]
    wanted.sort(key=lambda r: (kinds[r["kind"]], order[r["bucket"]], r["path"], r["line"] or 0))
    chosen = {r["id"] for r in wanted[:args.cap]}
    for r in rows:
        if r["id"] in chosen:
            r["selected"], r["reason"] = True, ""
        elif r["kind"] not in kinds:
            r["selected"], r["reason"] = False, "a %s finding" % (r["kind"] or "unclassified")
        elif r["bucket"] not in order:
            r["selected"], r["reason"] = False, "a %s finding, which no test can show" % r["bucket"]
        else:
            r["selected"], r["reason"] = False, "over the cap of %d" % args.cap
    # Groups: one scope each (a group builds one binary), same file together, then neighbours by
    # path, at most group-size each.
    picked = sorted((r for r in rows if r["selected"]), key=lambda r: (r["scope"], r["path"], r["line"] or 0))
    groups, cur = [], []
    for r in picked:
        if cur and (len(cur) >= args.group_size or cur[0]["scope"] != r["scope"]
                    or (Path(cur[0]["path"]).parent != Path(r["path"]).parent and len(cur) >= 2)):
            groups.append(cur)
            cur = []
        cur.append(r)
    if cur:
        groups.append(cur)
    out = vdir(args.label)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("group-*.json"):
        old.unlink()
    for old in out.glob("out-*.json"):
        old.unlink()
    keys = ("id", "path", "line", "start_line", "body", "suggestion")
    info = []
    for k, g in enumerate(groups, 1):
        (out / ("group-%d.json" % k)).write_text(json.dumps([{x: r[x] for x in keys} for r in g], indent=2))
        info.append({"group": k, "path": str(out / ("group-%d.json" % k)), "count": len(g),
                     "files": sorted({r["path"] for r in g}), "scope": g[0]["scope"]})
    (out / "findings.json").write_text(json.dumps(rows, indent=2))
    print(json.dumps({"dir": str(out), "selected": len(picked), "skipped": len(rows) - len(picked),
                      "groups": info}))
    return 0


def has_body_findings(body: str) -> bool:
    """True when the body holds a bullet."""
    return any(line.startswith("- ") for line in body.split("\n"))


def with_caveat(body: str, caveat: str) -> str:
    caveat = caveat.strip()
    if not caveat:
        return body
    m = FENCE.search(body)
    if not m:
        return body.rstrip() + " " + caveat
    return body[:m.start()].rstrip() + " " + caveat + body[m.start():]


def cell(text) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip()


def apply(args) -> int:
    out = vdir(args.label)
    rows = load(out / "findings.json")
    results = {}
    for f in sorted(out.glob("out-*.json")):
        for r in (load(f).get("results") or []):
            results[str(r.get("id"))] = r
    counts = {v: 0 for v in VERDICTS}
    sug = {"fixes": 0, "does_not_fix": 0, "breaks": 0}
    for r in rows:
        res = results.get(r["id"]) if r["selected"] else None
        if r["selected"] and res is None:
            res = {"verdict": "unverified", "how": "the verifier returned no result"}
        if res is not None:
            v = res.get("verdict")
            if v not in VERDICTS:
                res = dict(res, verdict="unverified", how="unknown verdict %r: %s" % (v, res.get("how", "")))
            counts[res["verdict"]] += 1
            s = res.get("suggestion") or "n/a"
            if r["suggestion"] is not None and s in ("fixes", "does-not-fix", "breaks-tests"):
                sug[{"fixes": "fixes", "does-not-fix": "does_not_fix", "breaks-tests": "breaks"}[s]] += 1
        r["result"] = res

    summaries = []
    for repo in repos_of(args.label):
        pp = payload_path(args.label, repo)
        orig = Path(str(pp).replace(".json", ".orig.json"))
        bp = Path(str(pp).replace("-payload.json", "-payload-buckets.json"))
        borig = Path(str(bp).replace(".json", ".orig.json"))
        if not orig.is_file():
            if not pp.is_file():
                continue
            shutil.copy2(pp, orig)
            if bp.is_file():
                shutil.copy2(bp, borig)
        payload = load(orig)
        buckets = load(borig) if borig.is_file() else None
        mine = {r["index"]: r for r in rows if r["repo"] == repo}
        comments, kept_buckets, dropped = [], [], 0
        for i, c in enumerate(payload.get("comments") or []):
            res = (mine.get(i) or {}).get("result") or {}
            v = res.get("verdict")
            if v == "refuted":
                dropped += 1
                continue
            body = c.get("body") or ""
            if v == "confirmed-caveat":
                body = with_caveat(body, res.get("caveat") or "")
            if res.get("suggestion") in ("does-not-fix", "breaks-tests"):
                body = FENCE.sub("", body).rstrip()
            comments.append(dict(c, body=body))
            if buckets is not None and i < len(buckets):
                kept_buckets.append(buckets[i])
        payload["comments"] = comments
        pp.write_text(json.dumps(payload, indent=2))
        if buckets is not None:
            bp.write_text(json.dumps(kept_buckets))
        summaries.append({"repo": repo, "payload": str(pp), "inline": len(comments), "dropped": dropped,
                          "post": bool(comments) or has_body_findings(payload.get("body") or "")})

    vd = Path(args.out)
    vd.mkdir(parents=True, exist_ok=True)
    if (vd / "tests").exists():
        shutil.rmtree(vd / "tests")
    if (out / "tests").is_dir():
        shutil.copytree(out / "tests", vd / "tests")
    label_of = {"confirmed": "Confirmed", "confirmed-caveat": "Confirmed, with a caveat",
                "confirmed-by-reading": "Confirmed by reading", "refuted": "Refuted",
                "unverified": "Not verified"}
    checked = [r for r in rows if r["result"] is not None]
    md = ["# Comment verification: %s" % args.label, "",
          "Each checked comment got one test that passes only if the claimed bug happens. The tests "
          "ran against a scratch clone of the PR head, never the moose checkout. They stay local: "
          "the pending review carries only the comments.", "",
          "Checked %d: %d confirmed, %d with a caveat, %d by reading, %d refuted, %d not verified."
          % (len(checked), counts["confirmed"], counts["confirmed-caveat"], counts["confirmed-by-reading"],
             counts["refuted"], counts["unverified"]), "",
          "| # | Comment | Verdict | How it was shown | Suggestion | Tests |",
          "|---|---|---|---|---|---|"]
    for r in checked:
        res = r["result"]
        how = res.get("how") or ""
        if res.get("caveat"):
            how += " Caveat: " + res["caveat"]
        s = (res.get("suggestion") or "n/a") if r["suggestion"] is not None else "n/a"
        if res.get("suggestion_detail"):
            s += " (%s)" % res["suggestion_detail"]
        tests = ", ".join("`tests/%s`" % t for t in (res.get("tests") or []))
        md.append("| %s | `%s:%s` %s | %s | %s | %s | %s |" % (
            r["id"], r["path"], r["line"], cell(first_sentence(r["body"])), label_of[res["verdict"]],
            cell(how), cell(s), tests))
    refuted = [r for r in checked if r["result"]["verdict"] == "refuted"]
    md += ["", "## Dropped before posting", ""]
    md += (["- %s `%s:%s` %s -- %s" % (r["id"], r["path"], r["line"], first_sentence(r["body"]),
                                        cell(r["result"].get("how"))) for r in refuted] or ["None."])
    skipped = [r for r in rows if r["result"] is None]
    md += ["", "## Posted without a check", ""]
    md += (["- %s `%s:%s` %s -- %s" % (r["id"], r["path"], r["line"], first_sentence(r["body"]), r["reason"])
            for r in skipped] or ["None."])
    (vd / "verify.md").write_text("\n".join(md) + "\n")
    print(json.dumps({"checked": len(checked), "confirmed": counts["confirmed"],
                      "caveat": counts["confirmed-caveat"], "by_reading": counts["confirmed-by-reading"],
                      "refuted": counts["refuted"], "unverified": counts["unverified"], "not_checked": len(skipped),
                      "suggestions": sug, "verify_md": str(vd / "verify.md"), "payloads": summaries}))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    s.add_argument("--label", required=True)
    s.add_argument("--cap", type=int, default=30)
    s.add_argument("--group-size", type=int, default=4)
    a = sub.add_parser("apply")
    a.add_argument("--label", required=True)
    a.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    return select(args) if args.cmd == "select" else apply(args)


if __name__ == "__main__":
    sys.exit(main())
