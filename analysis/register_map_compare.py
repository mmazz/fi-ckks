#!/usr/bin/env python3
"""Register maps side by side, one panel per numbered injection site.

The panels come from an enum in utils/sites.py: each member is
(panel number, stage, op_step). --diagram picks the enum and --panels picks which
numbers to draw, in that order. Everything else must be the same config (only seed and
seed_input may vary, and they are combined with --stat).

Examples:
  python3 register_map_compare.py --title mul --diagram mul --panels 1 3 4 7 8 9 \\
      --where library=heaan logN=6 logSlots=3 logQ=60 logDelta=25 bitsPerCoeff=64 "pipeline=add; mul"

  python3 register_map_compare.py --title client --diagram client \\
      --where library=heaan logN=6 logSlots=5 logQ=60 logDelta=25 bitsPerCoeff=64 pipeline=mul

--where must not contain stage or op_step: the enum sets them.
One color scale is shared by all panels.
"""
import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator

sys.path.append(str(Path(__file__).resolve().parent))
import register_map as rm                                              # noqa: E402
from utils.results import (load_campaigns, load_data, select, require_single_config,  # noqa: E402
                           assign_config_id, finite_max, parse_value)
from utils.sites import DIAGRAMS, select_sites                         # noqa: E402

EMPTY = (1.0, 1.0, 1.0, 1.0)     # (coeff, bit) that was never injected: white


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default="../results")
    p.add_argument("--where", nargs="+", default=[], metavar="COL=VAL",
                   help='exact filters, e.g. library=heaan "pipeline=add; mul"')
    p.add_argument("--diagram", required=True, choices=list(DIAGRAMS),
                   help="which enum of utils/sites.py defines the panels")
    p.add_argument("--panels", nargs="+", type=int, default=None,
                   help="panel numbers to draw, in this order (default: the whole enum)")
    p.add_argument("--stat", choices=["median", "mean", "max"], default="median",
                   help="how to combine the seeds in each (coeff, bit)")
    p.add_argument("--title", default="register_compare", help="output file name prefix")
    p.add_argument("--no-legend", "--no_legend", dest="no_legend", action="store_true")
    p.add_argument("--show", action="store_true")
    return p.parse_args()


# ------------------------------------------------------------------ #
# Data
# ------------------------------------------------------------------ #
def load_panels(args, sites):
    """[(number, cfg, cells, n_campaigns)], one per site, in the order of `sites`."""
    filters = {k: parse_value(v) for k, v in (w.split("=", 1) for w in args.where)}
    for col in ("stage", "op_step"):
        if col in filters:
            raise ValueError(f"remove {col} from --where: the diagram enum sets it")

    camps = select(load_campaigns(args.results), **filters)
    per_site = []
    for number, stage, op_step in sites:
        group = camps[(camps["stage"] == stage) & (camps["op_step"] == op_step)]
        if group.empty:
            raise ValueError(f"panel {number}: no finished campaigns with "
                             f"stage={stage} op_step={op_step} and {filters}")
        per_site.append((number, group))

    # All panels must share the config except for stage/op_step. Overwrite those two
    # columns with a constant, recompute config_id, and let the usual check say which
    # other column differs (typically op_depth or pipeline missing from --where).
    together = pd.concat([g for _, g in per_site], ignore_index=True)
    together[["stage", "op_step"]] = ["*", -1]
    try:
        require_single_config(assign_config_id(together))
    except ValueError as exc:
        raise ValueError(f"the panels differ in more than stage/op_step: {exc}. "
                         f"Add those columns to --where.") from exc

    panels = []
    for number, group in per_site:
        cfg = require_single_config(group).iloc[0]          # only seeds may vary
        cells = rm.mrep_per_cell(load_data(group, args.results), args.stat)
        panels.append((number, cfg, cells, len(group)))
    return panels


# ------------------------------------------------------------------ #
# Plot
# ------------------------------------------------------------------ #
def panel_image(cells, cfg, vmax):
    """(bits, x, RGBA) image: one pixel per (coeff, bit), limbs side by side."""
    N = 1 << int(cfg["logN"])
    n_limbs = int(cells["limb"].max()) + 1
    n_bits = int(cfg["bitsPerCoeff"])
    img = np.tile(np.array(EMPTY), (n_bits, N * n_limbs, 1))
    x = cells["limb"].to_numpy() * N + cells["coeff"].to_numpy()
    y = cells["bit"].to_numpy()
    img[y, x] = rm.mrep_colors(cells["mrep"].to_numpy(dtype=float), vmax)
    return img, N, n_limbs


def draw_panel(ax, number, cells, cfg, vmax, first):
    img, N, n_limbs = panel_image(cells, cfg, vmax)
    n_bits, n_x = img.shape[:2]
    # One pixel per cell: no marker-size tuning, no gaps, exact at any figure size.
    ax.imshow(img, origin="lower", aspect="auto", interpolation="nearest",
              extent=(-0.5, n_x - 0.5, -0.5, n_bits - 0.5))
    for limb in range(1, n_limbs):                   # limb separators (OpenFHE)
        ax.axvline(limb * N - 0.5, color="black", lw=1)

    ax.set_xticks([0, n_x - 1])
    ax.set_xticklabels(["0", str(n_x - 1)], fontsize=rm.FONT - 8)
    ax.yaxis.set_major_locator(MaxNLocator(4, integer=True))
    ax.tick_params(axis="y", labelsize=rm.FONT - 8, left=first, labelleft=first)
    ax.text(0.5, -0.16, str(number), transform=ax.transAxes, ha="center", va="center",
            color="white", fontsize=rm.FONT - 6, fontweight="bold", clip_on=False,
            bbox=dict(boxstyle="circle,pad=0.3", facecolor="red", edgecolor="black", lw=0.8))


def plot_comparison(panels, vmax, show_legend):
    n = len(panels)
    fig, axes = plt.subplots(1, n, figsize=(max(6.0, 1.9 * n + 1.0), 4.2),
                             sharey=True, squeeze=False)
    axes = axes[0]
    left, right, bottom, top = 0.10, 0.98, 0.26, (0.88 if show_legend else 0.95)
    fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top, wspace=0.12)

    for i, (ax, (number, cfg, cells, _)) in enumerate(zip(axes, panels)):
        draw_panel(ax, number, cells, cfg, vmax, first=(i == 0))

    fig.text(0.05, (bottom + top) / 2, "i-th Bit of Register", rotation=90,
             ha="center", va="center", fontsize=rm.FONT - 6, fontweight="bold")
    fig.text((left + right) / 2, 0.03, "Coefficients",
             ha="center", va="center", fontsize=rm.FONT - 6, fontweight="bold")
    if show_legend:
        # One compact row. register_map.add_legend() is sized for one big panel and
        # overlaps short panels; the severe gradient is still red -> black in the plot.
        handles = [Patch(facecolor=color, edgecolor="black", lw=0.5, label=label)
                   for color, label in [
                       (rm.GREEN, rf"Masked ($\leq${rm.MASKED_PCT:g}%)"),
                       (rm.YELLOW, rf"Minor SDC ($\leq${rm.MINOR_PCT:g}%)"),
                       (rm.ORANGE, rf"Moderate SDC ($\leq${rm.MODERATE_PCT:g}%)"),
                       (rm.RED, rf"Severe SDC ($>${rm.MODERATE_PCT:g}%)")]]
        fig.legend(handles=handles, loc="upper center", ncol=4, frameon=False,
                   fontsize=rm.FONT - 8, bbox_to_anchor=((left + right) / 2, 1.0))
    return fig


# ------------------------------------------------------------------ #
def main():
    args = parse_args()
    try:
        sites = select_sites(args.diagram, args.panels)
        panels = load_panels(args, sites)
    except (ValueError, KeyError) as exc:
        sys.exit(f"ERROR: {exc}")

    vmax = finite_max([cells["mrep"] for _, _, cells, _ in panels], rm.MODERATE_PCT)
    fig = plot_comparison(panels, vmax, show_legend=not args.no_legend)

    rm.IMG_DIR.mkdir(parents=True, exist_ok=True)
    out = rm.IMG_DIR / args.title
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=150)
    for number, _, cells, reps in panels:
        print(f"  panel {number}: {len(cells)} cells, {reps} repetition(s)")
    print(f"-> {out}.png / .pdf")
    if args.show:
        plt.show()
    plt.close(fig)


if __name__ == "__main__":
    main()
