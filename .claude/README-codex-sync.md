# Codex mirror

Codex reads `.claude/` through the tracked symlink `.agents -> .claude`. There is no separate mirror to regenerate. A change under `.claude/` is visible to Codex when it lands.

- A skill with `disable-model-invocation: true` carries `agents/openai.yaml` (`policy: allow_implicit_invocation: false`), so Codex does not auto-invoke it either.
- Codex ignores the `skills:` preload on agent files. Each agent names its preloaded skills in its body.
- Hooks in `.claude/settings.json` are Claude-only. The checks they run also live in `moose-build/scripts/gates.sh` and the standards skills.
- Check frontmatter after edits: `claude plugin validate --strict .claude/skills && claude plugin validate --strict .claude/agents`.
- The former `.codex/` TOML mirror was removed in commit 4ce9cb9.
