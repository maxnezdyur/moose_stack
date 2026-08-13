"""SSH / rsync / SLURM wrappers — the reliable machinery for talking to HPC.

All remote access goes through here. Auth is delegated entirely to the user's
``~/.ssh/config`` (ControlMaster is already configured for ``*.hpc.inl.gov``),
so this module never handles credentials or 2FA. Every method has a
``dry_run`` path that prints the command instead of running it, which makes
dispatch fully testable without side effects.

Connectivity is treated as fallible: a failed probe is reported, not retried
blindly, so the caller can park a study in the CONNECTION_DOWN lane.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from . import config


class ConnectionError_(RuntimeError):
    """Raised when the cluster is unreachable (off-network, ticket expired)."""


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _ssh_opts() -> List[str]:
    return [
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={config.SSH_CONNECT_TIMEOUT}",
    ]


class Remote:
    """Bound to one cluster. Reuses the SSH ControlMaster from ~/.ssh/config."""

    def __init__(self, cluster: str, dry_run: bool = False):
        self.cluster = cluster
        self.host = config.ssh_host(cluster)
        self.dry_run = dry_run
        self._user: Optional[str] = None

    # ---- primitive exec ----------------------------------------------------

    def run(
        self,
        command: str,
        login: bool = False,
        input: Optional[str] = None,
        check: bool = False,
        mutating: bool = False,
    ) -> Result:
        """Run ``command`` on the cluster.

        login=True wraps in ``bash -lc`` for a full module environment.
        mutating=True commands are skipped (and faked-ok) under dry_run;
        read-only commands still execute under dry_run so probes/reconcile
        return real data.
        """
        if login:
            remote_cmd = "bash -lc " + shlex.quote(command)
        else:
            remote_cmd = command

        argv = ["ssh", *_ssh_opts(), self.host, remote_cmd]

        if self.dry_run and mutating:
            print(f"[dry-run] ssh {self.host}: {command}")
            return Result(0, "", "")

        try:
            proc = subprocess.run(
                argv,
                input=input,
                capture_output=True,
                text=True,
                timeout=max(30, config.SSH_CONNECT_TIMEOUT + 20),
            )
        except subprocess.TimeoutExpired as e:
            raise ConnectionError_(f"ssh to {self.host} timed out: {e}")
        res = Result(proc.returncode, proc.stdout.strip(), proc.stderr.strip())
        if check and not res.ok:
            raise RuntimeError(
                f"remote command failed on {self.host} (rc={res.returncode}): "
                f"{command}\n{res.stderr}"
            )
        return res

    # ---- connectivity ------------------------------------------------------

    def check_connection(self) -> bool:
        """Fast non-interactive probe. False if unreachable / needs 2FA."""
        argv = ["ssh", *_ssh_opts(), self.host, "true"]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            return False
        return proc.returncode == 0

    def user(self) -> str:
        if self.dry_run:
            import os
            return os.environ.get("USER", "user")
        if self._user is None:
            res = self.run("echo $USER")
            if not res.ok or not res.stdout:
                raise ConnectionError_(f"could not resolve remote $USER on {self.host}")
            self._user = res.stdout.splitlines()[-1].strip()
        return self._user

    # ---- path helpers ------------------------------------------------------

    def analysis_root(self) -> str:
        return config.REMOTE_ANALYSIS_ROOT.format(user=self.user())

    def workdir(self, study_id: str) -> str:
        return f"{self.analysis_root()}/{config.validate_study_id(study_id)}"

    def bincache(self, app: str, sha: str) -> str:
        return config.REMOTE_BINCACHE.format(
            user=self.user(), cluster=self.cluster, app=app, sha=sha
        )

    def moose_stack(self) -> str:
        return config.REMOTE_MOOSE_STACK.format(user=self.user())

    def exists(self, remote_path: str) -> bool:
        if self.dry_run:
            print(f"[dry-run] exists? {self.host}:{remote_path} -> assuming no (cache miss)")
            return False
        res = self.run(f"test -e {shlex.quote(remote_path)} && echo yes || echo no")
        return res.ok and res.stdout.splitlines()[-1].strip() == "yes"

    def mkdirs(self, remote_path: str) -> None:
        self.run(f"mkdir -p {shlex.quote(remote_path)}", mutating=True, check=not self.dry_run)

    def write_file(self, content: str, remote_path: str) -> None:
        """Create/overwrite a remote file from ``content`` via stdin (no quoting
        pitfalls)."""
        if self.dry_run:
            print(f"[dry-run] write {len(content)}B -> {self.host}:{remote_path}")
            return
        self.mkdirs(str(Path(remote_path).parent))
        res = self.run(f"cat > {shlex.quote(remote_path)}", input=content)
        if not res.ok:
            raise RuntimeError(f"failed writing {remote_path}: {res.stderr}")

    # ---- rsync -------------------------------------------------------------

    def _rsync(self, src: str, dst: str, extra: Optional[List[str]] = None) -> Result:
        ssh_e = "ssh " + " ".join(_ssh_opts())
        argv = ["rsync", "-az", "-e", ssh_e]
        if extra:
            argv += extra
        argv += [src, dst]
        if self.dry_run:
            print(f"[dry-run] {' '.join(shlex.quote(a) for a in argv)}")
            return Result(0, "", "")
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired as e:
            raise ConnectionError_(f"rsync to/from {self.host} timed out: {e}")
        return Result(proc.returncode, proc.stdout.strip(), proc.stderr.strip())

    def push_dir(self, local_dir: Path, remote_dir: str) -> Result:
        """Mirror a local directory up to the cluster (no deletes)."""
        self.mkdirs(remote_dir)
        return self._rsync(f"{str(local_dir).rstrip('/')}/", f"{self.host}:{remote_dir}/")

    def push_file(self, local_file: Path, remote_path: str) -> Result:
        self.mkdirs(str(Path(remote_path).parent))
        return self._rsync(str(local_file), f"{self.host}:{remote_path}")

    def pull(
        self, remote_path: str, local_dir: Path, includes: Optional[List[str]] = None
    ) -> Result:
        """Pull files back. When ``includes`` is given, only matching paths are
        copied (used to grab CSVs + logs while leaving large fields behind)."""
        local_dir.mkdir(parents=True, exist_ok=True)
        extra: List[str] = []
        if includes:
            for pat in includes:
                extra += ["--include", pat]
            extra += ["--include", "*/", "--exclude", "*"]
        return self._rsync(
            f"{self.host}:{remote_path.rstrip('/')}/",
            f"{str(local_dir).rstrip('/')}/",
            extra=["-r"] + extra,
        )

    # ---- SLURM -------------------------------------------------------------

    def sbatch(self, remote_script: str, args: Optional[List[str]] = None) -> Optional[str]:
        """Submit a batch script; return the job id (or None under dry_run)."""
        parts = ["sbatch"]
        if args:
            parts += args
        parts.append(shlex.quote(remote_script))
        cmd = " ".join(parts)
        if self.dry_run:
            print(f"[dry-run] ssh {self.host}: {cmd}")
            return None
        res = self.run(cmd, login=True, check=True)
        # "Submitted batch job 123456"
        for tok in res.stdout.split():
            if tok.isdigit():
                return tok
        raise RuntimeError(f"could not parse sbatch output: {res.stdout!r}")

    def sacct(self, jobids: List[str]) -> Dict[str, Dict[str, object]]:
        """Per-task accounting for the given job ids.

        Returns {task_id: {state, elapsed_s, alloc_cpus}} keyed by the main
        task line (e.g. '12345_3'), filtering out .batch/.extern sub-steps.
        """
        if not jobids:
            return {}
        joblist = ",".join(jobids)
        res = self.run(
            f"sacct -j {shlex.quote(joblist)} -n -P "
            f"-o JobID,State,ElapsedRaw,AllocCPUS"
        )
        out: Dict[str, Dict[str, object]] = {}
        for line in res.stdout.splitlines():
            fields = line.split("|")
            if len(fields) < 4:
                continue
            jid, state, elapsed, cpus = fields[0], fields[1], fields[2], fields[3]
            if "." in jid:  # skip .batch / .extern / step lines
                continue
            try:
                elapsed_s = int(elapsed)
            except ValueError:
                elapsed_s = 0
            try:
                alloc = int(cpus)
            except ValueError:
                alloc = 0
            out[jid] = {
                "state": state.split()[0] if state else "",  # "CANCELLED by 123" -> CANCELLED
                "elapsed_s": elapsed_s,
                "alloc_cpus": alloc,
            }
        return out

    def jobids_by_name(self, name: str) -> List[str]:
        """Array base job ids currently queued/running under a given --job-name.

        Lets dispatch recover a submission whose id was never persisted (ssh
        dropped after the cluster accepted the job) and refuse to double-submit.
        %F collapses array tasks to their base id; dedup handles the rest.
        """
        res = self.run("squeue -u $USER -h -r -o '%F|%j'")
        bases: List[str] = []
        for line in res.stdout.splitlines():
            if "|" not in line:
                continue
            base, jname = line.split("|", 1)
            if jname.strip() == name:
                # normalize to the array base even if a task id slips through
                b = base.strip().split("_")[0]
                if b and b not in bases:
                    bases.append(b)
        return bases

    def squeue_states(self) -> Dict[str, str]:
        """Live states for this user's currently-queued/running tasks."""
        res = self.run("squeue -u $USER -h -o '%i|%T'")
        out = {}
        for line in res.stdout.splitlines():
            if "|" in line:
                jid, state = line.split("|", 1)
                out[jid.strip()] = state.strip()
        return out

    def queue_depth(self, partition: str) -> Optional[int]:
        """Number of pending jobs in a partition (for queue-aware decisions)."""
        res = self.run(
            f"squeue -h -p {shlex.quote(partition)} -t PENDING -o '%i' | wc -l"
        )
        try:
            return int(res.stdout.splitlines()[-1].strip())
        except (ValueError, IndexError):
            return None
