---
name: moose-params
description: Look up the registered-syntax YAML entry for an exact MOOSE object type name (e.g. `ADDirichletBC`). Auto-triggers on phrasings like "what params does X take", "params for X", "dump X", or invoke directly via `/moose-params <Type> [<ParamName> | --full]`. Returns a lean summary by default; a second positional arg drills into a single parameter; `--full` returns the complete YAML node. Reads from `<meta-repo>/.claude/cache/syntax.yaml`. Does NOT advise which object to pick — to find candidate objects, search the C++ source with codegraph (`codegraph_search` / `codegraph_explore`).
allowed-tools:
  - Bash(yq *)
  - Bash(ls *)
  - Bash(stat *)
  - Bash(test *)
  - Read
---

# moose-params

Look up the YAML node for an exact MOOSE object type name. Arguments arrive as `$ARGUMENTS` — never ask the user for clarification; on bad input emit the usage error below and stop.

## Parse `$ARGUMENTS`

Split on whitespace. First token is the type name; the second, if present, picks the mode:

| Tokens                   | Mode    | Notes                                                        |
|--------------------------|---------|--------------------------------------------------------------|
| `<TypeName>`             | `lean`  | one token only                                               |
| `<TypeName> --full`      | `full`  | exact flag `--full`                                          |
| `<TypeName> <ParamName>` | `param` | second token is the parameter name; must not start with `--` |

Empty `$ARGUMENTS`, three or more tokens, or a `--` flag other than `--full` → output exactly `ERROR: usage is /moose-params <TypeName> [<ParamName> | --full]` and stop.

## Run exactly one command

Substitute `$TYPE` (and `$PARAM` in param mode).

### Mode `lean` (default)

```bash
yq -y --arg name "$TYPE" '
  [.. | objects | select(has("name") and ((.name | split("/") | last) == $name))] as $hits
  | if ($hits | length) == 0 then
      "ERROR: no exact match for \"\($name)\"" | halt_error(1)
    else
      $hits | map({
        name,
        description,
        required: [.parameters[]? | select(.required == "Yes") | {(.name): .description}] | add,
        optional: [.parameters[]? | select(.required != "Yes") | .name]
      })[]
    end
' /Users/maxnezdyur/projects/moose_stack/.claude/cache/syntax.yaml
```

### Mode `full`

```bash
yq -y --arg name "$TYPE" '
  [.. | objects | select(has("name") and ((.name | split("/") | last) == $name))] as $hits
  | if ($hits | length) == 0 then
      "ERROR: no exact match for \"\($name)\"" | halt_error(1)
    else
      $hits[]
    end
' /Users/maxnezdyur/projects/moose_stack/.claude/cache/syntax.yaml
```

### Mode `param`

```bash
yq -y --arg name "$TYPE" --arg param "$PARAM" '
  [.. | objects | select(has("name") and ((.name | split("/") | last) == $name))] as $hits
  | if ($hits | length) == 0 then
      "ERROR: no exact match for \"\($name)\"" | halt_error(1)
    else
      [$hits[].parameters[]? | select(.name == $param)] as $params
      | if ($params | length) == 0 then
          "ERROR: no parameter \"\($param)\" on type \"\($name)\"" | halt_error(1)
        else
          $params[]
        end
    end
' /Users/maxnezdyur/projects/moose_stack/.claude/cache/syntax.yaml
```

## Emit

Print stdout verbatim in a fenced ```yaml block — no summary, no HIT block synthesis. On non-zero exit, print stderr verbatim and stop: no retry, no fallback to substring search. Exact-match-only is the contract; fuzzy results would let callers "verify" types that don't exist.

If the cache file is missing (yq complains), tell the user once:

```
Cache missing. Run:
  bash /Users/maxnezdyur/projects/moose_stack/.agents/skills/moose-params/refresh.sh <path-to-app-opt-binary>
```

Out of scope: choosing *which* object to pick (that's codegraph over the C++ source), auto-regenerating the cache, caring which binary produced it.
