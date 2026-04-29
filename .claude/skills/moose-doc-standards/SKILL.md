---
name: moose-doc-standards
description: MOOSE documentation standards and pitfalls reference for authoring .md doc pages in moose, blackbear, and isopod. Auto-loads when the user is writing, scaffolding, editing, or reviewing a MooseDocs markdown page. Covers shortcode conventions, file-location rules, citation handling, and the common ways pages break.
user-invocable: false
---

# MOOSE Documentation Standards

Reference and pitfalls for authoring `.md` pages under `<repo>/doc/content/` in moose, blackbear, and isopod. Apply these whenever editing or creating a doc page.

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

- **H1 matches the C++ class name exactly.** AD/non-AD pair → `# Class / ADClass` on one page.
- `!syntax description` pulls `addClassDescription` from C++. Missing → renders red; fix C++.
- `!syntax parameters/inputs/children` trailer is standard. Don't omit.
- Inline param refs: `[!param](/Kernels/ClassName/variable)`. Typos trigger Levenshtein suggestions.

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

**`block=` is `.i`/`.hit` only.** For `.C`/`.py` use `start=`/`end=`/`re=`.

## Citations

- `[!cite](key)` narrative; `[!citep](k1, k2)` parenthetical; `[!citet](key)` textual.
- `!bibtex bibliography` controls placement. Without it the extension auto-appends `## References`.
- Bibs auto-discovered tree-wide. Dup keys warn unless allowlisted in `config.yml` `bibtex.duplicates`.

## Cross-references

- Sibling: `[Class.md]` (autolink).
- Absolute virtual path: `[/Kernels/index.md]` — use when bare names collide.
- Section anchor: `## Heading id=foo` → `[#foo]` / `[Page.md#foo]`.
- Shortcut alias: `[Kernels]` (resolves via `framework/doc/globals.yml`).
- Optional: `[help/contact_us.md optional=True]`.

## Media

    !media path/img.png style=width:80% caption=Foo id=fig-foo
    !media path/clip.mp4 autoplay=True loop=True caption=...

Cross-ref via `[!ref](fig-foo)`.

## Alerts

`!alert <brand>` — `error`, `warning`, `note`, `tip`. Block: `!alert! note title=Foo` … `!alert-end!`. **`construction` is reserved for auto-stubs — don't use manually.**

## Module landing pages

    !row!
    !col! small=12 medium=4 large=4 icon=device_hub
    ### Heading class=center style=font-weight:200;
    - bullet
    !col-end!
    !row-end!

Theory-heavy pages: end with `!syntax complete groups=YourApp level=3`.

## SQA test specs

Every test block needs:

    [./mytest]
      type = ...
      input = ...
      requirement = 'The system shall <do something>'
      design = 'MyClass.md'
      issues = '#13736'
    [../]

"shall" wording is conventional. `design` must point to a real page. `issues = '#000'` only when no issue exists.

## Templates

- **Stubs** at `framework/doc/content/templates/stubs/` — written by `./moosedocs.py generate <App>`. The `!alert construction title=Undocumented Class` block marks them; replace it.
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

## Pitfalls — common ways pages break

1. **Missing `addClassDescription`** → `!syntax description` red. Fix C++.
2. **Stub never replaced** — `!alert construction title=Undocumented Class` blocks flagged by `check`. Replace.
3. **`block=` on non-`.i`** silently ignored. Use `start=`/`end=`/`re=`.
4. **Citation typos** render red. Dup keys warn unless allowlisted.
5. **No `!bibtex bibliography`** auto-appends `## References` — placement may be wrong.
6. **Bare-filename autolink ambiguity** when two roots share a filename → use `/Absolute/Path.md`.
7. **`[!param]` typos** trigger Levenshtein suggestions. Fix them.
8. **Stale binary breaks site-wide.** `appsyntax` runs `<exe> --json --allow-test-objects`. Rebuild first.
9. **Extension order:** `appsyntax` must come *after* `katex` in `config.yml`.
10. **`--fast` disables `appsyntax`** — `!syntax` blocks won't render. Drop `--fast` for final preview.
11. **H1 ≠ C++ class name** breaks every `!syntax` call on the page.
12. **AD pair split across two pages** — wrong. Use `# Class / ADClass`.
13. **No real test input** — don't fabricate. Omit the example or write a test first.
14. **SQA fields missing** fail `check`. `issues = '#000'` only as last resort.
15. **Manual `!alert construction`** — reserved for auto-stubs.

## Build / preview

    cd moose/modules/doc
    ./moosedocs.py build --serve --fast --files source/<base>/<Class>   # iterate on prose
    ./moosedocs.py build --serve                                         # full preview (slower)
    ./moosedocs.py check                                                 # SQA report
    ./moosedocs.py generate <YourApp>App                                 # write stubs
