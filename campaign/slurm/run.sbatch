#!/bin/bash
#SBATCH --job-name=campaign-run
#
# One run of a campaign: one job, not an array. tool/dispatch.py renders this
# file per run, replacing every {{KEY}} below, and uploads it next to the
# run's frozen inputs as <scratch>/<campaign>/<run>/run.sbatch. The resources
# (partition, ntasks, walltime, account, wckey, dependency) arrive as sbatch
# arguments, and --output points at run.log beside it.
#
#   {{RUN}}        the run id and campaign, for the log
#   {{MODULE}}     the container module
#   {{WORKDIR}}    <run dir>/<cwd>, where the command runs
#   {{ENV}}        one `export KEY=value` line per manifest env entry
#   {{COMMAND}}    the manifest command, its binary replaced by
#                  `moose-dev-exec <cached binary>`
set -uo pipefail

module purge
module load use.moose
module load "{{MODULE}}"
command -v moose-dev-exec >/dev/null || { echo "[run] moose-dev-exec absent after {{MODULE}}" >&2; exit 1; }

{{ENV}}

cd "{{WORKDIR}}" || { echo "[run] no workdir {{WORKDIR}}" >&2; exit 1; }
echo "[run] {{RUN}} host=$(hostname) job=${SLURM_JOB_ID:-} ntasks=${SLURM_NTASKS:-1}"
echo "[run] started $(date -u +%Y-%m-%dT%H:%M:%SZ)"

{{COMMAND}}
code=$?

echo "[run] finished $(date -u +%Y-%m-%dT%H:%M:%SZ) exit=$code"
exit "$code"
