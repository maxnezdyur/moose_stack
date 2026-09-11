#!/bin/bash
# PostToolUse hook (matcher Edit|Write): scan the lines ADDED to the file the
# tool just wrote and report, on stderr with exit 2, anything CIVET or the
# MOOSE standards would reject. PostToolUse cannot block, so exit 2 is
# feedback to the model, not a gate; gates.sh stays the authoritative scan.
#
# Checks, chosen by the path of the written file:
#   tests                     legacy HIT delimiters `[./name]` / `[../]`,
#                             plus non-ASCII bytes
#   *.C *.h *.py *.i          non-ASCII bytes (CIVET rejects any byte >0x7F
#                             in code files; .md and .bib are exempt since
#                             idaholab/moose c12859fc3f, May 2026, #32497)
#   */doc/content/**/*.md     the invisible subset only: smart quotes
#                             U+2018/2019/201C/201D, NBSP U+00A0,
#                             NNBSP U+202F, ZWSP U+200B, BOM U+FEFF.
#                             Scoped to doc/content so it never fires on
#                             .claude/** or README files.
#
# Basis is the git diff of the file, not its contents, so editing one of the
# ~800 legacy specs (or a page that already carries a smart quote) for an
# unrelated reason stays silent: only lines this session adds can trip a
# check. Tracked files use `git diff HEAD -U0` (staged + unstaged);
# untracked files count as entirely added; outside a git work tree the text
# the tool wrote is scanned instead (line numbers are then relative to that
# text, not the file).
#
# Fails open: missing jq/perl/git, unparsable input, or any internal error
# exits 0 rather than interrupting work. `set -u` only; no pipefail, because
# a scan that finds nothing must not read as an error.

set -u

usage() {
  echo "usage: $0 < hook-input.json   (PostToolUse Edit|Write hook; reads the tool input JSON on stdin)" >&2
  exit 2
}

# The hook takes no arguments. Any argument, or an interactive stdin with
# nothing piped in, is a human calling it by hand: show usage.
[ "$#" -eq 0 ] || usage
[ -t 0 ] && usage

command -v jq >/dev/null 2>&1 || exit 0
command -v perl >/dev/null 2>&1 || exit 0

input=$(cat)
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -n "$path" ] || exit 0

base=$(basename "$path")
check_legacy=0
check_ascii=0
check_invisible=0
case "$base" in
  tests)                check_legacy=1; check_ascii=1 ;;
  *.C|*.h|*.py|*.i)     check_ascii=1 ;;
  *.md)
    case "$path" in
      */doc/content/*)  check_invisible=1 ;;
      *)                exit 0 ;;
    esac ;;
  *)                    exit 0 ;;
esac

# Added lines are collected as "<line>\t<text>" so findings can carry the
# file line number. Only the first tab is a separator; the text may hold
# more tabs.
dir=$(dirname "$path")
added=""

if [ -d "$dir" ] && git -C "$dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if git -C "$dir" ls-files --error-unmatch "$path" >/dev/null 2>&1; then
    # Tracked: '+' lines of the -U0 diff vs HEAD. Each hunk header
    # `@@ -a[,b] +c[,d] @@` gives the new-file line number of the first
    # added line that follows it.
    added=$(git -C "$dir" diff HEAD -U0 -- "$path" 2>/dev/null | awk '
      /^@@ / { split($3, h, ","); n = substr(h[1], 2) + 0; next }
      /^\+\+\+ / { next }
      /^\+/ { printf "%d\t%s\n", n, substr($0, 2); n++ }')
  else
    # Untracked: the whole file is new.
    added=$(awk '{ printf "%d\t%s\n", NR, $0 }' "$path" 2>/dev/null)
  fi
else
  # Not in git: scan just the text this tool call wrote. Write gives
  # `content`; Edit gives `new_string`.
  added=$(printf '%s' "$input" \
    | jq -r '.tool_input | (.new_string // .content // "")' 2>/dev/null \
    | awk '{ printf "%d\t%s\n", NR, $0 }')
fi

[ -n "$added" ] || exit 0

findings=""

if [ "$check_legacy" -eq 1 ]; then
  # `[./name]` / `[../]` are vestigial HIT path-navigation tokens. They parse
  # identically to `[name]` / `[]` but are legacy. Trailing whitespace and a
  # comment are allowed after the closing bracket.
  hits=$(printf '%s\n' "$added" | perl -ne '
    my ($n, $t) = split /\t/, $_, 2;
    chomp $t;
    if ($t =~ /^\s*\[(\.\/[^\]]*|\.\.\/)\]\s*(#.*)?$/) {
      (my $s = $t) =~ s/^\s+//;
      print "$n: legacy HIT delimiter: $s\n";
    }' 2>/dev/null)
  if [ -n "$hits" ]; then
    findings="${findings}Legacy HIT block delimiters on lines added to ${path}:
$(printf '%s\n' "$hits" | sed "s|^|  ${path}:|")
New blocks use [name] ... [] -- not [./name] ... [../]. Renames count as new blocks.
Fix only the lines you added; leave the file's pre-existing legacy blocks alone
(whole-file conversion inflates the diff and destroys blame).

"
  fi
fi

if [ "$check_ascii" -eq 1 ]; then
  # Byte scan, no -C flags: perl sees raw bytes, so any byte 0x80-0xFF is a
  # non-ASCII byte regardless of whether the file is valid UTF-8. The hex
  # values are printed because the offending characters are often invisible
  # or look like their ASCII neighbours (smart quotes, NBSP, en dash).
  hits=$(printf '%s\n' "$added" | perl -ne '
    my ($n, $t) = split /\t/, $_, 2;
    chomp $t;
    if ($t =~ /[\x80-\xFF]/) {
      my %seen; my @b;
      while ($t =~ /([\x80-\xFF]+)/g) {
        my $h = join " ", map { sprintf "0x%02X", ord } split //, $1;
        push @b, $h unless $seen{$h}++;
      }
      (my $s = $t) =~ s/[\x80-\xFF]/?/g;
      print "$n: non-ASCII bytes (" . join("; ", @b) . "): $s\n";
    }' 2>/dev/null)
  if [ -n "$hits" ]; then
    findings="${findings}Non-ASCII bytes on lines added to ${path} (CIVET rejects them in code files):
$(printf '%s\n' "$hits" | sed "s|^|  ${path}:|")
Replace with the 7-bit ASCII equivalent (straight quotes, -- or a comma for a dash, plain space).

"
  fi
fi

if [ "$check_invisible" -eq 1 ]; then
  # -CSD decodes stdin as UTF-8 so the regex matches code points, not bytes;
  # without it the same pattern would silently match nothing. Only the
  # invisible subset is checked: accented letters, arrows and math symbols
  # are legitimate in doc pages.
  hits=$(printf '%s\n' "$added" | perl -CSD -ne '
    my %name = (0x2018 => "left single quote", 0x2019 => "right single quote",
                0x201C => "left double quote", 0x201D => "right double quote",
                0x00A0 => "no-break space",    0x202F => "narrow no-break space",
                0x200B => "zero-width space",  0xFEFF => "byte order mark");
    my ($n, $t) = split /\t/, $_, 2;
    chomp $t;
    if ($t =~ /[\x{2018}\x{2019}\x{201C}\x{201D}\x{00A0}\x{202F}\x{200B}\x{FEFF}]/) {
      my %seen; my @c;
      while ($t =~ /([\x{2018}\x{2019}\x{201C}\x{201D}\x{00A0}\x{202F}\x{200B}\x{FEFF}])/g) {
        my $cp = ord $1;
        push @c, sprintf("U+%04X %s", $cp, $name{$cp}) unless $seen{$cp}++;
      }
      (my $s = $t) =~ s/[\x{2018}\x{2019}\x{201C}\x{201D}\x{00A0}\x{202F}\x{200B}\x{FEFF}]/<?>/g;
      print "$n: invisible character (" . join("; ", @c) . "): $s\n";
    }' 2>/dev/null)
  if [ -n "$hits" ]; then
    findings="${findings}Invisible characters on lines added to ${path}:
$(printf '%s\n' "$hits" | sed "s|^|  ${path}:|")
Use straight quotes and plain spaces; <?> marks each offending character above.

"
  fi
fi

[ -n "$findings" ] || exit 0

printf '%s' "$findings" >&2
exit 2
