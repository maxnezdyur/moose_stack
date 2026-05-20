#!/bin/bash
# Multi-node MOOSE job template for INL HPC (sawtooth / lemhi / bitterroot / hoodoo / teton).
#
# Usage:
#   1. Build the app once on the login node (see scripts/build-opt.sh).
#   2. Resolve the container hash:
#        module load use.moose versioner
#        <moose-dir>/scripts/versioner.py moose-dev
#      Set MOOSE_DEV_VERSION below (or export it before sbatch).
#   3. Submit:
#        sbatch --export=ALL,APP_PATH=./blackbear-opt,INPUT=in.i scripts/moose-job.sbatch
#      or copy this file alongside your input and edit the defaults inline.

#SBATCH --job-name=moose-run
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=48          # sawtooth/lemhi compute nodes are 48-core; check `sinfo` for your target
#SBATCH --time=04:00:00
#SBATCH --output=%x.%j.out
#SBATCH --error=%x.%j.err
#SBATCH --wckey=neams                  # INL requires --wckey; override via `sbatch --wckey=<other>`
# #SBATCH --partition=<partition>      # leave commented to use the default
# #SBATCH --qos=<qos>                  # uncomment if your account needs an explicit QoS
# #SBATCH --mail-type=END,FAIL
# #SBATCH --mail-user=max.nezdyur@inl.gov

set -euo pipefail

# ---- container version (must match the moose tree this binary was built from) ----
MOOSE_DEV_VERSION="${MOOSE_DEV_VERSION:-REPLACE_ME}"

# ---- app + input (override via --export=ALL,APP_PATH=...,INPUT=...) ----
APP_PATH="${APP_PATH:-./blackbear-opt}"    # ./isopod-opt | ./moose-opt | <abs path>
INPUT="${INPUT:?set INPUT=path/to/input.i}"

# ---- env ----
module purge
module load use.moose "moose-dev-openmpi/${MOOSE_DEV_VERSION}"

cd "$SLURM_SUBMIT_DIR"

echo "[job] host=$(hostname) nodes=$SLURM_NNODES ntasks=$SLURM_NTASKS"
echo "[job] container=moose-dev-openmpi/${MOOSE_DEV_VERSION}"
echo "[job] app=${APP_PATH} input=${INPUT}"
echo "[job] started $(date -Iseconds)"

# moose-dev-exec runs each rank inside the container (required for multi-host).
# Always pass -n to mpiexec — OpenMPI in this container needs it explicitly.
mpiexec -n "$SLURM_NTASKS" moose-dev-exec "$APP_PATH" -i "$INPUT"

echo "[job] finished $(date -Iseconds)"
