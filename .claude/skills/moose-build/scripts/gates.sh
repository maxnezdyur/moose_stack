#!/usr/bin/env bash
# Standing gates for /moose-build: SQA, ASCII, docs smoke.
#
# Usage:
#   gates.sh <scope> <sqa|ascii|docs|all> [--base <ref>] [--core]
#
#   <scope>  moose | blackbear | isopod | moose/modules/<m>
#            A module scope diffs the whole moose git repo and runs the
#            module's own doc config (moose/modules/<m>/doc).
#   --base   merge-base ref for the diff (default: devel).
#   --core   skip the docs gate (reported as SKIPPED).
#
# Environment:
#   GATES_CHECK_TIMEOUT  seconds allowed for `moosedocs.py check` in the sqa
#                        gate (default 600). On expiry the check is killed and
#                        the gate reports BLOCKED with the log path.
#   GATES_DOC_DIR        replaces the scope's doc dir (the directory whose
#                        moosedocs.py the sqa gate runs). Test hook: point it
#                        at a stub moosedocs.py to exercise the PASS, FAIL,
#                        and BLOCKED classification without a real check. It
#                        may lie outside the worktree. Unset in normal use.
#
# Runtime: the sqa gate runs the full `moosedocs.py check` (doc, req, and app
# reports). For the `moose` scope that walks every registered object of the
# combined app and takes several minutes (more than 3 min on a laptop); the
# app scopes finish in about a minute. Callers run `sqa` and `all` in the
# background (run_in_background + Monitor) rather than on a foreground clock.
#
# Output: one JSON object per line
#   {"gate":"sqa","status":"PASS|FAIL|BLOCKED|SKIPPED","hits":[...],"hint":"..."}
# and, for `all`, a final {"gate":"all","status":...} line.
# Exit: 0 = pass, 1 = fail, 2 = blocked or usage.
#
# The diff basis is the merge-base of <base> and HEAD compared against the
# working tree, plus every untracked file. /moose-build never commits, so a
# plain <base>...HEAD would miss the edited tracked files; the merge-base
# form is <base>...HEAD plus the uncommitted changes.
#
# Hit paths are meta-root relative (moose/test/tests/x/tests:12) so a caller
# that runs several scopes can tell the repos apart.

set -u

usage() {
  echo "usage: gates.sh <moose|blackbear|isopod|moose/modules/<m>> <sqa|ascii|docs|all> [--base <ref>] [--core]" >&2
  exit 2
}

# ---------------------------------------------------------------- arguments
[ $# -ge 2 ] || usage
SCOPE="$1"; GATE="$2"; shift 2
BASE="devel"; CORE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --base) [ $# -ge 2 ] || usage; BASE="$2"; shift 2 ;;
    --core) CORE=1; shift ;;
    *) usage ;;
  esac
done
case "$GATE" in sqa|ascii|docs|all) ;; *) usage ;; esac

# ---------------------------------------------------------------- meta-root
# $CLAUDE_PROJECT_DIR when the harness sets it, else the first ancestor of
# $PWD that holds .clangd (the same rule scripts/moose-env.sh uses), so the
# script works from any moose-worktrees/<feature>/ checkout.
META="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$META" ]; then
  d="$PWD"
  while [ "$d" != "/" ] && [ ! -f "$d/.clangd" ]; do d="$(dirname "$d")"; done
  [ -f "$d/.clangd" ] && META="$d"
fi
if [ -z "$META" ] || [ ! -f "$META/.clangd" ]; then
  echo "gates.sh: not inside a moose_stack worktree (no .clangd found walking up from $PWD)" >&2
  exit 2
fi

# ---------------------------------------------------------------- scope table
case "$SCOPE" in
  moose)     REPO="moose";     DOC_DIR="$META/moose/modules/doc" ;;
  blackbear) REPO="blackbear"; DOC_DIR="$META/blackbear/doc" ;;
  isopod)    REPO="isopod";    DOC_DIR="$META/isopod/doc" ;;
  moose/modules/*)
    MOD="${SCOPE#moose/modules/}"
    case "$MOD" in ""|*/*) usage ;; esac
    [ -d "$META/moose/modules/$MOD" ] || { echo "gates.sh: no such module: $MOD" >&2; exit 2; }
    REPO="moose"; DOC_DIR="$META/moose/modules/$MOD/doc" ;;
  *) usage ;;
esac
REPO_DIR="$META/$REPO"
[ -d "$REPO_DIR/.git" ] || [ -f "$REPO_DIR/.git" ] || { echo "gates.sh: $REPO_DIR is not a git checkout" >&2; exit 2; }
# The override comes after the table so <scope> is still validated and the
# diff basis (REPO_DIR) is unchanged; only the moosedocs.py location moves.
DOC_DIR="${GATES_DOC_DIR:-$DOC_DIR}"

# INL HPC hosts have no conda: the user is already inside the container, so
# python commands run bare. Everywhere else they go through conda-run.sh.
case "$(hostname)" in
  sawtooth*|lemhi*|bitterroot*|hoodoo*|teton*) HPC=1 ;;
  *) HPC=0 ;;
esac

# moosedocs.py honors a pre-set MOOSE_DIR; without it a worktree's docs build
# can resolve against another checkout's moose.
export MOOSE_DIR="$META/moose"
export PYTHONPATH="$MOOSE_DIR/python${PYTHONPATH:+:$PYTHONPATH}"

SCOPE_LABEL="$(echo "$SCOPE" | tr '/' '-')"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/moose-gates.XXXXXX")" || exit 2
trap 'rm -rf "$WORK"' EXIT

# ---------------------------------------------------------------- helpers
# emit <gate> <status> <hits-file> [hint]  -> one JSON line via jq (jq owns the escaping).
emit() {
  jq -c -n --arg gate "$1" --arg status "$2" --rawfile hits "$3" --arg hint "${4:-}" \
    '{gate:$gate, status:$status, hits:($hits | split("\n") | map(select(length > 0)))}
     + (if $hint == "" then {} else {hint:$hint} end)'
}

# kill_tree <pid>: TERM the descendants of <pid> (children first), then <pid>.
# pgrep -P exists on macOS and on procps Linux; no process-group tricks, which
# would need job control (set -m) in a non-interactive bash 3.2.
kill_tree() {
  local c
  for c in $(pgrep -P "$1" 2>/dev/null); do kill_tree "$c"; done
  kill -TERM "$1" 2>/dev/null || true
}

# run_in <dir> <cmd...>: run a python-side command in <dir>, through conda on
# local hosts and bare on HPC. conda-run.sh does not cd, hence the subshell.
# conda-run.sh only uses -C to find the worktree whose moose-dev pin names
# the env, so -C "$META" is the same env for every in-tree <dir> and keeps
# working when GATES_DOC_DIR points outside the worktree.
run_in() {
  local dir="$1"; shift
  if [ "$HPC" = 1 ]; then
    (cd "$dir" && "$@")
  else
    (cd "$dir" && bash "$META/scripts/conda-run.sh" -C "$META" -- "$@")
  fi
}

# ---------------------------------------------------------------- diff basis
# Produces:
#   $WORK/added.tsv   <repo-relative path>TAB<new line number>TAB<added line text>
#   $WORK/files.txt   every tracked-changed or untracked path, one per line
collect_diff() {
  git -C "$REPO_DIR" rev-parse --verify --quiet "$BASE^{commit}" >/dev/null \
    || { echo "gates.sh: base ref '$BASE' not found in $REPO_DIR" >&2; exit 2; }
  local mb
  mb="$(git -C "$REPO_DIR" merge-base "$BASE" HEAD)" || exit 2
  # core.quotePath=false keeps non-ASCII path bytes literal instead of octal
  # escapes, so the path column round-trips into hits as written on disk.
  {
    git -C "$REPO_DIR" -c core.quotePath=false diff -U0 --no-color --no-ext-diff --no-renames "$mb" -- .
    git -C "$REPO_DIR" ls-files --others --exclude-standard -z \
      | while IFS= read -r -d '' f; do
          # Regular files only: git cannot --no-index a symlink or directory.
          [ -f "$REPO_DIR/$f" ] && [ ! -L "$REPO_DIR/$f" ] || continue
          # --no-index exits 1 whenever the files differ; that is the normal case.
          git -C "$REPO_DIR" -c core.quotePath=false diff -U0 --no-color --no-index -- /dev/null "$f" || true
        done
  } > "$WORK/full.diff"

  # Unified diff -> added lines with their new-file line numbers. "+++ " is a
  # file header only outside a hunk; inside one it is an added line that
  # starts with "++ ".
  awk '
    /^diff / { inhunk = 0; path = ""; next }
    !inhunk && /^\+\+\+ / {
      if ($0 ~ /^\+\+\+ b\//) { path = substr($0, 7) } else { path = "" }   # +++ /dev/null = deletion
      next
    }
    /^@@ / { match($0, /\+[0-9]+/); n = substr($0, RSTART + 1, RLENGTH - 1) + 0; inhunk = 1; next }
    inhunk && path != "" && /^\+/ { print path "\t" n "\t" substr($0, 2); n++; next }
    inhunk && /^ / { n++; next }
  ' "$WORK/full.diff" > "$WORK/added.tsv"

  {
    git -C "$REPO_DIR" -c core.quotePath=false diff --name-only --no-renames "$mb" -- .
    git -C "$REPO_DIR" -c core.quotePath=false ls-files --others --exclude-standard
  } | sort -u > "$WORK/files.txt"
  UNTRACKED_N="$(git -C "$REPO_DIR" ls-files --others --exclude-standard | wc -l | tr -d ' ')"
}

# ---------------------------------------------------------------- gate: sqa
gate_sqa() {
  local hits="$WORK/sqa.hits" status hint=""
  : > "$hits"

  # Part 1: grep audit. Every touched tests-spec block that declares a
  # `type` (a runnable test) needs requirement, design, and issues at its own
  # level or on an ancestor block; CIVET's SQA precheck rejects the spec
  # otherwise. Group blocks without `type` only need to cover their children.
  # `#` is not stripped as a comment because values like issues = '#1493'
  # carry one; keys are matched at line start instead.
  local spec added
  cut -f1 "$WORK/added.tsv" | sort -u | while IFS= read -r spec; do
    [ "$(basename "$spec")" = "tests" ] || continue
    [ -f "$REPO_DIR/$spec" ] || continue
    added="$(awk -F'\t' -v p="$spec" '$1 == p { printf "%s ", $2 }' "$WORK/added.tsv")"
    awk -v added="$added" -v label="$REPO/$spec" '
      BEGIN { key[1] = "requirement"; key[2] = "design"; key[3] = "issues"
              n = split(added, a, " "); for (i = 1; i <= n; i++) if (a[i] != "") addset[a[i]] = 1; depth = 0 }
      {
        if (depth > 0 && (NR in addset)) touched[depth] = 1
        if ($0 ~ /^[ \t]*\[(\.\.\/)?\][ \t]*$/) {                      # [] or [../] closes a block
          if (depth > 0 && touched[depth] && has_type[depth]) {
            miss = ""
            for (k = 1; k <= 3; k++) {
              ok = 0
              for (d = depth; d >= 1; d--) if (has[d, k]) { ok = 1; break }
              if (!ok) miss = miss (miss == "" ? "" : ",") key[k]
            }
            if (miss != "") printf "%s:%d: block [%s] missing %s\n", label, start[depth], name[depth], miss
          }
          if (depth > 0) { delete touched[depth]; delete has_type[depth]; for (k = 1; k <= 3; k++) delete has[depth, k]; depth-- }
          next
        }
        if ($0 ~ /^[ \t]*\[[^\]]+\][ \t]*$/) {                           # [name] or [./name] opens a block
          depth++; nm = $0; sub(/^[ \t]*\[(\.\/)?/, "", nm); sub(/\][ \t]*$/, "", nm)
          name[depth] = nm; start[depth] = NR; touched[depth] = (NR in addset) ? 1 : 0; has_type[depth] = 0
          next
        }
        if (depth == 0) next
        if ($0 ~ /^[ \t]*type[ \t]*=/)        has_type[depth] = 1
        if ($0 ~ /^[ \t]*requirement[ \t]*=/) has[depth, 1] = 1
        if ($0 ~ /^[ \t]*design[ \t]*=/)      has[depth, 2] = 1
        if ($0 ~ /^[ \t]*issues[ \t]*=/)      has[depth, 3] = 1
      }
    ' "$REPO_DIR/$spec"
  done >> "$hits"
  local grep_hits
  grep_hits="$(wc -l < "$hits" | tr -d ' ')"

  # Part 2: the authoritative check. Errors are filtered to files in the
  # diff: pre-existing SQA debt elsewhere is reported in the hint, not failed.
  if [ ! -x "$DOC_DIR/moosedocs.py" ]; then
    emit sqa BLOCKED "$hits" "no moosedocs.py in $DOC_DIR; grep audit ran ($grep_hits hits), moosedocs.py check did not"
    return 2
  fi
  local probe_err="$WORK/probe.err"
  if ! run_in "$DOC_DIR" python3 -c "import yaml, MooseDocs" >/dev/null 2>"$probe_err"; then
    local why
    why="$(grep -v '^$' "$probe_err" | tail -1)"
    if [ "$HPC" = 1 ]; then
      hint="MooseDocs env missing on an HPC host: load the moose container module (docs/hpc.md) and re-run. Grep audit ran ($grep_hits hits); moosedocs.py check did not. $why"
    else
      hint="MooseDocs env missing: create the pinned conda env (docs/local.md; name from scripts/moose-env.sh) and re-run. Grep audit ran ($grep_hits hits); moosedocs.py check did not. $why"
    fi
    emit sqa BLOCKED "$hits" "$hint"
    return 2
  fi

  # The check has no timeout of its own and the moose scope runs for minutes,
  # so it goes to the background and is polled against GATES_CHECK_TIMEOUT.
  # bash 3.2 has no `timeout` builtin and macOS ships no coreutils timeout;
  # the poll loop plus kill_tree is the portable equivalent. kill_tree walks
  # the children first because the job is a subshell -> conda-run.sh ->
  # python chain and killing only the subshell would orphan the python.
  local log="${TMPDIR:-/tmp}/moose-gates-$SCOPE_LABEL-check.log" rc=0
  local limit="${GATES_CHECK_TIMEOUT:-600}" waited=0 pid timed_out=0
  run_in "$DOC_DIR" ./moosedocs.py check > "$log" 2>&1 &
  pid=$!
  while kill -0 "$pid" 2>/dev/null && [ "$waited" -lt "$limit" ]; do
    sleep 5; waited=$((waited + 5))
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill_tree "$pid"
    wait "$pid" 2>/dev/null
    timed_out=1
  else
    wait "$pid" || rc=$?
  fi
  # Strip ANSI color so path matching and the JSON stay clean.
  sed -e $'s/\x1b\\[[0-9;]*m//g' "$log" > "$WORK/check.txt"

  # A check that crashed or never ran gives no verdict on the diff, so it is
  # BLOCKED, never PASS. Without this rule a missing app binary read as green
  # whenever no error line named an in-diff path. Markers: a Python Traceback
  # and the executable lookup failure ("Failed to locate a valid executable",
  # the missing *-opt case). CRITICAL is deliberately not a marker: MooseDocs
  # logs CRITICAL for content faults too (a missing design page, an SQA
  # tokenize error in sqa.py), which are the author's to fix and belong to the
  # in-diff FAIL rule below with the ERROR lines. A non-zero exit with no
  # ERROR or CRITICAL line at all is an abort under a message this list does
  # not know; that rule is skipped after a kill, whose exit status says nothing
  # about the check. The record keeps the grep audit hits; the partial check
  # output stays in the log the hint names.
  local abort
  abort="$(grep -E 'Traceback|Failed to locate a valid executable' "$WORK/check.txt" | head -n 1)"
  if [ -z "$abort" ] && [ "$timed_out" = 0 ] && [ "$rc" != 0 ] \
     && [ "$(grep -c -E 'ERROR|CRITICAL' "$WORK/check.txt" | tr -d ' ')" = 0 ]; then
    abort="exit $rc with no ERROR line in the output"
  fi
  if [ "$timed_out" = 1 ]; then
    hint="moosedocs.py check exceeded GATES_CHECK_TIMEOUT=${limit}s and was killed; grep audit ran ($grep_hits hits). Raise GATES_CHECK_TIMEOUT or run the gate in the background. Partial log: $log"
    if [ -n "$abort" ]; then hint="$hint. The partial output already shows an abort: $abort"; fi
    emit sqa BLOCKED "$hits" "$hint"
    return 2
  fi
  if [ -n "$abort" ]; then
    hint="moosedocs.py check did not complete: $abort; grep audit ran ($grep_hits hits), the check gave no verdict on the diff; fix its environment (usually the app binary or the conda env) and re-run; log: $log"
    emit sqa BLOCKED "$hits" "$hint"
    return 2
  fi
  local total_err in_diff=0
  total_err="$(grep -c -E 'ERROR|CRITICAL|Traceback' "$WORK/check.txt" | tr -d ' ')"
  if [ -s "$WORK/files.txt" ]; then
    grep -F -f "$WORK/files.txt" "$WORK/check.txt" | sed 's/^/moosedocs check: /' >> "$hits"
    in_diff="$(grep -F -c -f "$WORK/files.txt" "$WORK/check.txt" | tr -d ' ')"
  fi
  hint="moosedocs.py check exit $rc, $total_err error lines total, $in_diff mention in-diff files; log: $log"
  if [ "$UNTRACKED_N" != 0 ]; then
    hint="$hint. $UNTRACKED_N untracked file(s): MooseDocs resolves links against git-tracked files, so 'does not exist in the repository' errors on them clear once staged"
  fi
  if [ -s "$hits" ]; then status=FAIL; else status=PASS; fi
  emit sqa "$status" "$hits" "$hint"
  [ "$status" = PASS ]
}

# ---------------------------------------------------------------- gate: ascii
gate_ascii() {
  local hits="$WORK/ascii.hits"
  : > "$hits"

  # Code scan: any byte outside 7-bit ASCII on an added line. CIVET's
  # precheck scoped the non-ASCII rule to code (idaholab/moose c12859fc3f,
  # May 2026, refs #32497): .md and .bib are exempt, so a diacritic like
  # Nedelec with its accent is correct there and a hit in code. Gold files
  # are excluded because they are generated output. No -CSD here: the byte
  # test is the point.
  perl -ne '
    my ($p, $n, $t) = split /\t/, $_, 3;
    next unless defined $t;
    next if $p =~ /\.(md|bib)$/ or $p =~ /gold/;
    my %seen; my @bad;
    while ($t =~ /([^\x00-\x7F])/g) { my $h = sprintf("\\x%02X", ord $1); push @bad, $h unless $seen{$h}++ }
    print "'"$REPO"'/$p:$n: non-ASCII byte(s) ", join(" ", @bad), "\n" if @bad;
  ' "$WORK/added.tsv" >> "$hits"

  # .md scan: only the invisible subset, which breaks grep, `!listing re=`
  # slicing, and citation matching. Every other non-ASCII character in .md
  # is fine. -CSD is load-bearing: without it perl compares undecoded bytes,
  # never sees a smart quote as one character, and matches NBSP only through
  # its trailing 0xA0 byte.
  perl -CSD -ne '
    my ($p, $n, $t) = split /\t/, $_, 3;
    next unless defined $t and $p =~ /\.md$/;
    my %name = (0x2018 => "smart quote", 0x2019 => "smart quote", 0x201C => "smart quote", 0x201D => "smart quote",
                0x00A0 => "NBSP", 0x202F => "NNBSP", 0x200B => "ZWSP", 0xFEFF => "BOM");
    my %seen; my @bad;
    while ($t =~ /([\x{2018}\x{2019}\x{201C}\x{201D}\x{00A0}\x{202F}\x{200B}\x{FEFF}])/g) {
      my $c = sprintf("U+%04X (%s)", ord $1, $name{ord $1}); push @bad, $c unless $seen{$c}++
    }
    print "'"$REPO"'/$p:$n: invisible character(s) ", join(" ", @bad), "\n" if @bad;
  ' "$WORK/added.tsv" >> "$hits"

  local status
  if [ -s "$hits" ]; then status=FAIL; else status=PASS; fi
  emit ascii "$status" "$hits"
  [ "$status" = PASS ]
}

# ---------------------------------------------------------------- gate: docs
gate_docs() {
  local hits="$WORK/docs.hits" docs_sh="$META/.claude/skills/moose-docs/scripts/docs.sh" rc=0 status
  : > "$hits"
  if [ "$CORE" = 1 ]; then
    emit docs SKIPPED "$hits" "docs smoke skipped by --core"
    return 0
  fi
  if [ ! -f "$docs_sh" ]; then
    emit docs BLOCKED "$hits" "missing $docs_sh"
    return 2
  fi
  # docs.sh owns the executable lookup, the conda/HPC routing, and the
  # --diff filter; it prints at most 20 lines and exits 0/1/2 like this script.
  bash "$docs_sh" "$SCOPE" smoke --diff "$BASE" 2>&1 | sed -e $'s/\x1b\\[[0-9;]*m//g' > "$hits"
  rc=${PIPESTATUS[0]}
  # Any code other than 0/1 (docs.sh's own 2, or a 127 when bash cannot run
  # it) is BLOCKED, and the return is normalized to 2 to match the record.
  case "$rc" in 0) status=PASS ;; 1) status=FAIL ;; *) status=BLOCKED; rc=2 ;; esac
  emit docs "$status" "$hits"
  return "$rc"
}

# ---------------------------------------------------------------- dispatch
collect_diff

case "$GATE" in
  sqa)   gate_sqa;   exit $? ;;
  ascii) gate_ascii; exit $? ;;
  docs)  gate_docs;  exit $? ;;
esac

# all: run every gate, then summarize. BLOCKED outranks FAIL: a blocked gate
# means the run has no complete verdict, and a FAIL summary would read as one
# while hiding the env problem the caller has to surface. Each gate's own line
# above still carries its FAIL. SKIPPED passes. Any code other than 0/1 counts
# as blocked, the same rule the docs gate applies to docs.sh.
WORST=0
for g in gate_sqa gate_ascii gate_docs; do
  rc=0; "$g" || rc=$?
  case "$rc" in
    0) ;;
    1) [ "$WORST" = 2 ] || WORST=1 ;;
    *) WORST=2 ;;
  esac
done
case "$WORST" in 0) S=PASS ;; 1) S=FAIL ;; *) S=BLOCKED ;; esac
jq -c -n --arg status "$S" '{gate:"all", status:$status}'
exit "$WORST"
