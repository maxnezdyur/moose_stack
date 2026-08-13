"""Command-line surface for the analysis toolkit.

The AI (skills /analysis-blueprint, /analysis-run) drives these commands and
supplies judgment; the commands themselves are deterministic. Nothing here
authenticates to HPC — SSH auth is delegated to ~/.ssh/config.

Commands:
  new <id> [--kind K]      scaffold a study dir + skeleton study.yaml
  validate <id>            validate study.yaml (exit 2 on error)
  init <id>                mint card.yaml from an approved spec
  smoke <id>               local build-if-missing + smoke; -> READY on pass
  estimate <id>            print worst-case core-hour estimate + budget verdict
  run <id> [--dry-run]     fire: smoke (if needed) -> budget-gate -> dispatch
  reconcile [<id>|--all]   re-entry: sync SLURM -> advance -> collect -> report
  collect <id>             pull CSV/logs + extract QoIs (idempotent)
  report <id>              (re)render report.html from the current card
  fetch-fields <id> -c K   on-demand pull of large field output for one case
  status [<id>]            print a card summary (or the whole board)
  board                    regenerate the board (BOARD.md, or vault Home + notes)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import board as board_mod
from . import config
from . import dispatch as dispatch_mod
from . import localrun
from . import reconcile as reconcile_mod
from . import report as report_mod
from . import collect as collect_mod
from .model import ATTENTION_LANES, StudyState, now_iso
from .remote import ConnectionError_, Remote
from .spec import SpecError, load_for_id


SKELETON = """\
# Study spec (approve this before firing). See analysis/README.md for the schema.
id: {id}
title: "{id}"
kind: {kind}                 # sweep | convergence | optimization
app: combined                # moose | combined | blackbear | isopod
cluster: bitterroot          # default; overridable
account: intern
# repo_sha: HEAD             # pin a sha; default uses the scratch checkout HEAD

baseline:
  input: inputs/base.i       # path relative to this study dir (must exist)
  extra_files: []            # meshes, includes, etc.

# --- case definition (pick the block matching `kind`) ---
sweep:
  method: grid               # grid | zip
  params:
    Materials/thermal/k: [1.0, 2.0, 5.0, 10.0]
# convergence:
#   param: Mesh/uniform_refine
#   levels: [0, 1, 2, 3, 4]
#   reference: finest        # finest | analytic
# optimization:
#   max_iters: 100           # hard bound

qoi:
  csv: base_out.csv          # informational; per-case CSV is <file_base>.csv
  columns: [peak_T]          # CSV columns to extract as QoIs
  reduce: last               # last | max | min

# Optional cheap local smoke solve (else only --check-input runs locally):
# smoke:
#   overrides:
#     Executioner/num_steps: 1
#     Mesh/uniform_refine: 0

budget:
  ceiling_core_hours: 200    # REQUIRED — fire-and-forget must be bounded
  max_concurrent_jobs: 16
  max_walltime_per_case: "02:00:00"

resources:
  nodes: 1
  ntasks: 48
  partition: general
"""


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="analysis", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add(name, **kw):
        p = sub.add_parser(name, **kw)
        return p

    p = add("new"); p.add_argument("id"); p.add_argument("--kind", default="sweep")
    p = add("validate"); p.add_argument("id")
    p = add("init"); p.add_argument("id")
    p = add("smoke"); p.add_argument("id")
    p = add("estimate"); p.add_argument("id")
    p = add("run"); p.add_argument("id"); p.add_argument("--dry-run", action="store_true")
    p.add_argument("--cluster")
    p = add("reconcile"); p.add_argument("id", nargs="?"); p.add_argument("--all", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p = add("collect"); p.add_argument("id"); p.add_argument("--dry-run", action="store_true")
    p = add("report"); p.add_argument("id")
    p = add("fetch-fields"); p.add_argument("id"); p.add_argument("-c", "--case", type=int, required=True)
    p = add("status"); p.add_argument("id", nargs="?")
    add("board")

    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except SpecError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    except Exception as e:  # surfaced, not swallowed
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


def _dispatch(args) -> int:
    if args.cmd == "new":
        return _cmd_new(args.id, args.kind)
    if args.cmd == "validate":
        load_for_id(args.id)
        print(f"ok: {args.id}/study.yaml is valid")
        return 0
    if args.cmd == "init":
        return _cmd_init(args.id)
    if args.cmd == "smoke":
        return _cmd_smoke(args.id)
    if args.cmd == "estimate":
        return _cmd_estimate(args.id)
    if args.cmd == "run":
        return _cmd_run(args.id, dry_run=args.dry_run, cluster=args.cluster)
    if args.cmd == "reconcile":
        return _cmd_reconcile(args.id, all_=args.all, dry_run=args.dry_run)
    if args.cmd == "collect":
        return _cmd_collect(args.id, dry_run=args.dry_run)
    if args.cmd == "report":
        return _cmd_report(args.id)
    if args.cmd == "fetch-fields":
        return _cmd_fetch(args.id, args.case)
    if args.cmd == "status":
        return _cmd_status(args.id)
    if args.cmd == "board":
        board_mod.refresh()
        if config.vault_root():
            print(f"synced vault Home.md + study notes at {config.board_dir()}")
        else:
            print(f"wrote {config.board_dir() / 'BOARD.md'}")
        return 0
    print(f"unknown command {args.cmd}", file=sys.stderr)
    return 1


# --------------------------------------------------------------------------
# command implementations
# --------------------------------------------------------------------------


def _cmd_new(study_id: str, kind: str) -> int:
    d = config.study_dir(study_id)
    (d / "inputs").mkdir(parents=True, exist_ok=True)
    spec_path = d / "study.yaml"
    if spec_path.exists():
        print(f"exists: {spec_path}", file=sys.stderr)
        return 1
    spec_path.write_text(SKELETON.format(id=study_id, kind=kind))
    print(f"scaffolded {spec_path}\n  add your baseline input at {d/'inputs'/'base.i'}, "
          f"then: analysis validate {study_id}")
    return 0


def _load_or_mint_card(study_id: str):
    spec = load_for_id(study_id)
    if board_mod.has_card(study_id):
        card = board_mod.load_card(study_id)
    else:
        card = spec.new_card()
        board_mod.save_card(card)
    return spec, card


def _cmd_init(study_id: str) -> int:
    spec = load_for_id(study_id)
    if board_mod.has_card(study_id):
        print(f"card already exists for {study_id}")
        return 0
    card = spec.new_card()
    board_mod.save_card(card)
    board_mod.refresh()
    print(f"minted card for {study_id} (state={card.state.value})")
    return 0


def _park(card, exc: Exception, prefix: str) -> None:
    """Park a card on an unexpected failure instead of letting it crash the CLI."""
    card.state = (
        StudyState.CONNECTION_DOWN if isinstance(exc, ConnectionError_) else StudyState.ATTENTION
    )
    card.attention.append({"reason": f"{prefix}: {type(exc).__name__}: {exc}", "when": now_iso()})
    board_mod.save_card(card)
    board_mod.refresh()


def _cmd_smoke(study_id: str) -> int:
    spec, card = _load_or_mint_card(study_id)
    card.state = StudyState.SMOKING
    board_mod.save_card(card)
    try:
        localrun.smoke(spec, card)
    except Exception as ex:  # e.g. local build failure -> park, don't crash
        _park(card, ex, "smoke")
        print(f"smoke errored; parked: {ex}", file=sys.stderr)
        return 1
    if card.smoke.status == "passed":
        card.state = StudyState.READY
        print(f"smoke passed ({card.smoke.where}); state -> ready")
        rc = 0
    else:
        card.state = StudyState.ATTENTION
        card.attention.append({"reason": f"smoke failed: {card.smoke.message}", "when": now_iso()})
        print(f"smoke FAILED:\n{card.smoke.message}", file=sys.stderr)
        rc = 1
    board_mod.save_card(card)
    board_mod.refresh()
    return rc


def _cmd_estimate(study_id: str) -> int:
    spec = load_for_id(study_id)
    from .cases import enumerate_cases
    cases = enumerate_cases(spec)
    per, total = dispatch_mod.estimate_core_hours(spec, len(cases))
    ceil = spec.budget().ceiling_core_hours
    verdict = "WITHIN budget" if (ceil is None or total <= ceil) else "EXCEEDS budget"
    print(f"{study_id}: {len(cases)} cases x {per:.1f} core-h (worst case) "
          f"= {total:.0f} core-h; ceiling {ceil:.0f} -> {verdict}")
    return 0 if (ceil is None or total <= ceil) else 1


def _cmd_run(study_id: str, dry_run: bool, cluster: Optional[str]) -> int:
    spec, card = _load_or_mint_card(study_id)
    if cluster:
        card.cluster = cluster
    # don't re-fire a study that is already live on the cluster (double-submit guard)
    live = (StudyState.DISPATCHED, StudyState.RUNNING, StudyState.COLLECTING, StudyState.ANALYZING)
    if not dry_run and card.state in live:
        print(f"{study_id} is already {card.state.value}; not re-firing. "
              f"Run `analysis reconcile {study_id}` to advance it.", file=sys.stderr)
        return 1
    # smoke gate (unless already passed)
    if card.smoke.status != "passed":
        card.state = StudyState.SMOKING
        board_mod.save_card(card)
        try:
            localrun.smoke(spec, card)
        except Exception as ex:
            _park(card, ex, "smoke")
            print(f"smoke errored; parked: {ex}", file=sys.stderr)
            return 1
        if card.smoke.status != "passed":
            card.state = StudyState.ATTENTION
            card.attention.append({"reason": f"smoke failed: {card.smoke.message}", "when": now_iso()})
            board_mod.save_card(card)
            board_mod.refresh()
            print(f"smoke FAILED; parked.\n{card.smoke.message}", file=sys.stderr)
            return 1
        card.state = StudyState.READY
        board_mod.save_card(card)
    # dispatch (budget gate + submit)
    try:
        dispatch_mod.dispatch(card, spec, dry_run=dry_run)
    except Exception as ex:  # ssh/build/sbatch failure -> park, never crash
        _park(card, ex, "dispatch")
        print(f"dispatch errored; parked: {ex}", file=sys.stderr)
        return 1
    board_mod.save_card(card)
    board_mod.refresh()
    print(f"{study_id}: state -> {card.state.value}"
          + (f" ({card.progress()['total']} cases)" if card.cases else ""))
    if card.state in (StudyState.BUDGET_EXCEEDED, StudyState.ATTENTION, StudyState.CONNECTION_DOWN):
        for a in card.attention[-2:]:
            print(f"  ! {a['reason']}")
        return 1
    return 0


def _cmd_reconcile(study_id: Optional[str], all_: bool, dry_run: bool) -> int:
    if all_ or study_id is None:
        cards = reconcile_mod.reconcile_all(dry_run=dry_run)
        for c in cards:
            print(f"  {c.id:30s} {c.state.value}")
    else:
        card = reconcile_mod.advance_card(study_id, dry_run=dry_run)
        board_mod.refresh()
        print(f"{study_id}: {card.state.value} ({board_mod._progress_str(card)})")
        cards = [card]
    # nonzero if anything needs human eyes — matches run/smoke, useful for cron
    return 1 if any(c.state in ATTENTION_LANES for c in cards) else 0


def _cmd_collect(study_id: str, dry_run: bool) -> int:
    spec = load_for_id(study_id)
    card = board_mod.load_card(study_id)
    remote = Remote(card.cluster, dry_run=dry_run)
    try:
        collect_mod.collect_results(card, spec, remote, dry_run=dry_run)
    except Exception as ex:
        _park(card, ex, "collect")
        print(f"collect errored; parked: {ex}", file=sys.stderr)
        return 1
    board_mod.save_card(card)
    print(f"{study_id}: collected {sum(1 for c in card.cases if c.qoi)} QoI rows")
    return 0


def _cmd_report(study_id: str) -> int:
    spec = load_for_id(study_id)
    card = board_mod.load_card(study_id)
    out = report_mod.build_report(card, spec)
    board_mod.save_card(card)
    print(f"wrote {out}")
    return 0


def _cmd_fetch(study_id: str, case_idx: int) -> int:
    card = board_mod.load_card(study_id)
    remote = Remote(card.cluster)
    try:
        local = collect_mod.fetch_fields(card, case_idx, remote)
    except (ConnectionError_, RuntimeError, ValueError) as ex:
        print(f"fetch-fields failed: {ex}", file=sys.stderr)
        return 1
    print(f"fetched fields for case {case_idx} -> {local}")
    return 0


def _cmd_status(study_id: Optional[str]) -> int:
    if study_id:
        card = board_mod.load_card(study_id)
        print(f"{card.id}  [{card.state.value}]  {card.kind}/{card.app} on {card.cluster}")
        print(f"  progress: {board_mod._progress_str(card)}")
        print(f"  budget:   {card.budget.spent_core_hours:.1f}"
              + (f"/{card.budget.ceiling_core_hours:.0f}" if card.budget.ceiling_core_hours else "")
              + " core-h")
        if card.remote_workdir:
            print(f"  workdir:  {card.cluster}:{card.remote_workdir}")
        if card.report_path:
            print(f"  report:   {card.report_path}")
        for a in card.attention[-5:]:
            print(f"  ! {a.get('reason','')}")
        for h in card.history[-8:]:
            print(f"    {h}")
    else:
        print(board_mod.render_board_md(board_mod.load_all_cards()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
