# Standing gates

The checks every `/moose-build` run passes, whatever the blueprint asked for. A blueprint's work-plan JSON
carries a `gates` object with these ids and criteria, and the rendered page draws them as strips; a blueprint
cannot add, remove, reorder, or alter one. Gate A
runs inside the loop; Gate B runs after `GOAL_MET`. Each row's criterion is its entry in `/moose-build`'s
goal ledger, and a gate passes when its rows are green. Row ids are stable and `/moose-build` addresses Gate
B rows by number; B1 (the consistency sweep) was retired because the code and dry lenses of the clean-context
review cover it, and its id is not reused. The commands live in `scripts/gates.sh` beside this file: a new
CIVET rejection becomes a gate there plus a row here, once, and every later run inherits it.

| Gate | Criterion | Check |
| --- | --- | --- |
| **A1** Build clean | C1 | The loop's `moose-test-runner` round whose build exits 0 (`make -j 6` in the scope). |
| **B2** Suites green + gold staged | C2, C3 | Evidenced by the loop's runner on the registered names (`--re=<names>`, gold captured and staged per `/moose-build`'s gold policy); re-run only when a later row changed a file. |
| **B3** Reuse / out-of-scope audit | C4 | Main-thread diff check against the blueprint's reuse decisions and `out_of_scope`. |
| **B4** SQA | C5 | `gates.sh <repo> sqa`: every touched runnable `tests` block carries `requirement`, `design`, and `issues` at its own level or on an ancestor, then `moosedocs.py check` with errors filtered to in-diff files. |
| **B5** ASCII | C6 | `gates.sh <repo> ascii`: added lines of code files (not `.md`, `.bib`, gold) hold only 7-bit ASCII; added `.md` lines carry no invisible character. |
| **B6** Docs smoke | DG | `docs.sh <repo> smoke --diff devel`: the `docs` line of `gates.sh <repo> all`, or the docs-writer's SMOKE line when it authored pages. Skipped by `--core`. |

Two gotchas.

`.md` and `.bib` are exempt from the ASCII rule because CIVET's precheck covers code, not documentation:
idaholab/moose scoped the rule to code in `c12859fc3f` (May 2026, refs #32497). An em dash or Nedelec with
its accent in a `.md` or `.bib` is correct, not a defect, and a name's diacritics there are never "fixed".
In code a diacritic is a hit like any other and is transliterated; unicode math is spelled out or written
as LaTeX in a comment.

The `.md` scan looks only for the invisible subset (smart quotes U+2018/2019/201C/201D, NBSP U+00A0, NNBSP
U+202F, ZWSP U+200B, BOM U+FEFF), which breaks `grep`, `!listing re=` slicing, and citation matching. That
perl runs with `-CSD`, and the flag is load-bearing: without it perl compares undecoded bytes, never sees a
smart quote as one character, and matches NBSP only through its trailing 0xA0 byte. The code scan is a byte
test and needs no `-CSD`.
