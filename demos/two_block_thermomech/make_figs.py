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
EXACT, PENALTY = GREEN, VERMILION
STEP_TIMES = (500.0, 1.0e5)
# Step 2 ends just before 1e5 s: the output at 1e5 s already has the Step 3 loads
STEP_ENDS = (("end of Step 1", 500.0), ("end of Step 2", 1.0e5 - 1.0), ("end of Step 3", 1.05e5))
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


def fig_history_mechanical():
    d = read_csv(HERE / "two_block_exact.csv")
    keep = d["time"] > 0
    t = d["time"][keep]
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(150 * MM, 140 * MM), sharex=True)
    ax1.plot(t, d["sxx_interface"][keep] / 1e6, color=BLUE, label="mean stress_xx, interface")
    ax1.plot(t, d["vonmises_max"][keep] / 1e6, color=VERMILION, label="max von Mises")
    ax1.axhline(0, color=GRID, lw=0.6, zorder=0)
    ax1.set_ylabel("stress [MPa]")
    ax1.legend(frameon=False, loc="lower left")
    step_names(ax1)
    ax2.plot(t, d["Z_max"][keep] * 1e3, color=PURPLE)
    ax2.set_ylabel("max Z [$10^{-3}$]")
    ax3.plot(t, d["Rz_bottom"][keep], color=GREEN)
    ax3.axhline(2160, color=MUTED, lw=0.6, ls=":")
    ax3.set_ylabel("Rz, Bottom [N]")
    ax3.set_xlabel("time [s]")
    ax3.set_ylim(-200, 2600)
    for ax in (ax1, ax2, ax3):
        ax.set_xscale("log")
        mark_steps(ax)
    place_labels(ax3, [3e3], [2160], ["$p A$ = 2160 N"])
    fig.align_ylabels()
    save(fig, OUT / "fig_history_mechanical.png", title="Mechanical history", date=DATE, dpi=DPI)


def fig_profiles():
    """T and stress_xx through the thickness at the block center, at each step end."""
    with ExodusFile(EXO) as exo:
        xyz = exo.coords * CM
        times = exo.times
        corners = np.concatenate([b.corners for b in exo.blocks])
        cent = xyz[corners].mean(axis=1)
        # nodes on the center line x = 0, y = 0
        line = np.where((np.abs(xyz[:, 0]) < 1e-6) & (np.abs(xyz[:, 1]) < 1e-6))[0]
        line = line[np.argsort(xyz[line, 2])]
        # elements in the center column (x in [0, 1], y in [-0.5..]: nearest the center)
        col = np.where((np.abs(cent[:, 0] - 0.5) < 1e-6) & (np.abs(cent[:, 1] - 0.5) < 1e-6))[0]
        col = col[np.argsort(cent[col, 2])]
        data = []
        for (name, t), c in zip(STEP_ENDS, STEP_COLORS):
            i = step_index(times, t)
            T = exo.nodal("T", step=i)[line]
            sxx = np.concatenate([exo.elemental("stress_xx", step=i, block_id=b.id)
                                  for b in exo.blocks])[col] / 1e6
            data.append((name, c, T, sxx))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(160 * MM, 95 * MM), sharey=True)
    for name, c, T, sxx in data:
        ax1.plot(T, xyz[line, 2], color=c, label=name)
        z = cent[col, 2]
        edges = np.concatenate([[z[0] - 0.25], 0.5 * (z[1:] + z[:-1]), [z[-1] + 0.25]])
        ax2.stairs(sxx, edges, orientation="horizontal", color=c, baseline=None)
    for ax in (ax1, ax2):
        ax.axhspan(-4, 0, color=PALE_ORANGE, zorder=0)
        ax.axhline(0, color=INK, lw=0.6)
    ax2.axvline(0, color=GRID, lw=0.6, zorder=0)
    ax1.set_xlabel("temperature [C]")
    ax2.set_xlabel("stress_xx [MPa]")
    ax1.set_ylabel("z [cm]")
    ax1.set_ylim(-4, 4)
    handles, labels = ax1.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, loc="lower center", ncol=3,
               bbox_to_anchor=(0.5, 0.0))
    fig.text(0.02, 0.02, "shaded: block A", color=MUTED, ha="left")
    fig.subplots_adjust(bottom=0.24)
    save(fig, OUT / "fig_profiles.png", title="Through-thickness profiles", date=DATE, dpi=DPI)


def fig_prp():
    """Exact against penalty plane-remains-plane on the Right face."""
    ex = read_csv(HERE / "two_block_exact.csv")
    pe = read_csv(HERE / "two_block_penalty.csv")
    floor = 1e-21
    fig, ax = plt.subplots(figsize=(150 * MM, 80 * MM))
    for d, c, lab in ((ex, EXACT, "exact (#34249)"), (pe, PENALTY, "penalty 1e12")):
        keep = d["time"] > 0
        spread = np.maximum(np.maximum(d["prp_right_spread"], d["prp_front_spread"]), floor)
        ax.plot(d["time"][keep], spread[keep], color=c, label=lab)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_ylim(floor / 3, 1e-6)
    mark_steps(ax)
    ax.set_xlabel("time [s]")
    ax.set_ylabel("PRP error: max - min normal\ndisplacement on a PRP face [m]")
    ax.legend(frameon=False, loc="center right")
    place_labels(ax, [], [], [], captions=["exact: zero to round-off"])
    save(fig, OUT / "fig_prp_exact_vs_penalty.png", title="PRP error", date=DATE, dpi=DPI)


def fig_step3():
    """Step 3 on a linear time axis: pressure off, T_inf drops, phi off."""
    d = read_csv(HERE / "two_block_exact.csv")
    keep = d["time"] >= 9.9e4
    t = (d["time"][keep] - 1.0e5) / 1e3
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(150 * MM, 125 * MM), sharex=True)
    ax1.plot(t, d["T_max_A"][keep], color=BLOCK_A, label="max T, block A")
    ax1.plot(t, d["T_top"][keep], color=INK, ls="--", label="mean T, top face")
    ax1.set_ylabel("temperature [C]")
    ax1.legend(frameon=False, loc="lower left")
    ax2.plot(t, d["sxx_interface"][keep] / 1e6, color=BLUE, marker="o", ms=2.5)
    ax2.axhline(0, color=GRID, lw=0.6, zorder=0)
    ax2.set_ylabel("mean stress_xx,\ninterface [MPa]")
    ax3.plot(t, d["Rz_bottom"][keep], color=GREEN, marker="o", ms=2.5)
    ax3.set_ylabel("Rz, Bottom [N]")
    ax3.set_ylim(-200, 2600)
    ax3.set_xlabel("time after the start of Step 3 [$10^3$ s]")
    for ax in (ax1, ax2, ax3):
        ax.axvline(0, color=MUTED, lw=0.6, ls=(0, (3, 3)), zorder=0)
    fig.align_ylabels()
    save(fig, OUT / "fig_step3.png", title="Step 3", date=DATE, dpi=DPI)


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


FIGURES = [fig_schematic, fig_mesh, fig_history_thermal, fig_history_mechanical,
           fig_profiles, fig_prp, fig_step3, fig_deformed]

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
