"""Four monotonic attributed records per feature.

``.factory/gates/<feature>.json`` holds ``{gate: {state, when, by, via}}`` for
``blueprint_approved``, ``ship``, ``pr_ready`` and ``teardown``. Committed,
because a grant is an input.

Three channels, all human and all durable:

    verb        `factory grant <feature> <gate>`
    checkbox    a ticked box in the note's head block, read back before composing
    observed    a GitHub fact: an open PR proves `ship`, isDraft:false proves `pr_ready`

A gate never ungrants, so a double tick or an Obsidian conflict copy is
harmless. ``pr_ready`` is human-only: ``/moose-ship`` is forbidden from setting
it, and the only automatic channel for it is the observed fact that Max himself
produced in the GitHub user interface.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config, probe
from .model import GATES, GRANTED, PENDING


class GateStore:
    def __init__(self, gates_dir: Path, dry_run: bool = False):
        self.dir = Path(gates_dir)
        self.dry_run = dry_run
        # A dry run still has to show what the grant would do, so it keeps the
        # would-be records in memory instead of on disk.
        self._overlay: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def _path(self, feature: str) -> Path:
        return self.dir / (config.validate_id(feature) + ".json")

    def get(self, feature: str) -> Dict[str, Dict[str, Any]]:
        """All four records, pending where absent."""
        data, ok = probe._read_json(self._path(feature))
        table = dict(data) if (ok and isinstance(data, dict)) else {}
        table.update(self._overlay.get(feature) or {})
        out: Dict[str, Dict[str, Any]] = {}
        for gate in GATES:
            rec = table.get(gate)
            if isinstance(rec, dict) and rec.get("state") == GRANTED:
                out[gate] = {
                    "state": GRANTED,
                    "when": rec.get("when"),
                    "by": rec.get("by") or "max",
                    "via": rec.get("via") or "verb",
                }
            else:
                out[gate] = {"state": PENDING, "when": None, "by": None, "via": None}
        return out

    def grant(
        self,
        feature: str,
        gate: str,
        when: str,
        by: str = "max",
        via: str = "verb",
    ) -> bool:
        """Monotonic. Returns True only when this call changed the record."""
        if gate not in GATES:
            raise ValueError(
                "unknown gate %r: one of %s" % (gate, ", ".join(GATES))
            )
        cur = self.get(feature)
        if cur[gate]["state"] == GRANTED:
            return False
        record = {"state": GRANTED, "when": when, "by": by, "via": via}
        if self.dry_run:
            self._overlay.setdefault(feature, {})[gate] = record
            return True
        table = {g: r for g, r in cur.items() if r["state"] == GRANTED}
        table[gate] = record
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self._path(feature)
        config.write_text_atomic(path, json.dumps(table, indent=1, sort_keys=True))
        return True

    def features(self) -> List[str]:
        if not self.dir.is_dir():
            return []
        return sorted(p.stem for p in self.dir.glob("*.json"))


def observed(card_obs: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """Gates an on-disk or GitHub fact already proves, as ``[(gate, via, why)]``.

    An open PR proves `ship`: Max opened it. ``isDraft: false`` proves
    `pr_ready`: only Max can mark a draft ready in the user interface.

    GitHub is the only observed channel. The plan lists three grant channels,
    all human and all durable: the verb, a ticked checkbox, and a GitHub fact.
    """
    out: List[Tuple[str, str, str]] = []
    prs = card_obs.get("prs") or []
    openp = [p for p in prs if (p.get("state") or "").upper() == "OPEN"]
    merged = [p for p in prs if (p.get("state") or "").upper() == "MERGED"]
    for pr in openp + merged:
        out.append(("ship", "gh", "PR #%s exists" % (pr.get("number"),)))
        break
    for pr in openp:
        if pr.get("isDraft") is False:
            out.append(
                ("pr_ready", "gh", "PR #%s is no longer a draft" % (pr.get("number"),))
            )
            break
    for pr in merged:
        out.append(("pr_ready", "gh", "PR #%s merged" % (pr.get("number"),)))
        break
    # There is deliberately no blueprint channel. A file in a worktree is a
    # file any agent with Edit can write, and a grant recorded
    # {by: "max", via: "blueprint"} would attribute an agent's edit to Max in a
    # record that never ungrants. The blueprint already proves the lane (rank 3);
    # only Max's verb or his ticked box proves the gate.
    seen = set()
    uniq = []
    for gate, via, why in out:
        if gate in seen:
            continue
        seen.add(gate)
        uniq.append((gate, via, why))
    return uniq


def sync(
    store: GateStore,
    feature: str,
    card_obs: Dict[str, Any],
    now: str,
    timeline: Optional[Any] = None,
) -> Dict[str, Dict[str, Any]]:
    """Apply the checkbox and observed channels, then return all four records.

    Called before composing a note, so a box ticked ten seconds ago survives
    this run. The worst case is a grant that registers one tick late.
    """
    ticked = ((card_obs.get("note") or {}).get("ticked")) or []
    for gate in ticked:
        if gate in GATES and store.grant(feature, gate, now, by="max", via="checkbox"):
            if timeline is not None:
                timeline.append(
                    feature,
                    {"at": now, "event": "gate-granted", "gate": gate, "via": "checkbox"},
                )
    for gate, via, why in observed(card_obs):
        if store.grant(feature, gate, now, by="max", via=via):
            if timeline is not None:
                timeline.append(
                    feature,
                    {
                        "at": now,
                        "event": "gate-granted",
                        "gate": gate,
                        "via": via,
                        "why": why,
                    },
                )
    return store.get(feature)
