"""Per-machine settings, project-root discovery, the app table and the errors.

Everything machine-specific is here. The settings come from the ``[campaign]``
table of the factory's own file::

    ~/.config/moose-factory/config.toml        ($MOOSE_FACTORY_CONFIG overrides)

    meta_repo = "~/projects/moose_stack"       # the factory's key; read, never required
    [campaign]
    scratch = "/scratch/$USER/campaigns"       # remote root of every run
    projects = "/scratch/$USER/projects"       # remote parent of the pinned project checkouts
    freeze_max_kb = 1024                       # inputs at or under this size are copied
    ssh_user = ""                              # login name on the clusters, when it differs
    [campaign.clusters.teton]
    host = "<login host>"                      # or: clusters = {teton = "<login host>"}
    partition = "general"
    ntasks = 48
    walltime = "02:00:00"
    account = "<optional>"
    wckey = "<optional>"
    module = "<optional: the container module; else versioner.py decides>"
    build_partition = "short"

The file and every key are optional. ``$USER`` in ``scratch`` and ``projects``
expands at read time to ``ssh_user`` when set, else to the local login name.
SSH authentication is ``~/.ssh/config``; nothing here handles a credential.

Exit-code contract for every entry point:

    0  ok
    1  a human should look
    2  a refused write or a validation error
    3  a missing path or a bad configuration
    4  a cluster did not answer: ssh, rsync, sbatch or squeue failed
"""

from __future__ import annotations

import getpass
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - python older than 3.11
    tomllib = None  # type: ignore[assignment]


# --------------------------------------------------------------------------
# Errors. The CLI maps each class to its exit code.
# --------------------------------------------------------------------------


class Look(RuntimeError):
    """A human should look. Exit 1."""


class Refused(RuntimeError):
    """A refused write or a validation error. Exit 2."""


class Missing(RuntimeError):
    """A missing path or a bad configuration. Exit 3."""


class ConnectionDown(RuntimeError):
    """ssh, rsync, sbatch or squeue failed. Exit 4, one ``connection_down:`` line."""


class BadConfig(Missing):
    """``config.toml`` does not parse, or a value has the wrong type. Exit 3."""


# --------------------------------------------------------------------------
# Identifiers
# --------------------------------------------------------------------------

CAMPAIGN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
RUN_ID = re.compile(r"^D\d{3}$")
TAG = re.compile(r"^[a-z0-9._-]+$")


def validate_campaign_id(cid: str) -> str:
    if not isinstance(cid, str) or not CAMPAIGN_ID.match(cid):
        raise Refused("unsafe campaign id %r: use kebab-case, a-z 0-9 and '-'" % (cid,))
    return cid


# --------------------------------------------------------------------------
# Applications, containers, SLURM defaults (lifted from analysis/tool/config.py)
# --------------------------------------------------------------------------

# app name -> (build dir relative to the checkout root, produced binary name).
APPS: Dict[str, Tuple[str, str]] = {
    "moose": ("moose/test", "moose_test-opt"),
    "combined": ("moose/modules/combined", "combined-opt"),
    "blackbear": ("blackbear", "blackbear-opt"),
    "isopod": ("isopod", "isopod-opt"),
}


def app_build_dir(app: str) -> str:
    try:
        return APPS[app][0]
    except KeyError:
        raise Missing("unknown app %r; known: %s" % (app, ", ".join(sorted(APPS))))


def app_binary_name(app: str) -> str:
    return APPS[app][1] if app in APPS else ""


def app_submodule(app: str) -> str:
    """The checkout child whose sha keys the binary cache."""
    return "moose" if app in ("moose", "combined") else app


# The versioner script that resolves the moose-dev container hash from source.
VERSIONER = "./moose/scripts/versioner.py"
# The module a versioner hash names, when a cluster sets no `module`.
MODULE_FROM_HASH = "moose-dev-openmpi/{hash}"
# Runs one command per rank inside the container.
CONTAINER_EXEC = "moose-dev-exec"

SSH_CONNECT_TIMEOUT = 10        # seconds
MAX_TRANSIENT_RETRIES = 2       # resubmit ceiling for a transient SLURM failure
DEFAULT_NODES = 1
DEFAULT_NTASKS = 48
DEFAULT_WALLTIME = "02:00:00"
DEFAULT_PARTITION = "general"
DEFAULT_BUILD_PARTITION = "short"
BUILD_NTASKS = 16
BUILD_WALLTIME = "03:00:00"

DEFAULT_SCRATCH = "/scratch/$USER/campaigns"
DEFAULT_PROJECTS = "/scratch/$USER/projects"
DEFAULT_FREEZE_MAX_KB = 1024

# No cluster is known until the config file names one: this repository carries
# no hostname. `campaign doctor` says so when the table is empty.
DEFAULT_CLUSTERS: Dict[str, Dict[str, Any]] = {}

CLUSTER_KEYS = ("host", "partition", "ntasks", "walltime", "account", "wckey",
                "module", "build_partition")
CAMPAIGN_KEYS = ("clusters", "scratch", "projects", "freeze_max_kb", "ssh_user")


@dataclass
class Cluster:
    name: str
    host: str
    partition: str = DEFAULT_PARTITION
    ntasks: int = DEFAULT_NTASKS
    walltime: str = DEFAULT_WALLTIME
    account: Optional[str] = None
    wckey: Optional[str] = None
    module: Optional[str] = None
    build_partition: str = DEFAULT_BUILD_PARTITION


@dataclass
class Settings:
    clusters: Dict[str, Cluster]
    scratch: str
    projects: str
    freeze_max_kb: int
    ssh_user: Optional[str]
    meta_repo: Path
    config_file: Optional[Path]
    unknown_keys: list = field(default_factory=list)

    def cluster(self, name: str) -> Cluster:
        try:
            return self.clusters[name]
        except KeyError:
            raise Missing("unknown cluster %r; configured: %s"
                          % (name, ", ".join(sorted(self.clusters)) or "none"))


CONFIG_ENV = "MOOSE_FACTORY_CONFIG"
CONFIG_REL = ".config/moose-factory/config.toml"


def home_dir() -> Path:
    """``$HOME``. Never a literal, never a user name."""
    return Path("~").expanduser()


def config_path() -> Path:
    env = os.environ.get(CONFIG_ENV)
    if env:
        return Path(env).expanduser()
    return home_dir() / CONFIG_REL


def login_name(ssh_user: Optional[str] = None) -> str:
    if ssh_user:
        return ssh_user
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover - no login name at all
        return os.environ.get("USER", "")


def expand_user(template: str, ssh_user: Optional[str]) -> str:
    name = login_name(ssh_user)
    return template.replace("${USER}", name).replace("$USER", name)


def _read_file() -> Tuple[Dict[str, Any], Optional[Path]]:
    path = config_path()
    if not path.is_file():
        return {}, None
    if tomllib is None:  # pragma: no cover
        raise BadConfig("python has no tomllib (need 3.11+) to read %s" % path)
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh), path
    except (OSError, ValueError) as exc:
        raise BadConfig("%s: does not parse: %s" % (path, exc))


def _bad(path: Optional[Path], key: str, want: str, got: Any) -> BadConfig:
    return BadConfig("%s: [campaign] %s must be %s, got %r" % (path, key, want, got))


def _cluster(name: str, raw: Any, path: Optional[Path]) -> Cluster:
    base = dict(DEFAULT_CLUSTERS.get(name, {}))
    if isinstance(raw, str):
        base["host"] = raw
    elif isinstance(raw, dict):
        for k, v in raw.items():
            if k not in CLUSTER_KEYS:
                raise _bad(path, "clusters.%s.%s" % (name, k), "one of " + ", ".join(CLUSTER_KEYS), k)
            base[k] = v
    elif raw is not None:
        raise _bad(path, "clusters." + name, "a host string or a table", raw)
    if not isinstance(base.get("host"), str) or not base["host"].strip():
        raise _bad(path, "clusters.%s.host" % name, "a login host", base.get("host"))
    try:
        ntasks = int(base.get("ntasks", DEFAULT_NTASKS))
    except (TypeError, ValueError):
        raise _bad(path, "clusters.%s.ntasks" % name, "a whole number", base.get("ntasks"))

    def opt(k: str) -> Optional[str]:
        v = base.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return str(v).strip()

    return Cluster(
        name=name,
        host=base["host"].strip(),
        partition=opt("partition") or DEFAULT_PARTITION,
        ntasks=ntasks,
        walltime=opt("walltime") or DEFAULT_WALLTIME,
        account=opt("account"),
        wckey=opt("wckey"),
        module=opt("module"),
        build_partition=opt("build_partition") or DEFAULT_BUILD_PARTITION,
    )


def load() -> Settings:
    """Every resolved value. Reads the file on every call, by design."""
    data, path = _read_file()
    table = data.get("campaign") or {}
    if not isinstance(table, dict):
        raise _bad(path, "", "a table", table)
    unknown = [k for k in table if k not in CAMPAIGN_KEYS]

    ssh_user = table.get("ssh_user") or None
    if ssh_user is not None and not isinstance(ssh_user, str):
        raise _bad(path, "ssh_user", "a string", ssh_user)

    clusters: Dict[str, Cluster] = {}
    raw_clusters = table.get("clusters") or {}
    if not isinstance(raw_clusters, dict):
        raise _bad(path, "clusters", "a table", raw_clusters)
    for name in DEFAULT_CLUSTERS:
        if name not in raw_clusters:
            clusters[name] = _cluster(name, None, path)
    for name, raw in raw_clusters.items():
        clusters[name] = _cluster(name, raw, path)

    scratch = table.get("scratch", DEFAULT_SCRATCH)
    projects = table.get("projects", DEFAULT_PROJECTS)
    for key, val in (("scratch", scratch), ("projects", projects)):
        if not isinstance(val, str) or not val.startswith("/"):
            raise _bad(path, key, "an absolute remote path", val)
    try:
        freeze = int(table.get("freeze_max_kb", DEFAULT_FREEZE_MAX_KB))
    except (TypeError, ValueError):
        raise _bad(path, "freeze_max_kb", "a whole number", table.get("freeze_max_kb"))

    meta = data.get("meta_repo")
    if isinstance(meta, str) and meta.strip():
        meta_repo = Path(meta.strip()).expanduser()
    else:
        meta_repo = home_dir() / "projects" / "moose_stack"

    return Settings(
        clusters=clusters,
        scratch=expand_user(scratch.rstrip("/"), ssh_user),
        projects=expand_user(projects.rstrip("/"), ssh_user),
        freeze_max_kb=freeze,
        ssh_user=ssh_user,
        meta_repo=meta_repo,
        config_file=path,
        unknown_keys=unknown,
    )


# --------------------------------------------------------------------------
# Layout: this package, the project root, the campaign id
# --------------------------------------------------------------------------


def package_dir() -> Path:
    """``campaign/`` in the checkout that is running."""
    return Path(__file__).resolve().parents[1]


def templates_dir() -> Path:
    return package_dir() / "templates"


def slurm_dir() -> Path:
    return package_dir() / "slurm"


def find_root(explicit: Optional[str] = None, start: Optional[Path] = None) -> Path:
    """The project root: ``--root``, else the nearest parent holding ``campaigns/``."""
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not root.is_dir():
            raise Missing("--root %s is not a directory" % root)
        return root
    here = (start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / "campaigns").is_dir():
            return d
    raise Missing("no campaigns/ directory above %s; pass --root <project repo>" % here)


def campaign_from_cwd(root: Path, start: Optional[Path] = None) -> Optional[str]:
    here = (start or Path.cwd()).resolve()
    try:
        rel = here.relative_to((root / "campaigns").resolve())
    except ValueError:
        return None
    return rel.parts[0] if rel.parts else None


def campaign_dir(root: Path, cid: Optional[str]) -> Path:
    if not cid:
        cid = campaign_from_cwd(root)
    if not cid:
        raise Missing("no campaign id given and the current directory is not inside "
                      "%s/campaigns/<id>/" % root)
    validate_campaign_id(cid)
    d = root / "campaigns" / cid
    if not (d / "campaign.md").is_file():
        raise Missing("no campaign %s: %s/campaign.md is absent" % (cid, d))
    return d


def list_campaigns(root: Path) -> list:
    base = root / "campaigns"
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if (p / "campaign.md").is_file())


# --------------------------------------------------------------------------
# Atomic writes
# --------------------------------------------------------------------------


def write_text_atomic(path: Path, text: str) -> None:
    """Replace ``path`` with ``text`` through a uniquely named temporary file."""
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
