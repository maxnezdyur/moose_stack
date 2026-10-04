"""CIVET triage: is a red pull request red because of its own branch?

``ci-red`` is true whenever a CIVET context fails, and a context fails for two
unrelated reasons: the branch broke something, or CIVET's own environment broke
(a conda channel, a container build, a download) and the same job is red on
every pull request that ran it. Only the first one is work for Max.

``scripts/civet_triage.py`` tells them apart by comparing each failed job with
the same job on other recently updated pull requests and on the base branch
tips. This module runs it for every open pull request whose rollup is red on the
current head, and publishes the result three ways:

- ``collect`` attaches the verdict to the observation as ``pr["triage"]``, which
  is where ``derive`` reads it: a card whose every red pull request is ``infra``
  gets ``ci-infra``, leaves needs-you, and its next move becomes ``wait-ci``.
- ``note_sections`` writes the per-job table into the note.
- ``factory ci <feature>`` prints the full report; ``--refresh`` reruns it.

A verdict is cached in ``state/civet-triage.json`` per ``repo#number@sha`` for
:data:`TTL` seconds, because the peers it is measured against keep moving. A
cold run costs about 6 s for the first pull request of a repository and about
2 s for each further one, since the peers are read once per round. The round has
a :data:`BUDGET` and a pull request past it keeps its last verdict.

Nothing here reads a CIVET log. ``civet.inl.gov`` answers 403 off the INL
network, and a verdict from commit statuses is available everywhere.
"""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config, derive

CACHE_NAME = "civet-triage.json"
TTL = 1800
BUDGET = 45.0
ORDER_TRIAGE = 35
INFRA = "infra"

USAGE = "usage: factory ci <feature> [--refresh]"
HELP = {"ci": "the CIVET triage of a card's red pull requests: the branch, or CIVET's environment"}


def _script(cfg: Any) -> Path:
    return Path(cfg.repo_root).expanduser() / "scripts" / "civet_triage.py"


def _module(cfg: Any) -> Any:
    spec = importlib.util.spec_from_file_location("civet_triage", str(_script(cfg)))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % (_script(cfg),))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cache_path(cfg: Any) -> Path:
    return Path(cfg.state_dir) / CACHE_NAME


def _read_cache(cfg: Any) -> Dict[str, Any]:
    try:
        data = json.loads(_cache_path(cfg).read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _key(slug: str, pr: Dict[str, Any]) -> str:
    return "%s#%s@%s" % (slug, pr.get("number"), pr.get("headRefOid") or "?")


def _red_prs(obs: Dict[str, Any], cfg: Any) -> List[Tuple[str, Dict[str, Any]]]:
    """``(slug, pr)`` for every open pull request that is red on its current head."""
    out = []
    for pr in obs.get("prs") or []:
        if not isinstance(pr, dict) or (pr.get("state") or "").upper() != "OPEN":
            continue
        if pr.get("ci") != "red" or not derive.rollup_applies(pr, obs):
            continue
        slug = cfg.gh_repos.get(str(pr.get("repo")))
        if slug and pr.get("number") and pr.get("headRefOid"):
            out.append((slug, pr))
    return out


def collect(ctx: Any) -> None:
    cfg = ctx.config
    cache = _read_cache(cfg)
    now = time.time()
    deadline = now + BUDGET
    mod: Any = None
    peers: Dict[str, Dict[str, Any]] = {}
    live: Dict[str, Any] = {}
    changed = False
    for feature in sorted(ctx.obs or {}):
        obs = ctx.obs[feature]
        for slug, pr in _red_prs(obs, cfg):
            key = _key(slug, pr)
            rec = cache.get(key) if isinstance(cache.get(key), dict) else None
            fresh = rec is not None and now - float(rec.get("at") or 0) < TTL
            if not fresh and not cfg.offline and time.time() < deadline and _script(cfg).is_file():
                try:
                    mod = mod or _module(cfg)
                    t = mod.triage(slug, int(pr["number"]), peer_cache=peers)
                    # A push between the probe and this call is a different head.
                    if t.get("head_sha") == pr.get("headRefOid"):
                        rec = {"at": time.time(), "triage": t}
                        changed = True
                except Exception as exc:
                    ctx.log("ext_civet: triage of %s failed: %s" % (key, exc))
            if rec is not None:
                live[key] = rec
                pr["triage"] = dict(rec["triage"], at=rec.get("at"))
    # Keys for heads that are no longer red are dropped with the rewrite.
    if (changed or set(live) != set(cache)) and not ctx.dry_run:
        try:
            config.write_text_atomic(_cache_path(cfg), json.dumps(live, indent=1, sort_keys=True))
        except Exception as exc:
            ctx.log("ext_civet: could not write %s: %s" % (CACHE_NAME, exc))


def _age(at: Any) -> str:
    try:
        minutes = int((time.time() - float(at)) // 60)
    except Exception:
        return "at an unknown time"
    return "just now" if minutes < 1 else "%d min ago" % (minutes,)


def note_sections(card: Any, ctx: Any) -> List[Tuple[str, str, int]]:
    out: List[str] = []
    for pr in card.open_prs():
        t = pr.get("triage")
        if not isinstance(t, dict) or not t.get("jobs"):
            continue
        slug = ctx.config.gh_repos.get(str(pr.get("repo")), "?")
        out.append(
            "%s#%s: **%s**, measured %s against %s other heads."
            % (slug, pr.get("number"), t.get("verdict"), _age(t.get("at")), t.get("peers_compared"))
        )
        out.append("")
        out.append("| job | verdict | also fails on | passes on |")
        out.append("|---|---|---|---|")
        for j in t.get("jobs") or []:
            also = [str(x) for x in (j.get("also_failed_on") or [])]
            out.append(
                "| [%s](%s) | %s | %s | %s of %s |"
                % (
                    str(j.get("context")).replace("|", "/"),
                    j.get("url") or "",
                    j.get("verdict"),
                    (", ".join(also[:6]) + (", ..." if len(also) > 6 else "")) or "none",
                    len(j.get("passed_on") or []),
                    j.get("peers_ran"),
                )
            )
        if t.get("verdict") == INFRA:
            out.append("")
            out.append(
                "Every failed job also fails on other authors' heads, so this is CIVET's "
                "environment and not the branch. Change no code. Re-run when it recovers."
            )
        out.append("")
    if not out:
        return []
    return [("CIVET triage", "\n".join(out).rstrip(), ORDER_TRIAGE)]


def run_ci(rest: List[str], ctx: Any) -> int:
    cfg = ctx.config
    refresh = "--refresh" in rest
    names = [a for a in rest if not a.startswith("--")]
    if len(names) != 1:
        print(USAGE)
        return 2
    config.validate_id(names[0])
    card = ctx.card(names[0])
    if card is None:
        print("no card %r" % (names[0],))
        return 3
    openp = card.open_prs()
    if not openp:
        print("%s has no open pull request" % (card.id,))
        return 0
    try:
        mod = _module(cfg)
    except Exception as exc:
        print("cannot load %s: %s" % (_script(cfg), exc))
        return 3
    code = 0
    for pr in openp:
        slug = cfg.gh_repos.get(str(pr.get("repo")), "")
        t: Optional[Dict[str, Any]] = pr.get("triage") if isinstance(pr.get("triage"), dict) else None
        if (refresh or t is None) and slug and not cfg.offline:
            try:
                t = mod.triage(slug, int(pr["number"]))
                cache = _read_cache(cfg)
                cache["%s#%s@%s" % (slug, pr.get("number"), t.get("head_sha"))] = {
                    "at": time.time(), "triage": t,
                }
                if not ctx.dry_run:
                    config.write_text_atomic(
                        _cache_path(cfg), json.dumps(cache, indent=1, sort_keys=True)
                    )
            except Exception as exc:
                print("triage of %s#%s failed: %s" % (slug, pr.get("number"), exc))
                code = 1
                continue
        if t is None:
            print("%s#%s: no triage (offline, or CI is %s)" % (slug, pr.get("number"), pr.get("ci")))
            continue
        print(mod.render(t))
        if t.get("at"):
            print("(measured %s; `factory ci %s --refresh` reruns it)" % (_age(t.get("at")), card.id))
        print("")
    return code


VERBS = {"ci": run_ci}


def doctor_checks(ctx: Any) -> List[Tuple[str, bool, str]]:
    script = _script(ctx.config)
    return [
        (
            "scripts/civet_triage.py is present",
            script.is_file(),
            "%s is missing, so a red pull request is never triaged and every `ci-red` "
            "reads as the branch's own" % (script,),
        )
    ]
