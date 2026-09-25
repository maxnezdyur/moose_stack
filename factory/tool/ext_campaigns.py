"""The campaigns adapter: experimental campaigns as first-class cards on the board.

What this extension is
----------------------

A campaign lives inside the project repository that holds its inputs, as
``<root>/campaigns/<id>/``. The roots come from the ``campaign_roots`` setting
(``$FACTORY_CAMPAIGN_ROOTS``, colon separated). The contract is
``campaign/README.md`` and ``campaign/formats/``; this module reads it and
writes nothing into a campaign directory, ever:

    campaign.md       the question, the stop condition, the budget, the queue
    LEDGER.md         one entry per run: start line, ``done``, ``verdict``, ``note``
    FINDINGS.md       one ``## F<n>.`` section per finding
    handoff.md        parsed by ``ext_handoff.parse``, the feature reader
    gallery/          scanned by ``ext_gallery.scan``, linked as ``Gallery/<id>``
    runs/*/manifest.yaml   the spent numbers: core-hours, run count, running runs

It renders:

    Home.md               the campaign cards inside the six posture groups (through
                          the core ``board_cards`` hook) plus one ``## Campaigns`` table
    Board.html            a full campaign card in the same six columns
    Campaigns/<id>.md     one note per campaign, with the four markers and the two
                          prose regions of a feature note

Structure copied from the studies adapter it replaces: ``collect`` only loads,
``outputs`` writes the notes once per ``factory board``, ``home_sections`` adds
the table, ``doctor_checks`` and the read-only ``campaigns`` verb.

Rules
-----

1. **No clock in a note.** Every line is a function of the campaign files, the
   lease, the live sessions and the timeline. ``updated`` is a content stamp
   through ``ctx.state``. The one clock read is ``ctx.now`` in :func:`decide`,
   for the ``unjudged-run`` posture rule, never printed as an age.
2. **The spent budget is computed, never stored.** Core-hours are the sum of
   ``slurm.core_hours`` or ``local.core_hours`` over every manifest; runs are
   the ``runs/`` directories; the wall day counts from ``created`` to the
   newest date the files themselves carry.
3. **The proposal boxes are text on the note, never live checkboxes.** The tick
   lives in ``campaign.md`` and ``campaign run`` reads it there. A ``- [ ]`` on a
   regenerated note would be erased by the next board run and read by nobody,
   so the note prints them as code spans and links the real file through
   ``Specs/<id>/campaign.md``, where Obsidian writes through to the repo.

Posture
-------

In this order, the first that applies:

    parked      status draft or paused
    done        status done or abandoned
    needs-you   campaign.md does not parse (unreadable); or the spent core-hours or
                runs reach the budget, or the wall day passes it (over-budget); or a
                ledger ``done`` older than a day by ``ctx.now`` has no verdict
                (unjudged-run); or the last finding refutes an earlier one and no
                queued proposal cites it (refuted); or an entry is unticked under
                ``autonomy: propose-only`` (proposal-pending)
    running     the lease is live (or its liveness is unknown), or a manifest has
                ``started`` and no ``finished``
    waiting     the newest ledger note says connection_down, or the lease is stale
    ready       at least one proposal is ticked and no lease is held
    waiting     otherwise

Flags, the closed vocabulary of this card kind:

    proposal-pending   an entry under ## Proposed is unticked and autonomy is propose-only
    over-budget        spent core-hours or runs reached the budget, or the wall day passed it
    refuted            the last finding refutes an earlier one and no proposal cites it
    unjudged-run       a ledger run has done for over a day and no verdict
    lease-stale        <campaign dir>/.factory-lease survives its owner
    handoff-stale      the ledger or findings are more than two days newer than handoff.md
    unreadable         campaign.md has no parseable frontmatter
    marker-missing     the note lost a factory marker, so it was not rewritten
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config, derive, ext_gallery, ext_handoff, probe, render, snapshot
from .model import (
    DONE,
    NEEDS_YOU,
    PARKED,
    POSTURE,
    READY,
    RUNNING,
    WAITING,
    BoardCard,
    NextAction,
)

try:                                  # PyYAML is the one non-stdlib dependency.
    import yaml
except Exception:                     # pragma: no cover - doctor reports it
    yaml = None                       # type: ignore[assignment]

KIND = "campaign"
NOTE_FOLDER = "Campaigns"
CAMPAIGNS_REL = "campaigns"

CAMPAIGN_MD = "campaign.md"
LEDGER_MD = "LEDGER.md"
FINDINGS_MD = "FINDINGS.md"
HANDOFF_MD = "handoff.md"
GALLERY_REL = "gallery"
RUNS_REL = "runs"
MANIFEST = "manifest.yaml"

SECTIONS: Tuple[str, ...] = ("Hypothesis", "Constraints", "Measures", "Proposed")
VERDICTS: Tuple[str, ...] = ("supported", "refuted", "inconclusive", "failed")

PARKED_STATUS = ("draft", "paused")
DONE_STATUS = ("done", "abandoned")

UNJUDGED_SECONDS = 86400          # a done run with no verdict for this long needs you
HANDOFF_STALE_DAYS = 2            # same threshold as a feature's handoff-stale
LEDGER_ON_NOTE = 3
TIMELINE_ON_NOTE = 12
SNAPSHOT_NAME = "_campaigns.json"  # under factory/state/; "_" keeps Store.features blind to it

FLAGS: Tuple[str, ...] = (
    "proposal-pending",
    "over-budget",
    "refuted",
    "unjudged-run",
    "lease-stale",
    "handoff-stale",
    "unreadable",
    "marker-missing",
)

FLAG_WHY: Dict[str, str] = {
    "proposal-pending": "an entry under `## Proposed` is unticked and autonomy is propose-only",
    "over-budget": "the spent core-hours or runs reached the budget, or the wall day passed it",
    "refuted": "the last finding refutes an earlier one and no queued proposal cites it",
    "unjudged-run": "a run has a `done` line for over a day and no verdict",
    "lease-stale": "a .factory-lease survives in the campaign directory whose owner is gone",
    "handoff-stale": "the ledger or the findings are more than two days newer than handoff.md",
    "unreadable": "campaign.md has no parseable frontmatter",
    "marker-missing": "the note lost a factory marker, so it was not rewritten",
}

POSTURE_ORDER: Dict[str, int] = {p: i for i, p in enumerate(POSTURE)}

HEAD_BEGIN, HEAD_END, BODY_BEGIN, BODY_END = probe.MARKERS
EMPTY_HUMAN = "\n\n## Notes\n\n\n"

_PROPOSAL = re.compile(r"^-\s+\[( |x|X)\]\s+(D\d{3})\b\s*(.*)$")
_SUB = re.compile(r"^\s+-\s+([A-Za-z_]+)\s*:\s*(.*)$")
_LEDGER_START = re.compile(r"^- (D\d{3}) \| (.*)$")
_LEDGER_SUB = re.compile(r"^\s+- (done|verdict|note)\b:?\s*(.*)$")
_FINDING = re.compile(r"^##\s+(F\d+)\.\s*(.*?)\s*$")
_FINDING_KEY = re.compile(r"^-\s+([a-z_]+)\s*:\s*(.*)$")
_LEDGER_STAMP = re.compile(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$")
_KV = re.compile(r"([a-z_-]+)=(\S+)")
_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")
_REF = re.compile(r"\b([FD]\d+)\b")


# --------------------------------------------------------------------------
# The campaign
# --------------------------------------------------------------------------


@dataclass
class Campaign:
    """One read-only projection of a campaign directory. Derived, never stored."""

    id: str
    root: str = ""                    # the project repository root
    dir: str = ""                     # <root>/campaigns/<id>
    readable: bool = False
    fm: Dict[str, Any] = field(default_factory=dict)
    title: str = ""
    project: str = ""
    question: str = ""
    stop: str = ""
    status: str = ""
    autonomy: str = ""
    cluster: str = ""
    app: str = ""
    created: str = ""
    updated: str = ""
    closed: Dict[str, Any] = field(default_factory=dict)
    budget_core_hours: Optional[float] = None
    budget_wall_days: Optional[int] = None
    budget_runs: Optional[int] = None
    missing_sections: List[str] = field(default_factory=list)
    proposals: List[Dict[str, Any]] = field(default_factory=list)
    ledger: List[Dict[str, Any]] = field(default_factory=list)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    manifests: List[Dict[str, Any]] = field(default_factory=list)
    runs: int = 0
    spent_core_hours: float = 0.0
    wall_day: Optional[int] = None
    verdicts: Dict[str, int] = field(default_factory=dict)
    handoff: Dict[str, Any] = field(default_factory=dict)
    gallery: Dict[str, Any] = field(default_factory=dict)
    lease: Optional[Dict[str, Any]] = None
    lease_state: str = "none"
    sessions: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    posture: str = PARKED
    flags: List[str] = field(default_factory=list)
    next_action: NextAction = field(default_factory=NextAction)
    short: str = ""
    card: Optional[BoardCard] = None

    # ---- paths -----------------------------------------------------------

    def path(self, name: str) -> Path:
        return Path(self.dir) / name

    # ---- conveniences ----------------------------------------------------

    def has(self, flag: str) -> bool:
        return flag in self.flags

    def add_flag(self, flag: str) -> None:
        if flag not in self.flags:
            self.flags.append(flag)
        if self.card is not None:
            self.card.add_flag(flag)

    def ticked(self) -> List[Dict[str, Any]]:
        return [p for p in self.proposals if p.get("ticked")]

    def pending(self) -> List[Dict[str, Any]]:
        return [p for p in self.proposals if not p.get("ticked")]

    def last_finding(self) -> Optional[Dict[str, Any]]:
        return self.findings[-1] if self.findings else None

    def closing_finding(self) -> Optional[Dict[str, Any]]:
        for f in self.findings:
            if f.get("closes"):
                return f
        return None

    def unfinished(self) -> List[Dict[str, Any]]:
        return [m for m in self.manifests if m.get("started") and not m.get("finished")]


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def launcher(cfg: Any) -> str:
    """The campaign CLI, as a copyable path. Printed only, never executed."""
    return render.tilde(Path(cfg.repo_root) / "campaign" / "campaign")


def factory_launcher(cfg: Any) -> str:
    return render.tilde(Path(cfg.repo_root) / "factory" / "factory")


def _float(value: Any) -> Optional[float]:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _int(value: Any) -> Optional[int]:
    f = _float(value)
    return int(f) if f is not None else None


def _text(value: Any) -> str:
    """One line of frontmatter text. A folded ``>`` block arrives with newlines."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def _date(value: Any) -> str:
    """``YYYY-MM-DD`` from a YAML date, an ISO stamp or a ledger stamp."""
    text = str(value or "").strip()
    m = _LEDGER_STAMP.match(text)
    if m:
        return "%s-%s-%s" % (m.group(1), m.group(2), m.group(3))
    return text[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", text) else ""


def ledger_iso(stamp: str) -> str:
    """``20260922T122917Z`` as ``2026-09-22T12:29:17Z``, or ``""``."""
    m = _LEDGER_STAMP.match(str(stamp or "").strip())
    if not m:
        return ""
    return "%s-%s-%sT%s:%s:%sZ" % m.groups()


def _day_number(date_text: str) -> Optional[int]:
    ts = derive.ts_of(date_text) if date_text else None
    return int(ts // 86400) if ts is not None else None


def _hours(value: float) -> str:
    return "%.1f" % (value,)


def _num(value: Optional[float]) -> str:
    """A budget as its author wrote it: ``60``, not ``60.0``."""
    if value is None:
        return "?"
    return ("%d" % value) if float(value).is_integer() else ("%s" % value)


def _read(path: Path) -> Tuple[Optional[str], bool]:
    return probe._read_text(path)


def _contains(parent: Path, child: Path) -> bool:
    return ext_gallery._contains(parent, child)


# --------------------------------------------------------------------------
# Parsing: one function per file, each never raises
# --------------------------------------------------------------------------


def split_frontmatter(text: str) -> Tuple[Optional[Dict[str, Any]], str, str]:
    """``(mapping or None, body, error)``."""
    m = probe._FM.match(text or "")
    if not m:
        return (None, text or "", "no --- frontmatter block")
    body = (text or "")[m.end():]
    if yaml is None:
        return (None, body, "PyYAML is not importable")
    try:
        data = yaml.safe_load(m.group(1))
    except Exception as exc:
        return (None, body, "frontmatter: %s" % (" ".join(str(exc).split())[:160],))
    if not isinstance(data, dict):
        return (None, body, "the frontmatter is not a mapping")
    return (data, body, "")


def parse_proposals(lines: List[str]) -> List[Dict[str, Any]]:
    """The ``## Proposed`` queue. The first line has six ``|`` fields."""
    out: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    for line in lines:
        m = _PROPOSAL.match(line)
        if m:
            fields = [f.strip() for f in m.group(3).split(" | ")]
            # The id and the tag share the first field: "D016 layer-1.5mm".
            tag = fields[0] if fields else ""
            rest = fields[1:]
            cur = {
                "id": m.group(2),
                "ticked": m.group(1) in ("x", "X"),
                "tag": tag,
                "group": rest[0] if len(rest) > 0 else "",
                "estimate": rest[1] if len(rest) > 1 else "",
                "tests": "",
                "because": "",
                "sub": {},
            }
            for f in rest[2:]:
                if f.startswith("tests:"):
                    cur["tests"] = f[len("tests:"):].strip()
                elif f.startswith("because:"):
                    cur["because"] = f[len("because:"):].strip()
            num = _NUMBER.search(cur["estimate"] or "")
            cur["estimate_core_hours"] = float(num.group(0)) if num else None
            cur["because_refs"] = _REF.findall(cur["because"])
            out.append(cur)
            continue
        sm = _SUB.match(line)
        if sm and cur is not None:
            cur["sub"].setdefault(sm.group(1), []).append(sm.group(2).strip())
            continue
        if line.strip() and not line.startswith((" ", "\t")):
            cur = None
    return out


def parse_ledger(text: str) -> List[Dict[str, Any]]:
    """Start lines ``- D014 | ...`` and their indented ``done``, ``verdict``, ``note``."""
    out: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    for line in (text or "").splitlines():
        m = _LEDGER_START.match(line)
        if m:
            fields = [f.strip() for f in m.group(2).split(" | ")]
            fields += [""] * (5 - len(fields))
            hyp = " | ".join(fields[4:]).strip()
            cur = {
                "id": m.group(1),
                "tag": fields[0],
                "group": fields[1],
                "stamp": fields[2],
                "where": fields[3],
                "hypothesis": hyp,
                "done": None,
                "verdict": None,
                "notes": [],
            }
            out.append(cur)
            continue
        sm = _LEDGER_SUB.match(line)
        if not sm or cur is None:
            continue
        kind, rest = sm.group(1), sm.group(2).strip()
        if kind == "done":
            parts = rest.split()
            kv = dict(_KV.findall(rest))
            cur["done"] = {
                "stamp": parts[0] if parts else "",
                "exit": kv.get("exit"),
                "core_h": _float(kv.get("core-h")),
            }
        elif kind == "verdict":
            fields = [f.strip() for f in rest.split(" | ")]
            fields += [""] * (3 - len(fields))
            cur["verdict"] = {
                "word": fields[0],
                "measures": "" if fields[1] == "-" else fields[1],
                "finding": "" if fields[2] in ("-", "") else fields[2],
            }
        else:
            cur["notes"].append(rest)
    return out


def parse_findings(text: str) -> List[Dict[str, Any]]:
    """One ``## F<n>. <claim>`` section per finding, with its key lines."""
    out: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    for line in (text or "").splitlines():
        m = _FINDING.match(line)
        if m:
            cur = {
                "id": m.group(1),
                "claim": m.group(2),
                "heading": "%s. %s" % (m.group(1), m.group(2)),
                "date": "",
                "runs": [],
                "measures": "",
                "refutes": "",
                "closes": False,
            }
            out.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith("## "):
            cur = None
            continue
        km = _FINDING_KEY.match(line)
        if not km:
            continue
        key, value = km.group(1), km.group(2).strip()
        if key == "date":
            cur["date"] = _date(value)
        elif key == "runs":
            cur["runs"] = re.findall(r"D\d{3}", value)
        elif key == "measures":
            cur["measures"] = value
        elif key == "refutes":
            cur["refutes"] = "" if value in ("-", "") else value
        elif key == "closes":
            cur["closes"] = value.lower() in ("yes", "true")
    return out


def read_manifest(path: Path) -> Dict[str, Any]:
    """The few manifest fields the board reads. An unreadable one is an error row."""
    rec: Dict[str, Any] = {"dir": path.parent.name, "run": path.parent.name[:4]}
    if yaml is None:
        rec["error"] = "PyYAML is not importable"
        return rec
    text, ok = _read(path)
    if not ok or text is None:
        rec["error"] = "unreadable"
        return rec
    try:
        data = yaml.safe_load(text)
    except Exception as exc:
        rec["error"] = " ".join(str(exc).split())[:160]
        return rec
    if not isinstance(data, dict):
        rec["error"] = "not a mapping"
        return rec
    rec["run"] = str(data.get("run") or rec["run"])
    rec["tag"] = str(data.get("tag") or "")
    rec["cluster"] = str(data.get("cluster") or "")
    rec["started"] = str(data.get("started") or "") if data.get("started") else ""
    rec["finished"] = str(data.get("finished") or "") if data.get("finished") else ""
    rec["exit"] = data.get("exit")
    rec["verdict"] = str(data.get("verdict") or "") if data.get("verdict") else ""
    core = None
    for block in ("slurm", "local"):
        sub = data.get(block)
        if isinstance(sub, dict) and _float(sub.get("core_hours")) is not None:
            core = _float(sub.get("core_hours"))
            break
    rec["core_hours"] = core or 0.0
    code = data.get("code")
    rec["code"] = code if isinstance(code, dict) else {}
    return rec


# --------------------------------------------------------------------------
# Reading one campaign
# --------------------------------------------------------------------------


def read_campaign(root: Path, path: Path, ctx: Any = None) -> Campaign:
    """One campaign directory, whatever state it is in. Never raises."""
    c = Campaign(id=path.name, root=str(root), dir=str(path))
    text, ok = _read(path / CAMPAIGN_MD)
    if not ok or text is None:
        c.errors.append("%s: unreadable" % (CAMPAIGN_MD,))
        text = ""
    fm, body, error = split_frontmatter(text)
    if fm is None:
        c.errors.append("%s: %s" % (CAMPAIGN_MD, error))
        fm = {}
    else:
        c.readable = True
    c.fm = fm
    c.title = _text(fm.get("title"))
    c.project = _text(fm.get("project")) or Path(root).name
    c.question = _text(fm.get("question"))
    c.stop = _text(fm.get("stop"))
    c.status = _text(fm.get("status")) or ("unknown" if not c.readable else "draft")
    c.autonomy = _text(fm.get("autonomy")) or "propose-only"
    c.cluster = _text(fm.get("cluster")) or "local"
    c.app = _text(fm.get("app"))
    c.created = _date(fm.get("created"))
    c.updated = _date(fm.get("updated"))
    closed = fm.get("closed")
    c.closed = closed if isinstance(closed, dict) else {}
    budget = fm.get("budget")
    if isinstance(budget, dict):
        c.budget_core_hours = _float(budget.get("core_hours"))
        c.budget_wall_days = _int(budget.get("wall_days"))
        c.budget_runs = _int(budget.get("max_runs"))
    if fm.get("id") not in (None, "", c.id):
        c.errors.append("frontmatter id %r is not the directory name" % (fm.get("id"),))

    sections = ext_handoff.split_sections(body)
    c.missing_sections = [s for s in SECTIONS if s not in sections]
    c.proposals = parse_proposals(sections.get("Proposed") or [])

    ledger, lok = _read(path / LEDGER_MD)
    if not lok:
        c.errors.append("%s: unreadable" % (LEDGER_MD,))
    c.ledger = parse_ledger(ledger or "")
    findings, fok = _read(path / FINDINGS_MD)
    if not fok:
        c.errors.append("%s: unreadable" % (FINDINGS_MD,))
    c.findings = parse_findings(findings or "")

    runs_dir = path / RUNS_REL
    manifests: List[Dict[str, Any]] = []
    run_dirs = 0
    try:
        entries = sorted(os.scandir(str(runs_dir)), key=lambda e: e.name) if runs_dir.is_dir() else []
    except Exception:
        entries = []
    for entry in entries:
        try:
            if entry.name.startswith(".") or not entry.is_dir(follow_symlinks=False):
                continue
        except Exception:
            continue
        run_dirs += 1
        mpath = Path(runs_dir) / entry.name / MANIFEST
        if mpath.is_file():
            rec = read_manifest(mpath)
            if rec.get("error"):
                c.errors.append("runs/%s/%s: %s" % (entry.name, MANIFEST, rec["error"]))
            manifests.append(rec)
    c.manifests = manifests
    c.runs = run_dirs
    c.spent_core_hours = sum(float(m.get("core_hours") or 0.0) for m in manifests)

    counts = {v: 0 for v in VERDICTS}
    counts["unjudged"] = 0
    by_run = {str(e["id"]): e for e in c.ledger}
    for m in manifests:
        word = m.get("verdict") or ""
        if not word:
            entry = by_run.get(str(m.get("run")))
            word = ((entry or {}).get("verdict") or {}).get("word") or ""
        if word in counts:
            counts[word] += 1
        elif m.get("finished"):
            counts["unjudged"] += 1
    c.verdicts = counts

    c.wall_day = wall_day(c)

    hpath = path / HANDOFF_MD
    htext, hok = _read(hpath)
    if htext is not None and hok:
        rec = ext_handoff.parse(htext)
        rec["path"] = str(hpath)
        c.handoff = rec
    else:
        c.handoff = {}

    gdir = path / GALLERY_REL
    if ctx is not None and gdir.is_dir() and _contains(path, gdir):
        try:
            c.gallery = ext_gallery.scan(ctx, gdir, "worktree")
        except Exception:
            c.gallery = {}
    return c


def newest_date(c: Campaign) -> str:
    """The newest day the campaign's own files carry. Never the clock."""
    dates = [c.updated, c.created]
    for e in c.ledger:
        dates.append(_date(e.get("stamp")))
        dates.append(_date((e.get("done") or {}).get("stamp")))
    for m in c.manifests:
        dates.append(_date(m.get("started")))
        dates.append(_date(m.get("finished")))
    for f in c.findings:
        dates.append(f.get("date") or "")
    if c.status in DONE_STATUS:
        dates.append(_date(c.closed.get("date")))
    dates = [d for d in dates if d]
    return max(dates) if dates else ""


def wall_day(c: Campaign) -> Optional[int]:
    """``day N`` counted from ``created`` (day 1) to :func:`newest_date`."""
    start = _day_number(c.created)
    end = _day_number(newest_date(c))
    if start is None or end is None:
        return None
    return max(1, end - start + 1)


def _ledger_newest(c: Campaign) -> str:
    dates = [_date(e.get("stamp")) for e in c.ledger]
    dates += [_date((e.get("done") or {}).get("stamp")) for e in c.ledger]
    dates += [f.get("date") or "" for f in c.findings]
    dates = [d for d in dates if d]
    return max(dates) if dates else ""


def handoff_stale(c: Campaign) -> bool:
    upd = _day_number(_date(c.handoff.get("handoff_updated"))) if c.handoff else None
    newest = _day_number(_ledger_newest(c))
    if upd is None or newest is None:
        return False
    return (newest - upd) > HANDOFF_STALE_DAYS


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------


def roots(cfg: Any) -> List[Path]:
    return [Path(p) for p in (getattr(cfg, "campaign_roots", None) or ())]


def discover(
    cfg: Any, ctx: Any = None
) -> Tuple[List[Campaign], List[str], List[str]]:
    """``(campaigns, unsafe, duplicates)``, in id order.

    Every ``<root>/campaigns/<id>/campaign.md`` whose ``<id>`` is a safe slug
    and whose directory resolves inside its root. The first root wins an id
    that two roots both carry; the second is named, not merged.
    """
    out: List[Campaign] = []
    unsafe: List[str] = []
    dups: List[str] = []
    seen: Dict[str, str] = {}
    for root in roots(cfg):
        base = root / CAMPAIGNS_REL
        if not base.is_dir():
            continue
        try:
            entries = sorted(p for p in base.iterdir() if p.is_dir())
        except Exception:
            continue
        for path in entries:
            if not (path / CAMPAIGN_MD).is_file():
                continue
            if not config.is_safe_id(path.name):
                unsafe.append(path.name)
                continue
            if not _contains(root, path):
                unsafe.append(path.name)
                continue
            if path.name in seen:
                dups.append("%s (%s and %s)" % (path.name, seen[path.name], render.tilde(root)))
                continue
            seen[path.name] = render.tilde(root)
            out.append(read_campaign(root, path, ctx))
    out.sort(key=lambda c: c.id)
    return (out, unsafe, dups)


# --------------------------------------------------------------------------
# The lease and the sessions
# --------------------------------------------------------------------------


def observe_lease(c: Campaign, ctx: Any, rows: List[Dict[str, Any]]) -> None:
    from . import ext_dispatch

    try:
        c.lease = ext_dispatch.read_lease(c.dir)
    except Exception:
        c.lease = None
    c.sessions = ext_dispatch.sessions_under(rows, c.root) if c.root else []
    c.lease_state = ext_dispatch.lease_state(c.lease, c.sessions, getattr(ctx, "now", "") or "")


def _session_rows(ctx: Any) -> List[Dict[str, Any]]:
    from . import ext_dispatch

    try:
        rows, _ok = ext_dispatch.live_sessions(ctx)
        return list(rows or [])
    except Exception:
        return []


# --------------------------------------------------------------------------
# decide: posture, flags and the one next move
# --------------------------------------------------------------------------


def over_budget(c: Campaign) -> List[str]:
    """Each dimension that is spent, as a phrase. Empty when within budget."""
    out: List[str] = []
    if c.budget_core_hours is not None and c.spent_core_hours >= c.budget_core_hours:
        out.append("%s of %s core-h" % (_hours(c.spent_core_hours), _num(c.budget_core_hours)))
    if c.budget_runs is not None and c.runs >= c.budget_runs:
        out.append("%d of %d runs" % (c.runs, c.budget_runs))
    if c.budget_wall_days is not None and c.wall_day is not None and c.wall_day > c.budget_wall_days:
        out.append("day %d of %d" % (c.wall_day, c.budget_wall_days))
    return out


def unjudged(c: Campaign, now: str) -> List[Dict[str, Any]]:
    """Ledger runs with ``done`` and no verdict for longer than a day."""
    now_ts = derive.ts_of(now) if now else None
    out: List[Dict[str, Any]] = []
    for e in c.ledger:
        done = e.get("done")
        if not done or e.get("verdict"):
            continue
        at = derive.ts_of(ledger_iso(done.get("stamp") or ""))
        if now_ts is None or at is None or (now_ts - at) > UNJUDGED_SECONDS:
            out.append(e)
    return out


def refuted(c: Campaign) -> Optional[Dict[str, Any]]:
    """The last finding when it refutes an earlier one and nothing queued cites it."""
    last = c.last_finding()
    if not last or not last.get("refutes"):
        return None
    if any(last["id"] in (p.get("because_refs") or []) for p in c.proposals):
        return None
    return last


def connection_down(c: Campaign) -> bool:
    for e in reversed(c.ledger):
        if e.get("notes"):
            return "connection_down" in str(e["notes"][-1])
    return False


def decide(c: Campaign, cfg: Any, now: str) -> Campaign:
    """Posture, flags and one next move. Pure apart from ``now``."""
    fac = factory_launcher(cfg)
    camp = launcher(cfg)
    cid = c.id
    md = render.tilde(c.path(CAMPAIGN_MD))
    flags: List[str] = []

    if not c.readable:
        flags.append("unreadable")
    if c.lease_state in ("stale", "unattributable"):
        flags.append("lease-stale")
    if c.handoff and handoff_stale(c):
        flags.append("handoff-stale")

    spent = over_budget(c)
    late = unjudged(c, now)
    refuting = refuted(c)
    pending = c.pending()
    ticked = c.ticked()
    if c.readable and c.status not in PARKED_STATUS + DONE_STATUS:
        if spent:
            flags.append("over-budget")
        if late:
            flags.append("unjudged-run")
        if refuting:
            flags.append("refuted")
        if pending and c.autonomy == "propose-only":
            flags.append("proposal-pending")
    c.flags = flags

    na = NextAction()
    short = ""
    if not c.readable:
        posture = NEEDS_YOU
        na = NextAction(
            "fix", "%s validate %s" % (camp, cid),
            "campaign.md does not parse: %s" % (c.errors[0] if c.errors else "unreadable",),
        )
        short = "fix campaign.md"
    elif c.status in PARKED_STATUS:
        posture = PARKED
        na = NextAction(
            "activate", md,
            "status is %s; set `status: active` in campaign.md when it should run" % (c.status,),
        )
        short = "activate"
    elif c.status in DONE_STATUS:
        posture = DONE
        closing = c.closing_finding()
        if c.status == "done":
            why = "closed by %s" % (closing["heading"] if closing else (c.closed.get("finding") or "a finding"),)
        else:
            why = "abandoned %s" % (_date(c.closed.get("date")) or "",)
        na = NextAction("none", "", why.strip())
        short = "none"
    elif spent or late or refuting or "proposal-pending" in flags:
        posture = NEEDS_YOU
        if spent:
            na = NextAction(
                "budget", md,
                "budget spent: %s. Raise the budget in campaign.md and append a Decisions "
                "line, or close the campaign" % (", ".join(spent),),
            )
            short = "raise the budget"
        elif late:
            run = late[0]
            na = NextAction(
                "judge", "%s verdict %s %s <%s>" % (camp, cid, run["id"], "|".join(VERDICTS)),
                "%s finished %s and has no verdict" % (
                    run["id"], _date((run.get("done") or {}).get("stamp")) or "unknown",
                ),
            )
            short = "judge %s" % (run["id"],)
        elif refuting:
            na = NextAction(
                "rethink", md,
                "%s refutes %s and no proposal cites it; revise the hypothesis or propose "
                "the next run" % (refuting["id"], refuting["refutes"]),
            )
            short = "rethink %s" % (refuting["id"],)
        else:
            ids = ", ".join(p["id"] for p in pending)
            why = "%s await%s your tick" % (ids, "s" if len(pending) == 1 else "")
            if ticked:
                why += "; %s %s ticked and will run on the next start" % (
                    ", ".join(p["id"] for p in ticked), "is" if len(ticked) == 1 else "are",
                )
                command = "%s start %s" % (fac, cid)
            else:
                why += " in `Specs/%s/campaign.md`" % (cid,)
                command = md
            na = NextAction("tick", command, why)
            short = "tick %s" % (pending[0]["id"],)
    elif c.lease_state in ("live", "unknown") or c.unfinished():
        posture = RUNNING
        if c.lease_state in ("live", "unknown"):
            na = NextAction(
                "wait", "%s attach %s" % (fac, cid),
                "a session holds the lease%s" % (
                    "; %s running" % (", ".join(m["run"] for m in c.unfinished()),)
                    if c.unfinished() else "",
                ),
            )
            short = "attach"
        else:
            runs = c.unfinished()
            na = NextAction(
                "wait", "%s reconcile %s" % (camp, cid),
                "%s running on %s, started %s" % (
                    ", ".join(m["run"] for m in runs),
                    ", ".join(sorted(set(m.get("cluster") or c.cluster for m in runs))),
                    _date(runs[0].get("started")) or "unknown",
                ),
            )
            short = "reconcile"
    elif connection_down(c):
        posture = WAITING
        na = NextAction(
            "wait", "%s doctor %s" % (camp, cid),
            "the newest ledger note says connection_down; nothing can run until the cluster answers",
        )
        short = "fix the connection"
    elif c.lease_state in ("stale", "unattributable"):
        posture = WAITING
        na = NextAction(
            "release", "%s release %s" % (fac, cid),
            "a lease survives its owner in the campaign directory; a lease is never stolen",
        )
        short = "release"
    elif ticked:
        posture = READY
        na = NextAction(
            "start", "%s start %s" % (fac, cid),
            "%s %s ticked and no session holds the lease" % (
                ", ".join(p["id"] for p in ticked), "is" if len(ticked) == 1 else "are",
            ),
        )
        short = "start"
    else:
        posture = WAITING
        if pending:
            why = "%s queued; autonomy %s lets the loop take %s" % (
                ", ".join(p["id"] for p in pending), c.autonomy,
                "them" if len(pending) > 1 else "it",
            )
        else:
            why = "the queue is empty; the loop proposes the next runs on the next start"
        na = NextAction("start", "%s start %s" % (fac, cid), why)
        short = "start"

    c.posture = posture
    c.next_action = na
    c.short = short
    c.card = BoardCard(
        id=cid,
        kind=KIND,
        posture=posture,
        next_action=na,
        flags=list(flags),
        why=na.why,
        note_folder=NOTE_FOLDER,
        short=short,
        data=c,
    )
    return c


# --------------------------------------------------------------------------
# Strings shared by the note, Home.md and Board.html
# --------------------------------------------------------------------------


def verdict_str(c: Campaign, with_total: bool = True) -> str:
    """``5: 3 supported, 1 refuted, 1 failed``. Only the words that occur."""
    parts = ["%d %s" % (c.verdicts.get(v, 0), v) for v in VERDICTS if c.verdicts.get(v)]
    if c.verdicts.get("unjudged"):
        parts.append("%d unjudged" % (c.verdicts["unjudged"],))
    running = len(c.unfinished())
    if running:
        parts.append("%d running" % (running,))
    body = ", ".join(parts) or "none judged"
    if not with_total:
        return body
    return "%d: %s" % (c.runs, body) if c.runs else "no runs"


def budget_line(c: Campaign) -> str:
    """``14.1 / 60 core-h, day 7 of 14``."""
    core = "%s / %s core-h" % (_hours(c.spent_core_hours), _num(c.budget_core_hours))
    if c.wall_day is None:
        return core
    if c.budget_wall_days is None:
        return "%s, day %d" % (core, c.wall_day)
    return "%s, day %d of %d" % (core, c.wall_day, c.budget_wall_days)


def proposal_line(p: Dict[str, Any]) -> str:
    """One queue entry as prose: ``D016 layer-1.5mm-rtol10 - 3 core-h - tests: ...``."""
    bits = ["%s %s" % (p["id"], p.get("tag") or "")]
    if p.get("estimate"):
        bits.append(p["estimate"])
    if p.get("tests"):
        bits.append("tests: %s" % (p["tests"],))
    if p.get("because"):
        bits.append("because %s" % (p["because"],))
    return " - ".join(b.strip() for b in bits)


def last_finding_heading(c: Campaign) -> str:
    last = c.last_finding()
    return last["heading"] if last else ""


def status_words(c: Campaign) -> str:
    return "%s, %s" % (c.status or "unknown", c.posture.replace("-", " "))


def code_str(c: Campaign) -> str:
    """The newest manifest's code block: ``ptr-update eb8109b, moose d96c576``."""
    for m in sorted(c.manifests, key=lambda m: str(m.get("run")), reverse=True):
        code = m.get("code") or {}
        if not code:
            continue
        parts: List[str] = []
        for name, value in code.items():
            if name in ("binary", "python"):
                continue
            if isinstance(value, dict) and value.get("sha"):
                parts.append("%s %s" % (name, str(value["sha"])[:7]))
            elif name == "container" and value:
                parts.append(str(value))
        if parts:
            return ", ".join(parts)
    return "no manifest yet"


def cluster_str(c: Campaign) -> str:
    """The frontmatter cluster, plus the runs that went elsewhere."""
    other: Dict[str, List[str]] = {}
    for m in c.manifests:
        where = m.get("cluster") or ""
        if where and where != c.cluster:
            other.setdefault(where, []).append(str(m.get("run")))
    if not other:
        return c.cluster
    notes = []
    for where, ids in sorted(other.items()):
        verb = "ran locally" if where == "local" else "ran on %s" % (where,)
        notes.append("%s %s" % (", ".join(ids), verb))
    return "%s (%s)" % (c.cluster, "; ".join(notes))


# --------------------------------------------------------------------------
# collect: load. Writes nothing.
# --------------------------------------------------------------------------


def collect(ctx: Any) -> None:
    campaigns, unsafe, dups = discover(ctx.config, ctx)
    rows = _session_rows(ctx) if campaigns else []
    for c in campaigns:
        observe_lease(c, ctx, rows)
        decide(c, ctx.config, getattr(ctx, "now", "") or "")
    ctx.meta["campaigns"] = campaigns
    ctx.meta["campaigns_unsafe"] = unsafe
    ctx.meta["campaigns_duplicate"] = dups
    if unsafe:
        ctx.log("campaigns: ignoring %d directory name(s) that are not safe slugs or leave "
                "their root: %s" % (len(unsafe), ", ".join(unsafe)))
    if dups:
        ctx.log("campaigns: the same id under two roots, the first kept: %s" % (", ".join(dups),))


def campaigns_for(ctx: Any) -> List[Campaign]:
    """The collected campaigns, loading them once if ``collect`` did not run."""
    meta = getattr(ctx, "meta", None)
    if not isinstance(meta, dict):
        return []
    rows = meta.get("campaigns")
    if rows is None:
        collect(ctx)
        rows = meta.get("campaigns") or []
    return list(rows)


def find(ctx: Any, cid: str) -> Optional[Campaign]:
    for c in campaigns_for(ctx):
        if c.id == cid:
            return c
    return None


def link_targets(ctx: Any) -> List[Tuple[str, Path, Optional[Path], Dict[str, Any]]]:
    """``(id, campaign dir, gallery dir or None, gallery record)``, for
    ``ext_specs`` and ``ext_gallery``.

    ``Specs/<id>`` links the campaign directory and ``Gallery/<id>`` its
    ``gallery/``. Both link sweeps count these ids as seen, so a campaign's link
    is kept.
    """
    out: List[Tuple[str, Path, Optional[Path], Dict[str, Any]]] = []
    for c in campaigns_for(ctx):
        d = Path(c.dir)
        g = d / GALLERY_REL
        ok = g.is_dir() and _contains(d, g)
        out.append((c.id, d, g if ok else None, dict(c.gallery) if (ok and c.gallery) else {}))
    return out


def refuse(ctx: Any, cid: str, verb: str) -> bool:
    """True, after one sentence on stderr, when ``cid`` is a campaign and not a
    feature. For the feature-only verbs: reset, teardown, archive, refresh-pipeline."""
    try:
        if ctx.card(cid) is not None:
            return False
        if find(ctx, cid) is None:
            return False
    except Exception:
        return False
    import sys

    print(
        "refused: %s is a campaign, and `factory %s` acts on a feature worktree only; "
        "the campaign lives in its project repository." % (cid, verb),
        file=sys.stderr,
    )
    return True


# --------------------------------------------------------------------------
# Core hooks: board_cards and find_card
# --------------------------------------------------------------------------


def board_cards(ctx: Any) -> List[BoardCard]:
    return [c.card for c in campaigns_for(ctx) if c.card is not None]


def find_card(ctx: Any, cid: str) -> Optional[BoardCard]:
    c = find(ctx, cid)
    return c.card if c is not None else None


# --------------------------------------------------------------------------
# The timeline: adoption once, then one line per new ledger or findings entry
# --------------------------------------------------------------------------


def _snapshot_path(ctx: Any) -> Optional[Path]:
    store = getattr(ctx, "state", None)
    d = getattr(store, "dir", None)
    return (Path(d) / SNAPSHOT_NAME) if d is not None else None


def _snapshot_read(ctx: Any) -> Dict[str, Any]:
    path = _snapshot_path(ctx)
    if path is None:
        return {}
    data, ok = probe._read_json(path)
    return data if (ok and isinstance(data, dict)) else {}


def _facts(c: Campaign) -> Dict[str, List[str]]:
    return {
        "done": sorted(e["id"] for e in c.ledger if e.get("done")),
        "verdict": sorted(e["id"] for e in c.ledger if e.get("verdict")),
        "finding": sorted(f["id"] for f in c.findings),
    }


def record_timeline(ctx: Any, campaigns: List[Campaign]) -> None:
    """Idempotent. A missing snapshot entry is a baseline, never a flood of events,
    so ``rm -rf factory/state`` repeats nothing."""
    if getattr(ctx, "dry_run", False) or getattr(ctx, "timeline", None) is None:
        return
    snap = _snapshot_read(ctx)
    changed = False
    for c in campaigns:
        if not ctx.timeline.has(c.id, "campaign-adopted"):
            ctx.timeline.append(
                c.id,
                {
                    "at": ctx.now,
                    "event": "campaign-adopted",
                    "why": "board adopted this campaign from %s"
                    % (render.tilde(Path(c.root) / CAMPAIGNS_REL),),
                },
            )
        now_facts = _facts(c)
        before = snap.get(c.id)
        if isinstance(before, dict):
            by_id = {e["id"]: e for e in c.ledger}
            for rid in now_facts["done"]:
                if rid in (before.get("done") or []):
                    continue
                done = by_id[rid].get("done") or {}
                ctx.timeline.append(c.id, {
                    "at": ctx.now, "event": "campaign-run-done", "run": rid,
                    "why": "%s done exit=%s %s core-h" % (
                        rid, done.get("exit"),
                        _hours(done.get("core_h") or 0.0),
                    ),
                })
            for rid in now_facts["verdict"]:
                if rid in (before.get("verdict") or []):
                    continue
                v = by_id[rid].get("verdict") or {}
                ctx.timeline.append(c.id, {
                    "at": ctx.now, "event": "campaign-verdict", "run": rid,
                    "why": "%s %s%s" % (
                        rid, v.get("word") or "judged",
                        (" - " + v["finding"]) if v.get("finding") else "",
                    ),
                })
            by_f = {f["id"]: f for f in c.findings}
            for fid in now_facts["finding"]:
                if fid in (before.get("finding") or []):
                    continue
                ctx.timeline.append(c.id, {
                    "at": ctx.now, "event": "campaign-finding", "finding": fid,
                    "why": by_f[fid]["heading"][:160],
                })
        if before != now_facts:
            snap[c.id] = now_facts
            changed = True
    path = _snapshot_path(ctx)
    if changed and path is not None:
        try:
            config.write_text_atomic(path, json.dumps(snap, indent=1, sort_keys=True) + "\n")
        except Exception as exc:
            ctx.log("campaigns: cannot write %s: %s" % (path, exc))


# --------------------------------------------------------------------------
# Campaigns/<id>.md
# --------------------------------------------------------------------------


def _yaml_str(text: str) -> str:
    return json.dumps(str(text))


def frontmatter(c: Campaign) -> str:
    v = c.verdicts
    lines = [
        "---",
        "campaign: %s" % (c.id,),
        "project: %s" % (c.project or "unknown",),
        "status: %s" % (c.status or "unknown",),
        "posture: %s" % (c.posture,),
        "flags: [%s]" % (", ".join(c.flags),),
        "autonomy: %s" % (c.autonomy,),
        "cluster: %s" % (c.cluster,),
        "runs: %d" % (c.runs,),
    ]
    for word in VERDICTS:
        lines.append("%s: %d" % (word, v.get(word, 0)))
    lines += [
        "core_hours: %s" % (_hours(c.spent_core_hours),),
        "core_hours_budget: %s" % ("" if c.budget_core_hours is None else _num(c.budget_core_hours),),
        "wall_days: %s" % ("" if c.wall_day is None else c.wall_day,),
        "wall_days_budget: %s" % ("" if c.budget_wall_days is None else c.budget_wall_days,),
        "findings: %d" % (len(c.findings),),
        "last_finding: %s" % (_yaml_str(last_finding_heading(c)),),
        "closes: %s" % ("true" if c.closing_finding() else "false",),
        "proposals_ticked: %d" % (len(c.ticked()),),
        "proposals_pending: %d" % (len(c.pending()),),
        "session: %s" % (_session_name(c),),
        "handoff_sessions: %s" % (
            "" if c.handoff.get("handoff_sessions") is None else c.handoff["handoff_sessions"],
        ),
        "updated: %s" % (render.STAMP,),
        "tags: [factory-campaign]",
        "---",
    ]
    return "\n".join(lines)


def _session_name(c: Campaign) -> str:
    if c.lease and c.lease.get("bg_id"):
        return str(c.lease["bg_id"])
    return "none"


def head_block(c: Campaign, ctx: Any) -> str:
    cell = render.cell
    bits = ["[[Home]]", "**%s**" % (c.status or "unknown",), c.cluster]
    bits.append("%d runs: %s" % (c.runs, verdict_str(c, with_total=False)) if c.runs else "no runs")
    bits.append(budget_line(c))
    if c.posture == NEEDS_YOU:
        bits.append("needs you")
    out = [" - ".join(bits), ""]
    na = c.next_action
    out.append("> **Next:** %s" % (na.why or na.verb,))
    if na.command:
        out.append("> `%s`" % (na.command,))
    out.append("")
    out.append("## Gates")
    out.append("")
    out.append(
        "_Both are yours. The tick lives in `campaign.md`, through `Specs/%s/`, and is read "
        "back by `campaign run`; a box here would be read by nobody, so these are text. The "
        "budget is the frontmatter._" % (c.id,)
    )
    out.append("")
    if c.proposals:
        for p in c.proposals:
            out.append("- `[%s]` %s" % ("x" if p.get("ticked") else " ", cell(proposal_line(p))))
    else:
        out.append("- no proposal queued under `## Proposed`")
    runs_budget = "%d of %s runs" % (c.runs, c.budget_runs if c.budget_runs is not None else "?")
    wall = ""
    if c.wall_day is not None:
        wall = ", day %d of %s" % (
            c.wall_day, c.budget_wall_days if c.budget_wall_days is not None else "?",
        )
    out.append(
        "- budget: %s of %s core-h, %s%s. Raise it in `campaign.md` and append a Decisions line."
        % (_hours(c.spent_core_hours), _num(c.budget_core_hours), runs_budget, wall)
    )
    return "\n".join(out)


def _wiki(cid: str, name: str, alias: str) -> str:
    target = name[:-3] if name.endswith(".md") else name
    return "[[Specs/%s/%s|%s]]" % (cid, target, alias)


def _ledger_line(e: Dict[str, Any]) -> str:
    cell = render.cell
    bits = ["%s %s" % (e["id"], e.get("tag") or ""), e.get("where") or "?"]
    done = e.get("done")
    if done:
        bits.append("done exit=%s %s core-h" % (done.get("exit"), _hours(done.get("core_h") or 0.0)))
    else:
        bits.append("launched %s" % (ledger_iso(e.get("stamp") or "") or e.get("stamp") or "?",))
    v = e.get("verdict")
    if v:
        word = "**%s**" % (v.get("word") or "judged",)
        if v.get("measures"):
            word += " " + v["measures"]
        bits.append(word)
        if v.get("finding"):
            bits.append(v["finding"])
    elif done:
        bits.append("no verdict")
    for note in e.get("notes") or []:
        bits.append("note: %s" % (note,))
    return "- " + cell(" - ".join(b.strip() for b in bits))


def _gallery_text(c: Campaign, ctx: Any) -> str:
    """``ext_gallery``'s own section, reworded for a campaign directory."""
    try:
        rows = ext_gallery.note_sections(c.card or c, ctx)
    except Exception:
        rows = []
    if not rows:
        return ""
    text = rows[0][1]
    text = text.replace("read from the worktree", "read from the campaign directory")
    return text


def body_block(c: Campaign, ctx: Any) -> str:
    cfg = ctx.config
    cell = render.cell
    fac = factory_launcher(cfg)
    camp = launcher(cfg)
    out: List[str] = []

    out.append("## Open the campaign")
    out.append("")
    out.append("- Campaign: [%s](%s)" % (CAMPAIGN_MD, render.file_uri(c.path(CAMPAIGN_MD))))
    out.append(
        "- Ledger: [%s](%s), findings: [%s](%s)"
        % (LEDGER_MD, render.file_uri(c.path(LEDGER_MD)),
           FINDINGS_MD, render.file_uri(c.path(FINDINGS_MD)))
    )
    try:
        workspaces = sorted(Path(c.root).glob("*.code-workspace"))
    except Exception:
        workspaces = []
    for ws in workspaces[:2]:
        out.append("- Workspace: [%s](%s)" % (ws.name, render.file_uri(ws)))
    import urllib.parse

    out.append(
        "- Vault: `obsidian://open?vault=%s&file=%s`"
        % (urllib.parse.quote(render.vault_name(ctx), safe=""),
           urllib.parse.quote("%s/%s" % (NOTE_FOLDER, c.id)))
    )
    out.append("")
    out.append("```")
    out.append("%s status %s" % (camp, c.id))
    out.append(
        "cd %s && claude --bg --name %s \"/campaign %s\""
        % (render.tilde(c.root), c.id, c.id)
    )
    out.append("```")
    out.append("")

    out.append("## Campaign")
    out.append("")
    names = [(CAMPAIGN_MD, "the question, the budget, the queue"),
             (LEDGER_MD, "one entry per run"),
             (FINDINGS_MD, "one section per finding"),
             (HANDOFF_MD, "what the last session left")]
    for name, what in names:
        if c.path(name).is_file():
            out.append("- %s - %s" % (_wiki(c.id, name, name), what))
        else:
            out.append("- %s - absent" % (name,))
    out.append("")
    out.append(
        "_Linked at `Specs/%s/`, straight into `%s`. A box ticked in `Specs/%s/%s` is saved "
        "to the repository file, and `campaign run` reads it there._"
        % (c.id, render.tilde(c.dir), c.id, CAMPAIGN_MD)
    )
    out.append("")

    out.append("## Where it stands")
    out.append("")
    rows = ["| property | value |", "|---|---|"]
    rows.append("| question | %s |" % (cell(c.question or "not stated"),))
    rows.append("| stop | %s |" % (cell(c.stop or "not stated"),))
    rows.append("| status | %s |" % (cell("%s, %s" % (c.status or "unknown", c.autonomy)),))
    rows.append("| cluster | %s |" % (cell(cluster_str(c)),))
    rows.append(
        "| runs | %s |"
        % (cell("%d of %s: %s" % (
            c.runs, c.budget_runs if c.budget_runs is not None else "?",
            verdict_str(c, with_total=False))),)
    )
    rows.append(
        "| core-hours | %s |"
        % (cell("%s / %s" % (_hours(c.spent_core_hours), _num(c.budget_core_hours))),)
    )
    if c.wall_day is not None:
        wall = "day %d of %s, created %s" % (
            c.wall_day, c.budget_wall_days if c.budget_wall_days is not None else "?",
            c.created or "unknown",
        )
    else:
        wall = "created %s" % (c.created or "unknown",)
    rows.append("| wall | %s |" % (cell(wall),))
    closing = c.closing_finding()
    rows.append(
        "| findings | %s |"
        % (cell("%d, %s" % (len(c.findings), ("%s closes" % closing["id"]) if closing else "none closes")),)
    )
    rows.append("| last finding | %s |" % (cell(last_finding_heading(c) or "none yet"),))
    rows.append("| code | %s |" % (cell(code_str(c)),))
    out.extend(rows)
    out.append("")

    n = len(c.ledger)
    out.append("## Ledger (last %d of %d)" % (min(LEDGER_ON_NOTE, n), n))
    out.append("")
    if c.ledger:
        out.extend(_ledger_line(e) for e in c.ledger[-LEDGER_ON_NOTE:])
    else:
        out.append("_No run launched yet. `campaign run` writes the first line._")
    out.append("")

    out.append("## Findings")
    out.append("")
    if c.findings:
        for f in c.findings:
            tail = []
            if f.get("runs"):
                tail.append(", ".join(f["runs"]))
            if f.get("refutes"):
                tail.append("refutes %s" % (f["refutes"],))
            if f.get("closes"):
                tail.append("closes")
            out.append("- %s" % (cell(" - ".join([f["heading"]] + tail)),))
    else:
        out.append("_No finding yet._")
    out.append("")

    out.append("## Handoff")
    out.append("")
    h = c.handoff
    if not h:
        out.append(
            "_No `handoff.md` in the campaign directory. Run `/handoff` in the project: it is "
            "the only record of what a session already tried and ruled out._"
        )
    else:
        out.append("**State.** %s" % (h.get("handoff_state") or "_Empty._",))
        out.append("")
        out.append("**Next.**")
        steps = h.get("next") or []
        if steps:
            out.extend(ext_handoff._CHECKBOX.sub("- ", s) for s in steps[:ext_handoff.NEXT_ON_NOTE])
            if len(steps) > ext_handoff.NEXT_ON_NOTE:
                out.append("- and %d more, in the handoff" % (len(steps) - ext_handoff.NEXT_ON_NOTE,))
        else:
            out.append("_Empty._")
        out.append("")
        dnr = h.get("dnr") or []
        out.append("**Do not repeat (last %d).**" % (min(ext_handoff.DNR_ON_NOTE, len(dnr)),))
        if dnr:
            out.extend(dnr[-ext_handoff.DNR_ON_NOTE:])
        else:
            out.append("_Nothing recorded._")
        out.append("")
        out.append(
            "_Sessions: %s. Updated %s. Run `/handoff` in the project to change this block._"
            % (
                h.get("handoff_sessions") if h.get("handoff_sessions") is not None else "?",
                h.get("handoff_updated") or "unknown",
            )
        )
    out.append("")

    gallery = _gallery_text(c, ctx)
    if gallery:
        out.append("## Gallery")
        out.append("")
        out.append(gallery)
        out.append("")

    out.append("## Session")
    out.append("")
    lease = c.lease or {}
    if c.lease_state == "none":
        out.append("- Lease: **free**. `%s start %s` takes it." % (fac, c.id))
    elif c.lease_state == "live":
        out.append(
            "- Lease: **held** by bg `%s` (pid %s) since %s"
            % (lease.get("bg_id") or "unknown", lease.get("pid"), lease.get("acquired") or "unknown")
        )
    elif c.lease_state == "unknown":
        out.append("- Lease: **held** by pid %s; liveness unknown this run." % (lease.get("pid"),))
    else:
        out.append(
            "- Lease: **stale** (pid %s, taken %s). A lease is never stolen: `%s release %s`."
            % (lease.get("pid"), lease.get("acquired") or "unknown", fac, c.id)
        )
    if c.sessions:
        for row in c.sessions:
            out.append(
                "- Live session `%s` (%s, %s): %s"
                % (
                    row.get("bg_id") or row.get("jobId") or str(row.get("sessionId") or "").split("-")[0]
                    or "unknown",
                    row.get("kind") or "unknown",
                    row.get("state") or row.get("status") or "unknown",
                    cell(row.get("detail") or "no detail"),
                )
            )
    else:
        out.append("- Live sessions with cwd under `%s`: none" % (render.tilde(c.root),))
    out.append("")

    if c.flags:
        out.append("## Flags")
        out.append("")
        for flag in c.flags:
            out.append("- `%s` - %s" % (flag, FLAG_WHY.get(flag, "")))
        out.append("")

    problems = list(c.errors) + (
        ["campaign.md lacks: %s" % (", ".join("`## %s`" % s for s in c.missing_sections),)]
        if (c.readable and c.missing_sections) else []
    )
    if problems:
        out.append("## Errors")
        out.append("")
        for line in problems:
            out.append("- %s" % (cell(line),))
        out.append("")

    rows_tl = ctx.timeline.read(c.id) if getattr(ctx, "timeline", None) else []
    out.append("## Timeline")
    out.append("")
    if rows_tl:
        for rec in rows_tl[-TIMELINE_ON_NOTE:]:
            out.append(
                "- %s %s%s"
                % (
                    str(rec.get("at") or "")[:16].replace("T", " "),
                    cell(rec.get("event") or ""),
                    (" - " + cell(rec.get("why") or "")) if rec.get("why") else "",
                )
            )
    else:
        out.append("_Nothing recorded yet._")
    return "\n".join(out)


def compose_note(c: Campaign, ctx: Any, existing: Optional[str]) -> str:
    """The four-marker note, both human regions preserved byte for byte."""
    human = EMPTY_HUMAN
    tail = ""
    if existing and HEAD_END in existing and BODY_BEGIN in existing:
        human = existing.split(HEAD_END, 1)[1].split(BODY_BEGIN, 1)[0]
    if existing and BODY_END in existing:
        tail = existing.split(BODY_END, 1)[1]
        if not tail.strip():
            tail = ""
    text = "\n".join([frontmatter(c), "# %s" % (c.id,), "", HEAD_BEGIN, head_block(c, ctx), HEAD_END])
    text += human
    text += "\n".join([BODY_BEGIN, body_block(c, ctx), BODY_END])
    text += tail if tail else "\n"
    return text


def notes_dir(cfg: Any) -> Path:
    return Path(cfg.vault) / NOTE_FOLDER


def note_path(cfg: Any, cid: str) -> Path:
    return notes_dir(cfg) / (config.validate_id(cid) + ".md")


def write_campaign(c: Campaign, ctx: Any) -> str:
    """``written``, ``skipped``, ``refused`` or ``dry-run``. Same rules as a feature note."""
    cfg = ctx.config
    path = note_path(cfg, c.id)
    render.guard_path(cfg, path)
    existing, ok = probe._read_text(path)
    if not ok:
        ctx.log("campaign note %s is unreadable; not rewritten" % (path,))
        return "refused"
    if existing is not None:
        missing = [m for m in probe.MARKERS if m not in existing]
        if missing:
            ctx.log("campaign note %s is missing %s: not rewritten" % (path, ", ".join(missing)))
            return "refused"
    text = compose_note(c, ctx, existing)
    key = "%s/%s.md" % (NOTE_FOLDER, c.id)
    dg = snapshot.digest(text)
    stamp = ctx.state.stamp(key, dg, ctx.now) if ctx.state is not None else ctx.now
    final = text.replace(render.STAMP, stamp)
    status = render.atomic_write(path, final, ctx.dry_run)
    if ctx.stamps is not None:
        ctx.stamps[key] = (dg, stamp)
    return status


BASE_NAME = "Campaigns.base"

#: Written once when absent, never overwritten: Obsidian owns it afterwards, exactly
#: like Features.base (see ``render.write_base``).
BASE = """filters:
  and:
    - file.inFolder("Campaigns")
    - file.ext == "md"
    - file.tags.contains("factory-campaign")
properties:
  note.campaign:
    displayName: campaign
  note.posture:
    displayName: posture
  note.status:
    displayName: status
  note.autonomy:
    displayName: autonomy
  note.cluster:
    displayName: cluster
  note.runs:
    displayName: runs
  note.supported:
    displayName: supported
  note.refuted:
    displayName: refuted
  note.failed:
    displayName: failed
  note.core_hours:
    displayName: core hours
  note.core_hours_budget:
    displayName: core hours budget
  note.wall_days:
    displayName: wall days
  note.findings:
    displayName: findings
  note.last_finding:
    displayName: last finding
  note.proposals_pending:
    displayName: proposals pending
views:
  - type: table
    name: Campaigns
    order:
      - note.campaign
      - note.posture
      - note.status
      - note.autonomy
      - note.cluster
      - note.runs
      - note.supported
      - note.refuted
      - note.failed
      - note.core_hours
      - note.core_hours_budget
      - note.wall_days
      - note.findings
      - note.last_finding
      - note.proposals_pending
    sort:
      - property: note.posture
        direction: ASC
  - type: cards
    name: Board
    groupBy:
      property: note.posture
      direction: ASC
    order:
      - note.campaign
      - note.status
      - note.runs
      - note.core_hours
      - note.last_finding
      - note.proposals_pending
"""


def base_path(cfg: Any) -> Path:
    return Path(cfg.vault) / BASE_NAME


def write_base(ctx: Any) -> str:
    """``Campaigns.base``, written once when absent and never overwritten."""
    cfg = ctx.config
    path = base_path(cfg)
    if path.exists():
        return "skipped"
    if getattr(ctx, "dry_run", False):
        return "dry-run"
    render.guard_path(cfg, path)
    return render.atomic_write(path, BASE, False)


def outputs(ctx: Any) -> Dict[str, Any]:
    """Write every campaign note, at most once per run. Called by ``render.sync``."""
    cached = ctx.meta.get("_campaigns_write")
    if cached is not None:
        return cached
    campaigns = campaigns_for(ctx)
    # The folder exists from the first board run, like Gallery/ and Specs/, so
    # the doctor row has something to find before the first campaign does.
    if not getattr(ctx, "dry_run", False):
        try:
            notes_dir(ctx.config).mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            ctx.log("campaigns: cannot create %s: %s" % (notes_dir(ctx.config), exc))
    try:
        write_base(ctx)
    except Exception as exc:
        ctx.log("campaigns: %s not written: %s" % (BASE_NAME, exc))
    # Before composing: the note prints the timeline.
    try:
        record_timeline(ctx, campaigns)
    except Exception as exc:
        ctx.log("campaigns: timeline failed: %s" % (exc,))
    counts = {"written": 0, "skipped": 0, "refused": 0, "dry-run": 0}
    refused: List[str] = []
    for c in campaigns:
        try:
            status = write_campaign(c, ctx)
        except config.RefusedWrite as exc:
            ctx.log(str(exc))
            status = "refused"
        except Exception as exc:                      # one bad campaign is not fatal
            ctx.log("campaign %s failed to render: %s" % (c.id, exc))
            status = "refused"
        counts[status] = counts.get(status, 0) + 1
        if status == "refused":
            refused.append("%s/%s" % (NOTE_FOLDER, c.id))
            c.add_flag("marker-missing")
    # render.sync counts every refused id itself; counting it here too doubled it.
    counts.pop("refused", None)
    result = {"counts": counts, "refused": refused}
    ctx.meta["_campaigns_write"] = result
    return result


# --------------------------------------------------------------------------
# Home.md
# --------------------------------------------------------------------------


def home_sections(ctx: Any) -> List[Tuple[str, str, int]]:
    campaigns = campaigns_for(ctx)
    cell = render.cell
    lines: List[str] = []
    if not campaigns:
        where = ", ".join("`%s`" % (render.tilde(r),) for r in roots(ctx.config)) or "none configured"
        lines.append(
            "_No campaign under the campaign roots (%s). `%s new <id> --root <project>` "
            "scaffolds one; `campaign_roots` in the config names the projects._"
            % (where, launcher(ctx.config))
        )
        return [("Campaigns (0)", "\n".join(lines), 20)]
    lines.append("| campaign | status | runs | budget | last finding | next |")
    lines.append("|---|---|---|---|---|---|")
    for c in sorted(campaigns, key=lambda c: (POSTURE_ORDER.get(c.posture, 99), c.id)):
        lines.append(
            "| [[%s]] | %s | %s | %s | %s | %s |"
            % (
                c.id,
                cell(status_words(c)),
                cell(verdict_str(c)),
                cell(budget_line(c)),
                cell(last_finding_heading(c) or "none yet"),
                cell(c.short or c.next_action.verb),
            )
        )
    result = ctx.meta.get("_campaigns_write") or {}
    if result.get("refused"):
        lines.append("")
        lines.append(
            "_%d campaign note kept its own bytes because a factory marker is missing: %s. "
            "Restore the four markers, or delete the note and rerun._"
            % (len(result["refused"]), ", ".join(result["refused"]))
        )
    unsafe = ctx.meta.get("campaigns_unsafe") or []
    if unsafe:
        lines.append("")
        lines.append("_Ignored, not a safe slug: %s._" % (", ".join("`%s`" % (u,) for u in unsafe),))
    dups = ctx.meta.get("campaigns_duplicate") or []
    if dups:
        lines.append("")
        lines.append("_The same id under two roots, the first kept: %s._" % (", ".join(dups),))
    return [("Campaigns (%d)" % (len(campaigns),), "\n".join(lines), 20)]


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------


def doctor_checks(ctx: Any) -> List[Tuple[str, bool, str]]:
    """``ctx`` here carries only config, paths and ``now``: load our own data."""
    from . import ext_dispatch

    cfg = ctx.config
    out: List[Tuple[str, bool, str]] = []
    out.append((
        "PyYAML importable for the campaigns adapter",
        yaml is not None,
        "pip install PyYAML, or set FACTORY_PYTHON; without it no campaign renders",
    ))
    missing = [render.tilde(r) for r in roots(cfg) if not (r / CAMPAIGNS_REL).is_dir()]
    out.append((
        "every campaign root holds a campaigns/ directory",
        not missing,
        "no campaigns/ under: %s. `campaign new <id> --root <project>` creates one, or drop "
        "the root from `campaign_roots`." % (", ".join(missing),),
    ))
    campaigns, unsafe, dups = discover(cfg, None)
    out.append((
        "every campaign id is a safe slug inside its root",
        not unsafe,
        "ignored: %s. Rename to letters, digits, dot, dash, underscore." % (", ".join(unsafe),),
    ))
    out.append((
        "every campaign id is unique across the roots",
        not dups,
        "duplicate: %s. The first root wins; rename one." % ("; ".join(dups),),
    ))
    bad = [c.id for c in campaigns if not c.readable]
    out.append((
        "every campaign.md parses",
        not bad,
        "unreadable: %s. `campaign validate <id>` says why; those cards render as needs-you."
        % (", ".join(bad),),
    ))
    partial = [c.id for c in campaigns if c.readable and c.missing_sections]
    out.append((
        "every campaign.md carries the four headings",
        not partial,
        "missing a heading: %s. `campaign validate <id>`." % (", ".join(partial),),
    ))
    stale: List[str] = []
    for c in campaigns:
        rec = ext_dispatch.read_lease(c.dir)
        if rec and ext_dispatch.lease_state(rec, [], probe.iso()) in ("stale", "unattributable"):
            stale.append(c.id)
    out.append((
        "no stale lease in any campaign directory",
        not stale,
        "stale: %s. `factory release <id>` removes one, interactively." % (", ".join(stale),),
    ))
    d = notes_dir(cfg)
    bad_markers: List[str] = []
    orphans: List[str] = []
    known = set(c.id for c in campaigns)
    if d.is_dir():
        for note in sorted(d.glob("*.md")):
            text, tok = probe._read_text(note)
            if tok and text and any(m not in text for m in probe.MARKERS):
                bad_markers.append(note.stem)
            if note.stem not in known:
                orphans.append(note.stem)
    out.append((
        "every campaign note keeps its four markers",
        not bad_markers,
        "missing in: %s. The adapter refuses those notes." % (", ".join(bad_markers),),
    ))
    out.append((
        "Campaigns.base is in the vault",
        base_path(cfg).is_file(),
        "run `factory board`: it writes Campaigns.base once when absent and never overwrites it",
    ))
    out.append((
        "no orphan note in Campaigns/",
        not orphans,
        "no campaign directory for: %s. Remove the note by hand; no script deletes a note."
        % (", ".join(orphans),),
    ))
    return out


# --------------------------------------------------------------------------
# The verb
# --------------------------------------------------------------------------


def run_campaigns(argv: List[str], ctx: Any) -> int:
    """``factory campaigns [<id>...]``: print the rows. Writes nothing, ever."""
    wanted = [a for a in (argv or []) if not a.startswith("-")]
    campaigns = campaigns_for(ctx)
    where = ", ".join(render.tilde(r) for r in roots(ctx.config)) or "no campaign_roots"
    if wanted:
        campaigns = [c for c in campaigns if c.id in set(wanted)]
        if not campaigns:
            print("no campaign %s under %s" % (", ".join(wanted), where))
            return 3
    if not campaigns:
        print("no campaign under %s" % (where,))
        return 0
    width = max(len(c.id) for c in campaigns)
    for c in sorted(campaigns, key=lambda c: (POSTURE_ORDER.get(c.posture, 99), c.id)):
        print("%-*s %-9s %-9s %s; %s" % (width, c.id, c.status, c.posture, verdict_str(c), budget_line(c)))
        if c.flags:
            print("%-*s   flags %s" % (width, "", ", ".join(c.flags)))
        print("%-*s   %s" % (width, "", c.next_action.why))
        if c.next_action.command:
            print("%-*s   run %s" % (width, "", c.next_action.command))
    return 1 if any(c.posture == NEEDS_YOU for c in campaigns) else 0


VERBS = {"campaigns": run_campaigns}
HELP = {"campaigns": "print the campaigns under campaign_roots, read only"}
# Reads the campaign files and the session files only: no probe round.
NO_CTX_VERBS = ("campaigns",)
