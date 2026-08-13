"""Render a self-contained, data-forward HTML report for a study.

The report asserts only computed quantities (tables, plots, fitted convergence
order) and lists failures/attention items — no unbounded interpretation. Plots
are embedded as base64 PNGs so the file is standalone. matplotlib/pandas are
optional: without them the report degrades to a clean table-only page.
"""

from __future__ import annotations

import base64
import io
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config
from .model import Card, CaseStatus, StudyKind
from .spec import Spec

try:  # optional plotting stack
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _HAVE_MPL = True
except Exception:  # pragma: no cover - environment dependent
    _HAVE_MPL = False


def build_report(card: Card, spec: Spec) -> Path:
    columns = list(spec.qoi.get("columns", []))
    done = [c for c in card.cases if c.status == CaseStatus.DONE and c.qoi]
    param_keys = _param_keys(card)

    sections: List[str] = []
    sections.append(_provenance(card))
    sections.append(_summary(card))
    sections.append(_results_table(card, param_keys, columns))

    plots: List[str] = []
    if _HAVE_MPL and done:
        try:
            if card.kind == StudyKind.CONVERGENCE.value:
                plots += _convergence_plots(card, spec, columns)
            else:
                plots += _sweep_plots(card, param_keys, columns)
        except Exception as e:  # a plotting glitch must not sink the report
            sections.append(f"<p><em>plot generation skipped: {_esc(str(e))}</em></p>")
    elif not _HAVE_MPL:
        sections.append(
            "<p><em>matplotlib not installed — install the [report] extra for plots.</em></p>"
        )
    if plots:
        sections.append("<h2>Plots</h2>" + "".join(plots))

    if card.kind == StudyKind.CONVERGENCE.value:
        rate_html = _convergence_rate_table(card, spec, columns)
        if rate_html:
            sections.append(rate_html)

    sections.append(_attention_section(card))

    html = _page(card.title or card.id, sections)
    out = config.study_dir(card.id) / "results" / "report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    # relative to the study dir — robust whether studies live in the repo or the
    # external vault (repo_root() is not an ancestor of a vault study).
    card.report_path = str(out.relative_to(config.study_dir(card.id)))
    return out


# --------------------------------------------------------------------------
# sections
# --------------------------------------------------------------------------


def _provenance(card: Card) -> str:
    p = card.progress()
    rows = [
        ("Study id", card.id),
        ("Kind", card.kind),
        ("App", card.app),
        ("Git sha", card.repo_sha or "—"),
        ("Cluster", card.cluster),
        ("Account", card.account),
        ("Binary", card.binary_path or "—"),
        ("Core-hours spent", f"{card.budget.spent_core_hours:.1f}"
            + (f" / {card.budget.ceiling_core_hours:.0f} ceiling"
               if card.budget.ceiling_core_hours else "")),
        ("Cases", f"{p['done']} done / {p['failed']} failed / {p['total']} total"),
        ("Generated", card.updated),
    ]
    body = "".join(f"<tr><th>{_esc(k)}</th><td>{_esc(str(v))}</td></tr>" for k, v in rows)
    return f"<h2>Provenance</h2><table class='kv'>{body}</table>"


def _summary(card: Card) -> str:
    p = card.progress()
    gaps = ""
    if p["failed"]:
        gaps = (f" <strong>{p['failed']} case(s) failed</strong> — see the attention "
                f"section; results below cover the {p['done']} that completed.")
    return f"<p>Study <code>{_esc(card.id)}</code> is <strong>{card.state.value}</strong>.{gaps}</p>"


def _param_keys(card: Card) -> List[str]:
    keys: List[str] = []
    for c in card.cases:
        for k in c.params:
            if k not in keys:
                keys.append(k)
    return keys


def _results_table(card: Card, param_keys: List[str], columns: List[str]) -> str:
    head = ["case", "status", *[_short(k) for k in param_keys], *columns, "core-h"]
    header = "".join(f"<th>{_esc(h)}</th>" for h in head)
    body_rows = []
    for c in sorted(card.cases, key=lambda x: x.idx):
        cells = [str(c.idx), c.status.value]
        cells += [_fmt(c.params.get(k)) for k in param_keys]
        cells += [_fmt(c.qoi.get(col)) for col in columns]
        cells.append(f"{c.core_hours:.2f}")
        cls = "" if c.status == CaseStatus.DONE else " class='bad'"
        body_rows.append(f"<tr{cls}>" + "".join(f"<td>{_esc(x)}</td>" for x in cells) + "</tr>")
    return f"<h2>Results</h2><table class='data'><thead><tr>{header}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def _attention_section(card: Card) -> str:
    if not card.attention:
        return ""
    items = "".join(f"<li>{_esc(a.get('reason',''))}</li>" for a in card.attention)
    return f"<h2>⚠️ Attention</h2><ul>{items}</ul>"


# --------------------------------------------------------------------------
# plots
# --------------------------------------------------------------------------


def _sweep_plots(card: Card, param_keys: List[str], columns: List[str]) -> List[str]:
    if not param_keys:
        return []
    xk = param_keys[0]  # plot against the first swept parameter
    pts = []
    for c in card.cases:
        if c.status != CaseStatus.DONE:
            continue
        x = _num(c.params.get(xk))
        if x is None:
            continue
        pts.append((x, c.qoi))
    pts.sort(key=lambda t: t[0])
    imgs = []
    for col in columns:
        xs = [x for x, q in pts if _num(q.get(col)) is not None]
        ys = [_num(q.get(col)) for x, q in pts if _num(q.get(col)) is not None]
        if len(xs) < 2:
            continue
        fig, ax = plt.subplots(figsize=(5, 3.2))
        ax.plot(xs, ys, "o-")
        ax.set_xlabel(_short(xk))
        ax.set_ylabel(col)
        ax.set_title(f"{col} vs {_short(xk)}")
        ax.grid(True, alpha=0.3)
        imgs.append(_fig_img(fig))
    return imgs


def _h_params(spec: Spec):
    """Resolve how the convergence parameter maps to a mesh size h.

    refine mode (default when the param name contains 'refine'): the param is a
    refinement *level* and h = ratio**(-level), so the order is fit against the
    true halved size, not the raw integer level. direct mode: the param value IS
    h (e.g. a timestep dt). Override with convergence.h_mode / refinement_ratio.
    """
    conv = spec.raw.get("convergence", {})
    param = str(conv.get("param", ""))
    ratio = float(conv.get("refinement_ratio", 2) or 2)
    mode = conv.get("h_mode") or ("refine" if "refine" in param.lower() else "direct")
    return param, ratio, mode


def _h_of(lvl: float, ratio: float, mode: str) -> float:
    return ratio ** (-lvl) if mode == "refine" else lvl


def _convergence_plots(card: Card, spec: Spec, columns: List[str]) -> List[str]:
    param, ratio, mode = _h_params(spec)
    pts = _convergence_series(card, param, columns)
    imgs = []
    for col in columns:
        series = [(_h_of(float(lvl), ratio, mode), _num(q.get(col)))
                  for lvl, q in pts if _num(q.get(col)) is not None]
        series = [(h, y) for h, y in series if h > 0 and y is not None]
        if len(series) < 2:
            continue
        xs = [h for h, y in series]
        ys = [abs(y) for h, y in series]
        fig, ax = plt.subplots(figsize=(5, 3.2))
        if all(y > 0 for y in ys):
            ax.loglog(xs, ys, "o-")
        else:
            ax.plot(xs, ys, "o-")
        ax.set_xlabel("h" if mode == "refine" else _short(param))
        ax.set_ylabel(col)
        ax.set_title(f"{col} convergence")
        ax.grid(True, which="both", alpha=0.3)
        imgs.append(_fig_img(fig))
    return imgs


def _convergence_rate_table(card: Card, spec: Spec, columns: List[str]) -> str:
    param, ratio, mode = _h_params(spec)
    pts = _convergence_series(card, param, columns)
    rows = []
    for col in columns:
        series = [(_h_of(float(lvl), ratio, mode), _num(q.get(col)))
                  for lvl, q in pts if _num(q.get(col)) is not None]
        series = [(h, y) for h, y in series if y is not None and h > 0 and abs(y) > 0]
        if len(series) < 2:
            continue
        orders = []
        for (h0, y0), (h1, y1) in zip(series, series[1:]):
            if h1 == h0:
                continue
            try:
                p = math.log(abs(y1) / abs(y0)) / math.log(h1 / h0)
                orders.append(p)
            except (ValueError, ZeroDivisionError):
                pass
        if orders:
            avg = sum(orders) / len(orders)
            rows.append(f"<tr><td>{_esc(col)}</td><td>{avg:.3f}</td>"
                        f"<td>{', '.join(f'{o:.2f}' for o in orders)}</td></tr>")
    if not rows:
        return ""
    note = (f"slope of log|QoI| vs log(h), h = {ratio:g}^(-level), pairwise"
            if mode == "refine" else "slope of log|QoI| vs log(param), pairwise")
    return ("<h2>Observed convergence order</h2>"
            f"<p><em>{_esc(note)}.</em></p>"
            "<table class='data'><thead><tr><th>QoI</th><th>mean order</th>"
            f"<th>pairwise</th></tr></thead><tbody>{''.join(rows)}</tbody></table>")


def _convergence_series(card: Card, param: str, columns: List[str]) -> List[Tuple[Any, Dict]]:
    pts = []
    for c in card.cases:
        if c.status != CaseStatus.DONE:
            continue
        lvl = _num(c.params.get(param))
        if lvl is None:
            continue
        pts.append((lvl, c.qoi))
    pts.sort(key=lambda t: t[0])
    return pts


# --------------------------------------------------------------------------
# rendering helpers
# --------------------------------------------------------------------------


def _fig_img(fig) -> str:
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"<img alt='plot' style='max-width:100%' src='data:image/png;base64,{b64}'>"


def _page(title: str, sections: List[str]) -> str:
    return f"""<!doctype html>
<meta charset="utf-8"><title>{_esc(title)}</title>
<style>
  body{{font:14px system-ui,sans-serif;margin:2rem;max-width:60rem;color:#222}}
  h1{{margin-top:0}} h2{{margin-top:2rem;border-bottom:1px solid #ddd;padding-bottom:.2rem}}
  table{{border-collapse:collapse;margin:.5rem 0}}
  th,td{{padding:.3rem .6rem;border:1px solid #ddd;text-align:left}}
  table.kv th{{background:#f4f4f4;width:12rem}}
  table.data thead th{{background:#f0f0f0}}
  tr.bad td{{background:#fff2f2;color:#900}}
  code{{background:#eee;padding:.1rem .3rem;border-radius:3px}}
</style>
<h1>{_esc(title)}</h1>
{''.join(sections)}
"""


def _short(path: str) -> str:
    return path.split("/")[-1] if "/" in path else path


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def _num(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _esc(s: Any) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
