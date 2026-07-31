#!/bin/bash
# PostToolUse hook: flag legacy HIT block delimiters on lines ADDED to a `tests` spec.
#
# `[./name]` / `[../]` are vestigial HIT path-navigation tokens. They parse
# identically to `[name]` / `[]` but are legacy; ~800 moose specs still carry
# them. New blocks must use the modern form.
#
# Basis is the git diff of the file, not its contents, so editing one of those
# ~800 legacy files for an unrelated reason stays silent -- only lines you
# actually add can trip this. Falls back to scanning the written text when the
# file isn't in a git work tree.
#
# Fails open: any internal error exits 0 rather than blocking work.

input=$(cat)
command -v jq >/dev/null 2>&1 || exit 0

path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[[ -n "$path" && "$(basename "$path")" == "tests" ]] || exit 0

# `[./foo]` or `[../]`, allowing trailing whitespace/comment.
LEGACY='^[[:space:]]*\[(\./[^]]*|\.\./)\][[:space:]]*(#.*)?$'

dir=$(dirname "$path")
added=""

if [[ -d "$dir" ]] && git -C "$dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if git -C "$dir" ls-files --error-unmatch "$path" >/dev/null 2>&1; then
    # Tracked: added lines = '+' lines in the diff vs HEAD (staged + unstaged).
    added=$(git -C "$dir" diff HEAD -U0 -- "$path" 2>/dev/null \
            | grep '^+' | grep -v '^+++' | sed 's/^+//')
  else
    # Untracked: the whole file is new.
    added=$(cat "$path" 2>/dev/null)
  fi
else
  # Not in git -- fall back to just the text this tool call wrote.
  added=$(printf '%s' "$input" | jq -r '
    .tool_input |
    if .edits then ([.edits[].new_string] | join("\n"))
    else (.new_string // .content // "")
    end' 2>/dev/null)
fi

[[ -n "$added" ]] || exit 0

offenders=$(printf '%s\n' "$added" | grep -E "$LEGACY")
[[ -n "$offenders" ]] || exit 0

{
  echo "Legacy HIT block delimiters on lines added to ${path}:"
  printf '%s\n' "$offenders" | sed 's/^[[:space:]]*/  /'
  echo
  echo "New blocks use [name] ... [] -- not [./name] ... [../]. Renames count as new blocks."
  echo "Fix only the lines you added; leave the file's pre-existing legacy blocks alone"
  echo "(whole-file conversion inflates the diff and destroys blame)."
} >&2

exit 2
