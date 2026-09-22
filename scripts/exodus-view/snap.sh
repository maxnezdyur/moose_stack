#!/usr/bin/env bash
# Render one exodus-view URL headless and save <out-dir>/<name>.png + .json through the server.
#
#   snap.sh <name> <out-dir> "<viewer url without snap=>"
#
# Needs a running exodus-view server (the URL points at it) and a headless Chromium:
# $EXODUS_VIEW_CHROME, the Playwright chromium cache, Google Chrome, or chromium on PATH.
set -euo pipefail
name=${1:?name}; out=${2:?out-dir}; url=${3:?url}

find_chrome() {
  [[ -n "${EXODUS_VIEW_CHROME:-}" && -x "$EXODUS_VIEW_CHROME" ]] && { echo "$EXODUS_VIEW_CHROME"; return; }
  local c
  for c in "$HOME"/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-mac-*/chrome-headless-shell \
           "$HOME"/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux*/chrome-headless-shell \
           "$HOME"/Library/Caches/ms-playwright/chromium-*/chrome-mac-*/"Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing" \
           "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
           "/Applications/Chromium.app/Contents/MacOS/Chromium"; do
    [[ -x "$c" ]] && { echo "$c"; return; }
  done
  for c in chromium chromium-browser google-chrome google-chrome-stable; do
    command -v "$c" >/dev/null 2>&1 && { command -v "$c"; return; }
  done
  echo "snap.sh: no headless Chromium found; set EXODUS_VIEW_CHROME" >&2
  exit 2
}

chrome=$(find_chrome)
mkdir -p "$out"
out_abs=$(cd "$out" && pwd)
sep='&'; [[ "$url" == *'?'* ]] || sep='?'
full="${url}${sep}snap=${name}&snapdir=${out_abs}"
tmp=$(mktemp -t exosnap).png
"$chrome" --headless --disable-gpu --use-angle=swiftshader --enable-unsafe-swiftshader \
  --window-size=1400,900 --virtual-time-budget=20000 --screenshot="$tmp" "$full" >/dev/null 2>&1 || true
rm -f "$tmp"
if [[ -f "$out_abs/$name.png" ]]; then
  echo "$out_abs/$name.png"
else
  echo "snap.sh: no snapshot written for $name (is the server up? does the URL load?)" >&2
  exit 1
fi
