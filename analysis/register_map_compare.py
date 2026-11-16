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
--letters prefixes the panel labels with (a), (b), ...; --letters f starts at (f).
--no_labels leaves the space under the panels empty (the paper adds subcaptions).
--font sets the base font size; every text in the figure scales with it.
--separate saves each panel in its own file (<title>_1, <title>_2, ...) and the legend
alone in two rows (<title>_legend), all with the same color scale. Only the first panel
of each row has the y axis (--y_axis 1 4: rows 1-3 and 4-5): include them in LaTeX with
the same height, not the same width.
--legend_file keeps all the panels in one file and saves the legend alone, as --separate.

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
import step_heatmap as sh                                              # noqa: E402
sys.path.append(str(Path(__file__).resolve().parent))
import register_map as rm                                              # noqa: E402
from utils.results import (load_campaigns, load_data, select, require_single_config,  # noqa: E402
                           assign_config_id, finite_max, parse_value)
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
    p.add_argument("--separate", action="store_true",
                   help="one file per panel (<title>_1, <title>_2, ...) plus the legend alone "
                        "(<title>_legend, skipped with --no-legend), all with the same color scale")
    p.add_argument("--legend_file", action="store_true",
                   help="all panels in one file, the legend alone in <title>_legend; the figure "
                        "is only as wide as the panels (as with --separate)")
    p.add_argument("--no_labels", action="store_true",
                   help="with --vary: no text under the panels (e.g. the paper puts it in "
                        "\\subcaption); the x axis title moves up to the tick labels")
    p.add_argument("--y_axis", nargs="+", type=int, default=[1], metavar="K",
                   help="the panels (1, 2, ...) that start a row in the paper, which get the "
                        "y axis; the panel before each one gets the logDelta / logQ names "
                        "(default: 1, a single row). 0: no y axis at all (a file that goes "
                        "on the right of another one in the paper)")
    p.add_argument("--fill_bits", action="store_true",
                   help="random campaigns inject a subset of the bits: give each row that was not "
                        "injected the color of the next injected bit above it, instead of white")
    p.add_argument("--per_limb", action="store_true",
                   help="one column per limb: combine the coefficients of each limb with --limb_stat")
    p.add_argument("--limb_stat", choices=["max", "median", "mean"], default="max",
                   help="with --per_limb: how to combine the coefficients of a limb (default: max)")
    p.add_argument("--no_refs", action="store_true",
                   help="do not draw the logDelta / logQ lines (useful in RNS, where the bit does not matter)")
    p.add_argument("--taco", action="store_true",
                   help=f"masked threshold of {rm.TACO_MASKED_PCT:g}%% instead of {rm.MASKED_PCT:g}%%")
    p.add_argument("--collapse", type=float, default=None, metavar="TOL",
                   help="with --vary op_step: one panel per pattern of steps, found as in "
                        "step_heatmap.py --collapse --tol TOL; each panel draws the first step "
                        "of its group and is labelled with the steps of the group")
    p.add_argument("--letters", nargs="?", const="a", default=None, metavar="FIRST",
                   help="with --vary: prefix each panel label with (a), (b), ...; FIRST is the "
                        "first letter (e.g. --letters f continues a figure that ended at (e))")
    p.add_argument("--font", type=float, default=rm.FONT, metavar="PT",
                   help=f"base font size; every text in the figure scales with it (default: {rm.FONT})")
    p.add_argument("--label_size", type=float, default=None, metavar="PT",
                   help="font size of the text under each panel (default: --font - 6)")
    p.add_argument("--metric", default="linf_rel",
                   help="relative error column used for the colors (default: linf_rel = MREP), "
                        "e.g. l2_rel; the same categories and thresholds are applied")
    p.add_argument("--show", action="store_true")
    args = p.parse_args()
    if (args.diagram is None) == (args.vary is None):
        p.error("give exactly one of --diagram or --vary")
    if args.collapse is not None and args.vary != "op_step":
        p.error("--collapse needs --vary op_step")
    if args.collapse is not None and args.values:
        p.error("give --values or --collapse, not both")
    if args.labels and len(args.labels) != len(args.values or []):
        p.error("--labels needs one entry per --values")
    if args.no_labels and (args.letters or args.diagram):
        p.error("--no_labels draws no text under the panels: drop --letters / --diagram")
    if args.letters and args.diagram:
        p.error("--letters only applies to --vary (--diagram draws a numbered badge)")
    if args.letters and not (len(args.letters) == 1 and args.letters.isalpha()):
        p.error("--letters takes a single letter, e.g. --letters f")
    if args.label_size is None:
        args.label_size = args.font - 6
    args.masked = rm.TACO_MASKED_PCT if args.taco else rm.MASKED_PCT

    return args

# ------------------------------------------------------------------ #
# Data
# ------------------------------------------------------------------ #
def step_groups(camps, args):
    """Groups of op_steps with the same pattern, as step_heatmap.py --collapse finds them
    (MREP categories, aligned and non-aligned coefficients together, tolerance --collapse)."""
    hargs = argparse.Namespace(color="mrep", stat=args.stat, coeff_stat="median",
                               tol=args.collapse, floor=None, gap="all", results=args.results)
    curves = sh.step_curves(camps, args.results, hargs)
    return sh.collapse_patterns(camps, curves, hargs)


def panel_values(camps, args):
    """Values and labels of the --vary panels: --values as given, every value found in the
    data if --values is missing, or one per pattern with --collapse."""
    if args.collapse is not None:
        groups = step_groups(camps, args)
        return [g[0] for g in groups], [sh.fmt_steps(g) for g in groups]
    values = args.values or sorted(camps[args.vary].unique())
    return values, args.labels or [str(v) for v in values]
def per_limb_cells(cells, stat):
    """One row per (limb, bit), the coefficients of each limb combined with `stat`.
    The limb index is moved to `coeff`, so panel_image draws one column per limb."""
    out = cells.groupby(["limb", "bit"], as_index=False)["mrep"].agg(stat)
    return out.assign(coeff=out["limb"], limb=0)

def metric_per_cell(data, metric, stat):
    """Same as register_map.mrep_per_cell, for any relative error column (in %).

    On a collapsed dir the seeds are already combined and `{metric}_{stat}` holds that
    stat, so it is picked by name. The result keeps the name `mrep`, so the colors and
    the categories work unchanged."""
    col = f"{metric}_{stat}" if f"{metric}_{stat}" in data.columns else metric
    if col not in data.columns:
        options = sorted(c for c in data.columns if "rel" in c)
        raise ValueError(f"no column {col!r} in the data; relative columns: {options}")
    data = data.assign(mrep=data[col].astype(float) * 100.0)
    return data.groupby(["limb", "coeff", "bit"], as_index=False)["mrep"].agg(stat)

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
        values, labels = panel_values(camps, args)
        wanted = [(label, camps[args.vary] == (parse_value(v) if isinstance(v, str) else v),
                   f"{args.vary}={v}") for label, v in zip(labels, values)]

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
        cells = metric_per_cell(load_data(group, args.results), args.metric, args.stat)
        if args.ylim:
            cells = cells[cells["bit"].between(*args.ylim)]
        if args.per_limb:
            cells = per_limb_cells(cells, args.limb_stat)
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


def panel_image(cells, cfg, vmax, masked, fill=False, width=None):
    """(bits, x, RGBA) image: one pixel per (coeff, bit), limbs side by side.
    `width` overrides N (with --per_limb, one column per limb)."""
    N = width or (1 << int(cfg["logN"]))

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
    width = int(cells["coeff"].max()) + 1 if args.per_limb else None
    img, N, n_limbs = panel_image(cells, cfg, vmax, args.masked, fill=args.fill_bits, width=width)
    n_bits, n_x = img.shape[:2]
    # One pixel per cell: no marker-size tuning, no gaps, exact at any figure size.
    ax.imshow(img, origin="lower", aspect="auto", interpolation="nearest",
              extent=(-0.5, n_x - 0.5, -0.5, n_bits - 0.5))
    for limb in range(1, n_limbs):                   # limb separators (OpenFHE)
        ax.axvline(limb * N - 0.5, color="black", lw=1)
    if args.ylim:
        ax.set_ylim(args.ylim[0] - 0.5, args.ylim[1] + 0.5)
    lo, hi = ax.get_ylim()
    refs = [] if args.no_refs else [(cfg["logDelta"], r"$\log\Delta$"), (cfg["logQ"], r"$\log Q$")]
    # logDelta and logQ a few bits apart (e.g. 59 and 60): the two names would overlap,
    # so the lower one goes under its line and the upper one over it.
    close = len(refs) == 2 and abs(cfg["logQ"] - cfg["logDelta"]) < 0.08 * (hi - lo)
    for val, name in refs:
        if lo < val - 0.5 < hi:
            ax.axhline(val - 0.5, color="black", lw=1, ls="--", zorder=4)
            if last:
                upper = val == max(v for v, _ in refs)
                va = ("bottom" if upper else "top") if close else "center"
                ax.text(n_x - 0.5, val - 0.5, f" {name}", va=va, ha="left",
                        fontsize=args.font - 8, clip_on=False)

    cut = boot_cutoff_bit(cfg) if args.boot_cutoff else np.nan
    if np.isfinite(cut) and lo < cut - 0.5 < hi:
        # Between the last bit that still reaches the output and the first one removed.
        ax.axhline(cut - 0.5, color=CUT_COLOR, lw=2.5, ls=(0, (1.5, 1.5)), zorder=4)
    ax.set_xticks([0, n_x - 1])
    ax.set_xticklabels(["0", str(n_x - 1)], fontsize=args.font - 8)
    ax.yaxis.set_major_locator(MaxNLocator(4, integer=True))
    ax.tick_params(axis="y", labelsize=args.font - 8, left=first, labelleft=first)

    # The label goes a fixed distance (in points) under the tick labels, so the gap
    # does not change with the figure height or the font sizes.
    below = dict(xy=(0.5, 0), xycoords="axes fraction", xytext=(0, -label_offset(args)),
                 textcoords="offset points", ha="center", va="top", annotation_clip=False)
    if args.diagram:            # register number of the datapath figure: red badge
        ax.annotate(str(number), color="white", fontsize=args.font - 6, fontweight="bold",
                    bbox=dict(boxstyle="circle,pad=0.3", facecolor="red", edgecolor="black",
                              lw=0.8), **below)
    elif not args.no_labels:    # --vary: plain text label
        ax.annotate(str(number), fontsize=args.label_size, **below)


# Space under the panels, in points. A line of text takes ~1.2 times its font size; the
# x tick marks and their padding take ~7 pt (matplotlib defaults: 3.5 + 3.5).
GAP_PT = 4          # between the tick labels, the panel labels and the x axis title


def label_offset(args):
    """From the bottom of the panel to the top of the label under it."""
    return 7 + 1.2 * (args.font - 8) + GAP_PT


def bottom_margin_pt(args):
    """From the bottom of the panels to the bottom of the x axis title."""
    labels = 0 if args.no_labels else 1.2 * args.label_size + GAP_PT
    return label_offset(args) + labels + 1.2 * (args.font - 6) + GAP_PT


def legend_handles(args):
    handles = [Patch(facecolor=color, edgecolor="black", lw=0.5, label=label)
               for color, label in [
                   (rm.GREEN, rf"Masked ($\leq${args.masked:g}%)"),
                   (rm.YELLOW, rf"Minor SDC ($\leq${rm.MINOR_PCT:g}%)"),
                   (rm.ORANGE, rf"Moderate SDC ($\leq${rm.MODERATE_PCT:g}%)"),
                   (rm.RED, rf"Severe SDC ($>${rm.MODERATE_PCT:g}%)")]]
    if args.boot_cutoff:
        handles.append(Line2D([], [], color=CUT_COLOR, lw=2.5, ls=(0, (1.5, 1.5)),
                              label="Boot cutoff"))
    return handles
 
 
PANEL_H = 2.9       # height of the panels in inches, the same with or without the legend


def draw_legend(fig, handles, ncol, fontsize, x=0.5):
    """Legend on top of the figure, centered at `x`. Returns (legend, width, height),
    the sizes in inches."""
    leg = fig.legend(handles=handles, loc="upper center", ncol=ncol, frameon=False,
                     fontsize=fontsize, bbox_to_anchor=(x, 1.0))
    box = leg.get_window_extent(fig.canvas.get_renderer())
    return leg, box.width / fig.dpi, box.height / fig.dpi


def plot_comparison(panels, vmax, show_legend, args, first_index=0, n_total=None,
                    compact=False):
    """first_index / n_total: position of panels[0] among all the panels and how many
    there are (--separate draws one at a time). Only the first panel of each row has the
    y axis (title and tick labels), only the last one the logDelta / logQ names; the rows
    start at --y_axis.
    compact: the width only fits the panels (the legend is in another file)."""
    n = len(panels)
    n_total = n_total or n
    row_starts = {k - 1 for k in args.y_axis}
    has_y = first_index in row_starts
    k = args.font / rm.FONT         # --font: the left margin grows with the text
    # Room for the y title and the tick labels, in inches; without them, almost none.
    left_in = k * 0.9 if has_y else 0.05
    fig, axes = plt.subplots(1, n, sharey=True, squeeze=False)
    axes = axes[0]
    # One compact legend. register_map.add_legend() is sized for one big panel and
    # overlaps short panels; the severe gradient is still red -> black in the plot.
    handles, fontsize = legend_handles(args), args.font - 8

    # The figure is at least as wide as the legend in two columns, also with --no-legend:
    # figures made by the same command (e.g. one per depth, only one with the legend) then
    # have the same width, and the same scale when LaTeX fits them to the same width.
    leg, legend_w, _ = draw_legend(fig, handles, 2, fontsize)
    leg.remove()
    if compact:
        width = (1.9 * n + left_in) / 0.98
    else:
        width = max(6.0, 1.9 * n + 1.0, (legend_w + left_in) / 0.98)
    left, right = left_in / width, 0.98
    fig.set_size_inches(width, PANEL_H)

    top_in = 0.2                    # above the panels: room for half a tick label
    if show_legend:
        # As few rows as fit within the width of the panels; two columns always fit.
        for ncol in sorted({len(handles), -(-len(handles) // 2), 2}, reverse=True):
            leg, w, h = draw_legend(fig, handles, ncol, fontsize, x=(left + right) / 2)
            if w <= (right - left) * width or ncol == 2:
                break
            leg.remove()
        top_in = h + GAP_PT / 72
    # Margins in inches around panels of fixed height: the legend makes the figure taller
    # instead of the panels shorter.
    bottom_in = bottom_margin_pt(args) / 72
    height = PANEL_H + top_in + bottom_in
    fig.set_size_inches(width, height)
    bottom, top = bottom_in / height, 1 - top_in / height
    fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top, wspace=0.12)

    for i, (ax, (number, cfg, cells, _)) in enumerate(zip(axes, panels)):
        if args.letters:            # (a), (b), ... in front of the label under the panel
            number = f"({chr(ord(args.letters) + first_index + i)}) {number}"
        j = first_index + i         # position among all the panels
        draw_panel(ax, number, cells, cfg, vmax, first=(j in row_starts),
                   last=(j + 1 in row_starts or j == n_total - 1), args=args)

    if has_y:
        fig.text(k * 0.35 / width, (bottom + top) / 2, "i-th Bit of Register", rotation=90,
                 ha="center", va="center", fontsize=args.font - 6, fontweight="bold")
    # x axis title right under the panel labels (its bottom at the bottom of the margin).
    fig.text((left + right) / 2, GAP_PT / 72 / height,
             "Limbs" if args.per_limb else "Coefficients",
             ha="center", va="bottom", fontsize=args.font - 6, fontweight="bold")
    return fig


def plot_legend(args):
    """The legend alone, in two rows (--separate, --legend_file), to fit a paper column."""
    fig = plt.figure()
    handles = legend_handles(args)
    draw_legend(fig, handles, -(-len(handles) // 2), args.font - 8)
    return fig


def save(fig, out):
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=150)
    print(f"-> {out}.png / .pdf")


# ------------------------------------------------------------------ #
def main():
    args = parse_args()
    try:
        sites = select_sites(args.diagram, args.panels) if args.diagram else None
        panels = load_panels(args, sites)
    except (ValueError, KeyError) as exc:
        sys.exit(f"ERROR: {exc}")

    vmax = finite_max([cells["mrep"] for _, _, cells, _ in panels], rm.MODERATE_PCT)
    for number, _, cells, reps in panels:
        print(f"  panel {number}: {len(cells)} cells, {reps} repetition(s)")
    rm.IMG_DIR.mkdir(parents=True, exist_ok=True)
    out = rm.IMG_DIR / args.title
    if args.separate:
        # Same vmax in every file, so the colors compare across the panels.
        figs = [(plot_comparison([panel], vmax, show_legend=False, args=args, first_index=i,
                                 n_total=len(panels), compact=True),
                 out.with_name(f"{out.name}_{i + 1}"))
                for i, panel in enumerate(panels)]
    elif args.legend_file:
        figs = [(plot_comparison(panels, vmax, show_legend=False, args=args, compact=True), out)]
    else:
        figs = [(plot_comparison(panels, vmax, show_legend=not args.no_legend, args=args), out)]
    if (args.separate or args.legend_file) and not args.no_legend:
        figs.append((plot_legend(args), out.with_name(f"{out.name}_legend")))
    for fig, path in figs:
        save(fig, path)
    if args.show:
        plt.show()
    for fig, _ in figs:
        plt.close(fig)


if __name__ == "__main__":
    main()
