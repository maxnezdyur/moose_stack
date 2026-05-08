# Authoring inputs: HIT language reference

Reach for this guide when you are writing or editing a `.i` file and need to get the **parser-level mechanics** right — block syntax, vector quoting, includes, variable substitution, `type =` dispatch, `active`/`inactive`, and `[GlobalParams]`. This is *not* a catalog of what blocks contain (that lives in per-block guides like `kernels.md`, `bcs.md`, `materials.md`); it is the language the catalog entries are written in.

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. The HIT parser lives at `framework/contrib/hit/`; tokenization is delegated to the WASP HIT interpreter at `framework/contrib/wasp/wasphit/`. MOOSE-side post-processing (variable expansion, `[GlobalParams]` lookup, action dispatch) lives in `framework/src/parser/`.

## When to use this (vs alternatives)

Decide **what kind of edit** you are making first, then pick the reference:

1. Adding/removing a sub-block under an existing top-level block (`[Kernels]`, `[BCs]`, `[Materials]`, ...): you need this guide for the bracket/closer mechanics, *and* the matching per-block catalog (e.g. `kernels.md`) for which `type =` to set and which params are valid.
2. Pulling a fragment in from another file (`!include`), threading a value through `${var}`, or reusing a parameter across many sub-blocks via `[GlobalParams]`: this guide alone — these are language features, independent of which block you're in.
3. Toggling sub-blocks on/off without deleting them (`active = '...'` / `inactive = '...'`): this guide.
4. A parse error like `unused parameter 'foo/bar/baz'`, `parameter 'X' supplied multiple times`, `variables listed as active (...) not found in input`, or `missing closing '}' in brace expression`: this guide explains where each one comes from.
5. Authoring the C++ behind a new block-level keyword (a new Action) or a new MooseObject `type`: out of scope here — see `../moose/action-authoring.md` and `../moose/mooseobject-authoring.md`. Use this guide only to verify the *input syntax* the C++ side will receive.

If you're not sure which top-level block to put a sub-block under, that decision belongs in the per-block guide. This file assumes you already know the block.

## Mechanics

### Sub-blocks and nesting

The grammar is bracket-delimited and recursively nested. Formally (from `framework/contrib/hit/include/hit/parse.h:17`):

```
section          := section_header section_body section_terminator
section_header   := "[" PATH "]"
section_terminator := "[" CLOSING_PATH "]"   // CLOSING_PATH is "../" or ""
```

In practice a `.i` looks like:

```hit
[Kernels]            # top-level block opener
  [diff]             # sub-block opener (modern form)
    type = Diffusion
    variable = u
  []                 # sub-block closer
[]                   # top-level closer
```

- A top-level block is opened with `[Name]` and closed with `[]`. The closer is a bracket pair with empty content.
- A sub-block uses the same `[name]...[]` form. Nesting is unbounded.
- The token grammar is permissive about path characters: `PATH = [a-zA-Z0-9_./:<>+\-]+` (`framework/contrib/hit/include/hit/parse.h:36`). The `.` and `/` characters are legal in a name; they are not path separators inside a single bracket.

#### Legacy `[./sub]` ... `[../]` form

Older inputs use:

```hit
[Variables]
  [./u]              # legacy opener with leading ./
  [../]              # legacy closer with ../
[]
```

Both forms are accepted. The `./` and `../` are stripped at parse time — see `Section::clearLegacyMarkers` at `framework/contrib/hit/src/hit/parse.cc:565`. After normalization the legacy form is *semantically identical* to `[u] ... []`. Mixing forms within one file works, but new inputs should use the modern form. Examples: legacy `test/tests/parser/active_inactive/active_inactive.i:18`; modern `test/tests/parser/include/include_variables.i:2`.

### Parameter values and vectors

A parameter is `name = value` (an optional `:=` is also accepted, see `framework/contrib/wasp/wasphit/README.md:22`). The value is one of:

- A bareword: `type = Diffusion`. No quotes needed; terminated by whitespace or `[`.
- A number: `nx = 10`, `dt = 1.0e-3`. Recognized via `NUMBER = [+-]?[0-9]*(\.[0-9]*)?([eE][+-][0-9]+)?` (`framework/contrib/hit/include/hit/parse.h:35`).
- A boolean: `solve = false`. Accepts `TRUE/true/YES/yes/ON/on` and `FALSE/false/NO/no/OFF/off` (`framework/contrib/hit/src/hit/parse.cc:59`).
- A single-quoted string: `boundary = 'left right'`. Used for **vectors** — whitespace-separated tokens inside `' '` are split into a list.
- A double-quoted string: `expression = "u + v"`. Treated as a single string; preserves spaces.

#### Vector parameters

Vector-valued params use single quotes:

```hit
boundary = 'left right top bottom'
displacements = 'disp_x disp_y'
petsc_options_iname = '-pc_type -pc_hypre_type'
petsc_options_value = 'hypre boomeramg'
```

Tokens are split on whitespace. The split is a plain `istream_iterator` over whitespace (`framework/contrib/hit/src/hit/parse.cc:28`). Tabs and newlines are whitespace too, so a long vector can wrap:

```hit
active = 'kernel_1 kernel_2
         kernel_3 kernel_4'
```

A single bareword is auto-promoted to a 1-element vector when the C++ side asks for `std::vector<...>`. Conversely, if you write `boundary = left` (no quotes) for a vector param, that works for one element only.

#### Comments

`#` begins a comment that runs to end of line. Comments are tracked as `Comment` nodes in the tree (`framework/contrib/hit/src/hit/parse.cc:514`) but ignored for parameter resolution. They may sit at top level, inside any block, or trailing a parameter on the same line.

### `!include` directive

```hit
!include some_other_file.i
```

`!include` is a top-level token (`FILE`) handled by the WASP HIT grammar — see `framework/contrib/wasp/wasphit/HIT.bison:334` and the grammar summary in `framework/contrib/wasp/wasphit/README.md:12`. Mechanics:

- The path is **relative to the directory of the file containing the `!include`**, not the working directory. The nested interpreter pushes that directory onto its search path: `framework/contrib/wasp/wasphit/HITInterpreter.i.h:28`.
- The included file is parsed and its nodes are spliced in **textually at the directive's position**. There is no node-level merge step at include time — the included content simply becomes part of the same tree as if you had pasted it.
- `!include` may appear at file scope, or inside any sub-block, or even between parameters in a sub-block. Because it splices, `!include` can supply a complete block, a single sub-block, or just a few `name = value` lines.

Canonical example — top-level `!include` plus include inside a block plus include inside a sub-block in the same file: `test/tests/parser/include/include.i:8` (top-level), `test/tests/parser/include/include.i:11` (inside `[Kernels]`), `test/tests/parser/include/include.i:16` (inside `[BCs]/[left]`). The included fragments themselves: `test/tests/parser/include/include_variables.i` (a full `[Variables]` block), `test/tests/parser/include/include_diff.i` (a sub-block only — `[diff] ... []`), `test/tests/parser/include/include_left_bc.i` (just parameters `type =`, `boundary =`, `value =` — no brackets).

#### Multiple input files on the CLI

Distinct from `!include`: passing multiple `-i` arguments to a MOOSE app loads each file as a separate parse tree, then **merges** them via `hit::merge` (`framework/contrib/hit/src/hit/parse.cc:1116`, called from `framework/src/parser/Parser.C:353`). Later inputs override fields with the same fullpath in earlier inputs; sections only present later are appended. Use this for "base + overlay" patterns where you don't want to edit the base file. Overrides are reported via `OverrideParamWalker` (`framework/src/parser/Parser.C:194`).

### `${var}` substitution (GetPot-style)

```hit
length = 1.5
radius = 0.5
heat_flux = ${fparse 1e3 / (2 * pi * radius * length)}

[Mesh]
  xmax = ${length}
[]
```

Substitution is performed by `hit::BraceExpander`, declared at `framework/contrib/hit/include/hit/braceexpr.h:101` and walked over the tree at `framework/src/parser/Parser.C:424`. It runs **after** all `!include` splicing and CLI merging are done, so a `${var}` in an included file can reference a variable defined in the parent file or vice versa.

#### Variable resolution order

When the expander hits `${name}` in a field's value, it walks the **parent chain** of the current field, looking for a sibling field named `name` at each ancestor section (`ReplaceEvaler::eval`, `framework/contrib/hit/src/hit/braceexpr.cc:56`). First match wins; the matched field's *value* is substituted (not its name). If no ancestor has it, expansion fails with `no variable 'X' found for substitution expression` (`framework/contrib/hit/src/hit/braceexpr.cc:72`).

Practical implication: define scalars at the **top of the file** (the document root is every other section's ancestor) and they're visible everywhere. Defining `length = 1.5` inside `[Mesh]` makes it visible only inside `[Mesh]` and below.

#### Built-in evalers

`${name}` with one argument is the plain replace described above. Multi-argument forms call a registered "evaler", registered at `framework/src/parser/Parser.C:419`:

- `${fparse <expression>}` — evaluates a function-parser arithmetic expression, with `pi` and `e` predefined and any in-scope `${var}` available as identifiers. Source: `FuncParseEvaler::eval` at `framework/src/parser/Parser.C:29`. Example: `test/tests/coord_type/coord_type_rz_general.i:20` (`perimeter = ${fparse 2 * pi * radius}`).
- `${env <NAME>}` — pulls `getenv("NAME")`. Source: `EnvEvaler::eval` at `framework/contrib/hit/src/hit/braceexpr.cc:36`.
- `${raw <stuff>}` — concatenates args literally; useful for assembling strings that shouldn't be reparsed.
- `${units <number> <from> -> <to>}` and `${units <number> <unit>}` — unit conversion / annotation. Source: `UnitsConversionEvaler::eval` at `framework/src/parser/Parser.C:83`. Example: `test/tests/parser/param_substitution/unit_conversion.i:23`.
- `${replace <name>}` — explicit form of the default replace; rarely needed.

`${var}` without a registered evaler keyword and a single token is just `replace` (`framework/contrib/hit/src/hit/braceexpr.cc:152`).

#### "Cycle detection"

There is no explicit cycle detection. Each field is expanded once via a tree walk in document order (`framework/contrib/hit/src/hit/braceexpr.cc:115`). When `${a}` is replaced by the value of field `a`, the expander does *not* recursively re-expand the result. If `a = ${b}` and `b = ${a}`, both expansions look up the literal value of the other field — which is the still-unexpanded text `${...}` — and you get a "no variable found" error rather than infinite recursion. Define variables before using them, conceptually.

#### Bringing values in from the CLI

`-cli-args 'foo=42'` (or `MyApp-opt foo=42 ...`) is parsed as its own HIT root and merged in at `framework/src/parser/Parser.C:399`. Top-level CLI assignments are visible to `${foo}` everywhere because they sit at the document root.

### `type =` dispatch

Inside any block whose Action derives from `MooseObjectAction`, the `type =` parameter selects which registered C++ class to instantiate:

```hit
[Kernels]
  [diff]
    type = ADDiffusion          # picks the AD diffusion kernel
    variable = u
  []
  [src]
    type = ADBodyForce          # picks the AD body force kernel
    variable = u
    function = forcing_fn
  []
[]
```

`MooseObjectAction` declares `type` as required (`framework/src/actions/MooseObjectAction.C:22`) and reads it in its constructor (`framework/src/actions/MooseObjectAction.C:32`). The string is passed to `_factory.getValidParams(_type)` (`framework/src/actions/MooseObjectAction.C:37`), which looks `_type` up in the global `Factory` (objects registered via `registerMooseObject`). The remaining parameters in the sub-block are then validated against the chosen class's `validParams` — a misspelling becomes `unused parameter '...'; did you mean '...'?` (`framework/src/parser/Builder.C:171`).

So **changing `type =` changes which parameters are valid**. Swap `type = Diffusion` for `type = MatDiffusion` and the rest of the sub-block's params must be reconciled — see the per-block catalog for what each `type` accepts. Not every block uses `type` at a sub-block level (e.g. `[Variables]/[u]` does not), but `[Executioner]`, `[Mesh]/[gen]`, `[Kernels]/[diff]`, `[Materials]/[m]` all do. The signal: does this sub-block instantiate a MooseObject? If yes, `type =` is required.

### `active =` and `inactive =`

Toggle sub-blocks on/off without commenting them out:

```hit
[AuxKernels]
  active = 'aux2 aux4'
  [aux1]   ... []
  [aux2]   ... []
  [aux3]   ... []
  [aux4]   ... []
[]
```

- `active = 'a b c'` — only sub-blocks `a`, `b`, `c` of this section are processed. Others are silently skipped.
- `inactive = 'x y'` — sub-blocks `x` and `y` are skipped; everything else is processed.
- The two are **mutually exclusive in the same section**; using both raises `'active' and 'inactive' parameters both provided in section ...` (`framework/src/parser/Parser.C:220`).
- Listing a name that is not actually a child of this section raises `variables listed as active (...) not found in input` (`framework/src/parser/Parser.C:238`). This catches typos.
- `inactive = ''` (empty list) is the explicit "everything is active" form and is common in templates.
- Skipped sub-blocks are **not parsed for parameter validity** — see the comment at `test/tests/parser/active_inactive/active_inactive.i:25`. You can stash deliberately-broken sub-blocks under `inactive = '...'` and the input still loads.
- Resolution lives in `isSectionActive` (`framework/src/parser/Builder.C:45`); the consistency check is `BadActiveWalker::walk` (`framework/src/parser/Parser.C:210`).

Canonical example: `test/tests/parser/active_inactive/active_inactive.i:16-41`.

### Parametric replication

There is **no built-in repeat/loop construct** in HIT. You cannot write `[./sub_${i}]` and have the parser instantiate sub-blocks for `i = 0..N`. Variable expansion happens on field *values*, not on section *names* — the brace expander only walks `Field` nodes (`framework/contrib/hit/src/hit/braceexpr.cc:88-90`).

If you need many similar sub-blocks, the options are:

- Hand-write them and use `${var}` for values that vary by index.
- Generate the `.i` from a script that writes out N sub-blocks before invoking MOOSE.
- Use a MOOSE Action that *itself* expands into multiple objects (e.g. the Physics shorthands — see `solid-mechanics.md`, `heat-transfer.md`).

Variables in section names that you do see in the wild (e.g. `[${some_name}]`) are **not** parser-supported. If you encounter that, treat it as a bug or a custom preprocessing step.

### `[GlobalParams]`

```hit
[GlobalParams]
  displacements = 'u'
[]
```

Parameters under `[GlobalParams]` are **inherited** by every sub-block in the input that declares the same parameter name in its `validParams`. They are not magic globals — a sub-block whose chosen `type` does not have a parameter named `displacements` simply ignores the global.

#### Resolution order (precedence)

When the Builder is filling parameters for a sub-block, it asks, for each param name:

1. Is there a literal `name = value` in **this sub-block**? Use that. (`framework/src/parser/Builder.C:682`)
2. Otherwise, is there a `name = value` in `[GlobalParams]`? Use that. (`framework/src/parser/Builder.C:688`)
3. Otherwise, fall back to the C++ default (or report a missing required param).

So **local sub-block always wins over `[GlobalParams]`**. This is how you set a default for ten kernels and override it on one.

`[GlobalParams]` can hold any parameter name. Common patterns: `displacements` (for solid-mechanics kernels and BCs), `block` or `boundary` (when many sub-blocks act on the same domain region), the trio of HDG variables (`variable`, `face_variable`, `gradient_variable`) when authoring a hybridized DG input. See `kernels.md` HDG section for the typical HDG idiom.

Canonical example: `test/tests/misc/displaced_mesh_coupling/ad.i:1-3` defines `displacements = 'u'` globally; the sub-block at line 17 uses `use_displaced_mesh = true` without restating `displacements`.

## Cross-cutting concerns

### Order of operations during parse

`Parser::parse` (`framework/src/parser/Parser.C:299`) runs: (1) parse each `-i` file with `!include` expanded inline, (2) merge multiple `-i` files via `hit::merge` (later overrides earlier), (3) merge any `cli=value` args at the document root, (4) walk the tree with `BraceExpander` to expand `${...}`, (5) check duplicates and `active`/`inactive` consistency, (6) hand off to `Builder` which dispatches to Actions and reads `type =`.

Implication: `${var}` can reference values defined only via CLI or only in an `!include`'d file (those are present before expansion). But an `active = '...'` mismatch is detected on the merged tree, so you can't "fix" a bad active list with a later `-i`.

### Override semantics summary

| Source | Wins over | Mechanism |
| --- | --- | --- |
| Local `name = value` in a sub-block | `[GlobalParams]/name` | Builder resolution order (`Builder.C:682`) |
| Later `-i` file's field | Earlier `-i` file's same field | `hit::merge` overwrites Field values (`parse.cc:1083`) |
| `cli=` argument | Anything in any file | merged last (`Parser.C:399`) |
| `active`/`inactive` filter | Children of this section | `isSectionActive` short-circuits before extraction |
| `type =` choice | Which `validParams` apply | `MooseObjectAction::_type` drives factory dispatch |

### Common parse errors and what they mean

- `unused parameter 'foo/bar/baz'; did you mean 'qux'?` — param is not in the chosen `type`'s `validParams`; either `type =` is wrong or the name is misspelled. (`framework/src/parser/Builder.C:159`)
- `parameter 'foo/bar' supplied multiple times` — same fullpath set twice (within one file or after merge). (`framework/src/parser/Parser.C:163`)
- `'active' and 'inactive' parameters both provided in section 'Foo'` — pick one. (`framework/src/parser/Parser.C:220`)
- `variables listed as active (a, b) in section 'Foo' not found in input` — a name in the list isn't a sub-block of `[Foo]`. (`framework/src/parser/Parser.C:238`)
- `no variable 'X' found for substitution expression` — `${X}` could not be resolved by walking the parent chain; define `X` at file scope. (`framework/contrib/hit/src/hit/braceexpr.cc:72`)
- `missing closing '}' in brace expression` / `invalid brace-expression command 'foo'` — unbalanced `${...}` or unregistered evaler keyword. (`framework/contrib/hit/src/hit/braceexpr.cc:157,188`)
- `section '[Foo]' does not have an associated Action` — top-level name is unknown to the running app: wrong app, misspelling, or missing module. (`framework/src/parser/Builder.C:208`)
- `<file>:<line>.<col>: syntax error, unexpected end of line, expecting ]` — bracket not closed before newline (WASP grammar, e.g. `HIT.bison:352`).
- File-not-found inside `!include` — path is relative to the *including* file's directory, not `pwd`.

## Minimal scaffold

A small steady diffusion that exercises `[GlobalParams]`, `!include`, and `${var}` substitution:

```hit
# main.i — driver

# top-level vars: visible everywhere via ${...}
length = 1.0
nx     = 20

[GlobalParams]
  # propagates to any sub-block whose validParams declares 'use_displaced_mesh'
  use_displaced_mesh = false
[]

[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim  = 1
    nx   = ${nx}
    xmax = ${length}
  []
[]

# pulls in [Variables] [u] [] from a fragment file
!include _variables.i

[Kernels]
  [diff]
    type = ADDiffusion
    variable = u
  []
  [src]
    type = ADBodyForce
    variable = u
    value = ${fparse 2.0 / length}
  []
[]

[BCs]
  active = 'left right'   # toggle: drop 'right' to leave it free
  [left]
    type = ADDirichletBC
    variable = u
    boundary = left
    value = 0
  []
  [right]
    type = ADDirichletBC
    variable = u
    boundary = right
    value = 1
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
[]

[Outputs]
  exodus = true
[]
```

```hit
# _variables.i — fragment included by main.i

[Variables]
  [u]
  []
[]
```

What this exercises:

- `${length}` and `${nx}` resolve to top-level scalars; they appear inside `[Mesh]/[gen]` because the document root is an ancestor of every section.
- `${fparse 2.0 / length}` evaluates a small arithmetic expression on the fly.
- `[GlobalParams]/use_displaced_mesh = false` propagates to `[diff]` and `[src]` (both `ADDiffusion` and `ADBodyForce` declare `use_displaced_mesh` in their `validParams`).
- `!include _variables.i` splices the `[Variables]` block in textually; you could equally well move that block back into `main.i` with no semantic change.
- `active = 'left right'` is currently a no-op (lists all children); change it to `'left'` to drop the right BC without deleting it.
- Each sub-block's `type = ...` selects the C++ class — change `type = ADDiffusion` to `type = ADMatDiffusion` and the validation rules for the rest of `[diff]` change accordingly.
