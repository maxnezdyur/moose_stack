"""Dispatch a study to HPC: budget-gate, ensure the pinned binary, stage
inputs, and submit the cases as a throttled SLURM array.

Safety rails baked in here:
  * Conservative worst-case cost estimate (ntasks x walltime x cases) gates
    against the core-hour ceiling *before* anything is submitted.
  * The binary is built once per (cluster, app, sha) into a cache; cases
    depend on the build job via ``afterok`` so they never run against a
    half-built or missing binary.
  * We never mutate the shared scratch checkout's git state; if it isn't at
    the spec's pinned sha, we park rather than silently build the wrong tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from . import config
from .cases import case_overrides, enumerate_cases
from .model import Card, CaseStatus, StudyState, now_iso
from .remote import ConnectionError_, Remote
from .spec import Spec


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def parse_walltime_hours(hhmmss: str) -> float:
    """'02:30:00' -> 2.5 hours. Accepts D-HH:MM:SS too."""
    days = 0
    if "-" in hhmmss:
        d, hhmmss = hhmmss.split("-", 1)
        days = int(d)
    parts = [int(x) for x in hhmmss.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts[-3], parts[-2], parts[-1]
    return days * 24 + h + m / 60 + s / 3600


def app_submodule(app: str) -> str:
    return "moose" if app in ("moose", "combined") else app


def estimate_core_hours(spec: Spec, ncases: int) -> Tuple[float, float]:
    """(per_case, total) conservative worst-case core-hours."""
    res = spec.resources()
    ntasks = int(res["ntasks"])
    wall_h = parse_walltime_hours(spec.budget().max_walltime_per_case)
    per_case = ntasks * wall_h
    return per_case, per_case * ncases


# --------------------------------------------------------------------------
# binary cache
# --------------------------------------------------------------------------


def resolve_remote_sha(remote: Remote, app: str) -> str:
    sub = app_submodule(app)
    stack = remote.moose_stack()
    res = remote.run(f"cd {stack}/{sub} && git rev-parse --short=12 HEAD")
    if not res.ok or not res.stdout:
        raise ConnectionError_(
            f"could not read HEAD of {sub} at {stack} on {remote.cluster}"
        )
    return res.stdout.splitlines()[-1].strip()


def resolve_module_hash(remote: Remote) -> str:
    stack = remote.moose_stack()
    res = remote.run(f"cd {stack} && {config.VERSIONER} moose-dev", login=True)
    if not res.ok or not res.stdout:
        raise ConnectionError_(f"versioner failed on {remote.cluster}: {res.stderr}")
    return res.stdout.splitlines()[-1].strip()


def ensure_remote_binary(
    remote: Remote, card: Card, spec: Spec, module_hash: str, dry_run: bool
) -> Tuple[str, Optional[str]]:
    """Return (binary_path, build_jobid). build_jobid is None on a cache hit."""
    app = card.app
    sha = card.repo_sha
    cache = remote.bincache(app, sha)
    binary_name = config.app_binary_name(app)
    cached = f"{cache}/{binary_name}"

    if remote.exists(cached):
        card.log(f"binary cache hit: {cached}")
        return cached, None

    # cache miss -> submit a build job that copies the binary into the cache.
    build_dir = f"{remote.moose_stack()}/{config.app_build_dir(app)}"
    remote.write_file(_template("build.sbatch"), f"{remote.workdir(card.id)}/build.sbatch")
    args = [
        f"--account={card.account}",
        f"--partition={config.SHORT_PARTITION}",
        "--nodes=1",
        "--ntasks=16",
        "--time=03:00:00",
        f"--job-name=build-{app}",
        "--output=%x-%j.out",
        f"--export=ALL,MOOSE_HASH={module_hash},BUILD_DIR={build_dir},"
        f"BINARY_NAME={binary_name},CACHE_DIR={cache}",
    ]
    jobid = remote.sbatch(f"{remote.workdir(card.id)}/build.sbatch", args)
    card.log(f"submitted build job {jobid} for {app}@{sha}")
    return cached, jobid


# --------------------------------------------------------------------------
# dispatch
# --------------------------------------------------------------------------


def dispatch(card: Card, spec: Spec, dry_run: bool = False) -> Card:
    remote = Remote(card.cluster, dry_run=dry_run)

    # 0) connectivity — park rather than crash if HPC is unreachable.
    if not dry_run and not remote.check_connection():
        card.state = StudyState.CONNECTION_DOWN
        _attn(card, "cannot reach cluster (off-network or ticket expired)")
        return card

    # 1) enumerate cases + estimate cost
    cases = enumerate_cases(spec)
    if not cases:
        card.state = StudyState.ATTENTION
        _attn(card, "study enumerated zero cases; check the sweep/convergence definition")
        return card
    per_case, total = estimate_core_hours(spec, len(cases))
    card.smoke.est_core_hours_per_case = round(per_case, 3)
    ceiling = card.budget.ceiling_core_hours
    if ceiling is not None and total > ceiling:
        card.state = StudyState.BUDGET_EXCEEDED
        _attn(
            card,
            f"estimated {total:.0f} core-h ({len(cases)} cases x {per_case:.1f}) "
            f"exceeds ceiling {ceiling:.0f}",
        )
        return card

    # 2) resolve remote provenance (actual sha + module hash)
    workdir = remote.workdir(card.id)
    card.remote_workdir = workdir
    if not dry_run:
        actual_sha = resolve_remote_sha(remote, card.app)
        if spec.repo_sha and spec.repo_sha not in (actual_sha, "HEAD"):
            card.state = StudyState.ATTENTION
            _attn(
                card,
                f"scratch checkout of {app_submodule(card.app)} at {actual_sha}, "
                f"spec pins {spec.repo_sha}; refusing to mutate shared tree",
            )
            return card
        card.repo_sha = actual_sha
        module_hash = resolve_module_hash(remote)
    else:
        card.repo_sha = card.repo_sha or "HEAD"
        module_hash = "DRYRUNHASH"

    card.cases = cases

    # 3) stage inputs
    spec_dir = spec.path.parent
    inputs_remote = f"{workdir}/inputs"
    if not dry_run:
        remote.mkdirs(inputs_remote)
    remote.push_file(spec_dir / spec.baseline_input, f"{inputs_remote}/{Path(spec.baseline_input).name}")
    for extra in spec.extra_files:
        remote.push_file(spec_dir / extra, f"{inputs_remote}/{Path(extra).name}")

    # 4) write the cases manifest (idx \t space-joined overrides)
    lines = []
    for c in cases:
        ovr = " ".join(case_overrides(c))
        lines.append(f"{c.idx}\t{ovr}")
    remote.write_file("\n".join(lines) + "\n", f"{workdir}/cases.tsv")

    # 5) ensure binary (may submit a build job cases depend on)
    binary_path, build_jobid = ensure_remote_binary(
        remote, card, spec, module_hash, dry_run
    )
    card.binary_path = binary_path
    card.build_jobid = build_jobid

    # 6) upload the (static) case-array script + submit
    remote.write_file(_template("case.sbatch"), f"{workdir}/case.sbatch")

    n = len(cases)
    array = f"0-{n - 1}%{card.budget.max_concurrent_jobs}" if n > 1 else "0-0"
    args = array_sbatch_args(card, spec, module_hash, array, build_jobid=build_jobid)
    if not dry_run:
        remote.mkdirs(f"{workdir}/logs")

    # Lost-receipt / double-submit guard: a live job already carrying this
    # study's --job-name means a prior dispatch reached the cluster (even if its
    # id was never persisted). Adopt it instead of firing a second array.
    job_name = f"an-{card.id}"
    existing = [] if dry_run else remote.jobids_by_name(job_name)
    if existing:
        base = existing[0]
        card.log(f"adopted existing submission {existing} for {job_name}; not resubmitting")
    else:
        array_jobid = remote.sbatch(f"{workdir}/case.sbatch", args)
        base = array_jobid or "DRYRUN"

    # 7) map job ids onto cases
    for c in cases:
        c.jobid = f"{base}_{c.idx}"
        c.status = CaseStatus.QUEUED
        c.workdir = f"{workdir}/case_{c.idx:04d}"
    card.state = StudyState.DISPATCHED
    card.log(
        f"dispatched {n} cases as array {base} on {card.cluster} "
        f"(dep build={build_jobid})"
    )
    return card


def array_sbatch_args(
    card: Card,
    spec: Spec,
    module_hash: str,
    array_expr: str,
    build_jobid: Optional[str] = None,
) -> List[str]:
    """Build the sbatch CLI args for a (re)submission of the case array.

    Shared by initial dispatch and reconcile's transient-retry path so the two
    can never drift on account/partition/resources.
    """
    res = spec.resources()
    workdir = card.remote_workdir or f"/scratch/USER/analysis/{card.id}"
    input_abs = f"{workdir}/inputs/{Path(spec.baseline_input).name}"
    binary = card.binary_path or "BINARY_UNSET"
    args = [
        f"--account={card.account}",
        f"--partition={res['partition']}",
        f"--nodes={res['nodes']}",
        f"--ntasks={res['ntasks']}",
        f"--time={card.budget.max_walltime_per_case}",
        f"--array={array_expr}",
        f"--job-name=an-{card.id}",
        f"--chdir={workdir}",
        "--output=logs/case_%a-%A.out",
        f"--export=ALL,MOOSE_HASH={module_hash},BINARY={binary},INPUT={input_abs}",
    ]
    if build_jobid:
        args.append(f"--dependency=afterok:{build_jobid}")
    return args


def _attn(card: Card, reason: str) -> None:
    card.attention.append({"reason": reason, "when": now_iso()})
    card.log(f"ATTENTION: {reason}")


# --------------------------------------------------------------------------
# script rendering (templates are static; values injected here)
# --------------------------------------------------------------------------


def _template(name: str) -> str:
    """Read a SLURM template verbatim (uploaded as-is; values come via --export)."""
    return (config.slurm_template_dir() / name).read_text()
