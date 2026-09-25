"""SSH, rsync and SLURM wrappers: every byte that crosses to a cluster goes through here.

Lifted from ``analysis/tool/remote.py``. Authentication is the user's
``~/.ssh/config`` (ControlMaster, 2FA); this module never handles a
credential. The one change from the analysis version is dry-run: here a
dry-run executes nothing at all, not even a read-only probe, and prints every
ssh, rsync, sbatch, squeue and sacct line it would have run. A failure to
reach the cluster raises ``ConnectionDown`` (exit 4); the caller parks rather
than retries.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from . import config
from .config import ConnectionDown

# The analysis name, kept so a lifted caller reads the same.
ConnectionError_ = ConnectionDown


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _ssh_opts() -> List[str]:
    return ["-o", "BatchMode=yes", "-o", "ConnectTimeout=%d" % config.SSH_CONNECT_TIMEOUT]


class Remote:
    """Bound to one cluster. Reuses the SSH ControlMaster from ``~/.ssh/config``."""

    def __init__(self, cluster: config.Cluster, settings: config.Settings, dry_run: bool = False):
        self.cluster = cluster
        self.settings = settings
        self.host = ("%s@%s" % (settings.ssh_user, cluster.host)) if settings.ssh_user else cluster.host
        self.dry_run = dry_run

    # ---- primitive exec ----------------------------------------------------

    def run(self, command: str, login: bool = False, input: Optional[str] = None,
            check: bool = False) -> Result:
        """Run ``command`` on the cluster; ``login`` wraps it in ``bash -lc``."""
        remote_cmd = ("bash -lc " + shlex.quote(command)) if login else command
        if self.dry_run:
            print("[dry-run] ssh %s: %s" % (self.host, command))
            return Result(0, "", "")
        argv = ["ssh", *_ssh_opts(), self.host, remote_cmd]
        try:
            proc = subprocess.run(argv, input=input, capture_output=True, text=True,
                                  timeout=max(30, config.SSH_CONNECT_TIMEOUT + 20))
        except subprocess.TimeoutExpired as exc:
            raise ConnectionDown("ssh to %s timed out: %s" % (self.host, exc))
        except OSError as exc:
            raise ConnectionDown("ssh could not start: %s" % exc)
        res = Result(proc.returncode, proc.stdout.strip(), proc.stderr.strip())
        if res.returncode == 255:
            raise ConnectionDown("ssh to %s failed: %s" % (self.host, res.stderr.splitlines()[-1:] or ""))
        if check and not res.ok:
            raise ConnectionDown("%s on %s failed (rc=%d): %s"
                                 % (command.split()[0] if command else "command", self.host,
                                    res.returncode, res.stderr))
        return res

    # ---- connectivity ------------------------------------------------------

    def check_connection(self) -> bool:
        """Fast non-interactive probe. False when unreachable or when 2FA is due."""
        if self.dry_run:
            print("[dry-run] ssh %s: true" % self.host)
            return True
        argv = ["ssh", *_ssh_opts(), self.host, "true"]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=20)
        except (subprocess.TimeoutExpired, OSError):
            return False
        return proc.returncode == 0

    def require_connection(self) -> None:
        if not self.check_connection():
            raise ConnectionDown("cannot reach %s (off-network, or the ssh ticket expired)" % self.host)

    # ---- files -------------------------------------------------------------

    def exists(self, remote_path: str) -> bool:
        if self.dry_run:
            print("[dry-run] ssh %s: test -e %s  (assumed absent)" % (self.host, remote_path))
            return False
        res = self.run("test -e %s && echo yes || echo no" % shlex.quote(remote_path))
        return res.ok and res.stdout.splitlines()[-1:] == ["yes"]

    def mkdirs(self, remote_path: str) -> None:
        self.run("mkdir -p %s" % shlex.quote(remote_path), check=True)

    def write_file(self, content: str, remote_path: str) -> None:
        """Create or overwrite a remote file from ``content`` through stdin."""
        if self.dry_run:
            print("[dry-run] write %dB -> %s:%s" % (len(content), self.host, remote_path))
            return
        self.mkdirs(str(Path(remote_path).parent))
        self.run("cat > %s" % shlex.quote(remote_path), input=content, check=True)

    def sha256(self, remote_path: str) -> Optional[str]:
        res = self.run("sha256sum %s" % shlex.quote(remote_path))
        if self.dry_run or not res.ok or not res.stdout:
            return None
        return res.stdout.split()[0]

    # ---- rsync -------------------------------------------------------------

    def _rsync(self, src: str, dst: str, extra: Optional[List[str]] = None) -> Result:
        argv = ["rsync", "-az", "-e", "ssh " + " ".join(_ssh_opts())] + list(extra or []) + [src, dst]
        if self.dry_run:
            print("[dry-run] " + " ".join(shlex.quote(a) for a in argv))
            return Result(0, "", "")
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired as exc:
            raise ConnectionDown("rsync with %s timed out: %s" % (self.host, exc))
        except OSError as exc:
            raise ConnectionDown("rsync could not start: %s" % exc)
        res = Result(proc.returncode, proc.stdout.strip(), proc.stderr.strip())
        if not res.ok:
            raise ConnectionDown("rsync with %s failed (rc=%d): %s"
                                 % (self.host, res.returncode, res.stderr.splitlines()[-1:] or ""))
        return res

    def push_dir(self, local_dir: Path, remote_dir: str) -> Result:
        """Mirror a local directory up to the cluster, with no deletes."""
        self.mkdirs(remote_dir)
        return self._rsync("%s/" % str(local_dir).rstrip("/"), "%s:%s/" % (self.host, remote_dir))

    def pull(self, remote_dir: str, local_dir: Path, includes: Optional[List[str]] = None,
             excludes: Optional[List[str]] = None) -> Result:
        """Pull files back; with ``includes`` only matching paths, never a symlink."""
        if not self.dry_run:
            local_dir.mkdir(parents=True, exist_ok=True)
        extra = ["-r", "-m", "--no-links"]
        for pat in excludes or []:
            extra += ["--exclude", pat]
        if includes:
            for pat in includes:
                extra += ["--include", pat]
            extra += ["--include", "*/", "--exclude", "*"]
        return self._rsync("%s:%s/" % (self.host, remote_dir.rstrip("/")),
                           "%s/" % str(local_dir).rstrip("/"), extra=extra)

    def pull_file(self, remote_path: str, local_path: Path) -> Result:
        if not self.dry_run:
            local_path.parent.mkdir(parents=True, exist_ok=True)
        return self._rsync("%s:%s" % (self.host, remote_path), str(local_path))

    # ---- SLURM -------------------------------------------------------------

    def sbatch(self, remote_script: str, args: Optional[List[str]] = None) -> Optional[str]:
        """Submit a batch script; the job id, or None under dry-run."""
        cmd = " ".join(["sbatch", *(shlex.quote(a) for a in (args or [])), shlex.quote(remote_script)])
        res = self.run(cmd, login=True, check=not self.dry_run)
        if self.dry_run:
            return None
        for tok in res.stdout.split():
            if tok.isdigit():
                return tok
        raise ConnectionDown("could not parse sbatch output: %r" % res.stdout)

    def sacct(self, jobids: List[str]) -> Dict[str, Dict[str, object]]:
        """{job id: {state, elapsed_s, alloc_cpus, exit, end}} for the main job lines."""
        if not jobids:
            return {}
        res = self.run("sacct -j %s -n -P -o JobID,State,ElapsedRaw,AllocCPUS,ExitCode,End"
                       % shlex.quote(",".join(jobids)), login=True, check=not self.dry_run)
        out: Dict[str, Dict[str, object]] = {}
        for line in res.stdout.splitlines():
            f = line.split("|")
            if len(f) < 6 or "." in f[0]:
                continue
            try:
                elapsed = int(f[2])
            except ValueError:
                elapsed = 0
            try:
                alloc = int(f[3])
            except ValueError:
                alloc = 0
            code, _, sig = f[4].partition(":")
            try:
                exit_code = int(code)
                if exit_code == 0 and sig.strip() not in ("", "0"):
                    exit_code = 128 + int(sig)
            except ValueError:
                exit_code = None
            out[f[0]] = {"state": f[1].split()[0] if f[1] else "", "elapsed_s": elapsed,
                         "alloc_cpus": alloc, "exit": exit_code,
                         "end": f[5] if f[5] not in ("", "Unknown", "None") else None}
        return out

    def squeue_states(self) -> Dict[str, str]:
        """Live states of this user's queued and running jobs."""
        res = self.run("squeue -u $USER -h -o '%i|%T'", login=True, check=not self.dry_run)
        out = {}
        for line in res.stdout.splitlines():
            if "|" in line:
                jid, state = line.split("|", 1)
                out[jid.strip()] = state.strip()
        return out

    def jobids_by_name(self, name: str) -> List[str]:
        """Queued or running job ids under ``--job-name``: the lost-receipt guard."""
        res = self.run("squeue -u $USER -h -o '%i|%j'", login=True, check=not self.dry_run)
        ids = []
        for line in res.stdout.splitlines():
            if "|" in line:
                jid, jname = line.split("|", 1)
                if jname.strip() == name and jid.strip() not in ids:
                    ids.append(jid.strip())
        return ids
