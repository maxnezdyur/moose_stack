#!/usr/bin/env bash
# build.sh — compile moose (test or combined), blackbear, isopod, or a
# single moose module from inside a named conda env, with opt or dbg METHOD.
#
# Usage:
#   build.sh <target> [opt|dbg] [--env <name>] [-j N] [-- <extra make args>]
#
# Targets (resolved against the meta-repo root):
#   moose-test                 -> moose/test
#   moose-combined             -> moose/modules/combined
#   blackbear                  -> blackbear
#   isopod                     -> isopod
#   <module>                   -> moose/modules/<module> if that dir has a Makefile
#   <path>                     -> any path containing a Makefile (relative to cwd or absolute)
#
# Defaults:
#   method  = opt
#   env     = moose
#   -j      = 4 (override with -j N)
#
# Nothing is hardcoded: the meta-repo root is discovered by walking up from
# this script, and the conda base is discovered from $CONDA_EXE / `conda info`.

set -euo pipefail

die() { printf 'build.sh: %s\n' "$*" >&2; exit 2; }

usage() {
  sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'
}

# --- locate meta-repo root (the dir that holds .clangd / .gitmodules) -------
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$script_dir
while [[ "$repo_root" != "/" ]]; do
  if [[ -f "$repo_root/.clangd" || -f "$repo_root/.gitmodules" ]]; then
    break
  fi
  repo_root=$(dirname -- "$repo_root")
done
[[ "$repo_root" == "/" ]] && die "could not find meta-repo root (no .clangd/.gitmodules above $script_dir)"

# --- parse args -------------------------------------------------------------
target=""
method="opt"
env_name="moose"
jobs=""
extra_make_args=()

while (( $# )); do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --env)     [[ $# -ge 2 ]] || die "--env needs a value"; env_name="$2"; shift 2 ;;
    --env=*)   env_name="${1#--env=}"; shift ;;
    -j)        [[ $# -ge 2 ]] || die "-j needs a value"; jobs="$2"; shift 2 ;;
    -j*)       jobs="${1#-j}"; shift ;;
    --)        shift; extra_make_args+=("$@"); break ;;
    opt|dbg|devel|oprof) method="$1"; shift ;;
    -*)        die "unknown flag: $1" ;;
    *)
      if [[ -z "$target" ]]; then target="$1"; shift
      else extra_make_args+=("$1"); shift
      fi
      ;;
  esac
done

[[ -n "$target" ]] || { usage; die "missing <target>"; }

# --- resolve target -> build dir -------------------------------------------
case "$target" in
  moose-test)     build_dir="$repo_root/moose/test" ;;
  moose-combined) build_dir="$repo_root/moose/modules/combined" ;;
  blackbear|isopod)
                  build_dir="$repo_root/$target" ;;
  /*)             build_dir="$target" ;;                       # absolute path
  */*)            build_dir="$(cd "$PWD" && cd "$target" 2>/dev/null && pwd)" \
                    || die "path not found: $target" ;;        # relative path
  *)
    # bare name — try as a moose module, then as a path under cwd
    if [[ -f "$repo_root/moose/modules/$target/Makefile" ]]; then
      build_dir="$repo_root/moose/modules/$target"
    elif [[ -f "$repo_root/$target/Makefile" ]]; then
      build_dir="$repo_root/$target"
    else
      die "unknown target '$target' (no Makefile at moose/modules/$target or $repo_root/$target)"
    fi
    ;;
esac

[[ -f "$build_dir/Makefile" ]] || die "no Makefile in $build_dir"

# --- resolve conda env ------------------------------------------------------
if [[ -n "${CONDA_EXE:-}" && -x "$CONDA_EXE" ]]; then
  conda_base=$(dirname -- "$(dirname -- "$CONDA_EXE")")
elif command -v conda >/dev/null 2>&1; then
  conda_base=$(conda info --base 2>/dev/null)
else
  die "conda not found (set CONDA_EXE or put conda on PATH)"
fi

env_prefix="$conda_base/envs/$env_name"
[[ -d "$env_prefix" ]] || die "conda env '$env_name' not found at $env_prefix"

# --- jobs -------------------------------------------------------------------
[[ -z "$jobs" ]] && jobs=4

# --- announce + exec --------------------------------------------------------
printf 'build.sh: target=%s method=%s env=%s -j%s\n' "$target" "$method" "$env_name" "$jobs" >&2
printf 'build.sh: dir=%s\n' "$build_dir" >&2

cd "$build_dir"
exec env \
  CONDA_PREFIX="$env_prefix" \
  CONDA_DEFAULT_ENV="$env_name" \
  PATH="$env_prefix/bin:$conda_base/condabin:$PATH" \
  METHOD="$method" \
  make -j "$jobs" ${extra_make_args[@]+"${extra_make_args[@]}"}
