"""Board.html: the kanban the board has always described, rendered as one page.

Why an HTML file and not a Bases view
-------------------------------------

Bases at app 1.13.7 registers exactly ``table``, ``cards`` and ``list``. A
``cards`` view grouped by ``posture`` is the native fallback and it is what
``Features.base`` carries. It cannot show a next move, a command, a CIVET
colour and a links row on one card, and it cannot rank the needs-you column by
the flag priority. This file is the kanban; the Bases view stays as the native
fallback.

What this extension is
----------------------

One more generated output, written through the renderer's ``outputs`` hook
exactly like ``Studies/<id>.md``:

    Board.html     six columns, one card per feature, one compact card per study

Five rules, the first three inherited from the rest of the package:

1. **No clock.** The masthead prints a content stamp from
   ``snapshot.Store.stamp``, so deleting ``Board.html`` and running
   ``factory board`` gives back the same bytes. No age in days, no pid, no
   "as of" that moves on its own. The session rows print the session's state,
   never how long it has been up: an elapsed time is a clock read.
2. **Atomic, byte-equal-skip writes.** ``render.atomic_write`` compares the
   bytes first, so a run that changes nothing touches no file and the tick has
   nothing to commit.
3. **Every string escaped.** A pull-request title is arbitrary text from
   GitHub: ``<`` and ``&`` and ``|`` all occur. Everything that reaches the
   page goes through :func:`esc`, and every URL through
   :func:`urllib.parse.quote`, so no input can close a tag. The three strings
   that come from markdown a human wrote go through :func:`esc_md`, which
   escapes first and only then turns paired backticks into ``<code>``.
4. **Nothing remote.** No webfont, no script, and no image the network has to
   fetch. The gallery thumbnails are the one ``<img>`` on the page and they are
   a relative vault path, ``Gallery/<feature>/<file>``, which is a symlink into
   the worktree: the page still renders whole with no network at all. Every
   other generated file in this vault is self-contained and this one is not the
   exception: it
   has to look right offline and inside Obsidian's HTML Reader.
5. **Per card, not per page.** Every row renders inside its own ``try``, and a
   row that raises becomes a placeholder card plus one log line. A note
   degrades per card in ``render.sync``; before this the page was the one
   all-or-nothing output, so one odd-typed probe field on one card left the
   whole kanban unwritten and the stale page on disk.

The path comes from ``config.Config.board_html``, with a fallback to
``<vault>/Board.html`` for the test doubles that pass a bare namespace.

The card order is exactly ``Home.md``'s: the needs-you column is sorted by
``FeatureCard.priority_key`` (the flag precedence), and every other column by
id. The cap that turns Home's sixth needs-you row into one "Backlog" line does
not apply here: a column scrolls, a table does not.
"""

from __future__ import annotations

import html
import re
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Tuple

from . import config, ext_gallery, probe, render, snapshot
from .model import DONE, NEEDS_YOU, PARKED, POSTURE, READY, RUNNING, WAITING

BOARD_NAME = "Board.html"

#: The stamp key, and the key the counts land under in ``render.sync``.
STAMP_KEY = BOARD_NAME

#: Column order, left to right. Identical to ``model.POSTURE`` on purpose: the
#: board and Home.md may never disagree about the order of the six groups.
COLUMNS: Tuple[str, ...] = POSTURE

COLUMN_LABEL: Dict[str, str] = {
    NEEDS_YOU: "needs you",
    RUNNING: "running",
    READY: "ready",
    WAITING: "waiting",
    PARKED: "parked",
    DONE: "done",
}

COLUMN_EMPTY: Dict[str, str] = {
    NEEDS_YOU: "Nothing needs you. Read this line twice.",
    RUNNING: "No live session in any worktree.",
    READY: "Nothing is built and waiting on a ship gate.",
    WAITING: "Nothing is out for review.",
    PARKED: "Nothing parked.",
    DONE: "Nothing finished yet.",
}

# Flag severity. The vocabulary is closed (``model.FLAGS``) plus whatever an
# extension adds through ``card_flags``; anything not named here is neutral, so
# a new flag renders as a plain chip instead of shouting.
CRITICAL_FLAGS = frozenset(
    {
        "ci-red",
        "conflicting",
        "blocked",
        "stalled",
        "changes-requested",
        "review-findings",
        "foreign-worktree",
        "branch-mismatch",
    }
)

WARNING_FLAGS = frozenset(
    {
        "probe-stale",
        "lease-stale",
        "build-stale",
        "view-stale",
        "stale-pipeline",
        # Not in model.FLAGS yet: the handoff extension raises it. Listed here
        # so it renders as a warning the day it appears, with no edit.
        "handoff-stale",
    }
)

#: Three PR-derived flags that the PR row already states, with more detail. The
#: chips row drops them whenever that row is on the same card: four red chips
#: for two facts dilutes the colour that carries the severity.
PR_DERIVED_FLAGS = frozenset({"ci-red", "conflicting", "changes-requested"})

#: Only these three schemes may appear in an href. Anything else is rendered as
#: text, because a vault page that can reach an arbitrary scheme is a hole.
SAFE_SCHEMES = ("obsidian://", "vscode://file/", "https://github.com/")

#: The one relative URL on the page, and it is an ``img src`` rather than an
#: href, so :func:`safe_href` does not apply to it. It is kept to exactly one
#: shape -- ``Gallery/<feature>/<file>``, no scheme, no host, no ``..`` -- by
#: :func:`thumb_src`, which refuses anything else. That shape is what the
#: HTML Reader plugin resolves: the plugin prepends
#: ``<base href="<vault.getResourcePath(Board.html)>">`` to the document before
#: it hands it to the iframe as ``srcdoc``, so a relative path resolves against
#: Board.html's own ``app://`` resource URL, which is the vault directory.
GALLERY_HREF_PREFIX = "Gallery/"

#: Our own reader, the one plugin this vault expects. Its ``main.js`` is
#: gitignored like any plugin code, so the doctor row that names this id
#: carries the recipe to rebuild it.
BOARD_READER_ID = "moose-board-reader"

# There is no webfont. The page is a vault file and every other generated file
# in this vault is self-contained, so the one artifact Max opens on a plane may
# not need the network to look right: a Google Fonts stylesheet never arrives
# offline or inside Obsidian's HTML Reader, and `display=swap` re-lays the page
# out mid-read when it does. The three stacks below carry the hierarchy on
# their own, by weight and size, with the system faces macOS already has.


# --------------------------------------------------------------------------
# Escaping and links
# --------------------------------------------------------------------------


def esc(text: Any) -> str:
    """Every string that reaches the page goes through here. Quotes included."""
    return html.escape("" if text is None else str(text), quote=True)


#: Paired markdown backticks, matched on text that is already HTML-escaped.
_CODE = re.compile(r"`([^`]+)`")


def esc_md(text: Any) -> str:
    """Escape, then render paired backticks as ``<code>``.

    Three strings on a card come from markdown a human wrote: the handoff's
    first Next step, a compact card's why, and a study's why. The handoff
    template mandates ``- [ ] <step> - `<command or file>` ``, so nearly every
    real Next line carries a backticked command, and raw backticks on the page
    read as punctuation while the next-move command two lines above is in a
    monospace chip. Escaping first keeps the span's content escaped; an odd
    trailing backtick stays text, because only a pair opens a span.
    """
    return _CODE.sub(r"<code>\1</code>", esc(text))


def plural(n: Any, one: str, many: str) -> str:
    """``1 card``, ``2 cards``. The masthead is the first line anyone reads."""
    return one if n == 1 else many


def board_path(cfg: Any) -> Path:
    """``<vault>/Board.html``, from ``config.Config.board_html``.

    The fallback keeps every test double that passes a bare namespace with a
    ``vault`` attribute working.
    """
    path = getattr(cfg, "board_html", None)
    return Path(path) if path else Path(cfg.vault) / BOARD_NAME


def vault_name(cfg: Any) -> str:
    """The Obsidian vault name, which the config lets differ from the directory."""
    name = getattr(cfg, "obsidian_vault", "")
    return str(name) if name else Path(cfg.vault).name


def obsidian_url(cfg: Any, target: str) -> str:
    """``obsidian://open?vault=<vault>&file=<target>``, both components quoted."""
    return "obsidian://open?vault=%s&file=%s" % (
        urllib.parse.quote(vault_name(cfg), safe=""),
        urllib.parse.quote(target, safe=""),
    )


def vscode_uri(path: Any) -> str:
    """``vscode://file/<abs path>``, for a workspace the board offers to open.

    Not ``file://``. A page may not navigate to ``file://`` from any other
    origin: a browser refuses it outright, and inside Obsidian the board is a
    document on ``app://``, so the workspace links did nothing when clicked. VS
    Code declares the ``vscode`` scheme in its Info.plist, and a custom scheme
    is handed to the OS rather than blocked, so the same href works in a browser
    and in the reader. ``.code-workspace`` is not the thing to open by path: the
    scheme carries the intent, which is that VS Code opens the workspace.
    """
    return "vscode://file" + urllib.parse.quote(str(path))


def safe_href(url: Any) -> str:
    """The url when its scheme is one of the three, else ``""``."""
    text = str(url or "")
    return text if text.startswith(SAFE_SCHEMES) else ""


def link(url: Any, text: Any, cls: str = "") -> str:
    """One anchor, or plain text when the scheme is not allowed."""
    attr = ' class="%s"' % (esc(cls),) if cls else ""
    href = safe_href(url)
    if not href:
        return "<span%s>%s</span>" % (attr, esc(text))
    return '<a%s href="%s">%s</a>' % (attr, esc(href), esc(text))


def chip(text: Any, kind: str = "") -> str:
    return '<span class="chip%s">%s</span>' % (
        (" " + kind) if kind else "",
        esc(text),
    )


def flag_chip(flag: Any) -> str:
    # str() first: a set lookup on an unhashable value raises, and one odd flag
    # must never be the reason the whole page is not written.
    name = str(flag)
    if name in CRITICAL_FLAGS:
        return chip(name, "crit")
    if name in WARNING_FLAGS:
        return chip(name, "warn")
    return chip(name)


def is_critical(card: Any) -> bool:
    """One left stripe, and only for a reason in the critical set."""
    return any(str(f) in CRITICAL_FLAGS for f in (getattr(card, "flags", None) or []))


# --------------------------------------------------------------------------
# Facts the card needs that live in a sibling extension
# --------------------------------------------------------------------------


def handoff_next(card: Any, ctx: Any) -> str:
    """The first ``Next`` line of this card's handoff, or ``""``.

    ``tool/ext_handoff.py`` owns the handoff and publishes
    ``handoff_next(ctx, card)``, so that is asked first. The rest is defensive:
    the same string is published on ``ctx.meta["handoff"][id]``, on
    ``ctx.obs[id]["handoff"]`` and on ``card.extra``, and an older or newer
    shape of that record must degrade to "print nothing" rather than to a
    traceback inside the renderer.
    """
    try:
        from . import ext_handoff

        fn = getattr(ext_handoff, "handoff_next", None)
        if fn is not None:
            line = _one_line(fn(ctx, card))
            if line:
                return line
    except Exception:
        pass
    for payload in (
        (ctx.meta.get("handoff") or {}).get(card.id)
        if isinstance(getattr(ctx, "meta", None), dict)
        else None,
        ((ctx.obs or {}).get(card.id) or {}).get("handoff"),
        getattr(card, "extra", None),
        getattr(card, "handoff", None),
    ):
        line = _first_next(payload)
        if line:
            return line
    return ""


def _first_next(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("handoff_next", "next", "next_lines", "nexts", "first_next"):
            value = payload.get(key)
            if isinstance(value, (list, tuple)):
                for item in value:
                    line = _one_line(item)
                    if line:
                        return line
            line = _one_line(value)
            if line:
                return line
        return ""
    if isinstance(payload, (list, tuple)):
        for item in payload:
            line = _one_line(item)
            if line:
                return line
    return _one_line(payload)


def _one_line(value: Any) -> str:
    """One printable line, or ``""``. A dict contributes its ``text``."""
    if isinstance(value, dict):
        value = value.get("text") or value.get("why") or value.get("line")
    if not isinstance(value, str):
        return ""
    line = value.replace("\r", " ").replace("\n", " ").strip()
    line = line.lstrip("-* ").strip()
    return line[:200]


def teardown_due(card: Any) -> bool:
    """Is the teardown gate the thing that is actually waiting on Max?

    The note's Teardown section is wider: it prints the number for every card
    with a checkout, because the note is where you go to read one card. A board
    card has room for the facts that decide something today, so the size shows
    only where the disk is genuinely reclaimable: the work has merged or been
    archived, or the checkout is a legacy tree outside the worktree root.
    """
    if card.gate_state("teardown") == "granted":
        return False
    if not (card.worktree or card.has("foreign-worktree")):
        return False
    return card.has("foreign-worktree") or card.lane in ("merged", "archived")


def reclaimable(card: Any, ctx: Any) -> str:
    """``12.4 GB`` when the teardown gate is due, else ``""``.

    The number comes from ``tool/ext_teardown.py``, which owns it: the board
    and the note's Teardown section must print the same size or one of them is
    lying.
    """
    if not teardown_due(card):
        return ""
    try:
        from . import ext_teardown

        kb = ext_teardown.cached_kb(card.id, ctx)
        return ext_teardown._gb(kb) if kb else ""
    except Exception:
        return ""


def studies(ctx: Any) -> List[Any]:
    """Every study, already loaded by ``ext_studies.collect``. Never written."""
    try:
        from . import ext_studies
    except Exception:
        return []
    try:
        return list(ext_studies.studies_for(ctx))
    except Exception:
        return []


# --------------------------------------------------------------------------
# One feature card
# --------------------------------------------------------------------------


def session_state(session: Dict[str, Any]) -> str:
    """``waitingFor`` first: a session blocked on a prompt is not busy."""
    state = (
        session.get("waitingFor")
        or session.get("needs")
        or session.get("state")
        or session.get("status")
        or "unknown"
    )
    return "waiting: %s" % (state,) if session.get("waitingFor") else str(state)


def attach_id(session: Dict[str, Any]) -> str:
    # ``~/.claude/sessions/*.json`` is an external schema the CLI owns, so both
    # values are coerced: a numeric sessionId has no .split and would otherwise
    # take the whole page down with it.
    return str(session.get("bg_id") or "") or str(session.get("sessionId") or "").split("-")[0]


def clip_title(title: Any, width: int = 90) -> str:
    """A title cut at ``width`` says so, on a word boundary.

    Without the marker the page states a pull-request title that does not
    exist, which is the one thing a board may not do.
    """
    text = " ".join(str(title or "").split())
    if len(text) <= width:
        return text
    cut = text[: width - 3].rstrip()
    if " " in cut:
        cut = cut[: cut.rindex(" ")].rstrip()
    return cut + "..."


def pr_line(card: Any) -> str:
    """Number, draft or ready, CIVET colour, mergeability, and the title."""
    pr = card.primary_pr()
    if not pr:
        return ""
    bits = [
        link(pr.get("url"), "%s #%s" % (pr.get("repo") or "pr", pr.get("number")), "pr"),
    ]
    state = (pr.get("state") or "").lower()
    bits.append(chip("draft" if pr.get("isDraft") else (state or "open")))
    ci = pr.get("ci")
    if ci:
        # str() before the lookup: the rollup is GitHub's shape, and a dict
        # there is unhashable.
        colour = str(ci)
        kind = {"red": "crit", "pending": "warn", "green": "ok"}.get(colour, "")
        bits.append(chip("CIVET " + colour, kind))
    mergeable = pr.get("mergeable") or "UNKNOWN"
    if pr.get("mergeable_unknown") or mergeable == "UNKNOWN":
        bits.append(chip("mergeable not computed"))
    elif mergeable == "CONFLICTING":
        bits.append(chip("conflicting", "crit"))
    else:
        bits.append(chip(str(mergeable).lower()))
    review = pr.get("reviewDecision")
    if review:
        kind = "crit" if review == "CHANGES_REQUESTED" else ("ok" if review == "APPROVED" else "")
        bits.append(chip(str(review).lower().replace("_", " "), kind))
    title = clip_title(pr.get("title"))
    head = '<p class="pr">%s</p>' % (" ".join(bits),)
    if title:
        head += '<p class="title">%s</p>' % (esc(title),)
    return head


def links_row(card: Any, cfg: Any) -> str:
    """workspace, stack, note, PR. Only the ones that exist, in that order."""
    out: List[str] = []
    wt = card.worktree
    if wt:
        for name, label in (
            (card.id + ".code-workspace", "workspace"),
            ("moose_stack.code-workspace", "stack"),
        ):
            path = Path(wt) / name
            if path.is_file():
                out.append(link(vscode_uri(path), label))
    out.append(link(obsidian_url(cfg, "Features/" + card.id), "note"))
    pr = card.primary_pr()
    if pr and safe_href(pr.get("url")):
        out.append(link(pr.get("url"), "PR"))
    return '<p class="links">%s</p>' % (" ".join(out),)


def thumb_src(feature: Any, name: Any) -> str:
    """``Gallery/<feature>/<file>``, percent-encoded, or ``""``.

    The only relative URL on the page. It is refused unless both halves are the
    plain names the gallery extension already validated, so no input can turn
    an ``img src`` into a scheme, a host or a path that climbs out of the vault.
    ``quote`` with an empty safe set, so a space or a ``#`` in a filename is
    encoded rather than read as a fragment.
    """
    feat, file_name = str(feature or ""), str(name or "")
    if not config.is_safe_id(feat):
        return ""
    if not ext_gallery.SAFE_NAME.match(file_name):
        return ""
    return GALLERY_HREF_PREFIX + "%s/%s" % (
        urllib.parse.quote(feat, safe=""),
        urllib.parse.quote(file_name, safe=""),
    )


def gallery_strip(card: Any, ctx: Any) -> str:
    """Up to ``gallery_thumbs`` thumbnails, or ``""`` when there is no gallery.

    In the order ``specs/gallery/gallery.md`` puts them in, with the figure's
    own heading as its label: the page decides which figure leads, and a card
    that shows a different first figure than the note disagrees with the note.
    A file the page does not mention comes after the ones it does, labelled by
    its filename.

    Images only: a CSV has no thumbnail, and a broken image icon for one states
    something false. The label is both ``alt`` and ``title``, so the strip reads
    the same to a screen reader and to a pointer. Every heading was clipped and
    marker-escaped by ``ext_gallery`` before it got here, and :func:`esc` closes
    the HTML half of the same hole.
    """
    limit = ext_gallery.thumbs(ctx)
    if limit <= 0:
        return ""
    rows = [row for row in ext_gallery.files(ctx, card) if row.get("image")]
    if not rows:
        return ""
    out: List[str] = []
    for row in rows[:limit]:
        src = thumb_src(card.id, row.get("name"))
        if not src:
            continue
        label = str(row.get("title") or row.get("name") or "")
        out.append(
            '<img src="%s" alt="%s" title="%s" loading="lazy">'
            % (esc(src), esc(label), esc(label))
        )
    if not out:
        return ""
    more = len(rows) - len(out)
    tail = '<span class="more">+%d</span>' % (more,) if more > 0 else ""
    return '<p class="shots">%s%s</p>' % ("".join(out), tail)


def feature_card(card: Any, ctx: Any, compact: bool = False) -> str:
    cfg = ctx.config
    cls = ["card"]
    if compact:
        cls.append("compact")
    if is_critical(card):
        cls.append("crit")
    out: List[str] = ['<article class="%s">' % (" ".join(cls),)]
    out.append(
        '<p class="name">%s</p>'
        % (link(obsidian_url(cfg, "Features/" + card.id), card.id, "wl"),)
    )
    # The PR row is composed first, because its presence decides whether the
    # chips row repeats the three facts it already carries.
    pr = "" if compact else pr_line(card)
    flags = [f for f in (card.flags or []) if not (pr and str(f) in PR_DERIVED_FLAGS)]
    chips = [chip(card.lane, "lane")] + [flag_chip(f) for f in flags]
    out.append('<p class="chips">%s</p>' % ("".join(chips),))

    if compact:
        why = card.next_action.why or card.next_action.verb
        if why:
            out.append('<p class="why">%s</p>' % (esc_md(why),))
        out.append("</article>")
        return "\n".join(out)

    if pr:
        out.append(pr)

    na = card.next_action
    out.append(
        '<p class="next"><span class="verb">%s</span> %s</p>'
        % (esc(na.verb), esc(na.why))
    )
    if na.command:
        out.append('<p class="cmd"><code>%s</code></p>' % (esc(na.command),))

    shots = gallery_strip(card, ctx)
    if shots:
        out.append(shots)

    hand = handoff_next(card, ctx)
    if hand:
        out.append(
            '<p class="hand"><span class="lbl">handoff</span> %s</p>' % (esc_md(hand),)
        )

    session = card.session or {}
    if session:
        out.append(
            '<p class="sess"><span class="lbl">session</span> %s <code>%s attach %s</code></p>'
            % (
                esc(session_state(session)),
                esc(config.claude_display(getattr(ctx, "config", None))),
                esc(attach_id(session)),
            )
        )

    size = reclaimable(card, ctx)
    if size:
        out.append(
            '<p class="meta">reclaimable %s, teardown gate pending</p>' % (esc(size),)
        )

    out.append(links_row(card, cfg))
    out.append("</article>")
    return "\n".join(out)


# --------------------------------------------------------------------------
# One study card: compact, and marked as a study
# --------------------------------------------------------------------------


def study_card(study: Any, ctx: Any) -> str:
    cfg = ctx.config
    out = ['<article class="card compact study">']
    out.append(
        '<p class="name">%s %s</p>'
        % (
            link(obsidian_url(cfg, "Studies/" + study.id), study.id, "wl"),
            chip("study", "study"),
        )
    )
    chips = [chip(study.lane, "lane")]
    progress = _study_progress(study)
    if progress:
        chips.append(chip(progress))
    out.append('<p class="chips">%s</p>' % ("".join(chips),))
    if study.why:
        out.append('<p class="why">%s</p>' % (esc_md(study.why),))
    out.append("</article>")
    return "\n".join(out)


def _study_progress(study: Any) -> str:
    try:
        from . import ext_studies

        if (study.counts or {}).get("total"):
            return ext_studies.progress_str(study.counts)
    except Exception:
        pass
    return ""


# --------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------


def column_cards(posture: str, ctx: Any) -> List[Tuple[str, Any]]:
    """``[("feature", card), ("study", study)]`` in Home.md's order.

    The kind travels with the row, so nothing downstream has to guess which
    dataclass it holds. Features first, studies after them.
    """
    cards = [c for c in ctx.cards if c.posture == posture]
    if posture == NEEDS_YOU:
        try:
            cards.sort(key=lambda c: c.priority_key())
        except Exception as exc:
            # The flag precedence is the only sort on this page that reads a
            # card's contents, so it is the only one an odd flag can break. Id
            # order is wrong but readable; not writing the page at all is not.
            ctx.log("Board.html: the needs-you order fell back to id order: %s" % (exc,))
            cards.sort(key=lambda c: c.id)
    else:
        cards.sort(key=lambda c: c.id)
    rows: List[Tuple[str, Any]] = [("feature", c) for c in cards]
    rows.extend(
        ("study", s)
        for s in sorted((s for s in studies(ctx) if s.posture == posture), key=lambda s: s.id)
    )
    return rows


def column(posture: str, ctx: Any) -> str:
    rows = column_cards(posture, ctx)
    out = [
        '<section class="col %s" aria-labelledby="h-%s">' % (posture, posture),
        '<h2 id="h-%s">%s <span class="n">%d</span></h2>'
        % (posture, esc(COLUMN_LABEL.get(posture, posture)), len(rows)),
    ]
    if not rows:
        out.append('<p class="empty">%s</p>' % (esc(COLUMN_EMPTY.get(posture, "Nothing here.")),))
    for kind, row in rows:
        # One card at a time, each isolated. A note degrades per card in
        # render.sync; before this the page was the one all-or-nothing output,
        # so a single odd-typed probe field on one card meant the whole kanban
        # was not rewritten and the stale page stayed on disk unannounced.
        try:
            if kind == "study":
                out.append(study_card(row, ctx))
            else:
                out.append(feature_card(row, ctx, compact=(posture == DONE)))
        except Exception as exc:
            name = getattr(row, "id", None) or "unknown"
            ctx.log("Board.html: the %s card %s could not be rendered: %s" % (kind, name, exc))
            out.append(placeholder_card(name))
    out.append("</section>")
    return "\n".join(out)


def placeholder_card(name: Any) -> str:
    """The minimal card for a row that raised. It names itself and says so."""
    return "\n".join(
        [
            '<article class="card crit">',
            '<p class="name">%s</p>' % (esc(name),),
            '<p class="why">This card could not be rendered. Read it with '
            "<code>factory next %s</code>; the cause is in the board log.</p>" % (esc(name),),
            "</article>",
        ]
    )


def masthead(ctx: Any) -> str:
    cfg = ctx.config
    cards = ctx.cards
    open_prs = sum(len(c.open_prs()) for c in cards)
    n_studies = len(studies(ctx))
    n_needs = len([c for c in cards if c.posture == NEEDS_YOU])

    sub = [
        "Regenerated by <code>factory board</code>. This picture was established "
        + render.STAMP_HM
        + "; a stamp moves only when the content under it moves."
    ]
    stale = (ctx.meta or {}).get("stale") or []
    if stale:
        sub.append(
            "Unknown this run: " + esc(", ".join(stale)) + " (last good values carried forward)."
        )
    counts = [
        '<span class="count%s"><b>%d</b> %s</span>'
        % (" crit" if n_needs else "", n_needs, plural(n_needs, "needs you", "need you")),
        '<span class="count"><b>%d</b> %s</span>'
        % (len(cards), plural(len(cards), "card", "cards")),
        '<span class="count"><b>%d</b> %s</span>'
        % (open_prs, plural(open_prs, "open PR", "open PRs")),
        '<span class="count"><b>%d</b> %s</span>'
        % (n_studies, plural(n_studies, "study", "studies")),
    ]
    return "\n".join(
        [
            '<header class="masthead">',
            "<div>",
            '<div class="eyebrow">%s &middot; board</div>' % (esc(vault_name(cfg)),),
            "<h1>moose factory<small>" + " ".join(sub) + "</small></h1>",
            '<p class="open">%s</p>'
            % (link(obsidian_url(cfg, "Home"), "Open Home.md in Obsidian", "wl"),),
            "</div>",
            '<div class="counts">' + "".join(counts) + "</div>",
            "</header>",
        ]
    )


CSS = """
:root {
  --bg: #F2F4F7; --surface: #FFFFFF; --surface-2: #E9EDF2;
  --ink: #17202B; --ink-2: #55606E; --ink-3: #667080; --line: #D9DFE6;
  --accent: #0F6C74; --accent-ink: #0B565C; --accent-bg: #E1F0F1;
  --crit: #B4281E; --crit-bg: #FBE9E7; --warn: #8A5A00; --warn-bg: #FCF1D8;
  --ok: #2C6E49; --ok-bg: #E3F2E8; --now: #274C8F; --now-bg: #E6EDFA;
  --display: "Bricolage Grotesque", "Avenir Next", "Segoe UI", system-ui, sans-serif;
  --body: "Public Sans", "Helvetica Neue", Arial, system-ui, sans-serif;
  --mono: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0F1318; --surface: #171C23; --surface-2: #1F262F;
    --ink: #E7EBF0; --ink-2: #9AA5B2; --ink-3: #8A94A1; --line: #2A323C;
    --accent: #5FC3CA; --accent-ink: #8ADDE2; --accent-bg: #123338;
    --crit: #F08A80; --crit-bg: #3A1F1C; --warn: #E3B45C; --warn-bg: #3A2E14;
    --ok: #7CC79A; --ok-bg: #16301F; --now: #8FB3F0; --now-bg: #1B2A45;
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #0F1318; --surface: #171C23; --surface-2: #1F262F;
  --ink: #E7EBF0; --ink-2: #9AA5B2; --ink-3: #8A94A1; --line: #2A323C;
  --accent: #5FC3CA; --accent-ink: #8ADDE2; --accent-bg: #123338;
  --crit: #F08A80; --crit-bg: #3A1F1C; --warn: #E3B45C; --warn-bg: #3A2E14;
  --ok: #7CC79A; --ok-bg: #16301F; --now: #8FB3F0; --now-bg: #1B2A45;
  color-scheme: dark;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: var(--body); font-size: 14.5px; line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
.page { padding: 24px 16px 48px; max-width: 1800px; margin: 0 auto; }
a { color: inherit; }
a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 3px; }
code {
  font-family: var(--mono); font-size: 12px; background: var(--surface-2);
  padding: 1px 5px; border-radius: 4px; overflow-wrap: anywhere;
}
.masthead {
  display: flex; flex-wrap: wrap; align-items: end; justify-content: space-between;
  gap: 14px 32px; padding-bottom: 16px; border-bottom: 1px solid var(--line);
}
.eyebrow {
  font-family: var(--mono); font-size: 11.5px; letter-spacing: .08em;
  text-transform: uppercase; color: var(--ink-3); margin-bottom: 6px;
}
h1 {
  font-family: var(--display); font-size: clamp(26px, 4vw, 34px); font-weight: 600;
  line-height: 1.05; margin: 0; letter-spacing: -.01em;
}
h1 small {
  display: block; max-width: 78ch; font-family: var(--body); font-size: 13.5px;
  font-weight: 400; color: var(--ink-2); margin-top: 8px; letter-spacing: 0;
}
h1 small code { background: transparent; padding: 0; }
.masthead .open { margin: 10px 0 0; font-size: 13.5px; }
.counts { display: flex; flex-wrap: wrap; gap: 8px; }
.count {
  display: inline-flex; align-items: baseline; gap: 6px; padding: 6px 10px;
  border-radius: 6px; background: var(--surface); border: 1px solid var(--line);
  font-size: 13px; color: var(--ink-2);
}
.count b {
  font-family: var(--mono); font-weight: 500; font-size: 14px; color: var(--ink);
  font-variant-numeric: tabular-nums;
}
.count.crit { background: var(--crit-bg); border-color: transparent; color: var(--crit); }
.count.crit b { color: var(--crit); }
.rail { margin-top: 22px; overflow-x: auto; padding-bottom: 10px; }
.cols {
  display: grid; grid-auto-flow: column; grid-auto-columns: minmax(260px, 1fr);
  gap: 14px; align-items: start;
}
.col {
  background: var(--surface); border: 1px solid var(--line); border-radius: 10px;
  min-width: 260px; overflow: hidden;
}
.col h2 {
  font-family: var(--display); font-size: 14px; font-weight: 600; margin: 0;
  padding: 10px 12px; letter-spacing: .02em; text-transform: lowercase;
  display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
  border-bottom: 1px solid var(--line); background: var(--surface-2);
}
.col h2 .n {
  font-family: var(--mono); font-size: 12px; font-weight: 400; color: var(--ink-2);
  font-variant-numeric: tabular-nums;
}
.col.needs-you h2 { color: var(--crit); }
.col.needs-you h2 .n { color: var(--crit); }
.col.running h2 { color: var(--now); }
.col.ready h2 { color: var(--ok); }
.col.waiting h2, .col.done h2, .col.parked h2 { color: var(--ink-2); }
.empty { margin: 0; padding: 12px; color: var(--ink-3); font-size: 13px; }
.card { padding: 11px 12px 12px; border-left: 3px solid transparent; }
.card + .card { border-top: 1px solid var(--line); }
.card.crit { border-left-color: var(--crit); }
.card.compact { padding: 8px 12px; }
.card p { margin: 0; }
.card .name { font-family: var(--display); font-size: 15px; font-weight: 600; }
.card .name .wl { text-decoration: none; color: var(--accent-ink); }
.card .name .wl:hover { text-decoration: underline; }
.chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 5px; }
.chip {
  font-family: var(--mono); font-size: 10.5px; letter-spacing: .02em;
  padding: 2px 6px; border-radius: 4px; background: var(--surface-2);
  color: var(--ink-2); white-space: nowrap;
}
.chip.lane { background: var(--accent-bg); color: var(--accent-ink); }
.chip.crit { background: var(--crit-bg); color: var(--crit); }
.chip.warn { background: var(--warn-bg); color: var(--warn); }
.chip.ok { background: var(--ok-bg); color: var(--ok); }
.chip.study { background: var(--now-bg); color: var(--now); }
.card .pr { display: flex; flex-wrap: wrap; gap: 4px; align-items: baseline; margin-top: 7px; }
.card .pr .pr { font-family: var(--mono); font-size: 12px; color: var(--accent-ink); }
.card .title { color: var(--ink-2); font-size: 12.5px; margin-top: 2px; }
.card .next { margin-top: 8px; font-size: 13.5px; }
.card .next .verb {
  font-family: var(--mono); font-size: 11px; text-transform: uppercase;
  letter-spacing: .06em; color: var(--ink-2); margin-right: 4px;
}
.card .cmd { margin-top: 5px; }
.card .hand, .card .sess, .card .meta {
  margin-top: 6px; font-size: 12.5px; color: var(--ink-2);
}
.card .lbl {
  font-family: var(--mono); font-size: 10.5px; text-transform: uppercase;
  letter-spacing: .06em; color: var(--ink-3); margin-right: 4px;
}
.card .why { margin-top: 5px; font-size: 13px; color: var(--ink-2); }
.card .shots {
  display: flex; flex-wrap: wrap; align-items: center; gap: 5px; margin-top: 8px;
}
.card .shots img {
  width: 74px; height: 52px; object-fit: cover; border-radius: 4px;
  border: 1px solid var(--line); background: var(--surface-2); display: block;
}
.card .shots .more {
  font-family: var(--mono); font-size: 10.5px; color: var(--ink-3);
  align-self: flex-end; padding-bottom: 2px;
}
.card .links { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 8px; }
.card .links a, .card .links span {
  font-size: 12px; color: var(--ink-2); text-decoration: none;
  border-bottom: 1px solid var(--line);
}
.card .links a:hover { color: var(--accent-ink); border-bottom-color: var(--accent); }
.how {
  margin-top: 24px; padding: 12px 14px; border-radius: 10px;
  background: var(--accent-bg); color: var(--accent-ink); font-size: 13px;
}
.how p { margin: 0; }
.how p + p { margin-top: 5px; }
.how code { background: transparent; padding: 0; }
@media (max-width: 700px) {
  .cols { grid-auto-flow: row; grid-auto-columns: auto; }
  .col { min-width: 0; }
}
"""


def compose_board(ctx: Any) -> str:
    """The whole page, with ``render.STAMP_HM`` still a placeholder."""
    out: List[str] = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>moose factory board</title>",
        "<style>" + CSS + "</style>",
        "</head>",
        "<body>",
        '<div class="page">',
        masthead(ctx),
        '<div class="rail">',
        '<div class="cols">',
    ]
    for posture in COLUMNS:
        out.append(column(posture, ctx))
    out.append("</div>")
    out.append("</div>")
    out.append(
        '<div class="how"><p><strong>How to act on this page.</strong> A card name opens its '
        "note in Obsidian. A command is copyable. This page is generated: "
        "<code>factory board</code> rewrites it and every edit here is lost.</p>"
        "<p>One next move: <code>factory next &lt;feature&gt;</code>. "
        "What is misconfigured: <code>factory doctor</code>.</p></div>"
    )
    out.append("</div>")
    out.append("</body>")
    out.append("</html>")
    return "\n".join(out) + "\n"


def write_board(ctx: Any) -> str:
    """``written``, ``skipped`` or ``dry-run``. Same discipline as a note."""
    cfg = ctx.config
    path = board_path(cfg)
    render.guard_path(cfg, path)
    text = compose_board(ctx)
    dg = snapshot.digest(text)
    stamp = ctx.state.stamp(STAMP_KEY, dg, ctx.now) if ctx.state is not None else ctx.now
    final = text.replace(render.STAMP_HM, render.ymd_hm(stamp)).replace(render.STAMP, stamp)
    status = render.atomic_write(path, final, ctx.dry_run)
    if ctx.stamps is not None:
        ctx.stamps[STAMP_KEY] = (dg, stamp)
    return status


# --------------------------------------------------------------------------
# Hooks
# --------------------------------------------------------------------------


def outputs(ctx: Any) -> Dict[str, Any]:
    """Called by ``render.sync`` once per ``factory board``."""
    try:
        status = write_board(ctx)
    except Exception as exc:
        # RefusedWrite included, and deliberately not re-raised: render.sync
        # catches that one, logs it and continues without counting it, so a
        # page the path guard refused would leave `factory board` at exit 0
        # claiming "refused 0" while the stale page stayed on disk. Reporting
        # it as refused here is what reaches the documented exit code 2.
        ctx.log("Board.html was not written: %s" % (exc,))
        return {"counts": {}, "refused": [BOARD_NAME]}
    return {"counts": {status: 1}, "refused": []}


def doctor_checks(ctx: Any) -> List[Tuple[str, bool, str]]:
    """``ctx`` here carries only config, paths and ``now``."""
    cfg = ctx.config
    out: List[Tuple[str, bool, str]] = []
    path = board_path(cfg)
    out.append(
        (
            "Board.html is in the vault",
            path.is_file(),
            "run `factory board`; the page is generated on every run",
        )
    )
    # The reader is ours, not a community release. `manifest.json` is committed and
    # is the record that the plugin is expected; `main.js` is gitignored like any
    # plugin code, so this row is the only thing in git that names it. Say enough
    # here to rebuild it: the whole plugin points an iframe at
    # `vault.getResourcePath(file)`, which is why the board's one relative
    # `Gallery/<feature>/<file>` src resolves with no injected `<base href>`.
    plugin_dir = Path(cfg.vault) / ".obsidian" / "plugins" / BOARD_READER_ID
    has_source = (plugin_dir / "main.js").is_file()
    has_manifest = (plugin_dir / "manifest.json").is_file()
    enabled = False
    data, ok = probe._read_json(Path(cfg.vault) / ".obsidian" / "community-plugins.json")
    if ok and isinstance(data, list):
        enabled = BOARD_READER_ID in data
    out.append(
        (
            f"{BOARD_READER_ID} present and listed",
            has_source and has_manifest and enabled,
            f"the board reader is ours. `main.js` is gitignored on purpose, so a "
            f"fresh clone has the manifest and not the code. Write "
            f".obsidian/plugins/{BOARD_READER_ID}/main.js: a FileView whose "
            f"canAcceptExtension takes 'html', registered with "
            f"registerExtensions(['html'], ...), whose onLoadFile points an "
            f"iframe src at this.app.vault.getResourcePath(file) with "
            f"sandbox='allow-same-origin'. Obsidian also needs Restricted mode "
            f"off, which it keeps in its own localStorage, not in the vault. "
            f"Board.html opens in any browser without this",
        )
    )
    return out
