"""The verbs. The CLI prints; library code never does.

    board                   probe, derive, rewrite every output
    status [<feature>]      print Home.md, or one note. Touches nothing.
    next <feature>          the single next move and why
    set <feature> k=v       write a namespaced field. Refuses a projector field.
    grant <feature> <gate>  one monotonic attributed gate grant
    doctor                  what is misconfigured
    commit                  stage and commit the vault, no trailers
    dump-obs <feature>      one card's probe snapshot, for debugging
    version                 the package version and the resolved paths

Exit codes: 0 ok, 1 a human should look, 2 a refused write, 3 a missing path or
the wrong host. Every verb that writes accepts ``--dry-run``.

Extensions add verbs through ``VERBS`` and ``HELP`` in ``tool/ext_<name>.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import config, derive, gates as gates_mod, probe, render, snapshot, timeline as tl
from .model import GATES, POSTURE, Ctx

OK, LOOK, REFUSED, MISSING = 0, 1, 2, 3

# Fields the projector owns. Hand-written state is the main way an agent
# invents a transition, so the refusal is explicit and names the owner.
OWNED_FIELDS = (
    "id",
    "lane",
    "lane_rank",
    "posture",
    "flags",
    "next_action",
    "prs",
    "gates",
    "repos",
    "build",
    "session",
    "provenance",
    "worktree",
)

# Namespaces `factory set` accepts. A key must carry one.
SET_NAMESPACES = ("blueprint", "notes", "env", "hint", "label", "study")


def err(msg: str) -> None:
    print(msg, file=sys.stderr)


# --------------------------------------------------------------------------
# Context
# --------------------------------------------------------------------------


def build_ctx(
    cfg: config.Config,
    dry_run: bool = False,
    now: Optional[str] = None,
    want_du: bool = False,
    quiet: bool = False,
) -> Ctx:
    """One probe round, then the pure derivation. The only writer of state."""
    config.hostname_guard()
    config.require_vault(cfg)

    store = snapshot.Store(cfg.state_dir)
    obs, meta = probe.round_all(cfg, want_du=want_du)
    store.carry_forward(obs)

    # The one demotion cause with no probe behind it. `factory abandon` writes a
    # timeline line in the vault, which is committed and durable, and that line
    # is what makes the ABANDONED lane reachable. Reading it here keeps derive
    # pure: it still sees only an observation.
    reader = tl.TimelineWriter(cfg.timeline_dir, dry_run=True)
    for feature, card in obs.items():
        for rec in reader.read(feature):
            if rec.get("event") == "abandoned":
                card["abandoned"] = {"at": rec.get("at"), "why": rec.get("why")}
            elif rec.get("event") == "unabandoned":
                card.pop("abandoned", None)

    ctx = Ctx(
        config=cfg,
        obs=obs,
        cards=[],
        state_dir=cfg.state_dir,
        vault_dir=cfg.vault,
        now=now or probe.iso(),
        meta=meta,
        timeline=tl.TimelineWriter(cfg.timeline_dir, dry_run),
        gates=gates_mod.GateStore(cfg.gates_dir, dry_run),
        state=store,
        dry_run=dry_run,
        _log=(None if quiet else err),
    )

    # Extensions collect before derive; they may write only under state/ and the
    # vault's durable directories.
    for mod in render.extensions():
        fn = getattr(mod, "collect", None)
        if fn is None:
            continue
        try:
            fn(ctx)
        except Exception as exc:
            ctx.log("extension %s.collect raised: %s" % (mod.__name__, exc))

    # Read the gate checkboxes and the observed facts before composing anything.
    records: Dict[str, Dict[str, Any]] = {}
    for feature in sorted(obs):
        try:
            records[feature] = gates_mod.sync(
                ctx.gates, feature, obs[feature], ctx.now, ctx.timeline
            )
        except Exception as exc:
            ctx.log("gate sync failed for %s: %s" % (feature, exc))
            records[feature] = ctx.gates.get(feature)

    class _Records:
        """Hands derive the already-synced records without a second read."""

        def __init__(self, store: Any, table: Dict[str, Dict[str, Any]]):
            self._store, self._table = store, table

        def get(self, feature: str) -> Dict[str, Any]:
            return self._table.get(feature) or self._store.get(feature)

        def grant(self, *a: Any, **k: Any) -> bool:
            return self._store.grant(*a, **k)

        def features(self) -> List[str]:
            return self._store.features()

    real_gates = ctx.gates
    ctx.gates = _Records(real_gates, records)
    ctx.cards = derive.derive_all(ctx)
    ctx.gates = real_gates

    # Extension flags, applied after derive.
    for mod in render.extensions():
        fn = getattr(mod, "card_flags", None)
        if fn is None:
            continue
        for card in ctx.cards:
            try:
                for flag in fn(card, obs.get(card.id) or {}, ctx) or []:
                    card.add_flag(str(flag))
            except Exception as exc:
                ctx.log("extension %s.card_flags raised: %s" % (mod.__name__, exc))

    _adopt_and_nag(ctx)
    store.remember(obs, dry_run)
    return ctx


def _adopt_and_nag(ctx: Ctx) -> None:
    """One adoption line per new card, and one heads-up at 14 and 45 days."""
    now_ts = derive.ts_of(ctx.now) or 0.0
    for card in ctx.cards:
        if not ctx.timeline.has(card.id, "adopted"):
            ctx.timeline.append(
                card.id,
                {
                    "at": ctx.now,
                    "event": "adopted",
                    "provenance": card.provenance,
                    "lane": card.lane,
                    "why": "board adopted this feature",
                },
            )
        if card.posture != "parked":
            continue
        silent = derive.silent_days(ctx.obs.get(card.id) or {}, now_ts)
        for days in ctx.config.nag_days:
            if ctx.state.heads_up_due(card.id, days, silent):
                ctx.timeline.append(
                    card.id,
                    {
                        "at": ctx.now,
                        "event": "heads-up",
                        "days": days,
                        "why": "parked and silent for %s days" % (silent,),
                    },
                )
                ctx.state.heads_up_record(card.id, days, ctx.now, ctx.dry_run)


# --------------------------------------------------------------------------
# Verbs
# --------------------------------------------------------------------------


def run_board(args: Any, cfg: config.Config) -> int:
    ctx = build_ctx(cfg, dry_run=args.dry_run, want_du=args.du)
    result = render.sync(ctx)
    ctx.state.manifest_commit(cfg, args.dry_run)
    counts = result["counts"]
    print(
        "board: %d cards (%s). notes written %d, unchanged %d, refused %d. Home %s."
        % (
            len(ctx.cards),
            ", ".join(
                "%s %d" % (p, len(ctx.by_posture(p))) for p in POSTURE if ctx.by_posture(p)
            )
            or "none",
            counts.get("written", 0),
            counts.get("skipped", 0),
            counts.get("refused", 0),
            counts.get("home"),
        )
    )
    if ctx.meta.get("stale"):
        print("unknown this run: %s (carried forward)" % (", ".join(ctx.meta["stale"]),))
    ny = sorted(ctx.by_posture("needs-you"), key=lambda c: c.priority_key())
    for card in ny[: cfg.needs_you_cap]:
        print("  %-22s %-12s %s" % (card.id, card.next_action.verb, card.next_action.why))
    if result["refused"]:
        err("refused: %s (restore the four markers)" % (", ".join(result["refused"]),))
        return REFUSED
    if any(c.has("error") for c in ctx.cards):
        return LOOK
    return OK


def run_status(args: Any, cfg: config.Config) -> int:
    config.hostname_guard()
    config.require_vault(cfg)
    if args.feature:
        path = cfg.note_path(args.feature)
        if not path.is_file():
            err("no note for %s. Run `factory board` first." % (args.feature,))
            return MISSING
        text = path.read_text()
        if getattr(args, "head", False):
            # The head block verbatim: the next move and the gates, which is
            # what a session-start hook has room for. Falls back to the whole
            # note when a marker is absent, because a marker-less note is the
            # renderer's business, not this verb's.
            begin, end = probe.MARKERS[0], probe.MARKERS[1]
            if begin in text and end in text:
                text = text.split(begin, 1)[1].split(end, 1)[0].strip() + "\n"
        sys.stdout.write(text)
        return OK
    if not cfg.home_note.is_file():
        err("no Home.md yet. Run `factory board`.")
        return MISSING
    sys.stdout.write(cfg.home_note.read_text())
    return OK


def run_next(args: Any, cfg: config.Config) -> int:
    ctx = build_ctx(cfg, dry_run=True, quiet=True)
    card = ctx.card(args.feature)
    if card is None:
        err(
            "no card %r. Known: %s"
            % (args.feature, ", ".join(sorted(c.id for c in ctx.cards)))
        )
        return MISSING
    na = card.next_action
    print("%s: %s" % (card.id, na.verb))
    print("  lane     %s (%s)" % (card.lane, card.gates.get("_proof") or ""))
    print("  posture  %s" % (card.posture,))
    if card.flags:
        print("  flags    %s" % (", ".join(card.flags),))
    print("  why      %s" % (na.why,))
    if na.command:
        print("  run      %s" % (na.command,))
    return OK


def run_set(args: Any, cfg: config.Config) -> int:
    config.hostname_guard()
    try:
        config.validate_id(args.feature)
    except ValueError as exc:
        err(str(exc))
        return REFUSED
    if "=" not in args.assignment:
        err("usage: factory set <feature> key=value")
        return REFUSED
    key, value = args.assignment.split("=", 1)
    key = key.strip()
    root = key.split(".", 1)[0]
    if root in OWNED_FIELDS:
        err("refused: %s is owned by the projector, not by hand" % (root,))
        return REFUSED
    if "." not in key or root not in SET_NAMESPACES:
        err(
            "refused: %r needs a namespace. One of: %s"
            % (key, ", ".join("%s.<field>" % n for n in SET_NAMESPACES))
        )
        return REFUSED
    store = snapshot.Store(cfg.state_dir)
    data = store.read(args.feature)
    table = dict(data.get("set") or {})
    table[key] = value
    data["set"] = table
    store.write(args.feature, data, args.dry_run)
    print("set %s %s=%s%s" % (args.feature, key, value, " (dry run)" if args.dry_run else ""))
    print("recorded as an annotation; it renders in the card's Annotations section")
    return OK


def run_abandon(args: Any, cfg: config.Config) -> int:
    """Record that Max has given up on a card, with a reason.

    The missing input channel: ``derive`` has read ``obs["abandoned"]`` since the
    first version and nothing ever wrote it, so the ABANDONED lane and its
    "out of sight" posture were unreachable and a card Max had dropped stayed in
    needs-you forever. The record is a timeline line in the vault, because that
    is the durable half of the state; ``rm -rf factory/state`` must not resurrect
    a feature.
    """
    config.hostname_guard()
    config.require_vault(cfg)
    config.validate_id(args.feature)
    why = (args.why or "").strip()
    if not why:
        err("usage: factory abandon <feature> \"<reason>\"  (the reason is the point)")
        return REFUSED
    now = probe.iso()
    writer = tl.TimelineWriter(cfg.timeline_dir, args.dry_run)
    wrote = writer.append(
        args.feature,
        {"at": now, "event": "abandoned", "why": why, "by": "max"},
    )
    print(
        "%s abandoned: %s%s"
        % (args.feature, why, "" if wrote else " (dry run)")
    )
    print("the next `factory board` moves it to lane abandoned, posture done")
    return OK


def run_grant(args: Any, cfg: config.Config) -> int:
    config.hostname_guard()
    config.require_vault(cfg)
    if args.gate not in GATES:
        err("unknown gate %r: one of %s" % (args.gate, ", ".join(GATES)))
        return REFUSED
    store = gates_mod.GateStore(cfg.gates_dir, args.dry_run)
    now = probe.iso()
    changed = store.grant(args.feature, args.gate, now, by="max", via="verb")
    if changed and not args.dry_run:
        tl.TimelineWriter(cfg.timeline_dir).append(
            args.feature,
            {"at": now, "event": "gate-granted", "gate": args.gate, "via": "verb"},
        )
    print(
        "%s %s: %s"
        % (
            args.feature,
            args.gate,
            "granted" if changed else "already granted (gates never ungrant)",
        )
    )
    return OK


def run_commit(args: Any, cfg: config.Config) -> int:
    """Stage and commit the vault. No Co-Authored-By and no Claude-Session line."""
    config.hostname_guard()
    config.require_vault(cfg)
    if not (cfg.vault / ".git").exists():
        err("%s is not a git repository" % (cfg.vault,))
        return MISSING
    out, ok = probe.run(["git", "-C", str(cfg.vault), "status", "--porcelain"])
    if not ok:
        err("git status failed in %s" % (cfg.vault,))
        return LOOK
    if not out.strip():
        print("vault clean: nothing to commit")
        return OK
    # A board run always recreates Home.md, so an absent Home.md means the
    # generated view is mid-rebuild (or was deleted by hand). Committing then
    # records the deletion of every note under a message that reads like a
    # normal board commit. Refuse, and say what to run.
    if not (cfg.vault / "Home.md").exists():
        err(
            "refusing to commit: %s is absent, so the generated view is not built. "
            "Run `factory board` first, then commit." % (cfg.vault / "Home.md",)
        )
        return REFUSED
    if args.dry_run:
        print("would commit %d paths in %s" % (len(out.strip().splitlines()), cfg.vault))
        return OK
    _, ok = probe.run(["git", "-C", str(cfg.vault), "add", "-A"])
    if not ok:
        err("git add failed")
        return LOOK
    msg = "board %s" % (probe.iso(),)
    out, ok = probe.run(["git", "-C", str(cfg.vault), "commit", "-m", msg])
    if not ok:
        err("git commit failed: %s" % (out.strip().splitlines()[:1],))
        return LOOK
    print("committed: %s" % (msg,))
    return OK


def dump_target(cfg: config.Config, out: str) -> Path:
    """Where ``--out`` lands. A bare name goes to the scratch directory.

    ``state/dump/`` is scratch: gitignored, and thrown away with the rest of
    ``state/``. A path with a directory in it is taken as given, so a scratch
    path outside the package still works.
    """
    if out.startswith(("/", "~", "./", "../")) or "/" in out:
        return Path(out).expanduser()
    return cfg.state_dir / "dump" / out


def run_dump_obs(args: Any, cfg: config.Config) -> int:
    """The complete, pure input of ``derive_card``, for debugging one card."""
    ctx = build_ctx(cfg, dry_run=True, quiet=True)
    feature = args.feature
    if feature not in ctx.obs:
        err("no card %r" % (feature,))
        return MISSING
    card = ctx.card(feature)
    payload = {
        "feature": feature,
        "now": ctx.now,
        "obs": ctx.obs[feature],
        "prev": {},
        "gates": ctx.gates.get(feature),
        "expect": {
            "lane": card.lane if card else None,
            "flags": card.flags if card else None,
            "posture": card.posture if card else None,
            "next_verb": card.next_action.verb if card else None,
            "next_why": card.next_action.why if card else None,
        },
    }
    text = json.dumps(payload, indent=1, sort_keys=True, default=str)
    if args.out:
        path = dump_target(cfg, str(args.out))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n")
        print("wrote %s" % (path,))
    else:
        print(text)
    return OK


def run_version(args: Any, cfg: config.Config) -> int:
    from . import VERSION

    print("factory %s" % (VERSION,))
    print("  repo    %s" % (cfg.repo_root,))
    print("  vault   %s" % (cfg.vault,))
    print("  state   %s" % (cfg.state_dir,))
    print("  python  %s" % (sys.executable,))
    exts = [m.__name__.split(".")[-1] for m in render.extensions()]
    print("  ext     %s" % (", ".join(exts) or "none",))
    return OK


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------


def run_doctor(args: Any, cfg: config.Config) -> int:
    checks: List[Tuple[str, bool, str]] = []

    def check(name: str, ok: bool, hint: str = "") -> None:
        checks.append((name, bool(ok), hint))

    check("host is local", not config.on_hpc(), "factory exits 3 on an INL cluster")
    check("vault exists", cfg.vault.is_dir(), "mkdir %s" % (cfg.vault,))
    check(
        "vault is a git repo",
        (cfg.vault / ".git").is_dir(),
        "git -C %s init" % (cfg.vault,),
    )
    check(
        "vault is not a worktree",
        not (cfg.vault / ".git").is_file(),
        "the vault must never be a worktree of any repo",
    )
    for sub in ("Features", "Studies", "Archive", "Artifacts"):
        check("%s/ exists" % (sub,), (cfg.vault / sub).is_dir(), "mkdir %s" % (cfg.vault / sub,))
    for d in (cfg.gates_dir, cfg.timeline_dir, cfg.pulse_dir):
        check(".factory/%s/ exists" % (d.name,), d.is_dir(), "mkdir -p %s" % (d,))
    check("CLAUDE.md present", (cfg.vault / "CLAUDE.md").is_file(), "the manual is the contract")
    check("Ideas.md present", cfg.ideas_note.is_file(), "touch %s" % (cfg.ideas_note,))
    check(
        "state/ writable",
        _writable(cfg.state_dir),
        "rm -rf %s && factory board is the repair" % (cfg.state_dir,),
    )
    check("factory/state is gitignored", _state_ignored(cfg), "add factory/state/ to factory/.gitignore")

    try:
        import yaml  # noqa: F401

        check("python imports yaml", True, "")
    except Exception:
        check("python imports yaml", False, "pip install PyYAML, or set FACTORY_PYTHON")

    check("gh on PATH", bool(shutil.which("gh")), "brew install gh")
    if shutil.which("gh"):
        _, ok = probe.run(["gh", "auth", "status"], timeout=20)
        check("gh authenticated", ok, "gh auth login")
    cache, cok = probe._read_json(cfg.state_dir / "gh-cache.json")
    if cok and isinstance(cache, dict) and cache.get("at"):
        import time as _t

        age = int(_t.time() - float(cache["at"]))
        check(
            "gh cache fresh",
            age < 3600,
            "the cache is %ds old; the board renders from it first" % (age,),
        )

    av = os.environ.get("ANALYSIS_VAULT")
    check(
        "$ANALYSIS_VAULT is not this vault",
        not (av and Path(av).expanduser().resolve() == cfg.vault.resolve()),
        "analysis/tool/vault.py has its own write_home and would fight render.py",
    )

    for repo in config.SUBMODULES:
        out, ok = probe.run(
            ["git", "-C", str(cfg.repo_root / repo), "remote", "get-url", "--push", "upstream"]
        )
        check(
            "%s upstream push is disabled" % (repo,),
            ok and "DISABLED_UPSTREAM_PUSH" in out,
            "never push to idaholab; sync is manual through the web UI",
        )

    wts, ok = probe.all_worktrees(cfg)
    foreign = [p for p in wts if cfg.is_foreign(Path(p))]
    check(
        "every worktree is under %s" % (config.worktree_root(),),
        not foreign,
        "foreign: %s (tear them down by hand; no script touches them)" % (", ".join(foreign),),
    )
    bad_markers = []
    if cfg.features_dir.is_dir():
        for note in sorted(cfg.features_dir.glob("*.md")):
            text, tok = probe._read_text(note)
            if tok and text and any(m not in text for m in probe.MARKERS):
                bad_markers.append(note.stem)
    # The card list of the last board, not a fresh probe round: doctor stays
    # cheap and still names a note the board has stopped rewriting.
    last, lok = probe._read_json(cfg.last_sync)
    live = set((last or {}).get("cards") or []) if (lok and isinstance(last, dict)) else None
    orphans = (
        [n.stem for n in sorted(cfg.features_dir.glob("*.md")) if n.stem not in live]
        if (live and cfg.features_dir.is_dir())
        else []
    )
    check(
        "every note in Features/ still has a card",
        not orphans,
        "orphans: %s. The board no longer rewrites them, so the next "
        "delete-and-rebuild loses them: `factory archive <feature>`"
        % (", ".join(orphans),),
    )
    check(
        "every note keeps its four markers",
        not bad_markers,
        "missing in: %s. The renderer refuses those notes." % (", ".join(bad_markers),),
    )

    for mod in render.extensions():
        fn = getattr(mod, "doctor_checks", None)
        if fn is None:
            continue
        try:
            ctx = Ctx(config=cfg, state_dir=cfg.state_dir, vault_dir=cfg.vault, now=probe.iso())
            for row in fn(ctx) or []:
                if isinstance(row, tuple) and len(row) == 3:
                    check(row[0], row[1], row[2])
        except Exception as exc:
            check("%s doctor_checks" % (mod.__name__,), False, str(exc))

    width = max(len(n) for n, _o, _h in checks)
    failed = 0
    for name, ok, hint in checks:
        print("%s  %-*s %s" % ("ok  " if ok else "FAIL", width, name, "" if ok else hint))
        failed += 0 if ok else 1
    print("%d checks, %d failed" % (len(checks), failed))
    return OK if failed == 0 else LOOK


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe_file = path / ".write-test"
        probe_file.write_text("x")
        probe_file.unlink()
        return True
    except Exception:
        return False


def _state_ignored(cfg: config.Config) -> bool:
    out, ok = probe.run(
        ["git", "-C", str(cfg.repo_root), "check-ignore", "-q", str(cfg.state_dir / "x.json")]
    )
    return ok


# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------

CORE_HELP = {
    "board": "probe, derive and rewrite every generated file",
    "status": "print Home.md, or one feature note",
    "next": "the single next move for one feature, and why",
    "set": "record one namespaced annotation on a card; projector fields are refused",
    "abandon": "record that you have given up on a card, with a reason",
    "grant": "grant one gate, monotonically and attributed",
    "doctor": "say what is misconfigured",
    "commit": "stage and commit the vault, with no trailers",
    "dump-obs": "print one card's probe snapshot, for debugging one card",
    "version": "the version and the resolved paths",
}


def extension_verbs() -> Tuple[Dict[str, Callable], Dict[str, str]]:
    verbs: Dict[str, Callable] = {}
    help_text: Dict[str, str] = {}
    for mod in render.extensions():
        for name, fn in (getattr(mod, "VERBS", {}) or {}).items():
            verbs[str(name)] = fn
        for name, line in (getattr(mod, "HELP", {}) or {}).items():
            help_text[str(name)] = str(line)
    return (verbs, help_text)


def no_ctx_verbs() -> set:
    """Extension verbs that read no card and so need no probe round.

    A probe round costs about 6.5 s. A status-shaped verb that only reads a log
    should not pay it. An extension declares its own through
    ``NO_CTX_VERBS = ("tick-status",)``.
    """
    names: set = set()
    for mod in render.extensions():
        for name in getattr(mod, "NO_CTX_VERBS", ()) or ():
            names.add(str(name))
    return names


def bare_ctx(cfg: config.Config, dry_run: bool = False) -> Ctx:
    """A context with no probe round: paths, state and the clock only."""
    config.hostname_guard()
    return Ctx(
        config=cfg,
        obs={},
        cards=[],
        state_dir=cfg.state_dir,
        vault_dir=cfg.vault,
        now=probe.iso(),
        meta={},
        timeline=tl.TimelineWriter(cfg.timeline_dir, dry_run),
        gates=gates_mod.GateStore(cfg.gates_dir, dry_run),
        state=snapshot.Store(cfg.state_dir),
        dry_run=dry_run,
        _log=err,
    )


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ext_verbs, ext_help = extension_verbs()

    parser = argparse.ArgumentParser(
        prog="factory",
        description="moose-factory: a projected board with one next action per card.",
    )
    parser.add_argument("--dry-run", action="store_true", help="compose, compare, write nothing")
    parser.add_argument("--offline", action="store_true", help="never call gh; use the cache")

    # The same two flags after the verb. SUPPRESS keeps an absent subcommand
    # flag from overwriting the one given before the verb.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--dry-run", action="store_true", default=argparse.SUPPRESS,
        help="compose, compare, write nothing",
    )
    common.add_argument(
        "--offline", action="store_true", default=argparse.SUPPRESS,
        help="never call gh; use the cache",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("board", help=CORE_HELP["board"], parents=[common])
    p.add_argument("--du", action="store_true", help="also measure reclaimable bytes")
    p.add_argument("--feature", help="accepted and ignored in v1: the board is whole-vault")
    p.add_argument("--from-event", action="store_true", help="called by a hook")
    p = sub.add_parser("status", help=CORE_HELP["status"], parents=[common])
    p.add_argument("feature", nargs="?")
    p.add_argument(
        "--head", action="store_true",
        help="with a feature: print only the note's head block",
    )
    p = sub.add_parser("next", help=CORE_HELP["next"], parents=[common])
    p.add_argument("feature")
    p = sub.add_parser("set", help=CORE_HELP["set"], parents=[common])
    p.add_argument("feature")
    p.add_argument("assignment", metavar="key=value")
    p = sub.add_parser("abandon", help=CORE_HELP["abandon"], parents=[common])
    p.add_argument("feature")
    p.add_argument("why", help="why you are dropping it, in your own words")
    p = sub.add_parser("grant", help=CORE_HELP["grant"], parents=[common])
    p.add_argument("feature")
    p.add_argument("gate", choices=list(GATES))
    sub.add_parser("doctor", help=CORE_HELP["doctor"], parents=[common])
    sub.add_parser("commit", help=CORE_HELP["commit"], parents=[common])
    p = sub.add_parser("dump-obs", help=CORE_HELP["dump-obs"], parents=[common])
    p.add_argument("feature")
    p.add_argument(
        "--out",
        help="write the snapshot here; a bare name lands in state/dump/.",
    )
    sub.add_parser("version", help=CORE_HELP["version"], parents=[common])

    for name in sorted(ext_verbs):
        ep = sub.add_parser(name, help=ext_help.get(name, "(extension)"), parents=[common])
        ep.add_argument("rest", nargs="*")

    # An extension verb takes everything after it verbatim, leading flags
    # included. argparse refuses a trailing-argument list whose first token
    # starts with "-", so the split happens here and the parser never sees the
    # extension's own arguments. Only the two global flags may precede the
    # verb, and neither takes a value, so the first bare word is the verb.
    raw_rest: List[str] = []
    for i, token in enumerate(argv):
        if token in ext_verbs:
            raw_rest = argv[i + 1:]
            argv = argv[: i + 1]
            break
        if not token.startswith("-"):
            break
    if raw_rest and raw_rest[0] == "--":
        raw_rest = raw_rest[1:]

    args = parser.parse_args(argv)
    if raw_rest:
        args.rest = raw_rest
    for flag in ("dry_run", "du", "out", "feature"):
        if not hasattr(args, flag):
            setattr(args, flag, None if flag in ("out", "feature") else False)

    handlers: Dict[str, Callable[[Any, config.Config], int]] = {
        "board": run_board,
        "status": run_status,
        "next": run_next,
        "set": run_set,
        "abandon": run_abandon,
        "grant": run_grant,
        "doctor": run_doctor,
        "commit": run_commit,
        "dump-obs": run_dump_obs,
        "version": run_version,
    }
    try:
        # Inside the try: a malformed config file raises BadConfig, a
        # MissingPath, and the contract for that is exit 3 with the path and
        # the parser's own message, not a traceback.
        cfg = config.load(offline=args.offline)
        if args.cmd in handlers:
            return handlers[args.cmd](args, cfg)
        fn = ext_verbs.get(args.cmd)
        if fn is None:
            err("unknown verb %r" % (args.cmd,))
            return MISSING
        if args.cmd in no_ctx_verbs():
            ctx = bare_ctx(cfg, dry_run=args.dry_run)
        else:
            ctx = build_ctx(cfg, dry_run=args.dry_run)
        return int(fn(list(getattr(args, "rest", []) or []), ctx) or 0)
    except config.WrongHost as exc:
        err("factory: %s" % (exc,))
        return MISSING
    except config.MissingPath as exc:
        err("factory: %s" % (exc,))
        return MISSING
    except config.RefusedWrite as exc:
        err("factory: %s" % (exc,))
        return REFUSED
    except ValueError as exc:
        err("factory: %s" % (exc,))
        return REFUSED
    except KeyboardInterrupt:
        err("interrupted")
        return LOOK


if __name__ == "__main__":
    sys.exit(main())
