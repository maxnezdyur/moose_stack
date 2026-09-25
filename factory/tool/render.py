"""The renderer: four-marker fencing, atomic writes, Home.md and Features.base.

Rules, in order:

1. If the note exists and any of the four markers is missing, write nothing,
   print one line to stderr and flag the card ``marker-missing``. A loud no-op
   beats silent prose loss. ``factory board`` then exits 2.
2. The gate checkboxes in the head block are read back **before** composing, so
   a tick granted ten seconds ago survives this run. (``cli`` does that through
   ``gates.sync``, which runs between the probe round and derive.)
3. Compose the head block and the body block. The head block is small: its
   churn budget is 520 bytes, because its length decides whether Obsidian's
   diff-match-patch merge still finds the human text.
4. Preserve the region between ``head:end`` and ``body:begin`` byte for byte.
5. If the composed bytes equal the bytes on disk, skip the write.
6. Otherwise write through ``mkstemp`` in the same directory plus ``os.replace``.
7. A new note gets all four markers and an empty ``## Notes``.

The human section sits above the large generated block on purpose: Obsidian's
merge into an open unsaved buffer fails silently once the bytes before the human
text change by more than about 520 in one run.

No timestamp in a generated file is read from the clock. Every stamp is a
content stamp from ``snapshot.Store.stamp``, which is what makes "delete every
generated note, re-run, get byte-identical files" true.
"""

from __future__ import annotations

import json
import os
import pkgutil
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config, derive, probe
from .model import (
    DONE,
    GATES,
    GATE_BLURB,
    GRANTED,
    NEEDS_YOU,
    PARKED,
    POSTURE,
    READY,
    RUNNING,
    WAITING,
    FeatureCard,
)

HEAD_BEGIN, HEAD_END, BODY_BEGIN, BODY_END = probe.MARKERS
STAMP = "@@STAMP@@"
STAMP_HM = "@@STAMP_HM@@"

_GLYPH_CACHE: Optional[Dict[str, Any]] = None


def glyphs(cfg: config.Config) -> Dict[str, Any]:
    """Every marker string the renderer prints, so the .py stays 7-bit ASCII."""
    global _GLYPH_CACHE
    if _GLYPH_CACHE is None:
        data, ok = probe._read_json(cfg.repo_root / "factory" / "glyphs.json")
        _GLYPH_CACHE = data if (ok and isinstance(data, dict)) else {}
    return _GLYPH_CACHE


def g(cfg: config.Config, key: str, default: str = "") -> str:
    return str(glyphs(cfg).get(key, default))


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def cell(text: Any) -> str:
    """Sanitize free text for a GFM table cell."""
    return (
        str("" if text is None else text)
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def file_uri(path: Any) -> str:
    return "file://" + urllib.parse.quote(str(path))


def tilde(path: Any) -> str:
    """A path with ``$HOME`` collapsed back to ``~``. One implementation, in config."""
    return config.display_path(path)


def hhmm(stamp: str) -> str:
    return stamp[11:16] if len(stamp) >= 16 else stamp


def ymd_hm(stamp: str) -> str:
    return (stamp[:10] + " " + stamp[11:16]) if len(stamp) >= 16 else stamp


def _minutes_between(then: Any, now: Any) -> Optional[int]:
    """Whole minutes between two ISO stamps, or None. No clock is read."""
    a, b = derive.ts_of(str(then or "")), derive.ts_of(str(now or ""))
    if a is None or b is None:
        return None
    return int(max(0.0, b - a) // 60)


def atomic_write(path: Path, text: str, dry_run: bool = False) -> str:
    """``skipped`` when the bytes already match, else ``written``."""
    data = text.encode("utf-8")
    try:
        if path.read_bytes() == data:
            return "skipped"
    except FileNotFoundError:
        pass
    except Exception:
        pass
    if dry_run:
        return "dry-run"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        # mkstemp creates 0600; a vault note is ordinary content.
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return "written"


def guard_path(cfg: config.Config, path: Path) -> None:
    """Refuse every write under Artifacts/, .factory/gates/ or .factory/timeline/.

    Those three hold inputs. A generator that can overwrite its own inputs has
    no delete-and-rebuild guarantee.
    """
    # realpath, not resolve(): it follows the existing prefix of a path that does
    # not exist yet, so /var and /private/var compare equal on macOS.
    target = Path(os.path.realpath(str(path)))
    for protected in cfg.protected_dirs():
        try:
            target.relative_to(Path(os.path.realpath(str(protected))))
        except Exception:
            continue
        raise config.RefusedWrite(
            "refused: %s is an input (under %s), not an output" % (path, protected.name)
        )


# --------------------------------------------------------------------------
# Extension discovery
# --------------------------------------------------------------------------


def extensions() -> List[Any]:
    """``tool/ext_<name>.py``, auto-discovered, sorted by name.

    An extension may export any of::

        VERBS        dict[str, Callable[[list[str], Ctx], int]]
        HELP         dict[str, str]
        NO_CTX_VERBS tuple[str, ...]   verbs that need no probe round
        card_flags(card, obs, ctx)  -> list[str]
        home_sections(ctx)          -> list[(title, markdown, order)]
        note_sections(card, ctx)    -> list[(title, markdown, order)]
        doctor_checks(ctx)          -> list[(name, ok, hint)]
        collect(ctx)                -> None   during the probe round
        outputs(ctx)                -> dict   {"counts": {...}, "refused": [...]}
        board_cards(ctx)            -> list   first-class cards that are not
                                              features (model.BoardCard: id,
                                              kind, posture, next_action, flags,
                                              why, note_folder)
        find_card(ctx, id)          -> BoardCard or None, for `next` and `status`
        NOTE_FOLDER  str            the vault folder its cards' notes live in

    ``outputs`` is called by :func:`sync` before ``Features.base`` and
    ``Home.md``, so an extension's own generated notes are written by the
    renderer and a refused note reaches the board's exit code.
    """
    import importlib

    import tool

    found = []
    for mod in sorted(pkgutil.iter_modules(tool.__path__), key=lambda m: m.name):
        if not mod.name.startswith("ext_"):
            continue
        try:
            found.append(importlib.import_module("tool." + mod.name))
        except Exception:
            continue
    return found


def ext_sections(ctx: Any, hook: str, *args: Any) -> List[Tuple[str, str, int]]:
    out: List[Tuple[str, str, int]] = []
    for mod in extensions():
        fn = getattr(mod, hook, None)
        if fn is None:
            continue
        try:
            rows = fn(*args) or []
        except Exception as exc:
            ctx.log("extension %s.%s raised: %s" % (mod.__name__, hook, exc))
            continue
        for row in rows:
            if isinstance(row, tuple) and len(row) == 3:
                out.append(row)
    out.sort(key=lambda r: (r[2], r[0]))
    return out


def board_cards(ctx: Any) -> List[Any]:
    """Every extension card, from each extension's ``board_cards(ctx)``.

    Merged by :func:`compose_home` and ``ext_board_html`` into the six posture
    groups next to the feature cards. One extension that raises costs only its
    own cards, and one line in the log.
    """
    out: List[Any] = []
    for mod in extensions():
        fn = getattr(mod, "board_cards", None)
        if fn is None:
            continue
        try:
            rows = fn(ctx) or []
        except Exception as exc:
            ctx.log("extension %s.board_cards raised: %s" % (mod.__name__, exc))
            continue
        for row in rows:
            if getattr(row, "id", None) and getattr(row, "posture", None) in POSTURE:
                out.append(row)
    return out


def find_card(ctx: Any, card_id: str) -> Any:
    """A feature card, else the first extension card with this id, else None."""
    card = ctx.card(card_id) if hasattr(ctx, "card") else None
    if card is not None:
        return card
    for mod in extensions():
        fn = getattr(mod, "find_card", None)
        if fn is None:
            continue
        try:
            row = fn(ctx, card_id)
        except Exception as exc:
            ctx.log("extension %s.find_card raised: %s" % (mod.__name__, exc))
            continue
        if row is not None:
            return row
    return None


def note_candidates(cfg: Any, card_id: str) -> List[Path]:
    """Where a card's note may live: ``Features/`` first, then each
    extension's ``NOTE_FOLDER``. No probe round, so ``factory status`` stays
    cheap."""
    out = [cfg.note_path(card_id)]
    for mod in extensions():
        folder = getattr(mod, "NOTE_FOLDER", None)
        if folder:
            out.append(Path(cfg.vault) / str(folder) / (config.validate_id(card_id) + ".md"))
    return out


def is_feature(card: Any) -> bool:
    return isinstance(card, FeatureCard)


# --------------------------------------------------------------------------
# The feature note
# --------------------------------------------------------------------------


def frontmatter(card: FeatureCard, ctx: Any) -> str:
    pr = card.primary_pr()
    lines = [
        "---",
        "feature: %s" % (card.id,),
        "lane: %s" % (card.lane,),
        "posture: %s" % (card.posture,),
        "flags: [%s]" % (", ".join(card.flags),),
        "provenance: %s" % (card.provenance,),
        "worktree: %s" % (card.worktree or "none",),
    ]
    if pr:
        lines += [
            "repo: %s" % (pr.get("repo") or "",),
            "pr: %s" % (pr.get("number"),),
            "pr_state: %s" % ("draft" if pr.get("isDraft") else (pr.get("state") or "").lower(),),
            "ci: %s" % (pr.get("ci") or "unknown",),
            "review: %s" % (pr.get("reviewDecision") or "none",),
            "mergeable: %s" % (pr.get("mergeable") or "UNKNOWN",),
        ]
    lines.append("session: %s" % ((card.session or {}).get("name") or "none",))
    lines.append("builds: %s" % (1 if card.build else 0,))
    for gate in GATES:
        lines.append("gate_%s: %s" % (gate, card.gate_state(gate)))
    lines += ["updated: %s" % (STAMP,), "tags: [factory-feature]", "---"]
    return "\n".join(lines)


def head_block(card: FeatureCard, ctx: Any) -> str:
    """Small by budget. One status line, one next move, the four gate boxes."""
    cfg = ctx.config
    pr = card.primary_pr()
    bits = ["[[Home]]", "**%s**" % (card.lane,)]
    if pr:
        bits.append(
            "PR [#%s](%s) %s"
            % (
                pr.get("number"),
                pr.get("url") or "",
                "draft" if pr.get("isDraft") else (pr.get("state") or "").lower(),
            )
        )
        if pr.get("ci"):
            bits.append("CIVET %s" % (pr["ci"],))
        if pr.get("mergeable") == "CONFLICTING":
            bits.append("CONFLICTING")
    if card.posture == NEEDS_YOU:
        bits.append("needs you")
    out = [" - ".join(bits), ""]

    na = card.next_action
    out.append("> **Next:** %s" % (na.why or na.verb,))
    if na.command:
        out.append("> `%s`" % (na.command,))
    out.append("")
    out.append("## Gates")
    out.append("")
    out.append("_Tick to grant. Read back next run. Never ungranted._")
    out.append("")
    for gate in GATES:
        rec = card.gates.get(gate) or {}
        if rec.get("state") == GRANTED:
            when = str(rec.get("when") or "")[:10]
            out.append(
                "- [x] %s - granted %s by %s, via %s"
                % (gate, when, rec.get("by") or "max", rec.get("via") or "verb")
            )
        else:
            blurb = GATE_BLURB[gate]
            if gate == "blueprint_approved" and (card.blueprint or {}).get("kind") != "markdown":
                # Say why it is not due. Ticking it approves nothing.
                blurb = "no `specs/blueprint.md` to approve"
            out.append("- [ ] %s - %s" % (gate, blurb))
    return "\n".join(out)


def _repo_table(card: FeatureCard) -> List[str]:
    rows = [
        "| repo | branch | pushed | ahead of base | dirty | fetched |",
        "|---|---|---|---|---|---|",
    ]
    for repo in config.REPOS:
        st = card.repos.get(repo)
        if st is None:
            continue
        rows.append(
            "| %s | %s | %s | %s | %s | %s |"
            % (
                repo,
                cell(st.get("branch") or "detached"),
                "yes" if st.get("pushed") else ("no" if st.get("pushed") is False else "unknown"),
                st.get("ahead") if st.get("ahead") is not None else "unknown",
                st.get("dirty") if st.get("dirty") is not None else "unknown",
                st.get("fetched") or "unknown",
            )
        )
    return rows


def vault_name(ctx: Any) -> str:
    """The Obsidian vault name for an ``obsidian://open?vault=`` link.

    The config lets the vault name differ from the directory name, and a test
    double may carry neither, so this falls back to the directory basename and
    then to the packaged default.
    """
    cfg = getattr(ctx, "config", None)
    name = getattr(cfg, "obsidian_vault", "") if cfg is not None else ""
    if name:
        return str(name)
    vault = getattr(cfg, "vault", "") if cfg is not None else ""
    return Path(vault).name if vault else config.DEFAULT_VAULT_DIRNAME


def body_block(card: FeatureCard, ctx: Any) -> str:
    cfg = ctx.config
    out: List[str] = []
    wt = card.worktree

    out.append("## Open the workspace")
    out.append("")
    if wt:
        ws = []
        for name in (card.id + ".code-workspace", "moose_stack.code-workspace"):
            p = Path(wt) / name
            if p.is_file():
                label = "this feature" if name.startswith(card.id) else "whole stack"
                ws.append("- %s: [%s](%s)" % (label, name, file_uri(p)))
        out.extend(ws or ["- no `.code-workspace` in the worktree"])
        bp = card.blueprint or {}
        if bp.get("path"):
            kind = "generated view only" if bp.get("kind") == "view-only" else "the plan"
            out.append(
                "- Plan: [%s](%s) (%s)"
                % (Path(bp["path"]).name, file_uri(bp["path"]), kind)
            )
        out.append("- Vault: `obsidian://open?vault=%s&file=%s`"
                   % (urllib.parse.quote(vault_name(ctx), safe=""),
                      urllib.parse.quote("Features/" + card.id)))
    else:
        out.append("- no worktree. This card is a %s." % (card.provenance,))
    for pr in card.prs:
        out.append(
            "- PR %s #%s (%s): %s"
            % (
                pr.get("repo"),
                pr.get("number"),
                "draft" if pr.get("isDraft") else (pr.get("state") or "").lower(),
                pr.get("url") or "",
            )
        )
    out.append("")
    out.append("```")
    if wt:
        ws_file = Path(wt) / (card.id + ".code-workspace")
        if ws_file.is_file():
            out.append("code %s" % (tilde(ws_file),))
        if card.next_action.command:
            out.append(card.next_action.command)
        out.append(
            "cd %s && claude --bg --name %s \"/moose-build\"" % (tilde(wt), card.id)
        )
    else:
        out.append(card.next_action.command or "# nothing to run: there is no worktree")
    out.append("```")
    out.append("")

    sk = (ctx.obs.get(card.id) or {}).get("skills") or {}
    if sk and sk.get("has_ship") is False:
        out.append(
            "Warning: this worktree's `.claude/skills` has no `moose-ship`. The pipeline was "
            "frozen when the worktree was created: %d skills, and `%s` is not among them. "
            "Run `factory refresh-pipeline %s`, or ship from the canonical checkout."
            % (len(sk.get("names") or []), "moose-ship", card.id)
        )
        out.append("")

    out.append("## Where it stands")
    out.append("")
    if card.repos:
        out.extend(_repo_table(card))
        out.append("")
        out.append(
            "_Base: `%s` for each submodule, `%s` for the meta-repo. `origin/devel` is "
            "months stale and would report hundreds instead of one._"
            % (config.UPSTREAM_REF, config.META_BASE_REF)
        )
    else:
        out.append("_No checkout. Every fact below comes from GitHub._")
    out.append("")

    bp = card.blueprint or {}
    if not bp:
        out.append("- Blueprint: **absent**")
    elif bp.get("kind") == "view-only":
        out.append(
            "- Blueprint: **absent** (`%s` survives from %s, title %r)"
            % (Path(bp["path"]).name, probe.day(bp.get("mtime")), bp.get("title") or "")
        )
    else:
        out.append(
            "- Blueprint: **%s** (`%s`, %s unticked clarifications, work plan %s)"
            % (
                bp.get("status") or "no status",
                tilde(bp.get("path")),
                bp.get("unticked"),
                "parses" if bp.get("work_plan_ok") else (bp.get("work_plan_error") or "missing"),
            )
        )
    build = card.build or {}
    if build:
        out.append(
            "- Last `/moose-build`: **%s** (%s, %s)"
            % (build.get("status") or "unknown", build.get("label"), probe.day(build.get("mtime")))
        )
        if build.get("summary"):
            out.append("  - %s" % (cell(build["summary"])[:200],))
    else:
        out.append("- Last `/moose-build`: **no record** in the worktree or in `Artifacts/`")
    reviews = (ctx.obs.get(card.id) or {}).get("reviews") or []
    out.append(
        "- Reviews archived: %s%s"
        % (len(reviews), (" (" + ", ".join(reviews) + ")") if reviews else "")
    )
    sessions = (ctx.obs.get(card.id) or {}).get("sessions") or []
    if sessions:
        for row in sessions:
            out.append(
                "- Live session `%s` (%s): %s. Attach: `%s attach %s`"
                % (
                    row.get("name") or row.get("sessionId"),
                    row.get("kind"),
                    cell(row.get("detail") or row.get("status") or "unknown"),
                    config.claude_display(getattr(ctx, "config", None)),
                    row.get("bg_id") or (row.get("sessionId") or "").split("-")[0],
                )
            )
    else:
        out.append("- Live sessions with cwd at or under this worktree: none")
    out.append("")

    pr = card.primary_pr()
    if pr and pr.get("ci"):
        out.append("## CIVET")
        out.append("")
        failing = pr.get("failing") or []
        if failing:
            shown = failing[:6]
            line = "FAILURE or ERROR (%d): " % (len(failing),) + ", ".join(
                "[%s](%s)" % (cell(f.get("name")), f.get("url") or "") for f in shown
            )
            if len(failing) > len(shown):
                line += ", and %d more" % (len(failing) - len(shown),)
            out.append(line)
        else:
            out.append("Rollup: **%s**" % (pr["ci"],))
        fresh = derive.rollup_applies(pr, ctx.obs.get(card.id) or {})
        mergeable = pr.get("mergeable") or "UNKNOWN"
        if pr.get("mergeable_unknown") or mergeable == "UNKNOWN":
            verdict = "Mergeability is **not yet computed** (GitHub answered UNKNOWN twice)."
        else:
            verdict = "Mergeable: **%s**." % (mergeable,)
        out.append(
            "%s The rollup is for `headRefOid` %s, which is %s."
            % (
                verdict,
                (pr.get("headRefOid") or "unknown")[:7],
                "the current head" if fresh else "an older head, so no colour was taken from it",
            )
        )
        out.append("")

    if card.flags:
        out.append("## Flags")
        out.append("")
        from .model import FLAG_WHY

        for flag in card.flags:
            out.append("- `%s` - %s" % (flag, FLAG_WHY.get(flag, "")))
        out.append("")

    for title, text, _order in ext_sections(ctx, "note_sections", card, ctx):
        out.append("## %s" % (title,))
        out.append("")
        out.append(text.rstrip())
        out.append("")

    annotations = (ctx.state.read(card.id) or {}).get("set") if ctx.state else None
    if annotations:
        out.append("## Annotations")
        out.append("")
        out.append("_Recorded by hand with `factory set`. The projector reads them, never writes them._")
        out.append("")
        for key in sorted(annotations):
            out.append("- `%s` = %s" % (key, cell(annotations[key])))
        out.append("")

    rows = ctx.timeline.read(card.id) if ctx.timeline else []
    out.append("## Timeline")
    out.append("")
    if rows:
        for rec in rows[-12:]:
            out.append(
                "- %s %s%s"
                % (
                    str(rec.get("at") or "")[:16].replace("T", " "),
                    cell(rec.get("event") or ""),
                    (" - " + cell(rec.get("why") or rec.get("gate") or rec.get("cause") or ""))
                    if (rec.get("why") or rec.get("gate") or rec.get("cause"))
                    else "",
                )
            )
    else:
        out.append("_Nothing recorded yet._")
    return "\n".join(out)


def compose_note(card: FeatureCard, ctx: Any, existing: Optional[str]) -> Tuple[str, str]:
    """Return ``(text_with_stamp_placeholder, human_region)``.

    Two human regions, not one. The region between ``head:end`` and
    ``body:begin`` is the ``## Notes`` section, and everything after
    ``body:end`` is the tail: a cursor at the end of the file lands there, so
    that is where an appended paragraph goes. Both are preserved byte for byte.
    Keeping only the first silently deleted the tail on the next board, with all
    four markers intact, so no refusal fired and nothing was logged.
    """
    human = "\n\n## Notes\n\n\n"
    tail = ""
    if existing and HEAD_END in existing and BODY_BEGIN in existing:
        human = existing.split(HEAD_END, 1)[1].split(BODY_BEGIN, 1)[0]
    if existing and BODY_END in existing:
        tail = existing.split(BODY_END, 1)[1]
        if not tail.strip():
            tail = ""
    text = "\n".join(
        [
            frontmatter(card, ctx),
            "# %s" % (card.id,),
            "",
            HEAD_BEGIN,
            head_block(card, ctx),
            HEAD_END,
        ]
    )
    text += human
    text += "\n".join([BODY_BEGIN, body_block(card, ctx), BODY_END])
    text += tail if tail else "\n"
    return (text, human)


def write_note(card: FeatureCard, ctx: Any) -> str:
    """``written``, ``skipped``, ``refused`` or ``dry-run``."""
    cfg = ctx.config
    path = cfg.note_path(card.id)
    guard_path(cfg, path)
    existing, ok = probe._read_text(path)
    if not ok:
        ctx.log("note %s is unreadable; not rewritten" % (path,))
        return "refused"
    if existing is not None:
        missing = [m for m in probe.MARKERS if m not in existing]
        if missing:
            ctx.log(
                "note %s is missing %s: not rewritten, card flagged marker-missing"
                % (path, ", ".join(missing))
            )
            return "refused"
    text, _human = compose_note(card, ctx, existing)
    from . import snapshot

    dg = snapshot.digest(text)
    stamp = ctx.state.stamp("Features/%s.md" % (card.id,), dg, ctx.now)
    final = text.replace(STAMP, stamp)
    status = atomic_write(path, final, ctx.dry_run)
    ctx.stamps["Features/%s.md" % (card.id,)] = (dg, stamp)
    head = final.split(HEAD_BEGIN, 1)[1].split(HEAD_END, 1)[0]
    budget = getattr(cfg, "head_churn_budget", config.HEAD_CHURN_BUDGET)
    if len(head.encode("utf-8")) > budget * 3:
        ctx.log(
            "head block of %s is %d bytes: Obsidian's merge budget is about %d per run"
            % (card.id, len(head.encode("utf-8")), budget)
        )
    return status


# --------------------------------------------------------------------------
# Home.md
# --------------------------------------------------------------------------


def _needs_you_rows(cards: List[Any]) -> List[str]:
    rows = ["| card | next move | why |", "|---|---|---|"]
    for c in cards:
        rows.append(
            "| [[%s]] | `%s` | %s |"
            % (c.id, cell(c.next_action.command or c.next_action.verb), cell(c.next_action.why))
        )
    return rows


def _running_rows(cards: List[Any], now: str) -> List[str]:
    rows = [
        "| card | state | for | last thing it said | take over |",
        "|---|---|---|---|---|",
    ]
    for c in cards:
        if not is_feature(c):
            # An extension card carries no session record of its own: its why
            # says what runs, and its command is how to take it over.
            rows.append(
                "| [[%s]] | %s | %s | %s | `%s` |"
                % (
                    c.id,
                    cell(getattr(c, "kind", "") or "running"),
                    "-",
                    cell(c.next_action.why)[:80],
                    cell(c.next_action.command or c.next_action.verb),
                )
            )
            continue
        s = c.session or {}
        last = (s.get("last_line") or {}).get("detail") or s.get("detail") or ""
        bg = s.get("bg_id") or (s.get("sessionId") or "").split("-")[0]
        # waitingFor first: a session blocked on a permission prompt reads as
        # "busy" without it, which is the one state that needs a human.
        state = (
            s.get("waitingFor")
            or s.get("needs")
            or s.get("state")
            or s.get("status")
            or "unknown"
        )
        if s.get("waitingFor"):
            state = "waiting: %s" % (state,)
        rows.append(
            "| [[%s]] | %s | %s | %s | `claude attach %s` |"
            % (
                c.id,
                cell(state),
                _age(s.get("startedAt"), now),
                cell(last)[:80],
                bg,
            )
        )
    return rows


def _backlog_reason(card: Any, cfg: Any) -> str:
    if is_feature(card):
        return derive.backlog_reason(card, cfg)
    return ", ".join(str(f) for f in (getattr(card, "flags", None) or [])[:2]) or card.next_action.verb


def _age(started: Any, now: Any) -> str:
    """How long this session has been up, from its own stamp against ctx.now."""
    mins = _minutes_between(started, now)
    if mins is None:
        return "unknown"
    if mins < 60:
        return "%dm" % (mins,)
    return "%dh%02dm" % (mins // 60, mins % 60)


def compose_home(ctx: Any) -> str:
    cfg = ctx.config
    cards = ctx.cards
    meta = ctx.meta
    extra = board_cards(ctx)
    groups = {p: [c for c in list(cards) + extra if c.posture == p] for p in POSTURE}
    kinds: Dict[str, int] = {}
    for c in extra:
        kind = str(getattr(c, "kind", "") or "card")
        kinds[kind] = kinds.get(kind, 0) + 1

    open_prs = sum(len(c.open_prs()) for c in cards)
    worktrees = len([c for c in cards if c.worktree])
    fetched = sorted(
        st.get("fetched")
        for c in cards
        for st in c.repos.values()
        if st.get("fetched")
    )
    mismatch = len([c for c in cards if c.has("branch-mismatch")])

    out: List[str] = [
        "---",
        "updated: %s" % (STAMP,),
        "features: %d" % (len(cards),),
        "campaigns: %d" % (kinds.get("campaign", 0),),
    ]
    for p in POSTURE:
        out.append("%s: %d" % (p.replace("-", "_"), len(groups[p])))
    out += ["tags: [factory-home]", "---", "# moose factory", ""]

    kinds_text = "".join(
        "%d %s%s, " % (n, kind, "" if n == 1 else "s") for kind, n in sorted(kinds.items())
    )
    masthead = [
        "_%d features, %s%d workspaces, %d open PRs."
        % (len(cards), kinds_text, worktrees, open_prs),
        "Regenerated by `factory board`. This picture was established %s;" % (STAMP_HM,),
        "a stamp moves only when the content under it moves.",
    ]
    if fetched:
        masthead.append(
            "Upstream refs fetched %s to %s." % (fetched[0], fetched[-1])
        )
    if meta.get("stale_pipeline"):
        masthead.append(
            "%d worktrees carry a stale pipeline." % (meta["stale_pipeline"],)
        )
    if mismatch:
        masthead.append("%d carry a branch mismatch." % (mismatch,))
    # How old the picture is, without a fact that moves on its own. A healthy
    # GitHub payload is bounded by the cache TTL, and that bound is a constant;
    # printing its timestamp instead made Home.md differ on every cache refresh,
    # so the tick committed a board whose only change was the time it ran. An
    # unknown probe does carry a stamp, and it is frozen while the probe is down,
    # which is exactly when the reader needs it.
    gh_as_of = meta.get("gh_as_of")
    sess_as_of = meta.get("sessions_as_of")
    parts: List[str] = []
    if "github" in (meta.get("stale") or []):
        parts.append(
            "GitHub as of %s, carried forward and unknown since."
            % (hhmm(gh_as_of) if gh_as_of else "unknown",)
        )
    elif gh_as_of:
        parts.append(
            "GitHub is at most %d minutes old." % (max(1, int(cfg.gh_cache_ttl // 60)),)
        )
    if sess_as_of:
        parts.append("Sessions as of %s." % (hhmm(sess_as_of),))
    if parts:
        masthead.append(" ".join(parts))
    if meta.get("stale"):
        masthead.append(
            "Unknown this run: %s (last good values carried forward)."
            % (", ".join(meta["stale"]),)
        )
    if meta.get("recovered"):
        masthead.append(
            "%d cards came back from the last good snapshot: %s."
            % (len(meta["recovered"]), ", ".join(sorted(meta["recovered"])))
        )
    out.append("\n".join(masthead).rstrip() + "_")
    out.append("")

    # --- needs you, capped and ordered ------------------------------------
    ny = sorted(groups[NEEDS_YOU], key=lambda c: c.priority_key())
    shown, rest = ny[: cfg.needs_you_cap], ny[cfg.needs_you_cap:]
    out.append(
        "## Needs you (%s)"
        % ("%d of %d" % (len(shown), len(ny)) if rest else str(len(ny)),)
    )
    out.append("")
    if shown:
        out.extend(_needs_you_rows(shown))
    else:
        out.append("_Nothing needs you. Read this line twice._")
    out.append("")
    if rest:
        out.append(
            "_Backlog, triage once: %s._"
            % (
                ", ".join("[[%s]] (%s)" % (c.id, _backlog_reason(c, cfg)) for c in rest),
            )
        )
        out.append("")

    # --- running -----------------------------------------------------------
    out.append("## Running (%d)" % (len(groups[RUNNING]),))
    out.append("")
    if groups[RUNNING]:
        out.extend(_running_rows(sorted(groups[RUNNING], key=lambda c: c.id), ctx.now))
    else:
        out.append("_No live session in any worktree._")
    out.append("")

    out.append("## Ready (%d)" % (len(groups[READY]),))
    out.append("")
    if groups[READY]:
        for c in sorted(groups[READY], key=lambda c: c.id):
            out.append(
                "- [[%s]] - %s - `%s`" % (c.id, cell(c.next_action.why), c.next_action.command)
            )
    else:
        out.append("_Nothing is built and waiting on a ship gate._")
    out.append("")

    for posture, empty in ((WAITING, "_Nothing is out for review._"), (PARKED, "_Nothing parked._")):
        out.append("## %s (%d)" % (posture.capitalize(), len(groups[posture])))
        out.append("")
        if groups[posture]:
            for c in sorted(groups[posture], key=lambda c: c.id):
                out.append("- [[%s]] - %s" % (c.id, cell(c.next_action.why)))
        else:
            out.append(empty)
        out.append("")

    if groups[DONE]:
        out.append("## Done (%d)" % (len(groups[DONE]),))
        out.append("")
        for c in sorted(groups[DONE], key=lambda c: c.id):
            out.append("- [[%s]] - %s" % (c.id, cell(c.next_action.why)))
        out.append("")

    ideas = meta.get("ideas") or {"matched": [], "unmatched": []}
    out.append(
        "## Ideas (%d matched, %d unmatched)"
        % (len(ideas["matched"]), len(ideas["unmatched"]))
    )
    out.append("")
    if ideas["unmatched"]:
        for row in ideas["unmatched"]:
            out.append("- [[%s]] - %s" % (row["slug"], cell(row["text"])))
    if ideas["matched"]:
        out.append(
            "_Matched, so already on the board: %s._"
            % (", ".join("[[%s]]" % (r["slug"],) for r in ideas["matched"]),)
        )
    if not ideas["matched"] and not ideas["unmatched"]:
        out.append("_from [[Ideas]]. Nothing unfiled._")
    out.append("")

    skipped = meta.get("skipped_prs") or []
    unsafe = meta.get("skipped") or []
    if skipped or unsafe:
        out.append(
            "_Ignored, not a safe slug: %s._"
            % (
                ", ".join(
                    ["%s #%s (`%s`)" % (r.get("repo"), r.get("number"), r.get("head")) for r in skipped]
                    + ["`%s`" % (tilde(p),) for p in unsafe]
                ),
            )
        )
        out.append("")

    for title, text, _order in ext_sections(ctx, "home_sections", ctx):
        out.append("## %s" % (title,))
        out.append("")
        out.append(text.rstrip())
        out.append("")

    archived = sorted(p.stem for p in cfg.archive_dir.glob("*.md")) if cfg.archive_dir.is_dir() else []
    out.append("## Archive")
    out.append("")
    out.append("- %d archived. See `Archive/`." % (len(archived),))
    out.append("")
    out.append("---")
    out.append(
        "_`%s board` regenerates this. Read it headless: `cat Home.md`.\n"
        "One next move: `factory next <feature>`. Start a build: `factory start <feature>`.\n"
        "What is misconfigured: `factory doctor`._"
        % (tilde(cfg.repo_root / "factory" / "factory"),)
    )
    return "\n".join(out) + "\n"


def write_home(ctx: Any) -> str:
    from . import snapshot

    cfg = ctx.config
    text = compose_home(ctx)
    dg = snapshot.digest(text)
    stamp = ctx.state.stamp("Home.md", dg, ctx.now)
    ctx.stamps["Home.md"] = (dg, stamp)
    guard_path(cfg, cfg.home_note)
    final = text.replace(STAMP_HM, ymd_hm(stamp)).replace(STAMP, stamp)
    return atomic_write(cfg.home_note, final, ctx.dry_run)


# --------------------------------------------------------------------------
# Features.base, written once if absent
# --------------------------------------------------------------------------

BASE = """filters:
  and:
    - file.inFolder("Features")
    - file.ext == "md"
properties:
  file.name:
    displayName: feature
  note.posture:
    displayName: posture
  note.lane:
    displayName: lane
  note.flags:
    displayName: flags
  note.pr:
    displayName: pr
  note.ci:
    displayName: ci
  note.mergeable:
    displayName: mergeable
  note.session:
    displayName: session
  note.updated:
    displayName: updated
views:
  - type: cards
    name: Board
    groupBy:
      property: posture
      direction: ASC
    order:
      - file.name
      - posture
      - lane
      - pr
      - ci
      - flags
      - updated
    sort:
      - property: posture
        direction: ASC
      - property: lane
        direction: DESC
  - type: table
    name: Needs you
    filters:
      and:
        - note.posture == "needs-you"
    order:
      - file.name
      - lane
      - pr
      - ci
      - mergeable
      - flags
  - type: table
    name: Open PRs
    filters:
      and:
        - note.pr
    order:
      - file.name
      - pr
      - ci
      - mergeable
      - posture
    sort:
      - property: pr
        direction: DESC
"""


def write_base(ctx: Any) -> str:
    """Written once when absent, never overwritten.

    Bases at app 1.13.7 registers exactly ``table``, ``cards`` and ``list``. A
    ``kanban`` view parses but renders "Unknown view type" before 1.14, so the
    Board view is a ``cards`` view grouped by posture: the closest native thing
    to a kanban, and the fallback for the generated ``Board.html``. The two
    table views stay, because a sortable grouped table answers questions a card
    grid cannot.

    Ownership: this file is a **seed**, and Obsidian owns it afterwards. Measured
    on this vault: Obsidian rewrote the seeded ``groupBy: note.posture`` scalar
    into a mapping with ``property: posture`` and ``direction: ASC``, and added
    a ``columnSize`` for a column Max had dragged. Both are Obsidian's truth and
    neither is recomputable, which is exactly why this function never
    overwrites. The groupBy above is therefore written in the shape Obsidian
    normalises to, so a fresh vault gives it no reason to rewrite.

    The delete-and-rebuild guarantee covers ``Home.md``, ``Features/*.md`` and
    ``Campaigns/*.md``. Delete this file too and you get a working seed back, not
    the same bytes: a dragged column width is not derivable from anything.
    """
    cfg = ctx.config
    if cfg.base_file.exists():
        return "skipped"
    if ctx.dry_run:
        return "dry-run"
    guard_path(cfg, cfg.base_file)
    return atomic_write(cfg.base_file, BASE, ctx.dry_run)


# --------------------------------------------------------------------------
# The whole vault
# --------------------------------------------------------------------------


def sync(ctx: Any) -> Dict[str, Any]:
    """Write every output. Returns a count per status plus the refused ids."""
    counts = {"written": 0, "skipped": 0, "refused": 0, "dry-run": 0}
    refused: List[str] = []
    for card in sorted(ctx.cards, key=lambda c: c.id):
        try:
            status = write_note(card, ctx)
        except config.RefusedWrite as exc:
            ctx.log(str(exc))
            status = "refused"
        counts[status] = counts.get(status, 0) + 1
        if status == "refused":
            refused.append(card.id)
            card.add_flag("marker-missing")
    for mod in extensions():
        fn = getattr(mod, "outputs", None)
        if fn is None:
            continue
        try:
            extra = fn(ctx) or {}
        except config.RefusedWrite as exc:
            ctx.log(str(exc))
            continue
        except Exception as exc:
            ctx.log("extension %s.outputs raised: %s" % (mod.__name__, exc))
            continue
        for key, value in (extra.get("counts") or {}).items():
            if isinstance(value, int):
                counts[key] = counts.get(key, 0) + value
        for item in extra.get("refused") or []:
            refused.append(str(item))
            counts["refused"] = counts.get("refused", 0) + 1
    # A note with no card is a hole in the delete-and-rebuild guarantee: the
    # board stops rewriting it, and the next acceptance test deletes a file no
    # rebuild can restore. Counted here, named by `factory doctor`.
    live = {c.id for c in ctx.cards}
    cfg = ctx.config
    orphans = (
        [n.stem for n in sorted(cfg.features_dir.glob("*.md")) if n.stem not in live]
        if cfg.features_dir.is_dir()
        else []
    )
    counts["orphan_notes"] = len(orphans)
    if orphans:
        ctx.log(
            "%d note(s) in Features/ have no card: %s. `factory archive <feature>`"
            % (len(orphans), ", ".join(orphans))
        )
    counts["base"] = write_base(ctx)
    counts["home"] = write_home(ctx)
    ctx.state.stamp_commit(ctx.stamps, ctx.dry_run)
    if not ctx.dry_run:
        _last_sync(ctx, counts)
    return {"counts": counts, "refused": refused}


def _last_sync(ctx: Any, counts: Dict[str, Any]) -> None:
    """The one generated file that carries wall-clock truth. Gitignored."""
    cfg = ctx.config
    hist = {p: len(ctx.by_posture(p)) for p in POSTURE}
    payload = {
        "at": probe.iso(),
        "probes": {"stale": ctx.meta.get("stale") or []},
        "counts": {k: v for k, v in counts.items() if isinstance(v, int)},
        "postures": hist,
        "cards": sorted(c.id for c in ctx.cards),
    }
    try:
        cfg.factory_dir.mkdir(parents=True, exist_ok=True)
        cfg.last_sync.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    except Exception:
        pass
