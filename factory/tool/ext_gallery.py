"""The gallery: what a session made for a human to look at.

``<worktree>/specs/gallery/`` holds anything a session produced that a person is
meant to *see*: a PNG from chigger, an SVG, a short MP4, a CSV, a small HTML
table. Big outputs stay where the example wrote them; the gallery is the
shortlist. ``gallery.md`` beside them is the figure page, and it is the source
of truth for what the gallery shows and in which order. One ``## `` section per
figure: the heading is the title, the first image embed in the section is the
file, and the prose below it says what the figure shows. ``captions.md`` is
retired. This module never reads one, and ``preserve`` still copies one so an
old index is not lost with its worktree.

This module does three things and writes exactly one kind of thing.

1. ``collect`` scans each card's gallery directory, reads ``gallery.md``, and
   records the listing in ``ctx.obs[<feature>]["gallery"]``: the figures in page
   order first, then every eligible file the page does not mention. It also maintains
   ``<vault>/Gallery/<feature>`` as a **symlink** to that directory, and
   :func:`sweep` then removes any dangling link under ``Gallery/`` that no card
   claimed, which is how a link outlives the feature that made it. Link, not
   copy: a copy would be a second writer of the same bytes, it would double the
   disk, and it would go stale the moment the session re-rendered a figure.
   Obsidian follows a symlink, so the feature note can embed
   ``![[Gallery/<feature>/<file>]]`` and ``Board.html`` can use the relative
   ``Gallery/<feature>/<file>`` as an ``img`` source.

2. ``note_sections`` renders ``## Gallery`` on the feature note, at order 45:
   between the handoff (40) and build-and-review (50), because a picture of the
   result belongs above the build log and below what the last session said.

3. ``preserve`` is what ``factory teardown`` calls before it removes anything.
   It copies the size-capped gallery into ``Artifacts/<feature>/gallery/`` and
   repoints the symlink at that copy. That is the only copy this design ever
   makes, and it exists because the worktree is about to stop existing.

Seven disciplines, each one a hole that would otherwise be open.

- **No symlink is followed when listing.** A gallery entry that is itself a
  symlink is skipped and reported, and the gallery directory must resolve
  inside the worktree. Otherwise a ``ln -s / specs/gallery/root`` in a worktree
  would walk the whole filesystem into the note and into the vault.
- **A name is validated before it is spelled anywhere.** A filename reaches a
  wikilink, an ``img src`` and a symlink path, so it must not carry ``[``,
  ``]``, ``|``, ``#``, ``/`` or a leading dot. A name that fails is skipped and
  reported, never quietly dropped.
- **Nothing here reads the clock.** Sizes and captions are content, so the note
  rebuilds byte for byte after a deletion, exactly like every other generated
  file in the vault.
- **Every projected string passes through :func:`_clip`**, which escapes
  ``<!--``. That means the page's headings, which are human prose, and equally
  the filenames printed on the refusal lines, which a session chooses and which no
  validator has passed by the time they are printed. A string that named one of
  the note's fence markers would otherwise plant a second fence in the generated
  body, and the note would grow by its own length on every board run.
- **A zero byte file is not a figure.** An interrupted render leaves the file
  and its page section behind; publishing it embeds a broken image under a
  title that claims it shows something. It is named and skipped, like a file
  over the cap.
- **The index is not an exhibit.** ``gallery.md`` and ``captions.md`` are both
  kept out of the listing by :data:`PAGE_SHAPED` and :data:`CAPTIONS_SHAPED`,
  numbered teardown siblings included. :func:`copy_captions` lands each of them
  on its own name rather than suffixing it, because exactly one path is read
  back, and a stale index there would title every rescued figure in silence.
- **A real directory at ``Gallery/<feature>`` is never removed.** It means
  somebody copied where the design links, and destroying their copy to make
  room for a link is not this module's call: it is a ``factory doctor`` row.
"""

from __future__ import annotations

import os
import re
import shutil
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config

#: Where the gallery lives inside a worktree, and where it is linked from.
GALLERY_REL = os.path.join("specs", "gallery")
GALLERY_DIRNAME = "Gallery"
CAPTIONS_NAME = "captions.md"

#: The figure page. ``moose-figure`` writes it, this module only reads it, and
#: the note transcludes it instead of listing the files itself.
PAGE_NAME = "gallery.md"

#: Order among the note's extension sections: after Handoff (40), before
#: Build and review (50).
ORDER_GALLERY = 45

#: The only extensions that may be listed. Everything a human looks at, and
#: nothing that is an input to something else: an exodus file, a checkpoint and
#: a mesh all stay where the example wrote them.
ALLOWED_EXT: Tuple[str, ...] = (
    ".png",
    ".svg",
    ".gif",
    ".jpg",
    ".jpeg",
    ".webp",
    ".mp4",
    ".csv",
    ".html",
    ".md",
    ".txt",
)

#: The subset that renders inline, in the note and as a Board.html thumbnail.
IMAGE_EXT: Tuple[str, ...] = (".png", ".svg", ".gif", ".jpg", ".jpeg", ".webp")

#: A filename that may be spelled in a wikilink, an ``img src`` and a path.
#: No ``[``, ``]``, ``|``, ``#``, ``^``, ``/``, ``\\``, no leading dot, no
#: control character. Spaces are allowed: Obsidian resolves them in a wikilink
#: and ``urllib.parse.quote`` handles them in the page.
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,95}$")

#: ``captions.md`` and any numbered sibling an older ``preserve`` left behind.
#: The index is not a figure: listing ``captions-2.md`` among the files would
#: render the index as if it were evidence.
CAPTIONS_SHAPED = re.compile(r"^captions(-\d+)?\.md$", re.IGNORECASE)

#: ``gallery.md`` and its numbered siblings. Same rule, same reason: the page
#: is the index of the gallery and never one of its exhibits.
PAGE_SHAPED = re.compile(r"^gallery(-\d+)?\.md$", re.IGNORECASE)

#: One figure section of the page: ``## `` and nothing deeper, so a ``### ``
#: inside a section stays part of that section.
PAGE_HEADING = re.compile(r"^##(?!#)\s*(.*?)\s*#*$")

#: The first image embed in a section names that section's file. Both spellings
#: are accepted: markdown ``![](file.png)``, angle-bracketed or not, and the
#: Obsidian wikilink ``![[file.png]]`` with an optional alias or heading.
PAGE_MD_EMBED = re.compile(r"!\[[^\]]*\]\(\s*(?:<([^>]*)>|([^)\s]+))")
PAGE_WIKI_EMBED = re.compile(r"!\[\[([^\]\|#]+)")

CAPTION_WIDTH = 160        # one line under a figure, not a paragraph
TITLE_WIDTH = 120          # a figure heading, on a card and in an alt attribute
MAX_LISTED = 40            # a gallery longer than this is a directory, not a gallery
MAX_PAGE_BYTES = 200_000

#: Statuses ``maintain_link`` returns. ``blocked`` is the one a doctor row reads.
LINK_STATUSES: Tuple[str, ...] = (
    "created",
    "same",
    "repaired",
    "removed",
    "absent",
    "blocked",
    "dry-run",
    "failed",
)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _safe(text: str) -> str:
    """Neutralize the note's fence markers inside projected prose.

    Identical in purpose to the handoff's escape, and deliberately a second
    copy rather than an import: two extensions that reach into each other's
    private helpers are one refactor away from a circular import, and this is
    four characters of logic.
    """
    return str(text).replace("<!--", "&lt;!--")


def _clip(text: Any, width: int = CAPTION_WIDTH) -> str:
    """One whitespace-normal line, escaped, and cut on a width."""
    out = _safe(" ".join(str(text or "").split()))
    return out if len(out) <= width else out[: width - 3].rstrip() + "..."


def _kb(size: Any) -> int:
    """A byte count as whole kilobytes, rounded up, so a 40 byte file is 1 kB."""
    try:
        n = int(size)
    except Exception:
        return 0
    return (n + 1023) // 1024 if n > 0 else 0


def _size_str(kb: Any) -> str:
    """A size that reads the same on every run. Same shape as teardown's."""
    try:
        n = int(kb)
    except Exception:
        return "unknown"
    if n >= 1024 * 1024:
        return "%.1f GB" % (n / 1024.0 / 1024.0,)
    if n >= 1024:
        return "%.1f MB" % (n / 1024.0,)
    return "%d kB" % (n,)


def is_image(name: str) -> bool:
    return os.path.splitext(str(name))[1].lower() in IMAGE_EXT


def _allowed(name: str) -> bool:
    return os.path.splitext(str(name))[1].lower() in ALLOWED_EXT


def max_bytes(ctx: Any) -> int:
    """The per-file cap, in bytes. Config key ``gallery_max_mb``, default 5."""
    mb = getattr(getattr(ctx, "config", None), "gallery_max_mb", None)
    try:
        mb = int(mb)
    except Exception:
        mb = config.GALLERY_MAX_MB
    if mb <= 0:
        mb = config.GALLERY_MAX_MB
    return mb * 1024 * 1024


def thumbs(ctx: Any) -> int:
    """How many thumbnails one board card shows. Config ``gallery_thumbs``."""
    n = getattr(getattr(ctx, "config", None), "gallery_thumbs", None)
    try:
        n = int(n)
    except Exception:
        n = config.GALLERY_THUMBS
    return n if n > 0 else 0


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------


def worktree_gallery(obs: Dict[str, Any]) -> Optional[Path]:
    wt = (obs or {}).get("worktree")
    return (Path(wt) / GALLERY_REL) if wt else None


def artifacts_gallery(ctx: Any, feature: str) -> Path:
    return ctx.config.artifacts_dir / config.validate_id(feature) / "gallery"


def gallery_root(ctx: Any) -> Path:
    return Path(ctx.config.vault) / GALLERY_DIRNAME


def link_path(ctx: Any, feature: str) -> Path:
    return gallery_root(ctx) / config.validate_id(feature)


def _contains(parent: Path, child: Path) -> bool:
    """True when ``child`` resolves at or under ``parent``.

    ``realpath`` rather than ``resolve``: it compares the real locations, so
    /var and /private/var are equal on macOS, and a symlinked gallery directory
    that points outside the worktree fails here rather than being walked.
    """
    try:
        Path(os.path.realpath(str(child))).relative_to(
            Path(os.path.realpath(str(parent)))
        )
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# gallery.md, the figure page
# --------------------------------------------------------------------------


def _embed_target(line: str) -> str:
    """The file an embed points at, or ``""``.

    Only the name is kept. A page that writes ``![](./fig1.png)`` names the file
    beside it, and a page that writes a path out of the directory names nothing:
    every target is matched against the files the scan already accepted, so a
    name that is not one of them reaches nothing.
    """
    match = PAGE_WIKI_EMBED.search(line)
    raw = match.group(1) if match else ""
    if not raw:
        match = PAGE_MD_EMBED.search(line)
        if match:
            raw = match.group(1) or match.group(2) or ""
    raw = str(raw).strip().strip("'\"").strip()
    if not raw:
        return ""
    try:
        raw = urllib.parse.unquote(raw)
    except Exception:
        pass
    return os.path.basename(raw.replace("\\", "/").rstrip("/")).strip()


def parse_page(text: str) -> List[Dict[str, str]]:
    """``[{"title", "name"}]`` in page order, one entry per ``## `` section.

    The heading text is the title and the first image embed below it is the
    file. A section that embeds nothing is dropped: it names no figure, so it
    can order nothing. Prose above the first heading is ignored, which is what
    lets the page carry a ``# Gallery: <feature>`` title and a sentence of
    context.
    """
    out: List[Dict[str, str]] = []
    title: Optional[str] = None
    name = ""
    for raw in (text or "").splitlines():
        line = raw.strip()
        head = PAGE_HEADING.match(line) if line.startswith("##") else None
        if head is not None:
            if title is not None and name:
                out.append({"title": title, "name": name})
            title = _clip(head.group(1), TITLE_WIDTH)
            name = ""
            continue
        if title is None or name:
            continue
        found = _embed_target(line)
        if found and SAFE_NAME.match(found):
            name = found
    if title is not None and name:
        out.append({"title": title, "name": name})
    return out


def read_page(directory: Path) -> Tuple[List[Dict[str, str]], bool]:
    """``(figures, present)``. An unreadable or oversized page is ``([], ...)``."""
    path = Path(directory) / PAGE_NAME
    try:
        if not path.is_file() or path.is_symlink():
            return ([], False)
        if path.stat().st_size > MAX_PAGE_BYTES:
            return ([], True)
        return (parse_page(path.read_text(encoding="utf-8", errors="replace")), True)
    except Exception:
        return ([], False)


# --------------------------------------------------------------------------
# The listing
# --------------------------------------------------------------------------

EMPTY: Dict[str, Any] = {
    "source": None,            # "worktree", "artifacts", or None
    "dir": None,               # the directory that was scanned
    "files": [],               # [{name, kb, image}], sorted by name, the page included
    "figures": [],             # [{name, kb, image, title, on_page}] in page order
    "count": 0,
    "total_kb": 0,
    "over_cap": [],            # [{name, kb}] listed but never linked
    "empty": [],               # zero byte entries: a render that did not finish
    "links": [],               # entry names that were themselves symlinks
    "unsafe": [],              # entry names a wikilink may not spell
    "page": False,             # gallery.md is there and was read
    "page_missing": [],        # names the page embeds that the scan did not accept
    "link": None,              # the vault-side symlink path
    "link_status": "absent",
    "link_target": None,
    "refused": None,           # why no directory was read, when one exists
}


def scan(ctx: Any, directory: Optional[Path], source: Optional[str]) -> Dict[str, Any]:
    """One gallery directory as data. Never raises, never follows a symlink."""
    rec: Dict[str, Any] = dict(EMPTY)
    rec["files"] = []
    rec["figures"] = []
    rec["over_cap"] = []
    rec["empty"] = []
    rec["links"] = []
    rec["unsafe"] = []
    rec["page_missing"] = []
    if directory is None:
        return rec
    try:
        if not Path(directory).is_dir():
            return rec
    except Exception:
        return rec
    rec["dir"] = str(directory)
    rec["source"] = source

    page, present = read_page(Path(directory))
    rec["page"] = bool(present)

    cap = max_bytes(ctx)
    files: List[Dict[str, Any]] = []
    over: List[Dict[str, Any]] = []
    empty: List[str] = []
    linked: List[str] = []
    unsafe: List[str] = []
    try:
        entries = sorted(os.scandir(str(directory)), key=lambda e: e.name)
    except Exception as exc:
        ctx.log("gallery: cannot list %s: %s" % (directory, exc))
        return rec
    for entry in entries:
        name = entry.name
        # The retired captions index, and any numbered sibling an older teardown
        # made, is never an exhibit and is never read.
        if CAPTIONS_SHAPED.match(name):
            continue
        try:
            # follow_symlinks=False everywhere: a symlink is reported, never
            # walked, so nothing outside the worktree can reach the vault.
            if entry.is_symlink():
                if _allowed(name):
                    linked.append(name)
                continue
            if not entry.is_file(follow_symlinks=False):
                continue
            if not _allowed(name):
                continue
            if not SAFE_NAME.match(name):
                unsafe.append(name)
                continue
            size = entry.stat(follow_symlinks=False).st_size
        except Exception:
            continue
        if size > cap:
            over.append({"name": name, "kb": _kb(size)})
            continue
        if size <= 0:
            # A render that was interrupted leaves the file and its caption
            # line behind. Publishing it embeds a broken image under a caption
            # that claims it shows something, so name it and move on.
            empty.append(name)
            continue
        files.append(
            {
                "name": name,
                "kb": _kb(size),
                "image": is_image(name),
            }
        )

    if len(files) > MAX_LISTED:
        ctx.log(
            "gallery: %s holds %d eligible files; only the first %d are listed"
            % (directory, len(files), MAX_LISTED)
        )
        files = files[:MAX_LISTED]

    figures, missing = order_figures(files, page)

    rec["files"] = files
    rec["figures"] = figures
    rec["page_missing"] = missing
    rec["count"] = len(files)
    rec["total_kb"] = sum(int(f["kb"]) for f in files)
    rec["over_cap"] = over
    rec["empty"] = empty
    rec["links"] = linked
    rec["unsafe"] = unsafe
    return rec


def order_figures(
    files: List[Dict[str, Any]], page: List[Dict[str, str]]
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """``(figures, missing)``: the page's order, then everything it left out.

    The page is the source of truth for order and for titles, and the scan is
    the source of truth for what may be shown. A figure the page names that the
    scan refused (too big, zero bytes, gone) is not rendered under a title that
    claims it exists; its name is kept in ``missing`` for ``dump-obs``. A file
    the page never mentions is still shown, titled by its own name, because a
    figure that is on disk and off the page is the one thing a listing must not
    hide. The page itself is the index and never an exhibit.
    """
    known = {str(row.get("name")): row for row in files}
    figures: List[Dict[str, Any]] = []
    missing: List[str] = []
    used = set()
    for entry in page or []:
        name = str(entry.get("name") or "")
        if not name or name in used or PAGE_SHAPED.match(name):
            continue
        row = known.get(name)
        if row is None:
            missing.append(name)
            continue
        used.add(name)
        out = dict(row)
        out["title"] = str(entry.get("title") or "")
        out["on_page"] = True
        figures.append(out)
    for row in files:
        name = str(row.get("name"))
        if name in used or PAGE_SHAPED.match(name):
            continue
        out = dict(row)
        out["title"] = ""
        out["on_page"] = False
        figures.append(out)
    return (figures, missing)


def target_for(
    ctx: Any, feature: str, obs: Dict[str, Any]
) -> Tuple[Optional[Path], Optional[str], Optional[str]]:
    """``(directory, source, refused)``: the worktree gallery, else the copy.

    The worktree copy is the living one, so it always wins. Once the worktree
    is gone, ``Artifacts/<feature>/gallery/`` is the only copy, which is the
    whole reason ``preserve`` makes it.

    ``refused`` carries why a directory that does exist was not read, so the
    note can say that instead of the "there is none" placeholder. "Make the
    directory" is bad advice to give somebody whose directory is already there.
    """
    refused: Optional[str] = None
    live = worktree_gallery(obs)
    if live is not None and live.is_dir():
        wt = Path(str((obs or {}).get("worktree")))
        if not _contains(wt, live):
            ctx.log(
                "gallery: %s resolves outside %s, so it was not listed or linked"
                % (live, wt)
            )
            refused = "it resolves outside the worktree"
        else:
            return (live, "worktree", None)
    try:
        kept = artifacts_gallery(ctx, feature)
    except Exception:
        return (None, None, refused)
    if kept.is_dir():
        return (kept, "artifacts", None)
    return (None, None, refused)


# --------------------------------------------------------------------------
# The symlink
# --------------------------------------------------------------------------


def maintain_link(ctx: Any, feature: str, target: Optional[Path]) -> str:
    """Create, repair or remove ``<vault>/Gallery/<feature>``. One of
    :data:`LINK_STATUSES`.

    A real directory there is never touched. It means somebody copied where
    this design links; removing their copy to make room for a link is a
    decision, and a decision belongs in a ``factory doctor`` row, not in a
    board run that nobody is watching.
    """
    link = link_path(ctx, feature)
    dry = bool(getattr(ctx, "dry_run", False))
    is_link = os.path.islink(str(link))
    exists = is_link or link.exists()

    if target is None:
        if not exists:
            return "absent"
        if not is_link:
            return "blocked"
        if dry:
            return "dry-run"
        try:
            os.unlink(str(link))
        except Exception as exc:
            ctx.log("gallery: cannot remove the dangling link %s: %s" % (link, exc))
            return "failed"
        return "removed"

    want = str(Path(target))
    if is_link:
        try:
            if os.readlink(str(link)) == want:
                return "same"
        except Exception:
            pass
        if dry:
            return "dry-run"
        try:
            os.unlink(str(link))
            os.symlink(want, str(link))
        except Exception as exc:
            ctx.log("gallery: cannot repair %s -> %s: %s" % (link, want, exc))
            return "failed"
        return "repaired"
    if exists:
        return "blocked"
    if dry:
        return "dry-run"
    try:
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(want, str(link))
    except Exception as exc:
        ctx.log("gallery: cannot link %s -> %s: %s" % (link, want, exc))
        return "failed"
    return "created"


# --------------------------------------------------------------------------
# collect
# --------------------------------------------------------------------------


def collect(ctx: Any) -> None:
    """Runs in the probe round, before derive.

    Writes exactly one kind of thing: the symlinks under ``<vault>/Gallery/``.
    Nothing is copied here; ``preserve`` is the one copy, and only teardown
    calls it.
    """
    # The root exists from the first board run, before any card has a figure.
    # An absent folder is a convention nobody discovers: with it present in the
    # file explorer, `Gallery/` is visibly where the pictures land, and the two
    # doctor rows have something to scan. It is gitignored, so an empty one
    # costs the repository nothing.
    if not getattr(ctx, "dry_run", False):
        try:
            gallery_root(ctx).mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            ctx.log("gallery: cannot create %s: %s" % (gallery_root(ctx), exc))

    table: Dict[str, Dict[str, Any]] = {}
    seen: List[str] = []
    for feature in sorted(ctx.obs):
        obs = ctx.obs[feature] or {}
        try:
            config.validate_id(feature)
            directory, source, refused = target_for(ctx, feature, obs)
            rec = scan(ctx, directory, source)
            rec["refused"] = refused
            rec["link"] = str(link_path(ctx, feature))
            rec["link_target"] = str(directory) if directory is not None else None
            rec["link_status"] = maintain_link(ctx, feature, directory)
            seen.append(feature)
        except Exception as exc:
            ctx.log("gallery: %s failed: %s" % (feature, exc))
            continue
        obs["gallery"] = rec
        table[feature] = rec
    ctx.meta["gallery"] = table
    sweep(ctx, seen)


def sweep(ctx: Any, seen: List[str]) -> List[str]:
    """Remove every dangling ``Gallery/`` link no card visited this run.

    The loop above only reaches features that still have a card, so a feature
    whose worktree was torn down without a rescued copy is never revisited and
    its link would dangle forever. That is exactly the case the "removed"
    status was written for, and exactly the case the doctor row promises a
    board run clears. Same two guards as :func:`maintain_link`: never a real
    directory, never a link that still resolves.
    """
    if getattr(ctx, "dry_run", False):
        return []
    root = gallery_root(ctx)
    known = set(seen or [])
    gone: List[str] = []
    try:
        entries = sorted(os.scandir(str(root)), key=lambda e: e.name) if root.is_dir() else []
    except Exception:
        return []
    for entry in entries:
        if entry.name in known:
            continue
        path = Path(root) / entry.name
        try:
            if not os.path.islink(str(path)):
                continue
            if os.path.exists(str(path)):
                continue
            os.unlink(str(path))
        except Exception as exc:
            ctx.log("gallery: cannot remove the dangling link %s: %s" % (path, exc))
            continue
        gone.append(entry.name)
        ctx.log("gallery: removed the dangling link %s, its target is gone" % (path,))
    return gone


def record(ctx: Any, card_or_feature: Any) -> Dict[str, Any]:
    """The gallery record for one card, from the probe round when there was one.

    ``factory status`` renders with no probe round, so fall back to
    ``ctx.meta`` and then to a direct scan of the two directories.
    """
    feature = getattr(card_or_feature, "id", card_or_feature)
    obs = (ctx.obs.get(feature) if isinstance(ctx.obs, dict) else None) or {}
    rec = obs.get("gallery")
    if isinstance(rec, dict):
        return rec
    rec = (ctx.meta.get("gallery") or {}).get(feature)
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
        directory, source, refused = target_for(ctx, str(feature), obs)
        out = scan(ctx, directory, source)
        out["refused"] = refused
        out["link"] = str(link_path(ctx, str(feature)))
        out["link_target"] = str(directory) if directory is not None else None
        return out
    except Exception:
        return dict(EMPTY)


def files(ctx: Any, card_or_feature: Any) -> List[Dict[str, Any]]:
    """One card's figures, in page order. The published reader, for Board.html.

    Each row carries ``name``, ``kb``, ``image``, ``title`` and ``on_page``. A
    snapshot written before the page existed carries no ``figures`` key, so the
    name-sorted listing is the fallback and the board still renders.
    """
    rec = record(ctx, card_or_feature)
    out = rec.get("figures")
    if not isinstance(out, list):
        out = rec.get("files")
    return list(out) if isinstance(out, list) else []


def count(ctx: Any, card_or_feature: Any) -> int:
    rec = record(ctx, card_or_feature)
    try:
        return int(rec.get("count") or 0)
    except Exception:
        return 0


# --------------------------------------------------------------------------
# preserve: the one copy, made by teardown
# --------------------------------------------------------------------------


def _same_bytes(a: Path, b: Path) -> bool:
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        return a.read_bytes() == b.read_bytes()
    except Exception:
        return False


def _numbered(dest: Path, limit: int = 20) -> List[Path]:
    stem, suffix = dest.stem, dest.suffix
    return [dest.with_name("%s-%d%s" % (stem, n, suffix)) for n in range(2, limit + 1)]


def copy_one(ctx: Any, src: Path, dest: Path) -> Tuple[str, Optional[Path]]:
    """Copy one gallery file, idempotently and without ever overwriting.

    ``same``, ``copied``, ``suffixed``, ``dry-run`` or ``failed``. The suffix
    rule is the build record's, not the handoff's: two different figures that
    happen to share a filename are two facts, and overwriting one with the
    other destroys evidence that nothing else holds.
    """
    if dest.exists():
        if _same_bytes(src, dest):
            return ("same", dest)
        target = None
        for cand in _numbered(dest):
            if not cand.exists():
                target = cand
                break
            if _same_bytes(src, cand):
                return ("same", cand)
        if target is None:
            return ("failed", None)
        dest = target
        status = "suffixed"
    else:
        status = "copied"
    if getattr(ctx, "dry_run", False):
        return ("dry-run", dest)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))
    except Exception as exc:
        ctx.log("gallery: copy %s -> %s failed: %s" % (src, dest, exc))
        return ("failed", None)
    return (status, dest)


def retarget_captions(text: str, renames: Dict[str, str]) -> str:
    """Point each caption line at the name its figure actually landed under.

    A figure that collided with a differing one of the same name was copied to
    ``fig1-2.png``, so the line that reads ``fig1.png: ...`` describes a file
    that is not there: ``fig1.png`` is now the older figure, whose caption went
    aside with the older index. Rewriting the key labels the figure that
    arrived and leaves the older one showing its own name, which is true.
    """
    if not renames:
        return text
    out: List[str] = []
    for raw in (text or "").splitlines():
        line = raw.rstrip("\r")
        head, sep, rest = line.partition(":")
        key = head.strip().strip("`").lstrip("-* ").strip()
        if sep and key in renames:
            line = line.replace(head, head.replace(key, renames[key], 1), 1)
        out.append(line)
    tail = "\n" if (text or "").endswith("\n") else ""
    return "\n".join(out) + tail


def retarget_page(text: str, renames: Dict[str, str]) -> str:
    """Point each embed on the page at the name its figure landed under.

    Same rule as :func:`retarget_captions`, applied to the two embed spellings
    the page may use. A figure that collided with a differing one was copied to
    ``fig1-2.png``, so an embed that still reads ``fig1.png`` would show the
    older figure under the newer figure's heading.
    """
    if not renames:
        return text
    out = str(text or "")
    for old, new in renames.items():
        out = out.replace("](<%s>)" % (old,), "](<%s>)" % (new,))
        out = out.replace("](%s)" % (old,), "](%s)" % (new,))
        out = out.replace("[[%s]]" % (old,), "[[%s]]" % (new,))
    return out


def copy_captions(
    ctx: Any,
    src: Path,
    dest: Path,
    renames: Optional[Dict[str, str]] = None,
    rewrite: Any = None,
) -> str:
    """Land an index file **at** its own name, never beside it.

    A figure is evidence, so :func:`copy_one` suffixes rather than overwrites
    and two same-named figures both survive. ``gallery.md``, and the retired
    ``captions.md``, are not evidence: they are the index, and exactly one path
    is read back. Suffixing one would leave the stale index in the only place
    anything looks, so every rescued figure would carry the title of whatever it
    replaced, and nothing on the note would say so. The current index therefore
    always wins the name, a differing older one is moved aside to keep its text,
    and every reference to a figure that was suffixed is rewritten to the name
    it landed under.

    ``same``, ``copied``, ``replaced``, ``dry-run`` or ``failed``.
    """
    try:
        want = (rewrite or retarget_captions)(
            Path(src).read_text(encoding="utf-8", errors="replace"), renames or {}
        )
    except Exception as exc:
        ctx.log("gallery: cannot read %s: %s" % (src, exc))
        return "failed"
    try:
        if dest.exists() and dest.read_text(encoding="utf-8", errors="replace") == want:
            return "same"
    except Exception:
        pass
    if getattr(ctx, "dry_run", False):
        return "dry-run"
    status = "copied"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            kept = None
            for cand in _numbered(dest):
                if not cand.exists():
                    kept = cand
                    break
            if kept is not None:
                shutil.copy2(str(dest), str(kept))
            status = "replaced"
        dest.write_text(want, encoding="utf-8")
    except Exception as exc:
        ctx.log("gallery: index %s -> %s failed: %s" % (src, dest, exc))
        return "failed"
    return status


def preserve(ctx: Any, feature: str, worktree: Any = None) -> Dict[str, Any]:
    """Copy the size-capped gallery into ``Artifacts/<feature>/gallery/``.

    Called by ``factory teardown`` before the first destructive command, and by
    nothing else. Idempotent: a second call over an unchanged gallery copies
    nothing and reports ``same`` for every file. After the copy the vault-side
    symlink is repointed at it, so ``Gallery/<feature>`` keeps working once the
    worktree is gone and every ``![[Gallery/...]]`` embed on the note survives.

    Returns ``{"copied", "same", "suffixed", "failed", "page", "captions",
    "renamed", "dest", "link_status", "files", "kb", "over_cap"}``. Never
    raises: teardown must not die because a figure could not be copied, it must
    say so.
    """
    config.validate_id(feature)
    out: Dict[str, Any] = {
        "copied": 0,
        "same": 0,
        "suffixed": 0,
        "failed": 0,
        "page": "absent",
        "captions": "absent",
        "dest": None,
        "link_status": "absent",
        "files": 0,
        "kb": 0,
        "over_cap": [],
        "renamed": {},
        "source": None,
    }
    obs = dict((ctx.obs.get(feature) if isinstance(ctx.obs, dict) else None) or {})
    if worktree:
        obs["worktree"] = str(worktree)
    src_dir = worktree_gallery(obs)
    if src_dir is None or not src_dir.is_dir():
        return out
    if not _contains(Path(str(obs.get("worktree"))), src_dir):
        ctx.log("gallery: %s resolves outside the worktree, so it was not preserved" % (src_dir,))
        return out

    rec = scan(ctx, src_dir, "worktree")
    dest_dir = artifacts_gallery(ctx, feature)
    out["dest"] = str(dest_dir)
    out["source"] = str(src_dir)
    out["files"] = int(rec.get("count") or 0)
    out["kb"] = int(rec.get("total_kb") or 0)
    out["over_cap"] = [str(row.get("name")) for row in (rec.get("over_cap") or [])]

    renames: Dict[str, str] = {}
    for row in rec.get("files") or []:
        name = str(row["name"])
        if PAGE_SHAPED.match(name):
            # The page is the index of the gallery, so it lands on its own name
            # below rather than being suffixed aside like a figure.
            continue
        status, where = copy_one(ctx, src_dir / name, dest_dir / name)
        if where is not None and Path(where).name != name:
            renames[name] = Path(where).name
        if status in out:
            out[status] = int(out[status]) + 1
        elif status != "dry-run":
            out["failed"] = int(out["failed"]) + 1

    page = src_dir / PAGE_NAME
    if page.is_file() and not page.is_symlink():
        out["page"] = copy_captions(
            ctx, page, dest_dir / PAGE_NAME, renames, retarget_page
        )
    # captions.md is retired and is never read, but a worktree that still holds
    # one holds the only copy, and teardown is the last moment it exists.
    captions = src_dir / CAPTIONS_NAME
    if captions.is_file() and not captions.is_symlink():
        out["captions"] = copy_captions(
            ctx, captions, dest_dir / CAPTIONS_NAME, renames
        )
    out["renamed"] = dict(renames)

    # Repoint the link at the copy, so the note's embeds keep resolving. Only
    # when something actually landed: a link to an empty directory is worse
    # than no link, because it reads as "the figures are here" and they are not.
    if dest_dir.is_dir() and not getattr(ctx, "dry_run", False):
        out["link_status"] = maintain_link(ctx, feature, dest_dir)
    return out


# --------------------------------------------------------------------------
# The note section
# --------------------------------------------------------------------------


def _embed(feature: str, name: str) -> str:
    return "![[%s/%s/%s]]" % (GALLERY_DIRNAME, feature, name)


def _wiki(feature: str, name: str) -> str:
    return "[[%s/%s/%s]]" % (GALLERY_DIRNAME, feature, name)


def note_sections(card: Any, ctx: Any) -> List[Tuple[str, str, int]]:
    rec = record(ctx, card)
    feature = str(getattr(card, "id", card))
    out: List[str] = []

    blocked = (
        "_`%s/%s` is a real directory, not a link. The projector never removes one: "
        "delete it by hand and the next board run links it._"
        % (GALLERY_DIRNAME, feature)
        if rec.get("link_status") == "blocked"
        else ""
    )

    if not rec.get("dir"):
        refused = rec.get("refused")
        if refused:
            # The directory is there; it was refused. "Create it" would send the
            # author to make something that already exists.
            out.append(
                "_`specs/gallery/` was not read, because %s. Nothing under it reached this note "
                "or the vault._" % (_clip(refused),)
            )
        elif getattr(card, "worktree", None):
            out.append(
                "_No `specs/gallery/`. A session that renders a figure puts it there and "
                "describes it in `specs/gallery/gallery.md`, one `## ` section per figure, and "
                "the page appears here and the figures appear on the board._"
            )
        elif not blocked:
            return []
        if blocked:
            out.append("")
            out.append(blocked)
        return [("Gallery", "\n".join(out).rstrip(), ORDER_GALLERY)]

    where = (
        "the worktree"
        if rec.get("source") == "worktree"
        else "the rescued copy, because the worktree is gone"
    )
    rows = rec.get("files") or []
    out.append(
        "%d file%s, %s, read from %s. Linked at `%s/%s/`."
        % (
            len(rows),
            "" if len(rows) == 1 else "s",
            _size_str(rec.get("total_kb")),
            where,
            GALLERY_DIRNAME,
            feature,
        )
    )
    out.append("")

    figs = rec.get("figures") or []
    if rec.get("page"):
        # The page is the note. It carries the order, the titles and the prose,
        # so transcluding it keeps one writer for all three and the note never
        # states a second, staler version of what the figures show.
        out.append(_embed(feature, PAGE_NAME))
        out.append("")
    elif not figs:
        out.append("_Empty._")
    else:
        for row in figs:
            name = str(row.get("name"))
            if row.get("image"):
                if out and out[-1].startswith("- "):
                    # A bullet run directly above an embed makes the embed a lazy
                    # continuation of that list item, so it renders inside the bullet.
                    out.append("")
                out.append(_embed(feature, name))
                out.append("")
                out.append("_%s_" % (name,))
                out.append("")
            else:
                out.append("- %s" % (_wiki(feature, name),))
        if not figs[-1].get("image"):
            out.append("")

    over = rec.get("over_cap") or []
    if over:
        out.append(
            "_Over the %d MB cap, so not linked: %s._"
            % (
                max_bytes(ctx) // (1024 * 1024),
                ", ".join(
                    "%s (%s)" % (_clip(row.get("name")), _size_str(row.get("kb")))
                    for row in over
                ),
            )
        )
    empties = rec.get("empty") or []
    if empties:
        out.append(
            "_Empty, so not linked: %s._"
            % (", ".join(_clip(n) for n in sorted(str(x) for x in empties)),)
        )
    links = rec.get("links") or []
    if links:
        out.append(
            "_Skipped, a symlink is never followed out of the worktree: %s._"
            % (", ".join(_clip(n) for n in sorted(str(x) for x in links)),)
        )
    unsafe = rec.get("unsafe") or []
    if unsafe:
        out.append(
            "_Skipped, the name cannot be spelled in a link: %s._"
            % (", ".join(_clip(n) for n in sorted(str(x) for x in unsafe)),)
        )
    if not rec.get("page"):
        out.append(
            "_No `gallery.md`. A figure page there, one `## ` section per figure with its "
            "heading, its embed and what to look at, is shown here instead of this listing._"
        )
    if blocked:
        out.append(blocked)
    return [("Gallery", "\n".join(out).rstrip(), ORDER_GALLERY)]


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------


def doctor_checks(ctx: Any) -> List[Tuple[str, bool, str]]:
    """Two rows, both read straight off the filesystem.

    ``ctx`` here may carry only config, paths and ``now``: ``factory doctor``
    runs without a probe round, so nothing below touches ``ctx.obs``.
    """
    out: List[Tuple[str, bool, str]] = []
    root = gallery_root(ctx)
    dangling: List[str] = []
    copied: List[str] = []
    try:
        entries = sorted(os.scandir(str(root)), key=lambda e: e.name) if root.is_dir() else []
    except Exception:
        entries = []
    for entry in entries:
        try:
            if entry.is_symlink():
                if not os.path.exists(str(Path(root) / entry.name)):
                    dangling.append(entry.name)
            elif entry.is_dir(follow_symlinks=False):
                copied.append(entry.name)
        except Exception:
            continue
    out.append(
        (
            "every Gallery/ symlink resolves",
            not dangling,
            "these point at nothing: %s. The worktree is gone and no "
            "Artifacts/<feature>/gallery/ was kept, so run `factory board`: it removes a "
            "dangling link. A link that keeps coming back names a worktree whose gallery "
            "moved." % (", ".join(dangling),),
        )
    )
    out.append(
        (
            "no Gallery/ entry is a real directory",
            not copied,
            "these are copies, not links: %s. The projector links a gallery and copies it "
            "exactly once, in `factory teardown`. A real directory here is a second copy of "
            "the same bytes that nothing keeps current: remove it by hand and the next board "
            "run links the worktree again." % (", ".join(copied),),
        )
    )
    return out
