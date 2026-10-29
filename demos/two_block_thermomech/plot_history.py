#!/usr/bin/env python3
"""Plot the history of the two-block demo from the postprocessor CSV files."""

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
STEPS = (500.0, 1.0e5)


def read(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    return {k: [float(r[k]) for r in rows] for k in rows[0]}


def mark_steps(ax):
    for t in STEPS:
        ax.axvline(t, color="0.6", lw=0.8, ls="--")


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "two_block_exact"
    d = read(HERE / f"{base}.csv")
    # Drop t = 0 so the time axis can be logarithmic
    keep = [i for i, ti in enumerate(d["time"]) if ti > 0]
    d = {k: [v[i] for i in keep] for k, v in d.items()}
    t = d["time"]

    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), sharex=True)

    ax = axes[0, 0]
    for k, lab in [
        ("T_max_A", "max T, block A"),
        ("T_max_B", "max T, block B"),
        ("T_interface", "mean T, interface"),
        ("T_top", "mean T, top face"),
    ]:
        ax.plot(t, d[k], label=lab)
    ax.set_ylabel("Temperature [C]")
    ax.legend(frameon=False)

    ax = axes[0, 1]
    ax.plot(t, d["heat_out_top"], color="C3")
    ax.set_ylabel("Heat flux out of the top face [W]")

    ax = axes[1, 0]
    ax.plot(t, [s / 1e6 for s in d["sxx_interface"]], label="mean stress_xx, interface")
    ax.plot(t, [s / 1e6 for s in d["szz_interface"]], label="mean stress_zz, interface")
    ax.plot(t, [s / 1e6 for s in d["vonmises_max"]], label="max von Mises")
    ax.set_ylabel("Stress [MPa]")
    ax.legend(frameon=False)

    ax = axes[1, 1]
    ax.plot(t, d["Rz_bottom"], label="Rz, Bottom")
    ax.plot(t, d["Rx_left"], label="Rx, Left")
    ax.plot(t, d["Ry_back"], label="Ry, Back")
    ax.set_ylabel("Reaction force [N]")
    ax.legend(frameon=False)

    for ax in axes.flat:
        ax.set_xscale("log")
        mark_steps(ax)
    for ax in axes[1]:
        ax.set_xlabel("Time [s]")

    fig.suptitle(f"Two-block thermomechanical demo ({base})")
    fig.tight_layout()
    out = HERE / f"{base}_history.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
