"""The gitignored cache under ``factory/state/``.

It stores exactly what a later run cannot recompute:

    obs          the last successful probe values, for carry-forward
    lane         the last seen lane, for the clamp
    pending      the two-tick debounce of a non-durable lane move
    nags         which heads-up was already raised, so it never repeats
    stamps       content stamps, so a rebuild is byte-identical
    session      the background session registry {bg_id, session_id, started, prompt}
    builds       build start times, for the 3-per-day cap
    manifest     the cheap change test the launchd tick uses

``rm -rf factory/state && factory board`` is a complete repair. It costs one
probe round, and it re-stamps the generated files with the current time.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config, probe


def digest(payload: Any) -> str:
    """A stable digest of any JSON-able value."""
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:16]


class Store:
    """Per-feature JSON files plus two shared ones. No locking needed: the
    renderer is the single writer and it holds ``state/render.lock``."""

    def __init__(self, state_dir: Path):
        self.dir = Path(state_dir)

    # ---- paths ------------------------------------------------------------

    def _path(self, feature: str) -> Path:
        return self.dir / (config.validate_id(feature) + ".json")

    def _ensure(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)

    # ---- per-feature ------------------------------------------------------

    def read(self, feature: str) -> Dict[str, Any]:
        data, ok = probe._read_json(self._path(feature))
        return data if (ok and isinstance(data, dict)) else {}

    def write(self, feature: str, data: Dict[str, Any], dry_run: bool = False) -> None:
        if dry_run:
            return
        self._ensure()
        path = self._path(feature)
        config.write_text_atomic(
            path, json.dumps(data, indent=0, sort_keys=True, default=str)
        )

    def update(self, feature: str, patch: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        data = self.read(feature)
        data.update(patch)
        self.write(feature, data, dry_run)
        return data

    def features(self) -> List[str]:
        if not self.dir.is_dir():
            return []
        out = []
        for p in sorted(self.dir.glob("*.json")):
            if p.name.startswith("_") or p.name in ("gh-cache.json", "manifest.json", "stamps.json"):
                continue
            out.append(p.stem)
        return out

    # ---- carry-forward ----------------------------------------------------

    # A probe's name is not always the key it owns. ``github`` fills ``prs``,
    # ``du`` fills ``reclaimable_kb``, and ``sessions`` fills both the list and
    # the singular row the renderer reads. Comparing names against keys loses
    # exactly the two most volatile facts on the board, so the mapping is
    # explicit so every label resolves to a real observation key.
    CARRY: Dict[str, Tuple[str, ...]] = {
        "github": ("prs",),
        "du": ("reclaimable_kb",),
        "sessions": ("sessions", "session"),
        "worktrees": ("worktree", "foreign", "repos"),
        "ideas": ("idea",),
        "blueprint": ("blueprint",),
        "build": ("build",),
        "skills": ("skills",),
        "workspaces": ("workspaces",),
        "lease": ("lease",),
        "reviews": ("reviews",),
        "note": ("note",),
        "pulse": ("pulse",),
        "branches": (),
        "unfiled-reviews": (),
    }

    def carry_forward(self, obs: Dict[str, Dict[str, Any]]) -> None:
        """Replace every unknown with the last good value and flag the card.

        A failed probe can never register as a change. That exact bug caused
        phantom /digest runs on 2026-09-10 in the Work vault.
        """
        for feature, card in obs.items():
            stale = list(dict.fromkeys(card.get("stale") or []))
            if not stale:
                continue
            prev = (self.read(feature) or {}).get("obs") or {}
            for name in stale:
                head = name.split(":", 1)[0]
                if head == "repo":
                    repo = name.split(":", 1)[1]
                    was = ((prev.get("repos") or {}).get(repo)) or None
                    if was:
                        card.setdefault("repos", {})[repo] = was
                    continue
                for key in self.CARRY.get(name, (name,)):
                    if key in prev:
                        card[key] = prev[key]
            card["stale"] = stale
            card["probe_stale"] = True

    # Measured once and kept: ``factory board --du`` is 18 s, so an ordinary
    # board never measures, and a wholesale replacement would erase the number
    # one run later. Then the note says "2.7 GB" and the next-action why says
    # nothing, on the same card, in the same run.
    STICKY: Tuple[str, ...] = ("reclaimable_kb",)

    def remember(self, obs: Dict[str, Dict[str, Any]], dry_run: bool = False) -> None:
        """Store the merged observation of every card as the new last-good."""
        for feature, card in obs.items():
            keep = {
                k: v
                for k, v in card.items()
                if k not in ("stale", "probe_stale")
            }
            data = self.read(feature)
            was = data.get("obs") or {}
            for key in self.STICKY:
                if keep.get(key) is None and was.get(key) is not None:
                    keep[key] = was[key]
            data["obs"] = keep
            self.write(feature, data, dry_run)

    # ---- nag ageing -------------------------------------------------------

    def heads_up_due(self, feature: str, days: int, silent_days: Optional[int]) -> bool:
        """True exactly once per threshold. Quiet is not a problem."""
        if silent_days is None or silent_days < days:
            return False
        data = self.read(feature)
        return str(days) not in (data.get("nags") or {})

    def heads_up_record(self, feature: str, days: int, now: str, dry_run: bool = False) -> None:
        data = self.read(feature)
        nags = dict(data.get("nags") or {})
        nags[str(days)] = now
        data["nags"] = nags
        self.write(feature, data, dry_run)

    # ---- content stamps ---------------------------------------------------

    def stamp(self, key: str, content_digest: str, now: str) -> str:
        """The stamp for a generated file.

        A stamp changes only when the content below it changes. This is what
        makes "delete every generated note, re-run, get byte-identical files"
        true with a timestamp on the page. ``.factory/last-sync.json`` carries
        the wall-clock truth for the tick.
        """
        path = self.dir / "stamps.json"
        data, ok = probe._read_json(path)
        table = data if (ok and isinstance(data, dict)) else {}
        rec = table.get(key) or {}
        if rec.get("digest") == content_digest and rec.get("at"):
            return rec["at"]
        return now

    def stamp_commit(self, pairs: Dict[str, Tuple[str, str]], dry_run: bool = False) -> None:
        """``{key: (digest, stamp)}`` for every file actually composed."""
        if dry_run or not pairs:
            return
        path = self.dir / "stamps.json"
        data, ok = probe._read_json(path)
        table = data if (ok and isinstance(data, dict)) else {}
        for key, (dg, at) in pairs.items():
            table[key] = {"digest": dg, "at": at}
        self._ensure()
        config.write_text_atomic(path, json.dumps(table, indent=0, sort_keys=True))

    # ---- build cap --------------------------------------------------------

    def builds_today(self, feature: str, now_ts: Optional[float] = None) -> int:
        now_ts = now_ts if now_ts is not None else time.time()
        data = self.read(feature)
        return len([t for t in (data.get("builds") or []) if now_ts - float(t) < 86400])

    # ---- manifest --------------------------------------------------------

    def manifest(self, cfg: config.Config) -> Dict[str, str]:
        """The cheap change test. Cheap means no gh call and no du.

        A probe that fails records the literal ``"unknown"``, never a missing
        key: a missing key is indistinguishable from a real deletion and would
        register as a change and wake the board. ``manifest_changed`` drops
        every ``"unknown"`` from the diff, so a failed probe carries the old
        value forward. That is the phantom-run bug inherited from
        ``digest-changed.py``, closed here for every probe rather than only for
        the worktree enumeration.
        """
        m: Dict[str, str] = {}
        wts, ok = probe.all_worktrees(cfg)
        m["worktrees"] = digest(sorted(wts)) if ok else "unknown"
        for path in sorted(wts):
            for rel in ("specs/blueprint.md", "specs/handoff.md"):
                p = Path(path) / rel
                mt, mok = probe._mtime(p)
                key = "%s:%s" % (os.path.basename(path), rel)
                if not mok:
                    m[key] = "unknown"   # a failed stat is not a deletion
                elif mt:
                    m[key] = str(int(mt))
            cache = Path(path) / ".claude" / "cache"
            if cache.is_dir():
                for f in sorted(cache.glob("moose-build-*.json")):
                    mt, mok = probe._mtime(f)
                    key = "%s:%s" % (os.path.basename(path), f.name)
                    if not mok:
                        m[key] = "unknown"
                    elif mt:
                        m[key] = str(int(mt))
        for p in (cfg.ideas_note,):
            mt, mok = probe._mtime(p)
            if not mok:
                m["Ideas.md"] = "unknown"
            elif mt:
                m["Ideas.md"] = str(int(mt))
        for d in (cfg.timeline_dir, cfg.gates_dir):
            if d.is_dir():
                for f in sorted(d.iterdir()):
                    mt, mok = probe._mtime(f)
                    key = "%s/%s" % (d.name, f.name)
                    if not mok:
                        m[key] = "unknown"
                    elif mt:
                        m[key] = str(int(mt))
        sess_dir = cfg.claude_home / "sessions"
        rows: List[Dict[str, Any]] = []
        sess_ok = True
        if sess_dir.is_dir():
            for f in sorted(sess_dir.glob("*.json")):
                data, dok = probe._read_json(f)
                if not dok:
                    sess_ok = False    # a file that does not parse is unknown
                    continue
                if isinstance(data, dict):
                    rows.append(
                        {
                            k: v
                            for k, v in data.items()
                            if k in ("sessionId", "cwd", "kind", "name", "status", "jobId")
                        }
                    )
        m["sessions"] = digest(rows) if sess_ok else "unknown"
        return m

    def manifest_changed(self, cfg: config.Config) -> Tuple[bool, List[str]]:
        cur = self.manifest(cfg)
        old, ok = probe._read_json(self.dir / "manifest.json")
        if not ok or not isinstance(old, dict) or not old.get("files"):
            return (True, ["no manifest yet"])
        prev = old["files"]
        diff = sorted(
            k for k in set(cur) | set(prev) if cur.get(k) != prev.get(k)
        )
        # An unknown never counts as a change: carry the old value instead.
        diff = [k for k in diff if cur.get(k) != "unknown"]
        return (bool(diff), diff)

    def manifest_commit(self, cfg: config.Config, dry_run: bool = False) -> None:
        if dry_run:
            return
        self._ensure()
        path = self.dir / "manifest.json"
        config.write_text_atomic(
            path, json.dumps({"at": time.time(), "files": self.manifest(cfg)}, indent=0)
        )
