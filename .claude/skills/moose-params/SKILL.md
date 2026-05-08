---
name: moose-params
description: Look up the registered-syntax YAML entry for an exact MOOSE object type name (e.g. `ADDirichletBC`). Auto-triggers on phrasings like "what params does X take", "params for X", "dump X", or invoke directly via `/moose-params <Type> [<ParamName> | --full]`. Returns a lean summary by default; a second positional arg drills into a single parameter; `--full` returns the complete YAML node. Reads from `<meta-repo>/.claude/cache/syntax.yaml`. Does NOT advise which object to pick — for that, see `.claude/contexts/moose-input/`.
allowed-tools:
  - Bash(yq *)
  - Bash(ls *)
  - Bash(stat *)
  - Bash(test *)
  - Read
context: fork
agent: general-purpose
model: haiku
---

# moose-params

Look up the YAML node for an exact MOOSE object type name. The user has already provided arguments as `$ARGUMENTS` — do **not** ask them for clarification.

## Step 1 — parse `$ARGUMENTS`

Split `$ARGUMENTS` on whitespace. The first token is always the type name. The second token, if present, picks the mode:

| Tokens                            | Mode      | Notes                                       |
|-----------------------------------|-----------|---------------------------------------------|
| `<TypeName>`                      | `lean`    | one token only                              |
| `<TypeName> --full`               | `full`    | exact flag `--full`                         |
| `<TypeName> <ParamName>`          | `param`   | second token is the parameter name; must not start with `--` |

If `$ARGUMENTS` is empty, output exactly `ERROR: usage is /moose-params <TypeName> [<ParamName> | --full]` and stop.

Three or more tokens, or a second token that starts with `--` but isn't `--full` → error with the same usage line.

## Step 2 — run the matching command

Run **exactly one** of the three commands below — pick by mode. Substitute `$TYPE` with the type name from step 1, and (in param mode) `$PARAM` with the parameter name (the second token).

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

## Step 3 — emit

Print stdout in a fenced ```yaml block, verbatim. No summary, no commentary, no HIT block synthesis.

If the command exits non-zero, print stderr verbatim and stop. Do not retry, do not fall back to substring search, do not ask clarifying questions.

If the cache file does not exist (yq complains about missing file), tell the user once:

```
Cache missing. Run:
  bash /Users/maxnezdyur/projects/moose_stack/.claude/skills/moose-params/refresh.sh <path-to-app-opt-binary>
```

## Out of scope

- Choosing *which* object to pick — that's `.claude/contexts/moose-input/`.
- Substring/fuzzy match.
- Auto-regenerating the cache.
- Caring which binary produced the cache.
