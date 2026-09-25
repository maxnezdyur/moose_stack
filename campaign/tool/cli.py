"""The verbs. The CLI prints; library code prints only dry-run lines and progress.

    new <id>                 scaffold campaigns/<id>/ and the project's .claude links
    validate [<id>]          campaign.md, the manifests, LEDGER.md, FINDINGS.md; exit 2 on an error
    status [<id>] [--json]   one campaign, or every one under the root
    next-id [<id>]           the next run id
    tick [<id>] <D>          tick one proposal (the loop under within-budget, or --by <human>)
    run [<id>] <D>|--ticked  consume ticked entries: mint, freeze, launch or submit
    reconcile [<id>|--all]   squeue/sacct sync of every unfinished SLURM run
    collect [<id>] <D>       run the measures, write qoi.json
    verdict [<id>] <D> <w>   set the verdict, append the ledger verdict line
    note [<id>] <D> <text>   append a note line under the run's ledger entry
    close [<id>] F<n>        status done on a closes: yes finding; --abandon <reason>
    replay [<id>] <D>        the replay contract of formats/manifest.md
    bringup --cluster <c>    pin the project on the cluster, build the binary into the bincache
    spent [<id>]             spent over budget, as JSON
    doctor [<id>]            what is misconfigured

``<id>`` may be omitted inside ``campaigns/<id>/``. Every verb that writes
accepts ``--dry-run``. Exit codes: 0 ok, 1 a human should look, 2 a refused
write or a validation error, 3 a missing path or a bad configuration, 4 a
cluster did not answer (one ``connection_down:`` line).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import (__version__, collect as collect_mod, config, dispatch, findings, launch, ledger,
               manifest, reconcile as reconcile_mod, replay as replay_mod, spec, verdict as verdict_mod)
from .model import VERDICTS, Campaign, today
from .remote import Remote

OK, LOOK, REFUSED, MISSING, DOWN = 0, 1, 2, 3, 4

FINDING = re.compile(r"^F\d+$")

# The project-side links `new` makes, each pointing into the meta repo.
LINKS = (
    (".claude/skills/campaign", ".claude/skills/campaign"),
    (".claude/agents/campaign-loop.md", ".claude/agents/campaign-loop.md"),
    (".claude/hooks/session-context.sh", ".claude/hooks/session-context.sh"),
)
LEASE_IGNORE = "campaigns/*/.factory-lease"
HOOK_SNIPPET = """{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|compact",
        "hooks": [
          {
            "type": "command",
            "command": "\\"$CLAUDE_PROJECT_DIR\\"/.claude/hooks/session-context.sh"
          }
        ]
      }
    ]
  }
}"""


# --------------------------------------------------------------------------
# argument helpers
# --------------------------------------------------------------------------


def _root(args, for_new: bool = False) -> Path:
    if args.root or not for_new:
        return config.find_root(args.root)
    try:
        return config.find_root(None)
    except config.Missing:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        return Path(top.stdout.strip()) if top.returncode == 0 and top.stdout.strip() else Path.cwd()


def _classify(tokens: List[str], words: Tuple[str, ...] = ()) -> Dict[str, Any]:
    """Split loose positionals into campaign id, run ids, findings, words and free text."""
    out: Dict[str, Any] = {"id": None, "runs": [], "findings": [], "word": None, "text": []}
    free_text = "text" in words
    for t in tokens:
        if free_text and out["runs"]:
            out["text"].append(t)
        elif config.RUN_ID.match(t):
            out["runs"].append(t)
        elif FINDING.match(t):
            out["findings"].append(t)
        elif t in words:
            out["word"] = t
        elif out["id"] is None:
            out["id"] = t
        else:
            out["text"].append(t)
    return out


def _campaign(args, cid: Optional[str], settings: config.Settings) -> Campaign:
    root = _root(args)
    d = config.campaign_dir(root, cid)
    return spec.load(d, settings)


def _one_run(camp: Campaign, rid: Optional[str]):
    if not rid:
        raise config.Refused("name a run id, D plus three digits")
    d = spec.run_dir_for(camp, rid)
    if d is None:
        raise config.Missing("%s has no runs/%s_* directory" % (camp.id, rid))
    return manifest.load(d)


def _require_valid(camp: Campaign) -> None:
    if camp.errors:
        for e in camp.errors:
            print("error: " + e, file=sys.stderr)
        raise config.Refused("%s/campaign.md does not validate; run `campaign validate %s`"
                             % (camp.id, camp.id))


# --------------------------------------------------------------------------
# new
# --------------------------------------------------------------------------


def _fill(text: str, cid: str, project: str) -> str:
    day = today().isoformat()
    return (text.replace("<id>", cid).replace("<project>", project).replace("<title>", cid)
            .replace("<campaign>", cid).replace("<YYYY-MM-DD>", day))


def _lease_ignored(root: Path) -> bool:
    gi = root / ".gitignore"
    return gi.is_file() and LEASE_IGNORE in [l.strip() for l in gi.read_text().splitlines()]


def cmd_new(args, settings: config.Settings) -> int:
    cid = config.validate_campaign_id(args.id)
    root = _root(args, for_new=True)
    d = root / "campaigns" / cid
    if d.exists():
        raise config.Refused("%s exists; a campaign is scaffolded once" % d)
    tdir = config.templates_dir()
    files = {"campaign.md": "campaign.md", "LEDGER.md": "LEDGER.md", "FINDINGS.md": "FINDINGS.md",
             "handoff.md": "handoff.md"}
    for src in files.values():
        if not (tdir / src).is_file():
            raise config.Missing("template %s is absent" % (tdir / src))
    links = [(root / rel, settings.meta_repo / target) for rel, target in LINKS]
    if args.dry_run:
        print("[dry-run] would create %s/ with %s and runs/" % (d, ", ".join(files)))
        if not _lease_ignored(root):
            print("[dry-run] would append %s to %s" % (LEASE_IGNORE, root / ".gitignore"))
        for link, target in links:
            if not os.path.lexists(link):
                print("[dry-run] would link %s -> %s" % (link, target))
        return OK
    (d / "runs").mkdir(parents=True)
    for dst, src in files.items():
        config.write_text_atomic(d / dst, _fill((tdir / src).read_text(), cid, root.name))
    print("created %s" % d)
    if not _lease_ignored(root):
        gi = root / ".gitignore"
        text = gi.read_text() if gi.is_file() else ""
        if text and not text.endswith("\n"):
            text += "\n"
        config.write_text_atomic(gi, text + LEASE_IGNORE + "\n")
        print("added %s to %s" % (LEASE_IGNORE, gi))
    for link, target in links:
        if os.path.lexists(link):
            continue
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, link)
        print("linked %s -> %s%s" % (link, target, "" if target.exists() else "  (dangling for now)"))
    return OK


# --------------------------------------------------------------------------
# validate, status, next-id, spent
# --------------------------------------------------------------------------


def cmd_validate(args, settings: config.Settings) -> int:
    c = _classify(args.args)
    root = _root(args)
    d = config.campaign_dir(root, c["id"])
    errors, warnings = spec.validate(d, settings)
    for w in warnings:
        print("warning: " + w)
    for e in errors:
        print("error: " + e)
    if errors:
        print("%s: %d error(s)" % (d.name, len(errors)))
        return REFUSED
    print("%s: ok" % d.name)
    return OK


def run_state(r) -> str:
    if not r.started:
        return "queued"
    if not r.done:
        return "running"
    if r.verdict == "failed":
        return "failed"
    if r.verdict:
        return "judged"
    if not r.qoi:
        return "finished"
    return "collected"


def _summary(camp: Campaign) -> Dict[str, Any]:
    runs = manifest.load_all(camp.runs_dir)
    counts = {v: 0 for v in VERDICTS}
    counts["unjudged"] = 0
    for r in runs:
        counts[r.verdict if r.verdict in VERDICTS else "unjudged"] += 1
    fs = findings.load(camp.dir / "FINDINGS.md")
    closing = next((f for f in fs if f.closes), None)
    return {
        "frontmatter": camp.meta,
        "spent": {k: v for k, v in launch.spent(camp).items() if k not in ("campaign", "exact_core_hours")},
        "verdicts": counts,
        "runs": [{"id": r.run, "tag": r.tag, "group": r.group, "state": run_state(r),
                  "verdict": r.verdict, "qoi": r.qoi or {}} for r in runs],
        "findings": {"count": len(fs), "closing": closing.id if closing else None,
                     "last": ("%s. %s" % (fs[-1].id, fs[-1].claim)) if fs else None},
        "proposals": {"ticked": [p.id for p in camp.proposals if p.ticked],
                      "pending": [p.id for p in camp.proposals if not p.ticked]},
    }


def _num(v: Any) -> str:
    if v is None:
        return "-"
    return ("%g" % v) if isinstance(v, float) else str(v)


def _print_status(camp: Campaign, s: Dict[str, Any]) -> None:
    m = camp.meta
    sp = s["spent"]
    v = s["verdicts"]
    print("%s  %s  autonomy=%s  cluster=%s  app=%s" % (camp.id, m.get("status", "-"), m.get("autonomy", "-"),
                                                      m.get("cluster", "-"), m.get("app", "-")))
    print("  question   %s" % m.get("question", "-"))
    print("  spent      %s / %s core-h, %s / %s runs, %s / %s days"
          % (_num(sp["core_hours"]["spent"]), _num(sp["core_hours"]["budget"]),
             _num(sp["runs"]["spent"]), _num(sp["runs"]["budget"]),
             _num(sp["wall_days"]["spent"]), _num(sp["wall_days"]["budget"])))
    print("  verdicts   %d supported, %d refuted, %d inconclusive, %d failed, %d unjudged"
          % (v["supported"], v["refuted"], v["inconclusive"], v["failed"], v["unjudged"]))
    f = s["findings"]
    print("  findings   %d, closing: %s, last: %s" % (f["count"], f["closing"] or "-", f["last"] or "-"))
    p = s["proposals"]
    print("  proposals  %d ticked (%s), %d pending (%s)" % (len(p["ticked"]), ", ".join(p["ticked"]) or "-",
                                                          len(p["pending"]), ", ".join(p["pending"]) or "-"))
    running = [r["id"] for r in s["runs"] if r["state"] in ("running", "queued")]
    print("  running    %s" % (", ".join(running) or "-"))


def cmd_status(args, settings: config.Settings) -> int:
    c = _classify(args.args)
    root = _root(args)
    cid = c["id"] or config.campaign_from_cwd(root)
    dirs = [config.campaign_dir(root, cid)] if cid else config.list_campaigns(root)
    if not dirs:
        raise config.Missing("no campaigns under %s/campaigns" % root)
    out = []
    for d in dirs:
        camp = spec.load(d, settings)
        s = _summary(camp)
        if args.json:
            out.append(dict(campaign=camp.id, **s))
        else:
            _print_status(camp, s)
    if args.json:
        print(json.dumps(out[0] if cid else out, indent=2, default=str))
    return OK


def cmd_next_id(args, settings: config.Settings) -> int:
    c = _classify(args.args)
    print(spec.next_id(_campaign(args, c["id"], settings)))
    return OK


def cmd_spent(args, settings: config.Settings) -> int:
    c = _classify(args.args)
    s = launch.spent(_campaign(args, c["id"], settings))
    s.pop("exact_core_hours", None)
    print(json.dumps(s, indent=2))
    return OK


# --------------------------------------------------------------------------
# tick, run
# --------------------------------------------------------------------------


def cmd_tick(args, settings: config.Settings) -> int:
    c = _classify(args.args)
    camp = _campaign(args, c["id"], settings)
    _require_valid(camp)
    if len(c["runs"]) != 1:
        raise config.Refused("tick one run id")
    p = camp.proposal(c["runs"][0])
    if p is None:
        raise config.Refused("%s is not an entry under ## Proposed" % c["runs"][0])
    by = args.by
    human = bool(by) and by != "loop"
    if not human and camp.meta.get("autonomy") != "within-budget":
        raise config.Refused("autonomy is %s: only a human ticks; tick the box in campaign.md "
                             "or pass --by <your name>" % camp.meta.get("autonomy"))
    if p.ticked:
        print("%s is already ticked" % p.id)
        return OK
    hits = spec.constraint_hits(camp, p.cmd or "")
    if hits:
        raise config.Refused("%s sets frozen knob(s) %s from ## Constraints" % (p.id, ", ".join(hits)))
    if not human:
        others = sum(x.estimate or 0.0 for x in camp.proposals if x.ticked)
        launch.check_budget(camp, p.estimate or 0.0, extra_core=others)
    if args.dry_run:
        print("[dry-run] would tick %s in %s/campaign.md" % (p.id, camp.id))
        return OK
    config.write_text_atomic(camp.dir / "campaign.md", spec.tick_text(camp, p))
    print("ticked %s" % p.id)
    return OK


def cmd_run(args, settings: config.Settings) -> int:
    c = _classify(args.args)
    camp = _campaign(args, c["id"], settings)
    _require_valid(camp)
    if args.ticked:
        todo = [p for p in camp.proposals if p.ticked]
        if not todo:
            print("no ticked entry under ## Proposed")
            return OK
    else:
        if len(c["runs"]) != 1:
            raise config.Refused("name one run id, or pass --ticked")
        p = camp.proposal(c["runs"][0])
        if p is None:
            if spec.run_dir_for(camp, c["runs"][0]) is not None:
                raise config.Refused("runs/%s_* already exists; a run id is minted once" % c["runs"][0])
            raise config.Refused("%s is not an entry under ## Proposed" % c["runs"][0])
        todo = [p]
    rc = OK
    extra_core, extra_runs = 0.0, 0
    for p in todo:
        if not p.ticked:
            raise config.Refused("%s is not ticked; tick it (- [x]) to approve it" % p.id)
        hits = spec.constraint_hits(camp, p.cmd or "")
        if hits:
            raise config.Refused("%s sets frozen knob(s) %s from ## Constraints" % (p.id, ", ".join(hits)))
        plan = launch.plan_from_proposal(camp, p)
        rc = max(rc, launch.launch(camp, settings, plan, dry_run=args.dry_run, consume=p.id,
                                   extra_core=extra_core, extra_runs=extra_runs))
        if args.dry_run:
            extra_core += p.estimate or 0.0
            extra_runs += 1
        camp = spec.load(camp.dir, settings)
    return rc


# --------------------------------------------------------------------------
# reconcile, collect, verdict, note, close, replay
# --------------------------------------------------------------------------


def cmd_reconcile(args, settings: config.Settings) -> int:
    c = _classify(args.args)
    root = _root(args)
    cid = None if args.all else (c["id"] or config.campaign_from_cwd(root))
    dirs = [config.campaign_dir(root, cid)] if cid else config.list_campaigns(root)
    rc = OK
    for d in dirs:
        camp = spec.load(d, settings)
        runs = reconcile_mod.unfinished(camp)
        if not runs:
            print("%s: no unfinished SLURM run" % camp.id)
            continue
        for rid, what in reconcile_mod.reconcile(camp, settings, dry_run=args.dry_run).items():
            print("%s %s: %s" % (camp.id, rid, what))
            if what in ("failed", "unknown"):
                rc = LOOK
    return rc


def cmd_collect(args, settings: config.Settings) -> int:
    c = _classify(args.args)
    camp = _campaign(args, c["id"], settings)
    _require_valid(camp)
    run = _one_run(camp, (c["runs"] or [None])[0])
    qoi, problems = collect_mod.collect(camp, run, dry_run=args.dry_run)
    print(json.dumps(qoi))
    for p in problems:
        print("warning: " + p, file=sys.stderr)
    if run.replay_of and not args.dry_run:
        print((run.path / "note.md").read_text().rstrip())
    return LOOK if problems else OK


def cmd_verdict(args, settings: config.Settings) -> int:
    c = _classify(args.args, VERDICTS)
    camp = _campaign(args, c["id"], settings)
    run = _one_run(camp, (c["runs"] or [None])[0])
    if not c["word"]:
        raise config.Refused("name a verdict: %s" % ", ".join(VERDICTS))
    by = args.by or os.environ.get("USER") or "human"
    line = verdict_mod.judge(camp, run, c["word"], args.finding, by, dry_run=args.dry_run)
    if not args.dry_run:
        print(line.strip())
    return OK


def cmd_note(args, settings: config.Settings) -> int:
    c = _classify(args.args, ("text",))
    camp = _campaign(args, c["id"], settings)
    if len(c["runs"]) != 1:
        raise config.Refused("name one run id")
    text = " ".join(c["text"])
    line = ledger.note_line(text)
    if args.dry_run:
        print("[dry-run] would append under %s: %s" % (c["runs"][0], line.strip()))
        return OK
    ledger.append_under(camp.dir / "LEDGER.md", c["runs"][0], line)
    print(line.strip())
    return OK


def _append_decision(handoff: Path, line: str) -> str:
    if not handoff.is_file():
        raise config.Missing("%s is absent" % handoff)
    lines = handoff.read_text().split("\n")
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "## Decisions")
    except StopIteration:
        raise config.Refused("%s has no ## Decisions section" % handoff.name)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    at = end
    while at > start + 1 and not lines[at - 1].strip():
        at -= 1
    lines.insert(at, line)
    return "\n".join(lines)


def cmd_close(args, settings: config.Settings) -> int:
    c = _classify(args.args)
    camp = _campaign(args, c["id"], settings)
    day = today()
    if args.abandon:
        reason = " ".join(args.abandon.split())
        if not reason:
            raise config.Refused("--abandon needs a reason")
        closed: Dict[str, Any] = {"date": day}
        if c["findings"]:
            closed["finding"] = c["findings"][0]
        text = spec.set_frontmatter(camp, {"status": "abandoned", "closed": closed, "updated": day})
        decision = "- %s: abandoned %s because %s" % (day.isoformat(), camp.id, reason)
        handoff = _append_decision(camp.dir / "handoff.md", decision)
        if args.dry_run:
            print("[dry-run] would set status abandoned, closed.date %s, and append to handoff.md: %s"
                  % (day, decision))
            return OK
        config.write_text_atomic(camp.dir / "campaign.md", text)
        config.write_text_atomic(camp.dir / "handoff.md", handoff)
        print("%s abandoned" % camp.id)
        return OK
    if len(c["findings"]) != 1:
        raise config.Refused("name the closing finding, F<n>, or pass --abandon <reason>")
    fid = c["findings"][0]
    f = findings.get(camp.dir / "FINDINGS.md", fid)
    if f is None:
        raise config.Refused("%s is not a section of FINDINGS.md" % fid)
    if not f.closes:
        raise config.Refused("%s says closes: no; only a closes: yes finding closes a campaign" % fid)
    text = spec.set_frontmatter(camp, {"status": "done", "closed": {"date": day, "finding": fid},
                                       "updated": day})
    if args.dry_run:
        print("[dry-run] would set status done, closed {date: %s, finding: %s}" % (day, fid))
        return OK
    config.write_text_atomic(camp.dir / "campaign.md", text)
    print("%s done on %s" % (camp.id, fid))
    return OK


def cmd_replay(args, settings: config.Settings) -> int:
    c = _classify(args.args)
    camp = _campaign(args, c["id"], settings)
    _require_valid(camp)
    run = _one_run(camp, (c["runs"] or [None])[0])
    return replay_mod.replay(camp, settings, run, restore=args.restore, strict=args.strict,
                             cluster=args.cluster, dry_run=args.dry_run)


# --------------------------------------------------------------------------
# bringup, doctor
# --------------------------------------------------------------------------


def cmd_bringup(args, settings: config.Settings) -> int:
    c = _classify(args.args)
    root = _root(args)
    app = args.app
    if not app:
        cid = c["id"] or config.campaign_from_cwd(root)
        if not cid:
            raise config.Refused("name a campaign or pass --app")
        app = spec.load(config.campaign_dir(root, cid), settings).meta.get("app")
    config.app_build_dir(app)
    remote = Remote(settings.cluster(args.cluster), settings, dry_run=args.dry_run)
    prep = dispatch.bringup(remote, settings, root, app)
    print("%s on %s: checkout %s at %s" % (root.name, args.cluster, prep["stack"], str(prep["head"])[:12]))
    print("  module  %s" % prep["module"])
    print("  binary  %s%s" % (prep["binary"], ("  (build job %s)" % prep["build_job"]) if prep["build_job"] else ""))
    return OK


def _hook_registered(settings_json: Path) -> Optional[bool]:
    if not settings_json.is_file():
        return None
    try:
        data = json.loads(settings_json.read_text())
    except ValueError:
        return False
    for block in ((data.get("hooks") or {}).get("SessionStart") or []):
        for h in (block.get("hooks") or []):
            if "session-context.sh" in str(h.get("command", "")):
                return True
    return False


def cmd_doctor(args, settings: config.Settings) -> int:
    bad = 0

    def row(ok: Optional[bool], what: str, detail: str = "") -> None:
        nonlocal bad
        word = "ok  " if ok else ("warn" if ok is None else "FAIL")
        if ok is False:
            bad += 1
        print("%s  %s%s" % (word, what, (": " + detail) if detail else ""))

    print("campaign %s  config %s" % (__version__, settings.config_file or "(none; defaults)"))
    row(sys.version_info >= (3, 11), "python %s" % sys.version.split()[0], sys.executable)
    try:
        import yaml  # noqa: F401
        row(True, "PyYAML")
    except ImportError:
        row(False, "PyYAML", "pip install PyYAML")
    if settings.unknown_keys:
        row(None, "config", "unknown [campaign] keys: %s" % ", ".join(settings.unknown_keys))
    for name, cl in sorted(settings.clusters.items()):
        if args.offline:
            row(None, "cluster %s (%s)" % (name, cl.host), "not probed (--offline)")
        else:
            reach = Remote(cl, settings).check_connection()
            row(reach, "cluster %s (%s)" % (name, cl.host), "" if reach else "ssh BatchMode probe failed")
    try:
        root = _root(args)
    except config.Missing as exc:
        row(None, "project root", str(exc))
        return LOOK if bad else OK
    row(True, "project root %s" % root)
    for rel, _target in LINKS:
        link = root / rel
        if not os.path.lexists(link):
            row(False, rel, "absent; `campaign new` makes it")
        elif not link.exists():
            row(False, rel, "dangling -> %s" % os.readlink(link))
        else:
            row(True, rel)
    row(_lease_ignored(root), ".gitignore carries %s" % LEASE_IGNORE,
        "" if _lease_ignored(root) else "append that line; `campaign new` does it")
    reg = _hook_registered(root / ".claude" / "settings.json")
    if reg:
        row(True, ".claude/settings.json registers session-context.sh for SessionStart")
    else:
        row(False, ".claude/settings.json does not register session-context.sh for SessionStart",
            "merge this into %s:\n%s" % (root / ".claude" / "settings.json", HOOK_SNIPPET))
    c = _classify(args.args)
    cid = c["id"] or config.campaign_from_cwd(root)
    dirs = [config.campaign_dir(root, cid)] if cid else config.list_campaigns(root)
    for d in dirs:
        errors, _w = spec.validate(d, settings)
        row(not errors, "campaign %s validates" % d.name, "%d error(s)" % len(errors) if errors else "")
        camp = spec.load(d, settings)
        app = camp.meta.get("app")
        if app in config.APPS:
            from .localrun import local_binary_path
            b = local_binary_path(root, app)
            local = camp.meta.get("cluster") == "local"
            row(True if b.is_file() else (False if local else None), "binary %s" % b,
                "" if b.is_file() else "absent")
    return LOOK if bad else OK


# --------------------------------------------------------------------------
# argparse
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", help="the project repository (default: nearest parent holding campaigns/)")
    writes = argparse.ArgumentParser(add_help=False)
    writes.add_argument("--dry-run", action="store_true", help="print every write, ssh, rsync and sbatch; do nothing")

    p = argparse.ArgumentParser(prog="campaign", description="Open-ended experimental work: one question, "
                                "a stop condition, a budget, an append-only record.")
    p.add_argument("--version", action="version", version="campaign %s" % __version__)
    sub = p.add_subparsers(dest="verb", required=True)
    p.verb_parsers = sub.choices  # type: ignore[attr-defined]

    s = sub.add_parser("new", parents=[common, writes], help="scaffold campaigns/<id>/")
    s.add_argument("id")
    for verb, helptext in (("validate", "check campaign.md, the manifests, the ledger, the findings"),
                           ("next-id", "print the next run id"),
                           ("spent", "the spent numbers as JSON")):
        s = sub.add_parser(verb, parents=[common], help=helptext)
        s.add_argument("args", nargs="*")
    s = sub.add_parser("status", parents=[common], help="status of one campaign or every one")
    s.add_argument("args", nargs="*")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("tick", parents=[common, writes], help="tick one proposal")
    s.add_argument("args", nargs="*")
    s.add_argument("--by", help="who ticks: loop, or a human's name")
    s = sub.add_parser("run", parents=[common, writes], help="consume ticked proposals and launch them")
    s.add_argument("args", nargs="*")
    s.add_argument("--ticked", action="store_true", help="every ticked entry")
    s = sub.add_parser("reconcile", parents=[common, writes], help="squeue/sacct sync of unfinished SLURM runs")
    s.add_argument("args", nargs="*")
    s.add_argument("--all", action="store_true")
    s = sub.add_parser("collect", parents=[common, writes], help="run the measures, write qoi.json")
    s.add_argument("args", nargs="*")
    s = sub.add_parser("verdict", parents=[common, writes], help="judge one run")
    s.add_argument("args", nargs="*")
    s.add_argument("--finding")
    s.add_argument("--by")
    s = sub.add_parser("note", parents=[common, writes], help="append a note line under a run's ledger entry")
    s.add_argument("args", nargs="*")
    s = sub.add_parser("close", parents=[common, writes], help="close a campaign on a closes: yes finding")
    s.add_argument("args", nargs="*")
    s.add_argument("--abandon", metavar="REASON")
    s = sub.add_parser("replay", parents=[common, writes], help="replay one run from its manifest")
    s.add_argument("args", nargs="*")
    s.add_argument("--restore", action="store_true")
    s.add_argument("--strict", action="store_true")
    s.add_argument("--cluster")
    s = sub.add_parser("bringup", parents=[common, writes], help="pin the project and build the binary on a cluster")
    s.add_argument("args", nargs="*")
    s.add_argument("--cluster", required=True)
    s.add_argument("--app")
    s = sub.add_parser("doctor", parents=[common], help="what is misconfigured")
    s.add_argument("args", nargs="*")
    s.add_argument("--offline", action="store_true", help="skip the ssh probes")
    return p


VERBS = {
    "new": cmd_new, "validate": cmd_validate, "status": cmd_status, "next-id": cmd_next_id,
    "spent": cmd_spent, "tick": cmd_tick, "run": cmd_run, "reconcile": cmd_reconcile,
    "collect": cmd_collect, "verdict": cmd_verdict, "note": cmd_note, "close": cmd_close,
    "replay": cmd_replay, "bringup": cmd_bringup, "doctor": cmd_doctor,
}


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if argv and argv[0] in VERBS:
        # Intermixed, so `verdict D014 supported --finding F10 <id>` parses in any order.
        args = parser.verb_parsers[argv[0]].parse_intermixed_args(argv[1:])  # type: ignore[attr-defined]
        args.verb = argv[0]
    else:
        args = parser.parse_args(argv)
    try:
        settings = config.load()
        return VERBS[args.verb](args, settings)
    except config.ConnectionDown as exc:
        print("connection_down: %s" % exc)
        return DOWN
    except config.Look as exc:
        print("campaign: %s" % exc, file=sys.stderr)
        return LOOK
    except config.Refused as exc:
        print("campaign: refused: %s" % exc, file=sys.stderr)
        return REFUSED
    except config.Missing as exc:
        print("campaign: %s" % exc, file=sys.stderr)
        return MISSING


if __name__ == "__main__":
    sys.exit(main())
