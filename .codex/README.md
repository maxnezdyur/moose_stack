# Codex sync

This directory is **generated output** of `claude-to-codex`, run against the canonical Claude artifacts under `.claude/`. It's how the same agents and skills become usable from OpenAI Codex / Codex CLI.

## What's here

| Path | Source | Notes |
|---|---|---|
| `.codex/config.toml` | derived from `.claude/agents/*.md` | Codex agent registry, `multi_agent = true`, `max_threads = 10` |
| `.codex/agents/*.toml` | `.claude/agents/*.md` | One per Claude agent. Contains `developer_instructions`, `model`, `model_reasoning_effort` |
| `AGENTS.md` (repo root) | `CLAUDE.md` | Mirror with `CLAUDE.md` → `AGENTS.md` rewrites |
| `.agents/skills/*` | `.claude/skills/*` | **Hardlinked** to source — same inode. One canonical SKILL.md, visible from both `.claude/skills/` and `.agents/skills/` |
| `codex-migration-report.json` | last `--write` run | Machine-readable summary; safe to delete |

## Re-running after you add or edit stuff

From the meta-repo root (`/Users/maxnezdyur/projects/moose_stack`):

```bash
# Preview what would change. Always do this first.
npx --yes claude-to-codex --dry-run --json > /tmp/c2c-plan.json
jq '.plan.summary' /tmp/c2c-plan.json
jq '.plan.operations | map(select(.type != "skip")) | .[] | {type, relativePath}' /tmp/c2c-plan.json

# Apply.
npx --yes claude-to-codex --write --emit-report
```

If the meta-repo is dirty with unrelated changes, the tool will refuse. Either commit/stash first, or add `--dangerous-allow-dirty-git` (uses git as the rollback backstop).

## Gotchas

1. **Hardlinks.** `.agents/skills/<skill>/SKILL.md` and `.claude/skills/<skill>/SKILL.md` share an inode. Editing either side edits both. There is no per-system text — keep skill prose system-neutral (or accept that Codex users will see `.claude/agents/` references and Claude users will see `.codex/` references, depending on what the canonical version says).

2. **`skills:` frontmatter is dropped** from agent `.md` files when generating `.codex/agents/*.toml`. Codex agents don't support skill preload. The agent's prompt text still says "invoke skill X" so behavior is preserved, but the auto-warm is gone — first action per agent re-loads the skill.

3. **Model is hardcoded** to `gpt-5.5` with `model_reasoning_effort = "high"` in every generated `.codex/agents/*.toml`. If you want a different Codex model, edit the TOMLs after running — but note the next `--write` will overwrite them. (If you need a persistent model override, patch the source `.claude/agents/*.md` frontmatter and check whether the tool picks it up.)

4. **moose submodule writes.** The tool wants to replace `moose/CLAUDE.md` (symlink → `moose/AGENTS.md`) with a concrete file, and create `moose/petsc/AGENTS.md`. These land *inside* the `moose/` and `moose/petsc/` submodules — they don't belong in the meta-repo commit. Decide per-submodule whether to commit, revert, or ignore.

5. **petsc commands skipped.** `moose/petsc/.claude/commands/{review-branch,review-mr-post,review-mr}.md` lack legacy frontmatter so the tool can't migrate them. Surface only — manual fix if you actually use those.

## Verifying after a run

```bash
# Meta-repo: should only show .codex/, AGENTS.md, codex-migration-report.json as new/changed
git status --short

# Submodules: check whether moose/ or moose/petsc/ picked up writes you don't want
git -C moose status --short
git -C moose/petsc status --short

# Confirm a skill is hardlinked (same inode on both sides)
stat -f "%i" .claude/skills/moose-build-feature/SKILL.md .agents/skills/moose-build-feature/SKILL.md
```

## Reverting a bad run

The tool takes a git-backed snapshot before writing. To undo:

```bash
git restore --staged --worktree .codex/ AGENTS.md codex-migration-report.json .agents/
# Then in submodules if needed:
git -C moose restore CLAUDE.md
rm -rf moose/petsc/AGENTS.md
```

## See also

- `.claude/README-codex-sync.md` — pointer file on the Claude side.
- Tool docs: `npx claude-to-codex --help`.
