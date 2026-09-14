"""Artifact durability, plus the three sections that are not a feature row.

Four jobs, one file:

1. ``collect`` rescues what dies with a worktree or with a reboot:

   - every ``<worktree>/.claude/cache/moose-build-*.json``, because that cache
     is gitignored and disappears with the worktree;
   - exactly ``/tmp/moose-review-<feature>.md``, and only when
     ``/tmp/moose-review-<feature>-meta.json`` exists and its ``root``
     resolves under that feature's worktree. ``/tmp`` is purged at boot.

   The copies land in ``<vault>/Artifacts/<feature>/``, which is an input
   directory: nothing else in the package may write there, and this module
   writes nowhere else. A rescue is idempotent (identical bytes are never
   copied twice) and it never overwrites a differing existing copy: that copy
   gets a numbered suffix, ``build-<label>-2.json``, so a rewritten record
   cannot erase the one that is already archived.

2. ``note_sections`` renders "Build and review" on the feature note: every
   rescued copy as a normal wiki link, and the excerpt read from the copy once
   the original is gone.

3. ``home_sections`` renders "Elsewhere" (review artifacts in /tmp that no card
   owns, and any running MooseDocs preview server) and "Since yesterday" (the
   timeline of the last 24 hours, across features).

4. ``collect`` also raises the ageing heads-up: one at 14 days of quiet and one
   more at 45, recorded once through ``ctx.state`` so it never repeats. Quiet is
   not a problem; a forgotten card is.

Two deliberate conventions inherited from core: no generated line prints an age
in days (it prints the date), and nothing here reads the clock except the
24-hour window, which is measured against ``ctx.now``.

``$FACTORY_TMP_DIR`` relocates the ``/tmp`` scan. It exists for the tests; it
is not a production knob.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config, derive, probe

# Order of the sections this module contributes, among the extensions.
ORDER_BUILD_REVIEW = 50
ORDER_ELSEWHERE = 60
ORDER_SINCE = 70

# A build record is a few kB. Anything this large is not one, and copying it
# into a git repo on every board run would be the wrong kind of durable.
MAX_RESCUE_BYTES = 4_000_000
MAX_COPIES = 99                 # build-<label>-2.json ... -99.json
EXCERPT_LINES = 3
EXCERPT_WIDTH = 160
SINCE_WINDOW_SECONDS = 24 * 3600
SINCE_CAP = 12
BUILDS_ON_NOTE = 6
REVIEWS_ON_NOTE = 6
UNFILED_ON_HOME = 8

# The pattern docs.sh launches: `./moosedocs.py build --serve --port <PORT>`,
# recorded in /tmp/moose-docs-<tag>-serve.pid. The probe is one pgrep and a
# directory listing; it never starts, stops or signals anything.
DOCS_PATTERN = "moosedocs.py build --serve"
DOCS_PID_GLOB = "moose-docs-*-serve.pid"

REVIEW_PREFIX = "moose-review-"
BUILD_PREFIX = "moose-build-"

# The per-file suffixes /moose-pr-review writes beside one review label. They
# are stripped to group a /tmp family, never to guess at a feature name.
ROLE_SUFFIXES = (
    "-issues",
    "-meta",
    "-newobj",
    "-code",
    "-test",
    "-doc",
    "-dry",
    "-ad",
)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def tmp_dir() -> Path:
    return Path(os.environ.get("FACTORY_TMP_DIR") or "/tmp")


def _under(path: Path, parent: Path) -> bool:
    """True when ``path`` is at or under ``parent``, symlinks resolved.

    ``os.path.realpath`` and not ``Path.resolve`` because the destination does
    not exist yet, and /var against /private/var must compare equal on macOS.
    """
    try:
        Path(os.path.realpath(str(path))).relative_to(
            Path(os.path.realpath(str(parent)))
        )
        return True
    except Exception:
        return False


def _guard(ctx: Any, dest: Path) -> None:
    """This module writes under Artifacts/ and nowhere else."""
    if not _under(dest, ctx.config.artifacts_dir):
        raise config.RefusedWrite(
            "refused: %s is outside %s, which is the only place this extension writes"
            % (dest, ctx.config.artifacts_dir)
        )


def _same_bytes(a: Path, b: Path) -> bool:
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        return a.read_bytes() == b.read_bytes()
    except Exception:
        return False


def _numbered(dest: Path) -> List[Path]:
    stem, suffix = dest.stem, dest.suffix
    return [
        dest.with_name("%s-%d%s" % (stem, n, suffix))
        for n in range(2, MAX_COPIES + 1)
    ]


def rescue(ctx: Any, src: Path, dest: Path) -> Tuple[str, Optional[Path]]:
    """Copy ``src`` to ``dest``, idempotently and without ever overwriting.

    Returns one of ``same``, ``copied``, ``suffixed``, ``dry-run``,
    ``too-large``, ``failed``, with the path that now holds those bytes.
    """
    _guard(ctx, dest)
    try:
        size = src.stat().st_size
    except Exception:
        return ("failed", None)
    if size > MAX_RESCUE_BYTES:
        return ("too-large", None)

    status = "copied"
    if dest.exists():
        if _same_bytes(src, dest):
            return ("same", dest)
        target = None
        for cand in _numbered(dest):
            if not cand.exists():
                target = cand
                break
            if _same_bytes(src, cand):
                return ("same", cand)
        if target is None:
            return ("failed", None)
        dest, status = target, "suffixed"

    if ctx.dry_run:
        return ("dry-run", dest)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        # copy2 keeps the mtime, which is what makes the rescue idempotent for
        # every other reader of the copy, core's build_record included.
        shutil.copy2(src, dest)
    except Exception as exc:
        ctx.log("artifacts: copy %s -> %s failed: %s" % (src, dest, exc))
        return ("failed", None)
    return (status, dest)


def _label_of(name: str) -> str:
    """``moose-build-2026-09-12.json`` and ``build-2026-09-12.json`` both give
    ``2026-09-12``."""
    for prefix in (BUILD_PREFIX, "build-"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name[:-5] if name.endswith(".json") else name


def _wiki(ctx: Any, path: Path, label: Optional[str] = None) -> str:
    """A normal wiki link, by vault-relative path so two features can archive
    the same basename without colliding."""
    try:
        rel = Path(path).relative_to(ctx.config.vault).as_posix()
    except Exception:
        rel = Path(path).name
    return "[[%s|%s]]" % (rel, label or Path(path).stem)


def _excerpt(path: Path) -> List[str]:
    text, ok = probe._read_text(path, limit=200_000)
    if not ok or not text:
        return []
    out: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("---") or line.startswith("#"):
            continue
        out.append(line[:EXCERPT_WIDTH])
        if len(out) >= EXCERPT_LINES:
            break
    return out


# --------------------------------------------------------------------------
# 1. collect: the rescue
# --------------------------------------------------------------------------


def collect(ctx: Any) -> None:
    """Runs in the probe round, before derive. Writes only under Artifacts/."""
    tmp = tmp_dir()
    table: Dict[str, Dict[str, Any]] = {}
    for feature in sorted(ctx.obs):
        obs = ctx.obs[feature] or {}
        try:
            rec = _collect_one(ctx, feature, obs, tmp)
        except Exception as exc:
            ctx.log("artifacts: %s rescue failed: %s" % (feature, exc))
            continue
        table[feature] = rec
        obs["artifacts"] = rec
        if rec["reviews"]:
            # core captured the list before this rescue ran; refresh it so the
            # note and the board agree on this run, not on the next one.
            obs["reviews"] = list(rec["reviews"])
    ctx.meta["artifacts"] = table
    ctx.meta["artifacts_unfiled"] = unfiled(ctx, tmp, table)
    # This extension owns the Elsewhere section, so core's narrower list is
    # taken off the board to keep one heading. The core line is kept under a
    # second key for `dump-obs` and for doctor.
    core_unfiled = ctx.meta.pop("unfiled_reviews", None)
    if core_unfiled is not None:
        ctx.meta["unfiled_reviews_core"] = core_unfiled
    ctx.meta["docs_servers"] = docs_servers()
    ctx.meta["heads_up"] = heads_up(ctx)


def _collect_one(
    ctx: Any, feature: str, obs: Dict[str, Any], tmp: Path
) -> Dict[str, Any]:
    config.validate_id(feature)
    dest_dir = ctx.config.artifacts_dir / feature
    worktree = obs.get("worktree")
    rec: Dict[str, Any] = {
        "dir": str(dest_dir),
        "builds": [],
        "reviews": [],
        "review_detail": [],
        "review_skipped": None,
        "review_filed": False,
        "rescued": [],
    }

    # --- build records -----------------------------------------------------
    live_names: Dict[str, Path] = {}
    if worktree:
        cache = Path(worktree) / ".claude" / "cache"
        if cache.is_dir():
            for src in sorted(cache.glob(BUILD_PREFIX + "*.json")):
                label = _label_of(src.name)
                dest = dest_dir / ("build-%s.json" % (label,))
                status, path = rescue(ctx, src, dest)
                # Key on the copy that actually holds these bytes: a suffixed
                # rescue means the canonical name holds an older record whose
                # original is gone.
                live_names[Path(path).name if path else dest.name] = src
                if status in ("copied", "suffixed"):
                    rec["rescued"].append({"kind": "build", "status": status,
                                           "name": Path(path).name})
                elif status in ("too-large", "failed"):
                    ctx.log(
                        "artifacts: %s build record %s not rescued (%s)"
                        % (feature, src.name, status)
                    )

    for path in sorted(dest_dir.glob("build-*.json")) if dest_dir.is_dir() else []:
        data, ok = probe._read_json(path)
        mt, _ = probe._mtime(path)
        rec["builds"].append(
            {
                "name": path.name,
                "label": _label_of(path.name),
                "status": ((data or {}).get("status") if ok else None) or "unreadable",
                "runId": (data or {}).get("runId") if ok else None,
                "day": probe.day(mt) if mt else "unknown",
                "mtime": mt,
                "original": str(live_names[path.name]) if path.name in live_names else None,
            }
        )
    rec["builds"].sort(key=lambda b: (b.get("mtime") or 0, b["name"]), reverse=True)

    # --- the one review, verified through its meta file --------------------
    src = tmp / (REVIEW_PREFIX + feature + ".md")
    meta = tmp / (REVIEW_PREFIX + feature + "-meta.json")
    rec["review_source"] = str(src)
    if src.is_file():
        why = _review_refusal(src, meta, worktree)
        rec["review_skipped"] = why
        if why is None:
            mt, _ = probe._mtime(src)
            dest = dest_dir / ("review-%s.md" % (probe.day(mt),))
            status, path = rescue(ctx, src, dest)
            if status in ("copied", "suffixed"):
                rec["rescued"].append({"kind": "review", "status": status,
                                       "name": Path(path).name})
            elif status in ("too-large", "failed"):
                rec["review_skipped"] = "the copy failed (%s)" % (status,)
        rec["review_filed"] = rec["review_skipped"] is None

    for path in sorted(dest_dir.glob("review-*.md")) if dest_dir.is_dir() else []:
        mt, _ = probe._mtime(path)
        original = src if (src.is_file() and rec["review_skipped"] is None) else None
        rec["reviews"].append(path.name)
        rec["review_detail"].append(
            {
                "name": path.name,
                "day": probe.day(mt) if mt else "unknown",
                "mtime": mt,
                "original": str(original) if original else None,
                "excerpt": _excerpt(original or path),
                "read_from": "the original in /tmp" if original else "the rescued copy",
            }
        )
    rec["review_detail"].sort(key=lambda r: (r.get("mtime") or 0, r["name"]), reverse=True)
    return rec


def _review_refusal(src: Path, meta: Path, worktree: Optional[str]) -> Optional[str]:
    """``None`` when the review may be rescued, else the reason it may not.

    Never glob ``/tmp/moose-review-*``: that namespace is shared with
    ``/moose-pr-review``, one of whose roots is outside every worktree.
    """
    if not meta.is_file():
        return "no `%s` beside it, so its root is unverifiable" % (meta.name,)
    data, ok = probe._read_json(meta)
    if not ok or not isinstance(data, dict):
        return "`%s` does not parse" % (meta.name,)
    root = data.get("root")
    if not root:
        return "`%s` names no root" % (meta.name,)
    if not worktree:
        return "this card has no worktree, so no root can be under it"
    if not _under(Path(str(root)), Path(worktree)):
        return "its root `%s` is not under the worktree" % (root,)
    return None


# --------------------------------------------------------------------------
# Elsewhere: review artifacts no card owns, and docs servers
# --------------------------------------------------------------------------


def _raw_label(name: str) -> str:
    return name[len(REVIEW_PREFIX):].split(".", 1)[0]


def _family(label: str, known: Any) -> str:
    """``fc-syn-ad`` belongs to the family ``fc-syn``; ``fc-test`` is its own.

    ``/moose-pr-review`` writes one label plus a bucket suffix per file, and the
    suffix vocabulary overlaps real labels: ``fc-test.files`` is the file list of
    the label ``fc-test``, while ``fc-test-test.files`` is that label's test
    bucket. A suffix is therefore stripped only when what remains is itself a
    label that exists, either in ``/tmp`` or on the board. Grouping is what makes
    three families read as three artifacts instead of thirty files.
    """
    for suffix in ROLE_SUFFIXES:
        if label.endswith(suffix) and len(label) > len(suffix):
            base = label[: -len(suffix)]
            if base in known:
                return base
    return label


def unfiled(ctx: Any, tmp: Path, table: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every ``/tmp/moose-review-*`` family that is not a rescued feature review.

    Three kinds: a label that matches no card (today `fc-syn`, `fc-test` and
    `pr-5`, one of them rooted at `/tmp/fable-cleanup/snap2`), a feature review
    that failed the root check, and an ``-issues`` digest, which is a
    linked-issue list and not a review at all. Listed, never read, never moved.
    """
    rows: List[Dict[str, Any]] = []
    try:
        found = sorted(p for p in tmp.glob(REVIEW_PREFIX + "*") if p.is_file())
    except Exception:
        ctx.log("artifacts: cannot list %s" % (tmp,))
        return rows
    raw = {_raw_label(p.name) for p in found}
    known = {label for label in raw if label} | set(table)
    families: Dict[str, List[Path]] = {}
    for path in found:
        label = _family(_raw_label(path.name), known)
        if label:
            families.setdefault(label, []).append(path)
    for label in sorted(families):
        paths = families[label]
        kinds = sorted({p.suffix.lstrip(".") or "none" for p in paths})
        rec = table.get(label)
        if rec is not None:
            if rec.get("review_filed"):
                continue                      # rescued, so it is filed
            why = rec.get("review_skipped")
            if not why:
                why = (
                    "named after [[%s]], but no `%s%s.md` is here to rescue "
                    "(%d file%s: %s)"
                    % (
                        label,
                        REVIEW_PREFIX,
                        label,
                        len(paths),
                        "" if len(paths) == 1 else "s",
                        ", ".join(kinds),
                    )
                )
            rows.append({"label": label, "files": len(paths), "why": why})
            continue
        rows.append(
            {
                "label": label,
                "files": len(paths),
                "why": "matches no card (%d file%s: %s)"
                % (len(paths), "" if len(paths) == 1 else "s", ", ".join(kinds)),
            }
        )
    return rows


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _pgrep(pattern: str) -> Tuple[List[Tuple[int, str]], bool]:
    """``pgrep -fl`` rows. rc 1 means no match, which is a fact, not unknown."""
    try:
        p = subprocess.run(
            ["pgrep", "-fl", pattern],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return ([], False)
    if p.returncode not in (0, 1):
        return ([], False)
    rows: List[Tuple[int, str]] = []
    for line in (p.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        head, _, rest = line.partition(" ")
        try:
            rows.append((int(head), rest))
        except ValueError:
            continue
    return (rows, True)


def docs_servers(tmp: Optional[Path] = None) -> Dict[str, Any]:
    """Running MooseDocs preview servers. One pgrep and one listing, read-only.

    ``docs.sh`` records ``/tmp/moose-docs-<tag>-serve.pid``, which is how a pid
    gets a scope name. A pid file whose process is gone is stale, and saying so
    is cheaper than letting Max wonder which port is live.
    """
    tmp = tmp or tmp_dir()
    rows, ok = _pgrep(DOCS_PATTERN)
    by_pid: Dict[int, str] = {}
    stale: List[str] = []
    try:
        pid_files = sorted(tmp.glob(DOCS_PID_GLOB))
    except Exception:
        pid_files = []
    for path in pid_files:
        tag = path.name[len("moose-docs-"):-len("-serve.pid")]
        text, tok = probe._read_text(path, limit=64)
        pid = None
        if tok and text:
            try:
                pid = int(text.strip())
            except ValueError:
                pid = None
        if pid is None:
            continue
        if _alive(pid):
            by_pid[pid] = tag
        else:
            stale.append(tag)
    cmds = dict(rows)
    # One server is one (scope, port): MooseDocs --serve runs a reloader child
    # with the same command line, and two rows for one preview is a lie.
    groups: Dict[Tuple[str, Optional[int]], Dict[str, Any]] = {}
    for pid in sorted(set(cmds) | set(by_pid)):
        cmd = cmds.get(pid) or ""
        port = None
        m = re.search(r"--port\s+(\d{2,5})", cmd)
        if m:
            port = int(m.group(1))
        tag = by_pid.get(pid) or _docs_scope(cmd)
        key = (tag, port)
        rec = groups.get(key)
        if rec is None:
            rec = {
                "scope": tag,
                "port": port,
                "pids": [],
                "log": str(tmp / ("moose-docs-%s-serve.log" % (tag,)))
                if pid in by_pid
                else None,
                "seen": "pid file" if pid in by_pid else "pgrep",
            }
            groups[key] = rec
        rec["pids"].append(pid)
    servers = [groups[k] for k in sorted(groups, key=lambda k: (k[0], k[1] or 0))]
    for rec in servers:
        rec["pid"] = rec["pids"][0]
    return {"ok": ok, "servers": servers, "stale_pid_files": sorted(stale)}


def _docs_scope(cmd: str) -> str:
    """The docs.sh scope a running server belongs to, from its command line.

    A server started by hand has no pid file, so the path to ``moosedocs.py`` is
    the only name available: ``.../moose/modules/doc`` is ``moose``,
    ``.../moose/modules/<m>/doc`` is that module, and ``.../<app>/doc`` is the
    app.
    """
    m = re.search(r"(\S+)/moosedocs\.py", cmd or "")
    if not m:
        return "unknown"
    doc_dir = m.group(1)
    parts = [p for p in doc_dir.split("/") if p]
    if parts and parts[-1] == "doc":
        parts = parts[:-1]
    if len(parts) >= 2 and parts[-2] == "modules":
        return "moose/modules/" + parts[-1]
    if parts and parts[-1] == "modules":
        return "moose"
    return parts[-1] if parts else "unknown"


# --------------------------------------------------------------------------
# The ageing heads-up
# --------------------------------------------------------------------------


def heads_up(ctx: Any) -> List[Dict[str, Any]]:
    """One heads-up at 14 days of quiet and one more at 45, recorded once.

    Quiet means: nothing datable has moved, no live session, and no pull request
    of any state. A card with a merged or closed PR is teardown work, which the
    board already raises as needs-you, so a heads-up there would only repeat it.
    The record lives in ``factory/state/<feature>.json`` through ``ctx.state``,
    so a heads-up never repeats, and core's own parked-card nag reads the same
    key and therefore cannot double-raise it.
    """
    now_ts = derive.ts_of(ctx.now) or time.time()
    raised: List[Dict[str, Any]] = []
    for feature in sorted(ctx.obs):
        obs = ctx.obs[feature] or {}
        if obs.get("sessions"):
            continue
        if obs.get("prs"):
            continue
        silent = derive.silent_days(obs, now_ts)
        if silent is None:
            continue
        due = [
            d
            for d in sorted(ctx.config.nag_days)
            if ctx.state.heads_up_due(feature, d, silent)
        ]
        if not due:
            continue
        top = due[-1]
        ctx.timeline.append(
            feature,
            {
                "at": ctx.now,
                "event": "heads-up",
                "days": top,
                "why": "quiet for %d days, and quiet is not a problem" % (silent,),
            },
        )
        for days in due:
            ctx.state.heads_up_record(feature, days, ctx.now, ctx.dry_run)
        raised.append({"feature": feature, "days": top, "silent": silent})
    return raised


# --------------------------------------------------------------------------
# 2. The note section
# --------------------------------------------------------------------------


def _table_for(card: Any, ctx: Any) -> Dict[str, Any]:
    """The collect record, or a listing of what is on disk when collect did not
    run (``factory status`` renders without a probe round)."""
    rec = (ctx.obs.get(card.id) or {}).get("artifacts")
    if isinstance(rec, dict):
        return rec
    table = (ctx.meta.get("artifacts") or {}).get(card.id)
    if isinstance(table, dict):
        return table
    dest_dir = ctx.config.artifacts_dir / card.id
    builds, reviews = [], []
    if dest_dir.is_dir():
        for path in sorted(dest_dir.glob("build-*.json")):
            mt, _ = probe._mtime(path)
            builds.append(
                {
                    "name": path.name,
                    "label": _label_of(path.name),
                    "status": "unknown",
                    "day": probe.day(mt) if mt else "unknown",
                    "mtime": mt,
                    "original": None,
                }
            )
        for path in sorted(dest_dir.glob("review-*.md")):
            mt, _ = probe._mtime(path)
            reviews.append(
                {
                    "name": path.name,
                    "day": probe.day(mt) if mt else "unknown",
                    "mtime": mt,
                    "original": None,
                    "excerpt": [],
                    "read_from": "the rescued copy",
                }
            )
    return {
        "dir": str(dest_dir),
        "builds": builds,
        "reviews": [r["name"] for r in reviews],
        "review_detail": reviews,
        "review_skipped": None,
        "rescued": [],
    }


def note_sections(card: Any, ctx: Any) -> List[Tuple[str, str, int]]:
    rec = _table_for(card, ctx)
    dest_dir = ctx.config.artifacts_dir / card.id
    out: List[str] = []

    builds = rec.get("builds") or []
    out.append("### Builds rescued (%d)" % (len(builds),))
    out.append("")
    if builds:
        for b in builds[:BUILDS_ON_NOTE]:
            out.append(
                "- %s - **%s**, %s - %s"
                % (
                    _wiki(ctx, dest_dir / b["name"], b["name"]),
                    b.get("status") or "unknown",
                    b.get("day") or "unknown",
                    "the original is still in the worktree"
                    if b.get("original")
                    else "the original is gone; this copy is the record",
                )
            )
        if len(builds) > BUILDS_ON_NOTE:
            out.append("- and %d older, in `%s`" % (len(builds) - BUILDS_ON_NOTE,
                                                    _tilde(dest_dir)))
    else:
        out.append(
            "_No `/moose-build` record. The cache at `.claude/cache/` is "
            "gitignored and dies with the worktree, so a run here is what makes "
            "one durable._"
        )
    out.append("")

    details = rec.get("review_detail") or []
    out.append("### Reviews rescued (%d)" % (len(details),))
    out.append("")
    if details:
        for r in details[:REVIEWS_ON_NOTE]:
            out.append(
                "- %s - %s, read from %s"
                % (
                    _wiki(ctx, dest_dir / r["name"], r["name"][: -len(".md")]),
                    r.get("day") or "unknown",
                    r.get("read_from") or "the rescued copy",
                )
            )
            for line in (r.get("excerpt") or [])[:EXCERPT_LINES]:
                out.append("  > %s" % (line,))
        if len(details) > REVIEWS_ON_NOTE:
            out.append("- and %d older, in `%s`" % (len(details) - REVIEWS_ON_NOTE,
                                                    _tilde(dest_dir)))
    else:
        out.append("_No clean-context review archived._")
    skipped = rec.get("review_skipped")
    if skipped:
        out.append("")
        out.append(
            "`%s` exists and was **not** rescued: %s."
            % (_tilde(rec.get("review_source") or ""), skipped)
        )
    out.append("")
    out.append(
        "_Rescued copies live in `%s`, which is an input: the board reads them "
        "and never rewrites them._" % (_tilde(dest_dir),)
    )
    return [("Build and review", "\n".join(out), ORDER_BUILD_REVIEW)]


def _tilde(path: Any) -> str:
    home = str(Path.home())
    text = str(path)
    return "~" + text[len(home):] if text.startswith(home) else text


# --------------------------------------------------------------------------
# 3. The home sections
# --------------------------------------------------------------------------


def _elsewhere(ctx: Any) -> str:
    rows = ctx.meta.get("artifacts_unfiled")
    if rows is None:
        rows = unfiled(ctx, tmp_dir(), ctx.meta.get("artifacts") or {})
    out: List[str] = []
    if rows:
        shown = rows[:UNFILED_ON_HOME]
        out.append(
            "- %d unfiled review artifact%s in `%s`. `/moose-pr-review` writes that "
            "namespace too, so %s on this board."
            % (
                len(rows),
                "" if len(rows) == 1 else "s",
                _tilde(tmp_dir()),
                "this one is not a card" if len(rows) == 1 else "these are not cards",
            )
        )
        for row in shown:
            out.append("    - `%s` - %s" % (row["label"], row["why"]))
        if len(rows) > len(shown):
            out.append("    - and %d more" % (len(rows) - len(shown),))
    else:
        out.append("- 0 unfiled review artifacts in `%s`." % (_tilde(tmp_dir()),))

    docs = ctx.meta.get("docs_servers")
    if docs is None:
        docs = docs_servers()
    if not docs.get("ok"):
        out.append("- Docs servers: **unknown** (`pgrep` did not answer).")
    else:
        servers = docs.get("servers") or []
        if servers:
            out.append("- %d docs server%s running:" % (len(servers),
                                                        "" if len(servers) == 1 else "s"))
            # No pid here. A pid is wall-clock truth in a generated file: it
            # moves on every restart, so Home.md stopped rebuilding to the same
            # bytes and the tick committed on nearly every run. Scope and port
            # identify the server; `factory doctor` and docs.sh know the pid.
            for s in servers:
                out.append(
                    "    - `%s`%s%s"
                    % (
                        s.get("scope"),
                        (" at http://localhost:%d" % (s["port"],)) if s.get("port") else "",
                        (" - log `%s`" % (_tilde(s["log"]),)) if s.get("log") else "",
                    )
                )
        else:
            out.append("- 0 docs servers running.")
        if docs.get("stale_pid_files"):
            out.append(
                "    - stale pid file%s: %s. `docs.sh <scope> stop` clears one."
                % (
                    "" if len(docs["stale_pid_files"]) == 1 else "s",
                    ", ".join("`%s`" % (t,) for t in docs["stale_pid_files"]),
                )
            )
    return "\n".join(out)


def _since_yesterday(ctx: Any) -> str:
    if ctx.timeline is None:
        return "_No timeline._"
    now_ts = derive.ts_of(ctx.now) or time.time()
    floor = now_ts - SINCE_WINDOW_SECONDS
    rows: List[Tuple[float, str, Dict[str, Any]]] = []
    for feature in ctx.timeline.all_features():
        for rec in ctx.timeline.read(feature):
            ts = derive.ts_of(str(rec.get("at") or ""))
            if ts is None or ts < floor:
                continue
            rows.append((ts, feature, rec))
    rows.sort(key=lambda r: (r[0], r[1], str(r[2].get("event") or "")))
    out: List[str] = []
    if not rows:
        return "_Nothing happened in the last day._"
    shown = rows[-SINCE_CAP:]
    for ts, feature, rec in shown:
        why = rec.get("why") or rec.get("gate") or rec.get("cause") or ""
        out.append(
            "- %s [[%s]] %s%s"
            % (
                str(rec.get("at") or "")[:16].replace("T", " "),
                feature,
                str(rec.get("event") or ""),
                (" - " + str(why).replace("\n", " ")) if why else "",
            )
        )
    # The cap note goes last: the newest events are what a reader came for, and
    # a leading note about what is missing reads like the section is empty.
    if len(rows) > len(shown):
        out.append("")
        out.append(
            "_%d earlier events in the window are not shown._" % (len(rows) - len(shown),)
        )
    return "\n".join(out)


def home_sections(ctx: Any) -> List[Tuple[str, str, int]]:
    return [
        ("Elsewhere", _elsewhere(ctx), ORDER_ELSEWHERE),
        ("Since yesterday", _since_yesterday(ctx), ORDER_SINCE),
    ]


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------


def doctor_checks(ctx: Any) -> List[Tuple[str, bool, str]]:
    cfg = ctx.config
    out: List[Tuple[str, bool, str]] = []
    art = cfg.artifacts_dir
    out.append(
        (
            "artifacts dir writable",
            art.is_dir() and os.access(str(art), os.W_OK),
            "mkdir -p %s" % (_tilde(art),),
        )
    )
    tmp = tmp_dir()
    out.append(
        (
            "review namespace readable",
            tmp.is_dir() and os.access(str(tmp), os.R_OK),
            "%s is not readable, so unfiled reviews cannot be listed" % (_tilde(tmp),),
        )
    )
    crowded = []
    if art.is_dir():
        for path in sorted(art.glob("*/*-%d.*" % (MAX_COPIES,))):
            crowded.append(path.name)
    out.append(
        (
            "no rescue ran out of suffixes",
            not crowded,
            "these reached -%d: %s. Prune the directory." % (MAX_COPIES, ", ".join(crowded)),
        )
    )
    return out
