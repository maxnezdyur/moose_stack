#!/usr/bin/env bash
# Regenerate the MOOSE syntax YAML cache used by the moose-params skill.
#
# Usage:
#   bash refresh.sh <path-to-app-opt-binary>
#
# Always writes to: /Users/maxnezdyur/projects/moose_stack/.claude/cache/syntax.yaml
# Overwrites any existing cache. The skill does not track which binary produced it.

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: bash refresh.sh <path-to-app-opt-binary>" >&2
  exit 2
fi

BINARY="$1"

if [[ ! -x "$BINARY" ]]; then
  echo "ERROR: $BINARY is not an executable file" >&2
  exit 2
fi

META_ROOT="/Users/maxnezdyur/projects/moose_stack"
CACHE_DIR="$META_ROOT/.claude/cache"
OUT="$CACHE_DIR/syntax.yaml"

mkdir -p "$CACHE_DIR"

# --yaml output is preceded by deprecation warnings on stdout that would
# corrupt the document. Extract only the lines between the START/END markers.
#
# Sanitize a known MOOSE bug: `doc_range:` values occasionally contain an
# unescaped single quote inside a single-quoted scalar (e.g.
# `doc_range: 'elements_changed_threshold' > 0'`), which is invalid YAML and
# breaks yq. Lines with three or more single quotes get their value blanked.
"$BINARY" --disallow-test-objects --yaml \
  | awk '/\*\*START YAML DATA\*\*/{f=1;next} /\*\*END YAML DATA\*\*/{f=0} f' \
  | sed -E "s/^([[:space:]]*doc_range:)[[:space:]]*'[^']*'.*'.*$/\1/" \
  > "$OUT"

if ! yq empty "$OUT" 2>/dev/null; then
  echo "ERROR: extracted YAML is malformed at $OUT" >&2
  echo "Run: yq empty $OUT  to see the parser error." >&2
  exit 1
fi

SIZE=$(wc -c < "$OUT" | tr -d ' ')
echo "Wrote $OUT ($SIZE bytes)"
