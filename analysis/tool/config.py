"""Static configuration and path resolution for the analysis toolkit.

Everything host- or site-specific is centralized here. Values may be
overridden per study in ``study.yaml`` (see ``spec.py``) or via environment
variables for the few global ones.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

# A study id becomes both a local directory and a remote scratch path segment.
# Restrict it to a safe slug so it can never traverse (`..`, `/`) or land at an
# absolute path.
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def validate_study_id(study_id: str) -> str:
    if not isinstance(study_id, str) or not SAFE_ID.match(study_id) or ".." in study_id:
        raise ValueError(
            f"unsafe study id {study_id!r}: use letters, digits, dot, dash, underscore "
            f"(no '/', no leading '.', no '..')"
        )
    return study_id

# --------------------------------------------------------------------------
# Local layout
# --------------------------------------------------------------------------


def repo_root() -> Path:
    """Locate the moose_stack meta-repo root.

    Resolution order:
      1. ``$ANALYSIS_REPO_ROOT`` if set.
      2. Walk up from this file for a dir that contains ``analysis/`` and a
         ``moose/`` submodule (the meta-repo signature).
      3. Fall back to ``<this file>/../../..`` (analysis/tool/config.py ->
         repo root).
    """
    env = os.environ.get("ANALYSIS_REPO_ROOT")
    if env:
        return Path(env).expanduser().resolve()

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "analysis").is_dir() and (parent / "moose").exists():
            return parent
    # tool/config.py -> tool -> analysis -> repo
    return here.parents[2]


def analysis_dir() -> Path:
    return repo_root() / "analysis"


def vault_root() -> Optional[Path]:
    """The external analysis vault, if configured via ``$ANALYSIS_VAULT``.

    When set, study DATA (specs, cards, results, notes) and the board live in
    the vault — a personal knowledge hub separate from the code repo. The
    toolkit CODE (this package, SLURM templates) always stays in moose_stack.
    """
    v = os.environ.get("ANALYSIS_VAULT")
    return Path(v).expanduser().resolve() if v else None


def studies_dir() -> Path:
    v = vault_root()
    return (v / "studies") if v else (analysis_dir() / "studies")


def board_dir() -> Path:
    """Where the board / Home MOC is written (vault if configured)."""
    return vault_root() or analysis_dir()


def study_dir(study_id: str) -> Path:
    return studies_dir() / validate_study_id(study_id)


def slurm_template_dir() -> Path:
    return analysis_dir() / "tool" / "slurm"


# --------------------------------------------------------------------------
# Clusters
# --------------------------------------------------------------------------

# cluster name -> ssh host alias (must resolve via the user's ~/.ssh/config,
# which already carries ControlMaster settings for *.hpc.inl.gov).
CLUSTERS = {
    "bitterroot": "bitterroot1.hpc.inl.gov",
    "teton": "teton1.hpc.inl.gov",
}

DEFAULT_CLUSTER = "bitterroot"

# INL requires an accounting key on every batch job. The user's association
# is `intern` (verified via sacctmgr); overridable per study.
DEFAULT_ACCOUNT = "intern"

# Default SLURM partition for production runs (7-day walltime, default part).
DEFAULT_PARTITION = "general"

# Partition used for the cheap on-HPC fallbacks / build jobs (6h cap).
SHORT_PARTITION = "short"


def ssh_host(cluster: str) -> str:
    try:
        return CLUSTERS[cluster]
    except KeyError:
        raise ValueError(
            f"unknown cluster {cluster!r}; known: {', '.join(sorted(CLUSTERS))}"
        )


# --------------------------------------------------------------------------
# Remote layout (paths on HPC scratch; $USER expanded remotely at call time)
# --------------------------------------------------------------------------

# Root for all analysis runs on scratch. `{user}` is filled by remote.py once
# it has resolved the remote username (cached per host).
REMOTE_ANALYSIS_ROOT = "/scratch/{user}/analysis"

# Binary cache: keyed by (cluster, app, sha) so an arch mismatch between
# teton and bitterroot can never hand back the wrong `-opt`.
REMOTE_BINCACHE = "/scratch/{user}/analysis/.bincache/{cluster}/{app}/{sha}"

# Existing meta-repo checkout on scratch, used as the build source tree.
REMOTE_MOOSE_STACK = "/scratch/{user}/projects/moose_stack"


# --------------------------------------------------------------------------
# Applications
# --------------------------------------------------------------------------

# app name -> (submodule-relative build dir, produced binary name).
# Build dir is relative to the moose_stack checkout root.
APPS = {
    "moose": ("moose/test", "moose_test-opt"),
    "combined": ("moose/modules/combined", "combined-opt"),
    "blackbear": ("blackbear", "blackbear-opt"),
    "isopod": ("isopod", "isopod-opt"),
}


def app_build_dir(app: str) -> str:
    try:
        return APPS[app][0]
    except KeyError:
        raise ValueError(f"unknown app {app!r}; known: {', '.join(sorted(APPS))}")


def app_binary_name(app: str) -> str:
    return APPS[app][1]


# --------------------------------------------------------------------------
# Container / module environment on HPC
# --------------------------------------------------------------------------

# The versioner script that resolves the moose-dev container hash from source.
VERSIONER = "./moose/scripts/versioner.py"

# `moose-dev-exec` runs one command per rank inside the container (required
# for multi-host MPI). Prepended to the app invocation in batch scripts.
CONTAINER_EXEC = "moose-dev-exec"

# The module load incantation; `{hash}` filled from the versioner output.
MODULE_LOAD = "module load use.moose moose-dev-openmpi/{hash}"


# --------------------------------------------------------------------------
# Timeouts / retry policy defaults (overridable per study)
# --------------------------------------------------------------------------

SSH_CONNECT_TIMEOUT = 10          # seconds
MAX_TRANSIENT_RETRIES = 2         # tiered-failure: auto-resubmit ceiling
DEFAULT_MAX_CONCURRENT = 16       # SLURM array throttle (%N)
DEFAULT_NODES = 1
DEFAULT_NTASKS = 48               # bitterroot/teton standard node width
DEFAULT_WALLTIME = "02:00:00"     # per case, unless spec overrides
