#!/usr/bin/env bash
# review-snapshot.sh -- capture the review snapshot the moose review orchestrator
# (moose-pr-reviewer) hands to its bucket and lens reviewers, then print one
# manifest JSON on stdout. This script is the single home of the bucket and
# lens regex table; agents call it instead of carrying awk in prose.
#
# Usage:
#   review-snapshot.sh --mode pr --pr <N> [--root <moose repo>]
#   review-snapshot.sh --mode local --root <repo> --base <ref> --label <label>
#
# Files written (label is pr-<N> in pr mode; P = /tmp/moose-review-<label>):
#   P.diff              unified diff the reviewers read
#   P.files             every changed path, repo-relative, sorted, unique
#   P-meta.json         gh pr view JSON (pr mode) or branch facts (local mode)
#   P-issues.md         linked-issue digest (pr mode only)
#   P-<bucket>.files    code test doc ad dry newobj
#
# Exit 0 = snapshot written. Exit 2 = bad args, empty diff, or a failed git/gh
# step (the message names it). Nothing here edits source, builds, or tests.

set -u

GH_REPO="idaholab/moose"   # the only repo the review skill accepts

usage() {
  echo "usage: review-snapshot.sh --mode pr --pr <N> [--root <moose repo>] | --mode local --root <repo> --base <ref> --label <label>" >&2
  exit 2
}

die() { echo "review-snapshot: $*" >&2; exit 2; }

# Meta-root: $CLAUDE_PROJECT_DIR, else walk up from $PWD to the first directory
# that holds .clangd (the rule scripts/moose-env.sh uses). It only supplies the
# pr-mode default for --root, which is <meta-root>/moose.
meta_root() {
  if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then printf '%s\n' "$CLAUDE_PROJECT_DIR"; return 0; fi
  local d="$PWD"
  while [ "$d" != "/" ] && [ ! -f "$d/.clangd" ]; do d="$(dirname "$d")"; done
  [ -f "$d/.clangd" ] || return 1
  printf '%s\n' "$d"
}

mode=""; pr=""; root=""; base=""; label=""
while [ $# -gt 0 ]; do
  case "$1" in
    --mode)  [ $# -ge 2 ] || usage; mode="$2";  shift 2 ;;
    --pr)    [ $# -ge 2 ] || usage; pr="$2";    shift 2 ;;
    --root)  [ $# -ge 2 ] || usage; root="$2";  shift 2 ;;
    --base)  [ $# -ge 2 ] || usage; base="$2";  shift 2 ;;
    --label) [ $# -ge 2 ] || usage; label="$2"; shift 2 ;;
    *) usage ;;
  esac
done

case "$mode" in
  pr)
    printf '%s' "$pr" | grep -Eq '^[0-9]+$' || usage
    [ -z "$base" ] && [ -z "$label" ] || usage
    if [ -z "$root" ]; then
      mr="$(meta_root)" || die "no --root and no meta-root (.clangd) above $PWD"
      root="$mr/moose"
    fi
    label="pr-$pr"
    ;;
  local)
    [ -n "$root" ] && [ -n "$base" ] && [ -n "$label" ] && [ -z "$pr" ] || usage
    ;;
  *) usage ;;
esac

# The label becomes part of /tmp file names; keep it to one path-safe token.
printf '%s' "$label" | grep -Eq '^[A-Za-z0-9._-]+$' || die "label must match [A-Za-z0-9._-]+: $label"
[ -d "$root/.git" ] || [ -f "$root/.git" ] || die "not a git checkout: $root"
root="$(cd "$root" && pwd)"

P="/tmp/moose-review-$label"
tracked=0; untracked=0; issues_path=""

if [ "$mode" = "pr" ]; then
  command -v gh >/dev/null 2>&1 || die "gh not found on PATH"
  # gh reads the repo from cwd; -R pins it to upstream so the fork's origin
  # never answers. The dirty-tree guard already ran in the moose-pr-review skill.
  ( cd "$root" && gh pr checkout "$pr" -R "$GH_REPO" ) || die "gh pr checkout $pr failed in $root"
  ( cd "$root" && gh pr diff "$pr" -R "$GH_REPO" ) > "$P.diff" || die "gh pr diff $pr failed"
  ( cd "$root" && gh pr diff "$pr" -R "$GH_REPO" --name-only ) > "$P.files" || die "gh pr diff --name-only $pr failed"
  ( cd "$root" && gh pr view "$pr" -R "$GH_REPO" \
      --json title,body,author,baseRefName,headRefName,commits ) > "$P-meta.json" \
    || die "gh pr view $pr failed"
  base="$(jq -r '.baseRefName // ""' "$P-meta.json")"
  sort -u -o "$P.files" "$P.files"
  tracked="$(wc -l < "$P.files" | tr -d ' ')"

  # Linked-issue digest. The linked issues are the author's spec; the reviewers
  # (the completeness lens especially) judge scope and coverage against them.
  # References come from the title, body, and commit headlines: #N (which also
  # covers closes/fixes/refs #N) and full idaholab/moose issue URLs. A fetch
  # failure is recorded in the digest, never fatal: the review does not block
  # on this step.
  issues_path="$P-issues.md"
  text="$(jq -r '.title, (.body // ""), (.commits[]? | .messageHeadline // "")' "$P-meta.json")"
  refs="$( { printf '%s\n' "$text" | grep -oE '#[0-9]+' | tr -d '#'
             printf '%s\n' "$text" | grep -oE "$GH_REPO/issues/[0-9]+" | grep -oE '[0-9]+$'; } \
           | grep -v -x "$pr" | sort -un )"
  : > "$issues_path"
  failed=""
  for n in $refs; do
    if issue="$(gh issue view "$n" -R "$GH_REPO" --json number,title,state,body 2>/dev/null)"; then
      {
        printf '## #%s -- %s (%s)\n\n' "$n" "$(printf '%s' "$issue" | jq -r '.title')" \
          "$(printf '%s' "$issue" | jq -r '.state')"
        # <=15 lines per issue keeps the digest a spec summary, not a second diff.
        printf '%s' "$issue" | jq -r '.body // ""' | tr -d '\r' | head -n 15
        printf '\n'
      } >> "$issues_path"
    else
      failed="$failed #$n"
    fi
  done
  if [ -z "$refs" ]; then
    echo "No linked issues." > "$issues_path"
  elif [ -n "$failed" ]; then
    echo "Failed to fetch:$failed" >> "$issues_path"
  fi
else
  # Local mode: /moose-build never commits and stages only gold, so the
  # feature's new files are typically untracked, and git diff ignores untracked
  # files in every form, as does git ls-files. A diff-only snapshot hands the
  # reviewers an empty or gold-only bucket and yields a confident, vacuous
  # "clean" review of code nobody read. Capture all four states: committed,
  # staged, unstaged (git diff <merge-base>) and untracked (git diff --no-index).
  # Never git add, git add -N, git stash, or git commit to make files visible;
  # the index belongs to the user's build.
  #
  # Diff against the merge base of <base> and HEAD, not <base> itself. A plain
  # `git diff <base>` also emits the reverse of every commit <base> gained
  # after the branch point, so a devel that moved 40 commits shows 150+ files
  # of upstream drift as if the author wrote them (apptainer/*.def, conda
  # meta.yaml, moose.mk, ...) and swamps the buckets. The two-dot form against
  # the merge base still sees the working tree (staged + unstaged), which the
  # three-dot form `<base>...HEAD` would not.
  git -C "$root" rev-parse --verify -q "$base^{commit}" >/dev/null || die "unknown base ref '$base' in $root"
  branch="$(git -C "$root" rev-parse --abbrev-ref HEAD)"
  mb="$(git -C "$root" merge-base "$base" HEAD)" || die "no merge base between '$base' and HEAD in $root"
  git -C "$root" diff "$mb" > "$P.diff"                        # committed + staged + unstaged
  git -C "$root" diff "$mb" --name-only > "$P.files"
  git -C "$root" ls-files --others --exclude-standard > "$P.untracked"
  tracked="$(sort -u "$P.files" | wc -l | tr -d ' ')"
  untracked="$(grep -c . "$P.untracked" | tr -d ' ')"
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    git -C "$root" diff --no-index -- /dev/null "$f" >> "$P.diff" 2>/dev/null
    echo "$f" >> "$P.files"
  done < "$P.untracked"
  sort -u -o "$P.files" "$P.files"
  jq -n --arg mode local --arg root "$root" --arg base "$base" --arg mb "$mb" --arg branch "$branch" --arg label "$label" \
    '{mode:$mode, root:$root, base:$base, merge_base:$mb, branch:$branch, label:$label}' > "$P-meta.json"
fi

[ -s "$P.diff" ] || die "empty diff for $label ($root vs ${base:-?}); nothing to review"

# Bucket regex table (moved verbatim from moose-pr-reviewer.md steps 2 and 2b).
# Match on shape, not on a test/tests/ prefix: CI-run specs and inputs also live
# under modules/*/examples/, modules/*/tutorials/, and python/*/test/, and
# anchoring to test/tests/ silently drops them. A file lands in zero or one
# exclusive bucket:
#   test  basename exactly `tests`; any *.i; any path containing /gold/. First.
#   code  .C .h .py .K anywhere (production, test/src/, unit/src/ all count;
#         .K is Kokkos C++ under framework/src/kokkos/).
#   doc   any *.md (the doc reviewer scopes structural checks itself).
# Files matching none (.yml .yaml .json .sh .mk .bib, binary meshes, images)
# are "unrouted". Around 4-5% of a typical PR lands there legitimately;
# markedly more means the classifier missed a shape.
TEST_RE='(^|/)tests$|\.i$|/gold/'
grep -E "$TEST_RE" "$P.files" > "$P-test.files"
grep -Ev "$TEST_RE" "$P.files" | grep -E '\.(C|h|py|K)$' > "$P-code.files"
grep -Ev "$TEST_RE" "$P.files" | grep -E '\.md$' > "$P-doc.files"
cat "$P-test.files" "$P-code.files" "$P-doc.files" | grep -v -Fxf - "$P.files" > "$P.unrouted"

# Lens buckets: derived views, never exclusive. A file may appear in a lens
# bucket and its exclusive bucket; lenses re-read code files through a
# narrower, deeper bar. Triggers are cheap signals in the diff's ADDED lines.
# An empty lens bucket means the lens does not spawn; most PRs fire none.
D="$P.diff"

# ad: derivative correctness (moose-ad-reviewer). Code-bucket files whose added
# lines touch AD or residual/Jacobian code.
awk -v pat='ADReal|ADRank|ADVariable|adCoupled|declareADProperty|getADMaterialProperty|GenericReal|GenericMaterialProperty|raw_value|MetaPhysicL|computeQpResidual|computeQpJacobian|computeQpOffDiagJacobian' \
  '/^\+\+\+ b\//{f=substr($0,7)} /^\+/ && $0 ~ pat {print f}' "$D" \
  | sort -u | grep -Fxf - "$P-code.files" > "$P-ad.files"

# dry: reuse (moose-dry-reviewer). Code-bucket files the change adds outright,
# plus existing files whose added lines register new objects.
{ awk '/^--- \/dev\/null/{n=1; next} n && /^\+\+\+ b\//{print substr($0,7)} {n=0}' "$D"
  awk '/^\+\+\+ b\//{f=substr($0,7)} /^\+/ && /registerMooseObject/{print f}' "$D"; } \
  | sort -u | grep -Fxf - "$P-code.files" > "$P-dry.files"

# newobj: completeness (moose-completeness-reviewer). Code-bucket files whose
# added lines register an object or action. Each new registration drives an
# absence check (doc stub page, addClassDescription, any test coverage) that no
# changed-file bucket can see.
awk '/^\+\+\+ b\//{f=substr($0,7)} /^\+/ && /register(AD)?MooseObject|registerMooseAction/{print f}' "$D" \
  | sort -u | grep -Fxf - "$P-code.files" > "$P-newobj.files"

buckets='{}'
for b in code test doc ad dry newobj; do
  n="$(wc -l < "$P-$b.files" | tr -d ' ')"
  buckets="$(jq -n --argjson acc "$buckets" --arg b "$b" --arg p "$P-$b.files" --argjson n "$n" \
    '$acc + {($b): {path: $p, count: $n}}')"
done
unrouted="$(jq -R . "$P.unrouted" | jq -s .)"

jq -n --arg label "$label" --arg mode "$mode" --arg root "$root" --arg base "$base" \
  --arg diff "$P.diff" --arg files "$P.files" --arg meta "$P-meta.json" --arg issues "$issues_path" \
  --argjson tracked "$tracked" --argjson untracked "$untracked" \
  --argjson buckets "$buckets" --argjson unrouted "$unrouted" \
  '{label:$label, mode:$mode, root:$root, base:$base, diff_path:$diff, files_path:$files,
    meta_path:$meta, issues_path:(if $issues == "" then null else $issues end),
    tracked:$tracked, untracked:$untracked, buckets:$buckets, unrouted:$unrouted}'
