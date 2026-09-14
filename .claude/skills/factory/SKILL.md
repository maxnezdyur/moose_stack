---
name: factory
description: Regenerates the moose-factory board and relays the masthead and the needs-you rows. Use for "/factory", "show the board", "what needs me". Manual invoke only.
disable-model-invocation: true
effort: low
---

# /factory

Regenerates the vault board and relays it. The board is the answer to "what is going on": every
feature card, the studies, and one named next move per card.

The projector is called by **absolute path**, because this skill runs inside whatever worktree
invoked it and no `factory/` directory exists there. The path is resolved, never a literal: the
command below reads the `meta_repo` key of this machine's `~/.config/moose-factory/config.toml`
and falls back to `$HOME/projects/moose_stack`. No user name appears in this file, so the same
skill works on every machine. A checkout anywhere but `$HOME/projects/moose_stack` needs that key:
this skill cannot walk up to the checkout the way `tool/config.py` does. `factory/install.sh`
writes the key, and `zsh factory/install.sh --config` writes it and nothing else.

Relay in **12 lines maximum**:

1. The masthead: the card count, the workspace count, the open-PR count, and any whole-board flag
   line (stale pipelines, branch mismatches, upstream-ref ages).
2. The `## Needs you` rows, one line each, as `<card>: <next move> - <why>`. Keep the command
   copyable and verbatim.
3. One closing line with the backlog line if the board printed one, else the posture counts.

Do not restate the waiting, parked or done groups, do not summarise a card the board did not put in
needs-you, and do not run any command the board printed. `factory` writes the vault and nothing else;
the next move is the user's to run. A non-zero exit is relayed verbatim as the first line: 1 means a
human should look, 2 a refused write (a note lost one of its four markers), 3 a missing path, a
malformed `config.toml` or the wrong host. If the board output is absent below, say so and offer the
command instead of guessing.

!`C="${MOOSE_FACTORY_CONFIG:-$HOME/.config/moose-factory/config.toml}"; M="$(sed -n -e 's/[[:space:]]*#.*$//' -e 's/^[[:space:]]*meta_repo[[:space:]]*=[[:space:]]*//p' "$C" 2>/dev/null | head -n 1 | tr -d '"')"; M="${M:-$HOME/projects/moose_stack}"; F="${M/#\~/$HOME}/factory/factory"; "$F" board 2>&1; echo "--- board ---"; "$F" status 2>&1`
