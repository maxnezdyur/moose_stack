"""Append-only NDJSON per feature, under the vault's ``.factory/timeline/``.

One line per transition or hook event. Committed, because it is an input: no
run can recompute why a lane moved three days ago.

There is no ``flock(1)`` binary on this machine, and 21 concurrent writers
through ``fcntl.flock`` on this exact path produced 21 clean lines. The lock is
held across the whole record, not only the write call.
"""

from __future__ import annotations

import fcntl
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config


class TimelineWriter:
    def __init__(self, timeline_dir: Path, dry_run: bool = False):
        self.dir = Path(timeline_dir)
        self.dry_run = dry_run

    def _path(self, feature: str) -> Path:
        return self.dir / (config.validate_id(feature) + ".ndjson")

    def append(self, feature: str, event: Dict[str, Any]) -> bool:
        """One flock'd line. Returns False when the write was skipped."""
        if self.dry_run:
            return False
        rec = dict(event)
        rec.setdefault("at", "")
        path = self._path(feature)
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
                    f.flush()
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return True
        except Exception:
            return False

    def read(self, feature: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        path = self._path(feature)
        out: List[Dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    lines = f.readlines()
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except FileNotFoundError:
            return []
        except Exception:
            return []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if isinstance(rec, dict):
                    out.append(rec)
            except Exception:
                continue
        return out[-limit:] if limit else out

    def has(self, feature: str, kind: str) -> bool:
        """True when this kind of event was already recorded. Keeps adoption,
        demotion and heads-up lines from repeating on every run."""
        return any(r.get("event") == kind for r in self.read(feature))

    def all_features(self) -> List[str]:
        if not self.dir.is_dir():
            return []
        return sorted(p.stem for p in self.dir.glob("*.ndjson"))

    def recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """The newest lines across every feature, for "Since yesterday"."""
        rows: List[Dict[str, Any]] = []
        for feature in self.all_features():
            for rec in self.read(feature):
                rec = dict(rec)
                rec.setdefault("feature", feature)
                rows.append(rec)
        rows.sort(key=lambda r: str(r.get("at") or ""))
        return rows[-limit:]
