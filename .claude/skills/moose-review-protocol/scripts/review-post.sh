#!/usr/bin/env bash
# review-post.sh -- POST one PENDING GitHub review for an idaholab/moose PR from
# the merged payload review-merge.sh wrote, and print one JSON result line.
#
# Usage:
#   review-post.sh --pr <N> --payload <payload.json>
#
# payload.json is {"body": "<markdown>", "comments": [<inline comment>, ...]}.
# The request never carries an `event` field: omitting it leaves the review
# PENDING, so the user submits it from the GitHub UI. This script never uses
# `gh pr review` and never submits.
#
# 422 handling: GitHub rejects the whole review when one inline comment does not
# anchor on a diff line ("line must be part of the diff"). The rejected comment
# is not dropped: it moves into the body as a bullet under its bucket heading
# (creating `## Out-of-line findings` and the `### <Bucket>` section when the
# merged body omitted them), and the review is re-POSTed exactly once. A comment
# is never relocated to a different line.
#
# Bucket sidecar: the payload's comments carry no `bucket` (review-merge.sh
# strips it because GitHub 422s unknown keys). The bucket names live in the
# payload path with -payload.json replaced by -payload-buckets.json: a JSON
# array with one name per comment in `comments` order (code, test, doc, ad,
# dry, newobj). The demotion step takes the heading for comment i from
# sidecar[i]; without a usable sidecar it classifies by path shape instead.
# Dropping comment i from `comments` drops sidecar[i] too, so the retry and
# its sidecar stay index-aligned.
#
# Output (stdout, one line):
#   {"posted":true,"demoted":K,"url":"<review html_url>"}      exit 0
#   {"posted":false,"error":"<reason>"}                        exit 1
# Bad arguments or an unusable payload print usage / an error and exit 2.
#
# Files written beside the payload: <payload>-request.json (the exact body sent,
# `event`-free), <payload>-retry.json (the demoted request, only on a 422),
# <payload>-retry-buckets.json (the sidecar trimmed to the retry's comments,
# only on a 422 and only when the sidecar was read), and
# <payload>-response.json (the last API response).

set -u

GH_REPO="idaholab/moose"   # the only repo the review skill accepts
# Test seam: point at a fake gh to exercise the 422 path without the network.
GH="${REVIEW_POST_GH:-gh}"

usage() {
  echo "usage: review-post.sh --pr <N> --payload <payload.json>" >&2
  exit 2
}

die() { echo "review-post: $*" >&2; exit 2; }

# Failure result: one JSON line on stdout, exit 1. The reason is a plain string
# so the orchestrator can print it in its summary verbatim.
fail() {
  jq -n -c --arg e "$1" '{posted:false, error:$e}'
  exit 1
}

# Meta-root: $CLAUDE_PROJECT_DIR, else walk up from $PWD to the first directory
# that holds .clangd (the rule scripts/moose-env.sh uses). gh takes the repo
# explicitly, so the root only supplies a stable cwd inside the moose checkout
# (gh then reads that checkout's host config); missing root is not fatal.
meta_root() {
  if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then printf '%s\n' "$CLAUDE_PROJECT_DIR"; return 0; fi
  local d="$PWD"
  while [ "$d" != "/" ] && [ ! -f "$d/.clangd" ]; do d="$(dirname "$d")"; done
  [ -f "$d/.clangd" ] || return 1
  printf '%s\n' "$d"
}

pr=""; payload=""
while [ $# -gt 0 ]; do
  case "$1" in
    --pr)      [ $# -ge 2 ] || usage; pr="$2";      shift 2 ;;
    --payload) [ $# -ge 2 ] || usage; payload="$2"; shift 2 ;;
    *) usage ;;
  esac
done
printf '%s' "$pr" | grep -Eq '^[0-9]+$' || usage
[ -n "$payload" ] || usage
[ -f "$payload" ] || die "payload not found: $payload"
command -v jq >/dev/null 2>&1 || die "jq not found on PATH"
command -v "$GH" >/dev/null 2>&1 || die "gh not found on PATH"
jq -e 'type == "object" and ((.comments // []) | type == "array") and ((.body // "") | type == "string")' \
  "$payload" >/dev/null 2>&1 || die "payload is not {body: string, comments: array}: $payload"

# Nothing to post is review-merge's call (its summary says post:false); an empty
# pending review is noise and the API may reject it, so refuse rather than try.
if jq -e '((.body // "") == "") and ((.comments // []) | length == 0)' "$payload" >/dev/null; then
  die "payload has no body and no comments; nothing to post"
fi

workdir="$PWD"
if mr="$(meta_root)" && [ -d "$mr/moose" ]; then workdir="$mr/moose"; fi

stem="${payload%.json}"
request="$stem-request.json"
retry="$stem-retry.json"
response="$stem-response.json"
stderr_file="$stem-stderr.txt"
# $stem is the payload path without .json, so for the standard name
# /tmp/moose-review-<label>-payload.json this is exactly the sidecar
# review-merge.sh wrote: /tmp/moose-review-<label>-payload-buckets.json.
buckets_file="$stem-buckets.json"
retry_buckets="$stem-retry-buckets.json"

# The request carries only what the reviews endpoint accepts. Reviewer-side
# fields (kind, bucket, agent) stay in the payload for the demotion step but
# would draw a 422 ("is not a permitted key") if sent, and `event` is dropped
# on purpose: its absence is what keeps the review PENDING.
to_request='{
  body: (.body // ""),
  comments: [ (.comments // [])[]
    | with_entries(select(.key | IN("path", "body", "line", "side", "start_line", "start_side", "position"))) ]
}'

# post <request file>: run the API call from the moose checkout, keep the body
# and stderr, and return gh's exit status (non-2xx responses exit 1).
post() {
  ( cd "$workdir" && "$GH" api -X POST "repos/$GH_REPO/pulls/$pr/reviews" --input "$1" ) \
    >"$response" 2>"$stderr_file"
}

# is_422: gh prints "gh: <message> (HTTP 422)" on stderr and the error body
# (with "status":"422") on stdout; either is enough.
is_422() {
  grep -q 'HTTP 422' "$stderr_file" 2>/dev/null && return 0
  jq -e '.status == "422"' "$response" >/dev/null 2>&1
}

# error_text: message plus every entry of the errors array (strings or objects)
# joined with "; ", falling back to gh's stderr when the body is not JSON.
error_text() {
  local t
  t="$(jq -r '[.message // empty]
    + ((.errors // []) | map(if type == "string" then . else (.message // tostring) end))
    | join("; ")' "$response" 2>/dev/null)"
  [ -n "$t" ] || t="$(head -n 3 "$stderr_file" 2>/dev/null | tr '\n' ' ')"
  [ -n "$t" ] || t="gh api exited non-zero with no output"
  printf '%s' "$t"
}

# success <demoted>: print the result line from the API response and exit 0.
success() {
  jq -c --argjson k "$1" --arg fb "https://github.com/$GH_REPO/pull/$pr/files" \
    '{posted:true, demoted:$k, url:(.html_url // $fb)}' "$response"
  exit 0
}

# hunks_json: the diff hunks as [{path, side, start, end}] so the demotion step
# can tell which comment GitHub refused. The 422 message ("Pull request review
# thread line must be part of the diff") does not say which comment, so the
# script re-derives the answer from the diff. It prefers the snapshot diff the
# reviewers read (/tmp/moose-review-pr-<N>.diff, written by review-snapshot.sh)
# and falls back to `gh pr diff`. Prints nothing when neither is available.
hunks_json() {
  local diff="/tmp/moose-review-pr-$pr.diff"
  if [ ! -s "$diff" ]; then
    diff="$stem-prdiff.patch"
    ( cd "$workdir" && "$GH" pr diff "$pr" --repo "$GH_REPO" ) >"$diff" 2>/dev/null || return 1
    [ -s "$diff" ] || return 1
  fi
  # Both sides key on the new path (GitHub addresses LEFT-side comments by the
  # file's new path too); a deleted file has no new path, so its old path is
  # used. Counts default to 1 when the hunk header omits them (@@ -3 +3 @@).
  awk '
    /^--- / { old = $0; sub(/^--- (a\/)?/, "", old); next }
    /^\+\+\+ / { new = $0; sub(/^\+\+\+ (b\/)?/, "", new)
                 path = (new == "/dev/null") ? old : new; next }
    /^@@ / {
      l = $2; sub(/^-/, "", l); r = $3; sub(/^\+/, "", r)
      nl = split(l, la, ","); nr = split(r, ra, ",")
      lc = (nl > 1) ? la[2] : 1; rc = (nr > 1) ? ra[2] : 1
      if (lc > 0) printf "%s\tLEFT\t%d\t%d\n", path, la[1], la[1] + lc - 1
      if (rc > 0) printf "%s\tRIGHT\t%d\t%d\n", path, ra[1], ra[1] + rc - 1
    }' "$diff" \
  | jq -R -s 'split("\n") | map(select(length > 0) | split("\t")
      | {path: .[0], side: .[1], start: (.[2] | tonumber), end: (.[3] | tonumber)})'
}

# buckets_json: the bucket sidecar as a compact JSON array, or "null" when it
# cannot be trusted: absent, not a JSON array, or a different length from
# `comments` (then index i of one would not describe index i of the other).
# "null" makes the demotion step fall back to path-shape classification, the
# pre-sidecar behavior. Always exits 0; the reason for a fallback goes to
# stderr so a wrong heading can be traced.
buckets_json() {
  local b n_c n_b
  if [ ! -f "$buckets_file" ]; then printf 'null'; return 0; fi
  # -e exits 4 when select() produced nothing (not an array) and 2 on bad JSON.
  if ! b="$(jq -e -c 'select(type == "array")' "$buckets_file" 2>/dev/null)"; then
    echo "review-post: ignoring $buckets_file: not a JSON array" >&2
    printf 'null'; return 0
  fi
  n_c="$(jq '(.comments // []) | length' "$payload")"
  n_b="$(printf '%s' "$b" | jq 'length')"
  if [ "$n_b" != "$n_c" ]; then
    echo "review-post: ignoring $buckets_file: $n_b entries for $n_c comments" >&2
    printf 'null'; return 0
  fi
  printf '%s' "$b"
}

# demote: read the payload, move every comment that the 422 named or that the
# hunk table cannot anchor into the body, and print {demoted, payload, buckets}.
# $hunks == null means the diff was unavailable; then only named comments move.
# $buckets is the sidecar array (see buckets_json) or null.
demote_jq='
# heading($sb): $sb is the sidecar bucket for this comment (null when the
# sidecar was unusable). A bucket/agent field still on the comment is the next
# choice, so a hand-built payload that kept them keeps working; the last
# resort is the path shape.
def heading($sb):
  (($sb // .bucket // .agent // "") | tostring | ascii_downcase) as $b
  | if   $b == "code" then "### Code"
    elif $b == "test" then "### Tests"
    elif $b == "doc"  then "### Docs"
    elif $b == "ad"   then "### AD"
    elif $b == "dry"  then "### Reuse"
    elif $b == "newobj" or $b == "completeness" or $b == "compl" then "### Completeness"
    elif $b != "" then "### " + ($b[0:1] | ascii_upcase) + $b[1:]
    # No bucket from the sidecar or the comment: classify by path shape with
    # the exclusive-bucket table from review-snapshot.sh (test first, then
    # doc, else code). This cannot tell a lens finding (ad, dry, newobj) on a
    # .C file from a code finding, which is why the sidecar comes first.
    elif (.path | test("(^|/)tests$|\\.i$|/gold/")) then "### Tests"
    elif (.path | test("\\.md$")) then "### Docs"
    else "### Code" end;
def loc:
  if (.start_line != null and .start_line != .line) then "\(.path):\(.start_line)-\(.line)"
  else "\(.path):\(.line)" end;
# Continuation lines are indented so a multi-line comment (suggestion fence
# included) stays inside its bullet.
def bullet: "- " + loc + " -- " + ((.body // "") | split("\n") | join("\n  "));
def in_hunk($p; $s; $l):
  any($hunks[]; .path == $p and .side == $s and .start <= $l and $l <= .end);
def anchored:
  if $hunks == null or .line == null then true
  else (.side // "RIGHT") as $s
    | in_hunk(.path; $s; .line)
      and ((.start_line == null) or in_hunk(.path; (.start_side // $s); .start_line))
  end;
def named: (.path // "") as $p | ($p | length) > 0 and ($err | contains($p));
def rejected: named or (anchored | not);
def add_to_body($h; $b):
  (if . == "" then "## Out-of-line findings" else . end)
  | split("\n") as $lines
  | ($lines | index([$h])) as $i
  | if $i == null then ($lines | until(length == 0 or .[-1] != ""; .[:-1])) + ["", $h, $b]
    else
      # The section ends at the next heading; trailing blank lines are trimmed
      # so the bullet joins the existing list.
      ([range($i + 1; $lines | length) | select($lines[.] | test("^#{2,3} "))] | first // ($lines | length)) as $j
      | ($lines[0:$j] | until(length == 0 or .[-1] != ""; .[:-1])) + [$b]
        + (if $j < ($lines | length) then [""] + $lines[$j:] else [] end)
    end
  | join("\n");
# Work by index so the sidecar is consulted and trimmed in step with
# `comments`: $bad lists the rejected indices, $keep the survivors.
. as $p
| ($p.comments // []) as $cs
| [ range($cs | length) | select($cs[.] | rejected) ] as $bad
| [ range($cs | length) | select(IN($bad[]) | not) ] as $keep
| { demoted: ($bad | length),
    payload: {
      body: (reduce $bad[] as $i ($p.body // "";
               add_to_body($cs[$i] | heading($buckets[$i]); $cs[$i] | bullet))),
      comments: [ $keep[] | $cs[.] ] },
    # The sidecar with the same indices dropped, so retry comment j and
    # buckets[j] still describe the same finding; null when it was not read.
    buckets: (if $buckets == null then null else [ $keep[] | $buckets[.] ] end) }'

# First attempt.
jq "$to_request" "$payload" >"$request" || die "could not build the request from $payload"
if post "$request"; then success 0; fi
is_422 || fail "$(error_text)"

# 422: work out which comment GitHub refused, move it into the body, re-POST once.
err="$(error_text)"
hunks="$(hunks_json)" || hunks="null"
buckets="$(buckets_json)"
demoted_json="$(jq -c --arg err "$err" --argjson hunks "$hunks" --argjson buckets "$buckets" \
  "$demote_jq" "$payload")" \
  || fail "422 ($err); demotion step failed on $payload"
k="$(printf '%s' "$demoted_json" | jq '.demoted')"
[ "$k" -gt 0 ] 2>/dev/null || fail "422 ($err); could not identify the rejected comment, nothing demoted"

# One rewrite per retry: the request, plus the trimmed sidecar when one was
# read. Nothing downstream re-reads the sidecar (the review is re-POSTed once);
# it is kept so the retry can be checked against its buckets after the fact.
printf '%s' "$demoted_json" | jq '.payload' | jq "$to_request" >"$retry" \
  || fail "422 ($err); could not write $retry"
[ "$buckets" = "null" ] || printf '%s' "$demoted_json" | jq '.buckets' >"$retry_buckets"
if post "$retry"; then success "$k"; fi
fail "422 ($err); retry after demoting $k comment(s) failed: $(error_text)"
