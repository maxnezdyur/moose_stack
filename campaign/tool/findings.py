"""Parse ``FINDINGS.md``, per ``formats/findings.md``.

This module owns the ``## F<n>. <claim>`` section, its five bullet fields
(``date``, ``runs``, ``measures``, ``refutes``, ``closes``) and the body. The
tool never writes this file: the loop and the human append to it. The one
question the tool asks of it is which finding, if any, says ``closes: yes``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from . import config
from .model import Finding

HEAD = re.compile(r"^## F(\d+)\.\s+(.*)$")
FIELD = re.compile(r"^- ([a-z_]+):\s*(.*)$")
RUN = re.compile(r"\bD\d{3}\b")


def _list(value: str) -> List[str]:
    return [x.strip() for x in re.split(r"[,\s]+", value) if x.strip() and x.strip() != "-"]


def parse(path: Path) -> Tuple[List[str], List[Finding]]:
    """(header lines, findings in file order)."""
    if not path.is_file():
        raise config.Missing("%s is absent" % path)
    lines = path.read_text().split("\n")
    header: List[str] = []
    out: List[Finding] = []
    cur: Optional[Finding] = None
    in_fields = False
    body: List[str] = []
    for i, line in enumerate(lines):
        m = HEAD.match(line)
        if m:
            if cur is not None:
                cur.body = "\n".join(body).strip()
            cur = Finding(n=int(m.group(1)), claim=m.group(2).strip())
            out.append(cur)
            in_fields, body = True, []
            continue
        if cur is None:
            if line.startswith("## "):
                raise config.Refused("%s:%d: a finding heading is '## F<n>. <claim>'" % (path.name, i + 1))
            header.append(line)
            continue
        f = FIELD.match(line) if in_fields else None
        if f:
            key, val = f.group(1), f.group(2).strip()
            cur.fields[key] = val
            if key == "date":
                cur.date = val
            elif key == "runs":
                cur.runs = RUN.findall(val)
            elif key == "measures":
                cur.measures = _list(val)
            elif key == "refutes":
                cur.refutes = val or "-"
            elif key == "closes":
                cur.closes = val.lower() == "yes"
            continue
        if in_fields and not line.strip() and cur.fields:
            in_fields = False
            continue
        in_fields = False
        body.append(line)
    if cur is not None:
        cur.body = "\n".join(body).strip()
    return header, out


def load(path: Path) -> List[Finding]:
    try:
        return parse(path)[1]
    except config.Missing:
        return []


def get(path: Path, fid: str) -> Optional[Finding]:
    return next((f for f in load(path) if f.id == fid), None)


def closing(path: Path) -> Optional[Finding]:
    """The first finding that says ``closes: yes``."""
    return next((f for f in load(path) if f.closes), None)
