"""Automation: the launchd tick's change gate, its notifier and its doctor checks.

The 120-second tick is ``~/.local/bin/moose-factory-tick.sh``, installed from
``factory/install.sh`` together with
``~/Library/LaunchAgents/com.moose-factory.plist``, which that script generates
from a template. Every path here is derived from ``$HOME`` or from
:mod:`tool.config`; none is a literal. This module is the Python half of that
loop, and the only place the loop's policy lives:

    python -m tool.ext_tick check     exit 0 = an input changed, 1 = nothing new
    python -m tool.ext_tick notify    one banner per card newly in needs-you
    python -m tool.ext_tick postures  the posture of every card, from the notes
    python -m tool.ext_tick status    what the automation looks like right now

``check`` is the free gate that keeps the tick from calling ``factory board``
every two minutes. It reuses the core manifest (``snapshot.Store.manifest``) and
adds the one rule the Work vault paid for on 2026-09-10: a failed probe is never
a change. When the worktree enumeration itself fails, the tick does nothing.

``notify`` reads the postures out of the generated notes, so it costs no probe
round and cannot disagree with the board that just ran. The previous needs-you
set lives outside the vault, in ``~/Library/Logs/moose-factory.needs-you``, so it
never enters a commit and never reaches Obsidian.

Nothing here calls Claude, and nothing here writes inside a worktree.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from . import config, probe, snapshot

# --------------------------------------------------------------------------
# Where the automation keeps its wall-clock state
# --------------------------------------------------------------------------

# The launchd label. It carries no username: one label per machine is enough,
# because a user launchd domain is already per user.
LABEL = "com.moose-factory"
LOG_DIR = Path("~/Library/Logs").expanduser()
LAST_CHECK = LOG_DIR / "moose-factory.last-check"
TICK_LOG = LOG_DIR / "moose-factory.log"
LOCK_DIR = LOG_DIR / "moose-factory.lock"
TICK_COUNT = LOG_DIR / "moose-factory.ticks"
SEEN_NEEDS_YOU = LOG_DIR / "moose-factory.needs-you"
TICK_SCRIPT = Path("~/.local/bin/moose-factory-tick.sh").expanduser()
PLIST = Path("~/Library/LaunchAgents").expanduser() / (LABEL + ".plist")

# The banner channel and the Obsidian vault name, resolved once at import from
# this machine's config. macOS approves notification authorization per
# executable, so the notifier is a pinned path rather than a search; absent, the
# banner falls back to osascript and the notifier says so. The except clause
# keeps a malformed config.toml from making this extension vanish silently:
# `factory` itself reports that file and exits 3.
try:
    NOTIFIER = config.notifier() or Path(config.DEFAULT_NOTIFIER)
    VAULT_NAME = config.obsidian_vault()
except Exception:                              # pragma: no cover - a bad config
    NOTIFIER = Path(config.DEFAULT_NOTIFIER)
    VAULT_NAME = config.DEFAULT_VAULT_DIRNAME

STARTINTERVAL = 120             # must match the plist
LAST_CHECK_STALE = 10 * 60      # three missed ticks is worth a doctor line
LOCK_STALE = 15 * 60            # a lock older than this with a dead owner
NOTIFY_CAP = 3                  # banners per tick; the board is the surface

POSTURE_RE = re.compile(r"^posture:\s*([a-z-]+)\s*$", re.M)
NEXT_RE = re.compile(r"^>\s*\*\*Next:\*\*\s*(.+?)\s*$", re.M)
NEEDS_YOU = "needs-you"


# --------------------------------------------------------------------------
# Reading the board back out of the notes
# --------------------------------------------------------------------------


def postures(cfg: Any) -> Tuple[Dict[str, str], bool]:
    """``{feature: posture}`` read from the generated note frontmatter.

    The notes are an output of the run that just finished, so this is the
    board's own verdict with no second probe round. ``ok`` is False when the
    Features directory is unreadable, and the caller then does nothing.
    """
    out: Dict[str, str] = {}
    d = Path(cfg.features_dir)
    if not d.is_dir():
        return ({}, False)
    try:
        notes = sorted(d.glob("*.md"))
    except Exception:
        return ({}, False)
    ok = True
    for note in notes:
        text, tok = probe._read_text(note)
        if not tok or not text:
            ok = False
            continue
        head = text[:4000]
        m = POSTURE_RE.search(head)
        if m:
            out[note.stem] = m.group(1)
    return (out, ok)


def next_line(cfg: Any, feature: str) -> str:
    """The note's own ``> **Next:**`` sentence, for the banner body."""
    text, ok = probe._read_text(Path(cfg.features_dir) / (feature + ".md"))
    if not ok or not text:
        return "open the card"
    m = NEXT_RE.search(text)
    if not m:
        return "open the card"
    line = re.sub(r"[`*_\[\]]", "", m.group(1)).strip()
    return line[:140]


def read_seen() -> Tuple[Set[str], bool]:
    """The needs-you set as of the last notify. ``ok`` False means first run."""
    text, ok = probe._read_text(SEEN_NEEDS_YOU)
    if not ok or text is None:
        return (set(), False)
    return ({ln.strip() for ln in text.splitlines() if ln.strip()}, True)


def write_seen(ids: Set[str]) -> None:
    """Atomic, and with a unique temporary name: a hand-run notify may race the tick."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(LOG_DIR), prefix=SEEN_NEEDS_YOU.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write("".join(sorted(i + "\n" for i in ids)))
        os.replace(tmp, SEEN_NEEDS_YOU)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------
# The banner
# --------------------------------------------------------------------------


def obsidian_url(feature: str, vault_name: str = "") -> str:
    return "obsidian://open?vault=%s&file=%s" % (
        urllib.parse.quote(vault_name or VAULT_NAME, safe=""),
        urllib.parse.quote("Features/" + feature, safe=""),
    )


def _osascript_literal(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _notifier_cmd(feature: str, message: str) -> Optional[List[str]]:
    """terminal-notifier, pinned. It is the only channel that can open the note."""
    if not (NOTIFIER.is_file() and os.access(NOTIFIER, os.X_OK)):
        return None
    return [
        str(NOTIFIER),
        "-title", "moose factory",
        "-subtitle", "%s needs you" % (feature,),
        "-message", message,
        "-group", "moose-factory-%s" % (feature,),
        "-open", obsidian_url(feature),
    ]


def _osascript_cmd(feature: str, message: str) -> List[str]:
    """The fallback. No clickable URL: the board is the surface, the banner is a nudge."""
    return [
        "/usr/bin/osascript",
        "-e",
        "display notification %s with title %s subtitle %s"
        % (
            _osascript_literal(message),
            _osascript_literal("moose factory"),
            _osascript_literal("%s needs you" % (feature,)),
        ),
    ]


def _run_banner(cmd: List[str]) -> Tuple[bool, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except Exception as exc:
        return (False, "%s: %s" % (type(exc).__name__, exc))
    if r.returncode != 0:
        first = (r.stderr or r.stdout or "").strip().splitlines()[:1]
        return (False, "rc=%d %s" % (r.returncode, (first[0] if first else "")[:40]))
    return (True, "")


def notify(feature: str, message: str, dry_run: bool = False) -> str:
    """One desktop banner. Returns the channel that delivered it, for the log.

    terminal-notifier first, because only it carries ``-open``, which puts the
    card one click away. Verified on 2026-09-12: the freshly brewed copy exits 3
    with "Notifications are not allowed for this application" until macOS grants
    it authorization, so a failure is expected and is not an error. The fallback
    is osascript, which is already authorized and exits 0, and which loses only
    the click-through.
    """
    chain: List[Tuple[str, List[str]]] = []
    pinned = _notifier_cmd(feature, message)
    if pinned is not None:
        chain.append(("terminal-notifier", pinned))
    chain.append(("osascript", _osascript_cmd(feature, message)))
    if dry_run:
        return "%s (dry run)" % (chain[0][0],)
    notes: List[str] = []
    for name, cmd in chain:
        ok, why = _run_banner(cmd)
        if ok:
            return name if not notes else "%s after %s" % (name, ", ".join(notes))
        notes.append("%s %s" % (name, why))
    return "no banner: " + "; ".join(notes)


# --------------------------------------------------------------------------
# The verbs the tick calls
# --------------------------------------------------------------------------


def cmd_check(cfg: Any, argv: List[str]) -> int:
    """The free gate. Exit 0 when an input changed, 1 when nothing is new.

    Mirrors ``digest-changed.py``: the expensive job runs only on a real
    change, and a probe that failed carries the old value forward instead of
    registering as one.
    """
    store = snapshot.Store(cfg.state_dir)
    _wts, ok = probe.all_worktrees(cfg)
    if not ok:
        print("no change: the worktree probe failed (carried forward)")
        return 1
    changed, diff = store.manifest_changed(cfg)
    if "--status" in argv:
        cur = store.manifest(cfg)
        prev, pok = probe._read_json(store.dir / "manifest.json")
        at = (prev or {}).get("at") if pok and isinstance(prev, dict) else None
        age = ("%.1f min" % ((time.time() - float(at)) / 60.0)) if at else "never"
        print("manifest: %d entries, committed %s ago, %d differ" % (len(cur), age, len(diff)))
        for key in diff[:40]:
            print("   " + key)
        return 0 if changed else 1
    if changed:
        head = ", ".join(diff[:4]) + (" ..." if len(diff) > 4 else "")
        print("changed: %d - %s" % (len(diff), head))
        return 0
    print("no change")
    return 1


def cmd_notify(cfg: Any, argv: List[str]) -> int:
    """One banner per card that newly entered needs-you. Never a repeat."""
    dry = "--dry-run" in argv
    cur, ok = postures(cfg)
    if not ok and not cur:
        print("notify: no notes to read (skipped)")
        return 0
    now_set = {f for f, p in cur.items() if p == NEEDS_YOU}
    seen, had = read_seen()
    if not had:
        if not dry:
            write_seen(now_set)
        print("notify: seeded %d needs-you cards, no banner on the first run" % (len(now_set),))
        return 0
    fresh = sorted(now_set - seen)
    if not dry:
        write_seen(now_set)
    if not fresh:
        print("notify: needs-you %d, nothing new" % (len(now_set),))
        return 0
    lines = []
    for feature in fresh[:NOTIFY_CAP]:
        channel = notify(feature, next_line(cfg, feature), dry_run=dry)
        lines.append("%s via %s" % (feature, channel))
    extra = len(fresh) - NOTIFY_CAP
    print(
        "notify: %d new in needs-you - %s%s"
        % (len(fresh), "; ".join(lines), (" (+%d not shown)" % extra) if extra > 0 else "")
    )
    return 0


def cmd_postures(cfg: Any, argv: List[str]) -> int:
    cur, ok = postures(cfg)
    for feature in sorted(cur):
        print("%-24s %s" % (feature, cur[feature]))
    print("%d cards%s" % (len(cur), "" if ok else " (a note was unreadable)"))
    return 0


def cmd_status(cfg: Any, argv: List[str]) -> int:
    """What the automation looks like right now. Reads, never writes."""
    print("label        %s" % (LABEL,))
    print("loaded       %s" % ("yes" if agent_loaded() else "no",))
    print("script       %s%s" % (TICK_SCRIPT, "" if os.access(TICK_SCRIPT, os.X_OK) else "  (not executable)"))
    print("plist        %s%s" % (PLIST, "" if PLIST.is_file() else "  (absent)"))
    print("notifier     %s" % (NOTIFIER if NOTIFIER.is_file() else "osascript fallback",))
    age = last_check_age()
    print("last check   %s" % ("never" if age is None else "%.0f s ago" % (age,),))
    text, ok = probe._read_text(LAST_CHECK)
    if ok and text:
        print("             %s" % (text.strip().splitlines()[-1:] or [""])[0])
    print("ticks        %s" % (tick_count(),))
    lock_ok, lock_why = lock_state()
    print("lock         %s" % ("clear" if lock_ok and not lock_why else lock_why or "held",))
    return 0


# --------------------------------------------------------------------------
# Shared inspection, used by both `status` and `doctor`
# --------------------------------------------------------------------------


def agent_loaded() -> bool:
    try:
        r = subprocess.run(
            ["/bin/launchctl", "list", LABEL], capture_output=True, text=True, timeout=15
        )
        return r.returncode == 0
    except Exception:
        return False


def last_check_age() -> Optional[float]:
    mt, ok = probe._mtime(LAST_CHECK)
    if not ok or not mt:
        return None
    return max(0.0, time.time() - float(mt))


def tick_count() -> int:
    text, ok = probe._read_text(TICK_COUNT)
    try:
        return int((text or "0").strip()) if ok else 0
    except Exception:
        return 0


def lock_state() -> Tuple[bool, str]:
    """(ok, why). A held lock with a live owner is fine; a stale one is not."""
    if not LOCK_DIR.exists():
        return (True, "")
    pid_text, _ok = probe._read_text(LOCK_DIR / "pid")
    pid = (pid_text or "").strip()
    mt, mok = probe._mtime(LOCK_DIR)
    age = (time.time() - float(mt)) if (mok and mt) else 0.0
    alive = False
    if pid.isdigit():
        try:
            os.kill(int(pid), 0)
            alive = True
        except Exception:
            alive = False
    if alive and age < LOCK_STALE:
        return (True, "held by pid %s for %.0f s" % (pid, age))
    return (
        False,
        "stale: pid %s is %s and the lock is %.0f s old; rm -rf %s"
        % (pid or "unknown", "gone" if not alive else "stuck", age, LOCK_DIR),
    )


def installed_matches_repo(cfg: Any) -> bool:
    repo_copy = Path(cfg.repo_root) / "factory" / "moose-factory-tick.sh"
    if not repo_copy.is_file() or not TICK_SCRIPT.is_file():
        return False
    a, aok = probe._read_text(repo_copy)
    b, bok = probe._read_text(TICK_SCRIPT)
    return bool(aok and bok and a == b)


# --------------------------------------------------------------------------
# The extension contract
# --------------------------------------------------------------------------

HELP = {"tick-status": "what the 120 s launchd tick looks like right now"}


def _verb_status(argv: List[str], ctx: Any) -> int:
    return cmd_status(ctx.config, list(argv))


VERBS = {"tick-status": _verb_status}

# Reads ~/Library/Logs and launchctl only: no probe round, no 6.5 s.
NO_CTX_VERBS = ("tick-status",)


def doctor_checks(ctx: Any) -> List[Tuple[str, bool, str]]:
    """Four facts about the automation, plus the notifier channel."""
    cfg = ctx.config
    install = "zsh %s/factory/install.sh" % (cfg.repo_root,)
    rows: List[Tuple[str, bool, str]] = []

    rows.append(
        (
            "launchd agent %s is loaded" % (LABEL,),
            agent_loaded(),
            "%s (then: launchctl kickstart -k gui/$(id -u)/%s)" % (install, LABEL),
        )
    )
    rows.append(
        (
            "tick script is executable",
            TICK_SCRIPT.is_file() and os.access(TICK_SCRIPT, os.X_OK),
            "missing or not +x at %s: %s" % (TICK_SCRIPT, install),
        )
    )
    rows.append(
        (
            "installed tick matches the repo copy",
            installed_matches_repo(cfg),
            "re-run %s after editing factory/moose-factory-tick.sh" % (install,),
        )
    )
    lock_ok, lock_why = lock_state()
    rows.append(("tick lock is not stale", lock_ok, lock_why))
    age = last_check_age()
    rows.append(
        (
            "last check is recent",
            age is not None and age < LAST_CHECK_STALE,
            (
                "no %s yet: %s" % (LAST_CHECK.name, install)
                if age is None
                else "%.0f s old, over the %d s budget for a %d s interval"
                % (age, LAST_CHECK_STALE, STARTINTERVAL)
            ),
        )
    )
    rows.append(
        (
            "notifier is terminal-notifier",
            NOTIFIER.is_file() and os.access(NOTIFIER, os.X_OK),
            "brew install terminal-notifier; until then banners use osascript",
        )
    )
    return rows


# --------------------------------------------------------------------------
# python -m tool.ext_tick <verb>
# --------------------------------------------------------------------------

COMMANDS = {
    "check": cmd_check,
    "notify": cmd_notify,
    "postures": cmd_postures,
    "status": cmd_status,
}

USAGE = "usage: python -m tool.ext_tick {check|notify|postures|status} [--status|--dry-run]"


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0 if argv else 3
    verb, rest = argv[0], argv[1:]
    fn = COMMANDS.get(verb)
    if fn is None:
        print("ext_tick: unknown verb %r\n%s" % (verb, USAGE), file=sys.stderr)
        return 3
    try:
        config.hostname_guard()
        cfg = config.load(offline=("--offline" in rest))
        config.require_vault(cfg)
        return int(fn(cfg, rest) or 0)
    except config.WrongHost as exc:
        print("ext_tick: %s" % (exc,), file=sys.stderr)
        return 3
    except config.MissingPath as exc:
        print("ext_tick: %s" % (exc,), file=sys.stderr)
        return 3
    except Exception as exc:                      # never take the tick down
        print("ext_tick: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
