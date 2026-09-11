#!/usr/bin/env bash
# docs.sh - serve, stop, or smoke-test one MooseDocs site of the moose_stack meta-repo.
#
# Usage:
#   docs.sh <scope> serve            start (or restart) a background preview server
#   docs.sh <scope> stop             stop the server started by "serve"
#   docs.sh <scope> smoke [--diff <base>]
#                                    full build + serve + HTTP probe; PASS/FAIL/BLOCKED
#
#   <scope> = moose | blackbear | isopod | moose/modules/<m>
#
# Env:
#   SMOKE_TIMEOUT  seconds to wait for the smoke server to bind (default 600)
#   METHOD         build method suffix of the app binary (default opt)
#
# Exit codes: 0 = pass/started, 1 = fail, 2 = blocked (env, binary) or usage.
#
# Log and pid files: /tmp/moose-docs-<tag>-serve.{pid,log}, /tmp/moose-docs-<tag>-smoke.log,
# where <tag> is the scope with "/" replaced by "-".

set -u

usage() {
  echo "Usage: $0 <moose|blackbear|isopod|moose/modules/<m>> <serve|stop|smoke> [--diff <base>]" >&2
  exit 2
}

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
[[ $# -ge 2 ]] || usage
SCOPE="$1"
ACTION="$2"
shift 2
DIFF_BASE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --diff)
      [[ $# -ge 2 ]] || usage
      DIFF_BASE="$2"; shift 2 ;;
    *) usage ;;
  esac
done
case "$ACTION" in
  serve|stop|smoke) ;;
  *) usage ;;
esac
# --diff only means something for smoke; anywhere else it is a usage error.
[[ -z "$DIFF_BASE" || "$ACTION" == "smoke" ]] || usage

# ---------------------------------------------------------------------------
# Meta-root: $CLAUDE_PROJECT_DIR, else walk up from $PWD to the first .clangd.
# Every worktree of moose_stack carries .clangd at its root, so this works from
# ~/projects/moose-worktrees/<feature>/ as well as the canonical checkout.
# ---------------------------------------------------------------------------
META_ROOT="${CLAUDE_PROJECT_DIR:-}"
if [[ -z "$META_ROOT" ]]; then
  d="$PWD"
  while [[ "$d" != "/" ]]; do
    if [[ -f "$d/.clangd" ]]; then META_ROOT="$d"; break; fi
    d="$(dirname "$d")"
  done
fi
[[ -n "$META_ROOT" && -f "$META_ROOT/.clangd" ]] \
  || { echo "BLOCKED: not inside a moose_stack worktree (no .clangd found)" >&2; exit 2; }

# ---------------------------------------------------------------------------
# Scope table. REPO_DIR is the git repo the scope lives in (drives --diff and
# ${ROOT_DIR}); DOC_DIR holds moosedocs.py and config.yml.
# ---------------------------------------------------------------------------
case "$SCOPE" in
  moose)
    REPO_DIR="$META_ROOT/moose"
    DOC_DIR="$META_ROOT/moose/modules/doc" ;;
  blackbear|isopod)
    REPO_DIR="$META_ROOT/$SCOPE"
    DOC_DIR="$REPO_DIR/doc" ;;
  moose/modules/*)
    MODULE="${SCOPE#moose/modules/}"
    [[ -n "$MODULE" && "$MODULE" != */* ]] || usage
    REPO_DIR="$META_ROOT/moose"
    DOC_DIR="$META_ROOT/moose/modules/$MODULE/doc"
    [[ -f "$DOC_DIR/config.yml" ]] \
      || { echo "BLOCKED: no doc config for module '$MODULE' ($DOC_DIR/config.yml)" >&2; exit 2; } ;;
  *) usage ;;
esac
TAG="$(printf '%s' "$SCOPE" | tr '/' '-')"

# moosedocs.py honors a pre-set MOOSE_DIR, and the env probe below imports
# MooseDocs from $MOOSE_DIR/python. Export both unconditionally so the same
# checkout's MooseDocs is used from any worktree.
export MOOSE_DIR="$META_ROOT/moose"
export PYTHONPATH="$MOOSE_DIR/python${PYTHONPATH:+:$PYTHONPATH}"

# ---------------------------------------------------------------------------
# Environment routing. INL HPC hosts have no conda: the user is already inside
# the container, so run commands bare. Elsewhere go through conda-run.sh, which
# resolves the worktree's pinned env and fails clearly when it is missing.
# ---------------------------------------------------------------------------
ON_HPC=0
case "$(hostname)" in
  sawtooth*|lemhi*|bitterroot*|hoodoo*|teton*) ON_HPC=1 ;;
esac
CONDA_RUN="$META_ROOT/scripts/conda-run.sh"
run_in_env() {
  if [[ "$ON_HPC" == 1 ]]; then
    "$@"
  else
    bash "$CONDA_RUN" -C "$DOC_DIR" -- "$@"
  fi
}

PID_FILE="/tmp/moose-docs-$TAG-serve.pid"
SERVE_LOG="/tmp/moose-docs-$TAG-serve.log"
SMOKE_LOG="/tmp/moose-docs-$TAG-smoke.log"

kill_pid() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null || return 0
  kill "$pid" 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 1
  done
  kill -9 "$pid" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# stop: needs neither the env nor the binary.
# ---------------------------------------------------------------------------
if [[ "$ACTION" == "stop" ]]; then
  if [[ -f "$PID_FILE" ]]; then
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      kill_pid "$pid"
      echo "stopped: $SCOPE (pid $pid)"
    else
      echo "no running server for $SCOPE (stale pid file removed)"
    fi
    rm -f "$PID_FILE"
  else
    echo "no running server for $SCOPE"
  fi
  exit 0
fi

# ---------------------------------------------------------------------------
# Env probe: a full build needs pyyaml and MooseDocs importable. Importing
# MooseDocs needs a git repo as the working directory (it derives ROOT_DIR
# from it), so probe from the doc dir, not from wherever the caller sits.
# ---------------------------------------------------------------------------
cd "$DOC_DIR" || { echo "BLOCKED: cannot cd to $DOC_DIR" >&2; exit 2; }
PROBE_OUT="$(run_in_env python3 -c "import yaml, MooseDocs" 2>&1)" || {
  echo "BLOCKED: $SCOPE MooseDocs Python deps missing (yaml, MooseDocs)."
  if [[ "$ON_HPC" == 1 ]]; then
    echo "  hint: run inside the container module that provides moose-dev python, then retry."
  else
    echo "  hint: conda-run.sh could not provide the env; see docs/local.md."
  fi
  printf '%s\n' "$PROBE_OUT" | tail -3 | sed 's/^/  /'
  exit 2
}

# ---------------------------------------------------------------------------
# Executable. MooseDocs reads the "executable:" directory from config.yml and
# resolves <APPLICATION_NAME>-<METHOD> inside it (name from the Makefile, else
# the directory basename; "test" maps to "moose_test"). Mirror that here so the
# precheck tests the binary the build will use: combined -> modules/combined/
# combined-opt, app -> <app>-opt, module -> modules/<m>/<m>-opt. Without METHOD
# MooseDocs tries opt, oprof, dbg, devel in order; this precheck assumes opt.
# ---------------------------------------------------------------------------
METHOD_SUFFIX="${METHOD:-opt}"
resolve_exe() {
  # $1 = doc dir; prints the expected binary path, or nothing when the config
  # has no executable line.
  local cfg="$1/config.yml" line exe_dir name
  line="$(grep -E '^[[:space:]]*executable:' "$cfg" | head -1 | sed -E 's/^[[:space:]]*executable:[[:space:]]*//; s/[[:space:]]*$//')"
  [[ -n "$line" ]] || return 0
  exe_dir="${line//\$\{MOOSE_DIR\}/$MOOSE_DIR}"
  exe_dir="${exe_dir//\$\{ROOT_DIR\}/$REPO_DIR}"
  name=""
  if [[ -f "$exe_dir/Makefile" ]]; then
    name="$(sed -n -E 's/^APPLICATION_NAME[[:space:]]*:?=[[:space:]]*([^[:space:]]+).*$/\1/p' "$exe_dir/Makefile" | tail -1)"
  fi
  [[ -n "$name" ]] || name="$(basename "$exe_dir")"
  [[ "$name" == "test" ]] && name="moose_test"
  printf '%s\n' "$exe_dir/$name-$METHOD_SUFFIX"
}

BIN="$(resolve_exe "$DOC_DIR")"
FALLBACK_NOTE=""
if [[ -n "$BIN" && ! -x "$BIN" ]]; then
  # The combined binary is a multi-hour build. A feature worktree usually has
  # only one module binary, and that module's doc config points at it; fall
  # back to the newest module binary so the site can still be checked.
  if [[ "$SCOPE" == "moose" ]]; then
    for cand in $(ls -t "$META_ROOT"/moose/modules/*/*-"$METHOD_SUFFIX" 2>/dev/null); do
      m="$(basename "$(dirname "$cand")")"
      [[ "$m" == "combined" || "$m" == "doc" ]] && continue
      [[ -x "$cand" && -f "$META_ROOT/moose/modules/$m/doc/config.yml" ]] || continue
      FALLBACK_NOTE="note: $BIN missing; using module scope moose/modules/$m ($cand)"
      SCOPE="moose/modules/$m"
      DOC_DIR="$META_ROOT/moose/modules/$m/doc"
      BIN="$cand"
      break
    done
  fi
  if [[ ! -x "$BIN" ]]; then
    echo "BLOCKED: $SCOPE binary missing: $BIN"
    echo "  hint: build it first: make -C $(dirname "$BIN") -j"
    exit 2
  fi
fi
[[ -n "$FALLBACK_NOTE" ]] && echo "$FALLBACK_NOTE"

find_free_port() {
  local p=8000
  while [[ $p -lt 8100 ]]; do
    if ! (echo > /dev/tcp/127.0.0.1/$p) >/dev/null 2>&1; then
      echo "$p"; return 0
    fi
    p=$((p+1))
  done
  return 1
}

# ---------------------------------------------------------------------------
# serve: long-running background server, pid file, restart on re-invoke.
# ---------------------------------------------------------------------------
if [[ "$ACTION" == "serve" ]]; then
  if [[ -f "$PID_FILE" ]]; then
    old_pid="$(cat "$PID_FILE")"
    if kill -0 "$old_pid" 2>/dev/null; then
      echo "restarting: killing existing $SCOPE server (pid $old_pid)"
      kill_pid "$old_pid"
    fi
    rm -f "$PID_FILE"
  fi
  PORT="$(find_free_port)" || { echo "FAIL: no free port in 8000-8099" >&2; exit 1; }

  cd "$DOC_DIR" || exit 1
  : >"$SERVE_LOG"
  # conda-run.sh execs the command, so $! is the moosedocs process itself.
  if [[ "$ON_HPC" == 1 ]]; then
    nohup ./moosedocs.py build --serve --port "$PORT" >"$SERVE_LOG" 2>&1 </dev/null &
  else
    nohup bash "$CONDA_RUN" -C "$DOC_DIR" -- ./moosedocs.py build --serve --port "$PORT" >"$SERVE_LOG" 2>&1 </dev/null &
  fi
  PID=$!
  disown "$PID" 2>/dev/null || true
  echo "$PID" > "$PID_FILE"

  # Brief settle so an immediate crash is visible.
  sleep 2
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "FAIL: $SCOPE server exited at start. Last 40 log lines:" >&2
    tail -40 "$SERVE_LOG" >&2
    rm -f "$PID_FILE"
    exit 1
  fi

  cat <<MSG
serving $SCOPE docs:
  url:  http://localhost:$PORT
  pid:  $PID
  log:  $SERVE_LOG
  stop: bash $0 $SCOPE stop

Note: full build (no --fast); moosedocs is still building. Pages are incomplete
until the build finishes. Watch '$SERVE_LOG' for progress.
MSG
  exit 0
fi

# ---------------------------------------------------------------------------
# smoke: full build + serve + HTTP probe.
# Pass = server binds, HTTP 200, zero ERROR/CRITICAL/Traceback lines in the log.
# ---------------------------------------------------------------------------
TIMEOUT_SEC="${SMOKE_TIMEOUT:-600}"

# --diff: the set of files this branch touches in the scope's repo, relative to
# the repo root. Working tree vs merge-base catches committed, staged, and
# unstaged edits without pulling in upstream commits the branch lacks; the
# untracked list covers new pages and inputs that were never staged.
DIFF_LIST=""
if [[ -n "$DIFF_BASE" ]]; then
  mb="$(git -C "$REPO_DIR" merge-base "$DIFF_BASE" HEAD 2>/dev/null)" \
    || { echo "BLOCKED: $SCOPE --diff base '$DIFF_BASE' does not resolve in $REPO_DIR"; exit 2; }
  DIFF_LIST="/tmp/moose-docs-$TAG-smoke.diff-files"
  {
    git -C "$REPO_DIR" diff --name-only "$mb"
    git -C "$REPO_DIR" ls-files --others --exclude-standard
  } | sort -u > "$DIFF_LIST"
fi

PORT="$(find_free_port)" || { echo "FAIL: no free port in 8000-8099" >&2; exit 1; }
cd "$DOC_DIR" || exit 1
START="$(date +%s)"
: >"$SMOKE_LOG"

# Launch the same way serve does, not through run_in_env: a backgrounded shell
# function makes $! the function's subshell, and conda-run.sh execs moosedocs
# inside it, so killing $! would orphan the real server (re-parented to pid 1,
# still building and holding the port). Launched directly, $! is moosedocs.
if [[ "$ON_HPC" == 1 ]]; then
  ./moosedocs.py build --serve --port "$PORT" >"$SMOKE_LOG" 2>&1 </dev/null &
else
  bash "$CONDA_RUN" -C "$DOC_DIR" -- ./moosedocs.py build --serve --port "$PORT" >"$SMOKE_LOG" 2>&1 </dev/null &
fi
PID=$!

cleanup() {
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
    for _ in 1 2 3 4 5; do
      kill -0 "$PID" 2>/dev/null || break
      sleep 1
    done
    kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null
  fi
}
trap cleanup EXIT

# Poll the port until it accepts, the process exits, or the deadline passes.
DEADLINE=$(( $(date +%s) + TIMEOUT_SEC ))
while :; do
  if (echo > /dev/tcp/127.0.0.1/$PORT) >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    # A missing executable is an env problem, not a doc problem, even here.
    if grep -q "Failed to locate a valid executable" "$SMOKE_LOG"; then
      echo "BLOCKED: $SCOPE docs: MooseDocs could not locate a valid executable ($BIN)"
      echo "  log: $SMOKE_LOG"
      exit 2
    fi
    echo "FAIL: $SCOPE docs: moosedocs exited before serving."
    echo "  log: $SMOKE_LOG"
    echo "  --- last 15 lines ---"
    tail -15 "$SMOKE_LOG"
    exit 1
  fi
  if (( $(date +%s) >= DEADLINE )); then
    echo "FAIL: $SCOPE docs: timeout (${TIMEOUT_SEC}s) waiting for port $PORT to bind."
    echo "  log: $SMOKE_LOG"
    exit 1
  fi
  sleep 2
done

# HTTP probe.
HTTP_CODE="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 30 "http://localhost:$PORT/" 2>/dev/null || true)"
if [[ "$HTTP_CODE" != "200" ]]; then
  HTTP_CODE="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 30 "http://localhost:$PORT/index.html" 2>/dev/null || true)"
fi

# Error scan. MooseDocs writes ANSI color codes to the log even when it is not
# a tty, so strip them first. Each report_error record is "ERROR: <msg>" on
# one line and "<file>[:line]" on the next; the file line is appended in
# brackets so one output line carries the location. The "CRITICAL:n ERROR:n"
# summary printed at exit is not an error record. With --diff a record is kept
# only when its two lines mention a file from the diff list; the location line
# is an absolute path, so a repo-relative diff path matches as a substring.
ESC="$(printf '\033')"
ERR_LINES="$(sed "s/${ESC}\[[0-9;]*m//g" "$SMOKE_LOG" | awk -v listfile="${DIFF_LIST:-}" '
  BEGIN {
    n = 0
    if (listfile != "") while ((getline l < listfile) > 0) if (l != "") paths[n++] = l
  }
  { lines[NR] = $0 }
  END {
    for (i = 1; i <= NR; i++) {
      if (lines[i] !~ /ERROR|CRITICAL|Traceback/) continue
      if (lines[i] ~ /^CRITICAL:[0-9]+ ERROR:[0-9]+ WARNING:[0-9]+/) continue
      loc = (i < NR) ? lines[i+1] : ""
      if (listfile != "") {
        hit = 0
        for (k = 0; k < n; k++) if (index(lines[i] loc, paths[k]) > 0) { hit = 1; break }
        if (!hit) continue
      }
      sub(/^[[:space:]]+/, "", loc)
      if (loc ~ /\// && loc !~ /^ERROR|^CRITICAL|^Traceback/) print lines[i] " [" loc "]"
      else print lines[i]
    }
  }')"
ERR_COUNT=0
[[ -n "$ERR_LINES" ]] && ERR_COUNT="$(printf '%s\n' "$ERR_LINES" | grep -c .)"
ELAPSED=$(( $(date +%s) - START ))

# A missing executable disables every !syntax block silently: BLOCKED even
# when --diff would have filtered the message away.
if grep -q "Failed to locate a valid executable" "$SMOKE_LOG"; then
  echo "BLOCKED: $SCOPE docs (${ELAPSED}s): MooseDocs could not locate a valid executable ($BIN)"
  echo "  log: $SMOKE_LOG"
  exit 2
fi

if [[ "$HTTP_CODE" == "200" && "$ERR_COUNT" == "0" ]]; then
  if [[ -n "$DIFF_BASE" ]]; then
    echo "PASS: $SCOPE docs (${ELAPSED}s, http 200, 0 errors in files changed since $DIFF_BASE)"
  else
    echo "PASS: $SCOPE docs (${ELAPSED}s, http 200, 0 errors)"
  fi
  echo "  log: $SMOKE_LOG"
  exit 0
fi

# Output budget: header + 3 status lines + up to 12 error lines + hint + log.
echo "FAIL: $SCOPE docs (${ELAPSED}s)"
echo "  http_code: ${HTTP_CODE:-<none>}"
if [[ -n "$DIFF_BASE" ]]; then
  echo "  errors:    $ERR_COUNT (in files changed since $DIFF_BASE)"
else
  echo "  errors:    $ERR_COUNT"
fi
if [[ -n "$ERR_LINES" ]]; then
  echo "  --- error lines (first 12 of $ERR_COUNT) ---"
  printf '%s\n' "$ERR_LINES" | head -12 | cut -c1-300
fi
# MooseDocs resolves !listing and links against git-tracked files; a new input
# or page that is not staged reports as missing from the repository.
if printf '%s\n' "$ERR_LINES" | grep -q "does not exist in the repository"; then
  echo "  hint: 'does not exist in the repository' means the file is untracked; git add it (do not commit) and re-run."
fi
echo "  log:       $SMOKE_LOG"
exit 1
