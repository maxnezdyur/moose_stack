"""The replay contract of ``formats/manifest.md``, verbatim, in order.

1. Read the manifest. Refuse when ``verdict`` is ``failed``. (Also refuse a
   manifest whose identity digest no longer matches: an immutable block was
   edited after launch.)
2. For every input, compute the working-tree sha256 and compare. On a
   mismatch, refuse and name the file. With ``--restore``, copy the frozen
   file over the working-tree file first; a hash-only file cannot be restored
   and stays a refusal.
3. Compare every ``code`` sha with the working tree. Warn on a mismatch;
   refuse with ``--strict``.
4. Mint a new run ``D0nn`` with ``replay_of: D014``, the same ``command``,
   ``cwd``, ``env`` and ``hypothesis``, and the working tree's own ``code`` block.
5. Launch it like any run. ``collect`` compares its ``qoi`` with the original
   within a tolerance per measure and writes the result in the new run's ``note.md``.
"""

from __future__ import annotations

import shutil
from typing import Any, Dict, List, Optional

from . import config, launch, manifest, spec
from .model import Campaign, Run


def _code_mismatches(old: Dict[str, Any], new: Dict[str, Any]) -> List[str]:
    out = []
    for name, block in (old or {}).items():
        if name in ("container", "binary", "python") or not isinstance(block, dict):
            continue
        a = str(block.get("sha") or "")
        b = str(((new or {}).get(name) or {}).get("sha") or "")
        n = min(len(a), len(b))
        if not a or not b or n < 7 or a[:n] != b[:n]:
            out.append("%s: manifest %s, working tree %s" % (name, a[:12] or "-", b[:12] or "-"))
    ob = (old or {}).get("binary") or {}
    nb = (new or {}).get("binary") or {}
    if ob.get("sha256") and nb.get("sha256") and ob["sha256"] != nb["sha256"]:
        out.append("binary: manifest sha256 %s, working tree %s" % (ob["sha256"][:12], nb["sha256"][:12]))
    return out


def replay(camp: Campaign, settings: config.Settings, run: Run, restore: bool = False,
           strict: bool = False, cluster: Optional[str] = None, dry_run: bool = False) -> int:
    root = camp.root
    # 1
    if run.verdict == "failed":
        raise config.Refused("%s has verdict failed; a failed run is not replayed" % run.run)
    if manifest.identity_ok(run) is False:
        raise config.Refused("%s: an immutable block (%s) was edited after launch; the manifest "
                             "cannot be replayed" % (run.run, ", ".join(manifest.IMMUTABLE)))
    # 2
    for inp in run.inputs:
        path = root / inp["path"]
        now = manifest.sha256_file(path) if path.is_file() else None
        if now == inp.get("sha256"):
            continue
        if restore and inp.get("frozen") and (run.path / inp["frozen"]).is_file():
            if dry_run:
                print("[dry-run] would restore %s from %s" % (inp["path"], inp["frozen"]))
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(run.path / inp["frozen"], path)
            print("restored %s from runs/%s/%s" % (inp["path"], run.path.name, inp["frozen"]))
            continue
        why = "absent" if now is None else "sha256 %s, manifest %s" % (now[:12], str(inp.get("sha256"))[:12])
        hint = "" if inp.get("frozen") else " (hash only: it cannot be restored)"
        raise config.Refused("input %s differs from %s: %s%s" % (inp["path"], run.run, why, hint))
    # 3
    tokens = manifest.split(run.command)
    here = manifest.code_block(root, None,
                               manifest.local_binary(tokens, camp.meta.get("app"), root / (run.cwd or ".")),
                               None)
    mism = _code_mismatches(run.code, here)
    for m in mism:
        print("warning: code differs from %s: %s" % (run.run, m))
    if mism and strict:
        raise config.Refused("--strict: the working tree's code differs from %s" % run.run)
    # 4
    new_id = spec.next_id(camp)
    tag = "replay-%s" % run.run
    _ids, tags = spec.existing_runs(camp)
    n = 2
    while tag in tags.values():
        tag = "replay-%s-%d" % (run.run, n)
        n += 1
    target = cluster or run.cluster or "local"
    slurm = run.slurm or {}
    plan = {
        "run": new_id, "tag": tag, "group": None, "replay_of": run.run,
        "proposal": {"tests": run.hypothesis, "because": [run.run],
                     "estimate_core_hours": round(run.core_hours, 4) or run.proposal.get("estimate_core_hours")},
        "hypothesis": run.hypothesis, "command": run.command, "cwd": run.cwd, "env": dict(run.env or {}),
        "ins": [i["path"] for i in run.inputs], "cluster": target,
        "ntasks": slurm.get("ntasks") if target != "local" else None,
        "walltime": slurm.get("walltime") if target != "local" else None,
        "partition": slurm.get("partition") if target != "local" else None,
        "estimate": run.core_hours or float(run.proposal.get("estimate_core_hours") or 0.0),
    }
    # 5
    return launch.launch(camp, settings, plan, dry_run=dry_run)
