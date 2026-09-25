"""Submit one run to a cluster, and the ``bringup`` verb that prepares a cluster.

Lifted from ``analysis/tool/dispatch.py``: ``resolve_remote_sha``,
``resolve_module_hash``, ``ensure_remote_binary`` and the per-(cluster, app,
sha) binary cache. What changed: the dispatcher takes a manifest, not a study
spec, and a run is one job, not an array.

The remote layout, every path from ``tool/config.py``::

    <projects>/<project>/                   the pinned project checkout (bringup)
    <scratch>/.bincache/<cluster>/<app>/<sha>/<binary>
    <scratch>/<campaign>/<run>/             one run: the frozen inputs at their
        run.sbatch  run.log                 project paths, a symlink into the
        <cwd>/...                           checkout for each hash-only input

Safety rails kept from the analysis version: a build is submitted once per
(cluster, app, sha) and the run depends on it through ``afterok``; a job
already queued under the run's ``--job-name`` is adopted, never doubled; the
shared scratch checkout's git state is never mutated by a run.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config
from .manifest import binary_index, split
from .model import Run
from .remote import ConnectionDown, Remote


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def parse_walltime_hours(hhmmss: str) -> float:
    """'02:30:00' -> 2.5 hours. Accepts D-HH:MM:SS too."""
    days = 0
    if "-" in hhmmss:
        d, hhmmss = hhmmss.split("-", 1)
        days = int(d)
    parts = [int(x) for x in hhmmss.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts[-3], parts[-2], parts[-1]
    return days * 24 + h + m / 60 + s / 3600


def run_root(settings: config.Settings, campaign: str, run_id: str) -> str:
    return "%s/%s/%s" % (settings.scratch, campaign, run_id)


def workdir(settings: config.Settings, run: Run) -> str:
    base = run_root(settings, run.campaign, run.run)
    return base if run.cwd in ("", ".") else "%s/%s" % (base, run.cwd)


def stack_dir(settings: config.Settings, project: str) -> str:
    return "%s/%s" % (settings.projects, project)


def bincache(settings: config.Settings, cluster: str, app: str, sha: str) -> str:
    return "%s/.bincache/%s/%s/%s" % (settings.scratch, cluster, app, sha)


def job_name(run: Run) -> str:
    return "cmp-%s-%s" % (run.campaign, run.run)


def _template(name: str) -> str:
    path = config.slurm_dir() / name
    if not path.is_file():
        raise config.Missing("slurm template %s is absent" % path)
    return path.read_text()


# --------------------------------------------------------------------------
# provenance on the cluster
# --------------------------------------------------------------------------


def resolve_remote_sha(remote: Remote, stack: str, app: str, hint: Optional[str] = None) -> str:
    sub = config.app_submodule(app)
    res = remote.run("cd %s && git rev-parse --short=12 HEAD" % shlex.quote("%s/%s" % (stack, sub)))
    if remote.dry_run:
        return (hint or "SHA")[:12]
    if not res.ok or not res.stdout:
        raise config.Missing("could not read HEAD of %s at %s on %s; run `campaign bringup --cluster %s`"
                             % (sub, stack, remote.cluster.name, remote.cluster.name))
    return res.stdout.splitlines()[-1].strip()


def resolve_module_hash(remote: Remote, stack: str) -> Optional[str]:
    """The versioner's moose-dev hash, or None where the versioner cannot run."""
    res = remote.run("cd %s && test -x %s && %s moose-dev"
                     % (shlex.quote(stack), config.VERSIONER, config.VERSIONER), login=True)
    if remote.dry_run:
        return "HASH"
    if not res.ok or not res.stdout:
        return None
    return res.stdout.splitlines()[-1].strip()


def resolve_module(remote: Remote, stack: str) -> str:
    if remote.cluster.module:
        return remote.cluster.module
    h = resolve_module_hash(remote, stack)
    if not h:
        raise config.Missing("versioner.py gave no container hash on %s; set module under "
                             "[campaign.clusters.%s] in the config file"
                             % (remote.cluster.name, remote.cluster.name))
    return config.MODULE_FROM_HASH.format(hash=h)


def ensure_remote_binary(remote: Remote, settings: config.Settings, app: str, sha: str,
                         module: str, stack: str) -> Tuple[str, Optional[str]]:
    """(cached binary path, build job id). The job id is None on a cache hit."""
    cache = bincache(settings, remote.cluster.name, app, sha)
    binary_name = config.app_binary_name(app)
    cached = "%s/%s" % (cache, binary_name)
    if remote.exists(cached):
        return cached, None
    name = "build-%s-%s" % (app, sha)
    existing = [] if remote.dry_run else remote.jobids_by_name(name)
    if existing:
        return cached, existing[0]
    script = "%s/build.sbatch" % cache
    remote.write_file(_template("build.sbatch"), script)
    args = [
        "--partition=%s" % remote.cluster.build_partition,
        "--nodes=1",
        "--ntasks=%d" % config.BUILD_NTASKS,
        "--time=%s" % config.BUILD_WALLTIME,
        "--job-name=%s" % name,
        "--output=%s/build-%%j.out" % cache,
        "--export=ALL,MODULE=%s,BUILD_DIR=%s/%s,MOOSE_DIR=%s/moose,BINARY_NAME=%s,CACHE_DIR=%s"
        % (module, stack, config.app_build_dir(app), stack, binary_name, cache),
    ]
    args += _accounting(remote.cluster)
    return cached, remote.sbatch(script, args)


def _accounting(cluster: config.Cluster) -> List[str]:
    out = []
    if cluster.account:
        out.append("--account=%s" % cluster.account)
    if cluster.wckey:
        out.append("--wckey=%s" % cluster.wckey)
    return out


def prepare(remote: Remote, settings: config.Settings, project: str, app: str,
            local_sha: Optional[str] = None) -> Dict[str, Any]:
    """Resolve the module, the app sha and the cached binary; submit a build on a miss."""
    stack = stack_dir(settings, project)
    sha = resolve_remote_sha(remote, stack, app, hint=local_sha)
    module = resolve_module(remote, stack)
    binary, build_job = ensure_remote_binary(remote, settings, app, sha, module, stack)
    digest = None if build_job or remote.dry_run else remote.sha256(binary)
    return {"stack": stack, "sha": sha, "module": module, "binary": binary,
            "build_job": build_job, "binary_sha256": digest}


# --------------------------------------------------------------------------
# one run
# --------------------------------------------------------------------------


def resources(cluster: config.Cluster, cmd: str, ntasks: Optional[int], walltime: Optional[str],
              partition: Optional[str]) -> Dict[str, Any]:
    from .manifest import ranks

    return {"partition": partition or cluster.partition, "nodes": config.DEFAULT_NODES,
            "ntasks": int(ntasks or ranks(cmd) or cluster.ntasks),
            "walltime": walltime or cluster.walltime}


def remote_command(cmd: str, app: Optional[str], binary: str) -> str:
    """The manifest command with its binary replaced by ``moose-dev-exec <cached binary>``."""
    tokens = split(cmd)
    i = binary_index(tokens, app)
    if i is not None:
        tokens[i:i + 1] = [config.CONTAINER_EXEC, binary]
    return shlex.join(tokens)


def render_run_sbatch(run: Run, settings: config.Settings, module: str, binary: str,
                      app: Optional[str]) -> str:
    env = "\n".join("export %s=%s" % (k, shlex.quote(str(v))) for k, v in (run.env or {}).items())
    text = _template("run.sbatch")
    for key, val in (("RUN", "%s %s" % (run.campaign, run.run)), ("MODULE", module),
                     ("WORKDIR", workdir(settings, run)), ("ENV", env or ":"),
                     ("COMMAND", remote_command(run.command, app, binary))):
        text = text.replace("{{%s}}" % key, val)
    return text


def sbatch_args(run: Run, settings: config.Settings, cluster: config.Cluster,
                build_job: Optional[str] = None) -> List[str]:
    s = run.slurm or {}
    rdir = run_root(settings, run.campaign, run.run)
    args = [
        "--job-name=%s" % job_name(run),
        "--partition=%s" % s.get("partition", cluster.partition),
        "--nodes=%s" % s.get("nodes", config.DEFAULT_NODES),
        "--ntasks=%s" % s.get("ntasks", cluster.ntasks),
        "--time=%s" % s.get("walltime", cluster.walltime),
        "--chdir=%s" % rdir,
        "--output=%s/run.log" % rdir,
    ] + _accounting(cluster)
    if build_job:
        args.append("--dependency=afterok:%s" % build_job)
    return args


def submit(remote: Remote, settings: config.Settings, run: Run, staging: Path,
           prep: Dict[str, Any], app: Optional[str]) -> Optional[str]:
    """Stage the frozen inputs, link the hash-only ones, upload run.sbatch, sbatch. The job id."""
    rdir = run_root(settings, run.campaign, run.run)
    if remote.dry_run or (staging / "inputs").is_dir():
        remote.push_dir(staging / "inputs", rdir)
    else:
        remote.mkdirs(rdir)
    for inp in run.inputs:
        if inp.get("frozen"):
            continue
        src = "%s/%s" % (prep["stack"], inp["path"])
        dst = "%s/%s" % (rdir, inp["path"])
        digest = remote.sha256(src)
        if digest is not None and digest != inp.get("sha256"):
            raise config.Refused("%s on %s has sha256 %s, not the manifest's %s; pin the checkout "
                                 "with `campaign bringup`" % (src, remote.cluster.name, digest[:12],
                                                             str(inp.get("sha256"))[:12]))
        remote.run("mkdir -p %s && ln -sfn %s %s" % (shlex.quote(str(Path(dst).parent)),
                                                   shlex.quote(src), shlex.quote(dst)), check=True)
    remote.mkdirs(workdir(settings, run))
    remote.write_file(render_run_sbatch(run, settings, prep["module"], prep["binary"], app),
                      "%s/run.sbatch" % rdir)
    if remote.dry_run:
        print("[dry-run] run.sbatch runs, in %s: %s" % (workdir(settings, run),
                                                       remote_command(run.command, app, prep["binary"])))
    existing = [] if remote.dry_run else remote.jobids_by_name(job_name(run))
    if existing:
        print("adopted job %s already queued as %s; not resubmitting" % (existing[0], job_name(run)))
        return existing[0]
    return remote.sbatch("%s/run.sbatch" % rdir, sbatch_args(run, settings, remote.cluster,
                                                            prep.get("build_job")))


def resubmit(remote: Remote, settings: config.Settings, run: Run) -> Optional[str]:
    rdir = run_root(settings, run.campaign, run.run)
    return remote.sbatch("%s/run.sbatch" % rdir, sbatch_args(run, settings, remote.cluster))


# --------------------------------------------------------------------------
# bringup
# --------------------------------------------------------------------------


def bringup(remote: Remote, settings: config.Settings, root: Path, app: str) -> Dict[str, Any]:
    """Pin the project checkout on the cluster at the local HEAD, then ensure the binary.

    Absent checkout: clone the local ``origin`` into ``<projects>/<project>``,
    check out the local HEAD and its submodules. Present at another sha: refuse,
    exit 1; a shared checkout is never moved by this tool.
    """
    from .manifest import _git

    project = root.name
    stack = stack_dir(settings, project)
    head = _git(root, "rev-parse", "HEAD")
    if not head:
        raise config.Missing("%s is not a git repository with a commit" % root)
    origin = _git(root, "remote", "get-url", "origin")
    remote.require_connection()
    if remote.exists("%s/.git" % stack):
        res = remote.run("git -C %s rev-parse HEAD" % shlex.quote(stack))
        there = res.stdout.splitlines()[-1].strip() if res.stdout else ""
        if not remote.dry_run and there != head:
            raise config.Look("%s on %s is at %s, the local HEAD is %s; move it by hand, the tool "
                              "never moves a shared checkout" % (stack, remote.cluster.name,
                                                                 there[:12], head[:12]))
    else:
        if not origin:
            raise config.Missing("%s has no origin remote to clone on %s" % (root, remote.cluster.name))
        remote.run("mkdir -p %s && git clone %s %s && git -C %s checkout %s && "
                   "git -C %s submodule update --init --recursive"
                   % (shlex.quote(settings.projects), shlex.quote(origin), shlex.quote(stack),
                      shlex.quote(stack), head, shlex.quote(stack)), login=True, check=True)
    local_sub = _git(root / config.app_submodule(app), "rev-parse", "HEAD") \
        if (root / config.app_submodule(app)).exists() else None
    prep = prepare(remote, settings, project, app, local_sha=local_sub)
    prep["head"] = head
    return prep


__all__ = ["ConnectionDown", "bringup", "prepare", "submit", "resubmit", "sbatch_args",
           "render_run_sbatch", "remote_command", "resources", "parse_walltime_hours"]
