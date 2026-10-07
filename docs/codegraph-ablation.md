# CodeGraph ablation for the Haiku Explore agent

Question: does the CodeGraph index still earn its place now that code search runs on Haiku 5.5? Measured 2026-10-07 on this checkout (moose, blackbear, isopod; `.codegraph/` is 1.4 GB).

## Method

- Four arms, same question text, same working directory: the live `Explore` agent (Haiku high, CodeGraph tool available and told to query it first), `explore-nocg` (identical prompt, no CodeGraph tool, told not to run the CLI), and both again on Opus 5.5 at medium effort. Transcripts confirm no `nocg` run touched CodeGraph.
- Round 1: 12 grep-friendly questions (definition, callers, hierarchy, semantic, data flow, cross-module, blast radius, negative, test lookup, syntax registration, deep read, override filter). Round 2: 8 structure-heavy questions (10-hop call path, fan-out count across modules, a noisy symbol with hundreds of grep hits, registration aliases, action chain, override set, material-property flow, templated AD dispatch).
- 3 repetitions per question on Haiku, 2 on Opus: 198 scored runs. Each question's answer key was built by a separate Opus agent (xhigh effort in round 2) with CodeGraph and grep, every citation opened. Each run was scored by an Opus judge that opened every cited line. Cost, requests, tool mix, prompt size and wall time come from the transcripts. Two Haiku runs of the call-path question (one per arm) failed to produce the structured output after five retries and are excluded from both arms equally.

## Result

| Arm | Runs | Correct | Key items found | Citations valid | False claims per run | Cost per run | Wall per run | Mean peak prompt | CodeGraph calls |
|---|---|---|---|---|---|---|---|---|---|
| Haiku + CodeGraph | 59 | 95% | 86% | 99% | 0.27 | $0.0063 | 31 s | 28K | 92 |
| Haiku, grep only | 59 | 97% | 90% | 100% | 0.12 | $0.0045 | 20 s | 18K | 0 |
| Opus + CodeGraph | 40 | 95% | 88% | 100% | 0.10 | $0.095 | 17 s | 15K | 38 |
| Opus, grep only | 40 | 90% | 85% | 100% | 0.15 | $0.077 | 14 s | 13K | 0 |

By round:

| Arm | Round 1 correct | Round 2 correct | Round 2 false claims per run |
|---|---|---|---|
| Haiku + CodeGraph | 36/36 | 20/23 | 0.30 |
| Haiku, grep only | 35/36 | 22/23 | 0.04 |
| Opus + CodeGraph | 24/24 | 14/16 | 0.12 |
| Opus, grep only | 23/24 | 13/16 | 0.25 |

Where the arms differed (Haiku):

| Question | + CodeGraph | grep only | What happened |
|---|---|---|---|
| h01 10-hop call path | 0/2 | 2/2 | CodeGraph answered the call-path query with 26K characters of "dynamic-dispatch links" such as `computeResidualTags -> PetscDrawClear_X` through a PETSc function pointer, which is noise. Both CodeGraph runs then reported 9 or 10 of 10 hops with one wrong statement each. Both grep-only runs reported all 10 hops at the exact lines with no false claim |
| h02 count overrides across modules | 2/3 | 2/3 | One CodeGraph run reported "about 184" classes (key: 138); one grep-only run refused to commit to a count |
| h08 templated AD dispatch | 3/3 | 3/3 | Both arms caught the trap (the `computeQpResidual` in the base is `final` and only errors; `precomputeQpResidual` runs). CodeGraph runs used 8 index calls to get there |
| q03 direct subclasses | 3/3, 100% items | 3/3, 80% items | One grep-only run listed 2 of the key's 5 but 3 valid alternatives; a scoring artifact of which 5 of 19 the key chose |
| q12 override filter | 3/3 | 2/3 | One grep-only run missed one of five `Elastic` materials. The Opus grep-only arm missed the same one once |
| q09 test lookup | 3/3 | 3/3 | Every arm found a valid test; CodeGraph does not index tests, so the CodeGraph arm grepped anyway |

Tool mix over all Haiku runs: the CodeGraph arm made 92 index calls, 116 Bash greps and 75 Reads; the grep-only arm made 131 Bash greps and 92 Reads. Neither arm used the Grep or Glob tools; both grep from Bash. A CodeGraph request takes about 4.3 s against 2.6 s for a grep request, and its output is the reason the CodeGraph arm's peak prompt is 10K tokens larger.

## Reading

- For the Haiku search agent, CodeGraph does not improve correctness on either question set. It costs 40% more per run, takes 50% longer, and doubles the false-claim rate, because the agent trusts index output that is sometimes noise (dynamic-dispatch guesses, counts).
- The one structural case where an index should win, the 10-hop call path, is the case where grep-only Haiku won outright. Haiku at high effort reads the code.
- For Opus the picture is the opposite and small: CodeGraph lifted round 2 from 13/16 to 14/16 and cut false claims. Opus uses the index sparingly (0.6 calls per run in round 2) and does not get lost in its output.
- The index does not cover tests specs, `.i` inputs, or docs, which are a large share of real scout questions.
- Not measured here: the editing use, where the implementer or a reviewer wants callers and blast radius in view while changing code. That is a different workload from search-and-cite.

## Decision

Removed the same day: the MCP server, the CLI, every `.codegraph/` index, and every reference in agents, skills, and CLAUDE.md. The recommendation below is what the data supported before that call.

## Recommendation

1. Drop the CodeGraph-first rule for the Haiku search agents. In `~/.claude/agents/Explore.md` and `.claude/agents/moose-scout.md`, grep first; leave the tool available for a second lookup on a hierarchy or override enumeration, which is where it tied or edged ahead.
2. Keep CodeGraph in the Opus authoring and review agents (implementer, code and AD reviewers, dry reviewer) until the editing use is measured the same way.
3. The global CLAUDE.md rule "query codegraph before grep" is wrong for Haiku; scope it to Opus agents or delete it.
4. Re-run this benchmark after any CodeGraph update: the workflow scripts are in the session's workflow directory and the questions are in this file's history.

Raw data: `~/.claude/jobs/14c8acea/tmp/ablation-rows.json`, `ablation2-rows.json`, `ablation-summary.json`; transcripts under the two workflow directories `wf_04b419d5-c15` and `wf_d084b36e-aac`.
