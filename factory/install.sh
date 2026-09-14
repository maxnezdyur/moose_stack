#!/bin/zsh
# Installs the moose-factory tick: every 120 s (and at load), launchd runs the change check and
# regenerates the board only when an input changed. Nothing here ever invokes Claude.
#
#   zsh factory/install.sh              install or re-install, then bootstrap and verify one tick
#   zsh factory/install.sh --uninstall  bootout the agent and remove both installed files
#   zsh factory/install.sh --status     what is installed and what the last tick said
#   zsh factory/install.sh --config     write the `meta_repo` key for this checkout, nothing else
#
# Installs exactly two files outside the repo:
#   ~/.local/bin/moose-factory-tick.sh
#   ~/Library/LaunchAgents/com.moose-factory.plist   (generated from the .in template)
# Logs live in ~/Library/Logs/moose-factory*. The vault and the repo are never touched.
#
# Nothing here names a user. The label is com.moose-factory, one per machine, because a user
# launchd domain is already per user. The plist is generated, not copied: the template carries
# __LABEL__, __TICK_SCRIPT__ and __LOG__, and this script substitutes the resolved values.
#
# Exit codes: 0 ok, 1 a human should look, 3 a missing path or a refused host.

# 1. Hostname guard: the first statement. There is no vault on an INL cluster (sawtooth, lemhi,
#    bitterroot, hoodoo, teton) and no user launchd session to own an agent. The globs come from
#    the same config the projector reads; the five defaults stand in when the file is absent.
CONFIG="${MOOSE_FACTORY_CONFIG:-$HOME/.config/moose-factory/config.toml}"

# One key out of the config file, without a TOML parser. Absent file, absent key or a comment all
# print nothing, and every caller carries its own default. A leading "~" is expanded here, once,
# for every key, because tool/config.py expands it too: a shell reader that took the tilde
# literally would discard a value the Python side accepts and then report it as absent.
cfg_get() {
  [[ -r "$CONFIG" ]] || return 0
  local v
  v="$(sed -n -e 's/[[:space:]]*#.*$//' -e "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$CONFIG" \
       | head -1 | tr -d '"' | tr -d '[],')"
  [[ -n "$v" ]] || return 0
  print -r -- "${v/#\~/$HOME}"
}

# The short hostname and the globs are both lowercased before they meet, because config.on_hpc
# lowercases both. macOS capitalises a hostname by default, so a case-sensitive guard let
# "Teton-MBP" install an agent that every python entry point then refused.
HOST_RAW="$(hostname -s 2>/dev/null)"
SHORT_HOST="${HOST_RAW:l}"
HOSTS="sawtooth* lemhi* bitterroot* hoodoo* teton*"
FROM_CFG="$(cfg_get refuse_hosts)"
[[ -n "$FROM_CFG" ]] && HOSTS="${FROM_CFG:l}"
for glob in ${=HOSTS}; do
  case "$SHORT_HOST" in
    ${~glob}) echo "install.sh: not on $HOST_RAW (no vault, no user launchd session here)" >&2
              exit 3 ;;
  esac
done

set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.moose-factory"
TICK_SRC="$HERE/moose-factory-tick.sh"
PLIST_SRC="$HERE/$LABEL.plist.in"
TICK_DST="$HOME/.local/bin/moose-factory-tick.sh"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGDIR="$HOME/Library/Logs"
LOG="$LOGDIR/moose-factory.log"
LAUNCHD_LOG="$LOGDIR/moose-factory.launchd.log"
CHECK="$LOGDIR/moose-factory.last-check"
UID_="$(id -u)"
# The label this script used before it stopped naming the user. Booted out on every install, so a
# machine that ran the old agent does not end up with two ticks.
OLD_LABEL="com.$(id -un).moose-factory"

# The notifier, for the report only. This script installs nothing with brew.
NOTIFIER="$(cfg_get notifier)"
[[ -n "$NOTIFIER" ]] || NOTIFIER="/opt/homebrew/bin/terminal-notifier"

# The `meta_repo` key, written once per machine. tool/config.py derives the meta-repo by walking up
# from its own file, so the Python side runs from any checkout with no config file at all. The three
# shell readers (the /factory skill, session-context.sh and the tick) cannot: none of them sits
# inside the checkout it has to find, so their last resort is the literal $HOME/projects/moose_stack.
# Writing the key here is what makes a checkout at any other path work for all four. An existing key
# is never touched, and nothing else in the file is rewritten.
ensure_meta_repo() {
  local meta value
  meta="$(cd "$HERE/.." && pwd)"
  if [[ "$meta" == "$HOME"/* ]]; then value="~${meta#$HOME}"; else value="$meta"; fi
  if [[ -n "$(cfg_get meta_repo)" ]]; then
    echo "config:     meta_repo is already set in $CONFIG"
    return 0
  fi
  mkdir -p "${CONFIG:h}"
  if [[ -s "$CONFIG" ]] && [[ "$(tail -c 1 "$CONFIG")" != "" ]]; then echo "" >> "$CONFIG"; fi
  {
    echo "# written by factory/install.sh: the checkout the shell readers resolve"
    echo "meta_repo = \"$value\""
  } >> "$CONFIG"
  echo "config:     wrote meta_repo = $value to $CONFIG"
}

# Write the plist for this machine. One place knows the substitutions.
render_plist() {
  sed -e "s|__LABEL__|$LABEL|g" \
      -e "s|__TICK_SCRIPT__|$TICK_DST|g" \
      -e "s|__LOG__|$LAUNCHD_LOG|g" "$PLIST_SRC" > "$1"
}

case "${1:-}" in
  -h|--help)
    sed -n '2,19p' "$0"; exit 0 ;;

  --status)
    echo "label     $LABEL"
    if launchctl list "$LABEL" >/dev/null 2>&1; then
      echo "loaded    yes"
      launchctl list "$LABEL" | grep -E '"(PID|LastExitStatus)"' | sed 's/^/          /'
    else
      echo "loaded    no   (zsh $0)"
    fi
    launchctl list "$OLD_LABEL" >/dev/null 2>&1 && echo "stale     $OLD_LABEL is still loaded; zsh $0"
    for f in "$TICK_DST" "$PLIST_DST"; do
      [[ -e "$f" ]] && echo "installed $f" || echo "missing   $f"
    done
    if [[ -f "$TICK_DST" ]] && ! cmp -s "$TICK_SRC" "$TICK_DST"; then
      echo "stale     $TICK_DST differs from the repo copy; re-run $0"
    fi
    if [[ -f "$PLIST_DST" ]]; then
      tmp="$(mktemp -t moose-factory-plist)"; render_plist "$tmp"
      cmp -s "$tmp" "$PLIST_DST" || echo "stale     $PLIST_DST differs from the template; re-run $0"
      rm -f "$tmp"
    fi
    [[ -x "$NOTIFIER" ]] && echo "notifier  $NOTIFIER" || echo "notifier  osascript fallback (brew install terminal-notifier)"
    echo "config    $CONFIG"
    echo "last      $(cat "$CHECK" 2>/dev/null || echo 'no tick yet')"
    exit 0 ;;

  --uninstall)
    launchctl bootout "gui/$UID_/$LABEL" 2>/dev/null || true
    launchctl bootout "gui/$UID_/$OLD_LABEL" 2>/dev/null || true
    rm -f "$PLIST_DST" "$TICK_DST"
    rm -f "$LOGDIR/moose-factory.lock/pid"; rmdir "$LOGDIR/moose-factory.lock" 2>/dev/null || true
    echo "uninstalled: agent booted out, $PLIST_DST and $TICK_DST removed"
    echo "kept:        $LOGDIR/moose-factory*  (logs, tick counter, needs-you memory)"
    echo "kept:        the vault, the repo, and factory/state/ - nothing generated was touched"
    echo "reinstall:   zsh $0"
    exit 0 ;;

  --config)
    ensure_meta_repo; exit 0 ;;

  "") ;;
  *) echo "install.sh: unknown option '$1' (try --help)" >&2; exit 1 ;;
esac

[[ -f "$TICK_SRC" ]]  || { echo "install.sh: missing $TICK_SRC" >&2; exit 3; }
[[ -f "$PLIST_SRC" ]] || { echo "install.sh: missing $PLIST_SRC" >&2; exit 3; }
[[ -x "$HERE/factory" ]] || { echo "install.sh: missing $HERE/factory" >&2; exit 3; }

mkdir -p "$HOME/.local/bin" "$HOME/Library/LaunchAgents" "$LOGDIR"

ensure_meta_repo

# The banner channel. macOS grants notification authorization per executable, so the path is
# pinned in the config rather than searched. Absent, banners fall back to osascript. This script
# installs nothing: a missing notifier is reported, not fixed.
[[ -x "$NOTIFIER" ]] || echo "note: no notifier at $NOTIFIER; banners use the osascript fallback"

install -m 755 "$TICK_SRC" "$TICK_DST"
render_plist "$PLIST_DST"
chmod 644 "$PLIST_DST"
plutil -lint "$PLIST_DST"

# Boot out the old username-bearing agent first, so one machine never runs two ticks.
launchctl bootout "gui/$UID_/$OLD_LABEL" 2>/dev/null && echo "removed:    the old $OLD_LABEL agent" || true
rm -f "$HOME/Library/LaunchAgents/$OLD_LABEL.plist"
launchctl bootout "gui/$UID_/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID_" "$PLIST_DST"

echo "installed:  $TICK_DST"
echo "installed:  $PLIST_DST  (StartInterval 120, RunAtLoad, Background)"
[[ -x "$NOTIFIER" ]] && echo "notifier:   $NOTIFIER" || echo "notifier:   osascript fallback"

# Verify one tick. RunAtLoad has already started one; a board round takes tens of seconds, so wait
# up to 150 s for the verdict line to be rewritten. The verdict is one line and it is the contract.
before="$(cat "$CHECK" 2>/dev/null || true)"
echo "waiting:    one tick (up to 150 s)"
verdict=""
for i in $(seq 1 150); do
  now="$(cat "$CHECK" 2>/dev/null || true)"
  if [[ -n "$now" && "$now" != "$before" ]]; then verdict="$now"; break; fi
  sleep 1
done
if [[ -z "$verdict" ]]; then
  echo "verdict:    no tick in 150 s. Look at $LOG and $LAUNCHD_LOG" >&2
  echo "            (run one by hand: launchctl kickstart -k gui/$UID_/$LABEL)" >&2
  exit 1
fi
echo "verdict:    $verdict"
echo "run now:    launchctl kickstart -k gui/$UID_/$LABEL"
echo "board log:  tail -f $LOG"
echo "checks:     $HERE/factory doctor"
echo "config:     $HERE/factory config"
echo "remove:     zsh $0 --uninstall"
