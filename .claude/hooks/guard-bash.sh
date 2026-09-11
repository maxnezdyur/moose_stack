#!/bin/bash
# PreToolUse hook (matcher: Bash). Denies, for subagents only, the Bash
# commands that publish work to GitHub: git push, gh pr ready, gh pr merge,
# gh pr review that submits an event, and gh api POSTs to /reviews that carry
# an event. Publishing is a main-thread action behind a human gate
# (/moose-ship, the GitHub UI); subagents report what is ready instead.
#
# Scope: the hook input carries `agent_type` only when the tool call comes
# from a subagent. Without it (main thread) the hook allows everything.
#
# Exit codes: 0 = allow, 2 = deny (Claude Code reads the stderr line as the
# reason). Bad invocation (arguments, or no piped input) prints usage and
# exits 2 as well.
#
# Fails open: missing jq, unreadable input, or an empty command exit 0 so an
# internal error never blocks unrelated work. A pattern miss is not an error;
# the reviewers' tool lists and their boundary sentence stay as the second layer.

set -u

usage() {
  echo "usage: guard-bash.sh  (PreToolUse hook; reads the Bash tool-call JSON on stdin, no arguments)" >&2
  exit 2
}

[ "$#" -eq 0 ] || usage
[ -t 0 ] && usage

command -v jq >/dev/null 2>&1 || exit 0

input=$(cat)
[ -n "$input" ] || exit 0

# Main thread untouched: no agent_type (or an empty one) means allow.
agent_type=$(printf '%s' "$input" | jq -r '.agent_type // empty' 2>/dev/null) || exit 0
[ -n "$agent_type" ] || exit 0

# Defensive: the matcher already restricts to Bash, but a misconfigured
# settings.json must not turn this into a blanket deny for other tools.
tool_name=$(printf '%s' "$input" | jq -r '.tool_name // "Bash"' 2>/dev/null) || exit 0
[ "$tool_name" = "Bash" ] || exit 0

cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null) || exit 0
[ -n "$cmd" ] || exit 0

# Word-start guard so `mygit push` or `./gh` do not match; the token loop
# `([[:space:]]+[^[:space:]]+)*` lets global options sit between the binary
# and the subcommand (`git -C dir push`, `gh -R owner/repo pr merge`).
# The word-end guard mirrors it: `pushup` and `push-something` stay allowed,
# but a quote, `)`, `>` or end of segment right after the subcommand still
# matches, so `bash -c 'git push'`, `$(git push)`, `(git push)` and
# `git push>/dev/null` are denied.
W='(^|[^[:alnum:]_./-])'
TOK='([[:space:]]+[^[:space:]]+)*[[:space:]]+'
END='([^[:alnum:]_-]|$)'

GIT_PUSH="${W}git${TOK}push${END}"
GH_PR_READY_MERGE="${W}gh${TOK}pr[[:space:]]+(ready|merge)${END}"
GH_PR_REVIEW="${W}gh${TOK}pr[[:space:]]+review${END}"
# gh accepts the short forms -a/-r/-c for the three submitting flags; a bare
# `gh pr review` with none of them prompts interactively and is left alone.
REVIEW_EVENT='(^|[[:space:]])(--approve|--request-changes|--comment|-a|-r|-c)([[:space:]=]|$)'
GH_API="${W}gh${TOK}api${END}"
# `-f event=APPROVE` or a JSON body `"event":"..."`; review-post.sh never sends
# an event field, so a PENDING review passes. An event hidden in `--input
# file.json` is not visible here; that is the accepted gap.
API_EVENT='(^|[^[:alnum:]_])event([^[:alnum:]_]|$)'

# Each pipeline / list segment is judged on its own so `git log | grep push`
# does not read as `git push`. Quoted strings are not stripped, so the wrapped
# forms `bash -c "git push"`, `sh -c 'git push'` and `$(git push)` are denied
# like the bare command; a commit message containing `git push` is a rare
# false deny that costs one reworded retry.
segments=$(printf '%s\n' "$cmd" | tr '|;&' '\n\n\n')

reason=""
while IFS= read -r seg; do
  [ -n "$seg" ] || continue
  if printf '%s\n' "$seg" | grep -qE -- "$GIT_PUSH"; then
    reason="git push"
  elif printf '%s\n' "$seg" | grep -qE -- "$GH_PR_READY_MERGE"; then
    reason="gh pr ready/merge"
  elif printf '%s\n' "$seg" | grep -qE -- "$GH_PR_REVIEW" \
    && printf '%s\n' "$seg" | grep -qE -- "$REVIEW_EVENT"; then
    reason="gh pr review with --approve/--request-changes/--comment"
  elif printf '%s\n' "$seg" | grep -qE -- "$GH_API" \
    && printf '%s\n' "$seg" | grep -qF -- "/reviews" \
    && printf '%s\n' "$seg" | grep -qE -- "$API_EVENT"; then
    reason="gh api on /reviews with an event"
  fi
  [ -z "$reason" ] || break
done <<< "$segments"

[ -n "$reason" ] || exit 0

echo "guard-bash: denied for subagent '${agent_type}': ${reason} is a main-thread action behind a human gate; report what is ready instead of running it." >&2
exit 2
