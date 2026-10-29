#!/usr/bin/env bash
# Run the demo. Usage: run_all.sh [nprocs]
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
app="$here/../../moose/modules/combined/combined-opt"
cd "$here"
mpiexec -n "${1:-4}" "$app" -i two_block.i Outputs/file_base=two_block_exact > two_block_exact.log 2>&1
grep -h "Finished Executing\|ERROR" two_block_exact.log || true
