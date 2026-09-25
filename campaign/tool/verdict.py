"""Judge a run: set ``verdict`` and ``judged`` in its manifest and append the ledger verdict line.

This module owns the verdict words and the once-only rule. A run is judged
once; a wrong verdict earns a ``note`` line in the ledger, never a second
verdict. ``--finding F<n>`` must name a section that already exists in
``FINDINGS.md``. Only ``failed`` may be given to a run that has not finished.
"""

from __future__ import annotations

from typing import Optional

from . import config, findings, ledger, manifest
from .model import VERDICTS, Campaign, Run, now_iso


def judge(camp: Campaign, run: Run, word: str, finding: Optional[str], by: str,
          dry_run: bool = False) -> str:
    if word not in VERDICTS:
        raise config.Refused("verdict %r is not one of %s" % (word, ", ".join(VERDICTS)))
    if run.verdict is not None:
        raise config.Refused("%s already has verdict %s; append a note with `campaign note`"
                             % (run.run, run.verdict))
    if not run.done and word != "failed":
        raise config.Refused("%s has not finished; only `failed` may judge it now" % run.run)
    if finding:
        if findings.get(camp.dir / "FINDINGS.md", finding) is None:
            raise config.Refused("%s is not a section of FINDINGS.md; write the finding first" % finding)
    if manifest.identity_ok(run) is False:
        raise config.Refused("%s: an immutable block changed after launch; the only verdict is a "
                             "new run" % run.run)
    line = ledger.verdict_line(word, run.qoi if word != "failed" else {}, finding)
    if dry_run:
        print("[dry-run] would set verdict %s on %s and append: %s" % (word, run.run, line.strip()))
        return line
    run.verdict = word
    run.judged = {"by": by, "at": now_iso(), "finding": finding}
    manifest.save(run)
    ledger.append_under(camp.dir / "LEDGER.md", run.run, line)
    return line
