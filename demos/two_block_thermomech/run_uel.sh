#!/usr/bin/env bash
# Run the UEL model and the small-strain UMAT model it is compared with. Usage: run_uel.sh [nprocs]
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
app="$here/../../moose/modules/combined/combined-opt"
np="${1:-4}"
cd "$here"
mpiexec -n "$np" "$app" -i two_block_uel.i Outputs/file_base=two_block_uel > two_block_uel.log 2>&1
mpiexec -n "$np" "$app" -i two_block.i Outputs/file_base=two_block_umat_small \
  Physics/SolidMechanics/QuasiStatic/all/strain=SMALL \
  Physics/SolidMechanics/QuasiStatic/all/incremental=true > two_block_umat_small.log 2>&1
grep -h "Finished Executing\|ERROR" two_block_uel.log two_block_umat_small.log || true
