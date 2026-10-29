#!/usr/bin/env python3
"""Error per limb: x = limb where the bit was flipped, y = metric combined over every bit
and every coefficient of that limb (OpenFHE, RNS).

Seeds of the same config are first combined in each (limb, coeff, bit) with --seed_stat,
as in bit_curve.py. Then all the (coeff, bit) cells of each limb are combined with --stat.
Every sampled bit counts, also the ones above the prime of the limb.
  --vary COL    one curve per value of COL (typically pipeline)
  --per COL     one figure per value of COL (typically stage)
  --split gap   two files, <title>_aligned and <title>_other, as in bit_curve.py

Example (boot_rns group: fault in encrypt, 0, 1 and 2 muls before the boot):
  python3 limb_curve.py --results ../results_client --title rns_ntt_boot_limb \\
      --where library=openfhe logN=6 logSlots=3 logQ=60 logDelta=52 mult_depth=2 withNTT=1 \\
      --query 'stage in ["encrypt_c0", "encrypt_c1"]' --vary pipeline --per stage \\
      --order boot 'mul; boot' 'mul x2; boot' \\
      --labels '0 mul + boot' '1 mul + boot' '2 mul + boot'
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np

sys.path.append(str(Path(__file__).resolve().parent))
from bit_curve import (COLORS, FIGSIZE, FONT, SCATER_SIZE, SIZE_STEP, SPLIT_FIGSIZE, STATS,
                       TICK_FONT, load_curve_data, save_figure, select_campaigns)

# A limb counts as visible when its combined error is above this (same threshold as the
# "visible" criterion of the thesis, E_L2 > 1e-2). Only used for the printed summary.
VISIBLE = 1e-2
# Room below 0, as a fraction of linthresh (symlog) or of top/10 (linear).
ZERO_MARGIN = 0.25

def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default="../results")
    p.add_argument("--where", nargs="+", default=[], metavar="COL=VAL")
    p.add_argument("--query", default=None, help="extra pandas filter over the campaigns")
    p.add_argument("--vary", nargs="*", default=["pipeline"],
                   help="columns: one curve per combination of values (default: pipeline)")
    p.add_argument("--per", default=None, help="one figure per value of this column (e.g. stage)")
    p.add_argument("--split", choices=["none", "gap"], default="none",
                   help="gap: save <title>_aligned and <title>_other as two separate files")
    p.add_argument("--metric", default="l2_rel", help="column of data to be plotted")
    p.add_argument("--stat", choices=list(STATS), default="mean",
                   help="how to combine the (coeff, bit) cells of each limb")
    p.add_argument("--seed_stat", choices=["mean", "median"], default="mean",
                   help="how the repetitions of each (limb, coeff, bit) are combined")
    p.add_argument("--order", nargs="+", default=None,
                   help="values of the (single) --vary column in the order the curves are drawn")
    p.add_argument("--labels", nargs="+", default=None,
                   help="legend labels, one per curve, in the --order order")
    p.add_argument("--yscale", choices=["linear", "log", "symlog"], default="symlog")
    p.add_argument("--linthresh", type=float, default=VISIBLE,
                   help="symlog: linear region is [0, linthresh] (default %(default)s)")
    p.add_argument("--ylabel", default=None)
    p.add_argument("--lines", action="store_true", help="join the points of each curve")
    p.add_argument("--size", choices=["full", "half"], default=None,
                   help="full: FIGSIZE; half: SPLIT_FIGSIZE (default: half with --split gap)")
    p.add_argument("--title", default="limb_curve")
    p.add_argument("--show", action="store_true")
    args = p.parse_args()
    args.suptitle = ""            # save_figure() from bit_curve.py reads it
    return args


def curve_keys(data, vary, order):
    """Curve identities, in the order they are drawn, colored and listed."""
    keys = [k for k, _ in data.groupby(vary)]
    if not order:
        return keys
    by_name = {str(k[0] if isinstance(k, tuple) else k): k for k in keys}
    missing = [v for v in order if v not in by_name]
    if len(vary) != 1 or missing or len(order) != len(by_name):
        sys.exit(f"--order needs exactly one --vary column and all its values once: "
                 f"got {order}, the curves are {list(by_name)}")
    return [by_name[v] for v in order]


def per_limb(d, metric, stat):
    """One value per limb: `stat` over all its (coeff, bit) cells.
    Non-finite cells are left out and counted, so they do not turn the whole limb into inf."""
    vals = d[metric].to_numpy(dtype=float)
    finite = np.isfinite(vals)
    y = d[finite].groupby("limb")[metric].agg(STATS[stat])
    return y, int((~finite).sum())


def plot(ax, data, keys, args, ylim):
    vary = args.vary
    groups = dict(list(data.groupby(vary)))
    if args.labels and len(args.labels) != len(keys):
        sys.exit(f"--labels has {len(args.labels)} entries but there are {len(keys)} curves")
    for i, key in enumerate(keys):
        if key not in groups:
            continue
        y, n_bad = per_limb(groups[key], args.metric, args.stat)
        vals = key if isinstance(key, tuple) else (key,)
        label = args.labels[i] if args.labels else ", ".join(f"{k}={v}" for k, v in zip(vary, vals))
        visible = [int(l) for l, v in y.items() if v > VISIBLE]
        print(f"  {label}: limbs above {VISIBLE:g}: {visible}"
              + (f" ({n_bad} non-finite cells left out)" if n_bad else ""))
        color = COLORS[i % len(COLORS)]
        # First curve biggest and at the back: when two curves coincide, it shows as a ring.
        size = SCATER_SIZE + (len(keys) - 1 - i) * SIZE_STEP
        x = y.index.to_numpy(dtype=int)
        if args.lines:
            ax.plot(x, y.to_numpy(), color=color, lw=1.2, alpha=0.6, zorder=1 + i)
        ax.scatter(x, y.to_numpy(), s=size, color=color, label=label, zorder=2 + i)

    if args.yscale == "symlog":
        ax.set_yscale("symlog", linthresh=args.linthresh)
    else:
        ax.set_yscale(args.yscale)
    ax.set_ylim(*ylim)
    limbs = data["limb"].unique()
    ax.set_xlim(limbs.min() - 0.7, limbs.max() + 0.7)
    # Limbs are integers: steps of 1, 2, 5 or 10, so 21 limbs give 0, 2, ..., 20.
    ax.xaxis.set_major_locator(MaxNLocator(integer=True, steps=[1, 2, 5, 10]))
    ax.set_xlabel("Limb", fontsize=FONT)
    ax.set_ylabel(args.ylabel or f"{args.stat} {args.metric} ({args.yscale})", fontsize=FONT)
    ax.tick_params(labelsize=TICK_FONT)
    ax.grid(True, ls="--", alpha=0.3)


def y_limits(data, args):
    """Same y range for every file of one figure, from all its curves."""
    tops = []
    for _, d in data.groupby(args.vary):
        y, _ = per_limb(d, args.metric, args.stat)
        tops.append(y.max())
    top = max(tops) if tops else 1.0
    top = top * 3.0 if top > 0 else 1.0
    if args.yscale == "log":
        pos = data.loc[data[args.metric] > 0, args.metric]
        return (float(pos.min()) / 3.0 if len(pos) else 1e-12, top)
    # Bottom a bit below 0, so the points of the masked limbs (error 0) sit above the
    # x axis instead of being cut in half by it.
    if args.yscale == "symlog":
        return (-ZERO_MARGIN * args.linthresh, top)
    return (-ZERO_MARGIN * top / 10.0, top)

def make_figure(data, args, name):
    keys = curve_keys(data, args.vary, args.order)
    ylim = y_limits(data, args)
    half = args.size == "half" or (args.size is None and args.split == "gap")
    if args.split == "none":
        parts = {"": data}
    else:
        parts = {"_aligned": data[data["gap_aligned"]], "_other": data[~data["gap_aligned"]]}
    for suffix, part in parts.items():
        if part.empty:
            print(f"  {name}{suffix}: no coefficients in this subset (gap = 1), not saved")
            continue
        print(f"{name}{suffix}")
        fig, ax = plt.subplots(figsize=SPLIT_FIGSIZE if half else FIGSIZE)
        plot(ax, part, keys, args, ylim)
        if suffix != "_other":           # the legend goes once, in the first panel
            ax.legend(fontsize=FONT - 6, frameon=False)
        save_figure(fig, f"{name}{suffix}", args)


def main():
    args = parse_args()
    camps = select_campaigns(args)
    if (camps["library"] != "openfhe").any():
        print("WARNING: limbs only mean something in OpenFHE; HEAAN has a single limb 0")
    per_values = sorted(camps[args.per].unique()) if args.per else [None]
    for pv in per_values:
        sub = camps if pv is None else camps[camps[args.per] == pv]
        try:
            data = load_curve_data(sub, args.results, args.vary, [], args.metric,
                                   seed_stat=args.seed_stat)
        except ValueError as e:
            sys.exit(f"ERROR: {e}\n  -> add a filter with --where, or use --vary/--per for those columns")
        name = args.title if pv is None else f"{args.title}_{args.per}_{pv}"
        make_figure(data, args, name)


if __name__ == "__main__":
    main()
