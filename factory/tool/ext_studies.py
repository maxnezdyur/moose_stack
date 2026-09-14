"""The studies adapter: analysis study cards, read only, on the same board.

What this extension is
----------------------

``analysis/studies/<id>/`` holds two files. ``study.yaml`` is the immutable
spec, written by ``/analysis-blueprint``. ``card.yaml`` is the durable, mutable
state of that study, written by the analysis toolkit and by nothing else. This
extension reads both and renders:

    Home.md          one "Studies" section, grouped by the plan's posture map
    Studies/<id>.md  one note per study, with the same four-marker discipline

Two hard rules, also written in ``factory/README.md`` and the vault manual:

1. ``$ANALYSIS_VAULT`` must never point at the factory vault.
   ``analysis/tool/vault.py`` has its own ``write_home``, which would fight
   ``tool/render.py`` for ``Home.md``. ``doctor_checks`` enforces it, and
   refuses an overlap in either direction, not only an exact match.
2. The factory never writes a card and never runs ``analysis reconcile``. A
   study row is therefore exactly as fresh as Max's last reconcile, so every
   row and every note prints the card's own ``updated`` date, and adds a
   ``reconcile`` hint once that date is more than a day behind ``ctx.now``.

Three decisions worth stating
-----------------------------

*The schema is re-read, not imported.* This module parses ``card.yaml`` with
PyYAML and tolerates unknown keys, exactly as ``analysis/tool/model.py`` does.
It does not import the analysis package: that would put a second package on
``sys.path`` and make the board fail when the analysis toolkit moves. The field
names here are the ones ``Card.to_dict`` writes (verified against
``analysis/tool/model.py``).

*The notes are written when the board is written.* ``collect(ctx)`` is pure: it
only loads. The writes happen in ``outputs(ctx)``, which ``home_sections``
calls: that is the one hook the core runs after ``derive`` and inside
``render.sync``, exactly once per ``factory board``. So ``factory next`` and
``factory studies`` never touch the vault, and the study stamps land in
``ctx.stamps`` in time for the core's ``stamp_commit``. ``outputs(ctx)`` is
already shaped for a core hook of that name in ``render.sync`` (see
``core_change_requests``): when it lands, ``sync`` calls it first, the result is
cached on ``ctx.meta`` and ``home_sections`` writes nothing.

*The study gates are printed as words, never as checkboxes.* The analysis
toolkit owns ``spec_approved`` and ``dispatch``. A ``- [ ]`` box in a study note
would be read back by nobody, so it would be a trap. The note states both
states and says who owns them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config, derive, probe, render, snapshot
from .model import DONE, NEEDS_YOU, PARKED, POSTURE, RUNNING, WAITING, StudyCard

try:                                  # PyYAML is the one non-stdlib dependency.
    import yaml
except Exception:                     # pragma: no cover - doctor reports it
    yaml = None                       # type: ignore[assignment]

CARD_NAME = "card.yaml"
SPEC_NAME = "study.yaml"

# A card that has not been reconciled for this long gets the hint. The hint is
# the only clock-dependent content in a generated note, so it prints the card's
# date and never an age in days.
RECONCILE_STALE_SECONDS = 86400

# The Kanban ladder of analysis/tool/model.py:StudyState, in pipeline order.
# The three off-pipeline lanes carry no rank.
STUDY_LANES: Tuple[str, ...] = (
    "draft",
    "approved",
    "smoking",
    "ready",
    "dispatched",
    "running",
    "collecting",
    "analyzing",
    "reported",
    "done",
)
STUDY_LANE_RANK: Dict[str, int] = {lane: i for i, lane in enumerate(STUDY_LANES)}

OFF_PIPELINE: Tuple[str, ...] = ("attention", "budget_exceeded", "connection_down")

# Two lanes this module invents, for a study the toolkit has not described.
NO_CARD = "no-card"          # study.yaml only; the placeholder row
UNREADABLE = "unreadable"    # card.yaml exists and does not parse

# The plan's posture table. This is the whole reason features and studies can
# share one board: nothing reconciles two lane ladders, and posture is stored
# nowhere so it cannot go stale.
STUDY_POSTURE: Dict[str, str] = {
    "draft": PARKED,
    "approved": PARKED,
    "smoking": RUNNING,
    "dispatched": RUNNING,
    "running": RUNNING,
    "collecting": RUNNING,
    "analyzing": RUNNING,
    "ready": WAITING,
    "attention": NEEDS_YOU,
    "budget_exceeded": NEEDS_YOU,
    "connection_down": NEEDS_YOU,
    "reported": DONE,
    "done": DONE,
    NO_CARD: PARKED,
    UNREADABLE: NEEDS_YOU,
}

# Posture order on Home.md, highest attention first.
POSTURE_ORDER: Dict[str, int] = {p: i for i, p in enumerate(POSTURE)}

TERMINAL_CASE = ("done", "failed_systematic")


# --------------------------------------------------------------------------
# Where the studies live
# --------------------------------------------------------------------------


def studies_dir(cfg: Any) -> Path:
    """The directory the analysis toolkit keeps its studies in.

    Resolution order, mirroring ``analysis/tool/config.py``:

      1. ``$FACTORY_STUDIES_DIR`` (tests and an explicit override).
      2. the ``studies_dir`` key of ``config.toml``. This is the one machine
         fact that used to have no place in that file: a second machine had to
         export an environment variable from a shell profile, which the launchd
         tick never reads, so the tick and a hand-run board saw different
         studies.
      3. ``$ANALYSIS_VAULT/studies``, which is where the toolkit puts them when
         that vault is configured -- unless it overlaps the factory vault, in
         which case the factory ignores it and ``doctor`` fails loudly.
      4. ``<repo_root>/analysis/studies``.
    """
    env = os.environ.get("FACTORY_STUDIES_DIR")
    if env:
        return Path(env).expanduser()
    if (getattr(cfg, "sources", None) or {}).get("studies_dir") == "file":
        return Path(cfg.analysis_studies)
    av = os.environ.get("ANALYSIS_VAULT")
    if av:
        vault = Path(av).expanduser()
        if not _overlaps(vault, Path(cfg.vault)):
            return vault / "studies"
    return Path(cfg.repo_root) / "analysis" / "studies"


def analysis_launcher(cfg: Any) -> str:
    """The no-install launcher, as a copyable path."""
    return render.tilde(Path(cfg.repo_root) / "analysis" / "analysis")


def _overlaps(a: Path, b: Path) -> bool:
    """True when either path contains the other, or they are the same path."""
    try:
        ra = Path(os.path.realpath(str(a)))
        rb = Path(os.path.realpath(str(b)))
    except Exception:
        return False
    if ra == rb:
        return True
    for x, y in ((ra, rb), (rb, ra)):
        try:
            x.relative_to(y)
            return True
        except Exception:
            continue
    return False


# --------------------------------------------------------------------------
# The study
# --------------------------------------------------------------------------


@dataclass
class Study:
    """One read-only projection of a study directory. Derived, never stored."""

    id: str
    lane: str = NO_CARD
    posture: str = PARKED
    title: str = ""
    kind: str = ""
    app: str = ""
    cluster: str = ""
    account: str = ""
    repo_sha: Optional[str] = None
    created: str = ""
    updated: str = ""                 # the card's own stamp, never ours
    counts: Dict[str, int] = field(default_factory=dict)
    spent_core_hours: float = 0.0
    ceiling_core_hours: Optional[float] = None
    smoke: Dict[str, Any] = field(default_factory=dict)
    remote_workdir: Optional[str] = None
    binary_path: Optional[str] = None
    report_path: Optional[str] = None
    attention: List[Dict[str, Any]] = field(default_factory=list)
    cases: List[Dict[str, Any]] = field(default_factory=list)
    dir: Optional[str] = None
    has_card: bool = False
    has_spec: bool = False
    errors: List[str] = field(default_factory=list)
    stale: bool = False               # the reconcile hint applies
    verb: str = "wait"
    command: str = ""
    why: str = ""

    # ---- conveniences -----------------------------------------------------

    def rank(self) -> int:
        return STUDY_LANE_RANK.get(self.lane, -1)

    def card_path(self) -> Optional[Path]:
        return (Path(self.dir) / CARD_NAME) if self.dir else None

    def spec_path(self) -> Optional[Path]:
        return (Path(self.dir) / SPEC_NAME) if self.dir else None

    def gate_spec_approved(self) -> str:
        return "granted" if (self.has_card and self.lane != "draft") else "pending"

    def gate_dispatch(self) -> str:
        if any(c.get("jobid") for c in self.cases):
            return "granted"
        return "granted" if self.rank() >= STUDY_LANE_RANK["dispatched"] else "pending"

    def to_card(self) -> StudyCard:
        """The core's StudyCard: the board row, and nothing more."""
        return StudyCard(
            id=self.id,
            lane=self.lane,
            posture=self.posture,
            title=self.title,
            updated=self.updated,
            progress=progress_str(self.counts),
            note=self.why,
        )


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def _read_yaml(path: Path) -> Tuple[Optional[Dict[str, Any]], bool, str]:
    """``(mapping, ok, error)``. Absent is a fact; unparseable is not."""
    if yaml is None:
        return (None, False, "PyYAML is not importable")
    text, ok = probe._read_text(path)
    if not ok:
        return (None, False, "unreadable")
    if text is None:
        return (None, True, "")
    try:
        data = yaml.safe_load(text)
    except Exception as exc:
        return (None, False, "%s" % (exc,))
    if data is None:
        return ({}, True, "")
    if not isinstance(data, dict):
        return (None, False, "the top level is %s, not a mapping" % (type(data).__name__,))
    return (data, True, "")


def progress_of(cases: List[Dict[str, Any]]) -> Dict[str, int]:
    """The same buckets ``analysis/tool/model.py:Card.progress`` reports."""
    counts = {"total": 0, "done": 0, "running": 0, "queued": 0, "pending": 0, "failed": 0}
    for case in cases:
        counts["total"] += 1
        status = str((case or {}).get("status") or "pending")
        if status == "done":
            counts["done"] += 1
        elif status == "running":
            counts["running"] += 1
        elif status == "queued":
            counts["queued"] += 1
        elif status == "pending":
            counts["pending"] += 1
        elif status in ("failed_transient", "failed_systematic"):
            counts["failed"] += 1
    return counts


def progress_str(counts: Dict[str, int]) -> str:
    if not counts or not counts.get("total"):
        return "no cases"
    parts = ["%d/%d done" % (counts.get("done", 0), counts["total"])]
    if counts.get("running"):
        parts.append("%d running" % (counts["running"],))
    waiting = counts.get("queued", 0) + counts.get("pending", 0)
    if waiting:
        parts.append("%d queued" % (waiting,))
    if counts.get("failed"):
        parts.append("%d failed" % (counts["failed"],))
    return ", ".join(parts)


def posture_of(lane: str) -> str:
    """The plan's map. An unknown lane is never quietly parked."""
    return STUDY_POSTURE.get(str(lane or ""), NEEDS_YOU)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _ceiling(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def read_study(path: Path, now_ts: Optional[float]) -> Study:
    """One study directory, whatever state it is in. Never raises."""
    sid = path.name
    study = Study(id=sid, dir=str(path))
    study.has_spec = (path / SPEC_NAME).is_file()
    spec, spec_ok, spec_err = _read_yaml(path / SPEC_NAME)
    if spec_ok and spec:
        study.title = str(spec.get("title") or "")
        study.kind = str(spec.get("kind") or "")
        study.app = str(spec.get("app") or "")
        study.cluster = str(spec.get("cluster") or "")
        study.account = str(spec.get("account") or "")
        budget = spec.get("budget") or {}
        if isinstance(budget, dict):
            study.ceiling_core_hours = _ceiling(budget.get("ceiling_core_hours"))
    elif not spec_ok:
        study.errors.append("%s: %s" % (SPEC_NAME, spec_err))

    card_file = path / CARD_NAME
    study.has_card = card_file.is_file()
    if not study.has_card:
        study.lane = NO_CARD
        study.posture = posture_of(NO_CARD)
        return study

    card, ok, err = _read_yaml(card_file)
    if not ok or card is None:
        study.lane = UNREADABLE
        study.posture = posture_of(UNREADABLE)
        study.errors.append("%s: %s" % (CARD_NAME, err or "unreadable"))
        return study

    study.lane = str(card.get("state") or "draft")
    study.posture = posture_of(study.lane)
    study.title = str(card.get("title") or study.title)
    study.kind = str(card.get("kind") or study.kind)
    study.app = str(card.get("app") or study.app)
    study.cluster = str(card.get("cluster") or study.cluster)
    study.account = str(card.get("account") or study.account)
    study.repo_sha = card.get("repo_sha")
    study.created = str(card.get("created") or "")
    study.updated = str(card.get("updated") or "")
    cases = card.get("cases") or []
    study.cases = [c for c in cases if isinstance(c, dict)]
    study.counts = progress_of(study.cases)
    budget = card.get("budget") or {}
    if isinstance(budget, dict):
        study.spent_core_hours = _float(budget.get("spent_core_hours"))
        ceiling = _ceiling(budget.get("ceiling_core_hours"))
        if ceiling is not None:
            study.ceiling_core_hours = ceiling
    smoke = card.get("smoke") or {}
    study.smoke = smoke if isinstance(smoke, dict) else {}
    study.remote_workdir = card.get("remote_workdir")
    study.binary_path = card.get("binary_path")
    study.report_path = card.get("report_path")
    attention = card.get("attention") or []
    study.attention = [a for a in attention if isinstance(a, dict)]

    if study.lane not in STUDY_LANE_RANK and study.lane not in OFF_PIPELINE:
        study.errors.append(
            "unknown lane %r: not one of analysis StudyState" % (study.lane,)
        )

    study.stale = is_stale(study, now_ts)
    return study


def is_stale(study: Study, now_ts: Optional[float]) -> bool:
    """True when the card has not been reconciled for over a day.

    ``now_ts`` comes from ``ctx.now``, never from the clock, so the whole
    derivation stays reproducible from its inputs.
    """
    if not study.has_card or now_ts is None:
        return False
    at = derive.ts_of(study.updated)
    if at is None:
        return True
    return (now_ts - at) > RECONCILE_STALE_SECONDS


def discover(cfg: Any, now_ts: Optional[float] = None) -> Tuple[List[Study], List[str]]:
    """Every study directory, in id order, plus the ids that are not safe slugs."""
    root = studies_dir(cfg)
    out: List[Study] = []
    unsafe: List[str] = []
    if not root.is_dir():
        return (out, unsafe)
    try:
        entries = sorted(p for p in root.iterdir() if p.is_dir())
    except Exception:
        return (out, unsafe)
    for path in entries:
        if not ((path / CARD_NAME).is_file() or (path / SPEC_NAME).is_file()):
            continue                      # .git, .DS_Store, results/: not a study
        if not config.is_safe_id(path.name):
            unsafe.append(path.name)      # it holds a study file, so say so
            continue
        study = read_study(path, now_ts)
        decide(study, cfg)
        out.append(study)
    return (out, unsafe)


# --------------------------------------------------------------------------
# The one next move
# --------------------------------------------------------------------------


def decide(study: Study, cfg: Any) -> Study:
    """One verb, one copyable command, one reason. Pure."""
    an = analysis_launcher(cfg)
    sid = study.id
    lane = study.lane

    if lane == NO_CARD:
        study.verb = "blueprint"
        study.command = "/analysis-blueprint %s" % (sid,)
        study.why = "no card.yaml yet (only study.yaml), owned by `/analysis-blueprint`"
    elif lane == UNREADABLE:
        study.verb = "fix-card"
        study.command = "%s validate %s" % (an, sid)
        study.why = "card.yaml does not parse: %s" % (
            study.errors[-1] if study.errors else "unreadable",
        )
    elif lane == "draft":
        study.verb = "approve"
        study.command = "%s validate %s" % (an, sid)
        study.why = "the spec is still a draft; validate it, then `%s init %s`" % (an, sid)
    elif lane == "approved":
        study.verb = "smoke"
        study.command = "/analysis-run %s" % (sid,)
        study.why = "approved and not yet smoked; a smoke is cheap and local"
    elif lane == "smoking":
        study.verb = "wait"
        study.command = "%s status %s" % (an, sid)
        study.why = "a local smoke is running"
    elif lane == "ready":
        study.verb = "dispatch"
        study.command = "/analysis-run %s" % (sid,)
        study.why = "smoke passed and within budget; dispatch when you want the core-hours spent"
    elif lane in ("dispatched", "running"):
        study.verb = "wait"
        study.command = "%s reconcile %s" % (an, sid)
        study.why = "live on %s: %s" % (study.cluster or "HPC", progress_str(study.counts))
    elif lane in ("collecting", "analyzing"):
        study.verb = "wait"
        study.command = "%s reconcile %s" % (an, sid)
        study.why = "%s results: %s" % (lane, progress_str(study.counts))
    elif lane == "attention":
        study.verb = "triage"
        study.command = "%s status %s" % (an, sid)
        study.why = "parked for a human: %s" % (_last_reason(study) or "see the card",)
    elif lane == "budget_exceeded":
        study.verb = "decide"
        study.command = "%s estimate %s" % (an, sid)
        study.why = "halted on the core-hour cap (%s); raise the ceiling or drop cases" % (
            core_hours_str(study),
        )
    elif lane == "connection_down":
        study.verb = "fix-connection"
        study.command = "ssh %s" % (study.cluster or "the cluster",)
        study.why = "the toolkit could not reach %s; nothing can proceed" % (
            study.cluster or "the cluster",
        )
    elif lane == "reported":
        study.verb = "read"
        study.command = "%s report %s" % (an, sid)
        study.why = "the report is written; read it, then file the learning"
    elif lane == "done":
        study.verb = "none"
        study.command = ""
        study.why = "complete: %s" % (progress_str(study.counts),)
    else:
        study.verb = "look"
        study.command = "%s status %s" % (an, sid)
        study.why = "unknown lane %r: this board does not model it" % (lane,)

    if study.stale:
        study.why += "; card updated %s, so run `%s reconcile %s`" % (
            study.updated[:10] or "never", an, sid,
        )
    return study


def _last_reason(study: Study) -> str:
    for rec in reversed(study.attention):
        reason = rec.get("reason")
        if reason:
            return str(reason)
    return ""


def core_hours_str(study: Study) -> str:
    base = "%.1f" % (study.spent_core_hours,)
    if study.ceiling_core_hours is not None:
        return "%s / %.0f core-h" % (base, study.ceiling_core_hours)
    return "%s core-h" % (base,)


# --------------------------------------------------------------------------
# collect: pure. It loads, it does not write.
# --------------------------------------------------------------------------


def collect(ctx: Any) -> None:
    now_ts = derive.ts_of(ctx.now)
    studies, unsafe = discover(ctx.config, now_ts)
    ctx.meta["studies"] = studies
    ctx.meta["study_cards"] = [s.to_card() for s in studies]
    ctx.meta["studies_unsafe"] = unsafe
    if unsafe:
        ctx.log(
            "studies: ignoring %d directory name(s) that are not safe slugs: %s"
            % (len(unsafe), ", ".join(unsafe))
        )


def studies_for(ctx: Any) -> List[Study]:
    """The collected studies, loading them once if ``collect`` did not run."""
    rows = ctx.meta.get("studies")
    if rows is None:
        collect(ctx)
        rows = ctx.meta.get("studies") or []
    return list(rows)


def sort_key(study: Study) -> Tuple[int, int, str]:
    return (POSTURE_ORDER.get(study.posture, 99), -study.rank(), study.id)


# --------------------------------------------------------------------------
# Studies/<id>.md
# --------------------------------------------------------------------------

HEAD_BEGIN, HEAD_END, BODY_BEGIN, BODY_END = probe.MARKERS
EMPTY_HUMAN = "\n\n## Notes\n\n\n"


def frontmatter(study: Study) -> str:
    lines = [
        "---",
        "study: %s" % (study.id,),
        "lane: %s" % (study.lane,),
        "posture: %s" % (study.posture,),
        "kind: %s" % (study.kind or "unknown",),
        "app: %s" % (study.app or "unknown",),
        "cluster: %s" % (study.cluster or "unknown",),
        "title: %s" % (study.title.replace(":", " -") or study.id,),
        "cases_total: %d" % (study.counts.get("total", 0),),
        "cases_done: %d" % (study.counts.get("done", 0),),
        "cases_failed: %d" % (study.counts.get("failed", 0),),
        "core_hours: %s" % (("%.1f" % study.spent_core_hours),),
        "core_hours_ceiling: %s"
        % ("" if study.ceiling_core_hours is None else ("%.0f" % study.ceiling_core_hours),),
        "card: %s" % ("present" if study.has_card else "absent",),
        "card_updated: %s" % (study.updated or "never",),
        "reconcile_stale: %s" % ("true" if study.stale else "false"),
        "updated: %s" % (render.STAMP,),
        "tags: [factory-study]",
        "---",
    ]
    return "\n".join(lines)


def head_block(study: Study, ctx: Any) -> str:
    """Small, like a feature head block, and for the same reason: Obsidian's
    merge into an open buffer finds the human text only while the bytes above it
    move by less than about 520 per run."""
    bits = ["[[Home]]", "**%s**" % (study.lane,), study.posture]
    if study.title:
        bits.append(study.title)
    if study.counts.get("total"):
        bits.append(progress_str(study.counts))
    out = [" - ".join(bits), ""]
    out.append("> **Next:** %s" % (study.why or study.verb,))
    if study.command:
        out.append("> `%s`" % (study.command,))
    out.append("")
    out.append("## Gates")
    out.append("")
    out.append(
        "_The analysis toolkit owns these two. They are words, not boxes: a tick here "
        "would be read back by nobody._"
    )
    out.append("")
    out.append("- spec_approved: **%s**" % (study.gate_spec_approved(),))
    out.append("- dispatch: **%s**" % (study.gate_dispatch(),))
    return "\n".join(out)


def _stands_table(study: Study, ctx: Any) -> List[str]:
    cell = render.cell
    rows = ["| property | value |", "|---|---|"]
    rows.append("| lane | %s |" % (cell(study.lane),))
    rows.append("| kind | %s |" % (cell(study.kind or "unknown"),))
    rows.append("| app | %s |" % (cell(study.app or "unknown"),))
    rows.append(
        "| cluster | %s |"
        % (cell("%s (%s)" % (study.cluster or "unknown", study.account or "no account")),)
    )
    rows.append("| repo sha | %s |" % (cell(study.repo_sha or "unknown"),))
    rows.append("| cases | %s |" % (cell(progress_str(study.counts)),))
    rows.append("| core-hours | %s |" % (cell(core_hours_str(study)),))
    smoke = study.smoke or {}
    smoke_text = str(smoke.get("status") or "unknown")
    if smoke.get("where"):
        smoke_text += " (%s)" % (smoke["where"],)
    if smoke.get("est_core_hours_per_case") is not None:
        smoke_text += ", %s core-h per case estimated" % (
            smoke["est_core_hours_per_case"],
        )
    rows.append("| smoke | %s |" % (cell(smoke_text),))
    rows.append("| card created | %s |" % (cell(study.created or "unknown"),))
    rows.append("| card updated | %s |" % (cell(study.updated or "never"),))
    return rows


def body_block(study: Study, ctx: Any) -> str:
    cfg = ctx.config
    an = analysis_launcher(cfg)
    cell = render.cell
    out: List[str] = []

    out.append("## Open the study")
    out.append("")
    spec = study.spec_path()
    card = study.card_path()
    if spec is not None and spec.is_file():
        out.append("- Spec: [%s](%s)" % (SPEC_NAME, render.file_uri(spec)))
    else:
        out.append("- Spec: **absent**. `%s new %s` scaffolds one." % (an, study.id))
    if card is not None and card.is_file():
        out.append(
            "- Card: [%s](%s) (the analysis toolkit owns it; the factory only reads it)"
            % (CARD_NAME, render.file_uri(card))
        )
    else:
        out.append("- Card: **absent**. `%s init %s` mints one from an approved spec."
                   % (an, study.id))
    if study.report_path:
        out.append("- Report: [%s](%s)" % (
            os.path.basename(str(study.report_path)),
            render.file_uri(study.report_path),
        ))
    if study.remote_workdir:
        out.append("- HPC workdir: `%s:%s`" % (study.cluster or "cluster", study.remote_workdir))
    if study.binary_path:
        out.append("- Binary: `%s`" % (study.binary_path,))
    out.append("")
    out.append("```")
    out.append("%s status %s" % (an, study.id))
    if study.command and not study.command.startswith("/"):
        out.append(study.command)
    out.append("```")
    out.append("")

    out.append("## Where it stands")
    out.append("")
    out.extend(_stands_table(study, ctx))
    out.append("")

    out.append("## Cases")
    out.append("")
    if not study.cases:
        out.append("_No case enumerated yet._")
    else:
        out.append(progress_str(study.counts) + ".")
        failed = [
            c for c in study.cases
            if str(c.get("status") or "").startswith("failed")
        ]
        if failed:
            out.append("")
            out.append("| case | status | jobid | diagnosis |")
            out.append("|---|---|---|---|")
            for c in sorted(failed, key=lambda c: _idx(c))[:8]:
                out.append(
                    "| %s | %s | %s | %s |"
                    % (
                        cell(c.get("idx")),
                        cell(c.get("status")),
                        cell(c.get("jobid") or "none"),
                        cell(c.get("diagnosis") or ""),
                    )
                )
            if len(failed) > 8:
                out.append("")
                out.append("_and %d more failed cases in the card._" % (len(failed) - 8,))
    out.append("")

    if study.attention:
        out.append("## Attention")
        out.append("")
        for rec in study.attention[-8:]:
            out.append("- %s" % (cell(rec.get("reason") or rec),))
        out.append("")

    out.append("## Freshness")
    out.append("")
    if not study.has_card:
        out.append(
            "- There is no card, so there is nothing to reconcile. The spec is owned by "
            "`/analysis-blueprint`."
        )
    else:
        out.append("- The card says it was updated %s." % (study.updated or "never",))
        if study.stale:
            out.append(
                "- That is more than a day behind this board, so the live picture may "
                "have moved: `%s reconcile %s`." % (an, study.id)
            )
        else:
            out.append("- That is within a day of this board, so the row is current.")
    out.append(
        "- The factory never writes `%s` and never runs `analysis reconcile`. A study is "
        "exactly as fresh as your last reconcile." % (CARD_NAME,)
    )
    out.append("")

    if study.errors:
        out.append("## Errors")
        out.append("")
        for line in study.errors:
            out.append("- %s" % (cell(line),))
        out.append("")

    rows = ctx.timeline.read(study.id) if ctx.timeline else []
    out.append("## Timeline")
    out.append("")
    if rows:
        for rec in rows[-12:]:
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


def _idx(case: Dict[str, Any]) -> int:
    try:
        return int(case.get("idx"))
    except Exception:
        return 0


def compose_note(study: Study, ctx: Any, existing: Optional[str]) -> str:
    """The four-marker note, with both human regions preserved byte for byte.

    The tail after ``body:end`` is human prose too: that is where a cursor at
    the end of the file lands. Same rule as ``render.compose_note``.
    """
    human = EMPTY_HUMAN
    tail = ""
    if existing and HEAD_END in existing and BODY_BEGIN in existing:
        human = existing.split(HEAD_END, 1)[1].split(BODY_BEGIN, 1)[0]
    if existing and BODY_END in existing:
        tail = existing.split(BODY_END, 1)[1]
        if not tail.strip():
            tail = ""
    text = "\n".join(
        [
            frontmatter(study),
            "# %s" % (study.id,),
            "",
            HEAD_BEGIN,
            head_block(study, ctx),
            HEAD_END,
        ]
    )
    text += human
    text += "\n".join([BODY_BEGIN, body_block(study, ctx), BODY_END])
    text += tail if tail else "\n"
    return text


def note_path(ctx: Any, study_id: str) -> Path:
    return Path(ctx.config.studies_dir) / (config.validate_id(study_id) + ".md")


def write_study(study: Study, ctx: Any) -> str:
    """``written``, ``skipped``, ``refused`` or ``dry-run``. Same rules as a note."""
    cfg = ctx.config
    path = note_path(ctx, study.id)
    render.guard_path(cfg, path)
    existing, ok = probe._read_text(path)
    if not ok:
        ctx.log("study note %s is unreadable; not rewritten" % (path,))
        return "refused"
    if existing is not None:
        missing = [m for m in probe.MARKERS if m not in existing]
        if missing:
            ctx.log(
                "study note %s is missing %s: not rewritten"
                % (path, ", ".join(missing))
            )
            return "refused"
    text = compose_note(study, ctx, existing)
    key = "Studies/%s.md" % (study.id,)
    dg = snapshot.digest(text)
    stamp = ctx.state.stamp(key, dg, ctx.now) if ctx.state is not None else ctx.now
    final = text.replace(render.STAMP, stamp)
    status = render.atomic_write(path, final, ctx.dry_run)
    if ctx.stamps is not None:
        ctx.stamps[key] = (dg, stamp)
    return status


def write_studies(ctx: Any) -> Dict[str, Any]:
    """Write every study note. Called once per board, from ``home_sections``."""
    counts = {"written": 0, "skipped": 0, "refused": 0, "dry-run": 0}
    refused: List[str] = []
    for study in sorted(studies_for(ctx), key=lambda s: s.id):
        # Before composing: the note prints the timeline, so a line appended
        # after the write would change the note on the next run for no reason.
        if ctx.timeline is not None and not ctx.timeline.has(study.id, "study-adopted"):
            ctx.timeline.append(
                study.id,
                {
                    "at": ctx.now,
                    "event": "study-adopted",
                    "lane": study.lane,
                    "why": "board adopted this study",
                },
            )
        try:
            status = write_study(study, ctx)
        except config.RefusedWrite as exc:
            ctx.log(str(exc))
            status = "refused"
        except Exception as exc:                      # one bad study is not fatal
            ctx.log("study %s failed to render: %s" % (study.id, exc))
            status = "refused"
        counts[status] = counts.get(status, 0) + 1
        if status == "refused":
            refused.append(study.id)
    return {"counts": counts, "refused": refused}


# --------------------------------------------------------------------------
# Home.md
# --------------------------------------------------------------------------


def outputs(ctx: Any) -> Dict[str, Any]:
    """Write the study notes, at most once per run, whoever asks first.

    This is the shape a core ``outputs(ctx)`` hook in ``render.sync`` would
    call. Until that hook exists, ``home_sections`` calls it, which is the one
    place the core runs an extension after derive and inside the renderer. When
    the hook lands, ``sync`` calls it first and ``home_sections`` reuses the
    result, so nothing is written twice either way.
    """
    result = ctx.meta.get("_studies_write")
    if result is None:
        result = write_studies(ctx)
        ctx.meta["_studies_write"] = result
    return result


def home_sections(ctx: Any) -> List[Tuple[str, str, int]]:
    studies = studies_for(ctx)
    result = outputs(ctx)

    cell = render.cell
    an = analysis_launcher(ctx.config)
    lines: List[str] = []
    if not studies:
        lines.append(
            "_No study in `%s`. `%s new <id>` scaffolds one; `/analysis-blueprint` writes "
            "the spec._" % (render.tilde(studies_dir(ctx.config)), an)
        )
        return [("Studies (0)", "\n".join(lines), 20)]

    stale = [s for s in studies if s.stale]
    lines.append(
        "_%d stud%s. The analysis toolkit is the only writer of a card; this board only "
        "reads them, so a row is exactly as fresh as your last reconcile._"
        % (len(studies), "y" if len(studies) == 1 else "ies")
    )
    lines.append("")
    for study in sorted(studies, key=sort_key):
        parts = ["[[%s]]" % (study.id,), "`%s`" % (study.lane,), study.posture]
        if study.counts.get("total"):
            parts.append(progress_str(study.counts))
        lines.append("- %s - %s" % (" - ".join(parts), cell(study.why)))
    if stale:
        lines.append("")
        lines.append(
            "_Not reconciled within a day: %s. `%s reconcile --all`._"
            % (", ".join("[[%s]]" % (s.id,) for s in stale), an)
        )
    if result.get("refused"):
        lines.append("")
        lines.append(
            "_%d study note kept its own bytes because a factory marker is missing: %s. "
            "Restore the four markers, or delete the note and rerun._"
            % (len(result["refused"]), ", ".join(result["refused"]))
        )
    unsafe = ctx.meta.get("studies_unsafe") or []
    if unsafe:
        lines.append("")
        lines.append(
            "_Ignored, not a safe slug: %s._" % (", ".join("`%s`" % (u,) for u in unsafe),)
        )
    return [("Studies (%d)" % (len(studies),), "\n".join(lines), 20)]


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------


def doctor_checks(ctx: Any) -> List[Tuple[str, bool, str]]:
    """``ctx`` here carries only config, paths and ``now``: load our own data."""
    cfg = ctx.config
    out: List[Tuple[str, bool, str]] = []

    out.append((
        "PyYAML importable for the studies adapter",
        yaml is not None,
        "pip install PyYAML, or set FACTORY_PYTHON; without it no study renders",
    ))

    av = os.environ.get("ANALYSIS_VAULT")
    overlaps = bool(av) and _overlaps(Path(av).expanduser(), Path(cfg.vault))
    out.append((
        "$ANALYSIS_VAULT does not overlap the factory vault",
        not overlaps,
        "$ANALYSIS_VAULT=%s overlaps %s. analysis/tool/vault.py has its own write_home "
        "and would fight render.py for Home.md. Point it elsewhere or unset it."
        % (av, cfg.vault),
    ))

    root = studies_dir(cfg)
    out.append((
        "studies directory present",
        root.is_dir(),
        "no %s: the Studies section renders empty" % (root,),
    ))

    studies, unsafe = discover(cfg, derive.ts_of(ctx.now))
    out.append((
        "every study id is a safe slug",
        not unsafe,
        "ignored: %s. Rename to letters, digits, dot, dash, underscore." % (", ".join(unsafe),),
    ))
    bad = [s.id for s in studies if s.lane == UNREADABLE]
    out.append((
        "every card.yaml parses",
        not bad,
        "unreadable: %s. Those studies render as needs-you." % (", ".join(bad),),
    ))
    unknown = [s.id for s in studies if s.lane not in STUDY_POSTURE]
    out.append((
        "every study lane is one the board models",
        not unknown,
        "unknown lane in: %s. Add it to STUDY_POSTURE in tool/ext_studies.py."
        % (", ".join(unknown),),
    ))
    stale = [s.id for s in studies if s.stale]
    out.append((
        "every study card was reconciled within a day",
        not stale,
        "stale: %s. Run `%s reconcile --all`; the factory never does."
        % (", ".join(stale), analysis_launcher(cfg)),
    ))

    notes_dir = Path(cfg.studies_dir)
    bad_markers: List[str] = []
    orphans: List[str] = []
    known = set(s.id for s in studies)
    if notes_dir.is_dir():
        for note in sorted(notes_dir.glob("*.md")):
            text, tok = probe._read_text(note)
            if tok and text and any(m not in text for m in probe.MARKERS):
                bad_markers.append(note.stem)
            if note.stem not in known:
                orphans.append(note.stem)
    out.append((
        "every study note keeps its four markers",
        not bad_markers,
        "missing in: %s. The adapter refuses those notes." % (", ".join(bad_markers),),
    ))
    out.append((
        "no orphan note in Studies/",
        not orphans,
        "no study directory for: %s. Remove the note by hand; no script deletes a note."
        % (", ".join(orphans),),
    ))
    return out


# --------------------------------------------------------------------------
# The verb
# --------------------------------------------------------------------------


def run_studies(argv: List[str], ctx: Any) -> int:
    """``factory studies [<id>]``: print the rows. Writes nothing, ever."""
    wanted = [a for a in (argv or []) if not a.startswith("-")]
    studies = studies_for(ctx)
    if wanted:
        studies = [s for s in studies if s.id in set(wanted)]
        if not studies:
            print("no study %s in %s" % (", ".join(wanted), studies_dir(ctx.config)))
            return 3
    if not studies:
        print("no study in %s" % (studies_dir(ctx.config),))
        return 0
    width = max(len(s.id) for s in studies)
    for study in sorted(studies, key=sort_key):
        print(
            "%-*s %-16s %-9s %s"
            % (width, study.id, study.lane, study.posture, progress_str(study.counts))
        )
        print("%-*s   %s" % (width, "", study.why))
        if study.command:
            print("%-*s   run %s" % (width, "", study.command))
    return 1 if any(s.posture == NEEDS_YOU for s in studies) else 0


VERBS = {"studies": run_studies}
HELP = {"studies": "print the analysis studies, read only"}
