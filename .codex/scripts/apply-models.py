#!/usr/bin/env python3
"""Re-apply .codex/model-map.json to the generated .codex/agents/*.toml.

claude-to-codex --write regenerates every agent TOML with its built-in
claude-model -> gpt-5.5 tier mapping (opus->xhigh, sonnet->high, haiku->medium).
This script re-applies your overrides afterwards, so run it after every --write.

model-map.json shape:
  {
    "default_model": null,                  // null: STRIP the model line so Codex
                                            // uses its own configured default model
    "agents": {                             // per-agent pins (win over default)
      "moose-docs-builder": { "model": "gpt-5.5", "effort": "low" }
    }
  }
Omit "effort" to keep the tool's tier-derived model_reasoning_effort
(opus->xhigh, sonnet->high, haiku->medium), which applies to whatever model runs.
"""
import json
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
map_path = root / ".codex" / "model-map.json"
if not map_path.exists():
    sys.exit("no .codex/model-map.json; nothing to do")
mapping = json.loads(map_path.read_text())
default_model = mapping.get("default_model")

def set_key(segments, key, value):
    """Set `key = "value"` in the non-string segments; return whether it was found."""
    pat = re.compile(rf'^{key}\s*=\s*"[^"\n]*"', re.M)
    found = False
    for i in range(0, len(segments), 2):  # even indices = outside '"""' strings
        if pat.search(segments[i]):
            segments[i] = pat.sub(f'{key} = "{value}"', segments[i])
            found = True
    return found

def drop_key(segments, key):
    pat = re.compile(rf'^{key}\s*=\s*"[^"\n]*"\n?', re.M)
    for i in range(0, len(segments), 2):
        segments[i] = pat.sub("", segments[i])

changed = 0
tomls = sorted((root / ".codex" / "agents").glob("*.toml"))
for toml in tomls:
    overrides = mapping.get("agents", {}).get(toml.stem, {})
    model = overrides.get("model") or default_model
    effort = overrides.get("effort")
    text = toml.read_text()
    # Split off '"""..."""' blocks so instruction bodies are never touched.
    parts = re.split(r'("""[\s\S]*?""")', text)
    if model:
        if not set_key(parts, "model", model):
            parts[-1] += f'\nmodel = "{model}"\n'
    else:
        drop_key(parts, "model")  # no pin -> Codex uses its configured default
    if effort and not set_key(parts, "model_reasoning_effort", effort):
        parts[-1] += f'\nmodel_reasoning_effort = "{effort}"\n'
    new = "".join(parts)
    if new != text:
        toml.write_text(new)
        changed += 1

print(f"model map: {changed}/{len(tomls)} agent toml(s) updated")
