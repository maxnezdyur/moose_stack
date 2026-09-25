"""Turn a finished run's outputs into ``qoi.json``, per the ``## Measures`` table.

This module owns the two measure forms of ``formats/campaign.md``:

* a backtick command, run from the campaign directory with ``{outputs}``
  replaced by the run's outputs and ``{run}`` by its id; it prints one JSON
  object keyed by measure names. A command shared by several measures runs once.
* ``csv:<file>:<column>:<last|max|min>``, which reads one column of a kept
  output file and reduces it.

``{outputs}`` and a csv ``<file>`` resolve against ``runs/<D>/outputs/``, the
kept copy (pulled by ``reconcile``, or copied at the end of a local run),
when it holds the file, else against ``outputs.dir`` when that directory is on
this machine. A key no measure names is refused and nothing is written.
Collect is idempotent: the same outputs give the same bytes. Once a verdict
is set the run is frozen and collect refuses.

For a replay, collect compares the new ``qoi`` with the original run's,
measure by measure, and writes the result into the new run's ``note.md``.
"""

from __future__ import annotations

import csv
import json
import math
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config, manifest, spec
from .model import Campaign, Measure, Run

REPLAY_RTOL = 1e-6
REPLAY_ATOL = 1e-12


def _to_float(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def outputs_dir(run: Run) -> Path:
    kept = run.path / "outputs"
    if kept.is_dir() and any(kept.iterdir()):
        return kept
    d = Path(str((run.outputs or {}).get("dir") or ""))
    if d.is_dir():
        return d
    return kept


def csv_measure(m: Measure, run: Run) -> Tuple[Optional[float], Optional[str]]:
    candidates = [run.path / "outputs" / m.csv_file]
    d = (run.outputs or {}).get("dir")
    if d:
        candidates.append(Path(str(d)) / m.csv_file)
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        return None, "%s: %s not found in the kept outputs or %s" % (m.name, m.csv_file, d)
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows or m.csv_column not in rows[0]:
        return None, "%s: column %r absent from %s" % (m.name, m.csv_column, path.name)
    vals = [_to_float(r.get(m.csv_column)) for r in rows]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None, "%s: column %r of %s holds no number" % (m.name, m.csv_column, path.name)
    if m.csv_reduce == "max":
        return max(vals), None
    if m.csv_reduce == "min":
        return min(vals), None
    return vals[-1], None


def run_command(m: Measure, run: Run, camp: Campaign) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    out_dir = str(outputs_dir(run))
    tokens = [t.replace("{outputs}", out_dir).replace("{run}", run.run) for t in shlex.split(m.command)]
    try:
        p = subprocess.run(tokens, cwd=str(camp.dir), capture_output=True, text=True, timeout=3600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, "%s: %s" % (m.name, exc)
    if p.returncode != 0:
        tail = (p.stderr.strip().splitlines() or [""])[-1]
        return None, "%s: command exited %d: %s" % (m.name, p.returncode, tail)
    for line in reversed(p.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                return obj, None
    try:
        obj = json.loads(p.stdout)
        if isinstance(obj, dict):
            return obj, None
    except ValueError:
        pass
    return None, "%s: command printed no JSON object" % m.name


def measure(camp: Campaign, run: Run) -> Tuple[Dict[str, Any], List[str]]:
    """({measure name: value}, problems). Raises Refused on a key no measure names."""
    names = [m.name for m in camp.measures]
    qoi: Dict[str, Any] = {}
    problems: List[str] = []
    cache: Dict[str, Tuple[Optional[Dict[str, Any]], Optional[str]]] = {}
    for m in camp.measures:
        if m.kind == "csv":
            v, err = csv_measure(m, run)
            if err:
                problems.append(err)
            else:
                qoi[m.name] = v
        elif m.kind == "cmd":
            if m.command not in cache:
                cache[m.command] = run_command(m, run, camp)
            obj, err = cache[m.command]
            if err:
                problems.append(err)
                continue
            unknown = [k for k in obj if k not in names]
            if unknown:
                raise config.Refused("measure %s printed key(s) %s, not in ## Measures; nothing written"
                                     % (m.name, ", ".join(sorted(unknown))))
            if m.name in obj:
                qoi[m.name] = obj[m.name]
            else:
                problems.append("%s: its command printed no %r key" % (m.name, m.name))
    return {k: qoi[k] for k in names if k in qoi}, problems


def kept_patterns(camp: Campaign) -> List[str]:
    files = [m.csv_file for m in camp.measures if m.kind == "csv"]
    out: List[str] = []
    for f in files + ["run.log"]:
        if f not in out:
            out.append(f)
    return out


def compare(new: Dict[str, Any], old: Dict[str, Any]) -> List[Tuple[str, Any, Any, bool]]:
    rows = []
    for k in sorted(set(new) | set(old)):
        a, b = new.get(k), old.get(k)
        fa, fb = _to_float(a), _to_float(b)
        if fa is not None and fb is not None:
            ok = math.isclose(fa, fb, rel_tol=REPLAY_RTOL, abs_tol=REPLAY_ATOL)
        else:
            ok = a == b
        rows.append((k, b, a, ok))
    return rows


def replay_note(run: Run, original: Run, rows) -> str:
    lines = ["# %s %s" % (run.run, run.tag), "",
             "Replay of %s. Tolerance: relative %g, absolute %g per measure." % (original.run, REPLAY_RTOL, REPLAY_ATOL),
             "", "| measure | %s | %s | match |" % (original.run, run.run), "|---|---|---|---|"]
    for k, old, new, ok in rows:
        lines.append("| %s | %s | %s | %s |" % (k, old, new, "yes" if ok else "no"))
    lines.append("")
    lines.append("Reproduced: %s." % ("yes" if rows and all(r[3] for r in rows) else "no"))
    return "\n".join(lines) + "\n"


def stub_note(run: Run, qoi: Dict[str, Any]) -> str:
    shown = ", ".join("%s = %s" % (k, v) for k, v in qoi.items()) or "no measure"
    return "# %s %s\n\nTested: %s\nShowed: %s.\n" % (run.run, run.tag, run.hypothesis, shown)


def collect(camp: Campaign, run: Run, dry_run: bool = False) -> Tuple[Dict[str, Any], List[str]]:
    if run.verdict is not None:
        raise config.Refused("%s has verdict %s; its qoi is frozen" % (run.run, run.verdict))
    if not run.done:
        raise config.Look("%s has not finished; run `campaign reconcile` first" % run.run)
    qoi, problems = measure(camp, run)
    if dry_run:
        print("[dry-run] would write runs/%s/qoi.json: %s" % (run.path.name, json.dumps(qoi)))
        return qoi, problems
    config.write_text_atomic(run.path / "qoi.json", json.dumps(qoi) + "\n")
    run.qoi = qoi
    run.outputs = dict(run.outputs or {})
    run.outputs["kept"] = kept_patterns(camp)
    manifest.save(run)
    note = run.path / "note.md"
    if run.replay_of:
        d = spec.run_dir_for(camp, run.replay_of)
        if d is not None:
            original = manifest.load(d)
            config.write_text_atomic(note, replay_note(run, original, compare(qoi, original.qoi or {})))
    elif not note.is_file():
        config.write_text_atomic(note, stub_note(run, qoi))
    return qoi, problems
