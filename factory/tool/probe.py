"""Every read of the world. Nothing here derives, and nothing here prints.

Contract: every probe returns ``(value, ok)``. ``ok=False`` means unknown, not
absent. The caller records the probe name in ``obs[id]["stale"]``, and
``snapshot.carry_forward`` replaces the value with the last good one and raises
``probe-stale``. Only a successful probe that says "absent" may demote anything.

Order of the round, cheapest and most authoritative first:

    1. worktrees           git worktree list --porcelain, four repos
    2. per-repo git        branch, pushed, dirty, ahead of upstream/devel, FETCH_HEAD
    3. blueprint           frontmatter, work-plan JSON, unticked clarifications
    4. build record        newest .claude/cache/moose-build-*.json, rescued
    5. GitHub              two passes, both parallel, 300 s cache
    6. sessions            ~/.claude/sessions/*.json plus ~/.claude/jobs/<id>/
    7. ideas               Ideas.md slugs against worktrees, branches, PR heads
"""

from __future__ import annotations

import calendar
import json
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config

Probe = Tuple[Any, bool]

_ISO = "%Y-%m-%dT%H:%M:%S"


def iso(ts: Optional[float] = None) -> str:
    """Local ISO-8601 with a numeric offset, second resolution."""
    if ts is None:
        ts = time.time()
    lt = time.localtime(ts)
    off = -(time.altzone if lt.tm_isdst else time.timezone)
    sign = "+" if off >= 0 else "-"
    off = abs(off)
    return "%s%s%02d:%02d" % (
        time.strftime(_ISO, lt), sign, off // 3600, (off % 3600) // 60,
    )


def day(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts if ts is not None else time.time()))


# --------------------------------------------------------------------------
# Subprocess helper
# --------------------------------------------------------------------------


def run(
    cmd: List[str],
    cwd: Optional[Path] = None,
    timeout: Optional[int] = None,
) -> Probe:
    """Run a command. Returns ``(stdout, ok)``; ``ok`` is False on any failure.

    ``timeout`` defaults to the resolved ``subprocess_timeout``, read per call
    rather than bound at import, so a machine that tunes it in its config file
    changes what the code does and not only what ``factory config`` prints.
    """
    if timeout is None:
        timeout = int(config.settings()["subprocess_timeout"])
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception:
        return ("", False)
    if p.returncode != 0:
        return (p.stdout or "", False)
    return (p.stdout, True)


def _mtime(path: Path) -> Probe:
    try:
        return (path.stat().st_mtime, True)
    except FileNotFoundError:
        return (None, True)          # absent is a fact, not an unknown
    except Exception:
        return (None, False)


def _read_text(path: Path, limit: int = 2_000_000) -> Probe:
    try:
        if path.stat().st_size > limit:
            with path.open("r", errors="replace") as f:
                return (f.read(limit), True)
        return (path.read_text(errors="replace"), True)
    except FileNotFoundError:
        return (None, True)
    except Exception:
        return (None, False)


def _read_json(path: Path) -> Probe:
    text, ok = _read_text(path)
    if not ok:
        return (None, False)
    if text is None:
        return (None, True)
    try:
        return (json.loads(text), True)
    except Exception:
        return (None, False)


# --------------------------------------------------------------------------
# 1. Worktrees
# --------------------------------------------------------------------------


def worktree_list(repo: Path) -> Probe:
    """Parse ``git worktree list --porcelain``.

    Authoritative over a glob: the porcelain list catches the two legacy
    checkouts outside ~/projects/moose-worktrees/, which a glob would hide.
    """
    out, ok = run(["git", "-C", str(repo), "worktree", "list", "--porcelain"])
    if not ok:
        return ([], False)
    entries: List[Dict[str, Any]] = []
    cur: Dict[str, Any] = {}
    for line in out.splitlines():
        if not line.strip():
            if cur.get("path"):
                entries.append(cur)
            cur = {}
            continue
        if line.startswith("worktree "):
            cur = {"path": line[len("worktree "):], "branch": None, "head": None}
        elif line.startswith("HEAD "):
            cur["head"] = line[len("HEAD "):]
        elif line.startswith("branch refs/heads/"):
            cur["branch"] = line[len("branch refs/heads/"):]
        elif line.strip() == "detached":
            cur["branch"] = None
    if cur.get("path"):
        entries.append(cur)
    return (entries, True)


def all_worktrees(cfg: config.Config) -> Tuple[Dict[str, Dict[str, Dict[str, Any]]], bool]:
    """``{worktree path: {repo: entry}}`` for every repo, canonical excluded."""
    ok_all = True
    by_repo: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for repo in cfg.repos:
        root = cfg.repo_root if repo == config.META else cfg.repo_root / repo
        entries, ok = worktree_list(root)
        ok_all = ok_all and ok
        by_repo[repo] = {e["path"]: e for e in entries}

    canonical = str(cfg.repo_root)
    out: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for path, entry in by_repo.get(config.META, {}).items():
        if os.path.realpath(path) == os.path.realpath(canonical):
            continue
        repos: Dict[str, Dict[str, Any]] = {config.META: entry}
        for repo in config.SUBMODULES:
            sub = os.path.join(path, repo)
            found = by_repo.get(repo, {}).get(sub)
            if found:
                repos[repo] = found
        out[path] = repos
    return (out, ok_all)


def local_branches(cfg: config.Config) -> Probe:
    """Every local branch in all four repos, for the Ideas match."""
    names: set = set()
    ok_all = True
    for repo in cfg.repos:
        root = cfg.repo_root if repo == config.META else cfg.repo_root / repo
        out, ok = run(
            ["git", "-C", str(root), "branch", "--list", "--format=%(refname:short)"]
        )
        ok_all = ok_all and ok
        if ok:
            names.update(n.strip() for n in out.splitlines() if n.strip())
    return (sorted(names), ok_all)


# --------------------------------------------------------------------------
# 2. Per-repo git state
# --------------------------------------------------------------------------

_AHEAD_RE = re.compile(r"^\d+$")


def repo_state(path: Path, branch: Optional[str], upstream: str) -> Dict[str, Any]:
    """branch, pushed, dirty, ahead of upstream/devel, FETCH_HEAD date.

    One ``status -sb --porcelain`` call gives both "pushed" and the dirty count.
    A first line ``## b...origin/b`` means pushed; a bare ``## b`` means the
    branch has never been pushed.
    """
    st: Dict[str, Any] = {
        "branch": branch,
        "base": upstream,
        "pushed": None,
        "dirty": None,
        "ahead": None,
        "fetched": None,
        "head": None,
        "stale": [],
    }
    if not path.is_dir():
        st["stale"].append("missing")
        return st

    out, ok = run(["git", "-C", str(path), "status", "-sb", "--porcelain"])
    if ok:
        lines = out.splitlines()
        if lines and lines[0].startswith("##"):
            st["pushed"] = "..." in lines[0]
            st["dirty"] = len(lines) - 1
        else:
            st["dirty"] = len(lines)
    else:
        st["stale"].append("status")

    # The current head sha, so a CI rollup for an older head can be discarded
    # instead of colouring the card. One more cheap call in the same batch.
    out, ok = run(["git", "-C", str(path), "rev-parse", "HEAD"])
    if ok and out.strip():
        st["head"] = out.strip()
    else:
        st["stale"].append("head")

    out, ok = run(["git", "-C", str(path), "rev-list", "--count", upstream + "..HEAD"])
    if ok and _AHEAD_RE.match(out.strip()):
        st["ahead"] = int(out.strip())
    # Not an unknown: with no upstream ref there is no count to know. Render
    # "unknown", never 0, and say so through `fetched`.

    gitdir, ok = run(["git", "-C", str(path), "rev-parse", "--git-dir"])
    common, _ = run(["git", "-C", str(path), "rev-parse", "--git-common-dir"])
    for d in (gitdir.strip(), common.strip()):
        if not d:
            continue
        fh = Path(d)
        if not fh.is_absolute():
            fh = path / fh
        mt, mok = _mtime(fh / "FETCH_HEAD")
        if mok and mt:
            st["fetched"] = day(mt)
            st["fetched_at"] = mt
            break
    if not ok:
        st["stale"].append("gitdir")
    return st


# --------------------------------------------------------------------------
# 3. Blueprint
# --------------------------------------------------------------------------

_FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)


def _frontmatter(text: str) -> Dict[str, Any]:
    m = _FM.match(text)
    if not m:
        return {}
    block = m.group(1)
    try:
        import yaml

        data = yaml.safe_load(block)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    # Six-line fallback so a broken YAML line still yields the status field.
    out: Dict[str, Any] = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith((" ", "\t", "#")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _work_plan(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """The single fenced json block under ``## Work plan``."""
    idx = text.find("\n## Work plan")
    if idx < 0:
        return (None, "no '## Work plan' section")
    block = re.search(r"```json\s*\n(.*?)\n```", text[idx:], re.S)
    if not block:
        return (None, "no fenced json block under '## Work plan'")
    try:
        data = json.loads(block.group(1))
    except Exception as exc:
        return (None, "work-plan JSON does not parse: %s" % (exc,))
    if not isinstance(data, dict):
        return (None, "work-plan JSON is not an object")
    return (data, None)


def _unticked(text: str) -> int:
    idx = text.find("\n## Needs clarification")
    if idx < 0:
        return 0
    rest = text[idx + 1:]
    nxt = re.search(r"\n## ", rest)
    section = rest[: nxt.start()] if nxt else rest
    return len(re.findall(r"^\s*- \[ \]", section, re.M))


def blueprint(worktree: Path) -> Probe:
    """``specs/blueprint.md``, any ``specs/*.md`` with a ``feature:`` key, or the
    generated view's title when the markdown is gone."""
    specs = worktree / "specs"
    if not specs.is_dir():
        return (None, True)

    candidates: List[Path] = []
    primary = specs / "blueprint.md"
    if primary.is_file():
        candidates.append(primary)
    else:
        others = sorted(p for p in specs.glob("*.md") if p.is_file())
        for p in others:
            text, ok = _read_text(p)
            if ok and text and re.search(r"^feature:", text, re.M):
                candidates.append(p)
                break

    if candidates:
        path = candidates[0]
        text, ok = _read_text(path)
        if not ok:
            return (None, False)
        fm = _frontmatter(text or "")
        plan, plan_error = _work_plan(text or "")
        mt, _ = _mtime(path)
        units = plan.get("units") if isinstance(plan, dict) else None
        return (
            {
                "path": str(path),
                "kind": "markdown",
                "status": str(fm.get("status") or "").strip() or None,
                "title": fm.get("title"),
                "feature": fm.get("feature"),
                "repo": fm.get("repo"),
                "scope": fm.get("scope"),
                "object_kind": fm.get("object_kind"),
                "created": str(fm.get("created") or "") or None,
                "unticked": _unticked(text or ""),
                "work_plan_ok": plan is not None,
                "work_plan_error": plan_error,
                "units": len(units) if isinstance(units, list) else None,
                "units_done": sum(
                    1
                    for u in (units or [])
                    if isinstance(u, dict) and u.get("status") == "done"
                )
                if isinstance(units, list)
                else None,
                "mtime": mt,
            },
            True,
        )

    view = specs / "blueprint.html"
    if view.is_file():
        text, ok = _read_text(view, limit=20000)
        if not ok:
            return (None, False)
        m = _TITLE.search(text or "")
        mt, _ = _mtime(view)
        return (
            {
                "path": str(view),
                "kind": "view-only",
                "status": None,
                "title": (m.group(1).strip() if m else None),
                "mtime": mt,
            },
            True,
        )
    return (None, True)


# --------------------------------------------------------------------------
# 4. Build record and review, rescued
# --------------------------------------------------------------------------


def build_record(worktree: Path, rescue_dir: Optional[Path]) -> Probe:
    """Newest ``.claude/cache/moose-build-*.json``, copied into the vault.

    That cache directory is gitignored and dies with the worktree, so the copy
    under ``Artifacts/<feature>/`` is what survives. When the original is gone,
    the copy is read instead.
    """
    found: List[Tuple[float, Path, bool]] = []
    cache = worktree / ".claude" / "cache"
    if cache.is_dir():
        for p in cache.glob("moose-build-*.json"):
            mt, ok = _mtime(p)
            if ok and mt:
                found.append((mt, p, True))
    if rescue_dir and rescue_dir.is_dir():
        for p in rescue_dir.glob("build-*.json"):
            mt, ok = _mtime(p)
            if ok and mt:
                found.append((mt, p, False))
    if not found:
        return (None, True)

    found.sort(reverse=True)
    mt, path, live = found[0]
    data, ok = _read_json(path)
    if not ok:
        return (None, False)
    label = path.name
    label = label[len("moose-build-"):] if label.startswith("moose-build-") else label
    label = label[len("build-"):] if label.startswith("build-") else label
    report = (data or {}).get("report")
    required = None
    if isinstance(report, dict):
        for key in ("required", "required_findings", "findings_required"):
            if isinstance(report.get(key), int):
                required = report[key]
                break
    return (
        {
            "path": str(path),
            "label": label[:-5] if label.endswith(".json") else label,
            "live": live,
            "runId": (data or {}).get("runId"),
            "status": (data or {}).get("status"),
            "required": required,
            "summary": (
                report.get("summary")
                if isinstance(report, dict)
                else (report if isinstance(report, str) else None)
            ),
            "mtime": mt,
        },
        True,
    )


def rescue_review(feature: str, worktree: Optional[Path], artifacts: Path) -> Probe:
    """List the reviews already archived under ``Artifacts/<feature>/``.

    Listing only. ``tool/ext_artifacts.py`` is the single writer of
    ``Artifacts/``: it rescues ``/tmp/moose-review-<feature>.md`` (only with a
    meta file whose root resolves under this feature's worktree), gives a
    differing copy a numbered suffix, and records why a copy was refused.

    Never glob ``/tmp/moose-review-*``: that namespace is shared, and
    ``*-issues.md`` is a linked-issue digest, not a review.
    """
    dest_dir = artifacts / feature
    existing = sorted(dest_dir.glob("review-*.md")) if dest_dir.is_dir() else []
    return ([p.name for p in existing], True)


def unfiled_reviews(known: List[str]) -> Probe:
    """Review artifacts in /tmp that match no card. Listed, never read."""
    try:
        labels = set()
        for p in Path("/tmp").glob("moose-review-*.md"):
            name = p.name[len("moose-review-"):-len(".md")]
            if name.endswith("-issues"):
                name = name[: -len("-issues")]
            if name and name not in known:
                labels.add(name)
        return (sorted(labels), True)
    except Exception:
        return ([], False)


# --------------------------------------------------------------------------
# 5. GitHub, two passes, both parallel
# --------------------------------------------------------------------------

_PASS_A_FIELDS = "number,headRefName,isDraft,state,updatedAt,url,title,mergedAt"
_PASS_B_FIELDS = "number,statusCheckRollup,mergeable,reviewDecision,headRefOid"


def _gh_list(slug: str, limit: int = config.GH_LIMIT) -> Probe:
    out, ok = run(
        [
            "gh", "pr", "list", "--repo", slug, "--author", "@me", "--state", "all",
            "--limit", str(limit), "--json", _PASS_A_FIELDS,
        ],
        timeout=60,
    )
    if not ok:
        return ([], False)
    try:
        data = json.loads(out or "[]")
        return (data if isinstance(data, list) else [], True)
    except Exception:
        return ([], False)


def _gh_view(slug: str, number: int) -> Probe:
    out, ok = run(
        ["gh", "pr", "view", str(number), "--repo", slug, "--json", _PASS_B_FIELDS],
        timeout=60,
    )
    if not ok:
        return (None, False)
    try:
        return (json.loads(out), True)
    except Exception:
        return (None, False)


def _rollup(entries: Any) -> Dict[str, Any]:
    """CIVET posts commit statuses, so the entries are StatusContext.

    red if any FAILURE or ERROR, pending if any PENDING or EXPECTED, else green.
    """
    if not isinstance(entries, list) or not entries:
        return {"ci": None, "failing": []}
    red, pending, failing = False, False, []
    for e in entries:
        if not isinstance(e, dict):
            continue
        state = (e.get("state") or e.get("conclusion") or "").upper()
        name = e.get("context") or e.get("name") or "check"
        url = e.get("targetUrl") or e.get("detailsUrl") or ""
        if state in ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED"):
            red = True
            failing.append({"name": name, "url": url})
        elif state in ("PENDING", "EXPECTED", "IN_PROGRESS", "QUEUED", ""):
            pending = True
    return {"ci": "red" if red else ("pending" if pending else "green"), "failing": failing}


def github(cfg: config.Config) -> Probe:
    """``{repo: [pr, ...]}`` with the live fields applied, through a 300 s cache.

    Pass A is three thin calls at once. Pass B is one call per open PR, in
    parallel. The one-shot full-field call is not just slow, it returns HTTP 504
    on idaholab/moose, reproducibly.
    """
    cache_path = cfg.state_dir / "gh-cache.json"
    cached, _ = _read_json(cache_path)
    if isinstance(cached, dict):
        age = time.time() - float(cached.get("at") or 0)
        fresh = age < cfg.gh_cache_ttl
        if fresh or cfg.offline:
            # "Use the cache" and "the probe succeeded" are two facts. A cache
            # older than its TTL, served because --offline forbids a call, is a
            # carried-forward value: say so, so probe-stale and the masthead fire.
            return (cached, bool(fresh and cached.get("ok", True)))
    if cfg.offline:
        return ({"at": 0, "repos": {}, "as_of": None}, False)
    if not shutil.which("gh"):
        return (cached if isinstance(cached, dict) else {"at": 0, "repos": {}}, False)

    ok_all = True
    last_good = (cached or {}).get("repos") if isinstance(cached, dict) else {}
    last_good = last_good if isinstance(last_good, dict) else {}
    repos: Dict[str, List[Dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=len(cfg.gh_repos)) as pool:
        futures = {
            repo: pool.submit(_gh_list, slug, cfg.gh_limit)
            for repo, slug in cfg.gh_repos.items()
        }
        for repo, fut in futures.items():
            prs, ok = fut.result()
            ok_all = ok_all and ok
            if not ok and isinstance(last_good.get(repo), list):
                # One repo's 504 must not erase that repo's cards. Carry this
                # repo's last good list and let ok_all report the failure.
                repos[repo] = list(last_good[repo])
            else:
                repos[repo] = prs

    jobs: List[Tuple[str, str, int]] = []
    for repo, prs in repos.items():
        for pr in prs:
            if (pr.get("state") or "").upper() == "OPEN":
                jobs.append((repo, cfg.gh_repos[repo], int(pr["number"])))
    if jobs:
        with ThreadPoolExecutor(max_workers=min(cfg.gh_parallel, len(jobs))) as pool:
            results = list(
                pool.map(lambda j: (j[0], j[2], _gh_view(j[1], j[2])), jobs)
            )
        detail: Dict[Tuple[str, int], Dict[str, Any]] = {}
        for repo, number, (data, ok) in results:
            ok_all = ok_all and ok
            if ok and isinstance(data, dict):
                detail[(repo, number)] = data
        for repo, prs in repos.items():
            for pr in prs:
                d = detail.get((repo, int(pr["number"])))
                if not d:
                    continue
                roll = _rollup(d.get("statusCheckRollup"))
                pr["ci"] = roll["ci"]
                pr["failing"] = roll["failing"]
                # UNKNOWN is unknown: GitHub computes mergeability lazily and
                # returns UNKNOWN on every merged or closed PR. Never set
                # `conflicting` from it.
                pr["mergeable"] = d.get("mergeable")
                pr["reviewDecision"] = d.get("reviewDecision")
                pr["headRefOid"] = d.get("headRefOid")

        # GitHub computes mergeability lazily and answers UNKNOWN for a minute
        # or two after every push. Re-poll once, in parallel; if it is still
        # UNKNOWN, mark it so the renderer says "not yet computed" rather than
        # rendering the card as clean.
        unknown = [
            (repo, cfg.gh_repos[repo], int(pr["number"]))
            for repo, prs in repos.items()
            for pr in prs
            if (pr.get("state") or "").upper() == "OPEN"
            and (pr.get("mergeable") or "UNKNOWN") == "UNKNOWN"
        ]
        if unknown:
            with ThreadPoolExecutor(max_workers=min(cfg.gh_parallel, len(unknown))) as pool:
                again = list(pool.map(lambda j: (j[0], j[2], _gh_view(j[1], j[2])), unknown))
            second: Dict[Tuple[str, int], Optional[str]] = {}
            for repo, number, (data, ok) in again:
                ok_all = ok_all and ok
                if ok and isinstance(data, dict):
                    second[(repo, number)] = data.get("mergeable")
            for repo, prs in repos.items():
                for pr in prs:
                    key = (repo, int(pr.get("number") or 0))
                    if key not in second:
                        continue
                    value = second[key]
                    if value and value != "UNKNOWN":
                        pr["mergeable"] = value
                        pr.pop("mergeable_unknown", None)
                    else:
                        pr["mergeable"] = value or "UNKNOWN"
                        pr["mergeable_unknown"] = True

    if not ok_all:
        # Never persist a payload from a failed pass. Caching one writes a fresh
        # timestamp over a partial answer, and every board inside the TTL then
        # serves it as a successful probe with no staleness anywhere.
        if isinstance(cached, dict) and cached.get("repos"):
            return (cached, False)
        return ({"at": time.time(), "as_of": iso(), "repos": repos, "ok": False}, False)

    payload = {"at": time.time(), "as_of": iso(), "repos": repos, "ok": True}
    try:
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        config.write_text_atomic(cache_path, json.dumps(payload))
    except Exception:
        pass
    return (payload, ok_all)


# --------------------------------------------------------------------------
# 6. Live sessions, from files, not from the CLI
# --------------------------------------------------------------------------


def _ps_lstart(pid: int) -> Probe:
    """The process start stamp, or ``None``. Three outcomes, never two.

    ``(stamp, True)``  the process lives and this is when it started.
    ``(None, True)``   ps answered "no such process". Absence as a fact.
    ``(None, False)``  ps could not be asked: a timeout, a missing binary, a
                       fork failure. Unknown, and never "the process is gone".

    Conflating the last two is how a live session reads as dead: the board
    empties its Running table, a lease on a working session reads as stale, and
    ``factory start``'s double-booking refusals stop firing. ``run()`` cannot
    tell them apart, because it returns ok=False for both, so this probe calls
    subprocess itself and reads the return code.
    """
    try:
        p = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return (None, False)
    out = " ".join((p.stdout or "").split())
    if p.returncode == 0:
        return ((out or None), True) if out else (None, False)
    if p.returncode == 1 and not out:
        return (None, True)          # no such process: a fact
    return (None, False)             # any other rc: ps could not answer


_LSTART = "%a %b %d %H:%M:%S %Y"


def _same_process(proc_start: Any, lstart: Any, tolerance: float = 2.0) -> Optional[bool]:
    """Is this pid still the process the session file describes?

    None when the two stamps cannot be compared. The session file writes
    ``procStart`` in UTC while ``ps -o lstart=`` prints local time, so a string
    comparison reads every live session as pid reuse.
    """

    def epochs(stamp: Any) -> Tuple[float, ...]:
        text = " ".join(str(stamp or "").split())
        if not text:
            return ()
        try:
            tm = time.strptime(text, _LSTART)
        except Exception:
            return ()
        got: List[float] = []
        for fn in (time.mktime, calendar.timegm):
            try:
                got.append(float(fn(tm)))
            except Exception:
                pass
        return tuple(got)

    a, b = epochs(proc_start), epochs(lstart)
    if not a or not b:
        return None
    return any(abs(x - y) <= tolerance for x in a for y in b)


def sessions_as_of(cfg: config.Config) -> Optional[str]:
    """When the session picture was last written, from the files themselves."""
    d = cfg.claude_home / "sessions"
    newest: Optional[float] = None
    try:
        for f in d.glob("*.json"):
            mt, ok = _mtime(f)
            if ok and mt and (newest is None or mt > newest):
                newest = mt
    except Exception:
        return None
    return iso(newest) if newest else None


def sessions(cfg: config.Config) -> Probe:
    """Read ``~/.claude/sessions/*.json``, one file per live session.

    A six-line read of that glob reproduces ``claude agents --json`` exactly.
    Never poll the CLI from a tick: each call starts a transient supervisor,
    rewrites roster.json and re-adopts workers, so the probe mutates what it
    measures.
    """
    d = cfg.claude_home / "sessions"
    if not d.is_dir():
        return ([], False)
    try:
        files = sorted(d.glob("*.json"))
    except Exception:
        return ([], False)

    live: List[Dict[str, Any]] = []
    for f in files:
        data, ok = _read_json(f)
        if not ok or not isinstance(data, dict):
            return (live, False)      # a file that does not parse is unknown
        pid = data.get("pid")
        if not isinstance(pid, int):
            continue
        lstart, lok = _ps_lstart(pid)
        if not lok:
            return (live, False)
        if lstart is None:
            continue                  # the process is gone
        if _same_process(data.get("procStart"), lstart) is False:
            continue                  # genuine pid reuse
        row = {
            "pid": pid,
            "sessionId": data.get("sessionId"),
            "cwd": data.get("cwd"),
            "kind": data.get("kind"),
            "name": data.get("name"),
            "status": data.get("status"),
            "waitingFor": data.get("waitingFor"),
            "jobId": data.get("jobId"),
            "startedAt": data.get("startedAt"),
            "procStart": data.get("procStart"),
        }
        short = (row.get("sessionId") or "").split("-")[0]
        job_dir = cfg.claude_home / "jobs" / (row.get("jobId") or short)
        st, st_ok = _read_json(job_dir / "state.json")
        if st_ok and isinstance(st, dict):
            row["bg_id"] = job_dir.name
            row["state"] = st.get("state")
            row["detail"] = st.get("detail")
            row["needs"] = st.get("needs")
            row["tempo"] = st.get("tempo")
            row["children"] = st.get("children")
            text, tok = _read_text(job_dir / "timeline.jsonl")
            if tok and text:
                last = [ln for ln in text.splitlines() if ln.strip()]
                if last:
                    try:
                        row["last_line"] = json.loads(last[-1])
                    except Exception:
                        row["last_line"] = None
        live.append(row)
    return (live, True)


# --------------------------------------------------------------------------
# 7. Ideas
# --------------------------------------------------------------------------

_SLUG_BAD = re.compile(r"[^a-z0-9]+")


def slugify(line: str) -> str:
    """lowercase; strip a leading '- ' and any [[ ]]; every run of characters
    outside [a-z0-9] becomes '-'; trim '-'; truncate to 40 characters."""
    s = line.strip()
    if s.startswith("- "):
        s = s[2:]
    s = s.replace("[[", " ").replace("]]", " ").lower()
    s = _SLUG_BAD.sub("-", s).strip("-")
    return s[:40].strip("-")


def ideas(cfg: config.Config) -> Probe:
    """``[{text, slug}]`` from Ideas.md. No script ever writes that file."""
    text, ok = _read_text(cfg.ideas_note)
    if not ok:
        return ([], False)
    if text is None:
        return ([], True)
    out: List[Dict[str, str]] = []
    for line in text.splitlines():
        if not line.startswith("- "):
            continue
        slug = slugify(line)
        if slug:
            out.append({"text": line[2:].strip(), "slug": slug})
    return (out, True)


# --------------------------------------------------------------------------
# Small per-card probes
# --------------------------------------------------------------------------

MARKERS = (
    "<!-- factory:head:begin -->",
    "<!-- factory:head:end -->",
    "<!-- factory:body:begin -->",
    "<!-- factory:body:end -->",
)


def note(cfg: config.Config, feature: str) -> Probe:
    """The existing note: its markers, its ticked gate boxes, its bytes."""
    path = cfg.note_path(feature)
    text, ok = _read_text(path)
    if not ok:
        return (None, False)
    if text is None:
        return ({"exists": False, "markers_ok": True, "ticked": []}, True)
    missing = [m for m in MARKERS if m not in text]
    ticked: List[str] = []
    if not missing:
        head = text.split(MARKERS[0], 1)[1].split(MARKERS[1], 1)[0]
        for m in re.finditer(r"^\s*- \[[xX]\]\s*([a-z_]+)", head, re.M):
            ticked.append(m.group(1))
    return (
        {
            "exists": True,
            "markers_ok": not missing,
            "missing": missing,
            "ticked": ticked,
            "bytes": len(text.encode("utf-8")),
        },
        True,
    )


def pulse(cfg: config.Config, feature: str) -> Probe:
    mt, ok = _mtime(cfg.pulse_dir / feature)
    return (mt, ok)


def lease(worktree: Optional[Path]) -> Probe:
    """``<worktree>/.factory-lease``: reported when stale, never stolen."""
    if not worktree:
        return (None, True)
    d = Path(worktree) / ".factory-lease"
    if not d.exists():
        return (None, True)
    data, ok = _read_json(d / "lease.json") if d.is_dir() else _read_json(d)
    if not ok:
        return ({"held": True, "owner_alive": None}, True)
    pid = (data or {}).get("pid")
    alive = None
    if isinstance(pid, int):
        lstart, lok = _ps_lstart(pid)
        alive = bool(lstart) if lok else None
    if alive is False:
        # The recorded pid is the launcher's. The Claude daemon respawns a
        # background session in a new process (an auto-update did it to every
        # one on 2026-09-17), so the session outlives that pid. A session file
        # naming this lease's session id or bg id, with a live pid, is the same
        # owner in a new skin, not a stale lease.
        if _lease_session_alive(data or {}):
            alive = True
    rec = dict(data or {})
    rec["held"] = True
    rec["owner_alive"] = alive
    return (rec, True)


def _lease_session_alive(data: Dict[str, Any]) -> bool:
    """True when a session file names this lease's session with a live pid."""
    sid = str(data.get("session_id") or "")
    bg = str(data.get("bg_id") or "")
    if not sid and not bg:
        return False
    try:
        home = Path(config.settings()["claude_home"]).expanduser() / "sessions"
        entries = list(home.glob("*.json"))
    except Exception:
        return False
    for path in entries:
        rec, ok = _read_json(path)
        if not ok or not isinstance(rec, dict):
            continue
        if (sid and str(rec.get("sessionId") or "") == sid) or (
            bg and str(rec.get("jobId") or "") == bg
        ):
            spid = rec.get("pid")
            if isinstance(spid, int):
                lstart, lok = _ps_lstart(spid)
                if lok and lstart:
                    return True
    return False


def skills(worktree: Optional[Path]) -> Probe:
    """The worktree's frozen skill inventory.

    Every worktree carries a ``.claude`` frozen at its creation date, so the
    board must never print a command the worktree cannot run.
    """
    if not worktree:
        return (None, True)
    d = Path(worktree) / ".claude" / "skills"
    if not d.is_dir():
        return ({"names": [], "has_ship": False}, True)
    try:
        names = sorted(p.name for p in d.iterdir() if p.is_dir())
    except Exception:
        return (None, False)
    return ({"names": names, "has_ship": "moose-ship" in names}, True)


def workspaces(worktree: Optional[Path]) -> Probe:
    """The ``.code-workspace`` files the note links."""
    if not worktree:
        return ([], True)
    try:
        return (sorted(p.name for p in Path(worktree).glob("*.code-workspace")), True)
    except Exception:
        return ([], False)


def reclaimable_kb(worktree: Optional[Path]) -> Probe:
    """``du -sk`` of the worktree. The only number that motivates teardown."""
    if not worktree or not Path(worktree).is_dir():
        return (None, True)
    out, ok = run(["du", "-sk", str(worktree)], timeout=60)
    if not ok:
        return (None, False)
    try:
        return (int(out.split()[0]), True)
    except Exception:
        return (None, False)


# --------------------------------------------------------------------------
# The round
# --------------------------------------------------------------------------


def remembered(cfg: config.Config) -> Dict[str, Dict[str, Any]]:
    """The last good observation of every card the state store remembers.

    Read straight from ``factory/state/*.json`` rather than through
    ``snapshot.Store``, which imports this module. Used for exactly one thing:
    a card whose *enumerating* probe came back unknown must not disappear. A
    failed ``git worktree list`` is not proof that nine worktrees were deleted.
    """
    out: Dict[str, Dict[str, Any]] = {}
    d = cfg.state_dir
    if not d.is_dir():
        return out
    try:
        files = sorted(d.glob("*.json"))
    except Exception:
        return out
    for f in files:
        if f.name in ("gh-cache.json", "manifest.json", "stamps.json") or f.name.startswith("_"):
            continue
        data, ok = _read_json(f)
        if not ok or not isinstance(data, dict):
            continue
        obs = data.get("obs")
        if isinstance(obs, dict) and obs.get("id"):
            out[f.stem] = obs
    return out


def _recover(
    cfg: config.Config,
    obs: Dict[str, Dict[str, Any]],
    meta: Dict[str, Any],
    want_du: bool,
) -> None:
    """Re-create the cards an unknown enumeration would have silently deleted.

    One rule per enumerating probe: a remembered card whose own enumerator is
    unknown this run comes back, with every per-card value marked stale so
    ``carry_forward`` restores it. A board that publishes half the work is worse
    than a board that says "unknown".
    """
    stale = set(meta.get("stale") or [])
    if not stale & {"worktrees", "github", "ideas"}:
        return
    for feature, prev in sorted(remembered(cfg).items()):
        if feature in obs or not config.is_safe_id(feature):
            continue
        provenance = prev.get("provenance") or ""
        if prev.get("worktree"):
            owner = "worktrees"
        elif provenance == "idea":
            owner = "ideas"
        else:
            owner = "github"
        if owner not in stale:
            continue
        card: Dict[str, Any] = {
            "id": feature,
            "worktree": prev.get("worktree"),
            "foreign": prev.get("foreign") or False,
            "provenance": provenance or "discovered-worktree",
            "stale": [owner],
            "repos": {},
            "prs": [],
        }
        if prev.get("idea"):
            card["idea"] = prev["idea"]
        for repo in cfg.repos:
            card["stale"].append("repo:" + repo)
        if "github" in stale:
            card["stale"].append("github")
        path = Path(card["worktree"]) if card["worktree"] else None
        _fill_card(cfg, card, path if (path and path.is_dir()) else None, want_du)
        if card["worktree"] and not (path and path.is_dir()):
            card["stale"].extend(["blueprint", "build", "skills", "workspaces", "lease"])
        obs[feature] = card
        meta.setdefault("recovered", []).append(feature)


def round_all(cfg: config.Config, want_du: bool = False) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """One snapshot per run, shared by every card.

    Returns ``(obs, meta)``. ``obs[id]["stale"]`` names every probe that came
    back unknown for that card; ``meta["stale"]`` names the global ones.
    """
    meta: Dict[str, Any] = {"stale": [], "at": iso()}

    wts, ok = all_worktrees(cfg)
    if not ok:
        meta["stale"].append("worktrees")
    gh, ok = github(cfg)
    if not ok:
        meta["stale"].append("github")
    sess, ok = sessions(cfg)
    if not ok:
        meta["stale"].append("sessions")
    idea_rows, ok = ideas(cfg)
    if not ok:
        meta["stale"].append("ideas")
    branches, ok = local_branches(cfg)
    if not ok:
        meta["stale"].append("branches")

    meta["gh_as_of"] = (gh or {}).get("as_of")
    # The session picture's own stamp, never the clock: the newest mtime in
    # ~/.claude/sessions/. A wall-clock stamp in the masthead would move on
    # every run, which moves the content stamp, which makes the tick commit a
    # board whose only change is the time it ran.
    meta["sessions_as_of"] = sessions_as_of(cfg)
    meta["session_count"] = len(sess)
    meta["worktree_count"] = len(wts)
    meta["branches"] = branches

    # --- per-worktree git, in parallel: 4 repos x 9 worktrees of MOOSE ----
    jobs: List[Tuple[str, str, Path, Optional[str]]] = []
    for path, repos in sorted(wts.items()):
        feature = os.path.basename(path.rstrip("/"))
        for repo in cfg.repos:
            entry = repos.get(repo)
            sub = Path(path) if repo == config.META else Path(path) / repo
            jobs.append((feature, repo, sub, (entry or {}).get("branch")))
    states: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if jobs:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for (feature, repo, _sub, _b), st in zip(
                jobs,
                pool.map(lambda j: repo_state(j[2], j[3], config.base_ref(j[1])), jobs),
            ):
                states[(feature, repo)] = st

    obs: Dict[str, Dict[str, Any]] = {}

    # --- worktree cards ---------------------------------------------------
    for path, repos in sorted(wts.items()):
        feature = os.path.basename(path.rstrip("/"))
        if not config.is_safe_id(feature):
            meta.setdefault("skipped", []).append(path)
            continue
        card: Dict[str, Any] = {
            "id": feature,
            "worktree": path,
            "foreign": cfg.is_foreign(Path(path)),
            "provenance": "discovered-worktree",
            "stale": [],
            "repos": {},
        }
        for repo in cfg.repos:
            st = states.get((feature, repo))
            if st is None:
                continue
            card["repos"][repo] = st
            if st.get("stale"):
                card["stale"].append("repo:" + repo)
        _fill_card(cfg, card, Path(path), want_du)
        obs[feature] = card

    # --- join pull requests on the feature name and on every repo HEAD ----
    matched: Dict[Tuple[str, int], str] = {}
    for feature, card in obs.items():
        keys = {feature}
        for repo, st in (card.get("repos") or {}).items():
            if st.get("branch"):
                keys.add(st["branch"])
        card["prs"] = []
        for repo, prs in ((gh or {}).get("repos") or {}).items():
            for pr in prs:
                if pr.get("headRefName") in keys:
                    row = dict(pr)
                    row["repo"] = repo
                    card["prs"].append(row)
                    matched[(repo, int(pr["number"]))] = feature
        card["prs"].sort(key=lambda p: (p.get("repo") or "", -int(p.get("number") or 0)))

    # --- adopt PR-only cards: an authored OPEN PR that matches no worktree -
    for repo, prs in ((gh or {}).get("repos") or {}).items():
        for pr in prs:
            if (pr.get("state") or "").upper() != "OPEN":
                continue
            if (repo, int(pr["number"])) in matched:
                continue
            feature = pr.get("headRefName") or ""
            if not config.is_safe_id(feature):
                # Dropping work is acceptable; dropping it silently is not.
                meta.setdefault("skipped_prs", []).append(
                    {"repo": repo, "number": int(pr["number"]), "head": feature}
                )
                continue
            card = obs.get(feature)
            if card is None:
                card = {
                    "id": feature,
                    "worktree": None,
                    "foreign": False,
                    "provenance": "discovered-pr",
                    "stale": [],
                    "repos": {},
                    "prs": [],
                }
                _fill_card(cfg, card, None, False)
                obs[feature] = card
            row = dict(pr)
            row["repo"] = repo
            card["prs"].append(row)

    # A card whose enumerating probe failed comes back before anything joins
    # sessions or ideas to it, so a recovered card is a whole card.
    _recover(cfg, obs, meta, want_du)

    # --- live sessions, mapped to the deepest worktree that contains them -
    for row in sess:
        cwd = row.get("cwd") or ""
        best, best_len = None, -1
        for feature, card in obs.items():
            w = card.get("worktree")
            if not w:
                continue
            if cwd == w or cwd.startswith(w.rstrip("/") + "/"):
                if len(w) > best_len:
                    best, best_len = feature, len(w)
        if best:
            obs[best].setdefault("sessions", []).append(row)
    for card in obs.values():
        rows = card.get("sessions") or []
        card["sessions"] = rows
        card["session"] = rows[0] if rows else None
        if "sessions" in meta["stale"]:
            card["stale"].append("sessions")
        if "github" in meta["stale"]:
            card["stale"].append("github")

    # --- ideas: matched against worktrees, branches and PR heads ----------
    known = set(obs)
    pr_heads = {
        pr.get("headRefName")
        for prs in ((gh or {}).get("repos") or {}).values()
        for pr in prs
    }
    all_keys = known | set(branches or []) | {h for h in pr_heads if h}
    m_rows, u_rows = [], []
    for row in idea_rows:
        (m_rows if row["slug"] in all_keys else u_rows).append(row)
    meta["ideas"] = {"matched": m_rows, "unmatched": u_rows}

    # rank-0 cards for unmatched ideas
    for row in u_rows:
        feature = row["slug"]
        if feature in obs or not config.is_safe_id(feature):
            continue
        card = {
            "id": feature,
            "worktree": None,
            "foreign": False,
            "provenance": "idea",
            "idea": row,
            "stale": [],
            "repos": {},
            "prs": [],
        }
        _fill_card(cfg, card, None, False)
        obs[feature] = card

    unfiled, ok = unfiled_reviews(sorted(known))
    if not ok:
        meta["stale"].append("unfiled-reviews")
    meta["unfiled_reviews"] = unfiled

    ages = [
        st.get("fetched_at")
        for card in obs.values()
        for st in (card.get("repos") or {}).values()
        if st.get("fetched_at")
    ]
    if ages:
        now = time.time()
        meta["fetch_age_days"] = [
            int((now - max(ages)) // 86400),
            int((now - min(ages)) // 86400),
        ]
    meta["stale_pipeline"] = sum(
        1
        for c in obs.values()
        if (c.get("skills") or {}).get("has_ship") is False
    )
    return (obs, meta)


def _fill_card(
    cfg: config.Config, card: Dict[str, Any], worktree: Optional[Path], want_du: bool
) -> None:
    """The per-card probes that do not depend on any other card."""
    feature = card["id"]
    artifacts = cfg.artifacts_dir

    if worktree is not None:
        bp, ok = blueprint(worktree)
        card["blueprint"] = bp
        if not ok:
            card["stale"].append("blueprint")

        rec, ok = build_record(worktree, artifacts / feature)
        card["build"] = rec
        if not ok:
            card["stale"].append("build")

        sk, ok = skills(worktree)
        card["skills"] = sk
        if not ok:
            card["stale"].append("skills")

        ws, ok = workspaces(worktree)
        card["workspaces"] = ws
        if not ok:
            card["stale"].append("workspaces")

        lz, ok = lease(worktree)
        card["lease"] = lz
        if not ok:
            card["stale"].append("lease")

        if want_du:
            kb, ok = reclaimable_kb(worktree)
            card["reclaimable_kb"] = kb
            if not ok:
                card["stale"].append("du")
    else:
        card.setdefault("blueprint", None)
        card.setdefault("build", None)
        card.setdefault("skills", None)
        card.setdefault("workspaces", [])
        card.setdefault("lease", None)

    rv, ok = rescue_review(feature, worktree, artifacts)
    card["reviews"] = rv
    if not ok:
        card["stale"].append("reviews")

    nt, ok = note(cfg, feature)
    card["note"] = nt
    if not ok:
        card["stale"].append("note")

    pl, ok = pulse(cfg, feature)
    card["pulse"] = pl
    if not ok:
        card["stale"].append("pulse")

    card.setdefault("sessions", [])
    card.setdefault("session", None)
