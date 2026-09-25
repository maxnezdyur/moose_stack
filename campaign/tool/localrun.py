"""Launch one run on this machine, and build an app binary when it is absent.

This module owns the local process: the working directory, the environment
(the caller's, plus the run's ``env``), the tee of every line into
``run.log`` in the run directory, the real exit code, and the core-hours,
which are ``np x elapsed``. It never goes through a shell: the command is
split once with ``shlex`` and executed as an argument vector, which is why a
proposal's ``cmd`` may not hold a shell variable.

``ensure_local_binary`` is lifted from ``analysis/tool/localrun.py``: it
returns ``<checkout>/<app build dir>/<binary>`` and runs ``make`` there when
the file is missing.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import config


class BuildError(config.Look):
    pass


def local_binary_path(checkout: Path, app: str) -> Path:
    return checkout / config.app_build_dir(app) / config.app_binary_name(app)


def ensure_local_binary(checkout: Path, app: str, jobs: int = 0) -> Path:
    """Return the local binary, building it with ``make`` when it is absent."""
    binary = local_binary_path(checkout, app)
    if binary.is_file() and os.access(binary, os.X_OK):
        return binary
    build_dir = checkout / config.app_build_dir(app)
    if not build_dir.is_dir():
        raise BuildError("build dir missing for app %r: %s" % (app, build_dir))
    jobs = jobs or min(8, (os.cpu_count() or 4))
    print("[build] %s absent; make -j%d in %s" % (binary.name, jobs, build_dir))
    proc = subprocess.run(["make", "-j%d" % jobs], cwd=str(build_dir), text=True, capture_output=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.splitlines()[-25:])
        raise BuildError("local build of %s failed (rc=%d). Is the moose conda env active?\n%s"
                         % (app, proc.returncode, tail))
    if not binary.is_file():
        raise BuildError("build finished but the binary is absent: %s" % binary)
    return binary


def launch(argv: List[str], cwd: Path, env: Dict[str, str], log: Path,
           quiet: bool = False) -> Tuple[int, float]:
    """Run ``argv`` in ``cwd``; tee stdout and stderr into ``log``. (exit code, seconds)."""
    full_env = dict(os.environ)
    full_env.update({k: str(v) for k, v in (env or {}).items()})
    log.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    with log.open("w") as fh:
        try:
            proc = subprocess.Popen(argv, cwd=str(cwd), env=full_env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1)
        except OSError as exc:
            fh.write("campaign: could not start %s: %s\n" % (argv[0] if argv else "", exc))
            return 127, time.monotonic() - t0
        assert proc.stdout is not None
        for line in proc.stdout:
            fh.write(line)
            if not quiet:
                sys.stdout.write(line)
        code = proc.wait()
    return code, time.monotonic() - t0


def core_hours(np: Optional[int], seconds: float) -> float:
    """``np x elapsed`` in hours, kept to four significant digits so a tiny run is not 0."""
    value = (np or 1) * seconds / 3600.0
    return float("%.4g" % value)
