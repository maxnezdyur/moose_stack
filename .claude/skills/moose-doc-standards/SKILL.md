---
name: moose-doc-standards
description: MOOSE documentation standards and pitfalls reference for authoring .md doc pages in moose, blackbear, and isopod. Auto-loads when the user is writing, scaffolding, editing, or reviewing a MooseDocs markdown page. Covers shortcode conventions, file-location rules, citation handling, and the common ways pages break.
user-invocable: false
---

# MOOSE Documentation Standards

Reference and pitfalls for authoring `.md` pages under `<repo>/doc/content/` in moose, blackbear, and isopod. Upstream canonical standards: `moose/python/doc/content/python/MooseDocs/standards.md` — this skill adds the house rules and pitfalls it doesn't cover.

## File location

- **Source-paired pages** mirror source: `<repo>/src/<base>/<Class>.C` ↔ `<repo>/doc/content/source/<base>/<Class>.md`. Base dirs: `kernels`, `bcs`, `materials`, `auxkernels`, `dgkernels`, `interfacekernels`, `ics`, `postprocessors`, `userobjects`, `functions`, `executioners`, `outputs`, `markers`, `meshgenerators`, `multiapps`, `transfers`.
- **Free-form / theory pages** live anywhere under `<repo>/doc/content/`.
- **Module landing** is wired via `menu:` in `config.yml`. The content-tree `index.md` is often a one-line redirect: `[modules/heat_transfer/index.md]`.
- **SQA pages** live under `<repo>/doc/content/sqa/` or per-module `.../sqa/`.

## Syntax pages vs source pages

- `syntax/<block path>/index.md` documents the input-file block; `source/<dir>/<Class>.md` documents the C++ class. Both are derived mechanically and required by the checker (`moose/python/moosesqa/check_syntax.py`) — an Action registered at N syntax paths needs one class page and N index pages.
- Commands are node-typed: `!syntax list` renders only on an index page; `!syntax description`/`inputs`/`children` only on a class page; `!syntax parameters` on an index page aggregates all child actions. Put each fact on the page its command belongs to.
- Render a given parameter table on one page only — for a single-action block, the class page. Class page owns the class description, constructed objects, and class-level preconditions; index page owns block semantics, sub-block usage, example inputs, and the `!syntax list` trailer.
- A deprecated-syntax mirror page (forced by `registerDeprecatedSyntax`) is a deprecation `!alert` plus `!include` of the live page — never a hand-copied fork. Alternative: drop the path from docs via `remove.yml` referenced in both `config.yml` and `sqa_reports.yml`.

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

- **H1 names the class** — exact or prose-spaced (`!syntax` commands resolve from their positional path, not the H1). The joint `# Class / ADClass` heading is only for a single page documenting both registered variants; a page for one variant names only that class.
- `!syntax description` pulls `addClassDescription` from C++. Missing → renders red; fix the C++.
- `!syntax parameters/inputs/children` trailer is standard. Don't omit.
- Inline param refs: `[!param](/Kernels/ClassName/variable)` — prefer one over plain code formatting whenever prose names a parameter. Typos trigger Levenshtein suggestions in the build log.

## Prose

- Never label a maintained implementation legacy, deprecated, or superseded — AD vs non-AD is a capability axis, not a lifecycle axis; distinguish variants by capability only. Use deprecation language only where the codebase already carries it (a deprecation banner, a `Legacy*` name, a deprecated registration).
- Cut filler qualifiers and abstract path/mode narration — keep only words that carry information the user needs.
- State meaning directly ("<subject> does X because Y") — cut conversational scaffolding ("What happens is...", "Note that...", "need to make sure") but keep the rationale, restated declaratively.
- Document the operating envelope, not just the mechanism: the frame/configuration results are reported in, the assumptions the math makes, and the limitations — read them off the C++ guards and the tests, never guess from the class name. Upstream: § End-User Focused in the standards page above.
- In worked-example prose, state the general requirement and mark the input's concrete values as instances ("$\Delta t = 4$ in this case"), anchored to the parameter name.
- When a change adds or alters a parameter whose behavior the page prose describes, revise that prose (naming the parameter via `[!param]`); never restate defaults, types, or required/optional status — the `!syntax parameters` trailer generates those. See `moose/framework/doc/content/framework/documenting.md` (modifying a class obliges updating its page).

## Math

- Default to bare `\begin{equation}...\end{equation}` (katex picks them up).
- `!equation id=foo` only when you need cross-refs (`[!eqref](foo)` or `[foo]`).
- Inline: `$...$`.
- State which residual the object contributes to (and which it does not), and define every symbol and sign convention in a shown equation, naming what supplies each symbol — a `[!param]` link, material property, coupled variable, or companion object. Upstream: § Equations Standards in the standards page above.

## Listings

| Form | Use |
|---|---|
| `!listing path/file.i block=Kernels` | HIT block (`.i`/`.hit` only) |
| `!listing path/file.i start=[./foo] end=[../] include-end=true` | Literal-line bracket |
| `!listing path/file.C start=Foo::compute end=}` | Pattern slice for `.C` |
| `!listing path/file.py end=ft` | End at first match |
| `!listing path/file.C re=... re-flags=re.M\|re.S\|re.U` | Regex extraction |

**`block=` is `.i`/`.hit` only** — on other file types it is silently ignored; use `start=`/`end=`/`re=`.

**Point `!listing` at the input file itself, scoped by `block=`** — never a `tests` spec, and never a variant whose behavior comes only from `cli_args`.

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
- Name and link the specific object or action — never a generic noun phrase in its place.
- One canonical page per topic — cross-link to it instead of restating it, and keep concept and theory prose off object and action reference pages.

## Sibling and variant pages

- Apply a page fix to every sibling page of the same kind in the same change — read each page in full first, never paste text across pages blindly.
- Keep AD/non-AD counterpart pages near-identical. Factor a duplicated prose block into `<module>/doc/content/modules/<module>/common/` and `!include` it — with separate AD and non-AD snippets so cross-links resolve to the right variant.

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
