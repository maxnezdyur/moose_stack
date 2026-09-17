"""Pure derivation: lane, flags, posture, next action.

Nothing here reads the filesystem, the network or the clock. The inputs are one
card's observation, its stored snapshot, the configuration, the gate records and
``now`` as an ISO string. The same inputs always give the same card, which is
what makes the board reproducible.

Every card derives inside its own try and except. A malformed blueprint or an
unreadable worktree yields a card flagged ``error``, never an omitted card and
never a fatal run.
"""

from __future__ import annotations

import calendar
import os.path
import time
from typing import Any, Dict, List, Optional, Tuple

from . import config
from .model import (
    ABANDONED,
    CLOSED_UNMERGED,
    DEMOTION_CAUSES,
    APPROVED,
    ARCHIVED,
    BLUEPRINT_DRAFT,
    BUILDING,
    BUILT,
    DONE,
    GATES,
    GRANTED,
    IDEA,
    MERGED,
    NEEDS_YOU,
    NEEDS_YOU_PRIORITY,
    NON_DURABLE_LANES,
    PARKED,
    PR_READY,
    READY,
    RUNNING,
    SCAFFOLDED,
    SHIPPED,
    TERMINAL_LANES,
    WAITING,
    FeatureCard,
    NextAction,
    rank,
)

DAY = 86400.0


# --------------------------------------------------------------------------
# Time helpers: string in, number out. No clock is read.
# --------------------------------------------------------------------------


def ts_of(iso: str) -> Optional[float]:
    """Parse the ISO-8601 stamps this package writes and that gh returns.

    Handles ``...Z``, ``...+00:00`` and ``...+0000``, plus a bare date.
    """
    if not iso:
        return None
    text = str(iso).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+0000"
    elif len(text) > 6 and text[-6] in "+-" and text[-3] == ":":
        text = text[:-3] + text[-2:]
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            parsed = time.strptime(text, fmt)
        except ValueError:
            continue
        if "%z" in fmt and parsed.tm_gmtoff is not None:
            return calendar.timegm(parsed) - parsed.tm_gmtoff
        return time.mktime(parsed)
    return None


def _newest(values: List[Optional[float]]) -> Optional[float]:
    got = [v for v in values if isinstance(v, (int, float)) and v]
    return max(got) if got else None


# --------------------------------------------------------------------------
# Flags
# --------------------------------------------------------------------------


def rollup_applies(pr: Dict[str, Any], obs: Dict[str, Any]) -> bool:
    """Is this CI rollup and mergeability verdict about the current head?

    ``gh`` answers with the ``headRefOid`` the rollup was computed for. After a
    rebase and push, the previous head's red contexts and CONFLICTING verdict
    are still the cached answer, and colouring a card from them keeps it at the
    top of needs-you with a why that lists contexts which no longer exist.

    True whenever the question cannot be answered: no oid, no local head sha, or
    a local branch that does not head this PR. Unknown never demotes a fact.
    """
    oid = str(pr.get("headRefOid") or "")
    if not oid:
        return True
    repo = pr.get("repo")
    st = (obs.get("repos") or {}).get(repo) or {}
    head = str(st.get("head") or "")
    if not head:
        return True
    if st.get("branch") and pr.get("headRefName") and st["branch"] != pr["headRefName"]:
        return True
    return head == oid


def flags_of(obs: Dict[str, Any], cfg: config.Config, now_ts: float, lane: str) -> List[str]:
    """Wiped and rebuilt every run. A flag can never move a lane."""
    out: List[str] = []

    def add(name: str) -> None:
        if name not in out:
            out.append(name)

    prs = obs.get("prs") or []
    openp = [p for p in prs if (p.get("state") or "").upper() == "OPEN"]
    for pr in openp:
        fresh_rollup = rollup_applies(pr, obs)
        ci = pr.get("ci")
        if fresh_rollup:
            if ci == "red":
                add("ci-red")
            elif ci == "pending":
                add("ci-pending")
            # UNKNOWN is unknown: not clean and not conflicting.
            if pr.get("mergeable") == "CONFLICTING":
                add("conflicting")
        if pr.get("reviewDecision") == "CHANGES_REQUESTED":
            add("changes-requested")

    # A PR closed without merging is a decision, not an absence. Without a flag
    # the clamp releases to scaffolded and the board says "plan it", about work
    # that was just abandoned.
    closed = [
        p
        for p in prs
        if (p.get("state") or "").upper() == "CLOSED" and not p.get("mergedAt")
    ]
    if closed and not openp and not [p for p in prs if (p.get("state") or "").upper() == "MERGED"]:
        add("pr-closed-unmerged")

    build = obs.get("build") or {}
    if isinstance(build.get("required"), int) and build["required"] > 0:
        add("review-findings")
    bp = obs.get("blueprint") or {}
    if build and bp.get("mtime") and build.get("mtime") and build["mtime"] < bp["mtime"]:
        add("build-stale")

    if bp:
        if bp.get("kind") == "view-only":
            add("view-stale")
        elif (bp.get("status") or "") in ("approved", "building", "built") and (
            bp.get("unticked") or not bp.get("work_plan_ok")
        ):
            add("invalid-blueprint")

    sessions = obs.get("sessions") or []
    if len(sessions) > 1:
        add("two-sessions")
    for row in sessions:
        state = str(row.get("state") or row.get("status") or "").lower()
        if row.get("needs") or state in ("waiting", "blocked", "paused"):
            add("blocked")
        if state in ("working", "busy", "running"):
            add("burning")

    if lane == BUILDING and not sessions:
        newest = _newest(
            [obs.get("pulse"), bp.get("mtime"), build.get("mtime")]
        )
        if newest is None or (now_ts - newest) > cfg.stall_seconds:
            add("stalled")

    if (obs.get("skills") or {}).get("has_ship") is False:
        add("stale-pipeline")

    if obs.get("worktree") and obs.get("foreign"):
        add("foreign-worktree")

    repos = obs.get("repos") or {}
    if obs.get("worktree"):
        for repo, st in repos.items():
            branch = st.get("branch")
            if branch is not None and branch != obs["id"]:
                add("branch-mismatch")

    # partial-ship: one repository is shipped while another carries work that
    # no pull request covers.
    if openp:
        shipped_repos = {p.get("repo") for p in openp}
        for repo, st in repos.items():
            if repo == config.META or repo in shipped_repos:
                continue
            if (st.get("ahead") or 0) > 0 or (st.get("dirty") or 0) > 0:
                add("partial-ship")
                break

    lease = obs.get("lease") or {}
    if lease.get("held") and lease.get("owner_alive") is False:
        add("lease-stale")

    if (obs.get("note") or {}).get("markers_ok") is False:
        add("marker-missing")
    if obs.get("probe_stale"):
        add("probe-stale")
    return out


# --------------------------------------------------------------------------
# Lane
# --------------------------------------------------------------------------


#: The one lane move on this board that a non-durable signal can prove. The
#: debounce is a property of the *signal*, not of the destination lane: a
#: session row is ephemeral and must hold across two runs, while
#: ``specs/blueprint.md`` saying ``status: building`` is a file and applies at
#: once. Keying the debounce on the lane delayed the durable half by a run, and
#: that one run is the run Max reads, because a blueprint write is what woke the
#: tick.
SESSION_PROOF = "a live session has its cwd in the worktree"
NON_DURABLE_PROOFS = frozenset({SESSION_PROOF})


def derived_lane(obs: Dict[str, Any], now_ts: float) -> Tuple[str, str]:
    """The highest lane the probes prove, with the signal that proved it."""
    lane, proof = IDEA, "an Ideas.md line that matches nothing"

    prs = obs.get("prs") or []
    openp = [p for p in prs if (p.get("state") or "").upper() == "OPEN"]
    merged = [p for p in prs if (p.get("state") or "").upper() == "MERGED"]

    if obs.get("worktree"):
        lane, proof = SCAFFOLDED, "the path is in git worktree list"

    bp = obs.get("blueprint") or {}
    if bp.get("kind") == "markdown":
        status = (bp.get("status") or "").strip()
        if status in ("draft", "approved", "building", "built"):
            lane, proof = BLUEPRINT_DRAFT, "specs/blueprint.md exists"
        if status in ("approved", "building", "built") and not bp.get("unticked") and bp.get("work_plan_ok"):
            lane, proof = APPROVED, "blueprint approved and the work plan parses"
        if status in ("building",):
            lane, proof = BUILDING, "blueprint status is building"

    if obs.get("sessions"):
        lane, proof = BUILDING, SESSION_PROOF

    build = obs.get("build") or {}
    # `/moose-build` writes its record, then edits the blueprint (unit statuses,
    # `status: built`, an amendment line), so on a first run the record is always
    # older than the blueprint. The blueprint's own `built` is set only on that
    # path and `factory reset` takes it back to `approved`, so it is the second
    # proof. A record written by a session that reports `BUILT` instead of the
    # loop's `GOAL_MET` says the same thing.
    build_status = (build.get("status") or "").upper().split()[0] if build.get("status") else ""
    if build_status in ("GOAL_MET", "BUILT"):
        record_newer = not bp.get("mtime") or (build.get("mtime") or 0) >= bp["mtime"]
        if record_newer or (bp.get("status") or "").strip() == "built":
            lane, proof = BUILT, "a build record says %s" % (build_status,)

    for pr in openp:
        if pr.get("isDraft"):
            lane, proof = SHIPPED, "an open draft PR #%s" % (pr.get("number"),)
            break
    for pr in openp:
        if pr.get("isDraft") is False:
            lane, proof = PR_READY, "PR #%s is open and not a draft" % (pr.get("number"),)
            break

    if merged and not openp:
        lane, proof = MERGED, "PR #%s merged" % (merged[0].get("number"),)
    if not obs.get("worktree") and not openp and merged:
        lane, proof = MERGED, "PR #%s merged, no worktree" % (merged[0].get("number"),)
    if not obs.get("worktree") and not prs and obs.get("provenance") != "idea":
        lane, proof = ARCHIVED, "no worktree and no open PR"

    # Off-pipeline terminal, set by Max with a reason through `factory abandon`.
    # It outranks every probe (rank 99), so the clamp holds it with no demotion.
    ab = obs.get("abandoned") or {}
    if ab:
        lane = ABANDONED
        proof = "factory abandon: %s" % (ab.get("why") or "no reason recorded",)
    return (lane, proof)


def clamp(
    obs: Dict[str, Any],
    prev: Dict[str, Any],
    now: str,
) -> Tuple[str, str, List[str], List[Dict[str, Any]]]:
    """lane = max(rank(derived), rank(last_seen)), with two qualifications.

    The clamp releases only for a named cause. Otherwise the stored lane holds
    and the card gets ``signal-regression``.

    The debounce: a lane move driven by a non-durable signal (a session row, a
    CI rollup) must hold across two consecutive runs. A move driven by a durable
    artifact applies at once.
    """
    extra: List[str] = []
    events: List[Dict[str, Any]] = []
    now_ts = ts_of(now) or time.time()
    fresh, proof = derived_lane(obs, now_ts)
    stored = prev.get("lane")

    # --- the debounce -----------------------------------------------------
    if fresh in NON_DURABLE_LANES and proof in NON_DURABLE_PROOFS and fresh != stored:
        count = 1
        if prev.get("pending_lane") == fresh:
            count = int(prev.get("pending_count") or 1) + 1
        prev["pending_lane"] = fresh
        prev["pending_count"] = count
        if count < 2:
            held = stored or SCAFFOLDED
            return (held, "%s held one run: %s needs two" % (held, fresh), extra, events)
    else:
        prev["pending_lane"] = None
        prev["pending_count"] = 0

    if stored is None:
        return (fresh, proof, extra, events)

    if rank(fresh) >= rank(stored):
        return (fresh, proof, extra, events)

    # --- a demotion needs a named cause -----------------------------------
    cause = demotion_cause(obs)
    if cause:
        events.append(
            {
                "at": now,
                "event": "lane-demoted",
                "from": stored,
                "to": fresh,
                "cause": cause,
                "probe": proof,
            }
        )
        return (fresh, "demoted: %s" % (cause,), extra, events)
    extra.append("signal-regression")
    return (stored, "%s held: the probes only prove %s" % (stored, fresh), extra, events)


def demotion_cause(obs: Dict[str, Any]) -> Optional[str]:
    """The whitelist. Anything else holds the stored lane."""
    cause = _demotion_cause(obs)
    return cause if cause in DEMOTION_CAUSES else None


def _demotion_cause(obs: Dict[str, Any]) -> Optional[str]:
    build = obs.get("build") or {}
    if (build.get("status") or "").upper() == "NEEDS_DESIGN":
        return "needs-design"
    prs = obs.get("prs") or []
    if prs and not [p for p in prs if (p.get("state") or "").upper() == "OPEN"]:
        if [p for p in prs if (p.get("state") or "").upper() == "CLOSED"]:
            return "pr-closed-unmerged"
    bp = obs.get("blueprint") or {}
    if bp.get("kind") == "markdown" and (bp.get("unticked") or not bp.get("work_plan_ok")):
        if (bp.get("status") or "") in ("approved", "building", "built"):
            return "invalid-blueprint"
    if obs.get("abandoned"):
        return "abandoned"
    if obs.get("reset"):
        return "reset"
    return None


# --------------------------------------------------------------------------
# Gates that are actionable now
# --------------------------------------------------------------------------


def gate_due(card: FeatureCard) -> Optional[str]:
    """The one pending gate Max can grant today, or None.

    A gate that waits on work nobody has done is not "needs you": a scaffolded
    worktree with no blueprint has nothing to approve.
    """
    g = card.gates
    lane = card.lane

    def pending(name: str) -> bool:
        return (g.get(name) or {}).get("state") != GRANTED

    # Highest lane window first. A gate for finished work must never mask the
    # gate for the work in flight: a shipped card was offered
    # `grant blueprint_approved` while its green draft sat unmarked.
    if pending("teardown") and lane in (MERGED, ARCHIVED):
        return "teardown"
    if pending("pr_ready") and rank(lane) >= rank(SHIPPED) and lane not in (MERGED, ARCHIVED):
        if not (card.has("ci-red") or card.has("conflicting") or card.has("ci-pending")):
            return "pr_ready"
    if pending("ship") and rank(lane) >= rank(BUILT) and rank(lane) < rank(MERGED):
        return "ship"
    if (
        pending("blueprint_approved")
        and rank(lane) >= rank(BLUEPRINT_DRAFT)
        and rank(lane) < rank(BUILT)
        # A generated specs/blueprint.html is a view, not a plan. There is
        # nothing in it to approve, and offering the gate hides the real move.
        and (card.blueprint or {}).get("kind") == "markdown"
        and not card.has("invalid-blueprint")
    ):
        return "blueprint_approved"
    return None


# --------------------------------------------------------------------------
# Posture
# --------------------------------------------------------------------------

def uncommitted(card: FeatureCard) -> int:
    """Modified files across the four repos of one workspace."""
    return sum(int(st.get("dirty") or 0) for st in (card.repos or {}).values())


def needs_triage(card: FeatureCard, cfg: config.Config) -> bool:
    """A scaffolded workspace carrying real uncommitted work.

    The plan's parked group is "scaffolded with no blueprint and no session".
    A tree with dozens of modified files is not that: the work exists, nothing
    on the board explains it, and the only move is to decide. The shape that
    forced the rule is a workspace carrying tens of modified files whose only
    plan artifact is a generated ``blueprint.html`` with no ``.md`` beside it:
    it belongs on the needs-you backlog line, not in parked. The
    """
    if rank(card.lane) > rank(SCAFFOLDED) or card.open_prs():
        return False
    return uncommitted(card) >= cfg.triage_dirty


NEEDS_YOU_FLAGS = (
    "review-findings",
    "changes-requested",
    "pr-closed-unmerged",
    "blocked",
    "branch-mismatch",
    "foreign-worktree",
    "partial-ship",
    "invalid-blueprint",
    "marker-missing",
)

# A built card's review is done, so the only real reasons it is not Ready are a
# defect or a PR/branch problem -- never a session that parked itself `blocked`
# waiting for the ship grant, which is exactly the Ready action.
BUILT_NOT_READY_FLAGS = (
    "review-findings",
    "changes-requested",
    "pr-closed-unmerged",
    "branch-mismatch",
    "foreign-worktree",
    "partial-ship",
    "invalid-blueprint",
    "marker-missing",
)


def posture_of(
    card: FeatureCard,
    cfg: config.Config,
    now_ts: float,
    silent: Optional[int] = None,
) -> str:
    """Derived, stored nowhere, the grouping axis of Home.md.

    Order is the whole content of this function. Three precedences are load
    bearing: an actively working session (``burning``) outranks a pending gate,
    so a live build shows in Running instead of "act today", but a build session
    that has gone idle after finishing does not hold a ``built`` card out of
    Ready; ``built`` with its review applied and ``ship`` pending is Ready, the
    plan's first Ready rule; and a ``scaffolded`` workspace is Parked only once
    it has
    been quiet for ``park_idle_days``, so a workspace created minutes ago reads
    as work in flight rather than settled backlog.
    """
    openp = card.open_prs()
    # A terminal Max set by hand is out of sight, flags and all. `merged` is not
    # one of these: a merged card with `teardown` pending still needs him.
    if card.lane in (ABANDONED, CLOSED_UNMERGED):
        return DONE

    # A built card whose review is applied and whose ship gate is still yours is
    # Ready, and this is decided before the generic needs-you and running checks
    # for one reason: the session that finishes a build does not exit. It parks
    # in the worktree, and it reports its own state inconsistently -- `done` on
    # one run, `blocked` with needs "grant ship" on another. Both mean the same
    # thing, waiting for the ship grant, which is the Ready action, so neither
    # `blocked` nor a lingering idle session should hold the card out of Ready.
    # What still wins is a real defect (`review-findings` for an unapplied
    # review, or a PR/branch problem) and an actively working session
    # (`burning`); those fall through to the checks below.
    if (
        card.lane == BUILT
        and card.gate_state("ship") != GRANTED
        and not card.has("burning")
        and not any(card.has(f) for f in BUILT_NOT_READY_FLAGS)
    ):
        return READY

    for flag in NEEDS_YOU_FLAGS:
        if card.has(flag):
            return NEEDS_YOU
    if openp and (card.has("ci-red") or card.has("conflicting")):
        return NEEDS_YOU

    if card.session:
        return RUNNING
    if card.lane == BUILDING and not card.has("stalled"):
        return RUNNING

    if needs_triage(card, cfg):
        return NEEDS_YOU

    if card.lane == APPROVED and card.gate_state("blueprint_approved") == GRANTED and not card.session:
        return READY

    if card.gates.get("_due"):
        return NEEDS_YOU

    if openp and not card.has("changes-requested"):
        return WAITING

    if card.lane in TERMINAL_LANES:
        return DONE
    if card.has("stalled"):
        return PARKED
    if (
        card.lane == SCAFFOLDED
        and not card.blueprint
        and not card.session
        and silent is not None
        and silent < cfg.park_idle_days
    ):
        # Quiet for less than a week is not backlog. The plan's rule is
        # "scaffolded with no blueprint and no session for over 7 days".
        return NEEDS_YOU
    return PARKED


# --------------------------------------------------------------------------
# The next move
# --------------------------------------------------------------------------


def _pr_label(pr: Dict[str, Any]) -> str:
    return "%s #%s" % (pr.get("repo") or "?", pr.get("number"))


def _repo_of_pr(card: FeatureCard) -> str:
    pr = card.primary_pr()
    return (pr or {}).get("repo") or "moose"


def next_action(card: FeatureCard, cfg: config.Config) -> NextAction:
    """One verb, one copyable command, one reason. Highest priority wins.

    The command names a worktree; this program never touches one.
    """
    wt = card.worktree or ""
    pr = card.primary_pr()
    openp = card.open_prs()
    repo = _repo_of_pr(card)
    repo_dir = ("%s/%s" % (wt, repo)) if (wt and repo != config.META) else wt
    slug = cfg.gh_repos.get(repo, "idaholab/moose")

    if card.has("error"):
        return NextAction(
            "read-error",
            "%s dump-obs %s" % (_factory(cfg), card.id),
            "deriving this card raised: %s" % ("; ".join(card.errors[:2]) or "unknown",),
        )
    if card.has("marker-missing"):
        return NextAction(
            "fix-note",
            "grep -n 'factory:' %s" % (cfg.note_path(card.id),),
            "the note lost a marker, so it was not rewritten. Restore the four markers.",
        )
    if card.has("foreign-worktree"):
        return NextAction(
            "teardown",
            "%s teardown %s" % (_factory(cfg), card.id),
            "legacy checkout at %s, outside %s"
            % (config.display_path(wt), config.display_path(cfg.worktree_root)),
        )
    if card.has("branch-mismatch"):
        bad = [
            "%s on %s" % (r, st.get("branch"))
            for r, st in sorted(card.repos.items())
            if st.get("branch") and st["branch"] != card.id
        ]
        return NextAction(
            "fix-branch",
            "git -C %s branch --show-current" % (wt,),
            "a repository HEAD is not the feature name (%s). Fix the branch or tear down."
            % ("; ".join(bad),),
        )
    if card.has("pr-closed-unmerged"):
        closed = [
            p
            for p in card.prs
            if (p.get("state") or "").upper() == "CLOSED" and not p.get("mergedAt")
        ]
        newest = sorted(closed, key=lambda p: (p.get("updatedAt") or ""), reverse=True)
        label = _pr_label(newest[0]) if newest else "the PR"
        return NextAction(
            "decide",
            ("gh pr view %s --repo %s" % (newest[0].get("number"), cfg.gh_repos.get(
                newest[0].get("repo") or "moose", "idaholab/moose")))
            if newest
            else "",
            "%s was closed without merging. Reopen it, or tear the worktree down."
            % (label,),
        )
    if card.has("conflicting") and pr:
        return NextAction(
            "rebase",
            _rebase_cmd(card, cfg, repo_dir, pr, slug),
            "%s is CONFLICTING, so nothing can land%s"
            % (_pr_label(pr), "" if wt else ". There is no checkout to rebase in."),
        )
    if card.has("ci-red") and pr:
        failing = [f.get("name", "?") for f in (pr.get("failing") or [])]
        shown = ", ".join(failing[:4]) + (
            ", and %d more" % (len(failing) - 4,) if len(failing) > 4 else ""
        )
        also = ""
        if card.has("partial-ship"):
            # A co-present partial-ship is the second half of the move, not a
            # lower-priority card. Dropping it loses the only line that names it.
            unshipped = [
                r
                for r, st in sorted(card.repos.items())
                if r != config.META
                and r not in {p.get("repo") for p in openp}
                and ((st.get("ahead") or 0) > 0 or (st.get("dirty") or 0) > 0)
            ]
            also = ", and %s carries work no PR covers" % (
                ", ".join(unshipped) or "another repo",
            )
        return NextAction(
            "fix-ci",
            "gh pr checks %s --repo %s" % (pr.get("number"), slug),
            "%s is red%s%s" % (_pr_label(pr), (" (%s)" % shown) if shown else "", also),
        )
    if card.has("changes-requested") and pr:
        return NextAction(
            "read-review",
            "gh pr view %s --repo %s --comments" % (pr.get("number"), slug),
            "%s has CHANGES_REQUESTED" % (_pr_label(pr),),
        )
    if card.has("review-findings"):
        return NextAction(
            "rebuild",
            "%s start %s" % (_factory(cfg), card.id),
            "the clean-context review recorded %s required findings"
            % ((card.build or {}).get("required"),),
        )
    if card.has("blocked") and card.session:
        bg = card.session.get("bg_id") or (card.session.get("sessionId") or "").split("-")[0]
        return NextAction(
            "attach",
            "%s attach %s" % (config.claude_display(cfg), bg),
            "the session is waiting: %s"
            % (card.session.get("needs") or card.session.get("detail") or "unknown",),
        )
    if card.has("partial-ship"):
        unshipped = [
            r
            for r, st in sorted(card.repos.items())
            if r != config.META
            and r not in {p.get("repo") for p in openp}
            and ((st.get("ahead") or 0) > 0 or (st.get("dirty") or 0) > 0)
        ]
        return NextAction(
            "decide",
            "git -C %s/%s status -sb" % (wt, unshipped[0] if unshipped else "moose"),
            "%s is shipped, but %s carries work no PR covers. Push it, or drop it."
            % (_pr_label(pr) if pr else "one repo", ", ".join(unshipped) or "another repo"),
        )
    if card.has("stalled"):
        return NextAction(
            "reset",
            "%s reset %s" % (_factory(cfg), card.id),
            "lane is building, the pulse is cold and no session is alive",
        )
    if card.has("invalid-blueprint"):
        bp = card.blueprint or {}
        why = (
            "%s clarification boxes are unticked" % (bp.get("unticked"),)
            if bp.get("unticked")
            else (bp.get("work_plan_error") or "the work plan does not parse")
        )
        return NextAction(
            "fix-blueprint",
            "code %s" % (bp.get("path") or wt,),
            "the blueprint says %s, but %s" % (bp.get("status"), why),
        )

    due = card.gates.get("_due")
    if due == "pr_ready" and pr:
        return NextAction(
            "mark-ready",
            "open %s" % (pr.get("url") or ""),
            "%s is a green draft. Only you can mark it ready." % (_pr_label(pr),),
        )
    if due == "teardown":
        return NextAction(
            "teardown",
            "%s teardown %s" % (_factory(cfg), card.id),
            "%s merged. Reclaim the worktree%s."
            % (
                _pr_label(pr) if pr else "the PR",
                _kb(card),
            ),
        )
    if due == "ship":
        return NextAction(
            "grant",
            "%s grant %s ship" % (_factory(cfg), card.id),
            "the build met its goal. Grant ship, then run /moose-ship.",
        )
    if due == "blueprint_approved":
        return NextAction(
            "grant",
            "%s grant %s blueprint_approved" % (_factory(cfg), card.id),
            "a blueprint is waiting for your approval",
        )

    subs = {r: st for r, st in card.repos.items() if r != config.META}
    never_fetched = bool(subs) and all(not st.get("fetched") for st in subs.values())
    if never_fetched and rank(card.lane) <= rank(SCAFFOLDED):
        return NextAction(
            "fetch",
            "cd %s/moose && git fetch upstream" % (wt,),
            "no FETCH_HEAD in any repo, so every ahead count is unknown. Fetch, then triage.",
        )

    if needs_triage(card, cfg):
        bp = card.blueprint or {}
        return NextAction(
            "triage",
            "git -C %s status -sb" % (wt,),
            "%d modified files in a workspace with no plan%s. Decide: plan it, "
            "commit it, or tear it down."
            % (
                uncommitted(card),
                " (only a generated %s survives)" % (os.path.basename(bp["path"]),)
                if bp.get("kind") == "view-only" and bp.get("path")
                else "",
            ),
        )

    if card.lane == IDEA:
        return NextAction(
            "scaffold",
            "cd %s && claude \"/new-feature %s\"" % (config.display_path(cfg.repo_root), card.id),
            "an idea in Ideas.md that matches no worktree, branch or PR",
        )
    if card.lane == SCAFFOLDED:
        return NextAction(
            "blueprint",
            "cd %s && claude \"/moose-blueprint\"" % (wt,),
            "a worktree with no blueprint. Plan it, or tear it down.",
        )
    if card.lane == BLUEPRINT_DRAFT:
        return NextAction(
            "approve",
            "code %s" % ((card.blueprint or {}).get("path") or wt,),
            "a draft blueprint. Read it, tick the clarifications, set status: approved.",
        )
    if card.lane == APPROVED:
        return NextAction(
            "build",
            "%s start %s" % (_factory(cfg), card.id),
            "approved and nothing is dispatched",
        )
    if card.lane == BUILDING:
        bg = (card.session or {}).get("bg_id") or ""
        return NextAction(
            "wait",
            ("%s attach %s" % (config.claude_display(cfg), bg)) if bg else "",
            "a build is running. Leave it alone.",
        )
    if card.lane == BUILT:
        return NextAction(
            "ship",
            "cd %s && claude \"/moose-ship\"" % (wt,),
            "built, ship granted. Open the pull request.",
        )
    if card.lane == SHIPPED and pr:
        return NextAction(
            "wait",
            "gh pr checks %s --repo %s" % (pr.get("number"), slug),
            "%s is a draft and CI is %s" % (_pr_label(pr), pr.get("ci") or "unknown"),
        )
    if card.lane == PR_READY and pr:
        return NextAction(
            "wait",
            "gh pr view %s --repo %s" % (pr.get("number"), slug),
            "%s is ready and the reviewers have it" % (_pr_label(pr),),
        )
    if card.lane == MERGED:
        return NextAction(
            "teardown",
            "%s teardown %s" % (_factory(cfg), card.id),
            "%s merged%s" % (_pr_label(pr) if pr else "the PR", _kb(card)),
        )
    return NextAction("none", "", "archived. Nothing to do.")


def _rebase_cmd(
    card: FeatureCard, cfg: config.Config, repo_dir: str, pr: Dict[str, Any], slug: str
) -> str:
    """Rebase in the checkout when there is one; otherwise read the checks.

    A PR-only card has no worktree, and `cd` with an empty path is worse than
    no command at all.
    """
    if card.worktree and repo_dir:
        return "cd %s && git fetch upstream && git rebase %s" % (repo_dir, cfg.upstream_ref)
    return "gh pr checks %s --repo %s" % (pr.get("number"), slug)


def _kb(card: FeatureCard) -> str:
    """Reclaimable bytes, the only number that actually motivates teardown."""
    kb = card.gates.get("_reclaimable_kb")
    if isinstance(kb, int) and kb > 0:
        return " (%0.1f GB reclaimable)" % (kb / 1024.0 / 1024.0,)
    return ""


def _factory(cfg: config.Config) -> str:
    """The launcher, as a command to paste. Tilde-collapsed, like every other
    path a generated note carries: spelling $HOME out would put the machine's
    user name into every note and into every diff of one."""
    return config.display_path(cfg.repo_root / "factory" / "factory")


# --------------------------------------------------------------------------
# One card, and all of them
# --------------------------------------------------------------------------


def derive_card(
    obs: Dict[str, Any],
    prev: Dict[str, Any],
    cfg: config.Config,
    now: str,
    gate_records: Dict[str, Any],
) -> Tuple[FeatureCard, List[Dict[str, Any]]]:
    """One card. Returns the card and the timeline events the derivation earned."""
    now_ts = ts_of(now) or time.time()
    feature = obs["id"]
    card = FeatureCard(id=feature)
    events: List[Dict[str, Any]] = []
    try:
        card.worktree = obs.get("worktree")
        card.provenance = obs.get("provenance") or "discovered-worktree"
        card.repos = dict(obs.get("repos") or {})
        card.prs = list(obs.get("prs") or [])
        card.blueprint = obs.get("blueprint")
        card.build = obs.get("build")
        card.session = obs.get("session")
        card.gates = dict(gate_records)

        lane, proof, extra, lane_events = clamp(obs, prev, now)
        card.lane = lane
        card.lane_rank = rank(lane)
        events.extend(lane_events)

        card.flags = flags_of(obs, cfg, now_ts, lane) + extra
        # `factory board --du` measures it; every later run reads the cache, so
        # the next-action why and the note's Teardown section agree.
        kb = obs.get("reclaimable_kb")
        if not isinstance(kb, int):
            kb = (prev.get("obs") or {}).get("reclaimable_kb")
        if isinstance(kb, int) and kb > 0:
            card.gates["_reclaimable_kb"] = kb
        card.gates["_due"] = gate_due(card)
        card.gates["_proof"] = proof
        card.posture = posture_of(card, cfg, now_ts, silent_days(obs, now_ts))
        card.next_action = next_action(card, cfg)
    except Exception as exc:  # isolation: one bad card never sinks the board
        card.errors.append("%s: %s" % (type(exc).__name__, exc))
        card.add_flag("error")
        card.posture = NEEDS_YOU
        card.next_action = next_action(card, cfg)
    return (card, events)


def backlog_reason(card: FeatureCard, cfg: config.Config) -> str:
    """Why this card is in needs-you, for the one-line backlog on Home.md.

    Flags are not interchangeable here. ``stale-pipeline`` is true of every
    worktree and moves nobody to act, so a parenthetical that prints it instead
    of ``foreign-worktree`` says nothing.
    """
    reasons: List[str] = []
    for flag in NEEDS_YOU_PRIORITY:
        if flag in ("gate-pending",):
            continue
        if card.has(flag):
            reasons.append(flag)
    if needs_triage(card, cfg):
        reasons.append("%d modified, no plan" % (uncommitted(card),))
    due = card.gates.get("_due")
    if due:
        reasons.append("%s pending" % (due,))
    if not reasons:
        reasons = [f for f in card.flags[:2]] or [card.lane]
    return ", ".join(reasons)


def silent_days(obs: Dict[str, Any], now_ts: float) -> Optional[int]:
    """Days since anything happened to this card. None when nothing is datable."""
    stamps: List[Optional[float]] = [obs.get("pulse")]
    for key in ("blueprint", "build"):
        rec = obs.get(key) or {}
        stamps.append(rec.get("mtime"))
    for st in (obs.get("repos") or {}).values():
        stamps.append(st.get("fetched_at"))
    for pr in obs.get("prs") or []:
        stamps.append(ts_of(pr.get("updatedAt") or ""))
    newest = _newest(stamps)
    if newest is None:
        return None
    return int(max(0.0, now_ts - newest) // DAY)


def derive_all(ctx: Any) -> List[FeatureCard]:
    """Derive every card, in id order, each inside its own try and except."""
    cards: List[FeatureCard] = []
    now_ts = ts_of(ctx.now) or time.time()
    for feature in sorted(ctx.obs):
        obs = ctx.obs[feature]
        prev = ctx.state.read(feature) if ctx.state else {}
        records = (
            ctx.gates.get(feature)
            if ctx.gates
            else {g: {"state": "pending"} for g in GATES}
        )
        card, events = derive_card(obs, prev, ctx.config, ctx.now, records)
        for ev in events:
            if ctx.timeline:
                ctx.timeline.append(feature, ev)
        if ctx.state:
            prev["lane"] = card.lane
            prev["posture"] = card.posture
            prev["silent_days"] = silent_days(obs, now_ts)
            ctx.state.write(feature, prev, ctx.dry_run)
        cards.append(card)
    return cards
