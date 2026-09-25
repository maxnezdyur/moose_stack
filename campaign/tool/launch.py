"""Mint a run and start it: the one path every run takes, from ``run`` and from ``replay``.

This module owns the budget arithmetic and the launch sequence. Spent budget
is computed from the manifests every time and never stored (invariant 5). The
launch sequence, for one run:

1. refuse an existing run directory, a missing ``cwd``, a missing input, an
   input outside the project root, and an estimate the remaining budget
   cannot cover;
2. build the manifest: identity blocks, ``code``, ``inputs``, ``outputs``;
3. local: create ``runs/<D>_<tag>/``, freeze the inputs, write the manifest,
   consume the queue entry, append the ledger start line, run the command
   with its output teed into ``run.log``, record ``finished``, ``exit`` and
   ``local.core_hours``, keep the csv measure files, append the ``done`` line;
4. SLURM: resolve the module and the cached binary, stage the run under
   ``runs/.staging-<D>/``, rsync and sbatch, then rename it into place,
   consume the entry and append the ledger start line with the job id.

Under ``--dry-run`` nothing is written and nothing runs: the plan, the
manifest and every rsync and sbatch line are printed.
"""

from __future__ import annotations

import shutil
import socket
from pathlib import Path
from typing import Any, Dict, Optional

from . import config, dispatch, ledger, localrun, manifest, spec
from .model import Campaign, Run, now_iso, stamp, today
from .remote import Remote

LIGHT_INCLUDES = ["*.csv", "*.json", "*.log", "*.txt", "*.out"]


# --------------------------------------------------------------------------
# budget
# --------------------------------------------------------------------------


def spent(camp: Campaign) -> Dict[str, Any]:
    """Spent and budget per axis, from the manifests. ``committed`` adds each
    unfinished run's estimate where it exceeds what that run has used so far."""
    runs = manifest.load_all(camp.runs_dir)
    run_ids, _ = spec.existing_runs(camp)
    core = sum(r.core_hours for r in runs)
    committed = 0.0
    for r in runs:
        est = r.proposal.get("estimate_core_hours") if isinstance(r.proposal, dict) else None
        est = float(est) if isinstance(est, (int, float)) else 0.0
        committed += r.core_hours if r.done else max(r.core_hours, est)
    created = camp.meta.get("created")
    days = None
    if created:
        try:
            import datetime as _dt
            days = (today() - _dt.date.fromisoformat(str(created))).days
        except ValueError:
            days = None
    return {
        "campaign": camp.id,
        "core_hours": {"spent": round(core, 1), "budget": camp.budget("core_hours")},
        "runs": {"spent": len(run_ids), "budget": camp.budget("max_runs")},
        "wall_days": {"spent": days, "budget": camp.budget("wall_days")},
        "committed_core_hours": round(committed, 1),
        "exact_core_hours": core,
    }


def check_budget(camp: Campaign, estimate: float, extra_core: float = 0.0, extra_runs: int = 0) -> None:
    status = camp.meta.get("status")
    if status in ("done", "abandoned"):
        raise config.Refused("%s is %s; no run may start" % (camp.id, status))
    s = spent(camp)
    budget = s["core_hours"]["budget"]
    if budget is not None:
        left = budget - s["committed_core_hours"] - extra_core
        if estimate > left + 1e-9:
            raise config.Refused("estimate %g core-h exceeds the remaining budget %.1f of %g core-h"
                                 % (estimate, max(left, 0.0), budget))
    max_runs = s["runs"]["budget"]
    if max_runs is not None and s["runs"]["spent"] + extra_runs + 1 > max_runs:
        raise config.Refused("max_runs %d is spent (%d runs)" % (max_runs, s["runs"]["spent"] + extra_runs))
    wall = s["wall_days"]
    if wall["budget"] is not None and wall["spent"] is not None and wall["spent"] > wall["budget"]:
        raise config.Refused("wall_days %g is spent (%d days since created)" % (wall["budget"], wall["spent"]))


# --------------------------------------------------------------------------
# launch
# --------------------------------------------------------------------------


def _kept_now(camp: Campaign, run: Run, run_dir: Path) -> None:
    """Copy each csv measure file of a local run into ``outputs/``, before a later run overwrites it."""
    src_dir = Path(run.outputs.get("dir") or "")
    for m in camp.measures:
        if m.kind != "csv":
            continue
        src = src_dir / m.csv_file
        if src.is_file():
            dst = run_dir / "outputs" / m.csv_file
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def _print_plan(run: Run, where: str) -> None:
    print("[dry-run] would mint runs/%s_%s/ (%s)" % (run.run, run.tag, where))
    for inp in run.inputs:
        print("[dry-run]   input %s %s" % (inp["path"], "-> " + inp["frozen"] if inp.get("frozen")
                                          else "(hash only, %d bytes)" % inp["bytes"]))
    print("[dry-run] manifest:")
    for line in manifest.dump(run).splitlines():
        print("[dry-run]   " + line)


def launch(camp: Campaign, settings: config.Settings, plan: Dict[str, Any],
           dry_run: bool = False, consume: Optional[str] = None,
           extra_core: float = 0.0, extra_runs: int = 0) -> int:
    """Mint and start one run. Returns 0, or 1 when a local command exited non-zero."""
    root = camp.root
    rid, tag = plan["run"], plan["tag"]
    if spec.run_dir_for(camp, rid) is not None or (camp.runs_dir / (".staging-" + rid)).exists():
        raise config.Refused("runs/%s_* already exists; a run id is minted once" % rid)
    cwd = plan["cwd"] or "."
    if not (root / cwd).is_dir():
        raise config.Missing("cwd %s is not a directory under %s" % (cwd, root))
    rels, missing = manifest.discover_inputs(root, cwd, plan["command"], plan.get("ins") or [])
    if missing:
        raise config.Missing("%s: input(s) absent: %s" % (rid, ", ".join(missing)))
    estimate = float(plan.get("estimate") or 0.0)
    check_budget(camp, estimate, extra_core, extra_runs)

    tokens = manifest.split(plan["command"])
    app = camp.meta.get("app")
    cluster = plan.get("cluster") or "local"
    run = Run(
        run=rid, campaign=camp.id, tag=tag, group=plan.get("group"),
        replay_of=plan.get("replay_of"), proposal=plan["proposal"], hypothesis=plan["hypothesis"],
        cluster=cluster, command=plan["command"], cwd=cwd, env=dict(plan.get("env") or {}),
        inputs=manifest.describe_inputs(root, rels, settings.freeze_max_kb),
        qoi={}, verdict=None, judged=None,
    )

    if cluster == "local":
        np = manifest.ranks(plan["command"]) or 1
        env = dict(run.env)
        run.code = manifest.code_block(root, None, manifest.local_binary(tokens, app, root / cwd),
                                       manifest.local_python(tokens, env))
        run.host = socket.gethostname()
        run.local = {"np": np, "core_hours": None}
        run.outputs = {"dir": str((root / cwd).resolve()), "purge_risk": False, "kept": []}
        run.started = now_iso()
        run.identity = manifest.identity(run)
        if dry_run:
            _print_plan(run, "local:np%d" % np)
            print("[dry-run] cd %s && %s" % (root / cwd, plan["command"]))
            return 0
        run_dir = camp.runs_dir / ("%s_%s" % (rid, tag))
        run_dir.mkdir(parents=True)
        run.path = run_dir
        manifest.freeze(root, run_dir, run.inputs)
        manifest.save(run)
        if consume:
            spec.consume(camp.dir, consume, settings)
        hyp = ("replay_of: %s" % run.replay_of) if run.replay_of else ("tests: %s" % run.hypothesis)
        ledger.append_start(camp.dir / "LEDGER.md",
                            ledger.start_line(rid, tag, run.group, stamp(), "local:np%d" % np, hyp))
        code, seconds = localrun.launch(tokens, root / cwd, env, run_dir / "run.log")
        run.finished = now_iso()
        run.exit = code
        run.local["core_hours"] = localrun.core_hours(np, seconds)
        _kept_now(camp, run, run_dir)
        manifest.save(run)
        ledger.append_under(camp.dir / "LEDGER.md", rid,
                            ledger.done_line(stamp(), code, run.local["core_hours"]))
        print("%s exit=%d core-h=%s -> %s" % (rid, code, ledger.fmt_core_h(run.local["core_hours"]),
                                              run_dir.relative_to(root)))
        return 0 if code == 0 else 1

    cl = settings.cluster(cluster)
    remote = Remote(cl, settings, dry_run=dry_run)
    remote.require_connection()
    res = dispatch.resources(cl, plan["command"], plan.get("ntasks"), plan.get("walltime"),
                             plan.get("partition"))
    sub = root / config.app_submodule(app) if app else None
    local_sha = manifest._git(sub, "rev-parse", "HEAD") if sub is not None and sub.exists() else None
    prep = dispatch.prepare(remote, settings, root.name, app, local_sha=local_sha)
    python = None
    if tokens and manifest.PYTHON.match(Path(tokens[manifest.program_index(tokens)]).name):
        python = {"env": prep["module"], "version": None}
    run.code = manifest.code_block(root, prep["module"],
                                   {"path": prep["binary"], "built": None, "sha256": prep["binary_sha256"]},
                                   python)
    run.host = cl.host
    run.slurm = {"job": None, "partition": res["partition"], "nodes": res["nodes"],
                 "ntasks": res["ntasks"], "walltime": res["walltime"], "state": None, "core_hours": None}
    run.local = None
    wd = dispatch.workdir(settings, run)
    run.outputs = {"dir": wd, "purge_risk": wd.startswith("/scratch"), "kept": []}
    run.started = now_iso()
    run.identity = manifest.identity(run)
    staging = camp.runs_dir / (".staging-" + rid)
    if dry_run:
        _print_plan(run, "%s, %s tasks, %s" % (cluster, res["ntasks"], res["walltime"]))
        dispatch.submit(remote, settings, run, staging, prep, app)
        return 0
    staging.mkdir(parents=True)
    try:
        run.path = staging
        manifest.freeze(root, staging, run.inputs)
        manifest.save(run)
        job = dispatch.submit(remote, settings, run, staging, prep, app)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    run.slurm["job"] = int(job) if job and str(job).isdigit() else job
    run.slurm["state"] = "PENDING"
    run_dir = camp.runs_dir / ("%s_%s" % (rid, tag))
    staging.rename(run_dir)
    run.path = run_dir
    manifest.save(run)
    if consume:
        spec.consume(camp.dir, consume, settings)
    hyp = ("replay_of: %s" % run.replay_of) if run.replay_of else ("tests: %s" % run.hypothesis)
    ledger.append_start(camp.dir / "LEDGER.md",
                        ledger.start_line(rid, tag, run.group, stamp(), "%s:%s" % (cluster, job), hyp))
    print("%s submitted to %s as job %s -> %s" % (rid, cluster, job, run_dir.relative_to(root)))
    return 0


def plan_from_proposal(camp: Campaign, p) -> Dict[str, Any]:
    return {
        "run": p.id, "tag": p.tag, "group": p.group, "replay_of": None,
        "proposal": {"tests": p.tests, "because": list(p.because), "estimate_core_hours": p.estimate},
        "hypothesis": p.tests, "command": p.cmd, "cwd": p.cwd, "env": dict(p.env), "ins": list(p.ins),
        "cluster": p.cluster or camp.meta.get("cluster") or "local",
        "ntasks": p.ntasks, "walltime": p.walltime, "partition": p.partition,
        "estimate": p.estimate or 0.0,
    }
