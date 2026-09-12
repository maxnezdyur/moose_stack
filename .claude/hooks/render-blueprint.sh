#!/bin/bash
# PostToolUse hook (matcher Edit|Write): when the written file is a specs/blueprint.md,
# render specs/blueprint.html beside it with pandoc. The markdown is the source of truth;
# the HTML is a generated view (MathML for the equations, so it is self-contained and
# renders in Safari, which blocks file:// pages from loading other local files).
# Fails open: no jq, no pandoc, or any error exits 0 so a view problem never blocks work.

input=$(cat)
command -v jq >/dev/null 2>&1 || exit 0
command -v pandoc >/dev/null 2>&1 || exit 0

path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -n "$path" ] || exit 0
case "$path" in */specs/blueprint.md) ;; *) exit 0 ;; esac
[ -f "$path" ] || exit 0

# Template and card script live in the moose-blueprint skill of the worktree that owns the
# blueprint: walk up from specs/ to the directory holding .claude/.
root=$(dirname "$(dirname "$path")")
while [ "$root" != "/" ] && [ ! -d "$root/.claude" ]; do root=$(dirname "$root"); done
ref="$root/.claude/skills/moose-blueprint/references"
[ -f "$ref/blueprint.template.html" ] && [ -f "$ref/workplan.html" ] || exit 0

title=$(sed -n 's/^title:[[:space:]]*//p' "$path" | head -n 1 | tr -d '"')
out="${path%.md}.html"
if pandoc "$path" --standalone --toc --toc-depth=2 --mathml \
     --template "$ref/blueprint.template.html" --include-after-body "$ref/workplan.html" \
     --metadata pagetitle="${title:-Blueprint}" -o "$out" 2>/tmp/render-blueprint.err; then
  echo "rendered $out" >&2
else
  echo "render-blueprint: pandoc failed (see /tmp/render-blueprint.err); blueprint.md is still valid" >&2
fi
exit 0
