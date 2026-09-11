#!/usr/bin/env bash
# Look up the registered parameters of exact MOOSE object type names by asking
# a built app binary. Never a cache: the answer always matches the checkout.
#
# Usage:
#   moose-params.sh <binary> <Type>... [--param <name> | --full]
#
#   <binary>   path to a built app (absolute, or relative to the cwd or the
#              meta-root), e.g. moose/modules/combined/combined-opt,
#              moose/test/moose_test-opt, blackbear/blackbear-opt,
#              isopod/isopod-opt. Use -opt first, -devel if that is what is built.
#   <Type>     exact registered type name (ADDirichletBC). One or more.
#   --param    print only .parameters["<name>"] of each type.
#   --full     print the complete JSON node of each type.
#   (default)  print a lean summary per type: name, syntax paths, class
#              description, required params, optional params with defaults.
#
# Output: one JSON document per type on stdout, in argument order. A type the
# app does not register prints the line "NO_NODE: <Type>" instead; a missing
# parameter under --param prints "NO_PARAM: <Type>.<name>".
# Exit 0 when every type (and parameter) was found, 1 when any was absent,
# 2 on usage errors or when the app did not produce a JSON payload
# ("APP_FAILED: ..." on stderr, with the app's stderr and stdout tail).
#
# Why --json and not --json-search: --json-search takes exactly one pattern
# (MooseUtils::wildCardMatch, case-insensitive, `*` wildcard only) and matches
# it against syntax paths, action names, parent paths and parameter names, so
# it cannot serve several types in one boot and can pull in unrelated blocks
# when a type name collides with some parameter name. The boot itself (15-30 s,
# building the whole syntax tree) costs the same either way; only the dump size
# differs (about 65 MB for combined-opt), and jq reads that in a second or two.
# The exact-leaf-key selection below is what makes the match exact: no
# substring retry, no near-miss suggestions, so a caller can trust NO_NODE.

set -u

usage() {
  echo "usage: moose-params.sh <binary> <Type>... [--param <name> | --full]" >&2
  exit 2
}

# --- meta-root: $CLAUDE_PROJECT_DIR, else walk up from $PWD to .clangd -------
if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
  root="$CLAUDE_PROJECT_DIR"
else
  root="$PWD"
  while [[ "$root" != "/" && ! -f "$root/.clangd" ]]; do
    root="$(dirname "$root")"
  done
  if [[ ! -f "$root/.clangd" ]]; then
    echo "APP_FAILED: no .clangd found walking up from $PWD (not inside a moose_stack worktree?)" >&2
    exit 2
  fi
fi

# --- arguments ---------------------------------------------------------------
binary=""
types=()
mode="lean"
param=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --param)
      [[ $# -ge 2 && "$mode" == "lean" ]] || usage
      mode="param"; param="$2"; shift 2 ;;
    --full)
      [[ "$mode" == "lean" ]] || usage
      mode="full"; shift ;;
    -h|--help) usage ;;
    -*) usage ;;
    *)
      if [[ -z "$binary" ]]; then binary="$1"; else types+=("$1"); fi
      shift ;;
  esac
done
[[ -n "$binary" && ${#types[@]} -gt 0 ]] || usage

# Resolve the binary: as given (absolute or cwd-relative), else meta-root-relative.
if [[ ! -x "$binary" && -x "$root/$binary" ]]; then
  binary="$root/$binary"
fi
if [[ ! -x "$binary" || -d "$binary" ]]; then
  echo "APP_FAILED: $binary is not an executable file (app not built, or wrong path?)" >&2
  exit 2
fi
binary="$(cd "$(dirname "$binary")" && pwd)/$(basename "$binary")"

# --- boot the app once -------------------------------------------------------
tmp="$(mktemp -d "${TMPDIR:-/tmp}/moose-params.XXXXXX")" || exit 2
trap 'rm -rf "$tmp"' EXIT

# INL HPC hostnames have no conda: the user is already inside the container,
# so run the bare binary. Everywhere else, conda-run.sh activates the pinned env
# (a moose binary links against the env's libmesh/petsc, so it will not start
# without it) and fails with a clear message when the env is missing.
# The subshell keeps bash's own "Abort trap: 6" line (printed when the app dies
# on a signal, e.g. a dyld mismatch) in $tmp/err with the rest of the diagnostics.
(
  case "$(hostname)" in
    sawtooth*|lemhi*|bitterroot*|hoodoo*|teton*)
      "$binary" --json ;;
    *)
      bash "$root/scripts/conda-run.sh" -C "$(dirname "$binary")" -- "$binary" --json ;;
  esac
) >"$tmp/out" 2>"$tmp/err"
app_rc=$?

# Deprecation warnings and stack traces go to stdout, interleaved with the
# payload, so only the slice between the markers is JSON. 2>/dev/null alone
# would not make the output parseable.
awk '/\*\*START JSON DATA\*\*/{f=1;next} /\*\*END JSON DATA\*\*/{f=0} f' "$tmp/out" >"$tmp/json"

# No payload means the app never started (dyld mismatch after a moose bump,
# missing conda env, unbuilt app). It says nothing about whether the type exists.
if [[ ! -s "$tmp/json" ]] || ! jq -e 'type == "object"' "$tmp/json" >/dev/null 2>&1; then
  echo "APP_FAILED: $binary --json produced no JSON payload (exit $app_rc)" >&2
  echo "--- stderr (last 40 lines) ---" >&2
  tail -n 40 "$tmp/err" >&2
  echo "--- stdout (last 40 lines) ---" >&2
  tail -n 40 "$tmp/out" >&2
  exit 2
fi

# --- select each type --------------------------------------------------------
# A type lives at ...<System>/star/subblock_types/<Type> (block syntax such as
# BCs/*) or ...<System>/types/<Type> (type= syntax such as Executioner or Mesh),
# at any depth (Modules/.../Master/star/...). Many types are registered under
# more than one path (TimeStepper/types and TimeSteppers/star/subblock_types),
# so collect every node in document order; the lean view reports all syntax
# paths and --full/--param print the first node.
select_filter='
  [ .. | objects
    | (.subblock_types? // {}), (.types? // {})
    | select(type == "object" and has($t))
    | .[$t] ]'

lean_filter='
  def slim: {cpp_type}
    + (if .options != "" then {options} else {} end)
    + (if has("default") then {default} else {} end)
    + {description};
  {
    type: $t,
    syntax_paths: [ .[] | .syntax_path ],
    moose_base: .[0].moose_base,
    description: .[0].description,
    register_file: .[0].register_file,
    required: (.[0].parameters | with_entries(select(.value.required and (.value.deprecated | not)))
                                | map_values(slim)),
    optional: (.[0].parameters | with_entries(select((.value.required | not) and (.value.deprecated | not)))
                                | map_values(slim)),
    deprecated: [ .[0].parameters[] | select(.deprecated) | .name ]
  }'

status=0
for t in "${types[@]}"; do
  jq --arg t "$t" "$select_filter" "$tmp/json" >"$tmp/nodes"
  if [[ "$(jq 'length' "$tmp/nodes")" == "0" ]]; then
    echo "NO_NODE: $t"
    status=1
    continue
  fi
  case "$mode" in
    full)
      jq '.[0]' "$tmp/nodes" ;;
    param)
      if [[ "$(jq --arg p "$param" '.[0].parameters | has($p)' "$tmp/nodes")" != "true" ]]; then
        echo "NO_PARAM: $t.$param"
        status=1
        continue
      fi
      jq --arg p "$param" '.[0].parameters[$p]' "$tmp/nodes" ;;
    lean)
      jq --arg t "$t" "$lean_filter" "$tmp/nodes" ;;
  esac
done
exit $status
