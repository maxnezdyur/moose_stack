#!/usr/bin/env bash
# Start (or stop) a long-running MooseDocs preview server for one of the three
# top-level doc sites in the moose_stack meta-repo.
#
# Full build (no --fast). Background process. Auto-picks a free port from 8000.
# Re-invoking while a server is running restarts it.
#
# Usage:
#   serve.sh <moose|blackbear|isopod>          # start (or restart)
#   serve.sh <moose|blackbear|isopod> stop     # stop the running server

set -u

usage() {
  echo "Usage: $0 <moose|blackbear|isopod> [stop]" >&2
  exit 2
}

[[ $# -ge 1 ]] || usage
REPO="$1"
ACTION="${2:-start}"

# Locate moose_stack root by walking up from $PWD looking for .clangd.
META_ROOT=""
d="$PWD"
while [[ "$d" != "/" ]]; do
  if [[ -f "$d/.clangd" ]]; then META_ROOT="$d"; break; fi
  d="$(dirname "$d")"
done
[[ -n "$META_ROOT" ]] || { echo "ERROR: not inside a moose_stack worktree (no .clangd found)" >&2; exit 2; }

case "$REPO" in
  moose)
    DOC_DIR="$META_ROOT/moose/modules/doc"
    BIN="$META_ROOT/moose/test/moose_test-opt"
    BIN_BUILD="make -C $META_ROOT/moose/test -j" ;;
  blackbear)
    DOC_DIR="$META_ROOT/blackbear/doc"
    BIN="$META_ROOT/blackbear/blackbear-opt"
    BIN_BUILD="make -C $META_ROOT/blackbear -j" ;;
  isopod)
    DOC_DIR="$META_ROOT/isopod/doc"
    BIN="$META_ROOT/isopod/isopod-opt"
    BIN_BUILD="make -C $META_ROOT/isopod -j" ;;
  *)
    echo "ERROR: unknown repo '$REPO' (expected moose|blackbear|isopod)" >&2
    exit 2 ;;
esac

PID_FILE="/tmp/moose-docs-$REPO-serve.pid"
LOG_FILE="/tmp/moose-docs-$REPO-serve.log"

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

# ----- stop -----
if [[ "$ACTION" == "stop" ]]; then
  if [[ -f "$PID_FILE" ]]; then
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      kill_pid "$pid"
      echo "stopped: $REPO (pid $pid)"
    else
      echo "no running server for $REPO (stale pid file removed)"
    fi
    rm -f "$PID_FILE"
  else
    echo "no running server for $REPO"
  fi
  exit 0
elif [[ "$ACTION" != "start" ]]; then
  echo "ERROR: unknown action '$ACTION' (expected: stop)" >&2
  exit 2
fi

# ----- env probe -----
if ! python3 -c "import yaml, MooseDocs" >/dev/null 2>&1; then
  echo "ERROR: MooseDocs Python deps missing." >&2
  echo "Activate the env that has yaml + MooseDocs (typically moose-dev), then retry." >&2
  exit 1
fi

# ----- binary probe (full build needs appsyntax → needs the executable) -----
if [[ ! -x "$BIN" ]]; then
  echo "ERROR: binary missing: $BIN" >&2
  echo "Build it first:" >&2
  echo "    $BIN_BUILD" >&2
  exit 1
fi

# ----- restart: kill any existing server -----
if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE")"
  if kill -0 "$old_pid" 2>/dev/null; then
    echo "restarting: killing existing $REPO server (pid $old_pid)"
    kill_pid "$old_pid"
  fi
  rm -f "$PID_FILE"
fi

# ----- pick a free port starting at 8000 -----
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
PORT="$(find_free_port)" || { echo "ERROR: no free port in 8000-8099" >&2; exit 1; }

# ----- spawn moosedocs in background -----
cd "$DOC_DIR" || exit 1
: >"$LOG_FILE"
nohup ./moosedocs.py build --serve --port "$PORT" >"$LOG_FILE" 2>&1 &
PID=$!
disown "$PID" 2>/dev/null || true
echo "$PID" > "$PID_FILE"

# Brief settle so an immediate crash is visible.
sleep 2
if ! kill -0 "$PID" 2>/dev/null; then
  echo "ERROR: server failed to start. Last 40 log lines:" >&2
  tail -40 "$LOG_FILE" >&2
  rm -f "$PID_FILE"
  exit 1
fi

cat <<MSG
serving $REPO docs:
  url:  http://localhost:$PORT
  pid:  $PID
  log:  $LOG_FILE
  stop: $0 $REPO stop

Note: full build (no --fast) — moosedocs is still building. The page will be
incomplete until the build finishes. Watch '$LOG_FILE' for progress.
MSG
