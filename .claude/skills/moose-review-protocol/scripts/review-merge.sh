#!/usr/bin/env bash
# Merge the per-reviewer findings JSON of one moose review into a single
# payload (pr mode) or markdown report (local mode), checking each reviewer's
# coverage ledger on the way.
#
# Usage: review-merge.sh --label <label> --mode <pr|local> [--pr <N>]
#
# Inputs (all written by review-snapshot.sh and the reviewer agents):
#   /tmp/moose-review-<label>-<bucket>.files        one repo-relative path per line
#   /tmp/moose-review-<label>-<bucket>.json         reviewer findings, first pass
#   /tmp/moose-review-<label>-<bucket>-retry.json   reviewer findings, retry (optional)
# for bucket in: code test doc ad dry newobj. The findings JSON shape and the
# two ledger invariants are defined once, in ../SKILL.md ("Output JSON schema"
# and "files_reviewed is a coverage ledger"). This script re-checks them:
#   1. files_reviewed[].path is set-equal to the bucket file (no extras, no
#      duplicates, nothing missing);
#   2. sum(files_reviewed[].inline) == length(inline_comments) and
#      sum(files_reviewed[].body) == length(body_findings).
#
# Pass selection when a retry exists: the retry wins when its ledger passes
# both checks; otherwise the pass with the complete file set; otherwise the
# pass covering more files (tie -> first pass). Findings that exist only in
# the pass not picked are merged in, keyed on (path, line, text), so a retry
# never silently loses a finding the first pass produced.
#
# Outputs:
#   pr mode    /tmp/moose-review-<label>-payload.json
#                {"body": <markdown>, "comments": [<GitHub review comments>]}
#              The body lists body_findings grouped by bucket, headings only
#              for buckets that produced any, and carries no process text: a
#              GitHub reader sees findings and nothing else. Comments keep
#              only the fields the GitHub reviews API accepts (path, body,
#              line, side, start_line, start_side); `kind` and anything else
#              is stripped because an unknown field can 422 the whole POST.
#              /tmp/moose-review-<label>-payload-buckets.json
#                one bucket name per comment, same order as `comments`, so
#              review-post.sh can demote a 422-rejected comment into the body
#              under the right bucket heading.
#   local mode /tmp/moose-review-<label>.md
#                every finding (inline and body) as
#                `path:line -- [required|suggested] text`; all six bucket
#              sections always present; reviewer failures and coverage gaps
#              stated inline because there is no separate summary artifact.
#   stdout     one summary JSON:
#                {"reviewers":{"<bucket>":{"inline":N,"body":M,"covered":F,
#                 "total":T,"ledger_ok":bool,"failed":null|"<reason>",
#                 "missing":[...]}, ...},
#                 "required":N,"suggested":M,"payload":<path|null>,
#                 "markdown":<path|null>,"post":bool,"pr":<N|null>}
#              A failed reviewer has inline/body null, never 0: unknown is not
#              clean. A bucket with total 0 had no files, so no reviewer ran.
#              `post` is false when there is nothing to post (clean review, or
#              local mode).
#
# `kind` on a finding is `required` or `suggested` (../SKILL.md). When a
# reviewer omitted it, the MOOSE reviewing convention decides: text opening
# with "I suggest" or "Consider" is a suggestion, anything else is required.
#
# Exit codes: 0 = merged, every expected reviewer wrote a JSON whose ledger
# passes; 1 = merged, but a reviewer failed or a ledger check did not pass
# (the summary says which; the orchestrator retries that reviewer once and
# re-runs this script); 2 = usage, or no snapshot files for the label.
#
# This script reads and writes only /tmp/moose-review-<label>* files, so it
# does not resolve the meta-root and never touches a repository.
# Bash 3.2 compatible (no associative arrays, no mapfile); needs jq.

set -uo pipefail

usage="usage: review-merge.sh --label <label> --mode <pr|local> [--pr <N>]"

label=""
mode=""
pr=""
# A value-taking option that is the last argument has nothing to consume:
# `shift 2` on one remaining positional fails and leaves $# unchanged, so the
# loop would never end. Check for the value before shifting.
while [[ $# -gt 0 ]]; do
  case "$1" in
    --label|--mode|--pr)
      [[ $# -ge 2 ]] || { echo "$usage" >&2; exit 2; }
      case "$1" in
        --label) label="$2" ;;
        --mode)  mode="$2" ;;
        --pr)    pr="$2" ;;
      esac
      shift 2 ;;
    -h|--help) echo "$usage"; exit 0 ;;
    *) echo "$usage" >&2; exit 2 ;;
  esac
done
if [[ -z "$label" || -z "$mode" ]]; then
  echo "$usage" >&2; exit 2
fi
case "$mode" in
  pr|local) ;;
  *) echo "$usage" >&2; exit 2 ;;
esac
if [[ -n "$pr" && ! "$pr" =~ ^[0-9]+$ ]]; then
  echo "$usage" >&2; exit 2
fi
# The label becomes part of /tmp file names; keep it to one path segment.
if [[ ! "$label" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "error: label must match [A-Za-z0-9._-]+ (got '$label')" >&2; exit 2
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "error: jq is required" >&2; exit 2
fi

prefix="/tmp/moose-review-${label}"
# Bucket order fixes the section order in the body and the markdown.
buckets="code test doc ad dry newobj"

# --- sanity: the snapshot must have run -------------------------------------
found=0
for b in $buckets; do
  [[ -f "${prefix}-${b}.files" ]] && found=1
done
if [[ $found -eq 0 ]]; then
  echo "error: no ${prefix}-<bucket>.files found; run review-snapshot.sh first" >&2
  exit 2
fi

tmp="$(mktemp -d "${TMPDIR:-/tmp}/moose-review-merge.XXXXXX")" || exit 2
trap 'rm -rf "$tmp"' EXIT

# --- per-bucket normalisation ----------------------------------------------
# One jq program per bucket: validate both passes, check the ledger of each,
# pick a pass, merge the other pass's unique findings, label every finding
# with its bucket and a normalised kind. Emits one object per bucket.
read -r -d '' NORMALIZE <<'JQ' || true
def text: (.body // .summary // "" | tostring);
def kindof:
  if (.kind == "required" or .kind == "suggested") then .kind
  elif (text | test("^\\s*(I suggest|Consider)\\b"; "i")) then "suggested"
  else "required" end;
def key: {path: .path, line: .line, text: text};
def valid:
  if type == "object" then
    (.inline_comments | type) == "array" and
    (.body_findings | type) == "array" and
    (.files_reviewed | type) == "array"
  else false end;
def want: [$files | split("\n")[] | select(length > 0)] | unique;
def check:
  . as $doc
  | want as $want
  | ($doc.files_reviewed | map(.path | tostring)) as $paths
  | ($paths | unique) as $upaths
  | {
      set_ok: ($upaths == $want and ($paths | length) == ($upaths | length)),
      count_ok: (
        (($doc.files_reviewed | map(.inline // 0) | add) // 0) == ($doc.inline_comments | length) and
        (($doc.files_reviewed | map(.body // 0) | add) // 0) == ($doc.body_findings | length)),
      covered: (($upaths - ($upaths - $want)) | length),
      missing: ($want - $upaths)
    }
  | .ok = (.set_ok and .count_ok)
  | .score = (if .ok then 3000 elif .set_ok then 2000 else 1000 end) + .covered;
def merge_into($picked; $other):
  ($picked.inline_comments | map(key)) as $hi
  | ($picked.body_findings | map(key)) as $hb
  | {
      inline_comments: ($picked.inline_comments
        + [$other.inline_comments[] | key as $k | select(any($hi[]; . == $k) | not)]),
      body_findings: ($picked.body_findings
        + [$other.body_findings[] | key as $k | select(any($hb[]; . == $k) | not)])
    };
def tag: map(. + {kind: kindof, bucket: $bucket});

($p[0] // null) as $primary
| ($r[0] // null) as $retry
| ($primary | valid) as $pv
| ($retry | valid) as $rv
| (if $pv then ($primary | check) else null end) as $pc
| (if $rv then ($retry | check) else null end) as $rc
| (want | length) as $total
# A file that parsed as an object but lacks the three arrays is a schema
# failure the bash probe cannot see, so its reason is added here.
| ([ (if $reason == "" then empty else $reason end),
     (if ($primary != null and ($pv | not)) then "schema mismatch in \($ppath): inline_comments, body_findings, files_reviewed must be arrays" else empty end),
     (if ($retry != null and ($rv | not)) then "schema mismatch in \($rpath): inline_comments, body_findings, files_reviewed must be arrays" else empty end)
   ] | join("; ")) as $why
| (
    if $pv and $rv then
      (if $rc.ok then "retry"
       elif $pc.score >= $rc.score then "primary"
       else "retry" end)
    elif $pv then "primary"
    elif $rv then "retry"
    else null end
  ) as $pick
| if $pick == null then
    {
      bucket: $bucket, total: $total, covered: 0, missing: want,
      # No files and no JSON: the bucket was skipped, so there is no ledger
      # to fail. Any other way to get here is a reviewer failure.
      ledger_ok: ($total == 0 and $p == [] and $r == []), source: null,
      failed: (if $total == 0 and $p == [] and $r == [] then null else $why end),
      inline_comments: [], body_findings: []
    }
  else
    (if $pick == "primary" then $primary else $retry end) as $doc
    | (if $pick == "primary" then $pc else $rc end) as $chk
    | (if $pick == "primary" then $retry else $primary end) as $otherdoc
    | (if ($pick == "primary" and $rv) or ($pick == "retry" and $pv)
       then merge_into($doc; $otherdoc)
       else {inline_comments: $doc.inline_comments, body_findings: $doc.body_findings} end) as $m
    | {
        bucket: $bucket, total: $total, covered: $chk.covered, missing: $chk.missing,
        ledger_ok: $chk.ok, source: $pick, failed: null,
        inline_comments: ($m.inline_comments | tag),
        body_findings: ($m.body_findings | tag)
      }
  end
JQ

# Classify one findings file: prints "file" when it parses as a JSON object,
# else "none" and appends the reason to the reasons file ($2).
probe() {
  if [[ -f "$1" ]]; then
    if jq -e 'type == "object"' "$1" >/dev/null 2>&1; then
      echo "file"
    else
      echo "unparseable or non-object JSON at $1" >> "$2"
      echo "none"
    fi
  else
    echo "no findings JSON at $1" >> "$2"
    echo "none"
  fi
}

any_bad=0
for b in $buckets; do
  files="${prefix}-${b}.files"
  primary="${prefix}-${b}.json"
  retry="${prefix}-${b}-retry.json"
  reasons="$tmp/$b.reasons"
  : > "$reasons"
  args=("--arg" "bucket" "$b")
  if [[ -f "$files" ]]; then
    args+=("--rawfile" "files" "$files")
  else
    args+=("--arg" "files" "")
  fi
  if [[ "$(probe "$primary" "$reasons")" == "file" ]]; then
    args+=("--slurpfile" "p" "$primary")
  else
    args+=("--argjson" "p" "[]")
  fi
  # A missing retry is the normal case and is not a failure reason; only an
  # unparseable retry file is worth reporting.
  if [[ -f "$retry" ]]; then
    if [[ "$(probe "$retry" "$reasons")" == "file" ]]; then
      args+=("--slurpfile" "r" "$retry")
    else
      args+=("--argjson" "r" "[]")
    fi
  else
    args+=("--argjson" "r" "[]")
  fi
  reason="$(tr '\n' ';' < "$reasons" | sed 's/;$//; s/;/; /g')"
  args+=("--arg" "reason" "$reason" "--arg" "ppath" "$primary" "--arg" "rpath" "$retry")
  if ! jq -n "${args[@]}" "$NORMALIZE" > "$tmp/$b.json" 2> "$tmp/$b.err"; then
    # jq itself failed (malformed but object-typed findings, e.g. a string
    # where an array belongs). Report it as a reviewer failure, not a crash.
    err="$(tr '\n' ' ' < "$tmp/$b.err")"
    total=0
    [[ -f "$files" ]] && total="$(grep -c . "$files" 2>/dev/null || true)"
    jq -n --arg bucket "$b" --argjson total "${total:-0}" --arg failed "findings JSON rejected: $err" \
      '{bucket:$bucket,total:$total,covered:0,missing:[],ledger_ok:false,source:null,failed:$failed,inline_comments:[],body_findings:[]}' \
      > "$tmp/$b.json"
  fi
done

jq -s '.' "$tmp/code.json" "$tmp/test.json" "$tmp/doc.json" "$tmp/ad.json" "$tmp/dry.json" "$tmp/newobj.json" > "$tmp/all.json"

# --- shared jq helpers for rendering ---------------------------------------
read -r -d '' RENDER_DEFS <<'JQ' || true
def heading: {code:"Code", test:"Tests", doc:"Docs", ad:"AD", dry:"Reuse", newobj:"Completeness"}[.];
def is_lens: . == "ad" or . == "dry" or . == "newobj";
# A multi-line range renders as path:start-end; a single line as path:line.
def loc:
  if (.start_line != null and .start_line != .line) then "\(.path):\(.start_line)-\(.line)"
  else "\(.path):\(.line)" end;
# Continuation lines (a ```suggestion fence, a second paragraph) are indented
# two spaces so the whole finding stays inside its list item.
def indented: (.body // .summary // "" | tostring | split("\n") | join("\n  "));
JQ

payload_path="null"
markdown_path="null"
post=false

if [[ "$mode" == "pr" ]]; then
  payload="${prefix}-payload.json"
  jq "$RENDER_DEFS"'
    ([ .[] | select(.body_findings | length > 0)
       | "### \(.bucket | heading)\n"
         + (.body_findings | map("- " + loc + " -- " + indented) | join("\n")) ]) as $sections
    | {
        body: (if ($sections | length) == 0 then ""
               else "## Out-of-line findings\n\n" + ($sections | join("\n\n")) + "\n" end),
        comments: [ .[] | .inline_comments[]
                    | {path, body, line, side, start_line, start_side}
                    | with_entries(select(.value != null)) ]
      }' "$tmp/all.json" > "$payload" || { echo "error: could not write $payload" >&2; exit 2; }
  jq '[ .[] | .inline_comments[] | .bucket ]' "$tmp/all.json" > "${prefix}-payload-buckets.json"
  if jq -e '(.comments | length) > 0 or (.body | length) > 0' "$payload" >/dev/null; then
    post=true
    payload_path="\"$payload\""
  else
    # Nothing to post: an empty pending review is noise and the API may
    # reject it. The payload file is removed so a stale one cannot be posted.
    rm -f "$payload" "${prefix}-payload-buckets.json"
  fi
else
  markdown="${prefix}.md"
  jq -r "$RENDER_DEFS"'
    def section:
      . as $r
      | ($r.bucket | heading) as $h
      | ([ $r.inline_comments[], $r.body_findings[] ]
          | map("- " + loc + " -- [" + .kind + "] " + indented)) as $items
      | ([ (if $r.failed != null then "- (reviewer failed: \($r.failed))" else empty end),
           (if ($r.failed == null and ($r.missing | length) > 0)
            then "- (incomplete coverage: did not review: \($r.missing | join(", ")))" else empty end),
           (if ($r.failed == null and ($r.ledger_ok | not) and ($r.missing | length) == 0)
            then "- (ledger counts did not match the findings arrays)" else empty end)
         ]) as $notes
      | "## \($h)\n"
        + (if $r.total == 0 and $r.failed == null and ($items | length) == 0 then
             (if ($r.bucket | is_lens) then "- (lens not triggered)"
              else "- (no \($r.bucket) files in this branch)" end)
           elif ($items | length) == 0 and ($notes | length) == 0 then "- (none)"
           else ($items + $notes | join("\n")) end);
    "# Local review -- \($label)\n\n" + (map(section) | join("\n\n")) + "\n"
  ' --arg label "$label" "$tmp/all.json" > "$markdown" || { echo "error: could not write $markdown" >&2; exit 2; }
  markdown_path="\"$markdown\""
fi

# --- summary ----------------------------------------------------------------
pr_json="null"
[[ -n "$pr" ]] && pr_json="$pr"
jq -c --argjson payload "$payload_path" --argjson markdown "$markdown_path" \
   --argjson post "$post" --argjson pr "$pr_json" '
  {
    reviewers: (map({
      key: .bucket,
      value: {
        inline: (if .failed == null then (.inline_comments | length) else null end),
        body: (if .failed == null then (.body_findings | length) else null end),
        covered: .covered,
        total: .total,
        ledger_ok: .ledger_ok,
        failed: .failed,
        missing: .missing
      }
    }) | from_entries),
    required: ([ .[] | .inline_comments[], .body_findings[] | select(.kind == "required") ] | length),
    suggested: ([ .[] | .inline_comments[], .body_findings[] | select(.kind == "suggested") ] | length),
    payload: $payload,
    markdown: $markdown,
    post: $post,
    pr: $pr
  }' "$tmp/all.json"

# Exit 1 when any reviewer that should have run failed or left a bad ledger.
# A skipped bucket (total 0, no JSON) has ledger_ok true, so it never trips.
if jq -e '[ .[] | select(.failed != null or (.ledger_ok | not)) ] | length > 0' \
     "$tmp/all.json" >/dev/null; then
  exit 1
fi
exit 0
