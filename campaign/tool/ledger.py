"""Parse ``LEDGER.md`` and append to it, per ``formats/ledger.md``.

This module owns the start line, the three indented lines (``done``,
``verdict``, ``note``) and the discipline: no existing line is ever edited. A
start line goes at the end of the file. An indented line goes directly after
the last line of its own entry, so a run that finishes late still reads under
its own start line.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import config
from .model import LedgerEntry

START = re.compile(r"^- (D\d{3}) \| (.*)$")
INDENTED = re.compile(r"^  - (done|verdict|note)\b:? ?(.*)$")
DONE = re.compile(r"^(\S+) exit=(\S+) core-h=(\S+)$")


def parse(path: Path) -> Tuple[List[str], List[LedgerEntry]]:
    """(header lines up to and including ``---``, entries)."""
    if not path.is_file():
        raise config.Missing("%s is absent" % path)
    lines = path.read_text().split("\n")
    try:
        sep = next(i for i, l in enumerate(lines) if l.strip() == "---")
    except StopIteration:
        raise config.Refused("%s: no '---' line after the header" % path.name)
    entries: List[LedgerEntry] = []
    cur: Optional[LedgerEntry] = None
    for i in range(sep + 1, len(lines)):
        line = lines[i]
        if not line.strip():
            continue
        m = START.match(line)
        if m:
            f = [x.strip() for x in m.group(2).split(" | ")]
            if len(f) < 5:
                raise config.Refused("%s:%d: a start line has six fields" % (path.name, i + 1))
            cur = LedgerEntry(id=m.group(1), tag=f[0], group=f[1], stamp=f[2], where=f[3],
                              hypothesis=" | ".join(f[4:]), line=i, end=i + 1)
            entries.append(cur)
            continue
        m = INDENTED.match(line)
        if m and cur is not None:
            kind, rest = m.group(1), m.group(2).strip()
            if kind == "done":
                d = DONE.match(rest)
                cur.done = ({"stamp": d.group(1), "exit": d.group(2), "core_h": d.group(3)}
                            if d else {"raw": rest})
            elif kind == "verdict":
                parts = [x.strip() for x in rest.split(" | ")]
                cur.verdict = {"word": parts[0], "qoi": parts[1] if len(parts) > 1 else "-",
                               "finding": parts[2] if len(parts) > 2 else "-"}
            else:
                cur.notes.append(rest)
            cur.end = i + 1
            continue
        raise config.Refused("%s:%d: not a start line or an indented done/verdict/note line"
                             % (path.name, i + 1))
    return lines[: sep + 1], entries


def entry(path: Path, run_id: str) -> Optional[LedgerEntry]:
    return next((e for e in parse(path)[1] if e.id == run_id), None)


def fmt_core_h(x: float) -> str:
    """One decimal, the way the ledger has always carried it; small runs keep two digits."""
    if x >= 0.05 or x == 0:
        return "%.1f" % x
    return "%.2g" % x


def fmt_value(v: object) -> str:
    if isinstance(v, float):
        return "%g" % v
    return str(v)


def start_line(run_id: str, tag: str, group: Optional[str], when: str, where: str, hyp: str) -> str:
    return "- %s | %s | %s | %s | %s | %s" % (run_id, tag, group or "-", when, where, hyp)


def done_line(when: str, exit_code: object, core_h: float) -> str:
    return "  - done %s exit=%s core-h=%s" % (when, exit_code, fmt_core_h(core_h))


def verdict_line(word: str, qoi: Dict[str, object], finding: Optional[str]) -> str:
    pairs = ", ".join("%s=%s" % (k, fmt_value(v)) for k, v in (qoi or {}).items()) or "-"
    return "  - verdict %s | %s | %s" % (word, pairs, finding or "-")


def note_line(text: str) -> str:
    one = " ".join(text.split())
    if not one:
        raise config.Refused("a note needs text")
    return "  - note: %s" % one


def append_start(path: Path, line: str) -> None:
    text = path.read_text() if path.is_file() else ""
    if not path.is_file():
        raise config.Missing("%s is absent" % path)
    m = START.match(line)
    if m and entry(path, m.group(1)) is not None:
        raise config.Refused("LEDGER.md already has a start line for %s" % m.group(1))
    if text and not text.endswith("\n"):
        text += "\n"
    config.write_text_atomic(path, text + line + "\n")


def append_under(path: Path, run_id: str, line: str) -> None:
    """Insert ``line`` after the last line of ``run_id``'s entry."""
    _hdr, entries = parse(path)
    e = next((x for x in entries if x.id == run_id), None)
    if e is None:
        raise config.Refused("LEDGER.md has no start line for %s" % run_id)
    kind = INDENTED.match(line).group(1)
    if kind == "done" and e.done is not None:
        raise config.Refused("LEDGER.md already has a done line for %s; append a note instead" % run_id)
    if kind == "verdict" and e.verdict is not None:
        raise config.Refused("LEDGER.md already has a verdict line for %s; append a note instead" % run_id)
    lines = path.read_text().split("\n")
    lines.insert(e.end, line)
    config.write_text_atomic(path, "\n".join(lines))


def core_hours(path: Path) -> float:
    """The sum of every ``core-h=`` in the done lines: the ledger's own view of spend."""
    total = 0.0
    for e in parse(path)[1]:
        if e.done and "core_h" in e.done:
            try:
                total += float(e.done["core_h"])
            except ValueError:
                pass
    return total
