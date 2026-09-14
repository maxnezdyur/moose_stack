"""Teardown and archive: the actor behind the ``teardown`` gate.

A gate that grants permission for an action nothing performs is a hole. This
extension closes it with two verbs and one number:

    factory teardown <feature> [--yes] [--force]
    factory archive  <feature> [--force]

``teardown`` prints the recipe by default and runs it only with ``--yes``. It
never runs from the launchd tick or from a hook: ``--yes`` additionally needs an
interactive terminal and refuses when a tick or hook marker is in the
environment. Every other guard is a refusal, not a warning:

    the ``teardown`` gate must be granted by Max
    no pull request for the card may still be OPEN
    no live session may have its cwd inside the worktree
    a held lease whose owner is alive refuses
    dirty trees, unpushed commits and never-fetched repos refuse without --force

The conda env is removed only when ``<worktree>/specs/.factory-env`` says
``env_reused: false``. Envs are shared per moose-dev pin (``moose-8.19`` serves
every worktree on that pin), so with no such file the env is left alone and the
recipe says why.

Before the first destructive command, teardown copies the size-capped gallery
out of ``<worktree>/specs/gallery/`` into ``<vault>/Artifacts/<feature>/gallery/``
and repoints ``<vault>/Gallery/<feature>`` at the copy. That is the only copy
this design ever makes of a gallery: everywhere else the vault links. It has to
happen here, because the figures are the one artifact of the work that survives
nowhere else once the checkout is gone, and every ``![[Gallery/...]]`` embed on
the feature note would otherwise resolve to nothing. The copy is idempotent and
never overwrites a differing file; that one gets a numbered suffix. Print mode
shows the step as the first line of the recipe, so the reader knows a copy
happens before anything is removed.

Reclaimable bytes are the only thing that actually motivates teardown, so the
note carries them whenever the ``teardown`` gate is pending or the checkout is
foreign. The number comes from ``factory board --du`` and is then cached in
``factory/state/<feature>.json``, so a note rebuild stays byte-identical.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config, probe
from .model import ARCHIVED, GRANTED, MERGED

OK, LOOK, REFUSED, MISSING = 0, 1, 2, 3

# Indirection so a test can record every command without running one.
RUN = probe.run

# Markers that say "you are inside the tick or a hook". Teardown never runs there.
NON_INTERACTIVE_MARKERS = (
    "FACTORY_FROM_EVENT",
    "FACTORY_TICK",
    "FACTORY_NONINTERACTIVE",
    "CLAUDE_HOOK",
)

ENV_FILE = os.path.join("specs", ".factory-env")


def _run(argv: List[str], timeout: int = 120) -> Tuple[str, bool]:
    return RUN(list(argv), timeout=timeout)


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


# --------------------------------------------------------------------------
# Sizes
# --------------------------------------------------------------------------


def _gb(kb: Optional[int]) -> str:
    """A size that reads the same on every run, from a kilobyte count."""
    if not isinstance(kb, int) or kb <= 0:
        return "unknown"
    if kb >= 1024 * 1024:
        return "%.1f GB" % (kb / 1024.0 / 1024.0,)
    if kb >= 1024:
        return "%d MB" % (kb // 1024,)
    return "%d kB" % (kb,)


def cached_kb(card_id: str, ctx: Any) -> Optional[int]:
    """The last measured worktree size, from obs if fresh, else from state."""
    obs = (ctx.obs or {}).get(card_id) or {}
    live = obs.get("reclaimable_kb")
    if isinstance(live, int) and live > 0:
        return live
    if ctx.state is None:
        return None
    try:
        rec = (ctx.state.read(card_id) or {}).get("teardown") or {}
    except Exception:
        return None
    kb = rec.get("reclaimable_kb")
    return kb if isinstance(kb, int) and kb > 0 else None


def collect(ctx: Any) -> None:
    """Persist a measured worktree size so a later run prints the same number.

    ``du -sk`` over nine MOOSE trees is far too slow for every board run, so
    ``factory board --du`` measures and this caches. Writes only under state/.
    """
    if ctx.state is None:
        return
    for feature, obs in (ctx.obs or {}).items():
        kb = obs.get("reclaimable_kb")
        if not isinstance(kb, int) or kb <= 0:
            continue
        try:
            data = ctx.state.read(feature)
            rec = dict(data.get("teardown") or {})
            if rec.get("reclaimable_kb") == kb:
                continue
            rec["reclaimable_kb"] = kb
            rec["measured"] = ctx.now
            data["teardown"] = rec
            ctx.state.write(feature, data, ctx.dry_run)
        except Exception as exc:
            ctx.log("ext_teardown.collect could not cache %s: %s" % (feature, exc))


# --------------------------------------------------------------------------
# specs/.factory-env
# --------------------------------------------------------------------------


def _parse_env_text(text: str) -> Dict[str, Any]:
    try:
        import yaml

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    out: Dict[str, Any] = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        out[key.strip()] = value.strip().strip("'\"")
    return out


def _as_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "yes", "1"):
            return True
        if low in ("false", "no", "0"):
            return False
    return None


def env_record(worktree: Optional[str]) -> Dict[str, Any]:
    """What ``specs/.factory-env`` says about this worktree's conda env."""
    rec: Dict[str, Any] = {
        "path": None,
        "present": False,
        "env_name": None,
        "env_reused": None,
        "removable": False,
        "why": "no specs/.factory-env: a shared env cannot be told from a private "
        "one, so the env is left alone",
    }
    if not worktree:
        return rec
    path = Path(worktree) / ENV_FILE
    rec["path"] = str(path)
    text, ok = probe._read_text(path)
    if not ok or not text:
        return rec
    data = _parse_env_text(text)
    rec["present"] = True
    rec["env_name"] = data.get("env_name") or data.get("env") or None
    rec["env_reused"] = _as_bool(data.get("env_reused"))
    rec["donor_sha"] = data.get("donor_sha")
    if rec["env_reused"] is True:
        rec["why"] = "env_reused: true, so the env is shared with other worktrees"
    elif rec["env_reused"] is None:
        rec["why"] = "specs/.factory-env has no env_reused key, so the env is left alone"
    elif not rec["env_name"]:
        rec["why"] = "env_reused: false but no env_name, so there is nothing to remove"
    else:
        rec["removable"] = True
        rec["why"] = "env_reused: false, so this env was created for this worktree alone"
    return rec


def _conda_prefixes() -> Dict[str, str]:
    """``{env name: prefix}`` from ``conda env list``. Empty when conda is absent."""
    if not shutil.which("conda"):
        return {}
    out, ok = _run(["conda", "env", "list"], timeout=60)
    if not ok:
        return {}
    table: Dict[str, str] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.replace("*", " ").split()
        if len(parts) >= 2 and parts[-1].startswith("/"):
            table[parts[0]] = parts[-1]
    return table


def _du_kb(path: Optional[str]) -> Optional[int]:
    if not path or not Path(path).is_dir():
        return None
    out, ok = _run(["du", "-sk", str(path)], timeout=300)
    if not ok:
        return None
    try:
        return int(out.split()[0])
    except Exception:
        return None


# --------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------


def _checkouts(card: Any, cfg: config.Config) -> List[Tuple[str, str, str]]:
    """``[(repo, canonical repo dir, checkout path)]`` in removal order."""
    wt = card.worktree
    rows: List[Tuple[str, str, str]] = []
    if not wt:
        return rows
    for repo in reversed(list(config.SUBMODULES)):
        rows.append((repo, str(cfg.repo_root / repo), str(Path(wt) / repo)))
    rows.append((config.META, str(cfg.repo_root), str(wt)))
    return rows


def _branch_exists(repo_dir: str, branch: str) -> Optional[bool]:
    out, ok = _run(
        ["git", "-C", repo_dir, "branch", "--list", "--format=%(refname:short)", branch]
    )
    if not ok:
        return None
    return branch in [line.strip() for line in out.splitlines() if line.strip()]


def plan(card: Any, ctx: Any, force: bool = False, measure: bool = True) -> Dict[str, Any]:
    """Everything teardown would do, with every reason it must not."""
    cfg = ctx.config
    feature = card.id
    obs = (ctx.obs or {}).get(feature) or {}
    blockers: List[str] = []
    warnings: List[str] = []

    if card.gate_state("teardown") != GRANTED:
        blockers.append(
            "gate teardown is pending: `%s grant %s teardown` after the PR merges"
            % (_factory(cfg), feature)
        )
    open_prs = card.open_prs()
    for pr in open_prs:
        blockers.append(
            "%s #%s is still OPEN: merge or close it first"
            % (pr.get("repo") or "?", pr.get("number"))
        )
    merged = card.merged_prs()
    if not merged and not open_prs:
        warnings.append("no merged pull request on this card: nothing was landed")

    for row in obs.get("sessions") or []:
        blockers.append(
            "a live session (%s) has its cwd in this worktree: `claude stop %s`"
            % (row.get("sessionId") or row.get("name") or "?", row.get("jobId") or "?")
        )
    lease = obs.get("lease") or {}
    if lease.get("held") and lease.get("owner_alive") is not False:
        blockers.append(
            ".factory-lease is held and its owner may be alive: `factory release %s`" % (feature,)
        )

    soft: List[str] = []
    for repo, st in sorted((card.repos or {}).items()):
        if st.get("dirty"):
            soft.append("%s has %s dirty files" % (repo, st["dirty"]))
        if st.get("pushed") is False and (st.get("ahead") or 0) > 0:
            soft.append("%s is %s commits ahead and was never pushed" % (repo, st["ahead"]))
        elif (st.get("ahead") or 0) > 0 and st.get("pushed") is None:
            soft.append("%s is %s commits ahead of %s" % (repo, st["ahead"], st.get("base")))
    if soft and not force:
        for line in soft:
            blockers.append("%s (--force overrides)" % (line,))
    else:
        warnings.extend(soft)

    if not card.worktree:
        warnings.append("no worktree on disk: only the branches and the note remain")
    elif not Path(card.worktree).is_dir():
        warnings.append("%s is registered but absent on disk" % (card.worktree,))
    if card.has("foreign-worktree"):
        # A blocker, and --force does not lift it. Decision 12 reserves the two
        # legacy checkouts for Max by hand: the board flags them and prints the
        # recipe, and no script runs `git worktree remove` on one.
        blockers.append(
            "foreign checkout outside %s: it predates the naming rule, and a legacy "
            "checkout is removed by hand. The commands above are the recipe; run them "
            "yourself. No --force lifts this." % (config.display_path(cfg.worktree_root),)
        )

    # ---- the commands ----------------------------------------------------
    commands: List[Tuple[str, List[str]]] = []
    registered = _registered(card, cfg) if card.worktree else {}
    for repo, repo_dir, checkout in _checkouts(card, cfg):
        if card.worktree and checkout not in registered:
            warnings.append("%s is not a registered worktree of %s" % (checkout, repo))
            continue
        argv = ["git", "-C", repo_dir, "worktree", "remove"]
        if force:
            argv.append("--force")
        argv.append(checkout)
        commands.append(("remove the %s checkout" % (repo,), argv))
    for repo in config.REPOS:
        repo_dir = str(cfg.repo_root if repo == config.META else cfg.repo_root / repo)
        commands.append(("prune %s worktrees" % (repo,), ["git", "-C", repo_dir, "worktree", "prune"]))

    branches: List[Tuple[str, str]] = []
    for repo in config.REPOS:
        repo_dir = str(cfg.repo_root if repo == config.META else cfg.repo_root / repo)
        exists = _branch_exists(repo_dir, feature)
        if exists is None:
            warnings.append("could not list branches in %s" % (repo_dir,))
            continue
        if exists:
            branches.append((repo, repo_dir))
            commands.append(
                ("delete branch %s in %s" % (feature, repo), ["git", "-C", repo_dir, "branch", "-D", feature])
            )
    if not branches:
        warnings.append("no local branch named %s in any of the four repos" % (feature,))

    env = env_record(card.worktree)
    if env.get("removable") and env.get("env_name"):
        commands.append(
            ("remove the conda env %s" % (env["env_name"],),
             ["conda", "env", "remove", "-y", "-n", str(env["env_name"])]),
        )

    # ---- the number ------------------------------------------------------
    sizes: Dict[str, Any] = {"worktree_kb": None, "env_kb": None, "total_kb": None}
    if measure:
        sizes["worktree_kb"] = _du_kb(card.worktree)
        if env.get("removable") and env.get("env_name"):
            prefix = _conda_prefixes().get(str(env["env_name"]))
            sizes["env_prefix"] = prefix
            sizes["env_kb"] = _du_kb(prefix)
    if sizes["worktree_kb"] is None:
        sizes["worktree_kb"] = cached_kb(feature, ctx)
    total = sum(v for v in (sizes["worktree_kb"], sizes["env_kb"]) if isinstance(v, int))
    sizes["total_kb"] = total or None

    # ---- the gallery, measured now and copied before the first command ---
    gallery = _gallery_plan(card, ctx)

    return {
        "feature": feature,
        "worktree": card.worktree,
        "gallery": gallery,
        "commands": commands,
        "blockers": blockers,
        "warnings": warnings,
        "branches": branches,
        "env": env,
        "sizes": sizes,
        "merged": merged,
    }


def _gallery(card: Any, ctx: Any) -> Dict[str, Any]:
    """The gallery listing for one card, or an empty record.

    Imported inside the function on purpose: two extensions that import each
    other at module scope are one edit away from a circular import, and
    ``render.extensions()`` loads both in alphabetical order regardless.
    """
    try:
        from . import ext_gallery

        return ext_gallery.record(ctx, card)
    except Exception as exc:
        ctx.log("teardown: cannot read the gallery for %s: %s" % (card.id, exc))
        return {}


def _gallery_plan(card: Any, ctx: Any) -> Dict[str, Any]:
    """``{files, kb, dest, over_cap}``: what the copy step will move."""
    rec = _gallery(card, ctx)
    out: Dict[str, Any] = {"files": 0, "kb": 0, "dest": None, "over_cap": []}
    if not rec or rec.get("source") != "worktree":
        # Already rescued, or there is no gallery. Either way nothing to copy:
        # the copy reads the worktree, which is the thing about to disappear.
        return out
    out["files"] = int(rec.get("count") or 0)
    out["kb"] = int(rec.get("total_kb") or 0)
    out["over_cap"] = [str(row.get("name")) for row in (rec.get("over_cap") or [])]
    try:
        from . import ext_gallery

        out["dest"] = str(ext_gallery.artifacts_gallery(ctx, card.id))
    except Exception:
        out["dest"] = None
    return out


def preserve_gallery(card: Any, ctx: Any) -> Dict[str, Any]:
    """Run the copy. Called once, immediately before the first removal.

    Never raises and never blocks the teardown: a figure that could not be
    copied is a line on the terminal, not a reason to leave a merged worktree
    on disk forever.
    """
    try:
        from . import ext_gallery

        return ext_gallery.preserve(ctx, card.id, card.worktree)
    except Exception as exc:
        ctx.log("teardown: the gallery copy for %s failed: %s" % (card.id, exc))
        return {"failed": 1, "files": 0, "copied": 0, "same": 0, "suffixed": 0}


def _registered_paths(repo_dir: str) -> Tuple[List[str], bool]:
    """The worktree paths one repository knows about. Through ``RUN``, so a test
    records the call instead of shelling out."""
    out, ok = _run(["git", "-C", repo_dir, "worktree", "list", "--porcelain"])
    if not ok:
        return ([], False)
    paths = [
        line[len("worktree "):].strip()
        for line in out.splitlines()
        if line.startswith("worktree ")
    ]
    return (paths, True)


def _registered(card: Any, cfg: config.Config) -> Dict[str, str]:
    """``{checkout path: repo}`` for every checkout git still knows about."""
    out: Dict[str, str] = {}
    wt = card.worktree
    if not wt:
        return out
    for repo in config.REPOS:
        repo_dir = str(cfg.repo_root if repo == config.META else cfg.repo_root / repo)
        paths, ok = _registered_paths(repo_dir)
        if not ok:
            continue
        want = str(wt) if repo == config.META else str(Path(wt) / repo)
        for path in paths:
            if os.path.normpath(path) == os.path.normpath(want):
                out[want] = repo
    return out


def _factory(cfg: config.Config) -> str:
    """The launcher, as a command to paste: tilde-collapsed, never a user name."""
    return config.display_path(cfg.repo_root / "factory" / "factory")


# --------------------------------------------------------------------------
# Printing
# --------------------------------------------------------------------------


def format_plan(planned: Dict[str, Any], cfg: config.Config) -> List[str]:
    out: List[str] = []
    sizes = planned["sizes"]
    out.append("teardown %s" % (planned["feature"],))
    out.append(
        "  reclaimable  %s in the worktree, %s in the env (total %s)"
        % (_gb(sizes.get("worktree_kb")), _gb(sizes.get("env_kb")), _gb(sizes.get("total_kb")))
    )
    out.append("  env          %s" % (planned["env"]["why"],))
    if planned["merged"]:
        out.append(
            "  merged       %s"
            % (", ".join("%s #%s" % (p.get("repo"), p.get("number")) for p in planned["merged"]),)
        )
    gallery = planned.get("gallery") or {}
    if gallery.get("files"):
        out.append(
            "  gallery      %d file(s), %s -> %s   (copied before anything is removed)"
            % (
                gallery["files"],
                _gb(gallery.get("kb")),
                config.display_path(gallery.get("dest")),
            )
        )
        if gallery.get("over_cap"):
            out.append(
                "               over the size cap, not copied: %s"
                % (", ".join(gallery["over_cap"]),)
            )
    for line in planned["warnings"]:
        out.append("  note         %s" % (line,))
    for line in planned["blockers"]:
        out.append("  BLOCKED      %s" % (line,))
    out.append("")
    out.append("  # the recipe, in order")
    if gallery.get("files"):
        out.append(
            "  # step 0: copy %d gallery file(s) into %s and repoint Gallery/%s at the copy"
            % (
                gallery["files"],
                config.display_path(gallery.get("dest")),
                planned["feature"],
            )
        )
        out.append(
            "  #         `factory teardown %s --yes` does this itself; there is no "
            "command to paste." % (planned["feature"],)
        )
    for label, argv in planned["commands"]:
        out.append("  %s   # %s" % (" ".join(argv), label))
    out.append(
        "  # if %s survives, inspect it and remove it by hand. No script runs rm -rf."
        % (planned["worktree"] or "the worktree",)
    )
    return out


# --------------------------------------------------------------------------
# Verbs
# --------------------------------------------------------------------------


def _destructive_refusal(yes: bool) -> Optional[str]:
    """Why this run may not destroy anything. ``None`` means it may."""
    if not yes:
        return "print mode. Pass --yes to run it."
    for var in NON_INTERACTIVE_MARKERS:
        if os.environ.get(var):
            return (
                "refused: teardown never runs from the tick or a hook (%s is set)" % (var,)
            )
    try:
        tty = sys.stdin.isatty()
    except Exception:
        tty = False
    if not tty:
        return (
            "refused: --yes needs an interactive terminal. The tick, a hook and a "
            "background agent have none."
        )
    return None


def _split(rest: List[str]) -> Tuple[Optional[str], Dict[str, bool], List[str]]:
    flags = {"yes": False, "force": False, "dry_run": False}
    feature: Optional[str] = None
    unknown: List[str] = []
    for arg in rest or []:
        if arg in ("--yes", "-y"):
            flags["yes"] = True
        elif arg == "--force":
            flags["force"] = True
        elif arg in ("--dry-run", "-n"):
            flags["dry_run"] = True
        elif arg.startswith("-"):
            unknown.append(arg)
        elif feature is None:
            feature = arg
        else:
            unknown.append(arg)
    return (feature, flags, unknown)


def run_teardown(rest: List[str], ctx: Any) -> int:
    config.hostname_guard()
    cfg = ctx.config
    feature, flags, unknown = _split(rest)
    if unknown:
        _err("usage: factory teardown <feature> [--yes] [--force]")
        return REFUSED
    if not feature:
        _err("usage: factory teardown <feature> [--yes] [--force]")
        return REFUSED
    config.validate_id(feature)
    card = ctx.card(feature)
    if card is None:
        _err(
            "no card %r. Known: %s"
            % (feature, ", ".join(sorted(c.id for c in ctx.cards)))
        )
        return MISSING

    planned = plan(card, ctx, force=flags["force"])
    for line in format_plan(planned, cfg):
        print(line)

    if planned["blockers"]:
        print("")
        print(
            "%d blocker(s) above: teardown would refuse to run."
            % (len(planned["blockers"]),)
        )
        # Print mode reported; it neither wrote nor refused a write, so it is not
        # exit 2. A --yes run against the same blockers is.
        return REFUSED if flags["yes"] else OK

    refusal = _destructive_refusal(flags["yes"])
    if refusal is not None:
        print("")
        print(refusal)
        return OK if not flags["yes"] else REFUSED
    if flags["dry_run"] or ctx.dry_run:
        print("")
        print("dry run: nothing was removed.")
        return OK

    answer = ""
    try:
        answer = input("type the feature name to confirm teardown: ").strip()
    except Exception:
        answer = ""
    if answer != feature:
        print("aborted: %r is not %r" % (answer, feature))
        return REFUSED

    # The gallery is copied out first, and only then does anything get removed.
    # Reversing these two loses every figure the feature produced: the worktree
    # copy is the only one, and `git worktree remove` takes the directory with
    # it. The copy is idempotent, so a teardown re-run after a failed command
    # copies nothing a second time.
    kept = preserve_gallery(card, ctx)
    if kept.get("files"):
        print(
            "ok    gallery: %d copied, %d unchanged, %d suffixed, %d failed -> %s"
            % (
                int(kept.get("copied") or 0),
                int(kept.get("same") or 0),
                int(kept.get("suffixed") or 0),
                int(kept.get("failed") or 0),
                config.display_path(kept.get("dest")),
            )
        )
        if kept.get("link_status") in ("created", "repaired", "same"):
            print(
                "ok    Gallery/%s now points at the rescued copy (%s)"
                % (feature, kept.get("link_status"))
            )

    failed = 0
    for label, argv in planned["commands"]:
        out, ok = _run(argv, timeout=600)
        print("%s  %s" % ("ok  " if ok else "FAIL", " ".join(argv)))
        if not ok:
            failed += 1
            _err("  %s: %s" % (label, (out or "").strip().splitlines()[:1]))
            break
    event = {
        "at": ctx.now,
        "event": "teardown" if not failed else "teardown-failed",
        "reclaimable_kb": planned["sizes"].get("total_kb"),
        "gallery_kept": int(kept.get("copied") or 0) + int(kept.get("same") or 0)
        + int(kept.get("suffixed") or 0),
        "why": "worktree and branches removed" if not failed else "a command failed",
    }
    if ctx.timeline is not None:
        ctx.timeline.append(feature, event)
    if failed:
        return LOOK
    print("")
    print(
        "reclaimed about %s. Now: %s archive %s"
        % (_gb(planned["sizes"].get("total_kb")), _factory(cfg), feature)
    )
    return OK


def run_archive(rest: List[str], ctx: Any) -> int:
    """``git mv`` the note into ``Archive/``. The note is an output; the move
    is recorded in git so ``git log`` still answers what happened."""
    config.hostname_guard()
    cfg = ctx.config
    feature, flags, unknown = _split(rest)
    if unknown or not feature:
        _err("usage: factory archive <feature> [--force] [--dry-run]")
        return REFUSED
    config.validate_id(feature)
    note = cfg.note_path(feature)
    if not note.is_file():
        _err("no note at %s" % (note,))
        return MISSING

    card = ctx.card(feature)
    reasons: List[str] = []
    if card is not None:
        if card.worktree and Path(card.worktree).is_dir():
            reasons.append("the worktree still exists at %s" % (card.worktree,))
        if card.open_prs():
            reasons.append(
                "an open PR remains: %s"
                % (", ".join("%s #%s" % (p.get("repo"), p.get("number")) for p in card.open_prs()),)
            )
        if not reasons:
            reasons.append(
                "the card is still derived (lane %s), so the next board run rewrites "
                "the note in Features/" % (card.lane,)
            )
    if reasons and not flags["force"]:
        for line in reasons:
            _err("refused: %s" % (line,))
        _err("archive when the worktree and the PR are both gone, or pass --force")
        return REFUSED

    dest = cfg.archive_dir / note.name
    if dest.exists():
        _err("refused: %s already exists" % (dest,))
        return REFUSED
    if flags["dry_run"] or ctx.dry_run:
        print("would move %s -> %s" % (note, dest))
        return OK

    cfg.archive_dir.mkdir(parents=True, exist_ok=True)
    moved = False
    if (cfg.vault / ".git").exists():
        _, ok = _run(["git", "-C", str(cfg.vault), "mv", str(note), str(dest)])
        moved = ok
    if not moved:
        os.replace(str(note), str(dest))
    print("archived %s -> %s%s" % (note.name, dest, "" if moved else " (plain move)"))
    if ctx.timeline is not None:
        ctx.timeline.append(
            feature,
            {"at": ctx.now, "event": "archived", "why": "note moved into Archive/"},
        )
    return OK


# --------------------------------------------------------------------------
# The note section
# --------------------------------------------------------------------------


def _wants_section(card: Any) -> bool:
    """The gate is pending, or the checkout is foreign. Both want the number.

    A card with no worktree and no foreign checkout has nothing to reclaim, so
    it gets no section: the bytes are the whole point.
    """
    if not (card.worktree or card.has("foreign-worktree")):
        return False
    return card.gate_state("teardown") != GRANTED or card.has("foreign-worktree")


def note_sections(card: Any, ctx: Any) -> List[Tuple[str, str, int]]:
    if not _wants_section(card):
        return []
    cfg = ctx.config
    kb = cached_kb(card.id, ctx)
    env = env_record(card.worktree)
    lines: List[str] = []
    if kb:
        lines.append(
            "- Reclaimable: **%s** in `%s`" % (_gb(kb), config.display_path(card.worktree))
        )
    else:
        lines.append(
            "- Reclaimable: not measured yet. `%s board --du` measures it once and "
            "caches the number." % (_factory(cfg),)
        )
    lines.append("- Conda env: %s" % (env["why"],))
    state = card.gate_state("teardown")
    if state == GRANTED:
        lines.append("- Gate `teardown`: granted. Nothing has run yet.")
    elif card.lane in (MERGED, ARCHIVED):
        lines.append("- Gate `teardown`: pending, and the PR has merged. It is yours to grant.")
    else:
        lines.append("- Gate `teardown`: pending. Not until the PR merges.")
    if card.has("foreign-worktree"):
        lines.append(
            "- This checkout is outside `%s`. It predates the naming rule: tear it "
            "down rather than rename it." % (config.display_path(cfg.worktree_root),)
        )
    lines.append("")
    lines.append("```")
    lines.append("%s teardown %s          # print the recipe" % (_factory(cfg), card.id))
    lines.append("%s teardown %s --yes    # run it, in a terminal, after the gate" % (_factory(cfg), card.id))
    lines.append("```")
    return [("Teardown", "\n".join(lines), 60)]


VERBS = {"teardown": run_teardown, "archive": run_archive}

HELP = {
    "teardown": "print the teardown recipe; --yes runs it in a terminal",
    "archive": "git mv one feature note into Archive/",
}
