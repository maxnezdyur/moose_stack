"""Load and validate ``study.yaml`` (the human-authored, AI-drafted spec).

The spec is immutable once approved; it is the contract the toolkit executes.
This module parses it, validates it hard (a fire-and-forget run must not start
on an underspecified study), and mints the initial ``Card``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from . import config
from .model import Budget, Card, Smoke, StudyKind, StudyState


class SpecError(ValueError):
    """Raised when a study.yaml fails validation. Carries all messages."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("invalid study.yaml:\n  - " + "\n  - ".join(errors))


@dataclass
class Spec:
    """Parsed study.yaml. ``raw`` keeps the untouched dict for case enumeration."""

    raw: Dict[str, Any]
    path: Path

    # ---- typed accessors ---------------------------------------------------

    @property
    def id(self) -> str:
        return str(self.raw["id"])

    @property
    def title(self) -> str:
        return str(self.raw.get("title", self.id))

    @property
    def kind(self) -> str:
        return str(self.raw.get("kind", StudyKind.SWEEP.value))

    @property
    def app(self) -> str:
        return str(self.raw.get("app", "combined"))

    @property
    def cluster(self) -> str:
        return str(self.raw.get("cluster", config.DEFAULT_CLUSTER))

    @property
    def account(self) -> str:
        return str(self.raw.get("account", config.DEFAULT_ACCOUNT))

    @property
    def repo_sha(self) -> Optional[str]:
        v = self.raw.get("repo_sha")
        return str(v) if v is not None else None

    @property
    def baseline_input(self) -> str:
        return str(self.raw["baseline"]["input"])

    @property
    def extra_files(self) -> List[str]:
        return [str(x) for x in self.raw.get("baseline", {}).get("extra_files", [])]

    @property
    def qoi(self) -> Dict[str, Any]:
        return dict(self.raw.get("qoi", {}))

    def resources(self) -> Dict[str, Any]:
        r = dict(self.raw.get("resources", {}))
        r.setdefault("nodes", config.DEFAULT_NODES)
        r.setdefault("ntasks", config.DEFAULT_NTASKS)
        r.setdefault("partition", config.DEFAULT_PARTITION)
        return r

    def budget(self) -> Budget:
        b = dict(self.raw.get("budget", {}))
        return Budget(
            ceiling_core_hours=b.get("ceiling_core_hours"),
            spent_core_hours=0.0,
            max_concurrent_jobs=int(b.get("max_concurrent_jobs", config.DEFAULT_MAX_CONCURRENT)),
            max_walltime_per_case=str(b.get("max_walltime_per_case", config.DEFAULT_WALLTIME)),
        )

    # ---- card minting ------------------------------------------------------

    def new_card(self) -> Card:
        """Build the initial APPROVED card from this spec (no cases yet)."""
        return Card(
            id=self.id,
            title=self.title,
            kind=self.kind,
            state=StudyState.APPROVED,
            app=self.app,
            cluster=self.cluster,
            account=self.account,
            repo_sha=self.repo_sha,
            smoke=Smoke(),
            budget=self.budget(),
        )


# --------------------------------------------------------------------------
# Loading + validation
# --------------------------------------------------------------------------


def load(path: Path) -> Spec:
    """Load and validate a study.yaml at ``path``. Raises SpecError on failure."""
    if not path.is_file():
        raise SpecError([f"no study.yaml at {path}"])
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        raise SpecError([f"YAML parse error: {e}"])
    if not isinstance(raw, dict):
        raise SpecError(["top-level study.yaml must be a mapping"])

    spec = Spec(raw=raw, path=path)
    errors = validate(spec)
    if errors:
        raise SpecError(errors)
    return spec


def load_for_id(study_id: str) -> Spec:
    return load(config.study_dir(study_id) / "study.yaml")


# Characters that would be mangled by the case runner, which word-splits and
# glob-expands the joined override tokens (see tool/slurm/case.sbatch).
_UNSAFE_OVERRIDE_CHARS = set(" \t\n\r*?[]{}()<>|&;$`\"'\\")


def _expand(valuespec):
    from .cases import expand_values  # deferred: cases imports Spec
    return expand_values(valuespec)


def _override_safety_errors(path: str, valuespec) -> List[str]:
    """Reject override values that shell word-splitting/globbing would corrupt."""
    from .cases import moose_override
    errs: List[str] = []
    try:
        values = _expand(valuespec)
    except Exception:
        return errs  # a bad range is reported separately
    for val in values:
        tok = moose_override(path, val)
        bad = sorted(_UNSAFE_OVERRIDE_CHARS & set(tok))
        if bad:
            errs.append(
                f"override {tok!r} contains shell-unsafe characters {bad}; "
                f"the case runner word-splits overrides, so use quote-free scalar values"
            )
    return errs


def validate(spec: Spec) -> List[str]:
    """Return a list of human-readable errors (empty == valid)."""
    e: List[str] = []
    r = spec.raw

    if not r.get("id"):
        e.append("missing required field: id")
    else:
        try:
            config.validate_study_id(str(r["id"]))
        except ValueError as ve:
            e.append(str(ve))
        if spec.path.parent.name != str(r["id"]):
            e.append(
                f"study id {r['id']!r} must match its directory name "
                f"{spec.path.parent.name!r}"
            )
    if r.get("app") and r["app"] not in config.APPS:
        e.append(f"unknown app {r['app']!r}; known: {', '.join(sorted(config.APPS))}")
    if r.get("cluster") and r["cluster"] not in config.CLUSTERS:
        e.append(
            f"unknown cluster {r['cluster']!r}; known: {', '.join(sorted(config.CLUSTERS))}"
        )
    kind = r.get("kind", StudyKind.SWEEP.value)
    if kind not in {k.value for k in StudyKind}:
        e.append(f"unknown kind {kind!r}; known: sweep, convergence, optimization")

    # baseline input is mandatory and must exist next to the spec
    baseline = r.get("baseline") or {}
    if not baseline.get("input"):
        e.append("missing required field: baseline.input")
    else:
        inp = spec.path.parent / baseline["input"]
        if not inp.is_file():
            e.append(f"baseline.input not found: {inp}")
    for extra in baseline.get("extra_files", []):
        p = spec.path.parent / extra
        if not p.exists():
            e.append(f"baseline.extra_files entry not found: {p}")

    # kind-specific case definition
    if kind == StudyKind.SWEEP.value:
        sweep = r.get("sweep") or {}
        params = sweep.get("params") or {}
        if not params:
            e.append("sweep study requires non-empty sweep.params")
        method = sweep.get("method", "grid")
        if method not in {"grid", "list", "zip"}:
            e.append(f"sweep.method must be grid|list|zip, got {method!r}")
        if method in ("zip", "list"):
            # parallel-list methods require equal-length params; expand ranges too
            lengths = {}
            for k, v in params.items():
                try:
                    lengths[k] = len(_expand(v))
                except Exception as ex:
                    e.append(f"sweep.params[{k}] invalid: {ex}")
            if len(set(lengths.values())) > 1:
                e.append(f"sweep.method={method} requires equal-length params, got {lengths}")
        for k, v in params.items():
            try:
                if not _expand(v):
                    e.append(f"sweep.params[{k}] expands to zero values")
            except Exception as ex:
                e.append(f"sweep.params[{k}] invalid range: {ex}")
            e += _override_safety_errors(k, v)
    elif kind == StudyKind.CONVERGENCE.value:
        conv = r.get("convergence") or {}
        if not conv.get("param"):
            e.append("convergence study requires convergence.param (e.g. Mesh/uniform_refine)")
        if not conv.get("levels"):
            e.append("convergence study requires convergence.levels (list of values)")
        else:
            e += _override_safety_errors(conv.get("param", ""), conv.get("levels"))
    elif kind == StudyKind.OPTIMIZATION.value:
        # optimization is a single job; done is criterion-driven.
        opt = r.get("optimization") or {}
        if not opt.get("max_iters"):
            e.append("optimization study requires optimization.max_iters (hard bound)")

    # QoI required for sweep/convergence (optimization reads its own history)
    if kind in (StudyKind.SWEEP.value, StudyKind.CONVERGENCE.value):
        qoi = r.get("qoi") or {}
        if not qoi.get("csv"):
            e.append("missing qoi.csv (postprocessor CSV basename to read QoIs from)")
        if not qoi.get("columns"):
            e.append("missing qoi.columns (list of CSV column names to extract)")
        reduce = str(qoi.get("reduce", "last"))
        if reduce not in {"last", "max", "min"}:
            e.append(f"qoi.reduce must be last|max|min, got {reduce!r}")

    # budget: a fire-and-forget run must be bounded
    budget = r.get("budget") or {}
    if budget.get("ceiling_core_hours") is None:
        e.append("missing budget.ceiling_core_hours (fire-and-forget must be bounded)")
    else:
        try:
            if float(budget["ceiling_core_hours"]) <= 0:
                e.append("budget.ceiling_core_hours must be positive")
        except (TypeError, ValueError):
            e.append("budget.ceiling_core_hours must be a number")

    return e
