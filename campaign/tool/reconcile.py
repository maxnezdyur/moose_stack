"""Bring every unfinished SLURM run up to date from squeue and sacct.

Lifted from ``analysis/tool/reconcile.py``: the state classification
(``_classify``), the per-job sacct sync in the style of ``sync_card``, and
resubmit-on-transient with the failed attempt's core-hours banked. What
changed: the unit is one run's manifest, not a study card; a finished run
gets ``finished``, ``exit`` and ``slurm.core_hours``, its kept outputs are
pulled into ``runs/<D>/outputs/`` and its ``run.log`` beside the manifest,
and the ledger gets its ``done`` line. A resubmission appends a ``note`` line
and an entry to ``slurm.attempts``.

An unreachable cluster raises ``ConnectionDown`` (exit 4); nothing is
written for its runs.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Dict, List, Optional

from . import config, dispatch, ledger, manifest
from .collect import kept_patterns
from .launch import LIGHT_INCLUDES
from .model import Campaign, Run, now_iso, stamp
from .remote import Remote

# SLURM state -> classification
_RUNNING = {"RUNNING", "COMPLETING", "CONFIGURING", "RESIZING", "STAGE_OUT"}
_PENDING = {"PENDING", "SUSPENDED", "REQUEUE_HOLD", "RESV_DEL_HOLD", "REQUEUED", "REQUEUE_FED"}
_DONE = {"COMPLETED"}
_TRANSIENT = {"TIMEOUT", "NODE_FAIL", "PREEMPTED", "OUT_OF_MEMORY", "BOOT_FAIL"}
_SYSTEMATIC = {"FAILED", "CANCELLED", "DEADLINE", "SPECIAL_EXIT", "REVOKED"}


def _classify(state: str) -> str:
    s = (state or "").upper()
    if s in _DONE:
        return "done"
    if s in _RUNNING:
        return "running"
    if s in _PENDING:
        return "pending"
    if s in _TRANSIENT:
        return "transient"
    return "systematic"  # anything unexpected is a hard failure


def unfinished(camp: Campaign) -> List[Run]:
    return [r for r in manifest.load_all(camp.runs_dir)
            if r.is_slurm and not r.done and isinstance(r.slurm, dict) and r.slurm.get("job")]


def _end_iso(end: Optional[str]) -> str:
    if end:
        try:
            t = _dt.datetime.fromisoformat(str(end))
            if t.tzinfo is None:
                t = t.astimezone()
            return t.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass
    return now_iso()


def _pull(remote: Remote, settings: config.Settings, camp: Campaign, run: Run) -> None:
    rdir = dispatch.run_root(settings, run.campaign, run.run)
    remote.pull_file("%s/run.log" % rdir, run.path / "run.log")
    excludes = []
    cwd = Path(run.cwd or ".")
    for inp in run.inputs:
        try:
            rel = Path(inp["path"]).relative_to(cwd) if str(cwd) != "." else Path(inp["path"])
        except ValueError:
            continue
        excludes.append("/" + rel.as_posix())
    includes = [p for p in kept_patterns(camp) if p != "run.log"] + LIGHT_INCLUDES
    remote.pull(dispatch.workdir(settings, run), run.path / "outputs", includes=includes, excludes=excludes)


def sync_run(remote: Remote, settings: config.Settings, camp: Campaign, run: Run,
             acct: Dict[str, Dict[str, object]], live: Dict[str, str]) -> str:
    """Advance one run; return what happened, in one word."""
    s = run.slurm
    job = str(s.get("job"))
    info = acct.get(job)
    if not info and remote.dry_run:
        return "not read (dry-run)"
    if not info:
        state = live.get(job)
        if state and state != s.get("state"):
            s["state"] = state
            if not remote.dry_run:
                manifest.save(run)
        return "queued" if state else "unknown"
    state = str(info["state"])
    attempts = s.get("attempts") or []
    banked = sum(float(a.get("core_hours") or 0) for a in attempts)
    current = round(int(info["alloc_cpus"] or 0) * int(info["elapsed_s"] or 0) / 3600.0, 3)
    s["state"] = state
    s["core_hours"] = round(banked + current, 3)
    klass = _classify(state)
    if klass in ("running", "pending"):
        if not remote.dry_run:
            manifest.save(run)
        return klass
    if klass == "transient" and len(attempts) < config.MAX_TRANSIENT_RETRIES:
        new = dispatch.resubmit(remote, settings, run)
        if remote.dry_run:
            return "resubmit"
        attempts.append({"job": s.get("job"), "state": state, "core_hours": current})
        s["attempts"] = attempts
        s["job"] = int(new) if new and str(new).isdigit() else new
        s["state"] = "PENDING"
        manifest.save(run)
        ledger.append_under(camp.dir / "LEDGER.md", run.run,
                            ledger.note_line("job %s ended %s; resubmitted as job %s (attempt %d)"
                                             % (job, state, new, len(attempts) + 1)))
        return "resubmitted"
    code = info.get("exit")
    if klass == "done":
        run.exit = int(code) if isinstance(code, int) else 0
    else:
        run.exit = int(code) if isinstance(code, int) and code != 0 else 1
    run.finished = _end_iso(info.get("end"))  # type: ignore[arg-type]
    if remote.dry_run:
        return "finished"
    _pull(remote, settings, camp, run)
    manifest.save(run)
    ledger.append_under(camp.dir / "LEDGER.md", run.run,
                        ledger.done_line(stamp(), run.exit, float(s["core_hours"] or 0)))
    return "finished" if klass == "done" else "failed"


def reconcile(camp: Campaign, settings: config.Settings, dry_run: bool = False) -> Dict[str, str]:
    """{run id: outcome} for every unfinished SLURM run of one campaign."""
    runs = unfinished(camp)
    out: Dict[str, str] = {}
    by_cluster: Dict[str, List[Run]] = {}
    for r in runs:
        by_cluster.setdefault(r.cluster, []).append(r)
    for name, group in sorted(by_cluster.items()):
        remote = Remote(settings.cluster(name), settings, dry_run=dry_run)
        remote.require_connection()
        live = remote.squeue_states()
        acct = remote.sacct([str(r.slurm["job"]) for r in group])
        for r in group:
            out[r.run] = sync_run(remote, settings, camp, r, acct, live)
    return out
