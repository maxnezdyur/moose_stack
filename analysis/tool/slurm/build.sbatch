#!/bin/bash
#SBATCH --job-name=analysis-build
#
# Build one app's -opt binary once and cache it, so a study's cases can depend
# on it via `afterok`. Static script; values arrive via `sbatch --export`:
#   MOOSE_HASH    container module hash (from versioner)
#   BUILD_DIR     absolute build dir in the scratch checkout (e.g. .../blackbear)
#   BINARY_NAME   produced binary (e.g. blackbear-opt)
#   CACHE_DIR     absolute (cluster,app,sha)-keyed cache dir to copy the binary into
set -euo pipefail

: "${MOOSE_HASH:?need MOOSE_HASH via --export}"
: "${BUILD_DIR:?need BUILD_DIR via --export}"
: "${BINARY_NAME:?need BINARY_NAME via --export}"
: "${CACHE_DIR:?need CACHE_DIR via --export}"

JOBS="${SLURM_NTASKS:-16}"
module purge
module load use.moose "moose-dev-openmpi/${MOOSE_HASH}"

echo "[build] host=$(hostname) dir=$BUILD_DIR jobs=$JOBS"
moose-dev-exec bash -c "cd '$BUILD_DIR' && make -j ${JOBS} METHOD=opt"

if [ ! -x "$BUILD_DIR/$BINARY_NAME" ]; then
  echo "[build] ERROR: $BINARY_NAME not produced in $BUILD_DIR" >&2
  exit 1
fi

mkdir -p "$CACHE_DIR"
cp -f "$BUILD_DIR/$BINARY_NAME" "$CACHE_DIR/"
echo "[build] cached -> $CACHE_DIR/$BINARY_NAME"
