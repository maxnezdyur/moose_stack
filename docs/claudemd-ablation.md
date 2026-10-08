# CLAUDE.md in the Haiku Explore agent

Question: the Haiku Explore agent starts with the user and project CLAUDE.md files in its prefix. Is it better without them (`omitClaudeMd: true`, Claude Code >= 2.1.271)? Measured 2026-10-07.

## What the start prompt holds

The Haiku Explore agent's first request is about 7,400 tokens: its own prompt, the four tool schemas, the two CLAUDE.md files (about 1,900 tokens), the git status snapshot, the preloaded `haiku-discipline` skill (about 600), and the question. With `omitClaudeMd: true` it is about 4,600 tokens. For comparison, a `general-purpose` Haiku subagent starts at about 16,900 tokens, because it inherits every tool schema and the skill listing; CLAUDE.md is not the big part there either.

## Method

Two inline agent definitions, identical except for `omitClaudeMd`, each spawned 60 times from a headless Sonnet parent in this checkout: the 20 questions of the CodeGraph ablation (12 grep-friendly, 8 structure-heavy), 3 repetitions each. Transcripts confirm the CLAUDE.md text is present in all 60 runs of one arm and absent in all 60 of the other. The same Opus judges and answer keys as the CodeGraph ablation.

## Result

| Arm | Start prompt | Correct | Key items found | False claims per run | Output tokens per run | Cost per run | Wall |
|---|---|---|---|---|---|---|---|
| with CLAUDE.md | 7,408 | 58/60 (97%) | 92% | 0.20 | 3,675 | $0.0041 | 19 s |
| omitClaudeMd | 4,630 | 56/60 (93%) | 95% | 0.40 | 4,431 | $0.0043 | 22 s |

Without CLAUDE.md the agent reads more (214 Reads against 146), writes 20% more, and makes twice as many unsupported statements. The 2,800-token prefix saving is worth about $0.0003 per run at Haiku cache-write rates and is cancelled by the longer output. The two arms disagree on four questions, three of them in the structure-heavy set, and in each case the omitClaudeMd run added a wrong claim (a miscount of 168 against 138 overrides; a wrong statement about `parallel_reduce` calling the loop base directly) or went looser on a near miss.

The likely cause is the user CLAUDE.md's "Be terse. Short, direct answers" rule and the project file's conventions: Haiku follows them, and a shorter answer carries fewer unsupported claims.

## Decision

Keep CLAUDE.md in the Haiku search agents. Do not set `omitClaudeMd` on Explore, moose-scout, or haiku-worker. The place `omitClaudeMd` would pay is a machine with a large CLAUDE.md hierarchy (tens of thousands of tokens) feeding a cheap agent that needs none of it; this machine's two files are 1,900 tokens.

Raw data: `~/.claude/jobs/14c8acea/tmp/cm-rows.json` and `cm-results.json`; subagent transcripts under the 120 session directories in `~/.claude/projects/-Users-maxnezdyur-projects-moose-stack/`.
