"""The data types: a campaign, its measures and proposals, a run, a ledger entry, a finding.

This module owns the shapes and the clock. It reads no file and runs no
command: ``spec.py``, ``manifest.py``, ``ledger.py`` and ``findings.py`` parse
into these types and write them back out.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

VERDICTS = ("supported", "refuted", "inconclusive", "failed")
AUTONOMY = ("propose-only", "within-budget", "manual")
STATUSES = ("draft", "active", "done", "abandoned")

# The manifest blocks that may never change after launch.
IMMUTABLE = ("command", "cwd", "env", "code", "inputs", "hypothesis")


# --------------------------------------------------------------------------
# Time
# --------------------------------------------------------------------------


def utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)


def now_iso() -> str:
    """``2026-09-25T14:03:10Z``: the manifest's clock format."""
    return utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp(when: Optional[_dt.datetime] = None) -> str:
    """``20260925T140310Z``: the ledger's clock format."""
    return (when or utcnow()).strftime("%Y%m%dT%H%M%SZ")


def today() -> _dt.date:
    return _dt.date.today()


def normalize(value: Any) -> Any:
    """YAML turns an unquoted timestamp into a datetime; turn it back into text."""
    if isinstance(value, _dt.datetime):
        if value.tzinfo is not None:
            value = value.astimezone(_dt.timezone.utc).replace(tzinfo=None)
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def parse_iso(text: Optional[str]) -> Optional[_dt.datetime]:
    if not text:
        return None
    try:
        return _dt.datetime.strptime(str(text), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# campaign.md
# --------------------------------------------------------------------------


@dataclass
class Measure:
    name: str
    unit: str
    how: str
    added: str
    kind: str = ""                  # "cmd" | "csv" | "" when neither form matched
    command: str = ""               # the backtick span, for kind "cmd"
    csv_file: str = ""
    csv_column: str = ""
    csv_reduce: str = ""


@dataclass
class Proposal:
    id: str
    tag: str
    group: Optional[str]
    estimate: Optional[float]
    tests: str
    because: List[str]
    ticked: bool
    cwd: Optional[str] = None
    cmd: Optional[str] = None
    ins: List[str] = field(default_factory=list)
    cluster: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    ntasks: Optional[int] = None
    walltime: Optional[str] = None
    partition: Optional[str] = None
    line: int = 0                   # 0-based line of the entry in campaign.md
    end: int = 0                    # one past its last sub-bullet


@dataclass
class Campaign:
    dir: Path
    root: Path
    meta: Dict[str, Any]
    text: str
    hypothesis: str = ""
    constraints: List[Dict[str, str]] = field(default_factory=list)
    measures: List[Measure] = field(default_factory=list)
    proposals: List[Proposal] = field(default_factory=list)
    headings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.dir.name

    @property
    def knobs(self) -> List[str]:
        return [c["knob"] for c in self.constraints if c.get("knob")]

    def measure(self, name: str) -> Optional[Measure]:
        return next((m for m in self.measures if m.name == name), None)

    def proposal(self, run_id: str) -> Optional[Proposal]:
        return next((p for p in self.proposals if p.id == run_id), None)

    def budget(self, key: str) -> Optional[float]:
        b = self.meta.get("budget") or {}
        v = b.get(key) if isinstance(b, dict) else None
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    @property
    def runs_dir(self) -> Path:
        return self.dir / "runs"


# --------------------------------------------------------------------------
# manifest.yaml
# --------------------------------------------------------------------------

# Top-level key order, with a blank line before each key named in GROUP_BREAKS.
RUN_KEYS = (
    "run", "campaign", "tag", "group", "replay_of", "proposal", "hypothesis",
    "started", "finished", "exit", "host", "cluster", "slurm", "local",
    "code",
    "command", "cwd", "env",
    "inputs", "identity",
    "outputs",
    "qoi",
    "verdict", "judged",
)
GROUP_BREAKS = ("started", "code", "command", "inputs", "outputs", "qoi", "verdict")


@dataclass
class Run:
    run: str
    campaign: str
    tag: str
    group: Optional[str] = None
    replay_of: Optional[str] = None
    proposal: Dict[str, Any] = field(default_factory=dict)
    hypothesis: str = ""
    started: Optional[str] = None
    finished: Optional[str] = None
    exit: Optional[int] = None
    host: Optional[str] = None
    cluster: str = "local"
    slurm: Optional[Dict[str, Any]] = None
    local: Optional[Dict[str, Any]] = None
    code: Dict[str, Any] = field(default_factory=dict)
    command: str = ""
    cwd: str = "."
    env: Dict[str, str] = field(default_factory=dict)
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    identity: Optional[str] = None
    outputs: Dict[str, Any] = field(default_factory=dict)
    qoi: Dict[str, Any] = field(default_factory=dict)
    verdict: Optional[str] = None
    judged: Optional[Dict[str, Any]] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    path: Optional[Path] = None      # the run directory; never serialized

    def to_dict(self) -> Dict[str, Any]:
        out = {k: getattr(self, k) for k in RUN_KEYS}
        out.update(self.extra)
        return out

    @classmethod
    def from_dict(cls, data: Dict[str, Any], path: Optional[Path] = None) -> "Run":
        data = normalize(dict(data))
        known = {k: data.pop(k) for k in list(data) if k in RUN_KEYS}
        run = cls(run=str(known.pop("run", "")), campaign=str(known.pop("campaign", "")),
                  tag=str(known.pop("tag", "")), path=path, extra=data)
        for k, v in known.items():
            setattr(run, k, v)
        for k in ("proposal", "code", "env", "outputs", "qoi"):
            if getattr(run, k) is None:
                setattr(run, k, {})
        if run.inputs is None:
            run.inputs = []
        return run

    @property
    def core_hours(self) -> float:
        for block in (self.slurm, self.local):
            if isinstance(block, dict) and isinstance(block.get("core_hours"), (int, float)):
                return float(block["core_hours"])
        return 0.0

    @property
    def is_slurm(self) -> bool:
        return self.cluster not in (None, "local")

    @property
    def done(self) -> bool:
        return self.finished is not None or self.exit is not None


# --------------------------------------------------------------------------
# LEDGER.md and FINDINGS.md
# --------------------------------------------------------------------------


@dataclass
class LedgerEntry:
    id: str
    tag: str
    group: str
    stamp: str
    where: str
    hypothesis: str
    done: Optional[Dict[str, str]] = None      # {stamp, exit, core_h}
    verdict: Optional[Dict[str, str]] = None   # {word, qoi, finding}
    notes: List[str] = field(default_factory=list)
    line: int = 0
    end: int = 0


@dataclass
class Finding:
    n: int
    claim: str
    date: str = ""
    runs: List[str] = field(default_factory=list)
    measures: List[str] = field(default_factory=list)
    refutes: str = "-"
    closes: bool = False
    body: str = ""
    fields: Dict[str, str] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return "F%d" % self.n
