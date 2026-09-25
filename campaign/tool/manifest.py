"""Write and read ``manifest.yaml``, per ``formats/manifest.md``: the replication record.

This module owns four things:

* the file's layout: key order, blank lines between groups, flow style for
  each ``code`` entry and each ``inputs`` item;
* the ``code`` block: the project root's sha, branch and dirty flag, every
  direct child that is a git repository or a submodule, the container, the
  binary the command names (path, mtime, sha256) and the python that ran;
* input discovery and the freeze: the ``-i`` files, every ``!include`` they
  reach, every ``in:`` line; each with its size and sha256, copied to
  ``inputs/<path>`` when at or under ``freeze_max_kb``;
* the identity digest over the immutable blocks, which is how an edit made
  after launch is caught.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from . import config
from .model import GROUP_BREAKS, IMMUTABLE, RUN_KEYS, Run, normalize

MANIFEST = "manifest.yaml"
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}Z)?$")
INCLUDE = re.compile(r"^\s*!include\s+(\S+)")
BINARY_SUFFIX = re.compile(r"-(opt|dbg|devel|oprof)$")
PYTHON = re.compile(r"^python(\d(\.\d+)?)?$")
LAUNCHERS = ("mpiexec", "mpirun", "srun")


# --------------------------------------------------------------------------
# YAML layout
# --------------------------------------------------------------------------


PLAIN = re.compile(r"^[A-Za-z0-9_./+@(][A-Za-z0-9_./+@()=,' -]*$")


def _scalar(v: Any, in_list: bool = False) -> str:
    if isinstance(v, str):
        if TIMESTAMP.match(v):
            return v
        if PLAIN.match(v) and not v.endswith(" ") and yaml.safe_load(v) == v:
            return v
        return json.dumps(v)
    text = yaml.safe_dump(v, default_flow_style=True, width=1 << 30, sort_keys=False)
    return "\n".join(l for l in text.splitlines() if l.strip() != "...").strip()


def _flow(v: Any, in_list: bool = False) -> str:
    if isinstance(v, dict):
        return "{" + ", ".join("%s: %s" % (k, _flow(x)) for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ", ".join(_flow(x, in_list=True) for x in v) + "]"
    return _scalar(v, in_list)


def dump(run: Run) -> str:
    data = run.to_dict()
    out: List[str] = []
    for key in list(RUN_KEYS) + [k for k in data if k not in RUN_KEYS]:
        if key not in data or (key == "identity" and data[key] is None):
            continue
        if key in GROUP_BREAKS and out:
            out.append("")
        v = data[key]
        if key == "judged" or not isinstance(v, (dict, list)) or not v:
            out.append("%s: %s" % (key, _flow(v)))
        elif isinstance(v, dict):
            out.append("%s:" % key)
            for k, x in v.items():
                out.append("  %s: %s" % (k, _flow(x)))
        else:
            out.append("%s:" % key)
            for x in v:
                out.append("  - %s" % _flow(x))
    return "\n".join(out) + "\n"


def load(run_dir: Path) -> Run:
    path = run_dir / MANIFEST
    if not path.is_file():
        raise config.Missing("%s is absent" % path)
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise config.Refused("%s does not parse: %s" % (path, exc))
    if not isinstance(data, dict):
        raise config.Refused("%s is not a mapping" % path)
    return Run.from_dict(data, path=run_dir)


def save(run: Run, run_dir: Optional[Path] = None) -> None:
    d = run_dir or run.path
    config.write_text_atomic(d / MANIFEST, dump(run))


def load_all(runs_dir: Path) -> List[Run]:
    out = []
    if runs_dir.is_dir():
        for d in sorted(runs_dir.iterdir()):
            if d.is_dir() and re.match(r"^D\d{3}_", d.name) and (d / MANIFEST).is_file():
                out.append(load(d))
    return out


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------


def identity(run: Run) -> str:
    blob = {k: normalize(getattr(run, k)) for k in IMMUTABLE}
    text = json.dumps(blob, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def identity_ok(run: Run) -> Optional[bool]:
    """True or False; None when the manifest predates the identity field."""
    if not run.identity:
        return None
    return run.identity == identity(run)


# --------------------------------------------------------------------------
# Hashing, git
# --------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(repo: Path, *args: str) -> Optional[str]:
    try:
        p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def _is_repo(d: Path) -> bool:
    return (d / ".git").exists()


def _submodules(root: Path) -> List[str]:
    gm = root / ".gitmodules"
    if not gm.is_file():
        return []
    return re.findall(r"^\s*path\s*=\s*(\S+)", gm.read_text(), flags=re.M)


def repo_state(root: Path, exclude_campaigns: bool = True) -> Dict[str, Any]:
    """{sha, branch, dirty} of the project root. ``campaigns/`` never counts as dirt."""
    sha = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    spec = ["status", "--porcelain", "--ignore-submodules=dirty", "--", "."]
    if exclude_campaigns:
        spec.append(":(exclude)campaigns")
    status = _git(root, *spec)
    return {"sha": sha, "branch": branch, "dirty": bool(status) if status is not None else None}


def code_block(root: Path, container: Optional[str] = None,
               binary: Optional[Dict[str, Any]] = None,
               python: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    code: Dict[str, Any] = {root.name: repo_state(root)}
    children = set(_submodules(root))
    try:
        children |= {d.name for d in root.iterdir() if d.is_dir() and _is_repo(d)}
    except OSError:
        pass
    for name in sorted(children):
        d = root / name
        if "/" in name or not d.is_dir():
            continue
        sha = _git(d, "rev-parse", "HEAD") if _is_repo(d) else None
        if sha is None:
            line = _git(root, "submodule", "status", "--", name) or ""
            m = re.match(r"^[ +\-U]?([0-9a-f]{7,40})", line)
            sha = m.group(1) if m else None
        code[name] = {"sha": sha}
    code["container"] = container
    code["binary"] = binary
    code["python"] = python
    return code


# --------------------------------------------------------------------------
# What the command runs
# --------------------------------------------------------------------------


def split(cmd: str) -> List[str]:
    try:
        return shlex.split(cmd)
    except ValueError as exc:
        raise config.Refused("command does not split: %s" % exc)


def program_index(tokens: List[str]) -> int:
    """Index of the program a launcher line runs: skips ``mpiexec -np N`` and friends."""
    i = 0
    if tokens and os.path.basename(tokens[0]) in LAUNCHERS:
        i = 1
        while i < len(tokens) and tokens[i].startswith("-"):
            flag = tokens[i]
            i += 1
            if "=" not in flag and flag in ("-n", "-np", "--np", "-c", "--ntasks", "-N", "--host",
                                             "-host", "--hostfile", "-hostfile", "-ppn", "--map-by",
                                             "--bind-to", "-x", "-genv", "-env"):
                i += 2 if flag in ("-genv", "-env") else 1
    return min(i, max(len(tokens) - 1, 0))


def ranks(cmd: str) -> Optional[int]:
    tokens = split(cmd)
    if not tokens or os.path.basename(tokens[0]) not in LAUNCHERS:
        return None
    for i, t in enumerate(tokens[:-1]):
        if t in ("-n", "-np", "--np", "--ntasks"):
            try:
                return int(tokens[i + 1])
            except ValueError:
                return None
    return None


def binary_index(tokens: List[str], app: Optional[str]) -> Optional[int]:
    name = config.app_binary_name(app) if app else ""
    for i, t in enumerate(tokens):
        base = os.path.basename(t)
        if (name and base == name) or BINARY_SUFFIX.search(base):
            return i
    return None


def local_binary(tokens: List[str], app: Optional[str], cwd: Path) -> Optional[Dict[str, Any]]:
    i = binary_index(tokens, app)
    if i is None:
        return None
    tok = tokens[i]
    path = Path(tok) if os.path.isabs(tok) else (cwd / tok if "/" in tok else None)
    if path is None:
        found = shutil.which(tok)
        path = Path(found) if found else None
    if path is None or not path.is_file():
        return {"path": tok, "built": None, "sha256": None}
    path = path.resolve()
    import datetime as _dt
    built = _dt.datetime.fromtimestamp(path.stat().st_mtime, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"path": str(path), "built": built, "sha256": sha256_file(path)}


def local_python(tokens: List[str], env: Dict[str, str]) -> Optional[Dict[str, Any]]:
    i = program_index(tokens)
    if not tokens or not PYTHON.match(os.path.basename(tokens[i])):
        return None
    exe = shutil.which(tokens[i], path=env.get("PATH")) or tokens[i]
    try:
        p = subprocess.run([exe, "-c", "import platform;print(platform.python_version())"],
                           capture_output=True, text=True, timeout=30)
        version = p.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        version = None
    return {"env": env.get("CONDA_DEFAULT_ENV") or os.environ.get("CONDA_DEFAULT_ENV"), "version": version}


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        raise config.Refused("input %s lies outside the project root %s; a run can only "
                             "freeze what the project's git sha covers" % (path, root))


def input_files(tokens: List[str]) -> List[str]:
    out = []
    for i, t in enumerate(tokens):
        if t == "-i":
            j = i + 1
            while j < len(tokens) and not tokens[j].startswith("-") and "=" not in tokens[j]:
                out.append(tokens[j])
                j += 1
    return out


def discover_inputs(root: Path, cwd: str, cmd: str, ins: List[str]) -> Tuple[List[str], List[str]]:
    """(root-relative paths the command reads, missing paths). Order is stable."""
    base = root / cwd
    found: List[str] = []
    missing: List[str] = []
    seen = set()

    def add(path: Path, label: str) -> bool:
        if not path.is_file():
            if label not in missing:
                missing.append(label)
            return False
        rel = _rel(root, path)
        if rel in seen:
            return False
        seen.add(rel)
        found.append(rel)
        return True

    def walk(path: Path, label: str) -> None:
        if not add(path, label):
            return
        try:
            text = path.read_text(errors="replace")
        except OSError:
            return
        for line in text.splitlines():
            m = INCLUDE.match(line)
            if m:
                inc = path.parent / m.group(1)
                walk(inc, _label(root, inc))

    for f in input_files(split(cmd)):
        p = Path(f) if os.path.isabs(f) else base / f
        walk(p, _label(root, p))
    for f in ins:
        p = Path(f) if os.path.isabs(f) else root / f
        if not p.is_file() and not os.path.isabs(f) and (base / f).is_file():
            p = base / f
        if p.suffix == ".i":
            walk(p, _label(root, p))
        else:
            add(p, _label(root, p))
    return found, missing


def _label(root: Path, p: Path) -> str:
    try:
        return os.path.normpath(p).replace(os.path.normpath(str(root)) + os.sep, "")
    except Exception:
        return str(p)


def describe_inputs(root: Path, rels: List[str], max_kb: int) -> List[Dict[str, Any]]:
    out = []
    for rel in rels:
        p = root / rel
        size = p.stat().st_size
        out.append({"path": rel, "bytes": size, "sha256": sha256_file(p),
                    "frozen": ("inputs/" + rel) if size <= max_kb * 1024 else None})
    return out


def freeze(root: Path, run_dir: Path, inputs: List[Dict[str, Any]]) -> None:
    for inp in inputs:
        if inp.get("frozen"):
            dst = run_dir / inp["frozen"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / inp["path"], dst)
