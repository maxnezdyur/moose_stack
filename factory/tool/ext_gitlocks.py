"""Stale git index locks, reported and never removed.

Every checkout of one submodule shares that submodule's ``.git``, and each
worktree keeps its own index under ``.git/worktrees/<name>/``. A git process
killed while it holds ``index.lock`` there leaves a zero-byte file that makes
every later ``git add`` in that worktree fail with "index.lock exists". The
projector was the usual killer: its ``git status`` probe refreshed the index
and its timeout ended the process, which is why ``cli.main`` now sets
``GIT_OPTIONAL_LOCKS=0`` for every child. This module is the tripwire for the
next cause.

Two outputs, no writes:

- ``card_flags`` adds ``git-lock`` to a card whose worktree carries a lock older
  than :data:`STALE_SECONDS`, so the board says it before a build session hits
  it. A session in auto mode cannot remove a file under ``.git`` itself.
- ``doctor_checks`` lists every stale lock under the three submodules with the
  one command that clears it. Removal is a human decision, like a lease.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from . import config

SUBMODULES = ("moose", "blackbear", "isopod")
STALE_SECONDS = 600


def _gitdir(worktree: Path, sub: str) -> Path | None:
    """The real git directory of ``<worktree>/<sub>``: a worktree keeps a
    ``.git`` file whose one line is ``gitdir: <path>``."""
    dotgit = worktree / sub / ".git"
    try:
        if dotgit.is_dir():
            return dotgit
        text = dotgit.read_text().strip()
    except Exception:
        return None
    if text.startswith("gitdir:"):
        return Path(text[len("gitdir:"):].strip())
    return None


def _stale(lock: Path, now: float) -> int | None:
    """Age in seconds when ``lock`` exists and is older than the cutoff."""
    try:
        st = lock.stat()
    except Exception:
        return None
    age = int(now - st.st_mtime)
    return age if age >= STALE_SECONDS else None


def card_flags(card: Any, obs: Dict[str, Any], ctx: Any) -> List[str]:
    wt = (obs or {}).get("worktree")
    if not wt:
        return []
    now = time.time()
    for sub in SUBMODULES:
        gd = _gitdir(Path(wt), sub)
        if gd is None:
            continue
        if _stale(gd / "index.lock", now) is not None:
            return ["git-lock"]
    return []


def doctor_checks(ctx: Any) -> List[Tuple[str, bool, str]]:
    now = time.time()
    found: List[str] = []
    meta = Path(ctx.config.repo_root).expanduser()
    for sub in SUBMODULES:
        root = meta / sub / ".git" / "worktrees"
        try:
            entries = sorted(os.scandir(str(root)), key=lambda e: e.name) if root.is_dir() else []
        except Exception:
            entries = []
        for entry in entries:
            lock = Path(root) / entry.name / "index.lock"
            age = _stale(lock, now)
            if age is None:
                continue
            target = ""
            try:
                target = (Path(root) / entry.name / "gitdir").read_text().strip()
            except Exception:
                pass
            found.append("%s (%s, %d min)" % (lock, target or "?", age // 60))
    return [
        (
            "no stale git index.lock under any worktree",
            not found,
            "a git process died holding the lock, and every `git add` there fails until "
            "it is gone. With no git process running, remove each by hand: %s"
            % ("; ".join("rm %s" % (f.split(" ")[0],) for f in found),),
        )
    ]
