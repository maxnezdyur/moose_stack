#!/bin/zsh
# moose-factory tick. launchd (com.moose-factory, StartInterval 120) runs this at load and every
# two minutes. It regenerates the board only when a cheap manifest changed, and it never invokes
# Claude. Installed copy: ~/.local/bin/moose-factory-tick.sh. Source of truth:
# <meta_repo>/factory/moose-factory-tick.sh, where <meta_repo> is the `meta_repo` key of
# ~/.config/moose-factory/config.toml. Re-run factory/install.sh after editing.
#
# Nothing here names a user or a machine. Every path comes from $HOME or from the same config the
# projector reads, through `factory config --sh`.
#
# Order, per the plan's section 13:
#   hostname guard, ulimit, lock, watchdog, change check, board (on change or every tenth tick),
#   one notification per card newly in needs-you, `factory commit` when the vault is dirty,
#   one line to ~/Library/Logs/moose-factory.last-check.
#
# The change check is `python -m tool.ext_tick check`: exit 0 means an input changed, 1 means
# nothing new, anything else means the check itself failed and the board is NOT run. A failed probe
# carries the old value forward, so it can never register as a change. That exact bug caused
# phantom /digest runs in the Work vault on 2026-09-10.
#
# Manual use:
#   zsh ~/.local/bin/moose-factory-tick.sh              one tick now
#   MOOSE_FACTORY_FORCE=1 zsh ~/.local/bin/moose-factory-tick.sh   skip the change check
#   tail -f ~/Library/Logs/moose-factory.log            what the board did
#   cat ~/Library/Logs/moose-factory.last-check         the latest verdict, one line

# 1. Hostname guard: the first statement. On an INL cluster (sawtooth, lemhi, bitterroot, hoodoo,
#    teton) there is no vault, gh may be unauthenticated, and a dispatch would land on a login
#    node. The tick exits 0 silently there. The globs come from the config; the five defaults
#    stand in when the file is absent.
CONFIG="${MOOSE_FACTORY_CONFIG:-$HOME/.config/moose-factory/config.toml}"

# One key out of the config file, without a TOML parser: enough to find the projector. A leading
# "~" is expanded here, once, for every key, because tool/config.py expands it too; a shell reader
# that took the tilde literally would discard a value the Python side accepts.
cfg_get() {
  [[ -r "$CONFIG" ]] || return 0
  local v
  v="$(sed -n -e 's/[[:space:]]*#.*$//' -e "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$CONFIG" \
       | head -1 | tr -d '"' | tr -d '[],')"
  [[ -n "$v" ]] || return 0
  print -r -- "${v/#\~/$HOME}"
}

# The short hostname and the globs are both lowercased before they meet, because config.on_hpc
# lowercases both. macOS capitalises a hostname by default, so a case-sensitive guard and the
# python guard disagreed on a name like "Teton-MBP".
HOST_RAW="$(hostname -s 2>/dev/null)"
SHORT_HOST="${HOST_RAW:l}"
HOSTS="sawtooth* lemhi* bitterroot* hoodoo* teton*"
FROM_CFG="$(cfg_get refuse_hosts)"
[[ -n "$FROM_CFG" ]] && HOSTS="${FROM_CFG:l}"
for glob in ${=HOSTS}; do
  case "$SHORT_HOST" in ${~glob}) exit 0 ;; esac
done

# 2. launchd hands a job 256 descriptors; the probe round opens 36 git pipes in parallel.
ulimit -n 65536 2>/dev/null || ulimit -n 10240
# Prepend, never replace: a machine whose gh, git or python lives somewhere else (MacPorts, Nix, a
# per-user prefix) keeps it. Replacing the list made shutil.which("gh") return None inside every
# tick while `factory doctor`, run from a login shell, still reported gh as present, and the board
# then carried stale pull-request state forward without ever failing. `path_extra` in config.toml
# adds this machine's own prefixes; it is applied below, once the config has been read.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:${PATH:-/usr/bin:/bin}"
export DISABLE_AUTOUPDATER=1

if [[ -z "${FACTORY_DIR:-}" ]]; then
  # tool/config.py derives the meta-repo by walking up from its own file, but this script does not
  # sit inside the checkout, so the key is how it is found. factory/install.sh writes it.
  META="$(cfg_get meta_repo)"
  META="${META:-$HOME/projects/moose_stack}"
  FACTORY_DIR="$META/factory"
fi
FACTORY="$FACTORY_DIR/factory"

LOGDIR="$HOME/Library/Logs"
LOG="$LOGDIR/moose-factory.log"              # what the board did, appended
CHECK="$LOGDIR/moose-factory.last-check"     # this tick's verdict, one line, overwritten
LOCK="$LOGDIR/moose-factory.lock"            # one tick at a time (launchd vs a manual run)
TICKS="$LOGDIR/moose-factory.ticks"          # tick counter, for the every-tenth-tick board
WATCHDOG="${MOOSE_FACTORY_WATCHDOG:-300}"    # seconds for the whole tick
FULL_EVERY="${MOOSE_FACTORY_FULL_EVERY:-10}" # run the board anyway every Nth tick
mkdir -p "$LOGDIR" 2>/dev/null
stamp() { date '+%F %T'; }

# The launcher first: a missing launcher used to be reported as a missing vault, because the vault
# test ran before it and guessed a path from $HOME.
[[ -x "$FACTORY" ]] || {
  echo "$(stamp) launcher missing: $FACTORY (meta_repo in $CONFIG)" > "$CHECK"; exit 3; }

# Every other path comes from the projector itself, so the tick and the library can never disagree
# about where the vault is. One python start, every two minutes. The eval defines FACTORY_CFG_*.
# The launcher's own diagnosis is kept: discarding it turned "no python with PyYAML" into a
# verdict that blamed a vault path no config key ever named.
CFG_ERR="$(mktemp -t moose-factory-cfg)"
CFG_SH="$("$FACTORY" config --sh 2>"$CFG_ERR")"; cfg_rc=$?
if (( cfg_rc != 0 )); then
  echo "$(stamp) factory config failed (exit $cfg_rc): $(tr '\n' ' ' < "$CFG_ERR" | cut -c1-300)" \
    > "$CHECK"
  cat "$CFG_ERR" >> "$LOG"; rm -f "$CFG_ERR"; exit 3
fi
rm -f "$CFG_ERR"
eval "$CFG_SH"

# This machine's own PATH prefixes, from the config the projector just resolved.
[[ -n "${FACTORY_CFG_PATH_EXTRA:-}" ]] && export PATH="$FACTORY_CFG_PATH_EXTRA:$PATH"

VAULT="${MOOSE_FACTORY_VAULT:-${FACTORY_CFG_VAULT:-}}"
[[ -n "$VAULT" ]] || { echo "$(stamp) config named no vault ($CONFIG)" > "$CHECK"; exit 3; }
[[ -d "$VAULT" ]] || { echo "$(stamp) vault missing: $VAULT" > "$CHECK"; exit 3; }

# gh is how every pull-request fact reaches the board. When it is absent the probe reports the PR
# state as unknown and derive carries the previous value forward, which is invisible unless the
# verdict says so.
GH_NOTE=""
command -v gh >/dev/null 2>&1 || GH_NOTE=" | gh not on PATH"

# 3. Lock: a plain mkdir, because there is no flock(1) on this machine. A lock whose owner process
#    is gone is taken over; a live owner wins and this tick exits quietly.
if ! mkdir "$LOCK" 2>/dev/null; then
  oldpid=$(cat "$LOCK/pid" 2>/dev/null)
  if [[ -z "$oldpid" ]]; then
    # A lock directory with no pid file yet belongs to a tick that took it
    # microseconds ago and has not stamped it. Never steal that: two ticks both
    # "taking over" a half-built lock both win, and two boards then run against
    # one factory/state. An unstamped lock is treated as live.
    echo "$(stamp) busy: a tick holds the lock and has not stamped it yet" > "$CHECK"; exit 0
  fi
  if kill -0 "$oldpid" 2>/dev/null; then
    echo "$(stamp) busy: tick pid $oldpid still running" > "$CHECK"; exit 0
  fi
  echo "$(stamp) took over a stale lock (pid $oldpid gone)" >> "$LOG"
  rm -f "$LOCK/pid"; rmdir "$LOCK" 2>/dev/null; mkdir "$LOCK" 2>/dev/null || exit 0
fi
echo $$ > "$LOCK/pid"

WDPID=""; BPID=""
# The phase the tick is in, so a watchdog kill names what was in flight. Without
# it a 300 s kill is unexplainable after the fact: every step of this script is
# sub-second on a quiet machine, and the one kill seen so far (2026-09-12
# 22:33:48) left no evidence of which step blocked.
PHASE="start"
cleanup() {
  [[ -n "$WDPID" ]] && kill "$WDPID" 2>/dev/null
  [[ -n "$BPID" ]] && kill "$BPID" 2>/dev/null   # never leave an orphan board behind
  # Release only a lock this process still owns. Releasing another tick's lock
  # is how a third tick joins the two that are already running.
  if [[ "$(cat "$LOCK/pid" 2>/dev/null)" == "$$" ]]; then
    rm -f "$LOCK/pid"; rmdir "$LOCK" 2>/dev/null
  fi
}
trap cleanup EXIT
trap 'echo "$(stamp) watchdog: killed in phase $PHASE after ${SECONDS}s" >> "$LOG"; echo "$(stamp) watchdog killed the tick in phase $PHASE after ${SECONDS}s" > "$CHECK"; exit 124' TERM INT

# 4. Watchdog: one child that TERMs this script. The EXIT trap then releases the lock, so a hung
#    git or gh call cannot wedge the loop for the rest of the day.
( sleep "$WATCHDOG"; kill -TERM $$ 2>/dev/null ) &
WDPID=$!

# A python that imports yaml, same rule and same order as the factory launcher: the environment,
# then the config file's `python`, then the usual suspects.
pick_py() {
  local c
  for c in "$FACTORY_PYTHON" "$FACTORY_CFG_PYTHON" /opt/homebrew/bin/python3 python3 python; do
    [[ -n "$c" ]] || continue
    command -v "$c" >/dev/null 2>&1 || continue
    "$c" -c 'import yaml' >/dev/null 2>&1 && { echo "$c"; return 0 }
  done
  echo ""
}
PHASE="pick-python"
PY="$(pick_py)"
if [[ -z "$PY" ]]; then
  echo "$(stamp) no python with PyYAML (set FACTORY_PYTHON)" | tee -a "$LOG" > "$CHECK"; exit 1
fi
export PYTHONPATH="$FACTORY_DIR${PYTHONPATH:+:$PYTHONPATH}"

# 5. Tick counter.
PHASE="tick-counter"
n=$(( $(cat "$TICKS" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$TICKS"

# 6. The change check. Nothing else in this script decides whether to run the board.
PHASE="change-check"
if [[ -n "$MOOSE_FACTORY_FORCE" ]]; then
  CHANGE="forced"; run_board=1
else
  CHANGE="$("$PY" -P -m tool.ext_tick check 2>>"$LOG")"; rc=$?
  case $rc in
    0) run_board=1 ;;
    1) run_board=0 ;;
    *) run_board=0; CHANGE="${CHANGE:-check failed (rc $rc)}" ;;
  esac
fi
if (( run_board == 0 )) && (( n % FULL_EVERY == 0 )); then
  run_board=1; CHANGE="${CHANGE:-no change}, tenth tick"
fi

# 7. The board, at most once per tick. Never while a board of Max's own is in flight: two boards
#    share factory/state/, and a collision there costs a traceback and a wasted probe round.
if (( run_board )) && pgrep -f 'tool\.cli board' >/dev/null 2>&1; then
  run_board=0; CHANGE="$CHANGE, a board is already running"
fi
PHASE="board"
BOARD=""
if (( run_board )); then
  echo "=== $(stamp) tick $n board start - $CHANGE" >> "$LOG"
  # In the background, so the watchdog's TERM reaches this script while it waits and the EXIT trap
  # can kill the board with it. A command substitution would orphan a hung board instead.
  BOUT="$(mktemp -t moose-factory-board)"
  "$FACTORY" board > "$BOUT" 2>>"$LOG" &
  BPID=$!
  wait $BPID; brc=$?
  BPID=""
  cat "$BOUT" >> "$LOG"
  echo "=== $(stamp) tick $n board end (exit $brc)" >> "$LOG"
  BOARD="$(head -1 "$BOUT")"; rm -f "$BOUT"
  (( brc == 0 )) || BOARD="$BOARD [board exit $brc]"
fi

# 8. One banner per card that newly entered needs-you. Cheap: it reads the notes the board just
#    wrote, so it costs no probe round and cannot disagree with the board.
PHASE="notify"
NOTE="$("$PY" -P -m tool.ext_tick notify 2>>"$LOG")" || NOTE="notify failed"

# 9. Commit the vault when it is dirty. No trailers: `factory commit` owns the message.
PHASE="commit"
COMMIT="clean"
if [[ -n "$(git -C "$VAULT" status --porcelain 2>/dev/null)" ]]; then
  COMMIT="$("$FACTORY" commit 2>>"$LOG" | tail -1)"
fi

# 10. One line, overwritten, for the next tick and for `factory doctor`.
echo "$(stamp) tick $n: $CHANGE${BOARD:+ | $BOARD} | ${NOTE#notify: } | commit: $COMMIT$GH_NOTE" \
  > "$CHECK"
exit 0
