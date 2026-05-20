#!/bin/bash
#SBATCH --job-name=moose-build
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --ntasks=32
#SBATCH --time=02:00:00
#SBATCH --wckey=neams
#SBATCH --output=%x.%j.out
#SBATCH --error=%x.%j.err
#
# Build -opt binaries for moose's combined module app, blackbear, and isopod.
#
# Primary use (one-shot, async, queue):
#   sbatch scripts/build-opt.sbatch                # defaults above: short partition, 32 ranks, 2h
#
# Override on the command line:
#   sbatch --ntasks=48 --time=04:00:00 scripts/build-opt.sbatch
#   sbatch --wckey=<other> scripts/build-opt.sbatch
#
# Watch progress:
#   squeue --me
#   tail -f moose-build.<jobid>.out
#
# Interactive fallback (already inside moose-dev-shell on a compute node):
#   ./scripts/build-opt.sbatch                     # uses $(nproc) by default
#
# Override the make job count regardless of mode:
#   JOBS=64 sbatch scripts/build-opt.sbatch

set -euo pipefail

# --- Resolve meta-repo root ---
# Under sbatch, $0 is /var/spool/slurmd/job<id>/slurm_script (a SLURM-side copy
# that the moose-dev container can't see), so $0-based self-location fails.
# Walk upward from $MOOSE_STACK_ROOT (explicit), $SLURM_SUBMIT_DIR (sbatch cwd),
# or $PWD looking for moose/scripts/versioner.py.
resolve_stack() {
  local d
  d="${MOOSE_STACK_ROOT:-${SLURM_SUBMIT_DIR:-$PWD}}"
  d="$(cd "$d" && pwd -P)" || return 1
  while [ "$d" != "/" ]; do
    [ -x "$d/moose/scripts/versioner.py" ] && { echo "$d"; return 0; }
    d="$(dirname "$d")"
  done
  return 1
}

if ! STACK="$(resolve_stack)"; then
  echo "[bootstrap] ERROR: cannot locate meta-repo root (no moose/scripts/versioner.py above ${SLURM_SUBMIT_DIR:-$PWD})" >&2
  echo "[bootstrap] Submit from anywhere inside moose_stack, or set MOOSE_STACK_ROOT=/path/to/moose_stack via --export" >&2
  exit 1
fi
export MOOSE_STACK_ROOT="$STACK"

# --- Bootstrap into the container when running under sbatch ---
# An sbatch job lands on a compute node but outside the container. Load the
# matching moose-dev-openmpi module from the moose tree's versioner hash, then
# re-exec this same script inside the container via moose-dev-exec — but via
# the real path under $STACK (which is bind-mounted into the container), NOT
# via $0 (the SLURM spool path is not mounted).
if [ -n "${SLURM_JOB_ID:-}" ] && [ -z "${MOOSE_DEV_BUILD_BOOTED:-}" ]; then
  echo "[bootstrap] host=$(hostname) job=$SLURM_JOB_ID partition=${SLURM_JOB_PARTITION:-?} stack=$STACK"
  module purge
  module load use.moose versioner
  HASH=$("${STACK}/moose/scripts/versioner.py" moose-dev)
  echo "[bootstrap] versioner hash: $HASH"
  module load use.moose "moose-dev-openmpi/${HASH}"
  export MOOSE_DEV_BUILD_BOOTED=1
  cd "$STACK"
  exec moose-dev-exec bash "${STACK}/scripts/build-opt.sbatch" "$@"
fi

# --- Inside the container (either bootstrapped or via moose-dev-shell) ---
JOBS="${JOBS:-${SLURM_NTASKS:-$(nproc)}}"
export METHOD=opt

echo "[build] host=$(hostname) jobs=$JOBS method=$METHOD"

build() {
  local name="$1" dir="$2" expect="$3"
  echo "=== [$name] make -j $JOBS METHOD=opt in $dir ==="
  ( cd "$dir" && make -j "$JOBS" )
  if [ -x "$dir/$expect" ]; then
    echo "[$name] OK: $dir/$expect"
  else
    echo "[$name] MISSING $expect" >&2
    exit 1
  fi
}

# moose framework + all modules first (combined-opt); blackbear and isopod link against it.
build combined  "$STACK/moose/modules/combined" combined-opt
build blackbear "$STACK/blackbear"              blackbear-opt
build isopod    "$STACK/isopod"                 isopod-opt

echo "=== all builds OK ==="
