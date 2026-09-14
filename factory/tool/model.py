"""The domain model: four axes that are never conflated.

    lane     monotonic pipeline position, ranked 0 to 9, clamped
    flags    wiped and rebuilt every run, never able to move a lane
    posture  derived, stored nowhere, the grouping axis of Home.md
    gates    four monotonic attributed human grants

A ``FeatureCard`` is derived, never stored. ``Ctx`` is the one object every
verb and every extension receives.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# Lane: monotonic pipeline position
# --------------------------------------------------------------------------

IDEA = "idea"
SCAFFOLDED = "scaffolded"
BLUEPRINT_DRAFT = "blueprint-draft"
APPROVED = "approved"
BUILDING = "building"
BUILT = "built"
SHIPPED = "shipped"
PR_READY = "pr-ready"
MERGED = "merged"
ARCHIVED = "archived"

# Off-pipeline terminals. Set by Max with a reason, never derived.
ABANDONED = "abandoned"
CLOSED_UNMERGED = "closed-unmerged"

LANES: Tuple[str, ...] = (
    IDEA,
    SCAFFOLDED,
    BLUEPRINT_DRAFT,
    APPROVED,
    BUILDING,
    BUILT,
    SHIPPED,
    PR_READY,
    MERGED,
    ARCHIVED,
)

LANE_RANK: Dict[str, int] = {lane: i for i, lane in enumerate(LANES)}
# A terminal set by hand outranks nothing and is never overtaken by a probe.
LANE_RANK[ABANDONED] = 99
LANE_RANK[CLOSED_UNMERGED] = 98

TERMINAL_LANES = frozenset({MERGED, ARCHIVED, ABANDONED, CLOSED_UNMERGED})

# Lane owners, printed by `factory next` so the reader knows who must act.
LANE_OWNER: Dict[str, str] = {
    IDEA: "max",
    SCAFFOLDED: "max",
    BLUEPRINT_DRAFT: "max",
    APPROVED: "max (gate)",
    BUILDING: "agent",
    BUILT: "agent",
    SHIPPED: "max (gate)",
    PR_READY: "reviewers",
    MERGED: "max (gate)",
    ARCHIVED: "none",
    ABANDONED: "none",
    CLOSED_UNMERGED: "max",
}


def rank(lane: Optional[str]) -> int:
    return LANE_RANK.get(lane or IDEA, 0)


# A lane moves backwards only for a named cause.
DEMOTION_CAUSES = frozenset(
    {
        "needs-design",        # NEEDS_DESIGN in the build record
        "pr-closed-unmerged",  # the PR went away without merging
        "invalid-blueprint",   # rank 2 again until the blueprint parses
        "abandoned",           # Max said so
        "reset",               # `factory reset`
    }
)

# Signals that must hold across two consecutive runs before they move a lane.
# A durable artifact (a file, a PR number, a commit sha) applies at once.
NON_DURABLE_LANES = frozenset({BUILDING})


# --------------------------------------------------------------------------
# Flags: the closed vocabulary
# --------------------------------------------------------------------------

FLAGS: Tuple[str, ...] = (
    "ci-red",
    "ci-pending",
    "conflicting",
    "changes-requested",
    "pr-closed-unmerged",
    "review-findings",
    "blocked",
    "stalled",
    "build-stale",
    "handoff-stale",
    "invalid-blueprint",
    "view-stale",
    "stale-pipeline",
    "branch-mismatch",
    "foreign-worktree",
    "partial-ship",
    "two-sessions",
    "lease-stale",
    "marker-missing",
    "probe-stale",
    "signal-regression",
    "burning",
    "error",
)

FLAG_SET = frozenset(FLAGS)

# One line each, printed by `factory status` and in the note.
FLAG_WHY: Dict[str, str] = {
    "ci-red": "a CIVET context reported FAILURE or ERROR on the current head",
    "ci-pending": "a CIVET context is still PENDING or EXPECTED",
    "conflicting": "GitHub says the PR cannot merge; nothing else can land",
    "changes-requested": "a reviewer asked for changes",
    "pr-closed-unmerged": "the only pull request on this card was closed without merging",
    "review-findings": "the clean-context review recorded required findings",
    "blocked": "a live session is waiting on a prompt or is out of credits",
    "stalled": "lane is building, the pulse is cold and no session is alive",
    "build-stale": "the newest build record is older than the blueprint",
    "handoff-stale": "the blueprint or the newest build record is more than two days newer than specs/handoff.md",
    "invalid-blueprint": "approved, but a clarification box is unticked or the work plan fails to parse",
    "view-stale": "specs/blueprint.html survives with no blueprint.md beside it",
    "stale-pipeline": "the worktree's .claude is frozen and has no moose-ship",
    "branch-mismatch": "a repository HEAD is not the feature name",
    "foreign-worktree": "the checkout is outside the configured worktree root",
    "partial-ship": "one repository is shipped while another carries unshipped work",
    "two-sessions": "more than one live session has its cwd in this worktree",
    "lease-stale": "a .factory-lease survives whose owner process is gone",
    "marker-missing": "the note lost a factory marker, so it was not rewritten",
    "probe-stale": "a probe failed; the last good value was carried forward",
    "signal-regression": "a probe said less than the stored lane, so the lane held",
    "burning": "the card is spending quota right now",
    "error": "deriving this card raised; the card is rendered, not omitted",
}

# Needs-you priority, highest first. Decides the order of the table and which
# cards fall past the cap into the Backlog line.
NEEDS_YOU_PRIORITY: Tuple[str, ...] = (
    "conflicting",
    "ci-red",
    "changes-requested",
    "pr-closed-unmerged",
    "review-findings",
    "blocked",
    "branch-mismatch",
    "foreign-worktree",
    "partial-ship",
    "stalled",
    "gate-pending",
    "invalid-blueprint",
    "marker-missing",
)


# --------------------------------------------------------------------------
# Posture: the grouping axis
# --------------------------------------------------------------------------

NEEDS_YOU = "needs-you"
RUNNING = "running"
READY = "ready"
WAITING = "waiting"
PARKED = "parked"
DONE = "done"

POSTURE: Tuple[str, ...] = (NEEDS_YOU, RUNNING, READY, WAITING, PARKED, DONE)

POSTURE_MEANING: Dict[str, str] = {
    NEEDS_YOU: "act today",
    RUNNING: "leave it alone",
    READY: "one command away",
    WAITING: "the ball is elsewhere",
    PARKED: "triage when you feel like it",
    DONE: "out of sight",
}


# --------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------

GATES: Tuple[str, ...] = ("blueprint_approved", "ship", "pr_ready", "teardown")

GATE_BLURB: Dict[str, str] = {
    "blueprint_approved": "yours: the plan is right",
    "ship": "yours: open the pull request",
    "pr_ready": "yours alone, in the GitHub UI. /moose-ship is forbidden from setting it.",
    "teardown": "yours: reclaim the disk",
}

PENDING = "pending"
GRANTED = "granted"


# --------------------------------------------------------------------------
# Cards
# --------------------------------------------------------------------------


@dataclass
class NextAction:
    """The single next move. One verb, one copyable command, one reason."""

    verb: str = "wait"
    command: str = ""
    why: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class FeatureCard:
    """One row on the board. Derived every run, stored nowhere."""

    id: str
    worktree: Optional[str] = None
    lane: str = IDEA
    lane_rank: int = 0
    flags: List[str] = field(default_factory=list)
    posture: str = PARKED
    next_action: NextAction = field(default_factory=NextAction)
    prs: List[Dict[str, Any]] = field(default_factory=list)
    blueprint: Optional[Dict[str, Any]] = None
    build: Optional[Dict[str, Any]] = None
    session: Optional[Dict[str, Any]] = None
    gates: Dict[str, Any] = field(default_factory=dict)
    provenance: str = "discovered-worktree"
    repos: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    #: Per-card scratch space for the extensions. Core reads nothing from it.
    #: ``tool/ext_handoff.py`` publishes ``handoff_next`` and its four siblings here.
    extra: Dict[str, Any] = field(default_factory=dict)

    # ---- conveniences used by render, derive and the extensions ----------

    def has(self, flag: str) -> bool:
        return flag in self.flags

    def add_flag(self, flag: str) -> None:
        if flag not in self.flags:
            self.flags.append(flag)

    def open_prs(self) -> List[Dict[str, Any]]:
        return [p for p in self.prs if (p.get("state") or "").upper() == "OPEN"]

    def primary_pr(self) -> Optional[Dict[str, Any]]:
        """The newest open PR, else the newest PR of any state."""
        openp = self.open_prs()
        pool = openp or self.prs
        if not pool:
            return None
        return sorted(pool, key=lambda p: (p.get("updatedAt") or ""), reverse=True)[0]

    def merged_prs(self) -> List[Dict[str, Any]]:
        return [p for p in self.prs if (p.get("state") or "").upper() == "MERGED"]

    def gate_state(self, gate: str) -> str:
        rec = self.gates.get(gate) or {}
        return rec.get("state") or PENDING

    def pending_gates(self) -> List[str]:
        return [g for g in GATES if self.gate_state(g) != GRANTED]

    #: CI facts about a pull request whose head branch matches no checkout.
    #: They are true, and they still need Max, but he cannot fix a red CIVET
    #: context in a worktree he does not have. Ranked below every reason he can
    #: act on locally, so a red PR-only card cannot displace a branch mismatch
    #: or a review from the five-row table.
    REMOTE_ONLY_CI: ClassVar[Tuple[str, ...]] = ("conflicting", "ci-red")

    def priority_key(self) -> Tuple[int, str]:
        """Rank inside the needs-you group: lowest number first.

        Slots are doubled so a demoted reason can sit between two others.
        """
        reasons = set(self.flags)
        if self.gates.get("_due"):
            reasons.add("gate-pending")
        floor = 2 * len(NEEDS_YOU_PRIORITY)
        best: Optional[int] = None
        for i, name in enumerate(NEEDS_YOU_PRIORITY):
            if name not in reasons:
                continue
            slot = 2 * i
            if name in self.REMOTE_ONLY_CI and not self.worktree:
                slot = floor - 1
            best = slot if best is None else min(best, slot)
        return (floor if best is None else best, self.id)

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["next_action"] = self.next_action.to_dict()
        return d


@dataclass
class StudyCard:
    """A read-only projection of analysis/studies/<id>/card.yaml.

    Core never builds one: ``tool/ext_studies.py`` owns the adapter and the
    analysis toolkit stays the only writer of the card itself.
    """

    id: str
    lane: str = "draft"
    posture: str = PARKED
    title: str = ""
    updated: str = ""
    progress: str = ""
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


# --------------------------------------------------------------------------
# Ctx: what every verb and every extension receives
# --------------------------------------------------------------------------


@dataclass
class Ctx:
    """The one context object. ``now`` is passed in, never computed in derive."""

    config: Any                              # config.Config
    obs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    cards: List[FeatureCard] = field(default_factory=list)
    state_dir: Any = None
    vault_dir: Any = None
    now: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)   # global probe facts
    stamps: Dict[str, Any] = field(default_factory=dict)  # path -> (digest, stamp)
    timeline: Any = None                     # timeline.TimelineWriter
    gates: Any = None                        # gates.GateStore
    state: Any = None                        # snapshot.Store
    dry_run: bool = False
    _log: Optional[Callable[[str], None]] = None

    def log(self, msg: str) -> None:
        """One diagnostic line. Library code never prints to stdout."""
        if self._log is not None:
            self._log(msg)

    def card(self, feature: str) -> Optional[FeatureCard]:
        for c in self.cards:
            if c.id == feature:
                return c
        return None

    def by_posture(self, posture: str) -> List[FeatureCard]:
        return [c for c in self.cards if c.posture == posture]
