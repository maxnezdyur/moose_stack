"""Dispatch: the filesystem lease and the six session verbs.

Two builds on one workspace is the single destructive failure in the design.
They fight over ``specs/blueprint.md``, one conda env, one ``combined-opt`` tree
and one git index per submodule. The guard is a lease that is filesystem truth,
so it survives the background service being down:

    <worktree>/.factory-lease/            created by one atomic os.mkdir
    <worktree>/.factory-lease/lease.json  {bg_id, session_id, pid, host, acquired}

A lease whose owner process is gone is **reported** as ``lease-stale`` and never
stolen. Auto-stealing is how two builders end up in one tree. Only
``factory release`` removes one, interactively, after proving the owner is gone.

Verbs, all of them through ``VERBS``:

    start <f>     the plan's ten steps: lease, four refusals, three caps, launch,
                  short-id capture confirmed against the session files, registry,
                  timeline, board
    stop <f>      claude stop <bg_id>, then release the lease. --resume still works.
    attach <f>    print the attach command plus the session's state, detail and needs
    logs <f>      claude logs <bg_id>. Needs a live background service.
    release <f>   remove a stale lease. Interactive only, and never when the owner lives.
    reset <f>     print the diff that sets blueprint.md back to approved and every
                  running unit back to idle, release the lease, log the reason.
                  Interactive only, because it writes a file Max owns.

Nothing here ever calls ``claude rm``: that removes a worktree.

Two seams exist for the tests, and for rehearsing a launch outside the real
worktrees. Both are opt-in and neither changes the shipped behaviour:

    --root PATH                 treat PATH/<feature> as the worktree
    $FACTORY_CLAUDE_BIN         the binary ``start``, ``stop`` and ``logs`` run
    ctx.meta["sessions_all"]    the session rows, instead of one more probe

Exit codes: 0 ok, 1 a human should look, 2 a refused dispatch, 3 a missing path
or the wrong host.
"""

from __future__ import annotations

import argparse
import calendar
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config, derive, probe, render
from .model import APPROVED, FeatureCard, rank

OK, LOOK, REFUSED, MISSING = 0, 1, 2, 3

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

LEASE_DIR = ".factory-lease"
LEASE_FILE = "lease.json"
DEFAULT_PROMPT = "/moose-build"

LAUNCH_TIMEOUT = 180          # seconds: `claude --bg` prints and returns at once
STOP_TIMEOUT = 60
LOGS_TIMEOUT = 60
CONFIRM_SECONDS = 10.0        # wait this long for the session files to show the id
CONFIRM_POLL = 0.5

# A lease with no live session in its tree that is older than this reads as
# stale. It is still only a flag: nothing steals it.
LEASE_ORPHAN_SECONDS = 24 * 3600

DEAD_STATES = ("done", "stopped", "failed", "cancelled", "canceled", "error", "finished")

SHORT_ID = re.compile(r"\b([0-9a-f]{8})\b")

VERSION = "1.0.0"


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def out(msg: str = "") -> None:
    print(msg)


def err(msg: str) -> None:
    print(msg, file=sys.stderr)


def claude_bin(cfg: Any = None) -> Path:
    """Absolute path, always. The shell alias adds --dangerously-skip-permissions.

    Resolved like every other machine-specific path: ``$FACTORY_CLAUDE_BIN``,
    then ``claude_bin`` in the config file, then ``~/.local/bin/claude``.

    Takes the value off the :class:`~tool.config.Config` it is rendering for
    when one is in hand, like every other renderer, instead of re-reading the
    process-global config: a test that builds a Config by hand then gets the
    binary it asked for.
    """
    path = getattr(cfg, "claude_bin", None) if cfg is not None else None
    return Path(path) if path else Path(config.settings()["claude_bin"])


def launcher(cfg: config.Config) -> Path:
    return cfg.repo_root / "factory" / "factory"


def _run(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 60) -> Tuple[str, str, int]:
    """``(stdout, stderr, rc)``. rc 127 means the command could not run at all."""
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return ("", "%s: not found" % (cmd[0],), 127)
    except subprocess.TimeoutExpired:
        return ("", "%s: timed out after %ds" % (cmd[0], timeout), 124)
    except Exception as exc:
        return ("", "%s: %s" % (cmd[0], exc), 127)
    return (p.stdout or "", p.stderr or "", p.returncode)


def _ts(stamp: Any) -> Optional[float]:
    if isinstance(stamp, (int, float)) and stamp:
        return float(stamp)
    return derive.ts_of(str(stamp or "")) if stamp else None


def _pid_alive(pid: Any) -> Optional[bool]:
    """``True``, ``False``, or ``None`` for unknown. Unknown never demotes."""
    if not isinstance(pid, int):
        return None
    lstart, ok = probe._ps_lstart(pid)
    if not ok:
        return None
    return bool(lstart)


_LSTART = "%a %b %d %H:%M:%S %Y"


def _epochs(stamp: Any) -> Tuple[float, ...]:
    """Both readings of a ``ps -o lstart=`` shaped stamp: local, then UTC."""
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


def same_process(proc_start: Any, lstart: Any, tolerance: float = 2.0) -> Optional[bool]:
    """Is this pid still the process the session file describes?

    ``True``, ``False``, or ``None`` when the two stamps cannot be compared.

    Measured on this machine: for one live session the file recorded
    ``procStart`` 22:09 while ``ps -o lstart=`` printed 18:09, and for a
    background session launched at 22:24 local the file recorded 02:24 the next
    day. The file is UTC and ``ps`` is local, so a plain string comparison reads
    every session as pid reuse and drops it. Compare epochs under both readings
    instead, which is correct whatever the zone.
    """
    a, b = _epochs(proc_start), _epochs(lstart)
    if not a or not b:
        return None
    return any(abs(x - y) <= tolerance for x in a for y in b)


# --------------------------------------------------------------------------
# Interactive confirmation. `release` and `reset` are interactive only.
# --------------------------------------------------------------------------

_ASK: Optional[Any] = None        # tests install a callable here


def _isatty() -> bool:
    try:
        return bool(sys.stdin.isatty())
    except Exception:
        return False


def _confirm(question: str, assume_yes: bool = False) -> Tuple[bool, str]:
    """``(agreed, why_not)``. No terminal means no, whatever --yes says."""
    ask = _ASK
    if ask is not None:
        return (bool(ask(question)), "")
    if not _isatty():
        return (
            False,
            "interactive only: run it in a terminal. Nothing was changed.",
        )
    if assume_yes:
        return (True, "")
    try:
        answer = input(question + " [y/N] ")
    except EOFError:
        return (False, "no answer")
    return (answer.strip().lower() in ("y", "yes"), "answered no")


# --------------------------------------------------------------------------
# The lease
# --------------------------------------------------------------------------


class LeaseHeld(RuntimeError):
    """Somebody else holds the lease. Never stolen, only reported."""

    def __init__(self, record: Dict[str, Any], path: Path):
        self.record = record or {}
        self.path = path
        RuntimeError.__init__(self, "lease held: %s" % (path,))


def lease_path(worktree: Any) -> Path:
    return Path(worktree) / LEASE_DIR


def read_lease(worktree: Any) -> Optional[Dict[str, Any]]:
    """The lease record with ``held`` and ``owner_alive``, or None.

    Same shape ``probe.lease`` produces, so the flag rules read one dict
    whether they run from the board's snapshot or from a verb.
    """
    d = lease_path(worktree)
    if not d.exists():
        return None
    data, ok = probe._read_json(d / LEASE_FILE) if d.is_dir() else probe._read_json(d)
    rec = dict(data) if (ok and isinstance(data, dict)) else {}
    rec["held"] = True
    rec["owner_alive"] = _pid_alive(rec.get("pid"))
    rec["unreadable"] = not ok
    return rec


def _write_lease(d: Path, record: Dict[str, Any]) -> None:
    path = d / LEASE_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=1, sort_keys=True))
    os.replace(tmp, path)


def acquire(
    worktree: Any,
    feature: str,
    prompt: str,
    now: str,
    pid: Optional[int] = None,
) -> Dict[str, Any]:
    """One atomic ``os.mkdir``. Raises ``LeaseHeld`` when it already exists.

    ``pid`` starts as this process, because the background session does not
    exist yet. ``confirm_lease`` rewrites it with the session's own pid, so
    staleness is decided by the thing that actually occupies the tree.
    """
    w = Path(worktree)
    if not w.is_dir():
        raise config.MissingPath("no worktree at %s" % (w,))
    d = lease_path(w)
    try:
        os.mkdir(str(d))
    except FileExistsError:
        raise LeaseHeld(read_lease(w) or {}, d)
    record = {
        "bg_id": None,
        "session_id": None,
        "pid": int(pid if pid is not None else os.getpid()),
        "host": config.short_hostname(),
        "acquired": now,
        "feature": feature,
        "prompt": prompt,
    }
    _write_lease(d, record)
    return record


def confirm_lease(worktree: Any, patch: Dict[str, Any]) -> Dict[str, Any]:
    """Record the facts the launch produced: bg id, session id, session pid."""
    d = lease_path(worktree)
    rec = read_lease(worktree) or {}
    for key in ("held", "owner_alive", "unreadable"):
        rec.pop(key, None)
    rec.update({k: v for k, v in patch.items() if v is not None})
    if d.is_dir():
        _write_lease(d, rec)
    return rec


def release(worktree: Any, require_dead: bool = True) -> Tuple[bool, str]:
    """Remove the lease. ``(released, why_not)``.

    Refuses while the owner lives, and refuses on unknown. Releasing a lease
    whose owner is still working is the same accident as stealing one.
    """
    w = Path(worktree)
    d = lease_path(w)
    if not d.exists():
        return (True, "no lease")
    rec = read_lease(w) or {}
    alive = rec.get("owner_alive")
    mine = rec.get("pid") == os.getpid()
    if require_dead and not mine:
        if alive is True:
            return (
                False,
                "owner pid %s is alive. `factory stop` it first; a lease is never stolen."
                % (rec.get("pid"),),
            )
        if alive is None:
            return (
                False,
                "cannot prove the owner (pid %s) is gone. Unknown is not dead."
                % (rec.get("pid"),),
            )
    try:
        f = d / LEASE_FILE
        if f.exists():
            f.unlink()
        for junk in sorted(d.glob("*.tmp")):
            junk.unlink()
        os.rmdir(str(d))
    except Exception as exc:
        return (False, "could not remove %s: %s" % (d, exc))
    return (True, "")


def lease_state(record: Optional[Dict[str, Any]], sessions: List[Dict[str, Any]], now: str) -> str:
    """``none``, ``live``, ``unknown``, ``unattributable`` or ``stale``."""
    if not record or not record.get("held"):
        return "none"
    if not isinstance(record.get("pid"), int):
        return "unattributable"
    alive = record.get("owner_alive")
    if alive is False:
        return "stale"
    if alive is None:
        return "unknown"
    if not sessions:
        age = _age_seconds(record.get("acquired"), now)
        if age is not None and age > LEASE_ORPHAN_SECONDS:
            return "stale"
    return "live"


def _age_seconds(stamp: Any, now: str) -> Optional[float]:
    then, right_now = _ts(stamp), derive.ts_of(now)
    if then is None or right_now is None:
        return None
    return right_now - then


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------


def raw_sessions(cfg: config.Config) -> Tuple[List[Dict[str, Any]], bool]:
    """``~/.claude/sessions/*.json``, read directly, as ``(rows, ok)``.

    The same files ``probe.sessions`` reads, with one difference that matters to
    a dispatch: a pid whose ``procStart`` cannot be compared is kept, not
    dropped. For a refusal, a session wrongly believed live costs one refusal,
    while a live session wrongly believed gone costs two builders in one tree.
    """
    d = Path(cfg.claude_home) / "sessions"
    if not d.is_dir():
        return ([], False)
    try:
        files = sorted(d.glob("*.json"))
    except Exception:
        return ([], False)
    rows: List[Dict[str, Any]] = []
    ok = True
    for f in files:
        data, dok = probe._read_json(f)
        if not dok or not isinstance(data, dict):
            ok = False
            continue
        pid = data.get("pid")
        alive = _pid_alive(pid)
        if alive is None:
            ok = False
            continue
        if not alive:
            continue
        lstart, lok = probe._ps_lstart(int(pid))
        if lok and same_process(data.get("procStart"), lstart) is False:
            continue                                  # genuine pid reuse
        row = {
            "pid": pid,
            "sessionId": data.get("sessionId"),
            "cwd": data.get("cwd"),
            "kind": data.get("kind"),
            "name": data.get("name"),
            "status": data.get("status"),
            "jobId": data.get("jobId"),
            "startedAt": data.get("startedAt"),
        }
        job = Path(cfg.claude_home) / "jobs" / str(
            row.get("jobId") or str(row.get("sessionId") or "").split("-")[0]
        )
        st, st_ok = probe._read_json(job / "state.json")
        if st_ok and isinstance(st, dict):
            row["bg_id"] = job.name
            for key in ("state", "detail", "needs", "tempo", "children"):
                row[key] = st.get(key)
        rows.append(row)
    return (rows, ok)


def live_sessions(ctx: Any) -> Tuple[List[Dict[str, Any]], bool]:
    """Every live session on the machine, as ``(rows, ok)``.

    The core probe and the direct read are merged by session id, and the wider
    of the two wins: a dispatch must never see fewer sessions than exist.
    ``ctx.meta["sessions_all"]`` short-circuits both, which is how the tests and
    a verb called straight after ``board`` avoid one more probe round.
    """
    meta = getattr(ctx, "meta", None) or {}
    if "sessions_all" in meta:
        return (list(meta.get("sessions_all") or []), bool(meta.get("sessions_ok", True)))
    rows, ok = probe.sessions(ctx.config)
    rows = list(rows or [])
    extra, raw_ok = raw_sessions(ctx.config)
    seen = {str(r.get("sessionId") or r.get("pid")) for r in rows}
    for row in extra:
        if str(row.get("sessionId") or row.get("pid")) not in seen:
            rows.append(row)
    if "sessions" in (meta.get("stale") or []):
        ok = False
    # Both readers must be sure. `ok or raw_ok` let one blinded reader pass the
    # dispatch: with ps unavailable both return an empty list, and an empty list
    # read as a fact is how two builders end up in one workspace.
    return (rows, bool(ok and raw_ok))


def sessions_under(rows: List[Dict[str, Any]], worktree: Any) -> List[Dict[str, Any]]:
    """Every live session whose cwd is at or under the worktree.

    Interactive sessions count. The file probe sees them, and an interactive
    Claude in the tree edits the same files a build would.
    """
    base = str(worktree).rstrip("/")
    hit = []
    for row in rows:
        cwd = str(row.get("cwd") or "")
        if cwd == base or cwd.startswith(base + "/"):
            hit.append(row)
    return hit


def background_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Working background sessions: what the concurrency cap counts."""
    busy = []
    for row in rows:
        if str(row.get("kind") or "") == "interactive":
            continue
        if not (row.get("bg_id") or row.get("jobId")):
            continue
        state = str(row.get("state") or row.get("status") or "").lower()
        if state in DEAD_STATES:
            continue
        busy.append(row)
    return busy


def short_of(row: Dict[str, Any]) -> str:
    return (
        str(row.get("bg_id") or "")
        or str(row.get("jobId") or "")
        or str(row.get("sessionId") or "").split("-")[0]
    )


def parse_short_id(text: str) -> Optional[str]:
    """The short id from the ``backgrounded`` line.

    The line separates its three fields with a glyph this file cannot contain,
    so the match is on the word plus the first eight hex characters after it.
    The short id is the first segment of the session UUID in 8 of 8 local jobs,
    so the full UUID for ``--resume`` is derivable from it.
    """
    for line in (text or "").splitlines():
        if "backgrounded" in line.lower():
            m = SHORT_ID.search(line)
            if m:
                return m.group(1)
    m = SHORT_ID.search(text or "")
    return m.group(1) if m else None


def confirm_launch(
    cfg: config.Config,
    short: Optional[str],
    feature: str,
    worktree: Any,
    budget: float = CONFIRM_SECONDS,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Confirm the printed id against ``~/.claude/sessions/*.json``.

    The printed line is a claim; the session files are the oracle. Falls back to
    a background row whose cwd is the worktree and whose name is the feature,
    because ``--name <feature>`` pins that name with ``nameSource: user``.
    """
    deadline = time.time() + max(0.0, budget)
    base = str(worktree).rstrip("/")
    while True:
        rows, _ok = raw_sessions(cfg)
        if short:
            for row in rows:
                sid = str(row.get("sessionId") or "")
                if sid.startswith(short) or short_of(row) == short:
                    return (row, "id")
        for row in rows:
            if str(row.get("kind") or "") == "interactive":
                continue
            if str(row.get("cwd") or "").rstrip("/") == base and str(row.get("name") or "") == feature:
                return (row, "cwd+name")
        if time.time() >= deadline:
            break
        time.sleep(CONFIRM_POLL)

    # Last resort, only once the session files have had their whole budget: the
    # job record. It appears before the session file does, so checking it early
    # would hide the one row that carries the pid.
    if short:
        st, ok = probe._read_json(Path(cfg.claude_home) / "jobs" / short / "state.json")
        if ok and isinstance(st, dict) and str(st.get("cwd") or "").rstrip("/") == base:
            return (
                {
                    "pid": None,
                    "sessionId": st.get("sessionId"),
                    "cwd": st.get("cwd"),
                    "kind": "bg",
                    "name": st.get("name"),
                    "jobId": short,
                    "bg_id": short,
                    "state": st.get("state"),
                    "detail": st.get("detail"),
                    "needs": st.get("needs"),
                },
                "job record",
            )
    return (None, "")


# --------------------------------------------------------------------------
# The session registry, in factory/state/<feature>.json
# --------------------------------------------------------------------------


def registry(ctx: Any, feature: str) -> Dict[str, Any]:
    if getattr(ctx, "state", None) is None:
        return {}
    return (ctx.state.read(feature) or {}).get("session") or {}


def record_dispatch(ctx: Any, feature: str, record: Dict[str, Any], launched_at: float) -> None:
    """The two things a later run cannot recompute: who was launched, and when."""
    if getattr(ctx, "state", None) is None:
        return
    data = ctx.state.read(feature)
    data["session"] = record
    history = list(data.get("dispatches") or [])
    history.append(record)
    data["dispatches"] = history[-20:]
    builds = [float(t) for t in (data.get("builds") or []) if _ts(t)]
    builds.append(float(launched_at))
    data["builds"] = builds[-40:]
    ctx.state.write(feature, data, getattr(ctx, "dry_run", False))


def clear_dispatch(ctx: Any, feature: str, why: str) -> None:
    if getattr(ctx, "state", None) is None:
        return
    data = ctx.state.read(feature)
    rec = dict(data.get("session") or {})
    if rec:
        rec["ended"] = why
        data["session"] = rec
    ctx.state.write(feature, data, getattr(ctx, "dry_run", False))


def builds_today(ctx: Any, feature: str, now: str) -> int:
    now_ts = derive.ts_of(now) or time.time()
    if getattr(ctx, "state", None) is None:
        return 0
    data = ctx.state.read(feature)
    return len([t for t in (data.get("builds") or []) if (now_ts - float(t)) < 86400])


def bg_id_for(ctx: Any, feature: str, worktree: Any, rows: List[Dict[str, Any]]) -> Tuple[Optional[str], str]:
    """The background id to act on, and where it came from."""
    if worktree:
        for row in sessions_under(rows, worktree):
            if str(row.get("kind") or "") != "interactive" and short_of(row):
                return (short_of(row), "live session")
    reg = registry(ctx, feature)
    if reg.get("bg_id"):
        return (str(reg["bg_id"]), "the registry")
    if worktree:
        rec = read_lease(worktree) or {}
        if rec.get("bg_id"):
            return (str(rec["bg_id"]), "the lease")
    return (None, "")


# --------------------------------------------------------------------------
# Flags
# --------------------------------------------------------------------------


def card_flags(card: FeatureCard, obs: Dict[str, Any], ctx: Any) -> List[str]:
    """``lease-stale`` and ``two-sessions``, from the lease and the session rows.

    ``card.add_flag`` dedupes, so the two rules core already applies are simply
    reinforced here; these three are the cases core does not see:

      * a lease whose record carries no pid, which cannot be attributed at all
      * a lease with no live session in its tree, older than a day
      * a live lease plus a live session that is not the lease's session, which
        is two independent actors in one workspace
    """
    flags: List[str] = []
    lease = obs.get("lease") or {}
    sessions = list(obs.get("sessions") or [])

    if lease.get("held"):
        state = lease_state(lease, sessions, getattr(ctx, "now", "") or "")
        if state in ("stale", "unattributable"):
            flags.append("lease-stale")

    if len(sessions) > 1:
        flags.append("two-sessions")
    elif sessions and lease.get("held") and lease.get("owner_alive") is True:
        owner = str(lease.get("session_id") or "")
        if owner and any(
            str(r.get("sessionId") or "") and str(r.get("sessionId")) != owner for r in sessions
        ):
            flags.append("two-sessions")
    return flags


# --------------------------------------------------------------------------
# The note's Session block
# --------------------------------------------------------------------------


def note_sections(card: FeatureCard, ctx: Any) -> List[Tuple[str, str, int]]:
    """One ``## Session`` block: the lease, the registry, and the attach command.

    Every line is a function of stored data, never of the clock, so the note
    rebuilds byte for byte.
    """
    obs = (getattr(ctx, "obs", None) or {}).get(card.id) or {}
    reg = registry(ctx, card.id)
    lease = obs.get("lease") or {}
    if not card.worktree and not reg and not lease:
        return []

    cfg = ctx.config
    fac = render.tilde(launcher(cfg))
    lines: List[str] = []

    state = lease_state(lease, list(obs.get("sessions") or []), getattr(ctx, "now", "") or "")
    if state == "none":
        lines.append("- Lease: **free**. `%s start %s` takes it." % (fac, card.id))
    elif state == "live":
        lines.append(
            "- Lease: **held** by bg `%s` (pid %s) since %s"
            % (lease.get("bg_id") or "unknown", lease.get("pid"), lease.get("acquired") or "unknown")
        )
    elif state == "unknown":
        lines.append(
            "- Lease: **held** by pid %s; liveness unknown this run, so nothing was changed."
            % (lease.get("pid"),)
        )
    else:
        lines.append(
            "- Lease: **stale** (%s, pid %s, taken %s). A lease is never stolen: "
            "`%s release %s`."
            % (
                "no pid in the record" if state == "unattributable" else "the owner is gone",
                lease.get("pid"),
                lease.get("acquired") or "unknown",
                fac,
                card.id,
            )
        )

    if reg.get("bg_id") or reg.get("session_id"):
        lines.append(
            "- Registry: bg `%s`, session `%s`, started %s, prompt `%s`%s"
            % (
                reg.get("bg_id") or "unknown",
                reg.get("session_id") or "unknown",
                reg.get("started") or "unknown",
                reg.get("prompt") or DEFAULT_PROMPT,
                (" (ended: %s)" % (reg["ended"],)) if reg.get("ended") else "",
            )
        )
    else:
        lines.append("- Registry: no dispatch recorded by `factory start`")

    rows = list(obs.get("sessions") or [])
    for row in rows:
        lines.append(
            "- Live session `%s` (%s, %s): %s%s"
            % (
                short_of(row) or "unknown",
                row.get("kind") or "unknown",
                row.get("state") or row.get("status") or "unknown",
                row.get("detail") or "no detail",
                (". Needs: %s" % (row["needs"],)) if row.get("needs") else "",
            )
        )
    if not rows:
        lines.append("- Live sessions in this workspace: none")

    data = (ctx.state.read(card.id) if getattr(ctx, "state", None) else {}) or {}
    builds = [t for t in (data.get("builds") or []) if _ts(t)]
    lines.append(
        "- Launches recorded: %d%s. Caps: %d at once, %d per day, %d GB free."
        % (
            len(builds),
            (" (last %s)" % (probe.day(float(builds[-1])),)) if builds else "",
            cfg.max_concurrent_sessions,
            cfg.max_builds_per_day,
            cfg.min_free_gb,
        )
    )

    bg = reg.get("bg_id") or lease.get("bg_id") or (short_of(rows[0]) if rows else "")
    lines.append("")
    lines.append("```")
    lines.append("%s start %s" % (fac, card.id))
    if bg:
        lines.append("%s attach %s" % (render.tilde(claude_bin(cfg)), bg))
    lines.append("%s attach %s" % (fac, card.id))
    lines.append("%s stop %s" % (fac, card.id))
    lines.append("```")
    return [("Session", "\n".join(lines), 30)]


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------


def doctor_checks(ctx: Any) -> List[Tuple[str, bool, str]]:
    cfg = ctx.config
    checks: List[Tuple[str, bool, str]] = []
    binary = claude_bin(cfg)
    checks.append(
        (
            "claude binary at %s" % (render.tilde(binary),),
            binary.exists(),
            "factory start, stop and logs run it by absolute path",
        )
    )
    try:
        free_gb = shutil.disk_usage(str(cfg.worktree_root if cfg.worktree_root.exists() else Path.home())).free / (1024.0 ** 3)
    except Exception:
        free_gb = -1.0
    checks.append(
        (
            "free disk above the %d GB floor" % (cfg.min_free_gb,),
            free_gb < 0 or free_gb >= cfg.min_free_gb,
            "%.0f GB free: factory start refuses below the floor" % (free_gb,),
        )
    )
    wts, ok = probe.all_worktrees(cfg)
    held: List[str] = []
    stale: List[str] = []
    for path in sorted(wts or {}):
        rec = read_lease(path)
        if not rec:
            continue
        name = os.path.basename(path.rstrip("/"))
        held.append(name)
        if lease_state(rec, [], probe.iso()) in ("stale", "unattributable"):
            stale.append(name)
    checks.append(
        (
            "no stale lease in any worktree",
            not stale,
            "stale: %s. `factory release <f>` removes one, interactively."
            % (", ".join(stale),),
        )
    )
    if held:
        checks.append(
            (
                "leases held: %s" % (", ".join(held),),
                True,
                "",
            )
        )
    return checks


# --------------------------------------------------------------------------
# collect: release the clamp after a reset
# --------------------------------------------------------------------------


def collect(ctx: Any) -> None:
    """Turn a recorded reset into the named demotion cause, exactly once.

    ``derive.demotion_cause`` reads ``obs["reset"]``, and no probe produces it.
    ``factory reset`` records the intent in ``state/<feature>.json``; this hook
    hands it to derive for one run, so the lane demotion is attributed instead
    of silently held by the clamp.
    """
    for feature, obs in (getattr(ctx, "obs", None) or {}).items():
        data = ctx.state.read(feature) if getattr(ctx, "state", None) else {}
        if not data.get("reset_pending"):
            continue
        obs["reset"] = True
        if not getattr(ctx, "dry_run", False):
            data.pop("reset_pending", None)
            data["reset_applied"] = getattr(ctx, "now", "")
            ctx.state.write(feature, data, False)


# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise ValueError("%s: %s" % (self.prog, message))


def _args(
    verb: str,
    rest: List[str],
    prompt: bool = False,
    yes: bool = False,
    reason: bool = False,
) -> Any:
    p = _Parser(prog="factory " + verb, add_help=False)
    p.add_argument("feature")
    p.add_argument("--root", default=None, help="treat <root>/<feature> as the worktree")
    p.add_argument("--dry-run", action="store_true", dest="dry_run")
    p.add_argument("--offline", action="store_true")
    if prompt:
        p.add_argument("--prompt", default=DEFAULT_PROMPT)
        p.add_argument("--force", action="store_true")
        p.add_argument("--no-board", action="store_true", dest="no_board")
    if yes:
        p.add_argument("--yes", action="store_true")
    if reason:
        p.add_argument("--reason", default="")
    return p.parse_args(list(rest))


def resolve(ctx: Any, args: Any) -> Tuple[Optional[FeatureCard], Optional[Path]]:
    """``(card, worktree)``. ``--root`` wins, so a rehearsal never needs a card."""
    feature = config.validate_id(args.feature)
    card = ctx.card(feature) if hasattr(ctx, "card") else None
    if getattr(args, "root", None):
        return (card, Path(args.root).expanduser() / feature)
    if card is not None and card.worktree:
        return (card, Path(card.worktree))
    return (card, None)


# --------------------------------------------------------------------------
# start: the ten steps
# --------------------------------------------------------------------------


def refusals(
    ctx: Any,
    card: Optional[FeatureCard],
    worktree: Path,
    rows: List[Dict[str, Any]],
    rows_ok: bool,
    args: Any,
) -> List[Tuple[str, str]]:
    """Steps 3 to 6, in the plan's order. The first entry wins."""
    cfg = ctx.config
    bad: List[Tuple[str, str]] = []

    # 4 before 3: an unknown session probe makes step 3 unanswerable.
    if not rows_ok:
        bad.append(
            (
                "sessions-unknown",
                "the session probe came back unknown. Unknown is not empty: "
                "a dispatch now could double-book this workspace.",
            )
        )
        return bad

    here = sessions_under(rows, worktree)
    if here:
        bad.append(
            (
                "session-in-worktree",
                "a live session is already in this workspace: %s. Take it over with "
                "`%s attach %s`."
                % (
                    ", ".join(
                        "%s (%s, %s)"
                        % (short_of(r) or "unknown", r.get("kind") or "unknown", r.get("cwd"))
                        for r in here
                    ),
                    render.tilde(claude_bin(cfg)),
                    short_of(here[0]) or "unknown",
                ),
            )
        )

    if card is not None and not args.force:
        if card.has("foreign-worktree"):
            bad.append(
                (
                    "foreign-worktree",
                    "the checkout is outside %s. Tear it down or rename it; do not build in it."
                    % (render.tilde(cfg.worktree_root),),
                )
            )
        if card.has("branch-mismatch"):
            bad.append(
                (
                    "branch-mismatch",
                    "a repository HEAD is not %r. Fix the branch first: a build would "
                    "commit against the wrong branch name." % (card.id,),
                )
            )

    if not args.force:
        if card is None:
            bad.append(
                (
                    "no-card",
                    "no card for %r, so the lane is unknown. Run `factory board`, "
                    "or pass --force to dispatch anyway." % (args.feature,),
                )
            )
        elif rank(card.lane) < rank(APPROVED):
            bad.append(
                (
                    "lane",
                    "lane is %s, below approved. Approve the blueprint first, or "
                    "pass --force." % (card.lane,),
                )
            )

    busy = background_rows(rows)
    if len(busy) >= cfg.max_concurrent_sessions:
        bad.append(
            (
                "concurrency",
                "%d background sessions are already working (cap %d): %s. Each spends "
                "subscription quota independently."
                % (
                    len(busy),
                    cfg.max_concurrent_sessions,
                    ", ".join(short_of(r) or "unknown" for r in busy),
                ),
            )
        )

    today = builds_today(ctx, args.feature, getattr(ctx, "now", "") or probe.iso())
    if today >= cfg.max_builds_per_day:
        bad.append(
            (
                "per-day",
                "%d launches recorded for this card in the last 24 hours (cap %d)."
                % (today, cfg.max_builds_per_day),
            )
        )

    try:
        free_gb = shutil.disk_usage(str(worktree)).free / (1024.0 ** 3)
    except Exception:
        free_gb = -1.0
    if 0 <= free_gb < cfg.min_free_gb:
        bad.append(
            (
                "disk",
                "%.1f GB free on this volume, below the %d GB floor. A MOOSE build "
                "needs room." % (free_gb, cfg.min_free_gb),
            )
        )
    return bad


def run_start(rest: List[str], ctx: Any) -> int:
    """1 guard, 3-6 refuse, 2 lease, 7 launch, 8 confirm, 9 record, 10 board.

    The plan numbers the lease second. It is taken last of the checks here for
    one reason: a refusal must write nothing anywhere, and the lease is a
    directory inside the workspace. A `start` refused for a foreign checkout
    used to leave `.factory-lease/` behind in a tree no script may touch.
    """
    config.hostname_guard()                                   # 1
    args = _args("start", rest, prompt=True)
    cfg = ctx.config
    now = getattr(ctx, "now", "") or probe.iso()
    card, worktree = resolve(ctx, args)
    if worktree is None:
        err(
            "no workspace for %r. `factory start` dispatches into a worktree; pass "
            "--root PATH to rehearse elsewhere." % (args.feature,)
        )
        return MISSING
    if not worktree.is_dir():
        err("no directory at %s" % (worktree,))
        return MISSING

    dry = bool(args.dry_run or getattr(ctx, "dry_run", False))
    rows, rows_ok = live_sessions(ctx)

    # --- 3 to 6 before 2. Not one of these refusals needs the lease, and
    # taking it first wrote `.factory-lease/` into a legacy checkout that a
    # refused start is not allowed to touch at all. The lease still guards the
    # launch: it is taken below, immediately before the launch itself.
    bad = refusals(ctx, card, worktree, rows, rows_ok, args)
    if bad:
        name, why = bad[0]
        err("refused (%s): %s" % (name, why))
        for name, why in bad[1:]:
            err("  also (%s): %s" % (name, why))
        return REFUSED

    # --- 2. the lease -----------------------------------------------------
    if dry:
        existing = read_lease(worktree)
        if existing:
            err(
                "refused (lease): %s already holds %s (pid %s, %s)"
                % (
                    existing.get("bg_id") or "a session",
                    lease_path(worktree),
                    existing.get("pid"),
                    lease_state(existing, sessions_under(rows, worktree), now),
                )
            )
            return REFUSED
        held = None
    else:
        try:
            held = acquire(worktree, args.feature, args.prompt, now)
        except LeaseHeld as exc:
            rec = exc.record
            state = lease_state(rec, sessions_under(rows, worktree), now)
            err(
                "refused (lease): %s is held by bg %s, pid %s, since %s (%s)"
                % (
                    render.tilde(exc.path),
                    rec.get("bg_id") or "unknown",
                    rec.get("pid"),
                    rec.get("acquired") or "unknown",
                    state,
                )
            )
            if state in ("stale", "unattributable"):
                err(
                    "  the owner is gone, but a lease is never stolen: "
                    "`factory release %s` (interactive)." % (args.feature,)
                )
            return REFUSED

    def give_back() -> None:
        if held is not None:
            ok, why = release(worktree, require_dead=False)
            if not ok:
                err("warning: could not release the lease I just took: %s" % (why,))

    cmd = [str(claude_bin(cfg)), "--bg", "--name", args.feature, args.prompt]
    if dry:
        out("would run, with cwd %s:" % (worktree,))
        out("  %s" % (" ".join(cmd),))
        out("lease, registry, timeline and board: all skipped (dry run)")
        return OK

    # --- 7. launch --------------------------------------------------------
    launched_at = time.time()
    stdout, stderr, rc = _run(cmd, cwd=worktree, timeout=LAUNCH_TIMEOUT)
    if rc != 0:
        give_back()
        err("launch failed (rc %d): %s" % (rc, (stderr or stdout).strip()[:400]))
        return LOOK
    if stdout.strip():
        out(stdout.strip())

    # --- 8. capture the short id, then confirm it from the session files --
    short = parse_short_id(stdout + "\n" + stderr)
    row, how = confirm_launch(cfg, short, args.feature, worktree)
    session_id = str((row or {}).get("sessionId") or "")
    bg_id = short or (short_of(row) if row else "")
    if row is not None and not bg_id:
        bg_id = short_of(row)

    # --- 9. the registry, the lease record, and one timeline line --------
    record = {
        "bg_id": bg_id or None,
        "session_id": session_id or None,
        "started": now,
        "prompt": args.prompt,
        "worktree": str(worktree),
        "confirmed": how or None,
    }
    record_dispatch(ctx, args.feature, record, launched_at)
    confirm_lease(
        worktree,
        {
            "bg_id": bg_id or None,
            "session_id": session_id or None,
            "pid": (row or {}).get("pid"),
        },
    )
    if getattr(ctx, "timeline", None) is not None:
        ctx.timeline.append(
            args.feature,
            {
                "at": now,
                "event": "dispatched",
                "bg_id": bg_id or None,
                "session_id": session_id or None,
                "prompt": args.prompt,
                "lane": card.lane if card else None,
                "via": "factory start",
                "why": "confirmed by %s" % (how,) if how else "id not confirmed",
            },
        )

    if row is None:
        err(
            "launched, but no session file confirms %s within %.0fs. The lease now "
            "carries a pid that may be gone: check `%s agents --json "
            "--all`, then `factory release %s` if nothing is there."
            % (bg_id or "the new session", CONFIRM_SECONDS,
               render.tilde(claude_bin(cfg)), args.feature)
        )
        return LOOK

    out(
        "started %s: bg %s, session %s (confirmed by %s), pid %s"
        % (args.feature, bg_id or "unknown", session_id or "unknown", how, row.get("pid"))
    )
    if not row.get("pid"):
        err(
            "note: %s was confirmed by the %s, which carries no pid, so the lease "
            "keeps a provisional owner and may read as stale on the next board. "
            "The session itself is fine." % (bg_id or "the session", how)
        )
    out("  attach: %s attach %s" % (render.tilde(claude_bin(cfg)), bg_id or short_of(row)))
    out("  stop:   %s stop %s" % (render.tilde(launcher(cfg)), args.feature))

    # --- 10. the board ----------------------------------------------------
    if not getattr(args, "no_board", False):
        lp = launcher(cfg)
        if lp.exists():
            bout, berr, brc = _run([str(lp), "board"], cwd=cfg.repo_root, timeout=120)
            for line in (bout or "").splitlines()[:3]:
                out("  %s" % (line,))
            if brc != 0:
                err("board exited %d: %s" % (brc, (berr or "").strip()[:200]))
        else:
            err("no launcher at %s; run `factory board` by hand" % (lp,))
    return OK


# --------------------------------------------------------------------------
# stop, attach, logs
# --------------------------------------------------------------------------


def run_stop(rest: List[str], ctx: Any) -> int:
    config.hostname_guard()
    args = _args("stop", rest)
    now = getattr(ctx, "now", "") or probe.iso()
    card, worktree = resolve(ctx, args)
    rows, _ok = live_sessions(ctx)
    bg, source = bg_id_for(ctx, args.feature, worktree, rows)
    if not bg:
        err(
            "nothing to stop for %r: no live session, no registry entry, no lease."
            % (args.feature,)
        )
        return MISSING
    if args.dry_run or getattr(ctx, "dry_run", False):
        out("would run: %s stop %s (from %s)" % (claude_bin(ctx.config), bg, source))
        return OK
    stdout, stderr, rc = _run([str(claude_bin(ctx.config)), "stop", bg], timeout=STOP_TIMEOUT)
    if (stdout or stderr).strip():
        out((stdout or stderr).strip())
    if rc != 0:
        err("claude stop %s exited %d. The conversation is kept either way." % (bg, rc))
    out("stopped %s (%s). `--resume` still works: the conversation is kept." % (bg, source))
    clear_dispatch(ctx, args.feature, "stopped %s" % (now,))
    if getattr(ctx, "timeline", None) is not None:
        ctx.timeline.append(
            args.feature,
            {"at": now, "event": "dispatch-stopped", "bg_id": bg, "via": "factory stop"},
        )
    if worktree and lease_path(worktree).exists():
        # Give the process a moment to exit before the lease is judged.
        for _ in range(6):
            if _pid_alive((read_lease(worktree) or {}).get("pid")) is not True:
                break
            time.sleep(CONFIRM_POLL)
        ok, why = release(worktree)
        if ok:
            out("lease released")
        else:
            err("lease kept: %s" % (why,))
            return LOOK
    return OK if rc == 0 else LOOK


def run_attach(rest: List[str], ctx: Any) -> int:
    """Print the attach command and what the session is doing. Touches nothing."""
    config.hostname_guard()
    args = _args("attach", rest)
    card, worktree = resolve(ctx, args)
    rows, rows_ok = live_sessions(ctx)
    here = sessions_under(rows, worktree) if worktree else []
    bg, source = bg_id_for(ctx, args.feature, worktree, rows)
    if not bg:
        err(
            "no session for %r%s. Start one: `factory start %s`."
            % (
                args.feature,
                "" if rows_ok else " (and the session probe is unknown this run)",
                args.feature,
            )
        )
        return MISSING
    out("%s attach %s" % (render.tilde(claude_bin(ctx.config)), bg))
    out("  from     %s" % (source,))
    for row in here:
        out(
            "  state    %s%s"
            % (
                row.get("state") or row.get("status") or "unknown",
                " (%s)" % (row.get("kind"),) if row.get("kind") else "",
            )
        )
        if row.get("detail"):
            out("  detail   %s" % (row["detail"],))
        if row.get("needs"):
            out("  needs    %s" % (row["needs"],))
        last = row.get("last_line") or {}
        if isinstance(last, dict) and last.get("detail"):
            out("  doing    %s" % (last["detail"],))
    if not here:
        reg = registry(ctx, args.feature)
        out("  state    no live session file. Recorded prompt: %s" % (reg.get("prompt") or "unknown",))
        out(
            "  note     a background session does not survive a reboot, and the "
            "factory never relaunches one. Relaunch: factory start %s" % (args.feature,)
        )
    return OK


def run_logs(rest: List[str], ctx: Any) -> int:
    config.hostname_guard()
    args = _args("logs", rest)
    card, worktree = resolve(ctx, args)
    rows, _ok = live_sessions(ctx)
    bg, source = bg_id_for(ctx, args.feature, worktree, rows)
    if not bg:
        err("no background id for %r: nothing to read." % (args.feature,))
        return MISSING
    if args.dry_run or getattr(ctx, "dry_run", False):
        out("would run: %s logs %s (from %s)" % (claude_bin(ctx.config), bg, source))
        return OK
    stdout, stderr, rc = _run([str(claude_bin(ctx.config)), "logs", bg], timeout=LOGS_TIMEOUT)
    if stdout.strip():
        sys.stdout.write(stdout if stdout.endswith("\n") else stdout + "\n")
    if rc != 0:
        err(
            "claude logs %s exited %d: %s. This verb needs a live background service."
            % (bg, rc, (stderr or "").strip()[:200])
        )
        return LOOK
    return OK


# --------------------------------------------------------------------------
# release
# --------------------------------------------------------------------------


def run_release(rest: List[str], ctx: Any) -> int:
    """Remove a stale lease, interactively, after proving the owner is gone."""
    config.hostname_guard()
    args = _args("release", rest, yes=True)
    now = getattr(ctx, "now", "") or probe.iso()
    card, worktree = resolve(ctx, args)
    if worktree is None:
        err("no workspace for %r" % (args.feature,))
        return MISSING
    rec = read_lease(worktree)
    if not rec:
        out("no lease at %s" % (lease_path(worktree),))
        return OK
    rows, _ok = live_sessions(ctx)
    state = lease_state(rec, sessions_under(rows, worktree), now)
    out(
        "lease %s: bg %s, session %s, pid %s, host %s, taken %s (%s)"
        % (
            render.tilde(lease_path(worktree)),
            rec.get("bg_id") or "unknown",
            rec.get("session_id") or "unknown",
            rec.get("pid"),
            rec.get("host") or "unknown",
            rec.get("acquired") or "unknown",
            state,
        )
    )
    if state == "live":
        err("refused: the owner is alive. `factory stop %s` first." % (args.feature,))
        return REFUSED
    if state == "unknown":
        err("refused: cannot prove the owner is gone. Unknown is not dead.")
        return REFUSED
    if args.dry_run or getattr(ctx, "dry_run", False):
        out("would remove it (dry run)")
        return OK
    agreed, why = _confirm("remove this stale lease?", bool(args.yes))
    if not agreed:
        err("kept. %s" % (why or "answered no",))
        return REFUSED
    ok, why = release(worktree)
    if not ok:
        err("refused: %s" % (why,))
        return REFUSED
    out("lease removed")
    clear_dispatch(ctx, args.feature, "lease released %s" % (now,))
    if getattr(ctx, "timeline", None) is not None:
        ctx.timeline.append(
            args.feature,
            {
                "at": now,
                "event": "lease-released",
                "bg_id": rec.get("bg_id"),
                "pid": rec.get("pid"),
                "state": state,
                "via": "factory release",
            },
        )
    return OK


# --------------------------------------------------------------------------
# reset
# --------------------------------------------------------------------------


def blueprint_reset(text: str) -> str:
    """``status: approved`` in the frontmatter, every ``running`` unit ``idle``.

    Textual, deliberately: a re-dumped JSON work plan would diff against itself
    on whitespace, and this diff is the thing Max reads before agreeing.
    """
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        end = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end = i
                break
        if end is not None:
            seen = False
            for i in range(1, end):
                if re.match(r"^status\s*:", lines[i]):
                    lines[i] = "status: approved"
                    seen = True
            if not seen:
                lines.insert(end, "status: approved")
    text = "\n".join(lines)

    def fence(match: Any) -> str:
        body = match.group(2)
        body = re.sub(r'("status"\s*:\s*)"running"', r'\1"idle"', body)
        body = re.sub(r"('status'\s*:\s*)'running'", r"\1'idle'", body)
        return match.group(1) + body + match.group(3)

    return re.sub(r"(```json\n)(.*?)(```)", fence, text, flags=re.DOTALL)


def run_reset(rest: List[str], ctx: Any) -> int:
    """Repair a dead build: print the diff, apply it on a yes, release the lease."""
    config.hostname_guard()
    args = _args("reset", rest, yes=True, reason=True)
    now = getattr(ctx, "now", "") or probe.iso()
    card, worktree = resolve(ctx, args)
    if worktree is None:
        err("no workspace for %r" % (args.feature,))
        return MISSING
    rows, _ok = live_sessions(ctx)
    here = sessions_under(rows, worktree)
    if here:
        err(
            "refused: a live session is still in this workspace (%s). Stop it first: "
            "`factory stop %s`." % (short_of(here[0]) or "unknown", args.feature)
        )
        return REFUSED

    path = worktree / "specs" / "blueprint.md"
    old, ok = probe._read_text(path)
    if not ok:
        err("cannot read %s" % (path,))
        return LOOK
    diff = ""
    if old is None:
        out("no %s: nothing to rewrite, only the lease to release." % (render.tilde(path),))
    else:
        new = blueprint_reset(old)
        if new == old:
            out(
                "%s already says approved with no running unit. Nothing to rewrite."
                % (render.tilde(path),)
            )
        else:
            diff = "".join(
                difflib.unified_diff(
                    old.splitlines(True),
                    new.splitlines(True),
                    fromfile=str(render.tilde(path)),
                    tofile=str(render.tilde(path)) + " (reset)",
                    n=2,
                )
            )
            out(diff.rstrip())

    rec = read_lease(worktree)
    state = lease_state(rec, here, now) if rec else "none"
    out("lease: %s" % (state,))
    if args.dry_run or getattr(ctx, "dry_run", False):
        out("dry run: nothing written, the lease is untouched")
        return OK
    if not diff and state in ("none",):
        return OK

    agreed, why = _confirm(
        "apply this reset to %s?" % (args.feature,), bool(args.yes)
    )
    if not agreed:
        err("nothing changed. %s" % (why or "answered no",))
        return REFUSED

    if diff:
        tmp = path.with_suffix(".md.factory-tmp")
        tmp.write_text(blueprint_reset(old))
        os.replace(tmp, path)
        out("rewrote %s" % (render.tilde(path),))

    if state in ("stale", "unattributable"):
        ok, why = release(worktree)
        out("lease removed" if ok else "lease kept: %s" % (why,))
    elif state == "live":
        err("lease kept: the owner is alive, which contradicts a dead build.")
    elif state == "unknown":
        err("lease kept: liveness unknown. Unknown is not dead.")

    # Hand derive a named demotion cause on the next board run.
    if getattr(ctx, "state", None) is not None:
        data = ctx.state.read(args.feature)
        data["reset_pending"] = True
        data["reset_reason"] = args.reason or "reset by hand"
        ctx.state.write(args.feature, data, False)
    clear_dispatch(ctx, args.feature, "reset %s" % (now,))
    if getattr(ctx, "timeline", None) is not None:
        ctx.timeline.append(
            args.feature,
            {
                "at": now,
                "event": "reset",
                "reason": args.reason or "reset by hand",
                "blueprint": bool(diff),
                "lease": state,
                "via": "factory reset",
            },
        )
    out("recorded. The next `factory board` demotes the lane with cause `reset`.")
    return OK


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------

VERBS = {
    "start": run_start,
    "stop": run_stop,
    "attach": run_attach,
    "logs": run_logs,
    "release": run_release,
    "reset": run_reset,
}

HELP = {
    "start": "take the lease and launch one background session into a workspace",
    "stop": "stop the background session, then release the lease",
    "attach": "print the attach command plus the session's state, detail and needs",
    "logs": "stream the background session's log (needs a live service)",
    "release": "remove a stale lease, interactively, once the owner is proven gone",
    "reset": "repair a dead build: diff the blueprint back to approved, free the lease",
}
