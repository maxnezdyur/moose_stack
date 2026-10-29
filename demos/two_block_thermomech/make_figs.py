#!/usr/bin/env python3
"""Stills for the two-block demo, built with figkit (inl-deckkit).

Usage: make_figs.py [out_dir]   (default: ./figs)
Run in the MOOSE conda env; figkit needs only matplotlib, numpy and scipy.
"""

import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DECKKIT = Path(os.environ.get("DECKKIT", Path.home() / "projects" / "inl-deckkit"))
sys.path.insert(0, str(DECKKIT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cm, colors
from mpl_toolkits.mplot3d.art3d import Line3DCollection

from figkit import *
from figkit.mesh3d import facing

HERE = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "figs"
EXO = HERE / "two_block_exact.e"
DATE = datetime(2026, 10, 29, tzinfo=timezone.utc)
DPI = 250

configure(base_pt=9)

# semantics, bound once
BLOCK_A, BLOCK_B = ORANGE, SKYBLUE
STEP_TIMES = (500.0, 1.0e5)

STEP_ENDS = (("end of Step 1", 500.0), ("end of Step 2", 1.0e5), ("end of Step 3", 1.05e5))
STEP_COLORS = (BLUE, VERMILION, GREEN)
CM = 100.0  # m -> cm


def read_csv(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    return {k: np.array([float(r[k]) for r in rows]) for k in rows[0]}


def step_index(times, t):
    """Last output step at or before t (the converged state at the end of a step)."""
    return int(np.searchsorted(times, t + 1e-6) - 1)


def front_faces(ax, xyz, faces):
    """The faces that face the camera, so a solid skin hides its own back."""
    return [f for f in faces if facing(ax, xyz[f])]


def mark_steps(ax):
    for t in STEP_TIMES:
        ax.axvline(t, color=MUTED, lw=0.6, ls=(0, (3, 3)), zorder=0)


def step_names(ax):
    """Step names above the axes, between the step boundaries."""
    for x, name in ((70.0, "Step 1"), (7.0e3, "Step 2"), (1.025e5, "3")):
        ax.text(x, 1.02, name, color=MUTED, ha="center", va="bottom",
                transform=ax.get_xaxis_transform())


# --------------------------------------------------------------- figures


def fig_schematic():
    """The problem: two bonded blocks, the face conditions of Table 3."""
    fig = plt.figure(figsize=(170 * MM, 105 * MM))
    box_a = (-9, 9, -6, 6, -4, 0)
    box_b = (-9, 9, -6, 6, 0, 4)
    outer = (-9, 9, -6, 6, -4, 4)
    ax = axon_axes(fig, outer, rect=(0.12, 0.08, 0.76, 0.84), elev=24, azim=-58)
    draw_block(ax, box_a, BLOCK_A)
    draw_block(ax, box_b, BLOCK_B)
    add_box_edges(ax, outer, color=INK, linewidth=0.8)
    anchors = [
        (0, -6, -2),   # block A front face
        (0, -6, 2),    # block B front face
        (0, 0, 4),     # top
        (9, 0, -2),    # right
        (-4, -6, 0),   # interface on the front face
    ]
    texts = [
        "Block A: heat source $\\dot q = \\phi^2$",
        "Block B",
        "Top: pressure $p(t)$, film $h(t)\\,(T - T_\\infty(t))$",
        "Right, Front: plane remains plane",
        "Interface $z = 0$: shared nodes",
    ]
    place_labels_3d(ax, anchors, texts, blocks=[outer], fontsize=9,
                    captions=["Left, Back, Bottom: symmetric", "all faces but Top: adiabatic"])
    save(fig, OUT / "fig_schematic.png", title="Two-block problem", date=DATE, dpi=DPI)


def fig_mesh():
    """The mesh: 18 x 12 x 16 HEX8, blocks colored, interface marked."""
    with ExodusFile(EXO) as exo:
        xyz = exo.coords * CM
        faces = exo.surface_faces()
        n_elem = sum(len(b.connect) for b in exo.blocks)
    fig = plt.figure(figsize=(150 * MM, 95 * MM))
    box = bounds(xyz)
    ax = axon_axes(fig, box, rect=(0.05, 0.08, 0.9, 0.84), elev=24, azim=-58)
    add_box_edges(ax, box, color=INK, linewidth=0.8)
    keep = front_faces(ax, xyz, faces)
    face_colors = [BLOCK_A if xyz[f][:, 2].mean() < 0 else BLOCK_B for f in keep]
    add_surface(ax, xyz, keep, facecolors=face_colors, alpha=1.0, linewidth=0.25)
    ring = [[(-9, -6, 0), (9, -6, 0)], [(9, -6, 0), (9, 6, 0)]]
    ax.add_collection3d(Line3DCollection(ring, colors=INK, linewidths=1.6, zorder=2.5))
    place_labels_3d(ax, [(0, -6, -2), (0, -6, 2), (9, 0, 0)],
                    ["Block A", "Block B", "interface"], blocks=[box], fontsize=9,
                    captions=[f"{n_elem} HEX8, 1 cm elements"])
    save(fig, OUT / "fig_mesh.png", title="Mesh", date=DATE, dpi=DPI)


def fig_history_thermal():
    d = read_csv(HERE / "two_block_exact.csv")
    keep = d["time"] > 0
    t = d["time"][keep]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(150 * MM, 110 * MM), sharex=True)
    ax1.plot(t, d["T_max_A"][keep], color=BLOCK_A, label="max T, block A")
    ax1.plot(t, d["T_max_B"][keep], color=BLOCK_B, label="max T, block B")
    ax1.plot(t, d["T_top"][keep], color=INK, ls="--", label="mean T, top face")
    ax1.set_ylabel("temperature [C]")
    ax1.legend(frameon=False, loc="upper left")
    ax2.plot(t, d["heat_out_top"][keep], color=VERMILION)
    ax2.axhline(0, color=GRID, lw=0.6, zorder=0)
    ax2.set_ylabel("heat out of top face [W]")
    ax2.set_xlabel("time [s]")
    for ax in (ax1, ax2):
        ax.set_xscale("log")
        mark_steps(ax)
    step_names(ax1)
    fig.align_ylabels()
    save(fig, OUT / "fig_history_thermal.png", title="Thermal history", date=DATE, dpi=DPI)


def fig_deformed():
    """Deformed shape at the end of Steps 2 and 3, colored by displacement magnitude."""
    scale = 50.0
    with ExodusFile(EXO) as exo:
        xyz = exo.coords
        faces = exo.surface_faces()
        times = exo.times
        states = []
        for name, t in STEP_ENDS[1:]:
            i = step_index(times, t)
            u = np.column_stack([exo.nodal(f"disp_{c}", step=i) for c in "xyz"])
            states.append((name, u))
    umax = max(np.linalg.norm(u, axis=1).max() for _, u in states) * 1e6
    norm = colors.Normalize(0, umax)
    cmap = plt.get_cmap("viridis")
    fig = plt.figure(figsize=(170 * MM, 85 * MM))
    box = bounds(np.vstack([(xyz + scale * u) * CM for _, u in states] + [xyz * CM]), pad=0.3)
    for k, (name, u) in enumerate(states):
        ax = axon_axes(fig, box, rect=(0.02 + 0.44 * k, 0.12, 0.44, 0.8), elev=24, azim=-58)
        add_box_edges(ax, bounds(xyz * CM), color=MUTED, linewidth=0.6)
        mag = np.linalg.norm(u, axis=1) * 1e6
        moved = (xyz + scale * u) * CM
        keep = front_faces(ax, moved, faces)
        fc = cmap(norm(np.array([mag[f].mean() for f in keep])))
        add_surface(ax, moved, keep, facecolors=fc, alpha=1.0, linewidth=0.15)
        panel_label(ax, f"({'ab'[k]}) {name}")
    cax = fig.add_axes((0.9, 0.2, 0.018, 0.6))
    bar = fig.colorbar(cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax)
    bar.set_label("|u| [um]")
    fig.text(0.46, 0.04, f"displacement magnified {scale:.0f}x; gray: undeformed outline",
             ha="center", color=MUTED)
    save(fig, OUT / "fig_deformed.png", title="Deformed shape", date=DATE, dpi=DPI)


FIGURES = [fig_schematic, fig_mesh, fig_history_thermal, fig_deformed]

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    only = os.environ.get("ONLY")
    for f in FIGURES:
        if only and f.__name__ != only:
            continue
        try:
            f()
            print("ok  ", f.__name__)
        except Exception as error:
            print("FAIL", f.__name__, type(error).__name__, str(error)[:1500])
