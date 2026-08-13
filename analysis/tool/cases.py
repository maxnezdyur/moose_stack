"""Enumerate the concrete cases of a study from its spec.

Cases carry MOOSE HIT parameter overrides (``Path/To/param=value``) that are
applied on the command line — so a sweep never edits the input file, matching
the 'analysis shouldn't change code' constraint. Sweeps expand to a grid or a
zipped set; convergence expands one refinement parameter over levels; an
optimization study is a single self-driving job.
"""

from __future__ import annotations

import itertools
from typing import Any, Dict, List

from .model import Case, StudyKind
from .spec import Spec


def expand_values(v: Any) -> List[Any]:
    """Expand one parameter's value-spec into an explicit list.

    Accepts a scalar, an explicit list, or a range dict:
      - {start, stop, num}   -> num points, inclusive linear spacing
      - {start, stop, step}  -> arange-style, inclusive of stop within eps
    """
    if isinstance(v, list):
        return list(v)
    if isinstance(v, dict):
        if "num" in v:
            start, stop, num = float(v["start"]), float(v["stop"]), int(v["num"])
            if num < 1:
                raise ValueError(f"range num must be >=1: {v}")
            if num == 1:
                return [start]
            step = (stop - start) / (num - 1)
            return [round(start + i * step, 12) for i in range(num)]
        if "step" in v:
            start, stop, step = float(v["start"]), float(v["stop"]), float(v["step"])
            if step == 0:
                raise ValueError(f"range step must be nonzero: {v}")
            out, x, i = [], start, 0
            # guard against runaway ranges
            n = int(abs((stop - start) / step)) + 1
            for i in range(n + 1):
                x = start + i * step
                if (step > 0 and x > stop + 1e-9) or (step < 0 and x < stop - 1e-9):
                    break
                out.append(round(x, 12))
            if not out:
                raise ValueError(
                    f"range step sign disagrees with start->stop direction "
                    f"(produces zero points): {v}"
                )
            return out
        raise ValueError(f"range dict needs num or step: {v}")
    return [v]


def enumerate_cases(spec: Spec) -> List[Case]:
    kind = spec.kind
    if kind == StudyKind.SWEEP.value:
        return _sweep_cases(spec)
    if kind == StudyKind.CONVERGENCE.value:
        return _convergence_cases(spec)
    if kind == StudyKind.OPTIMIZATION.value:
        return _optimization_cases(spec)
    raise ValueError(f"cannot enumerate cases for kind {kind!r}")


def _mk_case(idx: int, params: Dict[str, Any]) -> Case:
    return Case(idx=idx, params=params, file_base=f"case_{idx:04d}")


def _sweep_cases(spec: Spec) -> List[Case]:
    sweep = spec.raw.get("sweep", {})
    method = sweep.get("method", "grid")
    params = sweep.get("params", {})
    keys = list(params.keys())
    expanded = {k: expand_values(params[k]) for k in keys}

    rows: List[Dict[str, Any]] = []
    if method == "grid":
        for combo in itertools.product(*[expanded[k] for k in keys]):
            rows.append(dict(zip(keys, combo)))
    else:  # zip / list -> parallel lists
        length = len(expanded[keys[0]]) if keys else 0
        for i in range(length):
            rows.append({k: expanded[k][i] for k in keys})

    return [_mk_case(i, row) for i, row in enumerate(rows)]


def _convergence_cases(spec: Spec) -> List[Case]:
    conv = spec.raw.get("convergence", {})
    param = conv["param"]
    levels = conv["levels"]
    return [_mk_case(i, {param: lvl}) for i, lvl in enumerate(levels)]


def _optimization_cases(spec: Spec) -> List[Case]:
    # A single job; the input drives its own optimizer to convergence.
    return [_mk_case(0, {})]


# --------------------------------------------------------------------------
# MOOSE command-line override formatting
# --------------------------------------------------------------------------


def _fmt_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        # keep integer-valued floats tidy (2.0 -> "2")
        if v.is_integer():
            return str(int(v))
        return repr(v)
    return str(v)


def moose_override(path: str, value: Any) -> str:
    """One HIT override token: ``Materials/thermal/k=2.5``."""
    return f"{path}={_fmt_value(value)}"


def case_overrides(case: Case) -> List[str]:
    """The ordered list of HIT override tokens for a case, plus its file_base.

    The Outputs/file_base override keeps per-case output filenames distinct
    even if two cases share a run directory (they don't, but it's cheap
    insurance and makes collection deterministic).
    """
    tokens = [moose_override(p, v) for p, v in case.params.items()]
    if case.file_base:
        tokens.append(moose_override("Outputs/file_base", case.file_base))
    return tokens
