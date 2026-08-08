---
name: moose-params
description: Look up the registered parameters of an exact MOOSE object type name (e.g. `ADDirichletBC`) by querying a built app binary — never a cache, so the answer always matches the current checkout. Auto-triggers on phrasings like "what params does X take", "params for X", "dump X", or invoke directly via `/moose-params <Type> [<ParamName> | --full]`. Returns a lean summary by default; a second positional arg drills into a single parameter; `--full` returns the complete JSON node. Costs 15-30 s and needs the app built. Does NOT advise which object to pick — to find candidate objects, search the C++ source with codegraph (`codegraph_explore`).
---

# moose-params

Ask a built app what it actually registered. Arguments arrive as `$ARGUMENTS`: first token is the type name, an optional second token is either a parameter name or `--full`. Never ask for clarification — on bad input emit `ERROR: usage is /moose-params <TypeName> [<ParamName> | --full]` and stop.

## Which binary

Pick by where the object lives, `-opt` first and `-devel` if that is what is built:

| Object | Binary |
|---|---|
| framework or any moose module | `moose/modules/combined/combined-opt` |
| test-only | `moose/test/moose_test-opt` |
| blackbear | `blackbear/blackbear-opt` |
| isopod | `isopod/isopod-opt` |

Paths are relative to the meta-repo root (or the feature worktree root — use the one you are in).

## Get the JSON

```bash
<binary> --json-search <TypeName> 2>/dev/null \
  | awk '/\*\*START JSON DATA\*\*/{f=1;next} /\*\*END JSON DATA\*\*/{f=0} f'
```

Three things about this, none of them guessable:

- **`--json-search` takes a wildcard pattern and matches it against syntax paths, action names, parent paths, and parameter names.** A bare type name therefore matches exactly, and the payload is kilobytes instead of the ~15 MB full tree. Never add `*`; fuzzy matching breaks the contract below.
- **Deprecation warnings and stack traces go to stdout**, interleaved with the payload. The `awk` slice is what makes the output parseable — `2>/dev/null` alone is not enough.
- **It takes 15-30 s.** The app boots and builds its whole syntax tree. Don't kill it early and don't run it twice for one question.

## Read the tree

The object sits at `blocks > <System> > star > subblock_types > <TypeName>`, so find it by that exact leaf key rather than trusting whatever the search returned — a type name that collides with some other object's *parameter* name pulls extra blocks in.

The node carries `description`, `moose_base`, `parent_syntax` (the input block it goes in), `register_file` and `file_info` (source path and line), and `parameters` — an **object keyed by parameter name**, each with `required` as a real boolean, plus `cpp_type`, `basic_type`, `default`, `options`, `group_name`, `deprecated`.

Then `jq` it to the mode asked for: the required/optional split for the default lean view, the whole node for `--full`, or `.parameters["<ParamName>"]` for a single parameter.

## Emit

Print the result verbatim in a fenced ```json block — no summary, no HIT block synthesis. Exact-match-only is the contract: no substring retry, no near-miss suggestions. A fuzzy hit would let a caller "verify" a type that is not registered.

Two failures look alike and are not:

- **No node for that name** — the app started and does not register the type. Believe it. Say so, and name the app you asked, since a blackbear or isopod object won't be in `combined-opt`.
- **No JSON between the markers** — the app never started. Re-run without `2>/dev/null` and surface its stderr; it is usually a `dyld` mismatch after a `moose` bump, or an unbuilt app. This says nothing about whether the type exists.

Out of scope: building or repairing the app, and caring which method binary answered.
