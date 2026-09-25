#!/bin/bash
#SBATCH --job-name=campaign-build
#
# Build one app's -opt binary once and cache it, so a run can depend on it
# through `afterok`. Lifted from analysis/tool/slurm/build.sbatch. Static
# script; values arrive through `sbatch --export`:
#   MODULE        the container module, e.g. moose-dev-openmpi/<hash>
#   BUILD_DIR     absolute build dir in the pinned project checkout
#   MOOSE_DIR     absolute moose checkout the app builds against
#   BINARY_NAME   the produced binary, e.g. isopod-opt
#   CACHE_DIR     the (cluster, app, sha) cache dir the binary is copied into
set -euo pipefail

: "${MODULE:?need MODULE via --export}"
: "${BUILD_DIR:?need BUILD_DIR via --export}"
: "${MOOSE_DIR:?need MOOSE_DIR via --export}"
: "${BINARY_NAME:?need BINARY_NAME via --export}"
: "${CACHE_DIR:?need CACHE_DIR via --export}"

JOBS="${SLURM_NTASKS:-16}"
module purge
module load use.moose
module load "${MODULE}"
command -v moose-dev-exec >/dev/null || { echo "[build] moose-dev-exec absent after ${MODULE}" >&2; exit 1; }

echo "[build] host=$(hostname) dir=$BUILD_DIR jobs=$JOBS module=$MODULE"
moose-dev-exec bash -c "cd '$BUILD_DIR' && make -j ${JOBS} METHOD=opt MOOSE_DIR='$MOOSE_DIR'"

if [ ! -x "$BUILD_DIR/$BINARY_NAME" ]; then
  echo "[build] ERROR: $BINARY_NAME not produced in $BUILD_DIR" >&2
  exit 1
fi

mkdir -p "$CACHE_DIR"
cp -f "$BUILD_DIR/$BINARY_NAME" "$CACHE_DIR/"
echo "[build] cached -> $CACHE_DIR/$BINARY_NAME"
