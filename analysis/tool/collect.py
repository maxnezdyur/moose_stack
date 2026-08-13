"""Collect results back from HPC and extract QoIs.

Design policy: pull only the light artifacts (CSVs + console logs) into the
card's ``results/`` dir; large Exodus/checkpoint fields stay on scratch and are
fetched on demand (see ``fetch_fields``). QoIs are read from each case's
``<file_base>.csv`` (MOOSE writes the CSV postprocessor output there because we
override ``Outputs/file_base`` per case).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config
from .model import Card, CaseStatus, now_iso
from .remote import Remote
from .spec import Spec

# artifacts small enough to always pull back
LIGHT_INCLUDES = ["*.csv", "*.out", "*.txt", "*.log", "*.json"]


def _case_local_dir(card: Card, idx: int) -> Path:
    return config.study_dir(card.id) / "results" / f"case_{idx:04d}"


def collect_results(card: Card, spec: Spec, remote: Remote, dry_run: bool = False) -> Card:
    """Pull CSV/logs for every done case and extract QoIs onto the card."""
    qoi = spec.qoi
    columns: List[str] = list(qoi.get("columns", []))
    reduce = str(qoi.get("reduce", "last"))

    for c in card.cases:
        if c.status != CaseStatus.DONE or not c.workdir:
            continue
        local_dir = _case_local_dir(card, c.idx)
        remote.pull(c.workdir, local_dir, includes=LIGHT_INCLUDES)
        if dry_run:
            continue
        csv_path = local_dir / f"{c.file_base}.csv"
        if not csv_path.is_file():
            # QoI CSV missing despite COMPLETED — flag but keep the case done.
            c.qoi = {}
            c.diagnosis = (c.diagnosis or "") + " [qoi csv missing]"
            _attn(card, f"case {c.idx}: COMPLETED but {csv_path.name} not found")
            continue
        header = _csv_header(csv_path)
        missing = [col for col in columns if col not in header]
        if missing:
            c.diagnosis = (c.diagnosis or "") + f" [qoi columns missing: {missing}]"
            _attn(card, f"case {c.idx}: QoI columns absent from {csv_path.name}: {missing}")
        c.qoi = extract_qoi(csv_path, columns, reduce)

    card.log(f"collected results for {sum(1 for c in card.cases if c.qoi)} cases")
    return card


def extract_qoi(csv_path: Path, columns: List[str], reduce: str = "last") -> Dict[str, Any]:
    """Read a MOOSE CSV and return {column: value} under the reduce rule.

    reduce=last -> values from the final data row.
    reduce=max/min -> values from the row where columns[0] is extremal.
    """
    rows = _read_csv(csv_path)
    if not rows:
        return {}
    if reduce == "last":
        target = rows[-1]
    elif reduce in ("max", "min") and columns:
        key = columns[0]
        numeric = [(r, _to_float(r.get(key))) for r in rows]
        numeric = [(r, v) for r, v in numeric if v is not None]
        if not numeric:
            target = rows[-1]
        else:
            target = (max if reduce == "max" else min)(numeric, key=lambda t: t[1])[0]
    else:
        target = rows[-1]

    out: Dict[str, Any] = {}
    for col in columns:
        v = target.get(col)
        fv = _to_float(v)
        out[col] = fv if fv is not None else v
    return out


def fetch_fields(card: Card, idx: int, remote: Remote, patterns: Optional[List[str]] = None) -> Path:
    """On-demand pull of large field output (Exodus etc.) for one case."""
    case = next((c for c in card.cases if c.idx == idx), None)
    if case is None or not case.workdir:
        raise ValueError(f"no dispatched case {idx} in study {card.id}")
    patterns = patterns or ["*.e", "*.e-s*", "*.exd", "*.nemesis", "*.pvd", "*.vtu"]
    local_dir = _case_local_dir(card, idx) / "fields"
    remote.pull(case.workdir, local_dir, includes=patterns)
    return local_dir


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _csv_header(path: Path) -> List[str]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f).fieldnames or [])


def _to_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _attn(card: Card, reason: str) -> None:
    card.attention.append({"reason": reason, "when": now_iso()})
    card.log(f"ATTENTION: {reason}")
