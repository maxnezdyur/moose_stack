# Keeping Codex in sync

When you add or edit anything under `.claude/agents/` or `.claude/skills/`, the Codex-side mirror at `.codex/` and `.agents/skills/` goes stale until you re-run `claude-to-codex`.

**Quick re-sync** (from the meta-repo root):

```bash
npx --yes claude-to-codex --dry-run --json > /tmp/c2c-plan.json && jq '.plan.summary' /tmp/c2c-plan.json
npx --yes claude-to-codex --write --emit-report
```

Full instructions, gotchas (hardlinks, dropped `skills:` preload, hardcoded model, moose submodule writes), and rollback steps live in `.codex/README.md`.
