"""The cross-session handoff document, rescued and projected onto the card.

``<worktree>/specs/handoff.md`` is what one session leaves for the next: the
state, the ordered next steps, the dead ends already paid for, the decisions,
the gotchas, the map, and one line per session. The skills write it
(``/handoff``, ``/moose-blueprint``, ``/moose-build``, ``/moose-ship``); this
module never writes it. It does three things:

1. ``collect`` rescues the worktree's copy into
   ``<vault>/Artifacts/<feature>/handoff.md``, because ``specs/handoff.md`` dies
   with the worktree and the handoff is the one artifact whose whole value is
   surviving the session that wrote it. The rescue is idempotent: identical
   bytes are never copied twice, and ``shutil.copy2`` carries the mtime over, so
   the second board run sees ``same``.

2. ``note_sections`` renders ``## Handoff`` on the feature note: the State
   paragraph, the Next list, and the last three Do-not-repeat lines, read
   from the worktree copy when it is there and from the rescued copy once the
   worktree is gone.

3. ``card_flags`` raises ``handoff-stale`` when the worktree moved on without
   the handoff: ``specs/blueprint.md`` or the newest build record is newer than
   ``handoff.md`` by more than two days. Three ``stat`` calls. No git runs here,
   not even a read-only one.

The first ``## Next`` line is published as ``handoff_next`` for every other
reader (the ``Board.html`` builder included) in three places that all carry the
same string: ``ctx.meta["handoff"][<feature>]["handoff_next"]``,
``ctx.obs[<feature>]["handoff"]["handoff_next"]`` and ``card.extra``. Use
:func:`handoff_next` rather than reaching into any of them.

Every projected string passes through :func:`_clip`, which escapes ``<!--``:
handoff prose that names one of ``probe.MARKERS`` would otherwise plant a second
fence inside the generated note body and the note would grow on every run. The
Next steps print as plain bullets for the same class of reason: a checkbox in a
regenerated body is a tick nothing reads back.

Two conventions inherited from core: nothing here reads the clock, and no
generated line prints an age in days. The staleness flag compares two file
mtimes against each other, never against now, so a rebuild after a deletion
renders byte for byte.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config, probe

# Order among the extension sections on a note: the handoff is what the reader
# wants first, so it sits above "Build and review" (50) and the Session block.
ORDER_HANDOFF = 40

HANDOFF_REL = "specs/handoff.md"
HANDOFF_NAME = "handoff.md"

#: The seven headings, in the order the template writes them. Read by name:
#: a writer may not reorder them, and a missing one is a doctor row.
SECTIONS: Tuple[str, ...] = (
    "State",
    "Next",
    "Do not repeat",
    "Decisions",
    "Gotchas",
    "Map",
    "Sessions",
)
REWRITE: Tuple[str, ...] = ("State", "Next", "Map")
APPEND_ONLY: Tuple[str, ...] = ("Do not repeat", "Decisions", "Gotchas", "Sessions")

#: The worktree moved this much further than the handoff before it counts as
#: stale. Two days, so one day of ordinary build churn raises nothing.
STALE_SECONDS = 2 * 86400

NEXT_ON_NOTE = 6           # ordered steps printed on the card
DNR_ON_NOTE = 3            # last three dead ends, which is what the stage asks for
STATE_WIDTH = 600          # one paragraph, not a transcript
LINE_WIDTH = 200
FM_WIDTH = 60              # one frontmatter scalar, e.g. a date
MAX_HANDOFF_BYTES = 400_000

TEMPLATE_REF = ".claude/skills/handoff/references/handoff-template.md"
RULES_REF = ".claude/skills/handoff/references/handoff-rules.md"

#: The template's own placeholder rows. They are skipped in the projection, so a
#: seeded-but-unfilled handoff renders as empty rather than as advice to Max.
#: Matched on the exact line, never on a pattern: a real Next step may well say
#: `factory grant <feature> ship`, and dropping that would be worse than
#: printing a placeholder.
TEMPLATE_LINES: Tuple[str, ...] = (
    "- [ ] <step> - `<command or file>`",
    "- YYYY-MM-DD: tried X; failed because Y; evidence <path>; retry only if Z",
    "- YYYY-MM-DD: chose A over B because C",
    "- <quirk>",
    "- YYYY-MM-DD HH:MM <session-id or label> <skill or mode>: one line of what it did",
    "| source | `<path>` | <why> |",
    "| what | where | why |",
    "|---|---|---|",
)

_HEADING = re.compile(r"^##\s+(\S.*?)\s*$")
_BULLET = re.compile(r"^\s*-\s+")
_CHECKBOX = re.compile(r"^\s*-\s+\[( |x|X)\]\s*")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _tilde(path: Any) -> str:
    home = str(Path.home())
    text = str(path)
    return "~" + text[len(home):] if text.startswith(home) else text


def _under(path: Path, parent: Path) -> bool:
    """True when ``path`` is at or under ``parent``, symlinks resolved.

    ``os.path.realpath`` rather than ``Path.resolve`` because the destination
    does not exist yet and /var against /private/var must compare equal here.
    """
    try:
        Path(os.path.realpath(str(path))).relative_to(
            Path(os.path.realpath(str(parent)))
        )
        return True
    except Exception:
        return False


def _is_note(line: str) -> bool:
    """A template discipline note, ``_Rewritten every session._``."""
    text = line.strip()
    return len(text) > 1 and text.startswith("_") and text.endswith("_")


def _is_template(line: str) -> bool:
    return line.strip() in TEMPLATE_LINES


def _skip(line: str) -> bool:
    return (not line.strip()) or _is_note(line) or _is_template(line)


def _safe(text: str) -> str:
    """Neutralize the note's fence markers inside projected handoff prose.

    The handoff is written by a session, and a session that records "the board
    refused the note because it lost its ``<!-- factory:body:end -->`` marker"
    plants a second fence in the generated body. ``render.compose_note`` splits
    the existing note at the **first** ``body:end``, so the planted one makes
    everything after it read as the human tail: the real body is preserved and
    then re-appended after the freshly generated one, and the note grows by its
    own length on every board run. All four markers stay present, so the marker
    refusal never fires and nothing is logged, and the delete-and-rebuild
    byte-identity invariant fails silently.

    Escaping the comment opener is enough, and it is enough for all four
    markers at once: the text still reads as written, and the generated file
    carries exactly the four markers the renderer put there.
    """
    return str(text).replace("<!--", "&lt;!--")


def _clip(text: str, width: int) -> str:
    # Collapse first, then escape: a marker wrapped over two source lines is
    # one marker once the whitespace is normalized, so the escape has to come
    # after the join. Truncation only takes a prefix, which can never create a
    # marker the escape did not already remove.
    text = _safe(" ".join(text.split()))
    return text if len(text) <= width else text[: width - 3].rstrip() + "..."


def worktree_path(obs: Dict[str, Any]) -> Optional[Path]:
    wt = (obs or {}).get("worktree")
    return (Path(wt) / HANDOFF_REL) if wt else None


def archive_path(ctx: Any, feature: str) -> Path:
    return ctx.config.artifacts_dir / config.validate_id(feature) / HANDOFF_NAME


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def split_sections(text: str) -> Dict[str, List[str]]:
    """``{heading: body lines}`` for every ``## `` heading, in file order.

    ``###`` subheadings stay inside their section: only a two-hash heading opens
    a new one, which is what lets a writer structure a Map however it likes.
    """
    out: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for line in (text or "").splitlines():
        m = _HEADING.match(line)
        if m:
            current = m.group(1)
            out.setdefault(current, [])
            continue
        if current is not None:
            out[current].append(line)
    return out


def _paragraphs(lines: List[str]) -> List[str]:
    """Blank-line-separated paragraphs, each joined into one whitespace-normal
    line. Markdown wraps a sentence over two lines; a reader must not care."""
    out: List[str] = []
    cur: List[str] = []
    for line in lines:
        if line.strip():
            cur.append(line.strip())
            continue
        if cur:
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def parse(text: str) -> Dict[str, Any]:
    """The handoff as data. Never raises: an unparseable file is still a card."""
    fm = probe._frontmatter(text or "")
    if not isinstance(fm, dict):
        fm = {}
    sections = split_sections(text or "")

    state = ""
    for para in _paragraphs(sections.get("State") or []):
        # Paragraph-wise, not line-wise: the template's discipline note wraps
        # over two lines, so neither line alone starts and ends with "_".
        if _is_note(para) or _is_template(para):
            continue
        state = _clip(para, STATE_WIDTH)
        break                    # the first real paragraph, and no more

    steps: List[str] = []
    for line in sections.get("Next") or []:
        if _skip(line) or not _BULLET.match(line):
            continue
        steps.append(_clip(line.strip(), LINE_WIDTH))

    dnr: List[str] = []
    for line in sections.get("Do not repeat") or []:
        if _skip(line) or not _BULLET.match(line):
            continue
        dnr.append(_clip(line.strip(), LINE_WIDTH))

    sessions = fm.get("sessions")
    try:
        sessions = int(str(sessions).strip())
    except Exception:
        sessions = None

    first = ""
    if steps:
        first = _CHECKBOX.sub("", steps[0])
        first = _BULLET.sub("", first).strip()

    return {
        # Frontmatter is arbitrary text too, and `updated` is printed on the
        # note, so it goes through the same clip as every projected line.
        "feature": _clip(str(fm.get("feature") or ""), FM_WIDTH) or None,
        "handoff_updated": _clip(str(fm.get("updated") or ""), FM_WIDTH) or None,
        "handoff_sessions": sessions,
        "handoff_state": state,
        "handoff_next": _clip(first, LINE_WIDTH),
        "next": steps,
        "dnr": dnr,
        "missing_sections": [s for s in SECTIONS if s not in sections],
    }


EMPTY: Dict[str, Any] = {
    "path": None,
    "source": None,
    "feature": None,
    "handoff_updated": None,
    "handoff_sessions": None,
    "handoff_state": "",
    "handoff_next": "",
    "handoff_stale": False,
    "next": [],
    "dnr": [],
    "missing_sections": list(SECTIONS),
    "mtime": None,
    "rescued": None,
    "readable": False,
}


def read_record(ctx: Any, feature: str, obs: Dict[str, Any]) -> Dict[str, Any]:
    """The handoff for one card: the worktree copy first, the rescued copy next.

    The worktree copy is the living document, so it wins whenever it is there.
    Once the worktree is gone the rescued copy under ``Artifacts/`` is the only
    record, which is the whole reason the rescue exists.
    """
    rec = dict(EMPTY)
    live = worktree_path(obs)
    archived = archive_path(ctx, feature)
    path, source = None, None
    if live is not None and live.is_file():
        path, source = live, "worktree"
    elif archived.is_file():
        path, source = archived, "artifacts"
    if path is None:
        return rec

    text, ok = probe._read_text(path, limit=MAX_HANDOFF_BYTES)
    mt, _ = probe._mtime(path)
    rec.update({"path": str(path), "source": source, "mtime": mt, "readable": bool(ok)})
    if not ok or not text:
        return rec
    rec.update(parse(text))
    rec["handoff_stale"] = is_stale(obs, mt) if source == "worktree" else False
    return rec


# --------------------------------------------------------------------------
# Staleness: three mtimes, compared against each other and never against now
# --------------------------------------------------------------------------


def tracked_mtime(obs: Dict[str, Any]) -> Optional[float]:
    """The newest mtime of the two tracked files: the blueprint and the build
    record. Both already come from the probe round, so this costs nothing."""
    best: Optional[float] = None
    for key in ("blueprint", "build"):
        rec = (obs or {}).get(key)
        mt = rec.get("mtime") if isinstance(rec, dict) else None
        if isinstance(mt, (int, float)) and (best is None or mt > best):
            best = float(mt)
    return best


def is_stale(obs: Dict[str, Any], handoff_mtime: Optional[float]) -> bool:
    """The worktree moved on and nobody wrote the handoff."""
    if not isinstance(handoff_mtime, (int, float)):
        return False
    newest = tracked_mtime(obs)
    if newest is None:
        return False
    return (newest - float(handoff_mtime)) > STALE_SECONDS


# --------------------------------------------------------------------------
# 1. collect: the rescue
# --------------------------------------------------------------------------


def rescue(ctx: Any, src: Path, dest: Path) -> str:
    """Copy ``src`` over ``dest``, idempotently. Writes under Artifacts/ only.

    Returns ``same``, ``copied``, ``dry-run``, ``too-large`` or ``failed``.

    This is deliberately not ``ext_artifacts.rescue``. That one gives a
    differing copy a numbered suffix, which is right for a build record (one
    immutable record per label) and wrong here: the handoff is a single living
    document that is rewritten every session, so suffixing would bury
    ``Artifacts/<feature>/`` under a hundred near-identical files within a week.
    The overwrite is safe because the append-only sections only ever grow, so the
    newest copy is a superset of the one it replaces. ``copy2`` keeps the mtime,
    which is what makes the next run a no-op.
    """
    if not _under(dest, ctx.config.artifacts_dir):
        raise config.RefusedWrite(
            "refused: %s is outside %s, which is the only place this extension writes"
            % (dest, ctx.config.artifacts_dir)
        )
    try:
        size = src.stat().st_size
    except Exception as exc:
        # The worktree can vanish between the is_file() check and this stat.
        # Silence here loses the only record of the dead ends the feature paid
        # for, because `factory teardown` then removes the sole other copy.
        ctx.log("handoff: cannot stat %s, so it was not rescued: %s" % (src, exc))
        return "failed"
    if size > MAX_HANDOFF_BYTES:
        ctx.log(
            "handoff: %s is %d bytes, over the %d byte cap, so it was not rescued; "
            "move the pasted output out of it and run /handoff"
            % (src, size, MAX_HANDOFF_BYTES)
        )
        return "too-large"
    try:
        if dest.is_file() and dest.stat().st_size == size and dest.read_bytes() == src.read_bytes():
            return "same"
    except Exception:
        pass
    if ctx.dry_run:
        return "dry-run"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    except Exception as exc:
        ctx.log("handoff: copy %s -> %s failed: %s" % (src, dest, exc))
        return "failed"
    return "copied"


def collect(ctx: Any) -> None:
    """Runs in the probe round, before derive. Writes only under Artifacts/."""
    table: Dict[str, Dict[str, Any]] = {}
    for feature in sorted(ctx.obs):
        obs = ctx.obs[feature] or {}
        try:
            config.validate_id(feature)
            live = worktree_path(obs)
            status = None
            if live is not None and live.is_file():
                status = rescue(ctx, live, archive_path(ctx, feature))
            rec = read_record(ctx, feature, obs)
            rec["rescued"] = status
        except Exception as exc:
            ctx.log("handoff: %s failed: %s" % (feature, exc))
            continue
        obs["handoff"] = rec
        table[feature] = rec
    ctx.meta["handoff"] = table


# --------------------------------------------------------------------------
# The published record
# --------------------------------------------------------------------------


def record(ctx: Any, card_or_feature: Any) -> Dict[str, Any]:
    """The handoff record for one card, from the probe round when there was one.

    ``factory status`` renders without a probe round, so fall back to
    ``ctx.meta`` and then to a direct read of the two paths.
    """
    feature = getattr(card_or_feature, "id", card_or_feature)
    obs = ctx.obs.get(feature) or {}
    rec = obs.get("handoff")
    if isinstance(rec, dict):
        return rec
    rec = (ctx.meta.get("handoff") or {}).get(feature)
    if isinstance(rec, dict):
        return rec
    if not config.is_safe_id(str(feature)):
        return dict(EMPTY)
    if not obs.get("worktree"):
        wt = getattr(card_or_feature, "worktree", None)
        if wt:
            obs = dict(obs)
            obs["worktree"] = wt
    try:
        return read_record(ctx, str(feature), obs)
    except Exception:
        return dict(EMPTY)


def handoff_next(ctx: Any, card_or_feature: Any) -> str:
    """The first ``## Next`` step, or the empty string. The published field."""
    return str(record(ctx, card_or_feature).get("handoff_next") or "")


# --------------------------------------------------------------------------
# 3. card_flags, and the published field on the card
# --------------------------------------------------------------------------

#: The keys this extension publishes per card. Every reader uses the same names,
#: so a core ``FeatureCard.extra`` dict can be filled from the record verbatim.
PUBLISHED: Tuple[str, ...] = (
    "handoff_next",
    "handoff_state",
    "handoff_updated",
    "handoff_sessions",
    "handoff_stale",
)


def card_flags(card: Any, obs: Dict[str, Any], ctx: Any) -> List[str]:
    """``handoff-stale``, plus the published fields on ``card.extra`` if it exists."""
    rec = record(ctx, card)
    extra = getattr(card, "extra", None)
    if isinstance(extra, dict):
        # Core has grown the field: publish there too, so `to_dict` carries it.
        for key in PUBLISHED:
            extra[key] = rec.get(key)
    if not card.worktree:
        return []
    return ["handoff-stale"] if rec.get("handoff_stale") else []


# --------------------------------------------------------------------------
# 2. The note section
# --------------------------------------------------------------------------


def note_sections(card: Any, ctx: Any) -> List[Tuple[str, str, int]]:
    rec = record(ctx, card)
    out: List[str] = []
    if not rec.get("path"):
        out.append(
            "_No `specs/handoff.md`. Run `/handoff` in the worktree to write one: it is the "
            "only record of what a session already tried and ruled out._"
        )
        return [("Handoff", "\n".join(out), ORDER_HANDOFF)]

    where = (
        "the worktree copy"
        if rec.get("source") == "worktree"
        else "the rescued copy, because the worktree is gone"
    )
    out.append(
        "%s - updated **%s**, %s session%s recorded - read from %s."
        % (
            "[%s](%s)" % (HANDOFF_NAME, _file_uri(rec.get("path"))),
            rec.get("handoff_updated") or "unknown",
            rec.get("handoff_sessions") if rec.get("handoff_sessions") is not None else "?",
            "" if rec.get("handoff_sessions") == 1 else "s",
            where,
        )
    )
    out.append("")

    if rec.get("handoff_stale"):
        out.append(
            "Flagged `handoff-stale`: `specs/blueprint.md` or the newest build record is more "
            "than two days newer than the handoff. Run `/handoff` before the next session reads it."
        )
        out.append("")

    out.append("### State")
    out.append("")
    out.append(rec.get("handoff_state") or "_Empty._")
    out.append("")

    steps = rec.get("next") or []
    out.append("### Next")
    out.append("")
    if steps:
        # Plain bullets, never live checkboxes. The note's body is regenerated
        # on every board run, so a box ticked here is erased within 120 s and
        # is never read back: `probe.note` scans the head block only. The real
        # checkboxes stay in the worktree file that /handoff owns.
        out.extend(_CHECKBOX.sub("- ", s) for s in steps[:NEXT_ON_NOTE])
        if len(steps) > NEXT_ON_NOTE:
            out.append("- and %d more, in the handoff" % (len(steps) - NEXT_ON_NOTE,))
    else:
        out.append("_Empty._")
    out.append("")

    dnr = rec.get("dnr") or []
    out.append("### Do not repeat (last %d of %d)" % (min(DNR_ON_NOTE, len(dnr)), len(dnr)))
    out.append("")
    if dnr:
        out.extend(dnr[-DNR_ON_NOTE:])
    else:
        out.append("_Nothing recorded. A dead end costs the next session an hour._")
    missing = rec.get("missing_sections") or []
    if missing:
        out.append("")
        out.append(
            "_Missing heading%s: %s. The readers find a section by name, so `/handoff` restores "
            "them from the template._" % ("" if len(missing) == 1 else "s", ", ".join(missing))
        )
    return [("Handoff", "\n".join(out), ORDER_HANDOFF)]


def _file_uri(path: Any) -> str:
    from . import render

    return render.file_uri(path)


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------


def doctor_checks(ctx: Any) -> List[Tuple[str, bool, str]]:
    cfg = ctx.config
    out: List[Tuple[str, bool, str]] = []
    template = cfg.repo_root / TEMPLATE_REF
    out.append(
        (
            "handoff template present",
            template.is_file(),
            "%s is missing, so /handoff and /moose-blueprint cannot seed a handoff"
            % (_tilde(template),),
        )
    )
    broken: List[str] = []
    for feature in sorted(ctx.meta.get("handoff") or {}):
        rec = (ctx.meta.get("handoff") or {})[feature]
        if not isinstance(rec, dict) or not rec.get("path"):
            continue
        if rec.get("missing_sections"):
            broken.append("%s (%s)" % (feature, ", ".join(rec["missing_sections"])))
    out.append(
        (
            "every handoff carries its seven headings",
            not broken,
            "these lost a heading: %s. Run /handoff in the worktree to restore it."
            % ("; ".join(broken),),
        )
    )
    # A handoff that is never rescued dies with its worktree. `too-large` and
    # `failed` are both silent to the reader of the note, so they get a row.
    unrescued = sorted(
        feature
        for feature, rec in (ctx.meta.get("handoff") or {}).items()
        if isinstance(rec, dict) and rec.get("rescued") in ("too-large", "failed")
    )
    out.append(
        (
            "every handoff is rescued into Artifacts/",
            not unrescued,
            "not copied for: %s. The worktree copy is then the only one, and "
            "`factory teardown` removes it: see the log line for the cause."
            % (", ".join(unrescued),),
        )
    )
    return out
