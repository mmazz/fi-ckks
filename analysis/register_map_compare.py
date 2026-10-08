#!/usr/bin/env python3
"""Register maps side by side, with one common color scale (built on register_map.py).

One panel per value of --vary (typically stage or op_step); every other config column
must be the same across panels. Works on a raw results dir (the collapsed cache is
refreshed first) or on a collapsed one; each panel combines the seeds with --stat.


Example (pipelines as panels):
  python3 register_map_compare.py --results ../results_client --title boot_map \\
      --where library=heaan logN=6 logSlots=3 logQ=840 logDelta=40 bitsPerCoeff=860 \\
              stage=encrypt_c1 \\
      --vary pipeline --values "mul x4" "mul; boot" "mul x2; boot" \\
      --labels "4 mul" "1 mul + boot" "2 mul + boot" --ylim 0 300 --boot_cutoff
--values picks the panels and their order; --numbers sets the label drawn under each
panel (default 1..n). The --vary column must not be in --where.
One figure per op_step, all with the same color scale. With --vary op_step, a single
figure compares those steps. --no-legend hides the top legend; panel numbers stay.
"""
import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator
from matplotlib.lines import Line2D

sys.path.append(str(Path(__file__).resolve().parent))
import register_map as rm                                              # noqa: E402
from utils.results import (load_campaigns, load_data, select, require_single_config,  # noqa: E402
                           assign_config_id, finite_max, parse_value, assign_config_id)
from utils.sites import DIAGRAMS, select_sites                         # noqa: E402
from bit_curve import boot_cutoff_bit                                  # noqa: E402

EMPTY = (1.0, 1.0, 1.0, 1.0)     # (coeff, bit) that was never injected: white
CUT_COLOR = "#1F4E9C"            # --boot_cutoff line: blue, absent from the MREP colors

def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default="../results")
    p.add_argument("--where", nargs="+", default=[], metavar="COL=VAL",
                   help='exact filters, e.g. library=heaan "pipeline=add; mul"')
    p.add_argument("--diagram", default=None, choices=list(DIAGRAMS),
                   help="which enum of utils/sites.py defines the panels (or use --vary)")
    p.add_argument("--vary", default=None,
                   help="instead of --diagram: one panel per value of this column (e.g. pipeline)")
    p.add_argument("--values", nargs="+", default=None,
                   help="with --vary: the values to draw, in panel order")
    p.add_argument("--labels", nargs="+", default=None,
                   help="with --vary: text under each panel (default: the value itself)")
    p.add_argument("--ylim", nargs=2, type=int, default=None, metavar=("LO", "HI"),
                   help="bit range to draw; the color scale is computed on this range only")
    p.add_argument("--boot_cutoff", action="store_true",
                   help="HEAAN only: dotted line at the first bit the boot removes "
                        "(see bit_curve.boot_cutoff_bit)")
    p.add_argument("--panels", nargs="+", type=int, default=None,
                   help="panel numbers to draw, in this order (default: the whole enum)")
    p.add_argument("--stat", choices=["median", "mean", "max"], default="median",
                   help="how to combine the seeds in each (coeff, bit)")
    p.add_argument("--title", default="register_compare", help="output file name prefix")
    p.add_argument("--no-legend", "--no_legend", dest="no_legend", action="store_true")
    p.add_argument("--fill_bits", action="store_true",
                   help="random campaigns inject a subset of the bits: give each row that was not "
                        "injected the color of the next injected bit above it, instead of white")
    p.add_argument("--taco", action="store_true",
                   help=f"masked threshold of {rm.TACO_MASKED_PCT:g}%% instead of {rm.MASKED_PCT:g}%%")
    p.add_argument("--show", action="store_true")
    args = p.parse_args()
    if (args.diagram is None) == (args.vary is None):
        p.error("give exactly one of --diagram or --vary")
    if args.vary and not args.values:
        p.error("--vary needs --values")
    if args.labels and len(args.labels) != len(args.values or []):
        p.error("--labels needs one entry per --values")
    args.masked = rm.TACO_MASKED_PCT if args.taco else rm.MASKED_PCT
    return args

# ------------------------------------------------------------------ #
# Data
# ------------------------------------------------------------------ #
def load_panels(args, sites):
    """[(number, cfg, cells, n_campaigns)], one per site, in the order of `sites`."""
    filters = {k: parse_value(v) for k, v in (w.split("=", 1) for w in args.where)}
    varying = ["stage", "op_step"] if args.diagram else [args.vary]
    for col in varying:
        if col in filters:
            raise ValueError(f"remove {col} from --where: it changes between panels")

    camps = select(load_campaigns(args.results), **filters)
    if args.diagram:
        wanted = [(number, (camps["stage"] == stage) & (camps["op_step"] == op_step),
                   f"stage={stage} op_step={op_step}") for number, stage, op_step in sites]
    else:
        labels = args.labels or args.values
        wanted = [(label, camps[args.vary] == parse_value(v), f"{args.vary}={v}")
                  for label, v in zip(labels, args.values)]
    per_site = []
    for label, mask, desc in wanted:
        group = camps[mask]
        if group.empty:
            raise ValueError(f"panel {label}: no finished campaigns with {desc} and {filters}")
        per_site.append((label, group))

    # All panels must share the config except for the varying columns. Overwrite them
    # with a constant, recompute config_id, and let the usual check say which other
    # column differs (typically op_depth or pipeline missing from --where).
    together = pd.concat([g for _, g in per_site], ignore_index=True)
    together = together.assign(**{c: "*" for c in varying})
    try:
        require_single_config(assign_config_id(together))
    except ValueError as exc:
        raise ValueError(f"the panels differ in more than {'/'.join(varying)}: {exc}. "
                         f"Add those columns to --where.") from exc

    panels = []
    for number, group in per_site:
        cfg = require_single_config(group).iloc[0]          # only seeds may vary
        cells = rm.mrep_per_cell(load_data(group, args.results), args.stat)
        if args.ylim:
            cells = cells[cells["bit"].between(*args.ylim)]
        panels.append((number, cfg, cells, len(group)))
    return panels


# ------------------------------------------------------------------ #
# Plot
# ------------------------------------------------------------------ #

def fill_unsampled_rows(img, sampled):
    """Each row that was not injected takes the next injected bit above it (the last
    injected one at the top of the panel). The random campaigns inject every bit around
    each boot cutoff (args.cpp), so no gap spans a transition there. The one coarse gap
    at a transition is right above logDelta without boot, where the error is already
    severe: filling from above keeps it severe, filling from below would paint it as
    the milder value at logDelta. Within a row, coefficients never injected stay white."""
    sampled = np.sort(np.unique(sampled))
    src = np.searchsorted(sampled, np.arange(img.shape[0]), side="left")
    return img[sampled[np.minimum(src, sampled.size - 1)]]

def panel_image(cells, cfg, vmax, masked, fill=False):
    """(bits, x, RGBA) image: one pixel per (coeff, bit), limbs side by side."""
    N = 1 << int(cfg["logN"])
    n_limbs = int(cells["limb"].max()) + 1
    n_bits = int(cfg["bitsPerCoeff"])
    img = np.tile(np.array(EMPTY), (n_bits, N * n_limbs, 1))
    x = cells["limb"].to_numpy() * N + cells["coeff"].to_numpy()
    y = cells["bit"].to_numpy()
    img[y, x] = rm.mrep_colors(cells["mrep"].to_numpy(dtype=float), vmax, masked)
    if fill:
        img = fill_unsampled_rows(img, y)
    return img, N, n_limbs

def draw_panel(ax, number, cells, cfg, vmax, first, last, args):
    img, N, n_limbs = panel_image(cells, cfg, vmax, args.masked, fill=args.fill_bits)
    n_bits, n_x = img.shape[:2]
    # One pixel per cell: no marker-size tuning, no gaps, exact at any figure size.
    ax.imshow(img, origin="lower", aspect="auto", interpolation="nearest",
              extent=(-0.5, n_x - 0.5, -0.5, n_bits - 0.5))
    for limb in range(1, n_limbs):                   # limb separators (OpenFHE)
        ax.axvline(limb * N - 0.5, color="black", lw=1)
    if args.ylim:
        ax.set_ylim(args.ylim[0] - 0.5, args.ylim[1] + 0.5)
    lo, hi = ax.get_ylim()
    # Same references as register_map.py; the name is written once, right of the last panel.
    for val, name in [(cfg["logDelta"], r"$\log\Delta$"), (cfg["logQ"], r"$\log Q$")]:
        if lo < val - 0.5 < hi:
            ax.axhline(val - 0.5, color="black", lw=1, ls="--", zorder=4)
            if last:
                ax.text(n_x - 0.5, val - 0.5, f" {name}", va="center", ha="left",
                        fontsize=rm.FONT - 8, clip_on=False)
    cut = boot_cutoff_bit(cfg) if args.boot_cutoff else np.nan
    if np.isfinite(cut) and lo < cut - 0.5 < hi:
        # Between the last bit that still reaches the output and the first one removed.
        ax.axhline(cut - 0.5, color=CUT_COLOR, lw=2.5, ls=(0, (1.5, 1.5)), zorder=4)
    ax.set_xticks([0, n_x - 1])
    ax.set_xticklabels(["0", str(n_x - 1)], fontsize=rm.FONT - 8)
    ax.yaxis.set_major_locator(MaxNLocator(4, integer=True))
    ax.tick_params(axis="y", labelsize=rm.FONT - 8, left=first, labelleft=first)

    if args.diagram:            # register number of the datapath figure: red badge
        ax.text(0.5, -0.16, str(number), transform=ax.transAxes, ha="center", va="center",
                color="white", fontsize=rm.FONT - 6, fontweight="bold", clip_on=False,
                bbox=dict(boxstyle="circle,pad=0.3", facecolor="red", edgecolor="black", lw=0.8))
    else:                       # --vary: plain text label
        ax.text(0.5, -0.16, str(number), transform=ax.transAxes, ha="center", va="center",
                fontsize=rm.FONT - 6, clip_on=False)

def plot_comparison(panels, vmax, show_legend, args):
    n = len(panels)
    fig, axes = plt.subplots(1, n, figsize=(max(6.0, 1.9 * n + 1.0), 4.2),
                             sharey=True, squeeze=False)
    axes = axes[0]
    # With 3 panels or fewer the legend does not fit in one row: it takes two or three.
    top = 0.95 if not show_legend else (0.88 if n > 3 else 0.74)
    # Fixed margins in inches, so the y label never runs into the ticks of a narrow figure.
    width = fig.get_figwidth()
    left, right, bottom = 0.9 / width, 0.98, 0.26
    fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top, wspace=0.12)

    for i, (ax, (number, cfg, cells, _)) in enumerate(zip(axes, panels)):
        draw_panel(ax, number, cells, cfg, vmax, first=(i == 0), last=(i == n - 1), args=args)

    fig.text(0.35 / width, (bottom + top) / 2, "i-th Bit of Register", rotation=90,
             ha="center", va="center", fontsize=rm.FONT - 6, fontweight="bold")
    fig.text((left + right) / 2, 0.03, "Coefficients",
             ha="center", va="center", fontsize=rm.FONT - 6, fontweight="bold")
    if show_legend:
        # One compact row. register_map.add_legend() is sized for one big panel and
        # overlaps short panels; the severe gradient is still red -> black in the plot.
        handles = [Patch(facecolor=color, edgecolor="black", lw=0.5, label=label)
                   for color, label in [
                       (rm.GREEN, rf"Masked ($\leq${args.masked:g}%)"),
                       (rm.YELLOW, rf"Minor SDC ($\leq${rm.MINOR_PCT:g}%)"),
                       (rm.ORANGE, rf"Moderate SDC ($\leq${rm.MODERATE_PCT:g}%)"),
                       (rm.RED, rf"Severe SDC ($>${rm.MODERATE_PCT:g}%)")]]
        if args.boot_cutoff:
            handles.append(Line2D([], [], color=CUT_COLOR, lw=2.5, ls=(0, (1.5, 1.5)),
                                  label="Boot cutoff"))
        fig.legend(handles=handles, loc="upper center", ncol=len(handles) if n > 3 else 2,
                   frameon=False, fontsize=rm.FONT - 8, bbox_to_anchor=((left + right) / 2, 1.0))
    return fig


# ------------------------------------------------------------------ #
def main():
    args = parse_args()
    try:
        sites = select_sites(args.diagram, args.panels) if args.diagram else None
        panels = load_panels(args, sites)
    except (ValueError, KeyError) as exc:
        sys.exit(f"ERROR: {exc}")

    vmax = finite_max([cells["mrep"] for _, _, cells, _ in panels], rm.MODERATE_PCT)
    fig = plot_comparison(panels, vmax, show_legend=not args.no_legend, args=args)
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
