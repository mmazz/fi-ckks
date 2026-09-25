#!/usr/bin/env python3
"""One row per op_step, one column per flipped bit, color = mean log2(l2_rel).

This is the base figure of every server operation: steps that behave the same show up
as identical rows. The script also groups the steps into patterns (rows whose curves
differ by less than --tol bits on every bit) and prints one representative per
pattern, which is what goes into MUL_REPR in scripts/serverCampaigns.py.

Seeds of the same config are averaged first in each (limb, coeff, bit), then the
coefficients of each bit are averaged. The metric is err_bits (log2 of l2_rel, clipped),
so an overflow (inf) counts as a very large error instead of disappearing.

  python3 step_heatmap.py --title op_mul \\
      --where library=heaan stage=mul_asplos pipeline=mul logN=6 logSlots=3 logQ=60 \\
              logDelta=30 bitsPerCoeff=124
  python3 step_heatmap.py --title op_rescale --per op_depth --where ... stage=rescale
"""
import argparse
import sys
from pathlib import Path
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
from utils.results import (ERR_CEIL, ERR_FLOOR, load_campaigns, load_data, parse_value,  # noqa: E402
                           require_single_config, select)

FONT = 20
TICK_FONT = 14
IMG_DIR = Path(__file__).resolve().parent / "img"
ERR_CEIL_BITS = np.log2(ERR_CEIL)   # err_bits of an overflowed flip (see utils/results.py)
ERR_FLOOR_BITS = np.log2(ERR_FLOOR) # err_bits of a fully masked flip (error exactly 0)

def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default="../results")
    p.add_argument("--where", nargs="+", default=[], metavar="COL=VAL")
    p.add_argument("--query", default=None, help="extra pandas filter over the campaigns")
    p.add_argument("--per", default=None, help="column: one figure per value (e.g. op_depth)")
    p.add_argument("--tol", type=float, default=1.0,
                   help="two steps are the same pattern if their curves differ by less than "
                        "this many bits (of log2 l2_rel) on every bit")
    p.add_argument("--gap", choices=["all", "aligned", "other"], default="all",
                   help="only the coefficients the decode reads (aligned), only the rest, or all")
    p.add_argument("--title", default="step_heatmap")
    p.add_argument("--suptitle", default="", help="text above the figure (default: none)")
    p.add_argument("--show", action="store_true")
    return p.parse_args()


def select_campaigns(args):
    filters = {k: parse_value(v) for k, v in (w.split("=", 1) for w in args.where)}
    camps = select(load_campaigns(args.results), **filters)
    if args.query:
        camps = camps.query(args.query)
    if camps.empty:
        sys.exit(f"No finished campaigns match --where {args.where} --query {args.query!r}")
    return camps


def step_curves(camps, results, gap_mode):
    """DataFrame: index = op_step, columns = bit, value = mean err_bits."""
    rows = {}
    for step, g in camps.groupby("op_step"):
        try:
            cfg = require_single_config(g).iloc[0]
        except ValueError as e:
            sys.exit(f"ERROR at op_step={step}: {e}\n  -> add a filter with --where / --query")
        d = load_data(g, results)
        if gap_mode != "all":
            gap = ((1 << int(cfg["logN"])) // 2) // (1 << int(cfg["logSlots"]))
            aligned = d["coeff"] % gap == 0
            d = d[aligned] if gap_mode == "aligned" else d[~aligned]
        per_coeff = d.groupby(["limb", "coeff", "bit"])["err_bits"].mean()   # average over seeds
        rows[int(step)] = per_coeff.groupby("bit").mean()                      # average over coeffs
    return pd.DataFrame(rows).T.sort_index()


def patterns(curves, tol):
    """Greedy grouping: each step joins the first pattern whose representative is within
    tol bits of it on every bit both have. Returns a list of lists of op_step."""
    groups = []
    for step, row in curves.iterrows():
        for g in groups:
            diff = (curves.loc[g[0]] - row).abs().dropna()
            if diff.empty or diff.max() < tol:
                g.append(step)
                break
        else:
            groups.append([step])
    return groups


def plot(curves, groups, cfg, name, args):
    # Columns are only the bits that were flipped, so a random campaign (a subset of the
    # bits) does not leave empty stripes.
    bits = curves.columns.to_numpy()
    fig, ax = plt.subplots(figsize=(14, 0.35 * len(curves) + 2.5))

    # Sequential, light = small error. It starts at 15% of Blues so the smallest real error
    # is still visibly blue and never looks like the white of a fully masked bit.
    cmap = mcolors.ListedColormap(plt.get_cmap("Blues")(np.linspace(0.15, 1.0, 256)))
    cmap.set_bad("#dddddd")                 # bit not flipped at this step
    cmap.set_over("black")                  # saturated: the flip overflowed (inf l2_rel)
    cmap.set_under("white")                 # error exactly 0 in every coefficient: masked
    values = curves.to_numpy(dtype=float)
    # The scale comes from the cells with a real error: an overflow is clipped to
    # ERR_CEIL_BITS and a masked flip sits at ERR_FLOOR_BITS, and either one would squash
    # every real difference into one color.
    masked = values <= ERR_FLOOR_BITS + 1e-9
    real = values[np.isfinite(values) & ~masked & (values < ERR_CEIL_BITS - 1)]
    vmin, vmax = (float(real.min()), float(real.max())) if real.size else (None, None)
    im = ax.imshow(np.ma.masked_invalid(values), aspect="auto", cmap=cmap,
                   interpolation="nearest", vmin=vmin, vmax=vmax)
    cb = fig.colorbar(im, ax=ax, pad=0.01, extend="both")
    cb.set_label(r"mean $\log_2 L_2^{rel}$", fontsize=FONT - 4)
    cb.ax.tick_params(labelsize=TICK_FONT)

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
        curves = step_curves(sub, args.results, args.gap)
        groups = patterns(curves, args.tol)
        name = args.title if pv is None else f"{args.title}_{args.per}_{pv}"
        print(f"{name}: {len(curves)} steps -> {len(groups)} patterns (tol = {args.tol} bits)")
        for i, g in enumerate(groups):
            print(f"  {chr(ord('A') + i)}: steps {g}  (representative: {g[0]})")
        print(f"  representatives: {[g[0] for g in groups]}")
        plot(curves, groups, sub.iloc[0], name, args)


if __name__ == "__main__":
    main()
