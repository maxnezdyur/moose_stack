"""Local smoke + build-if-missing.

Policy (from design): every study is validated locally before it can consume
HPC allocation. We require a local binary and build it if absent. The smoke
always runs ``--check-input`` (catches missing files, bad HIT paths, malformed
setup) and, when the spec supplies cheap ``smoke.overrides``, also runs a short
solve to catch immediate divergence/NaN. It never touches the input file — all
reductions are command-line overrides.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import List

from . import config
from .cases import moose_override
from .model import Card
from .spec import Spec


class BuildError(RuntimeError):
    pass


class SmokeError(RuntimeError):
    pass


def local_binary_path(app: str) -> Path:
    build_dir = config.repo_root() / config.app_build_dir(app)
    return build_dir / config.app_binary_name(app)


def ensure_local_binary(app: str, jobs: int = 0) -> Path:
    """Return the local binary path, building it if missing.

    Assumes the correct conda env is active (see docs/local.md); if ``make``
    fails we surface a clear hint rather than a raw compiler error.
    """
    binary = local_binary_path(app)
    if binary.is_file() and os.access(binary, os.X_OK):
        return binary

    build_dir = config.repo_root() / config.app_build_dir(app)
    if not build_dir.is_dir():
        raise BuildError(f"build dir missing for app {app!r}: {build_dir}")

    jobs = jobs or min(8, (os.cpu_count() or 4))
    print(f"[smoke] local binary absent; building {app} in {build_dir} (-j{jobs})…")
    proc = subprocess.run(
        ["make", f"-j{jobs}"], cwd=str(build_dir), text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.splitlines()[-25:])
        raise BuildError(
            f"local build of {app} failed (rc={proc.returncode}). "
            f"Is the moose conda env active? (see docs/local.md)\n{tail}"
        )
    if not binary.is_file():
        raise BuildError(f"build finished but binary not found: {binary}")
    return binary


def _stage_smoke_inputs(spec: Spec) -> Path:
    """Copy baseline input + extra files into a scratch smoke dir."""
    smoke_dir = config.study_dir(spec.id) / "results" / "smoke"
    if smoke_dir.exists():
        shutil.rmtree(smoke_dir)
    smoke_dir.mkdir(parents=True, exist_ok=True)
    spec_dir = spec.path.parent
    for rel in [spec.baseline_input, *spec.extra_files]:
        src = spec_dir / rel
        dst = smoke_dir / Path(rel).name
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    return smoke_dir


def smoke(spec: Spec, card: Card) -> Card:
    """Run the local smoke and record the result on the card."""
    card.smoke.where = "local"
    binary = ensure_local_binary(spec.app)
    card.smoke.binary = str(binary)

    smoke_dir = _stage_smoke_inputs(spec)
    input_name = Path(spec.baseline_input).name

    # 1) --check-input: always. Cheap, catches setup errors.
    check = subprocess.run(
        [str(binary), "-i", input_name, "--check-input"],
        cwd=str(smoke_dir), text=True, capture_output=True, timeout=600,
    )
    if check.returncode != 0:
        card.smoke.status = "failed"
        card.smoke.message = "check-input failed:\n" + "\n".join(
            check.stderr.splitlines()[-20:] or check.stdout.splitlines()[-20:]
        )
        return card

    # 2) optional short solve, if the spec defines cheap smoke overrides.
    overrides: List[str] = []
    smoke_spec = spec.raw.get("smoke") or {}
    for path, val in (smoke_spec.get("overrides") or {}).items():
        overrides.append(moose_override(path, val))

    if overrides:
        t0 = time.time()
        run = subprocess.run(
            [str(binary), "-i", input_name, *overrides],
            cwd=str(smoke_dir), text=True, capture_output=True, timeout=1800,
        )
        card.smoke.runtime_s = round(time.time() - t0, 2)
        if run.returncode != 0:
            card.smoke.status = "failed"
            card.smoke.message = "short solve failed:\n" + "\n".join(
                run.stdout.splitlines()[-20:]
            )
            return card

    card.smoke.status = "passed"
    card.smoke.message = None
    return card
