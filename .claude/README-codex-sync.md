# Keeping Codex in sync

When you add or edit anything under `.claude/agents/` or `.claude/skills/`, the Codex-side mirror at `.codex/` and `.agents/skills/` goes stale until you re-run `claude-to-codex`.

**Quick re-sync** (from the meta-repo root):

```bash
npx --yes claude-to-codex --dry-run --json > /tmp/c2c-plan.json && jq '.plan.summary' /tmp/c2c-plan.json
# STOP if this prints anything — a stale .claude/worktrees/ copy will overwrite the mirror:
jq -r '.plan.operations[] | select(.type != "skip") | .relativePath' /tmp/c2c-plan.json | sort | uniq -d
npx --yes claude-to-codex --write --emit-report
python3 .codex/scripts/apply-models.py   # re-apply .codex/model-map.json model overrides
```

When the duplicate check fails, prune the worktree or hand-patch the one TOML instead — see gotcha 5 in `.codex/README.md`.

Full instructions, gotchas (hardlinks, dropped `skills:` preload, hardcoded model, moose submodule writes), and rollback steps live in `.codex/README.md`.
