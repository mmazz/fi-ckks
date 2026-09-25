#!/usr/bin/env python3
"""One row per op_step, one column per flipped bit.

This is the base figure of every server operation: steps that behave the same show up
as identical rows. The script also groups the steps into patterns and prints one
representative per pattern, which is what goes into MUL_REPR in scripts/serverCampaigns.py.

Two colorings (--color):
  mrep  (default) the categories of register_map.py: Masked / Minor / Moderate / Severe
        SDC, from the MREP = linf_rel in %. Same colors as the register maps, so a row of
        this figure can be compared directly with the map of that op_step. Seeds are
        combined with --stat (as in register_map.py), then the coefficients of each bit
        with --coeff_stat. Two steps are the same pattern if their categories differ in
        at most --tol bits.
  log2  mean log2(l2_rel), continuous. Shows the structure of the error even where it is
        far below anything visible in the output. Two steps are the same pattern if their
        curves differ by less than --tol bits of log2 on every bit. --floor sets what
        counts as masked.

Combining the coefficients mixes the ones the decode reads with the rest: use
--gap aligned / --gap other when logSlots < logN - 1.

  python3 step_heatmap.py --title op_mul \\
      --where library=heaan stage=mul pipeline=mul logN=6 logSlots=3 logQ=60 \\
              logDelta=30 bitsPerCoeff=124 --gap aligned
  python3 step_heatmap.py --title op_rescale --per op_depth --where ... stage=rescale
"""
import argparse
import sys
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

sys.path.append(str(Path(__file__).resolve().parent))
import register_map as rm                                                   # noqa: E402
from utils.results import (ERR_CEIL, ERR_FLOOR, finite_max, load_campaigns,  # noqa: E402
                           load_data, parse_value, require_single_config, select)

FONT = 20
TICK_FONT = 14
IMG_DIR = Path(__file__).resolve().parent / "img"
ERR_CEIL_BITS = np.log2(ERR_CEIL)    # err_bits of an overflowed flip (see utils/results.py)
ERR_FLOOR_BITS = np.log2(ERR_FLOOR)  # err_bits of a fully masked flip (error exactly 0)
NOT_FLIPPED = "#dddddd"              # bit not injected at this step


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default="../results")
    p.add_argument("--where", nargs="+", default=[], metavar="COL=VAL")
    p.add_argument("--query", default=None, help="extra pandas filter over the campaigns")
    p.add_argument("--per", default=None, help="column: one figure per value (e.g. op_depth)")
    p.add_argument("--color", choices=["mrep", "log2"], default="mrep",
                   help="mrep: register_map categories (default) | log2: mean log2(l2_rel)")
    p.add_argument("--stat", choices=["median", "mean", "max"], default="median",
                   help="mrep: how to combine the seeds in each (coeff, bit), as in register_map.py")
    p.add_argument("--coeff_stat", choices=["median", "mean", "max"], default="median",
                   help="mrep: how to combine the coefficients of each bit")
    p.add_argument("--tol", type=float, default=None,
                   help="same pattern if: mrep -> the categories differ in at most TOL bits "
                        "(default 0) | log2 -> the curves differ by less than TOL bits of log2 "
                        "on every bit (default 1)")
    p.add_argument("--floor", type=float, default=None,
                   help="log2 only: err_bits at or below this count as masked (white). -10 is "
                        "about the Masked threshold of register_map.py (default: exactly 0)")
    p.add_argument("--gap", choices=["all", "aligned", "other"], default="all",
                   help="only the coefficients the decode reads (aligned), only the rest, or all")
    p.add_argument("--title", default="step_heatmap")
    p.add_argument("--suptitle", default="", help="text above the figure (default: none)")
    p.add_argument("--show", action="store_true")
    args = p.parse_args()
    if args.tol is None:
        args.tol = 0 if args.color == "mrep" else 1.0
    return args


def select_campaigns(args):
    filters = {k: parse_value(v) for k, v in (w.split("=", 1) for w in args.where)}
    camps = select(load_campaigns(args.results), **filters)
    if args.query:
        camps = camps.query(args.query)
    if camps.empty:
        sys.exit(f"No finished campaigns match --where {args.where} --query {args.query!r}")
    return camps


# ------------------------------------------------------------------ #
# Data
# ------------------------------------------------------------------ #
def step_curves(camps, results, args):
    """DataFrame: index = op_step, columns = bit. Value: MREP in % (mrep) or mean err_bits (log2)."""
    rows = {}
    for step, g in camps.groupby("op_step"):
        try:
            cfg = require_single_config(g).iloc[0]
        except ValueError as e:
            sys.exit(f"ERROR at op_step={step}: {e}\n  -> add a filter with --where / --query")
        d = load_data(g, results)
        if args.gap != "all":
            gap = ((1 << int(cfg["logN"])) // 2) // (1 << int(cfg["logSlots"]))
            aligned = d["coeff"] % gap == 0
            d = d[aligned] if args.gap == "aligned" else d[~aligned]
        if args.color == "mrep":
            cells = rm.mrep_per_cell(d, args.stat)                           # seeds combined
            rows[int(step)] = cells.groupby("bit")["mrep"].agg(args.coeff_stat)
        else:
            per_coeff = d.groupby(["limb", "coeff", "bit"])["err_bits"].mean()   # mean over seeds
            rows[int(step)] = per_coeff.groupby("bit").mean()                      # mean over coeffs
    return pd.DataFrame(rows).T.sort_index()


def categories(values):
    """register_map category of each MREP: 0 masked, 1 minor, 2 moderate, 3 severe, -1 NaN."""
    cat = np.digitize(values, [rm.MASKED_PCT, rm.MINOR_PCT, rm.MODERATE_PCT], right=True)
    cat = np.where(np.isnan(values), -1, cat)
    return np.where(np.isinf(values), 3, cat)


def patterns(curves, args):
    """Greedy grouping: each step joins the first pattern whose representative is close
    enough (see --tol) on every bit both have. Returns a list of lists of op_step."""
    groups = []
    for step, row in curves.iterrows():
        for g in groups:
            ref = curves.loc[g[0]]
            both = ref.notna() & row.notna()
            if args.color == "mrep":
                same = (categories(ref[both].to_numpy()) != categories(row[both].to_numpy())).sum() <= args.tol
            else:
                diff = (ref[both] - row[both]).abs()
                same = diff.empty or diff.max() < args.tol
            if same:
                g.append(step)
                break
        else:
            groups.append([step])
    return groups


# ------------------------------------------------------------------ #
# Plot
# ------------------------------------------------------------------ #
def draw_mrep(fig, ax, values):
    """Same colors as register_map.py: categories, severe as a red -> black log gradient."""
    vmax = finite_max(values, rm.MODERATE_PCT)
    flat = values.ravel()
    rgba = rm.mrep_colors(flat, vmax)
    rgba[np.isnan(flat)] = mcolors.to_rgba(NOT_FLIPPED)
    ax.imshow(rgba.reshape(*values.shape, 4), aspect="auto", interpolation="nearest")
    handles = [Patch(facecolor=color, edgecolor="black", lw=0.5, label=label)
               for color, label in [
                   (rm.GREEN, rf"Masked ($\leq${rm.MASKED_PCT:g}%)"),
                   (rm.YELLOW, rf"Minor SDC ($\leq${rm.MINOR_PCT:g}%)"),
                   (rm.ORANGE, rf"Moderate SDC ($\leq${rm.MODERATE_PCT:g}%)"),
                   (rm.RED, rf"Severe SDC ($>${rm.MODERATE_PCT:g}%, up to {vmax:.3g}%)"),
                   (NOT_FLIPPED, "not injected")]]
    # Above the axes, clear of the logDelta / logQ labels.
    ax.legend(handles=handles, loc="lower center", ncol=3, frameon=False,
              fontsize=TICK_FONT, bbox_to_anchor=(0.5, 1.05))


def draw_log2(fig, ax, values, floor):
    # Sequential, light = small error. It starts at 15% of Blues so the smallest real error
    # is still visibly blue and never looks like the white of a masked bit.
    cmap = mcolors.ListedColormap(plt.get_cmap("Blues")(np.linspace(0.15, 1.0, 256)))
    cmap.set_bad(NOT_FLIPPED)
    cmap.set_over("black")                  # saturated: the flip overflowed (inf l2_rel)
    cmap.set_under("white")                 # at or below the floor: masked
    floor = ERR_FLOOR_BITS if floor is None else floor
    # The scale comes from the cells with a real error: an overflow is clipped to
    # ERR_CEIL_BITS and a masked flip sits at the floor, and either one would squash every
    # real difference into one color.
    real = values[np.isfinite(values) & (values > floor + 1e-9) & (values < ERR_CEIL_BITS - 1)]
    vmin, vmax = (float(real.min()), float(real.max())) if real.size else (None, None)
    im = ax.imshow(np.ma.masked_invalid(values), aspect="auto", cmap=cmap,
                   interpolation="nearest", vmin=vmin, vmax=vmax)
    cb = fig.colorbar(im, ax=ax, pad=0.01, extend="both")
    cb.set_label(r"mean $\log_2 L_2^{rel}$", fontsize=FONT - 4)
    cb.ax.tick_params(labelsize=TICK_FONT)


def plot(curves, groups, cfg, name, args):
    # Columns are only the bits that were flipped, so a random campaign (a subset of the
    # bits) does not leave empty stripes.
    bits = curves.columns.to_numpy()
    fig, ax = plt.subplots(figsize=(14, 0.35 * len(curves) + 2.5))
    values = curves.to_numpy(dtype=float)
    if args.color == "mrep":
        draw_mrep(fig, ax, values)
    else:
        draw_log2(fig, ax, values, args.floor)

    # Row labels: op_step and its pattern letter.
    letter = {s: chr(ord("A") + i) for i, g in enumerate(groups) for s in g}
    ax.set_yticks(range(len(curves)))
    ax.set_yticklabels([f"{s} ({letter[s]})" for s in curves.index], fontsize=TICK_FONT - 2)
    ax.set_ylabel("op_step (pattern)", fontsize=FONT)

    step = max(1, len(bits) // 16)
    ax.set_xticks(range(0, len(bits), step))
    ax.set_xticklabels(bits[::step], fontsize=TICK_FONT)
    ax.set_xlabel("Bit index", fontsize=FONT)

    for col, label in [("logDelta", r"$\log\Delta$"), ("logQ", r"$\log Q$")]:
        pos = np.searchsorted(bits, cfg[col])
        if 0 < pos < len(bits):
            ax.axvline(pos - 0.5, color="black", ls="--", lw=1)
            ax.text(pos - 0.5, 1.01, label, transform=ax.get_xaxis_transform(),
                    ha="center", va="bottom", fontsize=TICK_FONT)

    if args.suptitle:
        ax.set_title(args.suptitle, fontsize=FONT - 2, pad=24)
    IMG_DIR.mkdir(exist_ok=True)
    out = IMG_DIR / name
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=120)
    print(f"-> {out}.png")
    if args.show:
        plt.show()
    plt.close(fig)


def main():
    args = parse_args()
    camps = select_campaigns(args)
    per_values = sorted(camps[args.per].unique()) if args.per else [None]
    for pv in per_values:
        sub = camps if pv is None else camps[camps[args.per] == pv]
        curves = step_curves(sub, args.results, args)
        if args.color == "log2" and args.floor is not None:
            # Below the floor every error counts as masked: clip so the patterns do not
            # split steps over differences nobody can see in the output.
            curves = curves.clip(lower=args.floor)
        groups = patterns(curves, args)
        name = args.title if pv is None else f"{args.title}_{args.per}_{pv}"
        print(f"{name}: {len(curves)} steps -> {len(groups)} patterns ({args.color}, tol = {args.tol})")
        for i, g in enumerate(groups):
            print(f"  {chr(ord('A') + i)}: steps {g}  (representative: {g[0]})")
        print(f"  representatives: {[g[0] for g in groups]}")
        plot(curves, groups, sub.iloc[0], name, args)


if __name__ == "__main__":
    main()
