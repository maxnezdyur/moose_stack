"""Paths, identifiers, caps, thresholds and the hostname guard.

Everything machine-specific is here. Nothing else in the package calls
``os.environ`` or hard-codes a path, and no file in the repository names a
user, a home directory or a vault.

Each machine keeps its own values in one small file::

    ~/.config/moose-factory/config.toml        ($MOOSE_FACTORY_CONFIG overrides)

The file is optional. Every key falls back to a default derived from ``$HOME``,
so a fresh clone runs with no file at all. Precedence, per key:

    1. the key's environment variable   (MOOSE_FACTORY_VAULT, FACTORY_PYTHON, ...)
    2. the config file
    3. the default

``factory config`` prints the resolved values and where each one came from, and
``factory doctor`` prints the same block above its checks.

Exit-code contract for every entry point:

    0  ok
    1  a human should look
    2  a refused write
    3  a missing path, a malformed config file, or the wrong host
"""

from __future__ import annotations

import fnmatch
import os
import re
import socket
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:                                  # stdlib since 3.11; both interpreters have it
    import tomllib
except ModuleNotFoundError:           # pragma: no cover - a 3.10 or older python
    tomllib = None                    # type: ignore[assignment]

# --------------------------------------------------------------------------
# Atomic state writes
# --------------------------------------------------------------------------


def write_text_atomic(path: "Path", text: str) -> None:
    """Replace ``path`` with ``text`` through a uniquely named temporary file.

    The unique name is load-bearing. Two boards at once (a hand-run
    ``factory board`` while the tick's board is in flight) used to compute the
    same ``<name>.tmp``, and the loser died in ``os.replace`` with
    FileNotFoundError. With ``mkstemp`` the last writer simply wins.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------

# A feature name is a directory name, four branch names, a PR head branch and a
# note basename at once. Restrict it so it can never traverse or land at an
# absolute path.
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_id(feature: str) -> str:
    if not isinstance(feature, str) or ".." in feature or not SAFE_ID.match(feature):
        raise ValueError(
            "unsafe feature id %r: use letters, digits, dot, dash, underscore "
            "(no '/', no leading '.', no '..', 64 chars maximum)" % (feature,)
        )
    return feature


def is_safe_id(feature: str) -> bool:
    try:
        validate_id(feature)
        return True
    except ValueError:
        return False


# --------------------------------------------------------------------------
# Hostname guard. The first statement of every entry point.
# --------------------------------------------------------------------------

# The five INL cluster families. Each entry is an fnmatch glob against the
# short hostname, lowercased. Another site overrides `refuse_hosts` in
# config.toml; an empty list refuses nothing.
DEFAULT_REFUSE_HOSTS: Tuple[str, ...] = (
    "sawtooth*",
    "lemhi*",
    "bitterroot*",
    "hoodoo*",
    "teton*",
)

# Kept for callers that predate `refuse_hosts`. Derived, never edited apart.
HPC_PREFIXES = tuple(g.rstrip("*") for g in DEFAULT_REFUSE_HOSTS)


def short_hostname() -> str:
    try:
        return socket.gethostname().split(".")[0]
    except Exception:
        return ""


def refuse_hosts() -> Tuple[str, ...]:
    """The hostname globs this machine refuses to run on."""
    return tuple(settings()["refuse_hosts"])


def on_hpc(host: str = "") -> bool:
    name = (host or short_hostname()).lower()
    if not name:
        return False
    return any(fnmatch.fnmatch(name, glob.lower()) for glob in refuse_hosts())


def hostname_guard() -> None:
    """Raise ``WrongHost`` on an INL cluster. Callers turn it into exit 3."""
    if on_hpc():
        raise WrongHost(
            "factory does not run on HPC (%s): there is no vault here, gh may be "
            "unauthenticated, and a dispatch would land on a login node"
            % (short_hostname(),)
        )


class WrongHost(RuntimeError):
    """The caller is on an INL cluster. Exit 3."""


class MissingPath(RuntimeError):
    """A required directory or file is absent. Exit 3."""


class RefusedWrite(RuntimeError):
    """A write was refused: an input path, or a note with a missing marker. Exit 2."""


class BadConfig(MissingPath):
    """``config.toml`` does not parse, or a value has the wrong type. Exit 3.

    It subclasses :class:`MissingPath` so that every entry point already turns
    it into exit 3 with no new except clause: a config file that cannot be read
    is, to the caller, the same class of problem as a path that is not there.
    """


# --------------------------------------------------------------------------
# Per-machine configuration
# --------------------------------------------------------------------------

CONFIG_ENV = "MOOSE_FACTORY_CONFIG"
CONFIG_REL = ".config/moose-factory/config.toml"

# The default notifier. macOS grants notification authorization per executable,
# so the path is pinned rather than searched. Empty means the osascript
# fallback, which is always authorized and loses only the click-through.
DEFAULT_NOTIFIER = "/opt/homebrew/bin/terminal-notifier"

# The directory names the defaults build under $HOME. The vault's basename is
# also the name an obsidian:// link carries, so it has one definition.
DEFAULT_VAULT_DIRNAME = "moose-factory"
DEFAULT_WORKTREES_DIRNAME = "moose-worktrees"
DEFAULT_META_DIRNAME = "moose_stack"

# key, environment variable, kind. The kinds are:
#   path        a filesystem path, "~" expanded
#   path_opt    the same, where "" means "none" (the notifier)
#   str         a bare string
#   int         a whole number
#   ints        a list of whole numbers (nag_days)
#   globs       a list of hostname globs
#   paths       a list of filesystem paths, "~" expanded: colon separated in
#               the environment, a TOML array in the file (campaign_roots)
KEYS: Tuple[Tuple[str, str, str], ...] = (
    ("vault", "MOOSE_FACTORY_VAULT", "path"),
    ("worktrees_root", "FACTORY_WORKTREE_ROOT", "path"),
    ("meta_repo", "FACTORY_REPO_ROOT", "path"),
    ("python", "FACTORY_PYTHON", "path"),
    ("claude_bin", "FACTORY_CLAUDE_BIN", "path"),
    ("claude_home", "FACTORY_CLAUDE_HOME", "path"),
    ("obsidian_vault", "MOOSE_FACTORY_OBSIDIAN_VAULT", "str"),
    # The project repositories that hold campaigns: each root carries
    # `campaigns/<id>/campaign.md`. Read by tool/ext_campaigns.py only.
    ("campaign_roots", "FACTORY_CAMPAIGN_ROOTS", "paths"),
    # Extra PATH prefixes for the launchd tick, colon separated. launchd hands a
    # job a minimal PATH, and a machine whose gh or git lives outside the usual
    # prefixes needs one place to say so.
    ("path_extra", "MOOSE_FACTORY_PATH_EXTRA", "str"),
    ("notifier", "MOOSE_FACTORY_NOTIFIER", "path_opt"),
    ("refuse_hosts", "MOOSE_FACTORY_REFUSE_HOSTS", "globs"),
    ("max_concurrent_sessions", "MOOSE_FACTORY_MAX_CONCURRENT_SESSIONS", "int"),
    ("max_builds_per_day", "MOOSE_FACTORY_MAX_BUILDS_PER_DAY", "int"),
    ("min_free_gb", "MOOSE_FACTORY_MIN_FREE_GB", "int"),
    ("stall_seconds", "MOOSE_FACTORY_STALL_SECONDS", "int"),
    ("nag_days", "MOOSE_FACTORY_NAG_DAYS", "ints"),
    ("park_idle_days", "MOOSE_FACTORY_PARK_IDLE_DAYS", "int"),
    ("triage_dirty", "MOOSE_FACTORY_TRIAGE_DIRTY", "int"),
    ("gh_cache_ttl", "MOOSE_FACTORY_GH_CACHE_TTL", "int"),
    ("gh_limit", "MOOSE_FACTORY_GH_LIMIT", "int"),
    ("gh_parallel", "MOOSE_FACTORY_GH_PARALLEL", "int"),
    ("subprocess_timeout", "MOOSE_FACTORY_SUBPROCESS_TIMEOUT", "int"),
    ("stale_ref_days", "MOOSE_FACTORY_STALE_REF_DAYS", "int"),
    ("needs_you_cap", "MOOSE_FACTORY_NEEDS_YOU_CAP", "int"),
    ("head_churn_budget", "MOOSE_FACTORY_HEAD_CHURN_BUDGET", "int"),
    ("timeline_on_home", "MOOSE_FACTORY_TIMELINE_ON_HOME", "int"),
    # The gallery: the per-file size cap in megabytes, and how many
    # thumbnails one Board.html card shows. Both are display policy, so
    # they live beside the other caps rather than inside the extension.
    ("gallery_max_mb", "MOOSE_FACTORY_GALLERY_MAX_MB", "int"),
    ("gallery_thumbs", "MOOSE_FACTORY_GALLERY_THUMBS", "int"),
)

KEY_NAMES: Tuple[str, ...] = tuple(k for k, _e, _t in KEYS)
KEY_KINDS: Dict[str, str] = {k: t for k, _e, t in KEYS}
KEY_ENV: Dict[str, str] = {k: e for k, e, _t in KEYS}

# Top-level tables in config.toml that belong to another tool. They are never a
# setting, never an unknown key and never a doctor complaint. `campaign` holds
# the campaign CLI's own table (scratch, freeze_max_kb, clusters).
RESERVED_TABLES: Dict[str, str] = {"campaign": "table, read by campaign/campaign"}


def home_dir() -> Path:
    """``$HOME``. Never a literal, never a username."""
    return Path("~").expanduser()


def config_path() -> Path:
    """Where this machine's config file lives, whether or not it exists."""
    env = os.environ.get(CONFIG_ENV)
    if env:
        return Path(env).expanduser()
    return home_dir() / CONFIG_REL


def _discover_meta_repo() -> Tuple[Path, str]:
    """The moose_stack checkout that owns this copy of the code.

    Walking up from this file is the honest answer: it is the checkout that is
    running. ``$HOME/projects/moose_stack`` is the last resort, for a copy of
    the code installed somewhere unusual.

    The three shell readers -- the ``/factory`` skill, ``session-context.sh``
    and the launchd tick -- cannot do this: none of them sits inside the
    checkout it has to find, so their last resort is the literal
    ``$HOME/projects/moose_stack``. A checkout at any other path therefore
    needs the ``meta_repo`` key, and ``factory/install.sh`` writes it (also
    ``zsh factory/install.sh --config``, which writes nothing else).
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "factory").is_dir() and (parent / "moose").exists():
            return (parent, "derived from this checkout")
    guess = home_dir() / "projects" / DEFAULT_META_DIRNAME
    if guess.is_dir():
        return (guess, "default")
    # tool/config.py -> tool -> factory -> repo
    return (here.parents[2], "derived from this checkout")


def _defaults() -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Every default, plus the word ``factory config`` prints for each."""
    home = home_dir()
    meta, meta_why = _discover_meta_repo()
    values: Dict[str, Any] = {
        "vault": home / "projects" / DEFAULT_VAULT_DIRNAME,
        "worktrees_root": home / "projects" / DEFAULT_WORKTREES_DIRNAME,
        "meta_repo": meta,
        # The launcher exec's the interpreter it picked, so this process is it.
        "python": Path(sys.executable),
        "claude_bin": home / ".local" / "bin" / "claude",
        "claude_home": home / ".claude",
        "obsidian_vault": "",                # filled from the vault's basename
        "campaign_roots": (),
        "path_extra": "",
        "notifier": Path(DEFAULT_NOTIFIER),
        "refuse_hosts": DEFAULT_REFUSE_HOSTS,
        "max_concurrent_sessions": MAX_CONCURRENT_SESSIONS,
        "max_builds_per_day": MAX_BUILDS_PER_DAY,
        "min_free_gb": MIN_FREE_GB,
        "stall_seconds": STALL_SECONDS,
        "nag_days": NAG_DAYS,
        "park_idle_days": PARK_IDLE_DAYS,
        "triage_dirty": TRIAGE_DIRTY,
        "gh_cache_ttl": GH_CACHE_TTL,
        "gh_limit": GH_LIMIT,
        "gh_parallel": GH_PARALLEL,
        "subprocess_timeout": SUBPROCESS_TIMEOUT,
        "stale_ref_days": STALE_REF_DAYS,
        "needs_you_cap": NEEDS_YOU_TABLE_CAP,
        "head_churn_budget": HEAD_CHURN_BUDGET,
        "timeline_on_home": TIMELINE_ON_HOME,
        "gallery_max_mb": GALLERY_MAX_MB,
        "gallery_thumbs": GALLERY_THUMBS,
    }
    why = {k: "default" for k in values}
    why["meta_repo"] = meta_why
    why["python"] = "derived from the running interpreter"
    return (values, why)


def read_config_file() -> Tuple[Dict[str, Any], Optional[Path]]:
    """``(table, path)``. An absent file is ``({}, None)`` and is not an error.

    A file that does not parse, or that is not a table of keys, raises
    :class:`BadConfig` carrying both the path and the parser's own message.
    """
    path = config_path()
    if not path.is_file():
        return ({}, None)
    if tomllib is None:                      # pragma: no cover
        raise BadConfig(
            "%s needs a python with tomllib (3.11 or newer); this one is %s"
            % (path, ".".join(str(n) for n in sys.version_info[:3]))
        )
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except Exception as exc:
        raise BadConfig("%s: %s: %s" % (path, type(exc).__name__, exc))
    if not isinstance(data, dict):
        raise BadConfig("%s: the file must be a table of keys" % (path,))
    return (data, path)


def _bad(key: str, origin: str, want: str, got: Any) -> "BadConfig":
    return BadConfig(
        "%s: %s must be %s, not %r" % (origin, key, want, got)
    )


def _as_int(key: str, origin: str, raw: Any) -> int:
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise _bad(key, origin, "a whole number", raw)
    try:
        return int(str(raw).strip())
    except ValueError:
        raise _bad(key, origin, "a whole number", raw)


def _as_list(key: str, origin: str, raw: Any) -> List[str]:
    if isinstance(raw, str):
        return [p for p in re.split(r"[,\s]+", raw.strip()) if p]
    if isinstance(raw, (list, tuple)):
        out = []
        for item in raw:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, int) and not isinstance(item, bool):
                out.append(str(item))
            else:
                raise _bad(key, origin, "a list of strings", raw)
        return out
    raise _bad(key, origin, "a list of strings", raw)


def coerce(key: str, kind: str, raw: Any, origin: str) -> Any:
    """One raw value, from the environment or the file, in its final type."""
    if kind in ("path", "path_opt"):
        if not isinstance(raw, str):
            raise _bad(key, origin, "a path string", raw)
        text = raw.strip()
        if not text:
            if kind == "path_opt":
                return None
            raise _bad(key, origin, "a path string", raw)
        return Path(text).expanduser()
    if kind == "str":
        if not isinstance(raw, str):
            raise _bad(key, origin, "a string", raw)
        return raw.strip()
    if kind == "int":
        return _as_int(key, origin, raw)
    if kind == "ints":
        return tuple(_as_int(key, origin, item) for item in _as_list(key, origin, raw))
    if kind == "globs":
        return tuple(_as_list(key, origin, raw))
    if kind == "paths":
        if isinstance(raw, str):
            # The environment spelling: colon separated, like $PATH.
            items = [p.strip() for p in raw.split(":") if p.strip()]
        elif isinstance(raw, (list, tuple)):
            items = []
            for item in raw:
                if not isinstance(item, str):
                    raise _bad(key, origin, "a list of path strings", raw)
                if item.strip():
                    items.append(item.strip())
        else:
            raise _bad(key, origin, "a list of path strings", raw)
        return tuple(Path(p).expanduser() for p in items)
    raise BadConfig("%s: unknown kind %r for %s" % (origin, kind, key))   # pragma: no cover


def settings() -> Dict[str, Any]:
    """Every resolved value, by key. Reads the file on every call, by design.

    There is no cache: the file is a few hundred bytes, an entry point reads it
    a handful of times, and a cache would make the tests lie about the
    environment they just changed.
    """
    return resolve()[0]


def resolve() -> Tuple[Dict[str, Any], Dict[str, str], Optional[Path], List[str]]:
    """``(values, sources, config_file, unknown_keys)``.

    ``sources[key]`` is the word ``factory config`` prints: ``env $NAME``,
    ``file`` (the file's path is on the header line), ``default``, or the
    sentence that says how a derived value was derived.
    """
    data, path = read_config_file()
    values, sources = _defaults()
    for key, env, kind in KEYS:
        raw_env = os.environ.get(env)
        if raw_env is not None and raw_env.strip() != "":
            values[key] = coerce(key, kind, raw_env, "$" + env)
            sources[key] = "env $" + env
            continue
        if key in data:
            values[key] = coerce(key, kind, data[key], str(path))
            sources[key] = "file"
    if not values["obsidian_vault"]:
        # The vault's directory name is the name Obsidian shows and the name an
        # obsidian:// link carries. Deriving it keeps one fact in one place.
        values["obsidian_vault"] = Path(values["vault"]).name
        sources["obsidian_vault"] = "derived from vault"
    unknown = sorted(
        str(k) for k in data if k not in KEY_NAMES and k not in RESERVED_TABLES
    )
    return (values, sources, path, unknown)


# --------------------------------------------------------------------------
# Repositories
# --------------------------------------------------------------------------

# Display order on every card. "moose_stack" is the meta-repo; the other three
# are its submodules and are also independent GitHub repos.
META = "moose_stack"
SUBMODULES: Tuple[str, ...] = ("moose", "blackbear", "isopod")
REPOS: Tuple[str, ...] = (META,) + SUBMODULES

# Only the submodules have pull requests. The meta-repo is private to Max.
GH_REPOS: Dict[str, str] = {
    "moose": "idaholab/moose",
    "blackbear": "idaholab/blackbear",
    "isopod": "idaholab/isopod",
}

# Always upstream/devel for a submodule. The fork's devel is months stale and
# reports 384 commits ahead instead of 1.
UPSTREAM_REF = "upstream/devel"

# The meta-repo has no upstream: it is Max's own pointer repo. Its baseline is
# its own default branch, so "ahead" means "pointer bumps not yet on main".
META_BASE_REF = "origin/main"


def base_ref(repo: str) -> str:
    """The ref an "ahead" count is measured against, per repository."""
    return META_BASE_REF if repo == META else UPSTREAM_REF


# --------------------------------------------------------------------------
# Caps and thresholds. Adjust after a real week, not before.
# --------------------------------------------------------------------------

MAX_CONCURRENT_SESSIONS = 2      # working background sessions at once
MAX_BUILDS_PER_DAY = 3           # per card, rolling 24 hours
MIN_FREE_GB = 50                 # free space on the worktree volume

STALL_SECONDS = 20 * 60          # a building card with no pulse for this long
NAG_DAYS: Tuple[int, int] = (14, 45)   # one heads-up each, never repeated
PARK_IDLE_DAYS = 7               # a scaffolded card quiet this long is settled
# Uncommitted files in a worktree with no plan. Below this a scaffolded card is
# parked; at or above it the card is a triage item, because the work is real and
# nothing on the board explains it. Calibrated on a real week: a card carrying
# tens of edited files is a decision; a card carrying one stray file is not.
TRIAGE_DIRTY = 10
GH_CACHE_TTL = 300               # seconds
GH_LIMIT = 50                    # --limit on every gh pr list
GH_PARALLEL = 10                 # xargs -P for pass B
SUBPROCESS_TIMEOUT = 25          # seconds, per git or gh call
STALE_REF_DAYS = 14              # a FETCH_HEAD older than this is worth saying

GALLERY_MAX_MB = 5               # per file, in specs/gallery/; bigger is listed, never linked
GALLERY_THUMBS = 3               # thumbnails one Board.html card shows

NEEDS_YOU_TABLE_CAP = 5          # the rest become one "Backlog" line
HEAD_CHURN_BUDGET = 520          # bytes: Obsidian's diff-match-patch limit
TIMELINE_ON_HOME = 5             # lines under "Since yesterday"


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------


def repo_root() -> Path:
    """The moose_stack meta-repo root that owns this checkout of the code."""
    return Path(settings()["meta_repo"])


def vault_dir() -> Path:
    return Path(settings()["vault"])


def worktree_root() -> Path:
    """Where a legitimate feature worktree lives. Anything else is foreign."""
    return Path(settings()["worktrees_root"])


def claude_home() -> Path:
    return Path(settings()["claude_home"])


def obsidian_vault() -> str:
    """The vault name an ``obsidian://open?vault=`` link carries."""
    return str(settings()["obsidian_vault"])


def claude_bin() -> Path:
    """The Claude Code binary this machine dispatches with."""
    return Path(settings()["claude_bin"])


def display_path(path: Any) -> str:
    """A path as prose: the home directory collapses back to ``~``.

    Generated files carry commands the reader copies. Spelling the home
    directory out would put the machine's user name into every note and into
    every diff of one, so a path under ``$HOME`` prints with a tilde and any
    other path prints in full.
    """
    text = str(path)
    home = str(home_dir())
    if text == home:
        return "~"
    if home and text.startswith(home + "/"):
        return "~" + text[len(home):]
    return text


def claude_display(cfg: Any = None) -> str:
    """The Claude binary as a command to paste, resolved and tilde-collapsed.

    Takes the value off a :class:`Config` when one is in hand, so a machine
    that sets ``claude_bin`` sees its own path, and falls back to the same
    resolution for the callers that have no config object.
    """
    path = getattr(cfg, "claude_bin", None) if cfg is not None else None
    return display_path(path or claude_bin())


def notifier() -> Optional[Path]:
    """The banner binary, or ``None`` for the osascript fallback."""
    value = settings()["notifier"]
    return Path(value) if value else None


@dataclass
class Config:
    """Resolved paths plus the caps and thresholds, passed around in ``Ctx``."""

    repo_root: Path
    vault: Path
    state_dir: Path
    worktree_root: Path
    claude_home: Path
    repos: Tuple[str, ...] = REPOS
    gh_repos: Dict[str, str] = field(default_factory=lambda: dict(GH_REPOS))
    upstream_ref: str = UPSTREAM_REF
    max_concurrent_sessions: int = MAX_CONCURRENT_SESSIONS
    max_builds_per_day: int = MAX_BUILDS_PER_DAY
    min_free_gb: int = MIN_FREE_GB
    stall_seconds: int = STALL_SECONDS
    nag_days: Tuple[int, int] = NAG_DAYS
    park_idle_days: int = PARK_IDLE_DAYS
    triage_dirty: int = TRIAGE_DIRTY
    gh_cache_ttl: int = GH_CACHE_TTL
    needs_you_cap: int = NEEDS_YOU_TABLE_CAP
    offline: bool = False            # skip gh entirely (doctor, tests, --offline)

    # ---- the rest of the per-machine settings ----------------------------
    # Every one has a default, so a test may still build a Config by hand with
    # the five paths and nothing else.
    python: Path = field(default_factory=lambda: Path(sys.executable))
    claude_bin: Path = field(default_factory=lambda: home_dir() / ".local" / "bin" / "claude")
    notifier: Optional[Path] = field(default_factory=lambda: Path(DEFAULT_NOTIFIER))
    obsidian_vault: str = ""         # filled from the vault basename below
    # The project repositories that hold `campaigns/<id>/`. Empty means none.
    campaign_roots: Tuple[Path, ...] = ()
    path_extra: str = ""             # extra PATH prefixes for the launchd tick
    refuse_hosts: Tuple[str, ...] = DEFAULT_REFUSE_HOSTS
    gh_limit: int = GH_LIMIT
    gh_parallel: int = GH_PARALLEL
    subprocess_timeout: int = SUBPROCESS_TIMEOUT
    stale_ref_days: int = STALE_REF_DAYS
    head_churn_budget: int = HEAD_CHURN_BUDGET
    timeline_on_home: int = TIMELINE_ON_HOME
    gallery_max_mb: int = GALLERY_MAX_MB
    gallery_thumbs: int = GALLERY_THUMBS

    # ---- where each value came from, for `factory config` and `doctor` ---
    config_file: Optional[Path] = None
    sources: Dict[str, str] = field(default_factory=dict)
    unknown_keys: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.obsidian_vault:
            self.obsidian_vault = Path(self.vault).name

    # ---- derived vault paths ---------------------------------------------

    @property
    def features_dir(self) -> Path:
        return self.vault / "Features"

    @property
    def campaigns_dir(self) -> Path:
        return self.vault / "Campaigns"

    @property
    def archive_dir(self) -> Path:
        return self.vault / "Archive"

    @property
    def artifacts_dir(self) -> Path:
        return self.vault / "Artifacts"

    @property
    def factory_dir(self) -> Path:
        return self.vault / ".factory"

    @property
    def gates_dir(self) -> Path:
        return self.factory_dir / "gates"

    @property
    def timeline_dir(self) -> Path:
        return self.factory_dir / "timeline"

    @property
    def pulse_dir(self) -> Path:
        return self.factory_dir / "pulse"

    @property
    def home_note(self) -> Path:
        return self.vault / "Home.md"

    @property
    def ideas_note(self) -> Path:
        return self.vault / "Ideas.md"

    @property
    def base_file(self) -> Path:
        return self.vault / "Features.base"

    @property
    def board_html(self) -> Path:
        return self.vault / "Board.html"

    @property
    def last_sync(self) -> Path:
        return self.factory_dir / "last-sync.json"

    # Paths the renderer must never write into: they hold the four inputs.
    def protected_dirs(self) -> List[Path]:
        return [self.artifacts_dir, self.gates_dir, self.timeline_dir]

    def note_path(self, feature: str) -> Path:
        return self.features_dir / (validate_id(feature) + ".md")

    def is_foreign(self, worktree: Path) -> bool:
        """True when a worktree lives outside the configured worktree root."""
        try:
            Path(worktree).resolve().relative_to(self.worktree_root.resolve())
            return False
        except Exception:
            return True


def load(offline: bool = False) -> Config:
    """Resolve the configuration: environment, then the file, then the defaults.

    Reads ``config.toml`` and nothing else. A malformed file raises
    :class:`BadConfig`, which every entry point reports as exit 3.
    """
    values, sources, path, unknown = resolve()
    root = Path(values["meta_repo"])
    return Config(
        repo_root=root,
        vault=Path(values["vault"]),
        state_dir=root / "factory" / "state",
        worktree_root=Path(values["worktrees_root"]),
        claude_home=Path(values["claude_home"]),
        offline=offline,
        python=Path(values["python"]),
        claude_bin=Path(values["claude_bin"]),
        notifier=values["notifier"],
        obsidian_vault=str(values["obsidian_vault"]),
        campaign_roots=tuple(Path(p) for p in values["campaign_roots"]),
        path_extra=str(values["path_extra"]),
        refuse_hosts=tuple(values["refuse_hosts"]),
        max_concurrent_sessions=int(values["max_concurrent_sessions"]),
        max_builds_per_day=int(values["max_builds_per_day"]),
        min_free_gb=int(values["min_free_gb"]),
        stall_seconds=int(values["stall_seconds"]),
        nag_days=tuple(values["nag_days"]),
        park_idle_days=int(values["park_idle_days"]),
        triage_dirty=int(values["triage_dirty"]),
        gh_cache_ttl=int(values["gh_cache_ttl"]),
        gh_limit=int(values["gh_limit"]),
        gh_parallel=int(values["gh_parallel"]),
        subprocess_timeout=int(values["subprocess_timeout"]),
        stale_ref_days=int(values["stale_ref_days"]),
        needs_you_cap=int(values["needs_you_cap"]),
        head_churn_budget=int(values["head_churn_budget"]),
        timeline_on_home=int(values["timeline_on_home"]),
        gallery_max_mb=int(values["gallery_max_mb"]),
        gallery_thumbs=int(values["gallery_thumbs"]),
        config_file=path,
        sources=dict(sources),
        unknown_keys=tuple(unknown),
    )


def require_vault(cfg: Config) -> None:
    """Exit-3 condition: the vault scaffold is absent."""
    if not cfg.vault.is_dir():
        raise MissingPath(
            "no vault at %s. Create it, set `vault` in %s, or set $MOOSE_FACTORY_VAULT."
            % (cfg.vault, config_path())
        )


# --------------------------------------------------------------------------
# Reporting the resolved configuration
# --------------------------------------------------------------------------


def _printable(value: Any, kind: str = "") -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        # A path list prints the way its environment variable is spelled, so
        # `factory config --sh` round-trips into $FACTORY_CAMPAIGN_ROOTS.
        sep = ":" if kind == "paths" else ", "
        return sep.join(str(v) for v in value)
    return str(value)


def as_dict(cfg: Config) -> Dict[str, Any]:
    """The resolved settings, JSON-ready, for ``factory config --json``."""
    values = {
        key: _printable(getattr(cfg, _FIELD.get(key, key)), KEY_KINDS.get(key, ""))
        for key in KEY_NAMES
    }
    return {
        "config_file": str(cfg.config_file) if cfg.config_file else "",
        "config_path": str(config_path()),
        "values": values,
        "sources": {key: cfg.sources.get(key, "default") for key in KEY_NAMES},
        "unknown_keys": list(cfg.unknown_keys),
    }


# Two settings are spelled differently on Config, because the field names
# predate the config file and other modules already read them.
_FIELD: Dict[str, str] = {
    "meta_repo": "repo_root",
    "worktrees_root": "worktree_root",
}


def describe(cfg: Config) -> List[str]:
    """``key = value  (source)`` for every setting, aligned, plus a header."""
    rows = [
        (key, _printable(getattr(cfg, _FIELD.get(key, key)), KEY_KINDS.get(key, "")))
        for key in KEY_NAMES
    ]
    kw = max(len(k) for k, _v in rows)
    vw = min(60, max(len(v) for _k, v in rows))
    out = [
        "config file  %s%s"
        % (config_path(), "" if cfg.config_file else "   (absent: using the defaults)")
    ]
    for key, value in rows:
        out.append(
            "  %-*s = %-*s  (%s)" % (kw, key, vw, value, cfg.sources.get(key, "default"))
        )
    for key in cfg.unknown_keys:
        out.append("  %-*s   ignored: not a setting" % (kw, key))
    table, _path = ({}, None)
    try:
        table, _path = read_config_file()
    except Exception:
        pass
    for key, what in sorted(RESERVED_TABLES.items()):
        if key in table:
            out.append("  %-*s   (%s)" % (kw, key, what))
    return out
