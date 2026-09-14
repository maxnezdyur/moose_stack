"""The ``config`` verb: what this machine resolved, and where each value came from.

The projector carries no machine-specific literal. Every path, binary and cap
comes from :mod:`tool.config`, which reads, in order, the key's environment
variable, ``~/.config/moose-factory/config.toml`` (``$MOOSE_FACTORY_CONFIG``
overrides the location), then a default derived from ``$HOME``.

    factory config              the table a human reads
    factory config --json       the same, as JSON
    factory config --sh         shell assignments, for a script to eval
    factory config --get <key>  one raw value, for a script that wants one

``--sh`` is what ``moose-factory-tick.sh`` evals, so the tick and the library
can never disagree about where the vault is.

This module also prints the resolved block above ``factory doctor``'s checks,
and adds the two checks the config file itself can fail.
"""

from __future__ import annotations

import json
from typing import Any, List, Tuple

from . import config

HELP = {"config": "print the resolved per-machine config and where each value came from"}

# Reads one small file: no probe round, no 6.5 s.
NO_CTX_VERBS = ("config",)

USAGE = "usage: factory config [json | sh | get <key>]   (--json, --sh, --get also work)"

# The prefix every `--sh` assignment carries, so an eval cannot collide with a
# variable the calling script already owns.
SH_PREFIX = "FACTORY_CFG_"


def _sh_quote(value: str) -> str:
    return "'" + str(value).replace("'", "'\\''") + "'"


def sh_lines(cfg: Any) -> List[str]:
    """``FACTORY_CFG_<KEY>='<value>'`` for every setting, safe to eval."""
    values = config.as_dict(cfg)["values"]
    out = []
    for key in config.KEY_NAMES:
        out.append("%s%s=%s" % (SH_PREFIX, key.upper(), _sh_quote(values[key])))
    return out


def run(argv: List[str], cfg: Any) -> Tuple[int, List[str]]:
    """``(exit code, lines to print)``. Pure, so the tests can call it.

    ``json``, ``sh``, ``get`` and their ``--`` spellings are the same word.
    Both are accepted because argparse hands an extension verb its arguments
    through ``REMAINDER``, which refuses a leading option string: ``factory
    config json`` always reaches here, and the launcher inserts the ``--`` that
    makes ``factory config --json`` reach here too.
    """
    args = [a[2:] if a.startswith("--") and len(a) > 2 else a for a in argv]
    if "-h" in args or "help" in args:
        return (0, [USAGE])
    if "get" in args:
        i = args.index("get")
        if i + 1 >= len(args):
            return (3, [USAGE])
        key = args[i + 1]
        if key not in config.KEY_NAMES:
            return (
                3,
                [
                    "config: no setting %r. Known: %s"
                    % (key, ", ".join(config.KEY_NAMES))
                ],
            )
        return (0, [config.as_dict(cfg)["values"][key]])
    if "json" in args:
        return (0, [json.dumps(config.as_dict(cfg), indent=2, sort_keys=True)])
    if "sh" in args:
        return (0, sh_lines(cfg))
    return (0, config.describe(cfg))


def _verb(argv: List[str], ctx: Any) -> int:
    code, lines = run(list(argv), ctx.config)
    for line in lines:
        print(line)
    return code


VERBS = {"config": _verb}


def doctor_checks(ctx: Any) -> List[Tuple[str, bool, str]]:
    """Print the resolved block, then report what the config file can get wrong.

    The block is printed rather than returned, because a check row is one line
    of pass or fail and this is a table of facts. ``run_doctor`` collects every
    row before it prints any of them, so the block lands above the checks.
    """
    cfg = ctx.config
    for line in config.describe(cfg):
        print(line)
    print("")
    rows: List[Tuple[str, bool, str]] = []
    rows.append(
        (
            "config file parses",
            True,                      # a malformed file never reaches doctor: exit 3
            "",
        )
    )
    unknown = list(getattr(cfg, "unknown_keys", ()) or ())
    rows.append(
        (
            "every key in the config file is a setting",
            not unknown,
            "ignored: %s. Known keys: %s"
            % (", ".join(unknown), ", ".join(config.KEY_NAMES)),
        )
    )
    return rows
