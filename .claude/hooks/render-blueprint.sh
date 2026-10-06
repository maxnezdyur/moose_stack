#!/bin/bash
# PostToolUse hook (matcher Edit|Write): keep specs/blueprint.html, the review page, in step
# with its source.
#
#   specs/blueprint-page.html written  -> pack it into specs/blueprint.html (html-plan runtime:
#                                         lint, doc-math via pandoc, embed code slices, inline).
#   specs/blueprint.md written         -> nothing when a blueprint-page.html sits beside it (the
#                                         page is the view); otherwise the legacy pandoc render,
#                                         so a worktree from before the page existed still gets
#                                         a readable blueprint.html.
#
# The markdown is the contract that agents and the factory read; the page is the human's review
# surface. Fails open: no jq, no node, no pandoc, or any error exits 0 so a view problem never
# blocks work. Pack errors are printed; the previous blueprint.html is left in place.

input=$(cat)
command -v jq >/dev/null 2>&1 || exit 0

path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -n "$path" ] || exit 0
[ -f "$path" ] || exit 0

case "$path" in
  */specs/blueprint-page.html) mode=page ;;
  */specs/blueprint.md)        mode=md ;;
  *) exit 0 ;;
esac

specs=$(dirname "$path")
# The skill that owns the runtime lives in the worktree that owns the blueprint: walk up from
# specs/ to the directory holding .claude/. That directory is also the worktree root pack reads
# code slices from.
root=$(dirname "$specs")
while [ "$root" != "/" ] && [ ! -d "$root/.claude" ]; do root=$(dirname "$root"); done
skill="$root/.claude/skills/moose-blueprint"

if [ "$mode" = md ] && [ -f "$specs/blueprint-page.html" ]; then
  exit 0
fi

if [ "$mode" = page ]; then
  command -v node >/dev/null 2>&1 || { echo "render-blueprint: node not installed; blueprint.html not packed" >&2; exit 0; }
  [ -f "$skill/runtime/pack-blueprint.py" ] || exit 0
  if python3 "$skill/runtime/pack-blueprint.py" "$path" --root "$root" -o "$specs/blueprint.html" \
       >/tmp/render-blueprint.out 2>/tmp/render-blueprint.err; then
    echo "packed $specs/blueprint.html" >&2
    grep -h '⚠\|✗\|warning' /tmp/render-blueprint.out /tmp/render-blueprint.err 2>/dev/null | head -n 20 >&2
  else
    echo "render-blueprint: pack failed; blueprint.html not updated. Run: python3 $skill/runtime/pack-blueprint.py $path --root $root" >&2
    cat /tmp/render-blueprint.err >&2
  fi
  exit 0
fi

# Legacy: markdown only, pandoc view.
command -v pandoc >/dev/null 2>&1 || exit 0
ref="$skill/references"
[ -f "$ref/blueprint.template.html" ] && [ -f "$ref/workplan.html" ] || exit 0
title=$(sed -n 's/^title:[[:space:]]*//p' "$path" | head -n 1 | tr -d '"')
out="${path%.md}.html"
if pandoc "$path" --standalone --toc --toc-depth=2 --mathml \
     --template "$ref/blueprint.template.html" --include-after-body "$ref/workplan.html" \
     --metadata pagetitle="${title:-Blueprint}" -o "$out" 2>/tmp/render-blueprint.err; then
  echo "rendered $out (legacy pandoc view; no blueprint-page.html beside the markdown)" >&2
else
  echo "render-blueprint: pandoc failed (see /tmp/render-blueprint.err); blueprint.md is still valid" >&2
fi
exit 0
