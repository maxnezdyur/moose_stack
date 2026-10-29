#!/usr/bin/env bash
# Run the exact-PRP and penalty-PRP variants. Usage: run_all.sh [nprocs]
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
app="$here/../../moose/modules/combined/combined-opt"
np="${1:-4}"
cd "$here"
for f in exact penalty; do
  mpiexec -n "$np" "$app" -i two_block.i prp_formulation="$f" Outputs/file_base="two_block_$f" \
    > "two_block_$f.log" 2>&1 &
done
wait
grep -h "Finished Executing\|ERROR" two_block_*.log || true
