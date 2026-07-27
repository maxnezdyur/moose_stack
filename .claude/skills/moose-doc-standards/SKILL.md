---
name: moose-doc-standards
description: MOOSE documentation standards and pitfalls reference for authoring .md doc pages in moose, blackbear, and isopod. Auto-loads when the user is writing, scaffolding, editing, or reviewing a MooseDocs markdown page. Covers shortcode conventions, file-location rules, citation handling, and the common ways pages break.
user-invocable: false
---

# MOOSE Documentation Standards

Reference and pitfalls for authoring `.md` pages under `<repo>/doc/content/` in moose, blackbear, and isopod.

## File location

- **Source-paired pages** mirror source: `<repo>/src/<base>/<Class>.C` ↔ `<repo>/doc/content/source/<base>/<Class>.md`. Base dirs: `kernels`, `bcs`, `materials`, `auxkernels`, `dgkernels`, `interfacekernels`, `ics`, `postprocessors`, `userobjects`, `functions`, `executioners`, `outputs`, `markers`, `meshgenerators`, `multiapps`, `transfers`.
- **Free-form / theory pages** live anywhere under `<repo>/doc/content/`.
- **Module landing** is wired via `menu:` in `config.yml`. The content-tree `index.md` is often a one-line redirect: `[modules/heat_transfer/index.md]`.
- **SQA pages** live under `<repo>/doc/content/sqa/` or per-module `.../sqa/`.

## Standard MooseObject page skeleton

    # ClassName

    !syntax description /<Base>/ClassName

    ## Description

    <prose, equations, [!param](...) inline links>

    ## Example Input File Syntax

    !listing test/tests/.../foo.i block=Kernels

    !syntax parameters /<Base>/ClassName
    !syntax inputs /<Base>/ClassName
    !syntax children /<Base>/ClassName

- **H1 matches the C++ class name exactly** — every `!syntax` call on the page breaks otherwise. AD/non-AD pair → `# Class / ADClass` on one page, never two pages.
- `!syntax description` pulls `addClassDescription` from C++. Missing → renders red; fix the C++.
- `!syntax parameters/inputs/children` trailer is standard. Don't omit.
- Inline param refs: `[!param](/Kernels/ClassName/variable)`. Typos trigger Levenshtein suggestions in the build log.

## Math

- Default to bare `\begin{equation}...\end{equation}` (katex picks them up).
- `!equation id=foo` only when you need cross-refs (`[!eqref](foo)` or `[foo]`).
- Inline: `$...$`.

## Listings

| Form | Use |
|---|---|
| `!listing path/file.i block=Kernels` | HIT block (`.i`/`.hit` only) |
| `!listing path/file.i start=[./foo] end=[../] include-end=true` | Literal-line bracket |
| `!listing path/file.C start=Foo::compute end=}` | Pattern slice for `.C` |
| `!listing path/file.py end=ft` | End at first match |
| `!listing path/file.C re=... re-flags=re.M\|re.S\|re.U` | Regex extraction |

**`block=` is `.i`/`.hit` only** — on other file types it is silently ignored; use `start=`/`end=`/`re=`.

Always reference real test inputs with `!listing`, never inline fenced HIT: a pasted snippet is a static fork that drifts silently when the test changes, while `!listing` re-extracts on every build. Slice with `start=`/`end=` if the piece isn't a discrete block. Inline fenced HIT is acceptable only for a tiny illustrative fragment with no corresponding test input — and if no real test input exists, omit the example (or write the test first) rather than fabricate one.

## Citations

- `[!cite](key)` narrative; `[!citep](k1, k2)` parenthetical; `[!citet](key)` textual. Typos render red.
- `!bibtex bibliography` controls placement. Without it the extension auto-appends `## References` — possibly in the wrong spot.
- Bibs auto-discovered tree-wide. Dup keys warn unless allowlisted in `config.yml` `bibtex.duplicates`.

## Cross-references

- Sibling: `[Class.md]` (autolink).
- Absolute virtual path: `[/Kernels/index.md]` — use when bare names collide across content roots.
- Section anchor: `## Heading id=foo` → `[#foo]` / `[Page.md#foo]`.
- Shortcut alias: `[Kernels]` (resolves via `framework/doc/globals.yml`).
- Optional: `[help/contact_us.md optional=True]`.

## Media

    !media path/img.png style=width:80% caption=Foo id=fig-foo
    !media path/clip.mp4 autoplay=True loop=True caption=...

Cross-ref via `[!ref](fig-foo)`.

## Alerts

`!alert <brand>` — `error`, `warning`, `note`, `tip`. Block: `!alert! note title=Foo` … `!alert-end!`. **`construction` is reserved for auto-stubs — never use it manually.**

## Module landing pages

    !row!
    !col! small=12 medium=4 large=4 icon=device_hub
    ### Heading class=center style=font-weight:200;
    - bullet
    !col-end!
    !row-end!

Theory-heavy pages: end with `!syntax complete groups=YourApp level=3`.

## Doc ↔ test coupling

Tests specs point at doc pages via `design = 'MyClass.md'` (suffix-matched). Renaming or moving a page silently breaks SQA traceability — grep the tests specs when you rename. Full spec standards: **moose-test-standards**.

## Templates

- **Stubs** at `framework/doc/content/templates/stubs/` — written by `./moosedocs.py generate <App>`. The `!alert construction title=Undocumented Class` block marks them; replace it (`moosedocs.py check` flags unreplaced stubs).
- **SQA templates** at `framework/doc/content/templates/sqa/` — `!template load file=sqa/srs.md.template ...` then `!template! item key=...`.

## Reference pages — read one before authoring

| Page kind | Reference |
|---|---|
| Kernel (minimal, math-heavy) | `moose/framework/doc/content/source/kernels/Diffusion.md` |
| Kernel (with !listing + [!param]) | `moose/framework/doc/content/source/kernels/CoupledForce.md` |
| BC | `moose/framework/doc/content/source/bcs/DirichletBC.md` |
| Material (simple) | `moose/framework/doc/content/source/materials/GenericConstantMaterial.md` |
| Material (with [!param]) | `moose/framework/doc/content/source/materials/ParsedMaterial.md` |
| Theory (eq + cite + listing) | `moose/modules/porous_flow/doc/content/modules/porous_flow/upwinding.md` |
| Module landing (cards) | `moose/modules/porous_flow/doc/content/modules/porous_flow/index.md` |
| Module landing (theory) | `moose/modules/heat_transfer/doc/content/modules/heat_transfer/index.md` |
| SQA RTM | `moose/modules/heat_transfer/doc/content/modules/heat_transfer/sqa/heat_transfer_rtm.md` |
| Stub template | `moose/framework/doc/content/templates/stubs/moose_object.md.template` |

## ASCII only — no smart quotes, em dashes, NBSP

Every byte in a `.md` page must be 7-bit ASCII (`.bib` files are exempt — author diacritics are legitimate). Non-ASCII lookalikes render fine and are invisible in most editors, but later break grep, `!listing re=...` slicing, citation key matching, CIVET tooling, and string compares. They arrive via paste (PDFs, web pages, AI prose) and editor Smart Quotes/Dashes autocorrect — disable those for `.md`, and scan touched files before commit (from repo root):

    grep -rnP '[^\x00-\x7F]' --include='*.md' doc/

| Banned char | U+ | Replace with |
|---|---|---|
| `'` `'` smart single quote | 2018 / 2019 | `'` |
| `"` `"` smart double quote | 201C / 201D | `"` |
| `–` en dash | 2013 | `-` |
| `—` em dash | 2014 | `--` |
| `…` horizontal ellipsis | 2026 | `...` |
| non-breaking space | 00A0 | regular space |
| narrow no-break space | 202F | regular space |
| zero-width space | 200B | delete |
| byte-order mark | FEFF | delete |

## Build pitfalls

- **Stale binary breaks the site.** `appsyntax` runs `<exe> --json --allow-test-objects` — rebuild the app before building docs.
- **Extension order:** `appsyntax` must come *after* `katex` in `config.yml`.
- **`--fast` disables `appsyntax`** — `!syntax` blocks won't render. Drop `--fast` for the final preview.

## Build / preview

    cd moose/modules/doc
    ./moosedocs.py build --serve --fast --files source/<base>/<Class>   # iterate on prose
    ./moosedocs.py build --serve                                         # full preview (slower)
    ./moosedocs.py check                                                 # SQA report
    ./moosedocs.py generate <YourApp>App                                 # write stubs
