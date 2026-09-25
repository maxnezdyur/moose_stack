"""Parse, validate and edit ``campaign.md``, exactly as ``formats/campaign.md`` says.

This module owns the frontmatter keys, the four ``##`` headings and their
order, the constraints and measures tables, the proposal entries and their
sub-bullets, run-id minting, and the two edits the tool may make to the file:
ticking one entry and consuming one entry. Every other byte of the file is
left as it was.
"""

from __future__ import annotations

import datetime as _dt
import re
import shlex
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from . import config
from .model import AUTONOMY, STATUSES, Campaign, Measure, Proposal, normalize

REQUIRED = ("id", "project", "title", "question", "stop", "budget", "cluster", "app", "autonomy")
BUDGET_KEYS = ("core_hours", "wall_days", "max_runs")
HEADINGS = ("## Hypothesis", "## Constraints", "## Measures", "## Proposed")

ENTRY = re.compile(r"^- \[([ xX])\] (.*)$")
SUB = re.compile(r"^\s+- ([A-Za-z_]+):\s?(.*)$")
ESTIMATE = re.compile(r"^(\d+(?:\.\d+)?)\s*core-h$")
CITE = re.compile(r"\b(F\d+|D\d{3})\b|campaign\.md")
WALLTIME = re.compile(r"^(\d+-)?\d{1,3}:\d{2}:\d{2}$")
ENVKEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MEASURE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
HOW_CMD = re.compile(r"^`([^`]+)`(.*)$")
HOW_CSV = re.compile(r"^csv:([^:\s`]+):([^:\s`]+):(last|max|min)\b(.*)$")

SUB_KEYS = ("cwd", "cmd", "in", "cluster", "env", "ntasks", "walltime", "partition")
MULTI_KEYS = ("in", "env")


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def split_frontmatter(text: str) -> Tuple[Optional[str], str, int]:
    """(frontmatter yaml, body, 0-based line where the body starts)."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, text, 0
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:]), i + 1
    return None, text, 0


def split_row(line: str) -> List[str]:
    """Cells of one markdown table row. A ``|`` inside a backtick span is text."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    cells, cur, tick = [], [], False
    for ch in s:
        if ch == "`":
            tick = not tick
        if ch == "|" and not tick:
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    cells.append("".join(cur).strip())
    return cells


def _table(lines: List[str]) -> Tuple[List[str], List[List[str]]]:
    rows = [split_row(l) for l in lines if l.strip().startswith("|")]
    if not rows:
        return [], []
    header = [c.lower() for c in rows[0]]
    body = [r for r in rows[1:] if not all(re.match(r"^:?-{2,}:?$", c) for c in r if c)]
    return header, body


def parse_measure(cells: List[str]) -> Measure:
    name, unit, how, added = (cells + ["", "", "", ""])[:4]
    m = Measure(name=name, unit=unit, how=how, added=added)
    mc = HOW_CMD.match(how)
    mv = HOW_CSV.match(how)
    if mc:
        m.kind, m.command = "cmd", mc.group(1).strip()
    elif mv:
        m.kind = "csv"
        m.csv_file, m.csv_column, m.csv_reduce = mv.group(1), mv.group(2), mv.group(3)
    return m


def parse_entry(first: str, subs: List[str], lineno: int, errors: List[str]) -> Optional[Proposal]:
    m = ENTRY.match(first)
    if not m:
        return None
    where = "campaign.md:%d" % (lineno + 1)
    parts = m.group(2).split(" | ")
    if len(parts) != 5:
        errors.append("%s: a proposal line has six fields separated by ' | ' "
                      "(id tag | group | estimate | tests | because)" % where)
        return None
    idtag = parts[0].split(None, 1)
    rid = idtag[0] if idtag else ""
    tag = idtag[1].strip() if len(idtag) > 1 else ""
    if not config.RUN_ID.match(rid):
        errors.append("%s: run id %r is not D plus three digits" % (where, rid))
    if not config.TAG.match(tag):
        errors.append("%s: %s tag %r is not [a-z0-9._-]+" % (where, rid, tag))
    group = parts[1].strip()
    est = ESTIMATE.match(parts[2].strip())
    if not est:
        errors.append("%s: %s estimate %r is not '<n> core-h'" % (where, rid, parts[2].strip()))
    tests = parts[3].strip()
    if not tests.startswith("tests:") or not tests[6:].strip():
        errors.append("%s: %s fifth field must be 'tests: <sentence>'" % (where, rid))
    because = parts[4].strip()
    if not because.startswith("because:"):
        errors.append("%s: %s sixth field must be 'because: <F<n> or D<nnn>>'" % (where, rid))
    cites = [c.group(0) for c in CITE.finditer(because)]
    if because.startswith("because:") and not cites:
        errors.append("%s: %s 'because' cites no F<n>, D<nnn> or campaign.md" % (where, rid))

    p = Proposal(
        id=rid, tag=tag, group=None if group in ("-", "") else group,
        estimate=float(est.group(1)) if est else None,
        tests=tests[6:].strip() if tests.startswith("tests:") else tests,
        because=cites, ticked=m.group(1) in "xX", line=lineno,
    )
    seen = set()
    for off, raw in enumerate(subs):
        sm = SUB.match(raw)
        swhere = "campaign.md:%d" % (lineno + 2 + off)
        if not sm:
            errors.append("%s: %s sub-bullet is not '  - key: value'" % (swhere, rid))
            continue
        key, val = sm.group(1), sm.group(2).strip()
        if key not in SUB_KEYS:
            errors.append("%s: %s unknown sub-bullet %r; known: %s" % (swhere, rid, key, ", ".join(SUB_KEYS)))
            continue
        if key not in MULTI_KEYS and key in seen:
            errors.append("%s: %s sub-bullet %r given twice" % (swhere, rid, key))
            continue
        seen.add(key)
        if key == "in":
            p.ins.append(val)
        elif key == "env":
            k, eq, v = val.partition("=")
            if not eq or not ENVKEY.match(k.strip()):
                errors.append("%s: %s env %r is not KEY=value" % (swhere, rid, val))
            else:
                p.env[k.strip()] = v.strip()
        elif key == "ntasks":
            try:
                p.ntasks = int(val)
                if p.ntasks < 1:
                    raise ValueError
            except ValueError:
                errors.append("%s: %s ntasks %r is not a positive whole number" % (swhere, rid, val))
        elif key == "walltime":
            if not WALLTIME.match(val):
                errors.append("%s: %s walltime %r is not HH:MM:SS" % (swhere, rid, val))
            p.walltime = val
        else:
            setattr(p, key, val)
    if not p.cwd:
        errors.append("%s: %s has no '  - cwd:' sub-bullet" % (where, rid))
    elif p.cwd.startswith("/") or ".." in Path(p.cwd).parts:
        errors.append("%s: %s cwd %r must be relative to the project root" % (where, rid, p.cwd))
    if not p.cmd:
        errors.append("%s: %s has no '  - cmd:' sub-bullet" % (where, rid))
    else:
        if "$" in p.cmd:
            errors.append("%s: %s cmd uses a shell variable; write the value" % (where, rid))
        try:
            shlex.split(p.cmd)
        except ValueError as exc:
            errors.append("%s: %s cmd does not split: %s" % (where, rid, exc))
    return p


def load(camp_dir: Path, settings: Optional[config.Settings] = None) -> Campaign:
    """Parse ``campaign.md``. Problems land in ``errors``; nothing is raised for them."""
    path = camp_dir / "campaign.md"
    if not path.is_file():
        raise config.Missing("%s is absent" % path)
    text = path.read_text()
    root = camp_dir.resolve().parents[1]
    camp = Campaign(dir=camp_dir, root=root, meta={}, text=text)
    errors, warnings = camp.errors, camp.warnings

    fm, _body, body_start = split_frontmatter(text)
    if fm is None:
        errors.append("campaign.md: no '---' frontmatter block")
    else:
        try:
            meta = yaml.safe_load(fm) or {}
            if not isinstance(meta, dict):
                raise ValueError("not a mapping")
            camp.meta = normalize(meta)
        except (yaml.YAMLError, ValueError) as exc:
            errors.append("campaign.md: frontmatter does not parse: %s" % exc)
    _check_meta(camp, settings)

    lines = text.split("\n")
    sections: Dict[str, Tuple[int, int]] = {}
    heads: List[Tuple[str, int]] = [(l.rstrip(), i) for i, l in enumerate(lines)
                                    if i >= body_start and l.startswith("## ")]
    camp.headings = [h for h, _ in heads]
    for n, (h, i) in enumerate(heads):
        end = heads[n + 1][1] if n + 1 < len(heads) else len(lines)
        if h in sections:
            errors.append("campaign.md:%d: heading %r appears twice" % (i + 1, h))
        sections[h] = (i + 1, end)
    present = [h for h in camp.headings if h in HEADINGS]
    for h in HEADINGS:
        if h not in camp.headings:
            errors.append("campaign.md: missing heading %r" % h)
    if present != [h for h in HEADINGS if h in present]:
        errors.append("campaign.md: the headings must come in this order: %s" % ", ".join(HEADINGS))
    for h in camp.headings:
        if h not in HEADINGS:
            warnings.append("campaign.md: extra heading %r is not part of the format" % h)

    def section(h: str) -> List[str]:
        a, b = sections.get(h, (0, 0))
        return lines[a:b]

    camp.hypothesis = "\n".join(l for l in section("## Hypothesis")).strip()

    header, rows = _table(section("## Constraints"))
    if "## Constraints" in sections:
        if header[:3] != ["knob", "value", "why"]:
            errors.append("campaign.md: the ## Constraints table header must be | knob | value | why |")
        for r in rows:
            knob = r[0].strip().strip("`").strip() if r else ""
            camp.constraints.append({"knob": knob, "value": r[1] if len(r) > 1 else "",
                                     "why": r[2] if len(r) > 2 else ""})

    header, rows = _table(section("## Measures"))
    if "## Measures" in sections:
        if header[:4] != ["name", "unit", "how", "added"]:
            errors.append("campaign.md: the ## Measures table header must be | name | unit | how | added |")
        for r in rows:
            m = parse_measure(r)
            if not MEASURE_NAME.match(m.name):
                errors.append("campaign.md: measure name %r is not an identifier" % m.name)
            if not m.kind:
                errors.append("campaign.md: measure %r how %r is neither a `command` nor "
                              "csv:<file>:<column>:<last|max|min>" % (m.name, m.how))
            if m.kind == "cmd":
                try:
                    shlex.split(m.command)
                except ValueError as exc:
                    errors.append("campaign.md: measure %r command does not split: %s" % (m.name, exc))
            if camp.measure(m.name):
                errors.append("campaign.md: measure %r appears twice" % m.name)
            camp.measures.append(m)

    if "## Proposed" in sections:
        a, b = sections["## Proposed"]
        i = a
        while i < b:
            line = lines[i]
            if line.startswith("- "):
                j = i + 1
                while j < b and lines[j].strip() and lines[j][:1] in (" ", "\t"):
                    j += 1
                if ENTRY.match(line):
                    p = parse_entry(line, lines[i + 1:j], i, errors)
                    if p is not None:
                        p.end = j
                        camp.proposals.append(p)
                else:
                    errors.append("campaign.md:%d: a queue line must start '- [ ] ' or '- [x] '" % (i + 1))
                i = j
            else:
                i += 1

    _check_proposals(camp, settings)
    return camp


def _check_meta(camp: Campaign, settings: Optional[config.Settings]) -> None:
    meta, errors = camp.meta, camp.errors
    if not meta:
        return
    for k in REQUIRED:
        if meta.get(k) in (None, ""):
            errors.append("campaign.md: frontmatter key %r is required" % k)
    if meta.get("id") and meta.get("id") != camp.dir.name:
        errors.append("campaign.md: id %r is not the directory name %r" % (meta.get("id"), camp.dir.name))
    budget = meta.get("budget")
    if budget is not None:
        if not isinstance(budget, dict):
            errors.append("campaign.md: budget must be a mapping of %s" % ", ".join(BUDGET_KEYS))
        else:
            for k in BUDGET_KEYS:
                v = budget.get(k)
                if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
                    errors.append("campaign.md: budget.%s must be a number >= 0" % k)
    cluster = meta.get("cluster")
    known = ["local"] + (sorted(settings.clusters) if settings else [])
    if cluster and settings and cluster not in known:
        errors.append("campaign.md: cluster %r is not one of %s" % (cluster, ", ".join(known)))
    if meta.get("app") and meta.get("app") not in config.APPS:
        errors.append("campaign.md: app %r is not one of %s" % (meta.get("app"), ", ".join(config.APPS)))
    if meta.get("autonomy") and meta.get("autonomy") not in AUTONOMY:
        errors.append("campaign.md: autonomy %r is not one of %s" % (meta.get("autonomy"), ", ".join(AUTONOMY)))
    status = meta.get("status")
    if status is not None and status not in STATUSES:
        errors.append("campaign.md: status %r is not one of %s" % (status, ", ".join(STATUSES)))
    for k in ("created", "updated"):
        v = meta.get(k)
        if v is not None:
            try:
                _dt.date.fromisoformat(str(v))
            except ValueError:
                errors.append("campaign.md: %s %r is not YYYY-MM-DD" % (k, v))
    closed = meta.get("closed")
    if status == "done" and not (isinstance(closed, dict) and closed.get("finding")):
        errors.append("campaign.md: status done needs closed.finding")
    if status == "abandoned" and not (isinstance(closed, dict) and closed.get("date")):
        errors.append("campaign.md: status abandoned needs closed.date")


def _check_proposals(camp: Campaign, settings: Optional[config.Settings]) -> None:
    errors = camp.errors
    run_ids, run_tags = existing_runs(camp)
    seen_ids: Dict[str, int] = {}
    seen_tags: Dict[str, str] = {}
    for p in camp.proposals:
        if p.id in seen_ids or p.id in run_ids:
            errors.append("campaign.md:%d: run id %s is already used" % (p.line + 1, p.id))
        seen_ids[p.id] = p.line
        if p.tag and (p.tag in seen_tags or p.tag in run_tags.values()):
            errors.append("campaign.md:%d: tag %r is already used" % (p.line + 1, p.tag))
        seen_tags[p.tag] = p.id
        if p.cluster and settings and p.cluster != "local" and p.cluster not in settings.clusters:
            errors.append("campaign.md:%d: %s cluster %r is not configured" % (p.line + 1, p.id, p.cluster))
        hit = constraint_hits(camp, p.cmd or "")
        if hit:
            camp.warnings.append("campaign.md:%d: %s cmd sets frozen knob(s) %s; run will refuse it"
                                 % (p.line + 1, p.id, ", ".join(hit)))


# --------------------------------------------------------------------------
# Queries
# --------------------------------------------------------------------------


def existing_runs(camp: Campaign) -> Tuple[List[str], Dict[str, str]]:
    """Run ids and their tags from the ``runs/`` directory names."""
    ids: List[str] = []
    tags: Dict[str, str] = {}
    if camp.runs_dir.is_dir():
        for d in sorted(camp.runs_dir.iterdir()):
            m = re.match(r"^(D\d{3})_(.+)$", d.name)
            if d.is_dir() and m:
                ids.append(m.group(1))
                tags[m.group(1)] = m.group(2)
    return ids, tags


def run_dir_for(camp: Campaign, run_id: str) -> Optional[Path]:
    if camp.runs_dir.is_dir():
        for d in sorted(camp.runs_dir.glob(run_id + "_*")):
            if d.is_dir():
                return d
    return None


def next_id(camp: Campaign, extra: Optional[List[str]] = None) -> str:
    """One more than the highest id in ``## Proposed``, ``runs/`` and the ledger."""
    from . import ledger as ledger_mod

    ids = [p.id for p in camp.proposals] + existing_runs(camp)[0] + list(extra or [])
    try:
        ids += [e.id for e in ledger_mod.parse(camp.dir / "LEDGER.md")[1]]
    except config.Missing:
        pass
    nums = [int(i[1:]) for i in ids if config.RUN_ID.match(i)]
    return "D%03d" % ((max(nums) if nums else 0) + 1)


def constraint_hits(camp: Campaign, cmd: str) -> List[str]:
    """The frozen knobs a command sets through ``<knob>=`` tokens."""
    knobs = set(camp.knobs)
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        tokens = cmd.split()
    hits = []
    for t in tokens:
        if "=" not in t or t.startswith("-"):
            continue
        key = t.split("=", 1)[0]
        leaf = key.rsplit("/", 1)[-1]
        if key in knobs or leaf in knobs:
            hits.append(key)
    return hits


# --------------------------------------------------------------------------
# The two edits: tick one entry, consume one entry
# --------------------------------------------------------------------------


def _locate(camp_dir: Path, run_id: str, settings: Optional[config.Settings]) -> Tuple[Campaign, Proposal]:
    camp = load(camp_dir, settings)
    p = camp.proposal(run_id)
    if p is None:
        raise config.Refused("%s is not an entry under ## Proposed in %s/campaign.md" % (run_id, camp_dir))
    return camp, p


def tick_text(camp: Campaign, p: Proposal) -> str:
    lines = camp.text.split("\n")
    lines[p.line] = lines[p.line].replace("- [ ] ", "- [x] ", 1)
    return "\n".join(lines)


def consume_text(camp: Campaign, p: Proposal) -> str:
    lines = camp.text.split("\n")
    del lines[p.line:p.end]
    return "\n".join(lines)


def consume(camp_dir: Path, run_id: str, settings: Optional[config.Settings] = None) -> None:
    """Delete one entry and its sub-bullets from ``## Proposed``. Re-reads the file first."""
    camp, p = _locate(camp_dir, run_id, settings)
    config.write_text_atomic(camp_dir / "campaign.md", consume_text(camp, p))


def set_frontmatter(camp: Campaign, updates: Dict[str, object]) -> str:
    """The file text with frontmatter keys replaced or appended; the body untouched."""
    lines = camp.text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise config.Refused("campaign.md has no frontmatter")
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    fm = lines[1:end]
    for key, value in updates.items():
        dumped = yaml.safe_dump({key: value}, default_flow_style=False, sort_keys=False).rstrip("\n").split("\n")
        start = next((i for i, l in enumerate(fm) if re.match(r"^%s:" % re.escape(key), l)), None)
        if start is None:
            fm.extend(dumped)
            continue
        stop = start + 1
        while stop < len(fm) and (fm[stop].startswith((" ", "\t")) or not fm[stop].strip()):
            stop += 1
        fm[start:stop] = dumped
    return "\n".join([lines[0]] + fm + lines[end:])


# --------------------------------------------------------------------------
# Validation of the whole campaign directory
# --------------------------------------------------------------------------


def validate(camp_dir: Path, settings: Optional[config.Settings] = None) -> Tuple[List[str], List[str]]:
    """(errors, warnings) over campaign.md, every manifest, LEDGER.md and FINDINGS.md."""
    from . import findings as findings_mod
    from . import ledger as ledger_mod
    from . import manifest as manifest_mod

    camp = load(camp_dir, settings)
    errors, warnings = list(camp.errors), list(camp.warnings)
    names = {m.name for m in camp.measures}

    try:
        _hdr, entries = ledger_mod.parse(camp_dir / "LEDGER.md")
    except config.Missing as exc:
        errors.append(str(exc))
        entries = []
    except config.Refused as exc:
        errors.append(str(exc))
        entries = []
    by_id = {e.id: e for e in entries}
    seen = set()
    for e in entries:
        if e.id in seen:
            errors.append("LEDGER.md: run %s has two start lines" % e.id)
        seen.add(e.id)

    run_ids, _tags = existing_runs(camp)
    for rid in run_ids:
        d = run_dir_for(camp, rid)
        try:
            run = manifest_mod.load(d)
        except (config.Missing, config.Refused) as exc:
            errors.append(str(exc))
            continue
        where = "runs/%s/manifest.yaml" % d.name
        if run.run != rid:
            errors.append("%s: run %r is not the directory's id %s" % (where, run.run, rid))
        if run.campaign != camp.id:
            errors.append("%s: campaign %r is not %s" % (where, run.campaign, camp.id))
        if manifest_mod.identity_ok(run) is False:
            errors.append("%s: an immutable block (%s) changed after launch"
                          % (where, ", ".join(manifest_mod.IMMUTABLE)))
        for k in run.qoi or {}:
            if k not in names:
                errors.append("%s: qoi key %r is not a ## Measures name" % (where, k))
        if run.verdict is not None and run.verdict not in ("supported", "refuted", "inconclusive", "failed"):
            errors.append("%s: verdict %r is not a verdict word" % (where, run.verdict))
        if rid not in by_id and run.started:
            warnings.append("LEDGER.md: run %s has no start line" % rid)
    for e in entries:
        if e.id not in run_ids:
            warnings.append("LEDGER.md: %s has a start line but no runs/%s_* directory" % (e.id, e.id))

    try:
        _fh, fs = findings_mod.parse(camp_dir / "FINDINGS.md")
    except config.Missing as exc:
        errors.append(str(exc))
        fs = []
    except config.Refused as exc:
        errors.append(str(exc))
        fs = []
    for i, f in enumerate(fs, start=1):
        if f.n != i:
            errors.append("FINDINGS.md: F%d is out of order; expected F%d" % (f.n, i))
        if not f.runs:
            errors.append("FINDINGS.md: F%d cites no run" % f.n)
        for r in f.runs:
            if r not in by_id or not by_id[r].done:
                errors.append("FINDINGS.md: F%d cites %s, which has no done line in LEDGER.md" % (f.n, r))
        if not f.measures:
            errors.append("FINDINGS.md: F%d cites no measure" % f.n)
        for m in f.measures:
            if m not in names:
                errors.append("FINDINGS.md: F%d cites measure %r, not in ## Measures" % (f.n, m))
        for k in ("date", "runs", "measures", "refutes", "closes"):
            if k not in f.fields:
                errors.append("FINDINGS.md: F%d has no '- %s:' line" % (f.n, k))

    closed = camp.meta.get("closed") if isinstance(camp.meta.get("closed"), dict) else {}
    if camp.meta.get("status") == "done" and closed.get("finding"):
        f = next((x for x in fs if x.id == closed.get("finding")), None)
        if f is None or not f.closes:
            errors.append("campaign.md: closed.finding %s is not a closes: yes finding in FINDINGS.md"
                          % closed.get("finding"))
    return errors, warnings
