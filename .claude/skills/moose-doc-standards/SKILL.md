---
name: moose-doc-standards
description: MOOSE documentation standards and pitfalls for authoring .md doc pages in moose, blackbear, and isopod. Loads when the user is writing, scaffolding, editing, or reviewing a MooseDocs markdown page. Covers page scope, shortcode conventions, file-location rules, citation handling, and the common ways pages break.
user-invocable: false
---

# MOOSE Documentation Standards

House rules and pitfalls for `.md` pages under `<repo>/doc/content/` in moose, blackbear, and isopod. The upstream canonical standards are `moose/python/doc/content/python/MooseDocs/standards.md`; this skill adds what that page does not cover. Building, serving, and smoke-testing a site is the `moose-docs` skill (`.claude/skills/moose-docs/scripts/docs.sh`).

## Page scope

Write what a `.i` author would read: what the object does, which residual or quantity it contributes, what it needs, and what it assumes. About 150 lines in 5 sections is the size signal; a page well past that is carrying theory or tutorial content that belongs on its own page. State limits inline where the relevant mechanism is described, not in a separate Limitations section.

## File location

- Source-paired pages mirror source: `<repo>/src/<base>/<Class>.C` pairs with `<repo>/doc/content/source/<base>/<Class>.md`, with `<base>` the same directory name on both sides.
- Free-form and theory pages live anywhere under `<repo>/doc/content/`.
- Module landing is wired via `menu:` in `config.yml`. The content-tree `index.md` is often a one-line redirect: `[modules/heat_transfer/index.md]`.
- SQA pages live under `<repo>/doc/content/sqa/` or per-module `.../sqa/`.

## Syntax pages vs source pages

- `syntax/<block path>/index.md` documents the input-file block; `source/<dir>/<Class>.md` documents the C++ class. Both are derived mechanically and required by the checker (`moose/python/moosesqa/check_syntax.py`): an Action registered at N syntax paths needs one class page and N index pages.
- Commands are node-typed: `!syntax list` renders only on an index page; `!syntax description`/`inputs`/`children` only on a class page; `!syntax parameters` on an index page aggregates all child actions. Put each fact on the page its command belongs to.
- Render a given parameter table on one page only; for a single-action block, the class page. The class page owns the class description, constructed objects, and class-level preconditions; the index page owns block semantics, sub-block usage, example inputs, and the `!syntax list` trailer.
- A deprecated-syntax mirror page (forced by `registerDeprecatedSyntax`) is a deprecation `!alert` plus `!include` of the live page, not a hand-copied fork. The alternative is to drop the path from docs via `remove.yml` referenced in both `config.yml` and `sqa_reports.yml`.

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

- The H1 names the class, exact or prose-spaced (`!syntax` commands resolve from their positional path, not the H1). The joint `# Class / ADClass` heading is only for a single page documenting both registered variants; a page for one variant names only that class.
- `!syntax description` pulls `addClassDescription` from C++. When it is missing the block renders red; the fix is in the C++.
- The `!syntax parameters/inputs/children` trailer is standard on every class page.
- Inline param refs: `[!param](/Kernels/ClassName/variable)`. Prefer one over plain code formatting whenever prose names a parameter. Typos trigger Levenshtein suggestions in the build log.

## Prose

- A maintained implementation is not labeled legacy, deprecated, or superseded. AD vs non-AD is a capability axis, not a lifecycle axis; distinguish variants by capability only. Deprecation language belongs only where the codebase already carries it (a deprecation banner, a `Legacy*` name, a deprecated registration).
- Cut filler qualifiers and abstract path/mode narration; keep only words that carry information the user needs.
- State meaning directly ("<subject> does X because Y"). Cut conversational scaffolding ("What happens is...", "Note that...", "need to make sure") but keep the rationale, restated declaratively.
- Document the operating envelope, not just the mechanism: the frame or configuration results are reported in, the assumptions the math makes, and the limitations. Read them off the C++ guards and the tests, not the class name. Upstream: section End-User Focused in the standards page above.
- In worked-example prose, state the general requirement and mark the input's concrete values as instances ("$\Delta t = 4$ in this case"), anchored to the parameter name.
- When a change adds or alters a parameter whose behavior the page prose describes, revise that prose (naming the parameter via `[!param]`). Defaults, types, and required/optional status are generated by the `!syntax parameters` trailer and are not restated. See `moose/framework/doc/content/framework/documenting.md` (modifying a class obliges updating its page).

## Math

- Default to bare `\begin{equation}...\end{equation}` (katex picks them up).
- `!equation id=foo` only when you need cross-refs (`[!eqref](foo)` or `[foo]`).
- Inline: `$...$`.
- State which residual the object contributes to (and which it does not), and define every symbol and sign convention in a shown equation, naming what supplies each symbol: a `[!param]` link, material property, coupled variable, or companion object. Upstream: section Equations Standards in the standards page above.

## Listings

| Form | Use |
|---|---|
| `!listing path/file.i block=Kernels` | HIT block (`.i`/`.hit` only) |
| `!listing path/file.i start=[./foo] end=[../] include-end=true` | Literal-line bracket |
| `!listing path/file.C start=Foo::compute end=}` | Pattern slice for `.C` |
| `!listing path/file.py end=ft` | End at first match |
| `!listing path/file.C re=... re-flags=re.M\|re.S\|re.U` | Regex extraction |

- `block=` is `.i`/`.hit` only; on other file types it is silently ignored, so use `start=`/`end=`/`re=`.
- Point `!listing` at the input file itself, scoped by `block=`; not a `tests` spec, and not a variant whose behavior comes only from `cli_args`.
- Reference real test inputs with `!listing` rather than inline fenced HIT: a pasted snippet is a static fork that drifts silently when the test changes, while `!listing` re-extracts on every build. Slice with `start=`/`end=` when the piece is not a discrete block. Inline fenced HIT is acceptable only for a tiny illustrative fragment with no corresponding test input; when no real test input exists, omit the example (or write the test first) rather than fabricate one.
- MooseDocs resolves `!listing` and links against git-tracked files. An untracked new input produces a phantom "does not exist in the repository" error; stage it, or expect that error.

## Citations

- `[!cite](key)` narrative; `[!citep](k1, k2)` parenthetical; `[!citet](key)` textual. Typos render red.
- `!bibtex bibliography` controls placement. Without it the extension auto-appends `## References`, possibly in the wrong spot.
- Bibs are auto-discovered tree-wide. Duplicate keys warn unless allowlisted in `config.yml` `bibtex.duplicates`.

## Cross-references

- Sibling: `[Class.md]` (autolink).
- Absolute virtual path: `[/Kernels/index.md]`, for when bare names collide across content roots.
- Section anchor: `## Heading id=foo` then `[#foo]` / `[Page.md#foo]`.
- Shortcut alias: `[Kernels]` (resolves via `framework/doc/globals.yml`).
- Optional: `[help/contact_us.md optional=True]`.
- Name and link the specific object or action, not a generic noun phrase in its place.
- One canonical page per topic: cross-link to it instead of restating it, and keep concept and theory prose off object and action reference pages.

## Sibling and variant pages

- Apply a page fix to every sibling page of the same kind in the same change. Read each page in full first; text is not pasted across pages blindly.
- Keep AD/non-AD counterpart pages near-identical. Factor a duplicated prose block into `<module>/doc/content/modules/<module>/common/` and `!include` it, with separate AD and non-AD snippets so cross-links resolve to the right variant.

## Media, alerts, landing pages

    !media path/img.png style=width:80% caption=Foo id=fig-foo
    !media path/clip.mp4 autoplay=True loop=True caption=...

Cross-ref via `[!ref](fig-foo)`.

`!alert <brand>` with `error`, `warning`, `note`, `tip`. Block form: `!alert! note title=Foo` ... `!alert-end!`. The `construction` brand is reserved for the stubs `./moosedocs.py generate <App>` writes (`!alert construction title=Undocumented Class`); replace that block, since `moosedocs.py check` flags unreplaced stubs.

Module landing pages use the card grid (`!row!` / `!col! small=12 medium=4 large=4 icon=device_hub` / `!col-end!` / `!row-end!`). Theory-heavy landing pages end with `!syntax complete groups=YourApp level=3`.

## Doc and test coupling

Tests specs point at doc pages via `design = 'MyClass.md'` (suffix-matched). Renaming or moving a page silently breaks SQA traceability, so grep the tests specs when you rename. Spec standards are the `moose-test-standards` skill.

## Reference pages, read one before authoring

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

## Invisible characters, not an ASCII ban

Doc pages are not ASCII-only: accented names, dashes, and unicode math stay as written, and a name's diacritics are never "fixed". The characters below look like ASCII but break `grep`, `!listing re=` slicing, and citation key matching; they arrive through paste and editor smart-quote autocorrect.

| Fix these | U+ | Replace with |
|---|---|---|
| smart single quotes | 2018 / 2019 | `'` |
| smart double quotes | 201C / 201D | `"` |
| non-breaking space | 00A0 | regular space |
| narrow no-break space | 202F | regular space |
| zero-width space | 200B | delete |
| byte-order mark | FEFF | delete |

Scan (from repo root):

    grep -rnP '[\x{2018}\x{2019}\x{201C}\x{201D}\x{00A0}\x{202F}\x{200B}\x{FEFF}]' --include='*.md' doc/

## Build pitfalls

- A stale binary breaks the site: `appsyntax` runs `<exe> --json --allow-test-objects`, so rebuild the app before building docs.
- Extension order: `appsyntax` comes after `katex` in `config.yml`.
- `--fast` disables `appsyntax`, so `!syntax` blocks do not render; the final preview and the smoke run without it.
