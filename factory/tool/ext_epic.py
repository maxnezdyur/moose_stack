"""An epic on the board: its plan rescued, its slice pull requests listed.

An epic is a chain of dependent pull requests built in one worktree
(``specs/epic-stack-plan.md`` in the meta-repo is the design). The branch
``<epic>`` is never pushed; each shipped slice has a local ref and a fork branch
``epic/<epic>/s<n>``, which is the pull-request head. A feature name cannot hold
a slash, so a head in the ``epic/`` namespace is a slice on every machine. Core
does the three things only core can do: ``probe`` puts every slice on the card
``<epic>`` and marks an epic worktree by ``specs/epic.md``, and ``derive`` prints
``scripts/stack sync`` where a plain rebase would strand the slice refs and
offers "mark ready" for the lowest open slice only. This module does the rest:

1. ``collect`` rescues ``<worktree>/specs/epic.md`` and every file under
   ``<worktree>/specs/slices/`` into ``<vault>/Artifacts/<epic>/``. Nothing under
   ``specs/`` is tracked on the meta-repo branch, so without this copy the plan
   of the chain and every archived slice plan die with the worktree. The rescue
   runs on every board run, like the handoff's, and ``factory teardown`` runs a
   probe round first, so the copy is current when the worktree is removed.

2. ``note_sections`` renders ``## Epic`` on the feature note: the plan, the
   slices that have a pull request, in order, and the archived slice plans.

3. ``unrescued`` tells ``ext_teardown`` which of those files have no identical
   copy in ``Artifacts/``, so a teardown that would lose one says so first.

4. ``chain`` tells ``ext_teardown`` whether every commit on the branch ``<epic>``
   is merged or published. That branch is never pushed, so "never pushed" is no
   test for an epic.

5. ``collect`` reports a collision: a slice whose card ``<epic>`` exists and is
   not an epic. Such a slice is on no card. One line goes to the board log, and
   ``factory doctor`` has a row for it.

What this version does not do is on the note itself and in ``factory/README.md``:
the lane and the four gates are still per card, never per slice.

The disciplines are ``ext_handoff``'s. This module writes under ``Artifacts/``
and nowhere else, a copy is idempotent, ``copy2`` keeps the mtime so a second
run sees ``same``, a symlink is never followed, and nothing here reads the clock,
so the note rebuilds byte for byte. A source that has bytes always replaces its
rescued copy, as the handoff's does: the worktree file is the truth while the
worktree exists, and the vault's own history keeps every older copy. An empty
source never replaces a copy that has bytes. One epic keeps at most
``epic_rescue_max_mb`` under ``Artifacts/``; the plan and each slice's plan and
reviews are copied first, and what does not fit is named on the note and blocks
a teardown until ``--force``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config

#: Order among the note's extension sections: above Blueprint (38), because the
#: plan of the chain is what the plan of one slice is read against.
ORDER_EPIC = 36

EPIC_NAME = "epic.md"
SLICES_DIRNAME = "slices"
SPECS_DIRNAME = "Specs"          # the vault link ext_specs maintains
ARTIFACTS_DIRNAME = "Artifacts"

#: Three caps, from the narrowest to the widest. A file over the first is build
#: output that was archived by mistake; it is the cap of one rescued build
#: record. The third is the setting ``epic_rescue_max_mb`` (20 MB by default,
#: ``factory config --get epic_rescue_max_mb``): `Artifacts/` is committed, so
#: without a total a set of archived figures would grow the vault's history on
#: every board run that sees a changed file.
MAX_FILE_BYTES = 4_000_000
MAX_FILES = 1000

#: A directory or file name this module is willing to spell in a wiki link.
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SLICE_DIR = re.compile(r"^s(\d+)$")

SKIP_NAMES = frozenset({".DS_Store"})

#: The collisions of the last board run, for `factory doctor`, which runs no
#: probe round. Under state/, absent when there is none. The leading underscore
#: keeps it out of the per-feature state files.
COLLISIONS_NAME = "_epic-collisions.json"

#: The fork. A slice is published when its local ref equals this remote's.
FORK_REMOTE = "origin"
#: Where a merged slice lands. Pull requests target `next`, and `devel` is an
#: ancestor of it, so a commit in either one is merged.
UPSTREAM_BASES = ("refs/remotes/upstream/next", "refs/remotes/upstream/devel")
_SLICE_REF = re.compile(r"^s([1-9]\d*)$")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _under(path: Path, parent: Path) -> bool:
    """True when ``path`` is at or under ``parent``, symlinks resolved."""
    try:
        Path(os.path.realpath(str(path))).relative_to(Path(os.path.realpath(str(parent))))
        return True
    except Exception:
        return False


def _same_bytes(a: Path, b: Path) -> bool:
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        return a.read_bytes() == b.read_bytes()
    except Exception:
        return False


def artifacts_dir(ctx: Any, feature: str) -> Path:
    return Path(ctx.config.artifacts_dir) / config.validate_id(feature)


def _worktree(obs_or_path: Any) -> Optional[Path]:
    wt = obs_or_path.get("worktree") if isinstance(obs_or_path, dict) else obs_or_path
    return Path(wt) if wt else None


def _safe(text: Any) -> str:
    """A file name as note prose. ``<!--`` would plant a second marker fence in
    the generated body, and a newline would break the bullet."""
    return " ".join(str(text).split()).replace("<!--", "<\\!--")


def _slice_key(name: str) -> Tuple[int, int, str]:
    m = _SLICE_DIR.match(name)
    return (0, int(m.group(1)), name) if m else (1, 0, name)


# --------------------------------------------------------------------------
# 1. The rescue
# --------------------------------------------------------------------------


def _kind(path: Path) -> Tuple[str, str]:
    """``(kind, error)``: ``file``, ``dir``, ``link``, ``other``, ``absent`` or ``error``.

    One ``lstat``, and the answer never hides a failure. ``Path.is_file`` says
    False for a path it was not allowed to look at, which reads as "nothing to
    rescue" on the one occasion that matters, a teardown.
    """
    try:
        st = os.lstat(str(path))
    except (FileNotFoundError, NotADirectoryError):
        return ("absent", "")
    except OSError as exc:
        return ("error", exc.strerror or type(exc).__name__)
    if stat.S_ISLNK(st.st_mode):
        return ("link", "")
    if stat.S_ISREG(st.st_mode):
        return ("file", "")
    if stat.S_ISDIR(st.st_mode):
        return ("dir", "")
    return ("other", "")


def sources(worktree: Optional[Path]) -> Tuple[List[Tuple[str, Path]], List[str]]:
    """``([(relative name, path)], [skipped])`` for one worktree, sorted by path.

    The relative name is the path under ``Artifacts/<epic>/``: ``epic.md`` and
    ``slices/<id>/...``. A symlink, whether a file or a directory, is never
    followed and never copied: it is named in ``skipped``. So is a directory
    that cannot be listed and a path that cannot be examined. Nothing that this
    function could not read is ever reported as absent.
    """
    out: List[Tuple[str, Path]] = []
    skipped: List[str] = []
    if worktree is None:
        return (out, skipped)
    specs = Path(worktree) / "specs"
    plan = specs / EPIC_NAME
    kind, why = _kind(plan)
    if kind == "file":
        out.append((EPIC_NAME, plan))
    elif kind == "link":
        skipped.append(EPIC_NAME + " (a symlink)")
    elif kind == "error":
        skipped.append("%s (cannot be read: %s)" % (EPIC_NAME, why))
    elif kind != "absent":
        skipped.append(EPIC_NAME + " (not a regular file)")

    root = specs / SLICES_DIRNAME
    kind, why = _kind(root)
    if kind == "link":
        skipped.append(SLICES_DIRNAME + "/ (a symlink)")
        return (out, skipped)
    if kind == "error":
        skipped.append("%s/ (cannot be read: %s)" % (SLICES_DIRNAME, why))
        return (out, skipped)
    if kind != "dir":
        if kind != "absent":
            skipped.append(SLICES_DIRNAME + " (not a directory)")
        return (out, skipped)

    def unreadable(exc: OSError) -> None:
        # os.walk drops a directory it cannot list unless it is told where to
        # put the error. A dropped directory would read as an empty one.
        try:
            rel = Path(str(exc.filename)).relative_to(specs).as_posix()
        except Exception:
            rel = str(exc.filename)
        skipped.append("%s/ (cannot be listed: %s)" % (rel, exc.strerror or type(exc).__name__))

    for dirpath, dirnames, filenames in os.walk(str(root), followlinks=False, onerror=unreadable):
        here = Path(dirpath)
        keep = []
        for name in sorted(dirnames):
            if _kind(here / name)[0] == "link":
                skipped.append(
                    "%s/ (a symlink)" % ((here / name).relative_to(specs).as_posix(),)
                )
            else:
                keep.append(name)
        dirnames[:] = keep
        for name in sorted(filenames):
            if name in SKIP_NAMES:
                continue
            path = here / name
            rel = path.relative_to(specs).as_posix()
            kind, why = _kind(path)
            if kind == "link":
                skipped.append("%s (a symlink)" % (rel,))
            elif kind == "error":
                skipped.append("%s (cannot be read: %s)" % (rel, why))
            elif kind != "file" or not _under(path, specs):
                skipped.append("%s (not a regular file under specs/)" % (rel,))
            else:
                out.append((rel, path))
    out.sort(key=lambda row: row[0])
    return (out, sorted(skipped))


def _priority(rel: str) -> Tuple[int, Tuple[int, int, str], int, str]:
    """The copy order: the plan, then each slice's plan and reviews, then the rest.

    ``epic.md`` is first. Then, slice by slice in slice order, ``blueprint.md``
    and each ``review-*.md``. Then every other file, by path. When the byte
    budget runs out, what is left out is the bulk (figures, proof and verify
    output), never the text that says what was built and why. The order reads
    names only, so the same worktree always gives the same selection.
    """
    if rel == EPIC_NAME:
        return (0, (0, 0, ""), 0, rel)
    parts = rel.split("/")
    if len(parts) == 3:
        name = parts[2]
        if name == "blueprint.md":
            return (1, _slice_key(parts[1]), 0, rel)
        if name.startswith("review-") and name.endswith(".md"):
            return (1, _slice_key(parts[1]), 1, rel)
    return (2, (0, 0, ""), 0, rel)


def budget_bytes(ctx: Any) -> int:
    mb = getattr(ctx.config, "epic_rescue_max_mb", config.EPIC_RESCUE_MAX_MB)
    try:
        return max(0, int(mb)) * 1_000_000
    except Exception:
        return config.EPIC_RESCUE_MAX_MB * 1_000_000


def select(ctx: Any, worktree: Optional[Path]) -> Tuple[List[Tuple[str, Path]], List[str]]:
    """``(chosen, left_out)``: the files the rescue keeps, and every one it does not.

    ``left_out`` carries the reason beside each name. A file is left out when it
    is a symlink or cannot be read (``sources``), when it alone is over
    ``MAX_FILE_BYTES``, when the epic already holds ``MAX_FILES``, or when it
    does not fit in what is left of the per-epic budget ``epic_rescue_max_mb``.
    A file that does not fit is passed over and the walk goes on, so a small
    review after a large figure is still kept. The selection depends on the
    worktree and the setting only: it is the same on every run.
    """
    rows, left = sources(worktree)
    left = list(left)
    budget = budget_bytes(ctx)
    mb = budget // 1_000_000
    chosen: List[Tuple[str, Path]] = []
    used = 0
    for rel, path in sorted(rows, key=lambda row: _priority(row[0])):
        try:
            size = path.stat().st_size
        except OSError as exc:
            left.append("%s (cannot be read: %s)" % (rel, exc.strerror or type(exc).__name__))
            continue
        if size > MAX_FILE_BYTES:
            left.append("%s (over %d bytes)" % (rel, MAX_FILE_BYTES))
        elif len(chosen) >= MAX_FILES:
            left.append("%s (over the %d file cap)" % (rel, MAX_FILES))
        elif used + size > budget:
            left.append("%s (over the %d MB budget of one epic)" % (rel, mb))
        else:
            chosen.append((rel, path))
            used += size
    return (chosen, sorted(left))


def rescue(ctx: Any, src: Path, dest: Path) -> str:
    """Copy ``src`` over ``dest``, idempotently. Writes under Artifacts/ only.

    Returns ``same``, ``copied``, ``dry-run``, ``too-large``, ``kept`` or
    ``failed``.

    The rule for a file that differs: a source with bytes always wins, shorter
    or not, because the worktree file is the truth while the worktree exists.
    The vault is a git repository, so the copy it replaces is in the history.
    The one exception is ``kept``: an empty source never replaces a copy that
    has bytes. A plan does not shrink to nothing, so an empty file is a write
    that failed in the worktree, not a newer version.
    """
    if not _under(dest, ctx.config.artifacts_dir):
        raise config.RefusedWrite(
            "refused: %s is outside %s, which is the only place this extension writes"
            % (dest, ctx.config.artifacts_dir)
        )
    try:
        size = src.stat().st_size
    except Exception as exc:
        ctx.log("epic: cannot stat %s, so it was not rescued: %s" % (src, exc))
        return "failed"
    if size > MAX_FILE_BYTES:
        return "too-large"
    if dest.is_file():
        if _same_bytes(src, dest):
            return "same"
        try:
            if size == 0 and dest.stat().st_size > 0:
                return "kept"
        except Exception:
            pass
    if getattr(ctx, "dry_run", False):
        return "dry-run"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))
    except Exception as exc:
        ctx.log("epic: copy %s -> %s failed: %s" % (src, dest, exc))
        return "failed"
    return "copied"


def rescue_all(ctx: Any, feature: str, worktree: Optional[Path]) -> Dict[str, Any]:
    """Rescue one worktree's epic files. ``{files, not_rescued}``, both stable.

    ``not_rescued`` names every file that has no identical copy afterwards, with
    the reason. It is a fact about the files, not about this run, so it is the
    same on the next run and may be stored.
    """
    rows, left = select(ctx, worktree)
    dest_root = artifacts_dir(ctx, feature)
    not_rescued: List[str] = list(left)
    if left:
        ctx.log("epic: %s has %d file(s) that were not rescued: %s"
                % (feature, len(left), "; ".join(left[:4])))
    for rel, src in rows:
        status = rescue(ctx, src, dest_root / rel)
        if status == "too-large":
            not_rescued.append("%s (over %d bytes)" % (rel, MAX_FILE_BYTES))
        elif status == "kept":
            not_rescued.append("%s (empty in the worktree; the rescued copy was kept)" % (rel,))
        elif status == "failed":
            not_rescued.append("%s (the copy failed)" % (rel,))
    return {"files": len(rows), "not_rescued": sorted(not_rescued)}


def collect(ctx: Any) -> None:
    """Runs in the probe round, before derive. Writes only under Artifacts/.

    A card with no ``specs/epic.md`` and no ``specs/slices/`` gets no key at
    all, so the state file of an ordinary feature is the one it always was.
    """
    for feature in sorted(ctx.obs):
        obs = ctx.obs[feature] or {}
        try:
            config.validate_id(feature)
            wt = _worktree(obs)
            if wt is None or not wt.is_dir():
                continue
            rec = rescue_all(ctx, feature, wt)
            if rec["files"] or rec["not_rescued"]:
                obs["epic_rescue"] = rec
        except Exception as exc:
            # One card's failure, a refused path included, never stops the
            # rescue of the cards after it.
            ctx.log("epic: %s rescue failed: %s" % (feature, exc))
    try:
        report_collisions(ctx)
    except Exception as exc:
        ctx.log("epic: the collision report failed: %s" % (exc,))


def collision_text(rows: List[Dict[str, Any]]) -> str:
    return "; ".join(
        "%s #%s %s (%s)" % (r.get("repo"), r.get("number"), r.get("head"), r.get("why"))
        for r in rows
    )


def collisions_path(ctx: Any) -> Path:
    return Path(getattr(ctx, "state_dir", None) or ctx.config.state_dir) / COLLISIONS_NAME


def report_collisions(ctx: Any) -> None:
    """One log line, and the list kept for doctor. Writes under state/ only.

    The file exists only while there is a collision, so a board with none
    leaves state/ exactly as it was.
    """
    rows = list((getattr(ctx, "meta", None) or {}).get("epic_collisions") or [])
    path = collisions_path(ctx)
    if rows:
        ctx.log(
            "epic: %d slice pull request(s) are on no card, because a card of that "
            "name exists and is not an epic: %s" % (len(rows), collision_text(rows))
        )
    if getattr(ctx, "dry_run", False):
        return
    if rows:
        text = json.dumps(rows, indent=1, sort_keys=True)
        try:
            if path.is_file() and path.read_text() == text:
                return
        except Exception:
            pass
        config.write_text_atomic(path, text)
    elif path.exists():
        path.unlink()


def unrescued(ctx: Any, feature: str, worktree: Any) -> List[str]:
    """The epic files in the worktree with no identical copy in Artifacts/.

    Read-only. ``ext_teardown`` asks this just before it removes a worktree,
    whether or not ``collect`` ran in this process. Every file ``select`` left
    out is in the answer with its reason, and so is a chosen file whose copy is
    absent or differs. An error is never an empty list: the caller turns an
    exception into a blocker of its own.
    """
    wt = _worktree(worktree)
    if wt is None or not config.is_safe_id(str(feature)):
        return []
    kind, why = _kind(wt)
    if kind == "absent":
        return []
    if kind == "error":
        return ["%s (cannot be read: %s)" % (wt, why)]
    rows, left = select(ctx, wt)
    dest_root = artifacts_dir(ctx, str(feature))
    out = list(left)
    for rel, src in rows:
        if not _same_bytes(src, dest_root / rel):
            out.append(rel)
    return sorted(out)


def chain(repo_dir: str, epic: str, run: Any) -> Dict[str, Any]:
    """Is every commit on the branch ``<epic>`` merged or published?

    ``{"problems": [...], "left": [...]}``. Local git reads only, through
    ``run`` (``(argv) -> (stdout, ok)``); nothing is fetched.

    ``{"problems", "left", "branch", "note"}``. ``branch`` is whether the local
    branch ``<epic>`` exists (None when the refs could not be read). An absent
    branch is a problem. ``note`` says which slices the answer took as published.

    A commit on ``<epic>`` is safe when it is reachable from an upstream base
    (``upstream/next`` or ``upstream/devel``: the slice merged), or from a local
    slice ref ``epic/<epic>/s<n>`` whose sha equals the fork's remote-tracking
    ref (the slice equals the fork as of the last fetch, which is not proof of
    what the fork holds now). Every other commit is lost when
    teardown deletes the branch, and ``problems`` names why: a slice that was
    sealed and never published, a slice that differs from the fork, commits
    that are in no slice at all. A read that fails is a problem too, never a
    pass.

    ``left`` is what teardown leaves behind in this repository: the local
    branches ``epic/<epic>/*`` and the refs ``refs/stack/<epic>/*``.
    """
    heads = "refs/heads/epic/%s/" % (epic,)
    fork = "refs/remotes/%s/epic/%s/" % (FORK_REMOTE, epic)
    stack = "refs/stack/%s/" % (epic,)
    branch_ref = "refs/heads/%s" % (epic,)
    out, ok = run(
        ["git", "-C", repo_dir, "for-each-ref", "--format=%(refname) %(objectname)",
         branch_ref, heads, fork, stack] + list(UPSTREAM_BASES)
    )
    if not ok:
        return {"problems": ["the refs could not be read, so the chain was not judged"],
                "left": [], "branch": None}
    refs: Dict[str, str] = {}
    for line in out.splitlines():
        name, _sep, sha = line.strip().partition(" ")
        if name and sha:
            refs[name] = sha.strip()
    left = sorted(
        [n[len("refs/heads/"):] for n in refs if n.startswith(heads)]
        + [n for n in refs if n.startswith(stack)]
    )
    branch = refs.get(branch_ref)
    if not branch:
        # Not a pass. The caller asked about a branch that is not here, and
        # "nothing to judge" must never read as "nothing to lose".
        return {
            "problems": ["there is no local branch %s here, so the chain was not judged" % (epic,)],
            "left": left,
            "branch": False,
        }

    local = {n[len(heads):]: sha for n, sha in refs.items()
             if n.startswith(heads) and _SLICE_REF.match(n[len(heads):])}
    remote = {n[len(fork):]: sha for n, sha in refs.items() if n.startswith(fork)}
    published = {n: sha for n, sha in local.items() if remote.get(n) == sha}
    bases = [refs[b] for b in UPSTREAM_BASES if b in refs]
    if not bases:
        return {
            "problems": ["no upstream/next and no upstream/devel ref here, so a merged "
                         "commit cannot be told from one that is not"],
            "left": left,
            "branch": True,
        }
    # A remote-tracking ref is what the fork held at the last fetch, not what it
    # holds now. Nothing is fetched here, so every line that leans on one says so.
    relied = (
        "%d slice(s) equal the fork as of the last fetch (%s); nothing was fetched to check"
        % (len(published), ", ".join("epic/%s/%s" % (epic, n) for n in sorted(published, key=lambda n: int(n[1:]))))
        if published
        else ""
    )

    def commits(exclude: List[str]) -> Tuple[List[Tuple[str, str]], bool]:
        text, good = run(["git", "-C", repo_dir, "log", "--format=%H%x09%s", branch, "--not"]
                         + sorted(set(exclude)))
        rows = []
        for line in text.splitlines():
            sha, _sep, subject = line.partition("\t")
            if sha.strip():
                rows.append((sha.strip(), subject.strip()))
        return (rows, good)

    unsafe, ok = commits(bases + list(published.values()))
    if not ok:
        return {"problems": ["the commits of %s could not be listed, so the chain was not "
                             "judged" % (epic,)], "left": left, "branch": True}
    if not unsafe:
        return {"problems": [], "left": left, "branch": True, "note": relied}

    problems: List[str] = []
    at_risk = {sha for sha, _subject in unsafe}
    for name in sorted(local, key=lambda n: int(n[1:])):
        sha = local[name]
        if name in published or sha not in at_risk:
            continue
        if name not in remote:
            problems.append(
                "epic/%s/%s (%s) was sealed and never published: %s had no such branch "
                "as of the last fetch" % (epic, name, sha[:9], FORK_REMOTE)
            )
        else:
            problems.append(
                "epic/%s/%s differs from the fork as of the last fetch: local %s, %s %s"
                % (epic, name, sha[:9], FORK_REMOTE, remote[name][:9])
            )
    loose, ok = commits(bases + list(local.values()))
    if not ok:
        loose = unsafe
    if loose:
        problems.append(
            "%d commit(s) on %s are in no slice: %s%s"
            % (
                len(loose), epic,
                "; ".join("%s %s" % (sha[:9], _safe(subject)[:60]) for sha, subject in loose[:3]),
                "; and %d more" % (len(loose) - 3,) if len(loose) > 3 else "",
            )
        )
    if not problems:
        problems.append("%d commit(s) on %s are neither merged nor published" % (len(unsafe), epic))
    return {"problems": problems, "left": left, "branch": True, "note": relied}


# --------------------------------------------------------------------------
# 2. The note section
# --------------------------------------------------------------------------


def slice_rows(obs: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The card's slice pull requests, in the order ``specs/epic.md`` gives.

    A slice the table does not list sorts after the listed ones, by number.
    With no readable table the order is numeric, which is the creation order.
    """
    order = list(((obs.get("epic") or {}).get("order")) or [])
    rows = [
        p
        for p in (obs.get("prs") or [])
        if isinstance(p.get("slice"), int) and not isinstance(p.get("slice"), bool)
    ]

    def key(p: Dict[str, Any]) -> Tuple[int, int, int]:
        n = p["slice"]
        pos = order.index(n) if n in order else len(order)
        return (pos, n, int(p.get("number") or 0))

    return sorted(rows, key=key)


def state_word(pr: Dict[str, Any]) -> str:
    """``draft``, ``ready``, ``merged`` or ``closed``. Never a guess."""
    state = str(pr.get("state") or "").upper()
    if state == "MERGED" or pr.get("mergedAt"):
        return "merged"
    if state == "CLOSED":
        return "closed"
    if state == "OPEN":
        return "draft" if pr.get("isDraft") else "ready"
    return "unknown"


def _slice_dirs(root: Path) -> List[str]:
    try:
        names = [
            p.name
            for p in root.iterdir()
            if p.is_dir() and not p.is_symlink() and SAFE_NAME.match(p.name)
        ]
    except Exception:
        return []
    return sorted(names, key=_slice_key)


def note_sections(card: Any, ctx: Any) -> List[Tuple[str, str, int]]:
    feature = str(getattr(card, "id", card))
    if not config.is_safe_id(feature):
        return []
    obs = (getattr(ctx, "obs", None) or {}).get(feature) or {}
    worktree = getattr(card, "worktree", None) or obs.get("worktree")
    live_plan = bool(obs.get("epic")) and bool(worktree)
    rescued_root = artifacts_dir(ctx, feature)
    rescued_plan = (rescued_root / EPIC_NAME).is_file()
    rows = slice_rows({"prs": getattr(card, "prs", None) or obs.get("prs") or [], "epic": obs.get("epic")})
    if not (live_plan or rescued_plan or rows):
        return []

    out: List[str] = []
    if live_plan:
        out.append("- Plan: [[%s/%s/epic|%s]]" % (SPECS_DIRNAME, feature, EPIC_NAME))
    elif rescued_plan:
        out.append(
            "- Plan: [[%s/%s/epic|%s]] _(the rescued copy; the worktree is gone or has no plan)_"
            % (ARTIFACTS_DIRNAME, feature, EPIC_NAME)
        )
    else:
        out.append(
            "- Plan: _no `specs/epic.md` on this machine. The worktree is on the other "
            "machine, or it was torn down._"
        )

    if rows:
        out.append(
            "- Slices with a pull request, %s:"
            % ("in the order of the plan" if (obs.get("epic") or {}).get("order") else "in numeric order",)
        )
        for pr in rows:
            url = str(pr.get("url") or "")
            label = "%s #%s" % (pr.get("repo") or "?", pr.get("number"))
            out.append(
                "  - s%s: %s, %s"
                % (pr["slice"], ("[%s](%s)" % (label, url)) if url else label, state_word(pr))
            )
    else:
        out.append("- _No slice has a pull request yet._")

    if live_plan and (Path(str(worktree)) / "specs" / SLICES_DIRNAME).is_dir():
        base, names = SPECS_DIRNAME, _slice_dirs(Path(str(worktree)) / "specs" / SLICES_DIRNAME)
        root = Path(str(worktree)) / "specs" / SLICES_DIRNAME
    else:
        base, names = ARTIFACTS_DIRNAME, _slice_dirs(rescued_root / SLICES_DIRNAME)
        root = rescued_root / SLICES_DIRNAME
    if names:
        links = []
        for name in names:
            if (root / name / "blueprint.md").is_file():
                links.append("[[%s/%s/%s/%s/blueprint|%s]]" % (base, feature, SLICES_DIRNAME, name, name))
            else:
                links.append("`%s`" % (name,))
        out.append("- Archived slice plans: %s" % (", ".join(links),))

    lost = list((obs.get("epic_rescue") or {}).get("not_rescued") or [])
    if lost:
        out.append(
            "- _Not in `%s/%s/`: %s. A teardown would lose %s._"
            % (
                ARTIFACTS_DIRNAME,
                feature,
                "; ".join(_safe(x) for x in lost[:6])
                + ("; and %d more" % (len(lost) - 6,) if len(lost) > 6 else ""),
                "it" if len(lost) == 1 else "them",
            )
        )

    out.append("")
    out.append(
        "_The gates on this card are for the whole card, not for one slice. A `ship` or "
        "`pr_ready` grant from the first slice covers every later slice, so the board does not "
        "ask for them again._"
    )
    return [("Epic", "\n".join(out).rstrip(), ORDER_EPIC)]


# --------------------------------------------------------------------------
# 3. Doctor
# --------------------------------------------------------------------------


def _epic_worktrees(cfg: Any) -> List[str]:
    try:
        root = Path(cfg.worktree_root)
        return sorted(
            p.name for p in root.iterdir() if (p / "specs" / EPIC_NAME).is_file()
        )
    except Exception:
        return []


def doctor_checks(ctx: Any) -> List[Tuple[str, bool, str]]:
    cfg = ctx.config
    script = Path(cfg.repo_root) / "scripts" / "stack"
    epics = _epic_worktrees(cfg)
    ok = (not epics) or (script.is_file() and os.access(str(script), os.X_OK))
    rows: List[Dict[str, Any]] = []
    readable = True
    path = collisions_path(ctx)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            rows = [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
        except Exception:
            readable = False
    return [
        (
            "scripts/stack runs for every epic worktree",
            ok,
            "%s is missing or not executable, and %s print%s `stack sync` as the next move"
            % (script, ", ".join(epics) or "no card", "s" if len(epics) == 1 else ""),
        ),
        (
            "every slice pull request is on the card of its epic",
            readable and not rows,
            (
                "as of the last board run: %s. A feature and an epic have the same name. "
                "Add specs/epic.md if it is the epic, or rename one of them"
                % (collision_text(rows),)
            )
            if readable
            else "%s does not parse; `factory board` rewrites it" % (path,),
        ),
    ]
