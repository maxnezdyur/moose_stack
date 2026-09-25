"""refresh-pipeline: unfreeze one worktree's ``.claude``.

Every worktree carries a ``.claude`` frozen at its creation date, so a skill
edited in the canonical checkout never reaches it. None of the nine worktrees
has ``moose-ship`` today, and one still ships skills that were deleted a month
ago. The board must therefore never print a command the worktree cannot run, and
there must be a way to fix that:

    factory refresh-pipeline <feature> [--dry-run] [--confirm]

It compares ``moose_stack/.claude/{skills,agents,hooks,settings.json}`` with the
worktree's copy and prints what differs. It copies the canonical tree in only on
explicit confirmation: ``--confirm`` plus an interactive terminal plus typing the
feature name. Without all three it prints and exits 0, so the tick, a hook and a
background agent can never write inside a worktree.

Two things it never does: it never deletes a file the worktree has and the
canonical tree does not (``settings.local.json`` and ``cache/`` are the
worktree's own), and it never touches a foreign checkout outside
``~/projects/moose-worktrees/``. Those are torn down, not refreshed.

It also owns the pipeline view of the board: ``stale-pipeline`` on any card whose
skill inventory is not the canonical one, and two ``factory doctor`` checks.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config, probe

OK, LOOK, REFUSED, MISSING = 0, 1, 2, 3

# What a pipeline is made of, in the order it is reported.
PIPELINE = ("skills", "agents", "hooks", "settings.json")

# Never copied, never reported: the worktree's own, or pure cache.
SKIP_NAMES = ("settings.local.json", "cache", ".DS_Store", "scheduled_tasks.lock")

NON_INTERACTIVE_MARKERS = (
    "FACTORY_FROM_EVENT",
    "FACTORY_TICK",
    "FACTORY_NONINTERACTIVE",
    "CLAUDE_HOOK",
)

# The skill whose absence makes a worktree unable to ship.
SHIP_SKILL = "moose-ship"


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _factory(cfg: config.Config) -> str:
    """The launcher, as a command to paste: tilde-collapsed, never a user name."""
    return config.display_path(cfg.repo_root / "factory" / "factory")


# --------------------------------------------------------------------------
# Comparing two .claude trees
# --------------------------------------------------------------------------


def _digest(path: Path) -> str:
    h = hashlib.sha1()
    try:
        with path.open("rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
    except Exception:
        return "unreadable"
    return h.hexdigest()[:16]


def _files(root: Path, entry: str) -> Dict[str, str]:
    """``{relative path: digest}`` under ``<root>/<entry>``, skips cache."""
    base = root / entry
    out: Dict[str, str] = {}
    if base.is_file():
        out[entry] = _digest(base)
        return out
    if not base.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in sorted(dirnames) if d not in SKIP_NAMES]
        for name in sorted(filenames):
            if name in SKIP_NAMES:
                continue
            full = Path(dirpath) / name
            rel = os.path.relpath(str(full), str(root))
            out[rel] = _digest(full)
    return out


def compare(canonical_claude: Path, worktree_claude: Path) -> Dict[str, Any]:
    """What the worktree is missing, what differs, and what is only its own."""
    report: Dict[str, Any] = {"entries": {}, "missing": [], "differs": [], "extra": [], "same": 0}
    for entry in PIPELINE:
        left = _files(canonical_claude, entry)
        right = _files(worktree_claude, entry)
        missing = sorted(set(left) - set(right))
        extra = sorted(set(right) - set(left))
        differs = sorted(k for k in set(left) & set(right) if left[k] != right[k])
        same = len(set(left) & set(right)) - len(differs)
        report["entries"][entry] = {
            "canonical": len(left),
            "worktree": len(right),
            "missing": missing,
            "differs": differs,
            "extra": extra,
            "same": same,
        }
        report["missing"].extend(missing)
        report["differs"].extend(differs)
        report["extra"].extend(extra)
        report["same"] += same
    report["clean"] = not (report["missing"] or report["differs"])
    return report


def skill_names(claude_dir: Path) -> List[str]:
    d = claude_dir / "skills"
    if not d.is_dir():
        return []
    try:
        return sorted(p.name for p in d.iterdir() if p.is_dir())
    except Exception:
        return []


_CANON_SKILLS: Dict[str, List[str]] = {}


def canonical_skills(cfg: config.Config) -> List[str]:
    """The canonical skill inventory, read once per process."""
    key = str(cfg.repo_root)
    if key not in _CANON_SKILLS:
        _CANON_SKILLS[key] = skill_names(cfg.repo_root / ".claude")
    return _CANON_SKILLS[key]


# --------------------------------------------------------------------------
# The verb
# --------------------------------------------------------------------------


def _split(rest: List[str]) -> Tuple[Optional[str], Dict[str, bool], List[str]]:
    flags = {"confirm": False, "dry_run": False}
    feature: Optional[str] = None
    unknown: List[str] = []
    for arg in rest or []:
        if arg == "--confirm":
            flags["confirm"] = True
        elif arg in ("--dry-run", "-n"):
            flags["dry_run"] = True
        elif arg.startswith("-"):
            unknown.append(arg)
        elif feature is None:
            feature = arg
        else:
            unknown.append(arg)
    return (feature, flags, unknown)


def format_report(feature: str, report: Dict[str, Any], worktree: Path, cfg: config.Config) -> List[str]:
    out = ["refresh-pipeline %s" % (feature,), "  worktree  %s" % (worktree,)]
    out.append("  canonical %s" % (cfg.repo_root / ".claude",))
    out.append("")
    out.append("  %-14s %9s %9s %8s %8s %6s" % ("entry", "canonical", "worktree", "missing", "differs", "extra"))
    for entry in PIPELINE:
        row = report["entries"][entry]
        out.append(
            "  %-14s %9d %9d %8d %8d %6d"
            % (entry, row["canonical"], row["worktree"], len(row["missing"]), len(row["differs"]), len(row["extra"]))
        )
    for entry in PIPELINE:
        row = report["entries"][entry]
        for rel in row["missing"][:12]:
            out.append("  missing   %s" % (rel,))
        if len(row["missing"]) > 12:
            out.append("  missing   and %d more under %s" % (len(row["missing"]) - 12, entry))
        for rel in row["differs"][:12]:
            out.append("  differs   %s" % (rel,))
        if len(row["differs"]) > 12:
            out.append("  differs   and %d more under %s" % (len(row["differs"]) - 12, entry))
        for rel in row["extra"][:6]:
            out.append("  worktree-only %s (kept)" % (rel,))
    return out


def _copy_refusal(confirm: bool) -> Optional[str]:
    if not confirm:
        return "print mode. Pass --confirm, in a terminal, to copy the canonical tree in."
    for var in NON_INTERACTIVE_MARKERS:
        if os.environ.get(var):
            return "refused: refresh-pipeline never writes from the tick or a hook (%s is set)" % (var,)
    try:
        tty = sys.stdin.isatty()
    except Exception:
        tty = False
    if not tty:
        return (
            "refused: --confirm needs an interactive terminal. A background agent, a "
            "hook and the tick have none, and this verb writes inside a worktree."
        )
    return None


def _copy_in(canonical: Path, target: Path, report: Dict[str, Any]) -> List[str]:
    """Copy every missing or differing file in. Deletes nothing."""
    done: List[str] = []
    for rel in sorted(set(report["missing"]) | set(report["differs"])):
        src = canonical / rel
        dst = target / rel
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        done.append(rel)
    return done


def run_refresh(rest: List[str], ctx: Any) -> int:
    config.hostname_guard()
    cfg = ctx.config
    feature, flags, unknown = _split(rest)
    if unknown or not feature:
        _err("usage: factory refresh-pipeline <feature> [--dry-run] [--confirm]")
        return REFUSED
    config.validate_id(feature)
    if _is_campaign(ctx, feature, "refresh-pipeline"):
        return REFUSED
    card = ctx.card(feature)
    if card is None:
        _err("no card %r. Known: %s" % (feature, ", ".join(sorted(c.id for c in ctx.cards))))
        return MISSING
    if not card.worktree:
        _err("%s has no worktree: there is no pipeline to refresh" % (feature,))
        return MISSING
    worktree = Path(card.worktree)
    if not worktree.is_dir():
        _err("%s is registered but absent on disk" % (worktree,))
        return MISSING
    if cfg.is_foreign(worktree):
        _err(
            "refused: %s is outside %s. A legacy checkout is torn down, not "
            "refreshed: `%s teardown %s`" % (worktree, cfg.worktree_root, _factory(cfg), feature)
        )
        return REFUSED

    canonical = cfg.repo_root / ".claude"
    if not canonical.is_dir():
        _err("no canonical pipeline at %s" % (canonical,))
        return MISSING
    report = compare(canonical, worktree / ".claude")
    for line in format_report(feature, report, worktree, cfg):
        print(line)
    print("")
    if report["clean"]:
        print("the pipeline already matches the canonical tree. Nothing to copy.")
        return OK

    print("  # the recipe, if you would rather run it yourself")
    for entry in PIPELINE:
        row = report["entries"][entry]
        if row["missing"] or row["differs"]:
            print("  cp -R %s %s" % (canonical / entry, worktree / ".claude" / entry))
    print("")

    refusal = _copy_refusal(flags["confirm"])
    if refusal is not None:
        print(refusal)
        return OK if not flags["confirm"] else REFUSED
    if flags["dry_run"] or ctx.dry_run:
        print("dry run: %d files would be copied." % (len(set(report["missing"]) | set(report["differs"])),))
        return OK

    answer = ""
    try:
        answer = input("type the feature name to copy the canonical pipeline in: ").strip()
    except Exception:
        answer = ""
    if answer != feature:
        print("aborted: %r is not %r" % (answer, feature))
        return REFUSED
    done = _copy_in(canonical, worktree / ".claude", report)
    print("copied %d files into %s" % (len(done), worktree / ".claude"))
    if ctx.timeline is not None:
        ctx.timeline.append(
            feature,
            {
                "at": ctx.now,
                "event": "pipeline-refreshed",
                "files": len(done),
                "why": "canonical .claude copied into the worktree",
            },
        )
    return OK


# --------------------------------------------------------------------------
# Board hooks
# --------------------------------------------------------------------------


def card_flags(card: Any, obs: Dict[str, Any], ctx: Any) -> List[str]:
    """``stale-pipeline`` whenever the worktree cannot run the canonical skills."""
    if not card.worktree:
        return []
    skills = obs.get("skills")
    if not isinstance(skills, dict):
        return []
    names = skills.get("names") or []
    if skills.get("has_ship") is False:
        return ["stale-pipeline"]
    try:
        canon = canonical_skills(ctx.config)
    except Exception:
        return []
    if canon and set(canon) - set(names):
        return ["stale-pipeline"]
    return []


def _worktrees(ctx: Any) -> List[str]:
    """Worktree paths, from the probe round when there is one, else from git."""
    if ctx.obs:
        return sorted(
            str(c.get("worktree"))
            for c in ctx.obs.values()
            if c.get("worktree")
        )
    wts, _ok = probe.all_worktrees(ctx.config)
    return sorted(wts)


def doctor_checks(ctx: Any) -> List[Tuple[str, bool, str]]:
    cfg = ctx.config
    canonical = cfg.repo_root / ".claude"
    rows: List[Tuple[str, bool, str]] = []
    if not canonical.is_dir():
        return [("pipeline: canonical .claude exists", False, "no %s" % (canonical,))]

    differs: List[str] = []
    no_ship: List[str] = []
    for path in _worktrees(ctx):
        name = os.path.basename(str(path).rstrip("/"))
        wt_claude = Path(path) / ".claude"
        report = compare(canonical, wt_claude)
        if not report["clean"]:
            differs.append(
                "%s (%d missing, %d differing)" % (name, len(report["missing"]), len(report["differs"]))
            )
        if SHIP_SKILL not in skill_names(wt_claude):
            no_ship.append(name)
    rows.append(
        (
            "pipeline: every worktree matches the canonical .claude",
            not differs,
            "differs: %s. `%s refresh-pipeline <f>` copies it in."
            % ("; ".join(differs), _factory(cfg)),
        )
    )
    rows.append(
        (
            "pipeline: every worktree has %s" % (SHIP_SKILL,),
            not no_ship,
            "no %s in: %s. The board prints no ship command for those."
            % (SHIP_SKILL, ", ".join(no_ship)),
        )
    )
    return rows


VERBS = {"refresh-pipeline": run_refresh}

HELP = {"refresh-pipeline": "diff and, on confirmation, copy the canonical .claude into a worktree"}


def _is_campaign(ctx: Any, feature: str, verb: str) -> bool:
    """A campaign id is refused here with one sentence: this verb acts on a
    feature worktree, and a campaign lives in its project repository."""
    try:
        from . import ext_campaigns
    except Exception:
        return False
    return ext_campaigns.refuse(ctx, feature, verb)
