#!/usr/bin/env bash
# Compile a UMAT or UEL (.f fixed form or .f90 free form) into the plugin name that
# AbaqusUMATStress / AbaqusUserElement load (<plugin>-opt.plugin).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
src="${1:-$here/umat/two_block_umat.f}"
out="${src%.*}-opt.plugin"
flags=(-O2 -fPIC -shared -Wl,-undefined,dynamic_lookup)
[[ "$src" == *.f90 ]] && flags+=(-ffree-line-length-none)
"${FC:-mpif90}" "${flags[@]}" "$src" -o "$out"
echo "built $out"
