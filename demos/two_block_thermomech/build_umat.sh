#!/usr/bin/env bash
# Compile the UMAT into the plugin name that AbaqusUMATStress loads (<plugin>-opt.plugin).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
src="${1:-$here/umat/two_block_umat.f}"
out="${src%.f}-opt.plugin"
"${FC:-mpif77}" -O2 -fPIC -shared -Wl,-undefined,dynamic_lookup "$src" -o "$out"
echo "built $out"
