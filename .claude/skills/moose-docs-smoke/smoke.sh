#!/usr/bin/env bash
# Smoke-test one of the three top-level MooseDocs sites: full build + serve +
# HTTP probe. Pass = moosedocs exits 0 + HTTP 200 + zero ERROR/CRITICAL in log.
#
# Usage:
#   smoke.sh <moose|blackbear|isopod>
#
# Env:
#   SMOKE_TIMEOUT  Max seconds to wait for the server to bind (default 600).

set -u

usage() {
  echo "Usage: $0 <moose|blackbear|isopod>" >&2
  exit 2
}

[[ $# -eq 1 ]] || usage
REPO="$1"

# Locate moose_stack root by walking up looking for .clangd.
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

LOG_FILE="/tmp/moose-docs-$REPO-smoke.log"
TIMEOUT_SEC="${SMOKE_TIMEOUT:-600}"

# ----- env probe -----
if ! python3 -c "import yaml, MooseDocs" >/dev/null 2>&1; then
  echo "FAIL: MooseDocs Python deps missing." >&2
  echo "       Activate moose-dev (or equivalent) and retry." >&2
  exit 1
fi

# ----- binary probe -----
if [[ ! -x "$BIN" ]]; then
  echo "FAIL: binary missing: $BIN" >&2
  echo "       Build it first: $BIN_BUILD" >&2
  exit 1
fi

# ----- pick a free port -----
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
PORT="$(find_free_port)" || { echo "FAIL: no free port in 8000-8099" >&2; exit 1; }

cd "$DOC_DIR" || exit 1

START="$(date +%s)"
: >"$LOG_FILE"

./moosedocs.py build --serve --port "$PORT" >"$LOG_FILE" 2>&1 &
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

# ----- poll port until accepting (or timeout / process exits) -----
DEADLINE=$(( $(date +%s) + TIMEOUT_SEC ))
while :; do
  if (echo > /dev/tcp/127.0.0.1/$PORT) >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "FAIL: moosedocs exited before serving."
    echo "  log: $LOG_FILE"
    echo "  --- last 40 lines ---"
    tail -40 "$LOG_FILE"
    exit 1
  fi
  if (( $(date +%s) >= DEADLINE )); then
    echo "FAIL: timeout (${TIMEOUT_SEC}s) waiting for port $PORT to bind."
    echo "  log: $LOG_FILE"
    exit 1
  fi
  sleep 2
done

# ----- HTTP probe -----
HTTP_CODE="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 30 "http://localhost:$PORT/" 2>/dev/null || true)"
if [[ "$HTTP_CODE" != "200" ]]; then
  HTTP_CODE="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 30 "http://localhost:$PORT/index.html" 2>/dev/null || true)"
fi

# ----- error/critical grep on the log -----
ERR_LINES="$(grep -E 'ERROR|CRITICAL|Traceback' "$LOG_FILE" 2>/dev/null || true)"
ERR_COUNT=0
[[ -n "$ERR_LINES" ]] && ERR_COUNT="$(printf '%s\n' "$ERR_LINES" | grep -c .)"

ELAPSED=$(( $(date +%s) - START ))

if [[ "$HTTP_CODE" == "200" && "$ERR_COUNT" == "0" ]]; then
  echo "PASS: $REPO docs (${ELAPSED}s, http 200, 0 errors)"
  exit 0
fi

echo "FAIL: $REPO docs (${ELAPSED}s)"
echo "  http_code: ${HTTP_CODE:-<none>}"
echo "  errors:    $ERR_COUNT"
if [[ -n "$ERR_LINES" ]]; then
  echo "  --- error lines (up to 20) ---"
  printf '%s\n' "$ERR_LINES" | head -20
fi
echo "  log:       $LOG_FILE"
exit 1
