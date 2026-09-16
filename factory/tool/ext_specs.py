"""The specs link: the blueprint, the handoff and the reviews, readable from the vault.

``<worktree>/specs/`` is where a session leaves what a human reads: ``blueprint.md``
and its rendered ``blueprint.html``, ``handoff.md``, and one ``review-<label>.md``
per clean-context review. ``ext_gallery`` links one subdirectory of it. This module
links the directory itself as ``<vault>/Specs/<feature>``, a **symlink**, so the
blueprint opens in Obsidian without opening the workspace. Obsidian writes through
the link, so a clarification box ticked in ``blueprint.md`` there lands in the
worktree file, which is the only copy that counts. The HTML page is a render of
that file and saves nothing; the note says so.

The disciplines are ``ext_gallery``'s: link, never copy; a target that resolves
outside its worktree is refused; a real directory at the link path is never
removed; nothing here reads the clock, so the note rebuilds byte for byte. Nothing
is preserved at teardown: the blueprint and the handoff are tracked on the
meta-repo branch, the reviews are rescued by ``ext_artifacts``, and the link is
swept once its target is gone.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config
from .ext_gallery import SAFE_NAME, _contains

SPECS_REL = "specs"
SPECS_DIRNAME = "Specs"

#: Order among the note's extension sections: just before Handoff (40), because
#: the plan belongs above what the last session said about executing it.
ORDER_SPECS = 38

BLUEPRINT = "blueprint.md"
RENDERED = "blueprint.html"
HANDOFF = "handoff.md"
REVIEW_PREFIX = "review-"

EMPTY: Dict[str, Any] = {
    "dir": None,
    "files": [],
    "reviews": [],
    "unsafe": [],
    "link": None,
    "link_target": None,
    "link_status": "absent",
    "refused": None,
}


def specs_root(ctx: Any) -> Path:
    return Path(ctx.config.vault) / SPECS_DIRNAME


def link_path(ctx: Any, feature: str) -> Path:
    return specs_root(ctx) / config.validate_id(feature)


def worktree_specs(obs: Dict[str, Any]) -> Optional[Path]:
    wt = (obs or {}).get("worktree")
    return (Path(wt) / SPECS_REL) if wt else None


def target_for(
    ctx: Any, feature: str, obs: Dict[str, Any]
) -> Tuple[Optional[Path], Optional[str]]:
    """``(directory, refused)``: the worktree specs directory, or why not."""
    live = worktree_specs(obs)
    if live is None or not live.is_dir():
        return (None, None)
    wt = Path(str((obs or {}).get("worktree")))
    if not _contains(wt, live):
        ctx.log("specs: %s resolves outside %s, so it was not linked" % (live, wt))
        return (None, "it resolves outside the worktree")
    return (live, None)


def scan(directory: Optional[Path]) -> Dict[str, Any]:
    """The readable files, by name. No symlink inside the directory is followed."""
    rec: Dict[str, Any] = dict(EMPTY)
    rec["files"] = []
    rec["reviews"] = []
    rec["unsafe"] = []
    if directory is None:
        return rec
    rec["dir"] = str(directory)
    try:
        entries = sorted(os.scandir(str(directory)), key=lambda e: e.name)
    except Exception:
        return rec
    for entry in entries:
        name = entry.name
        try:
            if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                continue
        except Exception:
            continue
        if name in (BLUEPRINT, RENDERED, HANDOFF):
            rec["files"].append(name)
        elif name.startswith(REVIEW_PREFIX) and name.endswith(".md"):
            if SAFE_NAME.match(name):
                rec["reviews"].append(name)
            else:
                rec["unsafe"].append(name)
    return rec


def maintain_link(ctx: Any, feature: str, target: Optional[Path]) -> str:
    """Create, repair or remove ``<vault>/Specs/<feature>``. A real directory
    there is never touched; it is a ``factory doctor`` row."""
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
            ctx.log("specs: cannot remove the dangling link %s: %s" % (link, exc))
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
            ctx.log("specs: cannot repair %s -> %s: %s" % (link, want, exc))
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
        ctx.log("specs: cannot link %s -> %s: %s" % (link, want, exc))
        return "failed"
    return "created"


def collect(ctx: Any) -> None:
    """Runs in the probe round. Writes exactly one kind of thing: the symlinks
    under ``<vault>/Specs/``."""
    if not getattr(ctx, "dry_run", False):
        try:
            specs_root(ctx).mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            ctx.log("specs: cannot create %s: %s" % (specs_root(ctx), exc))

    table: Dict[str, Dict[str, Any]] = {}
    seen: List[str] = []
    for feature in sorted(ctx.obs):
        obs = ctx.obs[feature] or {}
        try:
            config.validate_id(feature)
            directory, refused = target_for(ctx, feature, obs)
            rec = scan(directory)
            rec["refused"] = refused
            rec["link"] = str(link_path(ctx, feature))
            rec["link_target"] = str(directory) if directory is not None else None
            rec["link_status"] = maintain_link(ctx, feature, directory)
            seen.append(feature)
        except Exception as exc:
            ctx.log("specs: %s failed: %s" % (feature, exc))
            continue
        obs["specs"] = rec
        table[feature] = rec
    ctx.meta["specs"] = table
    sweep(ctx, seen)


def sweep(ctx: Any, seen: List[str]) -> List[str]:
    """Remove every dangling ``Specs/`` link no card visited this run."""
    if getattr(ctx, "dry_run", False):
        return []
    root = specs_root(ctx)
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
            ctx.log("specs: cannot remove the dangling link %s: %s" % (path, exc))
            continue
        gone.append(entry.name)
        ctx.log("specs: removed the dangling link %s, its target is gone" % (path,))
    return gone


def record(ctx: Any, card_or_feature: Any) -> Dict[str, Any]:
    """The specs record for one card, from the probe round when there was one;
    ``factory status`` renders without one, so fall back to a direct scan."""
    feature = getattr(card_or_feature, "id", card_or_feature)
    obs = (ctx.obs.get(feature) if isinstance(ctx.obs, dict) else None) or {}
    rec = obs.get("specs")
    if isinstance(rec, dict):
        return rec
    rec = (ctx.meta.get("specs") or {}).get(feature)
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
        directory, refused = target_for(ctx, str(feature), obs)
        out = scan(directory)
        out["refused"] = refused
        out["link"] = str(link_path(ctx, str(feature)))
        out["link_target"] = str(directory) if directory is not None else None
        return out
    except Exception:
        return dict(EMPTY)


def _wiki(feature: str, name: str, alias: str) -> str:
    # Obsidian resolves a note link without ``.md``; any other file keeps its extension.
    target = name[:-3] if name.endswith(".md") else name
    return "[[%s/%s/%s|%s]]" % (SPECS_DIRNAME, feature, target, alias)


def note_sections(card: Any, ctx: Any) -> List[Tuple[str, str, int]]:
    rec = record(ctx, card)
    feature = str(getattr(card, "id", card))
    out: List[str] = []

    blocked = (
        "_`%s/%s` is a real directory, not a link. The projector never removes one: "
        "delete it by hand and the next board run links it._" % (SPECS_DIRNAME, feature)
        if rec.get("link_status") == "blocked"
        else ""
    )

    if not rec.get("dir"):
        refused = rec.get("refused")
        if refused:
            out.append(
                "_`specs/` was not linked, because %s. Nothing under it reached this note "
                "or the vault._" % (refused,)
            )
        elif getattr(card, "worktree", None):
            out.append("_No `specs/` in the worktree. `/new-feature` creates it._")
        elif not blocked:
            return []
        if blocked:
            out.append("")
            out.append(blocked)
        return [("Blueprint", "\n".join(out).rstrip(), ORDER_SPECS)]

    files = list(rec.get("files") or [])
    reviews = list(rec.get("reviews") or [])
    if BLUEPRINT in files:
        line = "- Plan: %s" % (_wiki(feature, BLUEPRINT, BLUEPRINT),)
        if RENDERED in files:
            line += ", rendered as %s" % (_wiki(feature, RENDERED, RENDERED),)
        out.append(line)
    else:
        out.append(
            "- Plan: _no `specs/blueprint.md` yet. Run `/moose-blueprint` in the worktree._"
        )
    if HANDOFF in files:
        out.append("- Handoff: %s" % (_wiki(feature, HANDOFF, HANDOFF),))
    if reviews:
        out.append(
            "- Reviews: %s" % (", ".join(_wiki(feature, n, n) for n in reviews),)
        )
    unsafe = rec.get("unsafe") or []
    if unsafe:
        out.append(
            "- _Skipped, the name cannot be spelled in a link: %s._"
            % (", ".join(sorted(str(x) for x in unsafe)),)
        )
    out.append("")
    out.append(
        "_Linked at `%s/%s/`, straight into the worktree. A box ticked in `%s` here is "
        "saved to the worktree file. The `.html` page is a render of it and saves nothing; "
        "it re-renders when a session edits the markdown._"
        % (SPECS_DIRNAME, feature, BLUEPRINT)
    )
    if blocked:
        out.append("")
        out.append(blocked)
    return [("Blueprint", "\n".join(out).rstrip(), ORDER_SPECS)]


def doctor_checks(ctx: Any) -> List[Tuple[str, bool, str]]:
    """Two rows, read straight off the filesystem; no probe round needed."""
    out: List[Tuple[str, bool, str]] = []
    root = specs_root(ctx)
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
            "every Specs/ symlink resolves",
            not dangling,
            "these point at nothing: %s. The worktree is gone, so run `factory board`: it "
            "removes a dangling link." % (", ".join(dangling),),
        )
    )
    out.append(
        (
            "no Specs/ entry is a real directory",
            not copied,
            "these are copies, not links: %s. The projector only ever links a specs "
            "directory. Remove the copy by hand and the next board run links the worktree "
            "again." % (", ".join(copied),),
        )
    )
    return out
