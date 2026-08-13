"""Domain model: study cards, cases, and the Kanban state machine.

A *card* (``card.yaml``) is the durable, mutable state of one study. It lives
beside the immutable ``study.yaml`` spec in ``analysis/studies/<id>/``. The AI
is stateless between sessions; the card is the single source of truth, and
``reconcile`` rebuilds the live picture from it plus SLURM.

Serialization is plain dict <-> YAML. Enums serialize to their ``.value``
strings and datetimes to ISO-8601, so a card is human-readable and diffable.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    """UTC timestamp, second resolution, ISO-8601 with trailing Z."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------


class StudyState(str, Enum):
    """The Kanban lane a study card sits in."""

    DRAFT = "draft"                    # spec being written
    APPROVED = "approved"              # spec approved, not yet smoked
    SMOKING = "smoking"                # local smoke in progress
    READY = "ready"                    # smoke passed + within budget, ready to dispatch
    DISPATCHED = "dispatched"          # jobs submitted, none running yet
    RUNNING = "running"                # >=1 case running/queued on HPC
    COLLECTING = "collecting"          # all cases terminal, pulling results
    ANALYZING = "analyzing"            # QoIs extracted, computing derived quantities
    REPORTED = "reported"             # report.html written
    DONE = "done"                      # complete (possibly with flagged gaps)
    # Off-happy-path lanes (require human eyes on the board):
    ATTENTION = "attention"            # systematic failure / ambiguous, parked
    BUDGET_EXCEEDED = "budget_exceeded"  # refused or halted on the core-hour cap
    CONNECTION_DOWN = "connection_down"  # ssh/ticket unavailable; cannot proceed


# Lanes that mean "a human should look at this on the board".
ATTENTION_LANES = {
    StudyState.ATTENTION,
    StudyState.BUDGET_EXCEEDED,
    StudyState.CONNECTION_DOWN,
}

# Lanes that mean "no further automated progress is possible/needed".
TERMINAL_LANES = {StudyState.DONE} | ATTENTION_LANES


class CaseStatus(str, Enum):
    """Per-case lifecycle within a study."""

    PENDING = "pending"                # enumerated, not yet submitted
    QUEUED = "queued"                  # submitted, SLURM PENDING
    RUNNING = "running"                # SLURM RUNNING
    DONE = "done"                      # completed successfully, QoIs collected
    FAILED_TRANSIENT = "failed_transient"    # wallclock/node/preempt -> retryable
    FAILED_SYSTEMATIC = "failed_systematic"  # diverged/NaN/bad input -> parked


TERMINAL_CASE_STATUSES = {
    CaseStatus.DONE,
    CaseStatus.FAILED_SYSTEMATIC,
}


class StudyKind(str, Enum):
    SWEEP = "sweep"
    CONVERGENCE = "convergence"
    OPTIMIZATION = "optimization"


# --------------------------------------------------------------------------
# Dataclasses
# --------------------------------------------------------------------------


@dataclass
class Case:
    """One simulation within a study."""

    idx: int
    params: Dict[str, Any] = field(default_factory=dict)   # MOOSE HIT path -> value
    status: CaseStatus = CaseStatus.PENDING
    jobid: Optional[str] = None            # SLURM job/array-task id, e.g. "12345_3"
    slurm_state: Optional[str] = None      # raw sacct State for diagnostics
    retries: int = 0
    core_hours: float = 0.0                # current attempt's core-hours
    spent_core_hours: float = 0.0          # banked core-hours from prior (retried) attempts
    qoi: Dict[str, Any] = field(default_factory=dict)
    workdir: Optional[str] = None          # remote run dir
    file_base: Optional[str] = None        # Outputs/file_base for this case
    diagnosis: Optional[str] = None        # set when parked systematic

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Case":
        d = dict(d)
        # An explicit `status: null` in a hand-edited card must fall back to the
        # dataclass default (PENDING), not an untyped None that no lane logic matches.
        if d.get("status") is None:
            d.pop("status", None)
        else:
            d["status"] = CaseStatus(d["status"])
        # tolerate unknown keys from a newer schema without crashing
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Smoke:
    status: str = "pending"        # pending|passed|failed
    where: Optional[str] = None    # local|hpc
    binary: Optional[str] = None
    runtime_s: Optional[float] = None
    est_core_hours_per_case: Optional[float] = None
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Smoke":
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in dict(d).items() if k in known})


@dataclass
class Budget:
    ceiling_core_hours: Optional[float] = None
    spent_core_hours: float = 0.0
    max_concurrent_jobs: int = 16
    max_walltime_per_case: str = "02:00:00"

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Budget":
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in dict(d).items() if k in known})


@dataclass
class Card:
    """Durable state of one study. Serializes to card.yaml."""

    id: str
    title: str = ""
    kind: str = StudyKind.SWEEP.value
    state: StudyState = StudyState.DRAFT
    app: str = "combined"
    cluster: str = "bitterroot"
    account: str = "intern"
    repo_sha: Optional[str] = None
    build_jobid: Optional[str] = None      # SLURM job that builds the pinned binary
    binary_path: Optional[str] = None      # cached remote binary once built
    remote_workdir: Optional[str] = None   # /scratch/<user>/analysis/<id>
    created: str = field(default_factory=now_iso)
    updated: str = field(default_factory=now_iso)
    smoke: Smoke = field(default_factory=Smoke)
    budget: Budget = field(default_factory=Budget)
    cases: List[Case] = field(default_factory=list)
    attention: List[Dict[str, Any]] = field(default_factory=list)
    report_path: Optional[str] = None
    history: List[str] = field(default_factory=list)   # append-only audit log

    # ---- derived -----------------------------------------------------------

    def progress(self) -> Dict[str, int]:
        counts = {
            "total": len(self.cases),
            "done": 0,
            "running": 0,
            "queued": 0,
            "pending": 0,
            "failed": 0,
        }
        for c in self.cases:
            if c.status == CaseStatus.DONE:
                counts["done"] += 1
            elif c.status == CaseStatus.RUNNING:
                counts["running"] += 1
            elif c.status == CaseStatus.QUEUED:
                counts["queued"] += 1
            elif c.status == CaseStatus.PENDING:
                counts["pending"] += 1
            elif c.status in (
                CaseStatus.FAILED_TRANSIENT,
                CaseStatus.FAILED_SYSTEMATIC,
            ):
                counts["failed"] += 1
        return counts

    def all_cases_terminal(self) -> bool:
        """True when every case is done or parked systematic (no live work)."""
        return bool(self.cases) and all(
            c.status in TERMINAL_CASE_STATUSES for c in self.cases
        )

    def log(self, msg: str) -> None:
        self.history.append(f"{now_iso()}  {msg}")

    def touch(self) -> None:
        self.updated = now_iso()

    # ---- serialization -----------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "state": self.state.value,
            "app": self.app,
            "cluster": self.cluster,
            "account": self.account,
            "repo_sha": self.repo_sha,
            "build_jobid": self.build_jobid,
            "binary_path": self.binary_path,
            "remote_workdir": self.remote_workdir,
            "created": self.created,
            "updated": self.updated,
            "smoke": self.smoke.to_dict(),
            "budget": self.budget.to_dict(),
            "cases": [c.to_dict() for c in self.cases],
            "attention": self.attention,
            "report_path": self.report_path,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Card":
        d = dict(d)
        state = StudyState(d.get("state", StudyState.DRAFT.value))
        smoke = Smoke.from_dict(d.get("smoke") or {})
        budget = Budget.from_dict(d.get("budget") or {})
        cases = [Case.from_dict(c) for c in (d.get("cases") or [])]
        return cls(
            id=d["id"],
            title=d.get("title", ""),
            kind=d.get("kind", StudyKind.SWEEP.value),
            state=state,
            app=d.get("app", "combined"),
            cluster=d.get("cluster", "bitterroot"),
            account=d.get("account", "intern"),
            repo_sha=d.get("repo_sha"),
            build_jobid=d.get("build_jobid"),
            binary_path=d.get("binary_path"),
            remote_workdir=d.get("remote_workdir"),
            created=d.get("created", now_iso()),
            updated=d.get("updated", now_iso()),
            smoke=smoke,
            budget=budget,
            cases=cases,
            attention=d.get("attention") or [],
            report_path=d.get("report_path"),
            history=d.get("history") or [],
        )
