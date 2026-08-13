"""Reconcile-on-re-entry: rebuild the live picture from the card + SLURM.

This is the function the AI runs whenever a session starts. It queries sacct
over SSH, advances every case, applies the tiered failure policy (auto-resubmit
transient, park systematic), enforces the budget ceiling mid-flight, and then
drives a fully-collected study through collection and reporting to DONE.
"""

from __future__ import annotations

import sys
from typing import List, Optional

from . import collect as collect_mod
from . import dispatch as dispatch_mod
from . import report as report_mod
from .config import MAX_TRANSIENT_RETRIES
from .model import (
    ATTENTION_LANES,
    Card,
    CaseStatus,
    StudyState,
    TERMINAL_LANES,
    now_iso,
)
from .remote import ConnectionError_, Remote
from .spec import Spec, load_for_id

# SLURM state -> our classification
_RUNNING = {"RUNNING", "COMPLETING", "CONFIGURING", "RESIZING"}
_PENDING = {"PENDING", "SUSPENDED", "REQUEUE_HOLD", "RESV_DEL_HOLD", "REQUEUED"}
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
    return "systematic"  # default: anything unexpected is treated as a hard fail


def _spent(card: Card) -> float:
    """Total core-hours = banked (prior retried attempts) + current attempt."""
    return round(sum(c.spent_core_hours + c.core_hours for c in card.cases), 3)


def sync_card(card: Card, spec: Optional[Spec], remote: Remote) -> Card:
    """Update case states from sacct; apply retries and budget enforcement."""
    if not card.cases:
        # dispatched/running study with no cases is a stuck state, not silence
        if card.state in (StudyState.RUNNING, StudyState.DISPATCHED, StudyState.COLLECTING):
            card.state = StudyState.ATTENTION
            _attn(card, "study has no cases to run")
        return card

    bases = sorted({c.jobid.split("_")[0] for c in card.cases if c.jobid})
    acct = remote.sacct(bases)

    transient_retry: List[int] = []
    for c in card.cases:
        if c.status in (CaseStatus.DONE, CaseStatus.FAILED_SYSTEMATIC):
            continue
        info = acct.get(c.jobid or "")
        if not info:
            # not yet in slurmdbd (just submitted) -> leave as queued
            continue
        c.slurm_state = str(info["state"])
        alloc = int(info["alloc_cpus"] or 0)
        elapsed = int(info["elapsed_s"] or 0)
        c.core_hours = round(alloc * elapsed / 3600.0, 3)
        klass = _classify(c.slurm_state)
        if klass == "done":
            c.status = CaseStatus.DONE
        elif klass == "running":
            c.status = CaseStatus.RUNNING
        elif klass == "pending":
            c.status = CaseStatus.QUEUED
        elif klass == "transient":
            if c.retries < MAX_TRANSIENT_RETRIES:
                transient_retry.append(c.idx)
            else:
                c.status = CaseStatus.FAILED_SYSTEMATIC
                c.diagnosis = f"transient {c.slurm_state} persisted past {MAX_TRANSIENT_RETRIES} retries"
                _attn(card, f"case {c.idx}: {c.diagnosis}")
        else:  # systematic
            c.status = CaseStatus.FAILED_SYSTEMATIC
            c.diagnosis = f"systematic failure: {c.slurm_state}"
            _attn(card, f"case {c.idx}: {c.diagnosis}")

    # tiered recovery: resubmit transient indices as one throttled array
    if transient_retry:
        if spec is not None:
            _resubmit(card, spec, remote, transient_retry)
        else:
            _attn(
                card,
                f"cannot resubmit transient cases {transient_retry}: study.yaml failed to load",
            )
            card.state = StudyState.ATTENTION
            return card

    # budget enforcement (never overspend): cancel remainder if over ceiling.
    # Recompute the live job set AFTER resubmit — _resubmit mints new job ids,
    # so the pre-resubmit `bases` snapshot no longer covers what is running.
    card.budget.spent_core_hours = _spent(card)
    ceil = card.budget.ceiling_core_hours
    if ceil is not None and card.budget.spent_core_hours > ceil:
        live = sorted({c.jobid.split("_")[0] for c in card.cases if c.jobid})
        for b in live:
            remote.run(f"scancel {b}", mutating=True)
        card.state = StudyState.BUDGET_EXCEEDED
        _attn(
            card,
            f"spent {card.budget.spent_core_hours:.0f} core-h exceeded ceiling "
            f"{ceil:.0f}; cancelled remaining jobs",
        )
        return card

    _advance_lane(card)
    return card


def _resubmit(card: Card, spec: Spec, remote: Remote, indices: List[int]) -> None:
    module_hash = dispatch_mod.resolve_module_hash(remote)
    conc = card.budget.max_concurrent_jobs
    array_expr = ",".join(str(i) for i in sorted(indices)) + f"%{conc}"
    args = dispatch_mod.array_sbatch_args(card, spec, module_hash, array_expr)
    script = f"{card.remote_workdir}/case.sbatch"
    new_base = remote.sbatch(script, args)
    if new_base is None:  # dry-run: never mutate real card state
        card.log(f"[dry-run] would resubmit transient cases {indices}")
        return
    for c in card.cases:
        if c.idx in indices:
            # bank the failed attempt's hours before the id (and thus the
            # sacct lookup) is repointed, so retries never drop from the ledger
            c.spent_core_hours = round(c.spent_core_hours + c.core_hours, 3)
            c.core_hours = 0.0
            c.retries += 1
            c.jobid = f"{new_base}_{c.idx}"
            c.status = CaseStatus.QUEUED
            c.slurm_state = None
    card.log(f"resubmitted transient cases {indices} as array {new_base}")


def _advance_lane(card: Card) -> None:
    p = card.progress()
    if p["running"] or p["queued"] or p["pending"]:
        card.state = StudyState.RUNNING
        return
    if card.all_cases_terminal():
        if p["done"] == 0:
            card.state = StudyState.ATTENTION
            _attn(card, "all cases failed systematically; nothing to collect")
        else:
            card.state = StudyState.COLLECTING


def _attn(card: Card, reason: str) -> None:
    card.attention.append({"reason": reason, "when": now_iso()})
    card.log(f"ATTENTION: {reason}")


# --------------------------------------------------------------------------
# top-level orchestration
# --------------------------------------------------------------------------


def advance_card(study_id: str, dry_run: bool = False) -> Card:
    """Full re-entry step for one study: sync -> (collect -> report -> done)."""
    from . import board

    card = board.load_card(study_id)
    # DONE and the parked lanes (ATTENTION, BUDGET_EXCEEDED) are sticky: re-entry
    # must be idempotent and never re-append duplicate attention/history. Only
    # CONNECTION_DOWN is re-processed, so it can recover once the cluster is back.
    if card.state in (StudyState.DONE, StudyState.ATTENTION, StudyState.BUDGET_EXCEEDED):
        return card

    try:
        spec = load_for_id(study_id)
    except Exception:
        spec = None

    remote = Remote(card.cluster, dry_run=dry_run)
    if not dry_run and not remote.check_connection():
        card.state = StudyState.CONNECTION_DOWN
        _attn(card, "cluster unreachable at reconcile")
        board.save_card(card)
        return card

    # a card sitting in CONNECTION_DOWN recovers automatically once reachable
    if card.state == StudyState.CONNECTION_DOWN and card.cases:
        card.state = StudyState.RUNNING

    if card.cases and card.state not in (StudyState.APPROVED, StudyState.READY):
        try:
            sync_card(card, spec, remote)
        except ConnectionError_ as ce:
            card.state = StudyState.CONNECTION_DOWN
            _attn(card, f"lost connection during reconcile: {ce}")
            board.save_card(card)
            return card
        except Exception as ex:  # park, never crash the reconcile
            card.state = StudyState.ATTENTION
            _attn(card, f"reconcile error: {ex}")
            board.save_card(card)
            return card

    # collection + reporting when all cases are terminal
    if card.state == StudyState.COLLECTING and spec is not None:
        board.save_card(card)
        try:
            collect_mod.collect_results(card, spec, remote, dry_run=dry_run)
            card.state = StudyState.ANALYZING
            board.save_card(card)
            report_mod.build_report(card, spec)
            card.state = StudyState.DONE
            card.log("report written; study complete")
        except Exception as e:  # collection/report failure -> park, keep data
            card.state = StudyState.ATTENTION
            _attn(card, f"collection/report failed: {e}")

    board.save_card(card)
    return card


def reconcile_all(dry_run: bool = False) -> List[Card]:
    from . import board

    out = []
    for sid in board.list_study_ids():
        if not board.has_card(sid):
            continue
        # one malformed card, dead connection, or sbatch error must not sink the
        # whole run — isolate each study.
        try:
            card = board.load_card(sid)
        except Exception as ex:
            print(f"reconcile: skipping {sid!r} (unreadable card: {ex})", file=sys.stderr)
            continue
        if card.state in TERMINAL_LANES and card.state not in ATTENTION_LANES:
            out.append(card)
            continue
        try:
            out.append(advance_card(sid, dry_run=dry_run))
        except Exception as ex:
            print(f"reconcile: {sid!r} errored: {ex}", file=sys.stderr)
            out.append(card)
    board.refresh()
    return out
