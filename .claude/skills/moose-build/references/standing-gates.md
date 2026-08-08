# Standing gates

Sole owner of the standing gates `/moose-build` enforces — the checks every run passes, whatever
the blueprint asked for. Not negotiable, not blueprint-editable. Blueprints render it read-only
and cannot add, remove, reorder, or alter a gate.

**Gate A** runs inside the loop's normal flow. **Gate B** runs after `GOAL_MET`. Each row's
`Criterion` is its entry in `/moose-build`'s goal ledger; a gate is passed when its checks are
green. Row ids are stable — `/moose-build` addresses gate B checks by number.

| Gate | Criterion | Check |
| --- | --- | --- |
| **A1** Build clean | C1 | One-shot `moose-test-runner`, build-only — *"You are authorized to build: `cd <scope> && make -j 6`. Report compile errors verbatim with owning files."* |
| **B1** Consistency sweep | — | Only when the work plan has ≥2 implement units. One-shot reviewer agent (`general-purpose`) that reads every new/changed source file *together* against `moose/framework/doc/content/sqa/framework_scs.md` — naming drift, param-style drift, duplicated helpers across units. Findings route through `/moose-build` § Repair. |
| **B2** Suites green + gold staged | C2, C3 | Already evidenced by the loop's runner; re-run `moose-test-runner` on the registered test names (`--re=<names>`) only when a later gate check changed a file. Gold per `/moose-build` § Gold policy. |
| **B3** Reuse / out-of-scope audit | C4 | Diff vs the blueprint's `reuse_decisions[]` + `out_of_scope[]`. |
| **B4** SQA | C5 | Grep audit of in-diff spec files, then the authoritative `./moosedocs.py check` — `standing-gates.md` § SQA. |
| **B5** ASCII | C6 | Two scans over the branch diff, code then `.md` — `standing-gates.md` § ASCII. |
| **B6** Docs smoke | DG | Via the docs gate (`/moose-build` § Docs) — `moose-docs-writer`'s nested gate when docs are on, direct `moose-docs-builder` when off. Skipped by `--core`. |

## SQA (B4, C5)

Grep audit of in-diff spec files for `requirement`/`design`/`issues` — parent-block declarations
cover children. Then the authoritative check:

```bash
cd <doc-dir> && ./moosedocs.py check
```

Doc dir: `moose/modules/doc` | `blackbear/doc` | `isopod/doc`. Errors filtered to the branch diff
— pre-existing SQA debt is reported, not fixed. Env failure → surface the conda hint, note the
grep audit still ran.

## ASCII (B5, C6)

CIVET's precheck covers **code**, not documentation — `idaholab/moose` scoped the rule to code
comments in `c12859fc3f` (May 2026, refs #32497), so `.md` and `.bib` are excluded from this gate
and non-ASCII there (em dashes, `Nédélec`) is correct, not a defect. Never "fix" a name's
diacritics in a `.md` or `.bib`; in code a diacritic is a hit like any other.

```bash
git -C <scope> diff devel...HEAD -- . ':(exclude)*gold*' ':(exclude)*.md' ':(exclude)*.bib' \
  | perl -ne 'print if /^\+/ and /[^\x00-\x7F]/'
```

The code scan needs no `-CSD` — `[^\x00-\x7F]` is a byte test. Fix any hit in place on the main
thread (smart quotes → `'`/`"`, dashes → `--`, NBSP → space, unicode math → spelled out or LaTeX
in a comment, diacritics → transliterated), then re-run until clean.

Scan added `.md` lines separately, for the **invisible** subset only: smart quotes, NBSP/NNBSP,
zero-width space, and BOM, which break `grep`, `!listing re=` slicing, and citation matching.
Leave every other non-ASCII character alone. This `perl` **must** carry `-CSD` — without it perl
compares undecoded bytes, silently missing smart quotes entirely and matching NBSP only via its
trailing `0xa0`:

```bash
git -C <scope> diff devel...HEAD -- '*.md' \
  | perl -CSD -ne 'print if /^\+/ and /[\x{2018}\x{2019}\x{201C}\x{201D}\x{00A0}\x{202F}\x{200B}\x{FEFF}]/'
```
