#!/usr/bin/env python3
"""Decide whether the CIVET failures on a pull request belong to that pull request.

A red job is not always a defect in the branch. When CIVET's own environment
breaks (a conda channel, a container build, a download), the same job fails on
every pull request that runs it. This script compares each failed job on one
pull request against the same job on other recently updated pull requests and
on the tips of the base branches, and gives each failed job a verdict:

  widespread  the job also fails on at least two other authors' heads, and on
              at least half of the heads that ran it since the failures began.
              Likely not caused by this pull request.
  isolated    other heads ran the job in the same period and it passed there.
              Likely caused by this pull request.
  unclear     too few other heads ran the job to say either way.

It reads GitHub commit statuses through the gh CLI and nothing else, so it
works where civet.inl.gov is not reachable. It never reads a log: a verdict is
evidence about where to look, not a diagnosis. Use scripts/civet_ci_failures.py
for the failing tests and build errors inside a job.

    scripts/civet_triage.py --repo idaholab/moose --pr 33820
    scripts/civet_triage.py --repo idaholab/moose --pr 33820 --json
    scripts/civet_triage.py --repo idaholab/moose --pr 33820 --errors

Exit code: 0 when a verdict was reached (whatever it is), 1 when GitHub could
not be read.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BLOCKED = "Won't run due to failed dependencies"
ALLOWED = "Failed but allowed"
FAILED = ("failure", "error")
TERMINAL = ("success", "failure", "error")

WIDESPREAD = "widespread"
ISOLATED = "isolated"
UNCLEAR = "unclear"

# Overall verdicts, one per pull request.
GREEN = "green"        # nothing failed
PENDING = "pending"    # nothing failed yet, jobs still running
INFRA = "infra"        # every real failure is widespread
YOURS = "yours"        # at least one real failure is isolated
MIXED_UNCLEAR = "unclear"  # no isolated failure, and at least one unclear

DEFAULT_PEERS = 20
DEFAULT_WINDOW_H = 48
DEFAULT_BASES = ("next", "devel")
# A widespread verdict needs this many other authors' heads failing the job, and
# at least this share of all the heads that ran it since the failures began.
MIN_SHARED = 2
MIN_SHARE = 0.5
# An isolated verdict needs this many other heads passing the job since this
# pull request failed it, and none failing.
MIN_CLEAN = 3


class GitHubError(Exception):
    pass


def gh(args: List[str], timeout: int = 60) -> str:
    try:
        res = subprocess.run(
            ["gh", *args], capture_output=True, text=True, check=False, timeout=timeout
        )
    except FileNotFoundError as exc:
        raise GitHubError("the gh CLI was not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitHubError("gh %s timed out" % (" ".join(args),)) from exc
    if res.returncode != 0:
        raise GitHubError("gh %s failed: %s" % (" ".join(args), res.stderr.strip()))
    return res.stdout


def ts(iso: Optional[str]) -> Optional[float]:
    if not iso:
        return None
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def statuses_of(repo: str, sha: str) -> Dict[str, Dict[str, Any]]:
    """The newest status per context on one commit.

    CIVET posts a status when a job starts and another when it finishes, so the
    newest one per context is the job's state.
    """
    raw = gh(
        [
            "api", "repos/%s/commits/%s/statuses?per_page=100" % (repo, sha), "--paginate",
            "--jq", ".[] | {context, state, description, target_url, updated_at}",
        ]
    )
    out: Dict[str, Dict[str, Any]] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        s = json.loads(line)
        ctx = s.get("context")
        if not ctx:
            continue
        old = out.get(ctx)
        if old is None or (s.get("updated_at") or "") > (old.get("updated_at") or ""):
            out[ctx] = s
    return out


def is_real_failure(s: Dict[str, Any]) -> bool:
    return s.get("state") in FAILED and s.get("description") != BLOCKED


def peers_of(repo: str, number: int, limit: int, bases: List[str]) -> List[Dict[str, str]]:
    """Other heads to compare against: recently updated open PRs and base tips."""
    rows = json.loads(
        gh(
            [
                "pr", "list", "--repo", repo, "--state", "open", "--limit", str(limit + 1),
                "--search", "sort:updated-desc", "--json", "number,headRefOid,author",
            ]
        )
        or "[]"
    )
    peers = [
        {"label": "#%s" % (r["number"],), "sha": r["headRefOid"],
         "author": (r.get("author") or {}).get("login") or "?"}
        for r in rows
        if int(r["number"]) != int(number) and r.get("headRefOid")
    ][:limit]
    for base in bases:
        try:
            sha = gh(["api", "repos/%s/commits/%s" % (repo, base), "--jq", ".sha"]).strip()
        except GitHubError:
            continue  # a downstream app may lack one of the base branches
        if sha:
            peers.append({"label": base, "sha": sha, "author": "push"})
    return peers


def judge(
    job: Dict[str, Any], peer_states: List[Dict[str, Any]], window_s: float, author: str = ""
) -> Dict[str, Any]:
    """One failed job against the same context on every peer."""
    mine = ts(job.get("updated_at")) or 0.0
    ran: List[Dict[str, Any]] = []
    for peer in peer_states:
        s = (peer.get("statuses") or {}).get(job["context"])
        if not s or s.get("state") not in TERMINAL or s.get("description") == BLOCKED:
            continue
        when = ts(s.get("updated_at"))
        if when is None or abs(when - mine) > window_s:
            continue
        ran.append({"label": peer["label"], "failed": s["state"] in FAILED, "when": when,
                    "author": peer.get("author") or "?",
                    "url": s.get("target_url") or ""})
    failed = [r for r in ran if r["failed"]]
    # The onset is the earliest failure in the cluster. A head that passed the
    # job before the onset says nothing about an environment that broke later.
    onset = min([mine] + [r["when"] for r in failed])
    since = [r for r in ran if r["when"] >= onset]
    share = (len(failed) / len(since)) if since else 0.0
    clean_after = [r for r in ran if not r["failed"] and r["when"] >= mine]
    # One author's pull requests are often stacked on each other, so a commit
    # they share fails the same job on all of them. Only a failure on someone
    # else's head, or on a base branch, is evidence about the environment.
    foreign = [r for r in failed if r["author"] != author]
    if len(foreign) >= MIN_SHARED and share >= MIN_SHARE:
        verdict = WIDESPREAD
    elif not failed and len(clean_after) >= MIN_CLEAN:
        verdict = ISOLATED
    elif failed and share < MIN_SHARE and len(since) - len(failed) >= MIN_CLEAN:
        # One or two other heads fail it, most pass it: coincidence is likelier
        # than a broken environment.
        verdict = ISOLATED
    else:
        verdict = UNCLEAR
    return {
        "context": job["context"],
        "url": job.get("target_url") or "",
        "description": job.get("description") or "",
        "updated_at": job.get("updated_at"),
        "verdict": verdict,
        "also_failed_on": sorted(r["label"] for r in failed),
        "passed_on": sorted(r["label"] for r in since if not r["failed"]),
        "peers_ran": len(since),
    }


def triage(
    repo: str,
    number: int,
    peers: int = DEFAULT_PEERS,
    window_h: float = DEFAULT_WINDOW_H,
    bases: Optional[List[str]] = None,
    peer_cache: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """The verdict for one pull request. ``peer_cache`` maps ``repo@sha`` to a
    status table and lets a caller that triages several PRs read each peer once."""
    bases = list(DEFAULT_BASES if bases is None else bases)
    cache = peer_cache if peer_cache is not None else {}
    head = json.loads(
        gh(["pr", "view", str(number), "--repo", repo, "--json", "headRefOid,headRefName,title,author"])
    )
    sha = head["headRefOid"]
    mine = statuses_of(repo, sha)
    failed = sorted((s for s in mine.values() if is_real_failure(s)), key=lambda s: s["context"])
    counts = {
        "jobs": len(mine),
        "failed": len(failed),
        "blocked": sum(1 for s in mine.values() if s.get("state") in FAILED and s.get("description") == BLOCKED),
        "pending": sum(1 for s in mine.values() if s.get("state") == "pending"),
        "passed": sum(1 for s in mine.values() if s.get("state") == "success"),
    }
    out: Dict[str, Any] = {
        "repo": repo,
        "pr": int(number),
        "branch": head.get("headRefName"),
        "head_sha": sha,
        "counts": counts,
        "complete": bool(mine) and counts["pending"] == 0,
        "allowed_failures": sorted(
            s["context"] for s in mine.values()
            if s.get("state") == "success" and ALLOWED in (s.get("description") or "")
        ),
        "jobs": [],
        "peers_compared": 0,
        "peers_unread": 0,
    }
    if not failed:
        out["verdict"] = PENDING if counts["pending"] or not mine else GREEN
        return out

    plist = peers_of(repo, number, peers, bases)
    plist = [p for p in plist if p["sha"] != sha]

    def load(peer: Dict[str, str]) -> Dict[str, Any]:
        key = "%s@%s" % (repo, peer["sha"])
        if key not in cache:
            try:
                cache[key] = statuses_of(repo, peer["sha"])
            except GitHubError:
                return dict(peer, statuses=None)
        return dict(peer, statuses=cache[key])

    with ThreadPoolExecutor(max_workers=8) as pool:
        states = list(pool.map(load, plist))
    out["peers_unread"] = sum(1 for p in states if p["statuses"] is None)
    states = [p for p in states if p["statuses"] is not None]
    out["peers_compared"] = len(states)

    author = (head.get("author") or {}).get("login") or ""
    out["jobs"] = [judge(job, states, window_h * 3600.0, author) for job in failed]
    verdicts = {j["verdict"] for j in out["jobs"]}
    if ISOLATED in verdicts:
        out["verdict"] = YOURS
    elif UNCLEAR in verdicts:
        out["verdict"] = MIXED_UNCLEAR
    else:
        out["verdict"] = INFRA
    return out


HEADLINE = {
    GREEN: "No job failed.",
    PENDING: "No job has failed yet. The event is still running.",
    INFRA: "Every failed job also fails on other pull requests. Likely not caused by this branch: do not change code for it.",
    YOURS: "At least one failed job passes on other pull requests. Likely caused by this branch: read that job's log.",
    MIXED_UNCLEAR: "Not enough other pull requests ran the failed jobs to say. Read the logs before you change code.",
}


def render(t: Dict[str, Any]) -> str:
    c = t["counts"]
    lines = [
        "%s #%s %s @ %s  jobs: %d failed, %d blocked, %d pending, %d passed / %d"
        % (t["repo"], t["pr"], t.get("branch") or "?", (t.get("head_sha") or "")[:7],
           c["failed"], c["blocked"], c["pending"], c["passed"], c["jobs"]),
        "verdict: %s. %s" % (t["verdict"], HEADLINE.get(t["verdict"], "")),
    ]
    if not t["complete"] and c["jobs"]:
        lines.append("The event is incomplete (%d pending); more failures can still arrive." % (c["pending"],))
    if t["jobs"]:
        lines.append("")
        lines.append("compared against %d other heads%s" % (
            t["peers_compared"],
            (", %d could not be read" % (t["peers_unread"],)) if t["peers_unread"] else "",
        ))
    for j in t["jobs"]:
        lines.append("")
        lines.append("%-10s %s  %s" % (j["verdict"], j["context"], j["url"]))
        if j["also_failed_on"]:
            lines.append("  also fails on: %s" % (", ".join(j["also_failed_on"]),))
        lines.append(
            "  passes on %d of %d heads that ran it since the failures began%s"
            % (len(j["passed_on"]), j["peers_ran"],
               (": " + ", ".join(j["passed_on"][:8])) if j["passed_on"] else "")
        )
    if t["allowed_failures"]:
        lines.append("")
        lines.append("failed but allowed (reported as success): %s" % (", ".join(t["allowed_failures"]),))
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="owner/name of the repository that holds the pull request")
    ap.add_argument("--pr", type=int, required=True, help="pull request number")
    ap.add_argument("--peers", type=int, default=DEFAULT_PEERS, help="other open pull requests to compare against")
    ap.add_argument("--window-hours", type=float, default=DEFAULT_WINDOW_H,
                    help="ignore a peer job that finished further than this from the failure")
    ap.add_argument("--base", action="append", default=None,
                    help="base branch whose tip is also a peer; repeatable (default: next, devel)")
    ap.add_argument("--json", action="store_true", help="print the verdict as JSON")
    ap.add_argument("--errors", action="store_true",
                    help="then run civet_ci_failures.py --errors for the failing tests and build errors")
    args = ap.parse_args(argv)
    try:
        t = triage(args.repo, args.pr, args.peers, args.window_hours, args.base)
    except (GitHubError, KeyError, ValueError) as exc:
        print("civet_triage: %s" % (exc,), file=sys.stderr)
        return 1
    print(json.dumps(t, indent=2) if args.json else render(t))
    if args.errors and not args.json and t["counts"]["failed"]:
        print("\n--- civet_ci_failures.py --errors ---", flush=True)
        script = Path(__file__).resolve().parent / "civet_ci_failures.py"
        subprocess.run([sys.executable, str(script), "--repo", args.repo, "--pr", str(args.pr), "--errors"], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
