#!/bin/bash
#SBATCH --job-name=analysis-case
#
# One case of a MOOSE analysis study (a single SLURM array task).
#
# Static script: all study-specific values arrive via `sbatch --export`:
#   MOOSE_HASH  container module hash (from versioner)
#   BINARY      absolute path to the cached -opt binary
#   INPUT       absolute path to the baseline .i input
# SLURM provides SLURM_ARRAY_TASK_ID and SLURM_NTASKS; --chdir sets cwd to the
# study workdir, which contains cases.tsv (one line per case: "idx<TAB>overrides").
set -euo pipefail

: "${MOOSE_HASH:?need MOOSE_HASH via --export}"
: "${BINARY:?need BINARY via --export}"
: "${INPUT:?need INPUT via --export}"

module purge
module load use.moose "moose-dev-openmpi/${MOOSE_HASH}"

idx="${SLURM_ARRAY_TASK_ID:-0}"
line="$(sed -n "$((idx + 1))p" cases.tsv)"
overrides="$(printf '%s' "$line" | cut -f2-)"

casedir="$(printf 'case_%04d' "$idx")"
mkdir -p "$casedir"
cd "$casedir"

echo "[case $idx] host=$(hostname) ntasks=${SLURM_NTASKS:-1}"
echo "[case $idx] overrides: $overrides"

# Word-splitting of $overrides is intentional (each token is a HIT override).
# shellcheck disable=SC2086
mpiexec -n "${SLURM_NTASKS:-1}" moose-dev-exec "$BINARY" -i "$INPUT" $overrides

echo "[case $idx] done"
