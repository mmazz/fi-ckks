#!/usr/bin/env python3
"""Flat scan: one point per (limb, coeff, bit), no averaging over coefficients.

The x axis is a running index over the whole register file: every bit of coefficient 0,
then every bit of coefficient 1, and so on (with --order bit it is transposed: every
coefficient of bit 0, then every coefficient of bit 1). The y axis is the error.

This is the "naive" view: it keeps the coefficient structure that bit_curve.py averages
away, so a periodic pattern (gap-aligned coefficients, NTT butterflies) shows up as a
regular comb instead of being hidden inside a mean.

Seeds of the same config are averaged first, exactly like bit_curve.py.

Examples:
  python3 flat_curve.py --title enc_c0 --where library=heaan stage=encrypt_c0 pipeline= logN=6
  python3 flat_curve.py --title enc_c0_gap --where ... --color gap
  python3 flat_curve.py --title enc_c0_bitmajor --where ... --order bit
  python3 flat_curve.py --title mul --where ... stage=mul --per op_step
"""
import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

sys.path.append(str(Path(__file__).resolve().parent))
from utils.results import (load_campaigns, load_data, select,  # noqa: E402
                           require_single_config, parse_value)

FONT = 18
IMG_DIR = Path(__file__).resolve().parent / "img"
COLOR_ALL = "#4382B4"
COLOR_GAP = "#E31A1C"      # coeff % gap == 0
COLOR_NOGAP = "#4382B4"
COLOR_OVERFLOW = "#AA3377"
MAX_SEPARATORS = 80        # above this many blocks the separators are just ink


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default="../results")
    p.add_argument("--where", nargs="+", default=[], metavar="COL=VAL")
    p.add_argument("--per", default=None, help="column: one figure per value (e.g. op_step)")
    p.add_argument("--metric", default="l2_rel", help="data column to plot")
    p.add_argument("--order", choices=["coeff", "bit"], default="coeff",
                   help="coeff: all bits of coeff 0, then coeff 1, ... | bit: transposed")
    p.add_argument("--color", choices=["none", "gap"], default="none",
                   help="gap: one colour for coeff %% gap == 0, another for the rest")
    p.add_argument("--drop_coeffs", nargs="*", default=[], help="coefficients to exclude: 0 N/2 ...")
    p.add_argument("--style", choices=["line", "dots"], default="line")
    p.add_argument("--title", default="flat_curve")
    p.add_argument("--show", action="store_true")
    return p.parse_args()


def load_flat(camps, results, drop_coeffs, metric):
    """One row per (limb, coeff, bit), seeds already averaged. Returns (df, cfg)."""
    cfg = require_single_config(camps).iloc[0]
    n = 1 << int(cfg["logN"])
    gap = (n // 2) // (1 << int(cfg["logSlots"]))

    d = load_data(camps, results)
    drop = {n // 2 if c == "N/2" else int(c) for c in drop_coeffs}
    d = d[~d["coeff"].isin(drop)]
    d = d.groupby(["limb", "coeff", "bit"], as_index=False)[metric].mean()

    d["gap_aligned"] = (d["coeff"] % gap == 0)
    d["overflow"] = ~np.isfinite(d[metric].to_numpy())
    return d.sort_values(["limb", "coeff", "bit"]).reset_index(drop=True), cfg, gap


def flat_index(d, cfg, order):
    """Running x index, plus (block size, number of blocks, name of the block axis)."""
    n = 1 << int(cfg["logN"])
    n_bits = int(cfg["bitsPerCoeff"])
    limb, coeff, bit = (d[c].to_numpy() for c in ("limb", "coeff", "bit"))
    if order == "coeff":                      # all bits of coeff 0, then coeff 1, ...
        return (limb * n + coeff) * n_bits + bit, n_bits, (limb.max() + 1) * n, "coeff"
    # transposed: all coefficients of bit 0, then bit 1, ...
    n_coeffs = (limb.max() + 1) * n
    return bit * n_coeffs + limb * n + coeff, n_coeffs, n_bits, "bit"


def plot_flat(ax, d, cfg, gap, args):
    x, block, n_blocks, block_name = flat_index(d, cfg, args.order)
    y = d[args.metric].to_numpy(dtype=float)
    finite = np.isfinite(y)
    if not finite.any():
        raise ValueError(f"every {args.metric} value is non-finite")

    # Block separators first, so the data draws on top of them.
    if n_blocks <= MAX_SEPARATORS:
        for b in range(1, n_blocks):
            ax.axvline(b * block - 0.5, color="black", lw=0.4, alpha=0.25, zorder=1)

    # masked_invalid keeps the x positions: the line BREAKS at a non-finite value instead
    # of joining across it (and instead of the whole line silently disappearing).
    if args.style == "line":
        ax.plot(x, np.ma.masked_invalid(y), lw=0.8, color="#999999", zorder=2)

    if args.color == "gap":
        aligned = d["gap_aligned"].to_numpy()
        groups = [(aligned & finite, COLOR_GAP, f"coeff % {gap} == 0"),
                  (~aligned & finite, COLOR_NOGAP, f"coeff % {gap} != 0")]
    else:
        groups = [(finite, COLOR_ALL, None)]

    for mask, color, label in groups:
        if mask.any():
            ax.plot(x[mask], y[mask], ls="none", marker="o", ms=2.4, color=color,
                    label=label, zorder=3)

    # y limits BEFORE the rug: autoscaling with an inf in the data leaves the top at inf.
    # pad() never overflows: a single flip in a high bit already reaches ~2^800.
    def pad(v, factor):
        out = v * factor
        return out if np.isfinite(out) and out > 0 else v
    ymax = float(y[finite].max())
    ypos = y[finite & (y > 0)]
    if ypos.size and ypos.size == int(finite.sum()):     # no zeros: plain log reads better
        ax.set_yscale("log")
        ax.set_ylim(pad(float(ypos.min()), 1 / 3.0), pad(ymax, 3.0))
    else:
        ax.set_yscale("symlog", linthresh=_linthresh(y[finite]))
        ax.set_ylim(0, pad(ymax, 3.0))

    # Non-finite rows (a flip above logQ can overflow the decode) get a rug at the top,
    # so an overflowing bit is visible instead of being a hole in the curve.
    if (~finite).any():
        ax.plot(x[~finite], np.full((~finite).sum(), 0.97), ls="none", marker="|", ms=9,
                color=COLOR_OVERFLOW, transform=ax.get_xaxis_transform(), zorder=4,
                label=f"non-finite ({(~finite).sum()})")

    step = max(1, n_blocks // 16)
    ax.set_xticks([b * block + block / 2 for b in range(0, n_blocks, step)])
    ax.set_xticklabels([str(b % (1 << int(cfg["logN"]))) if block_name == "coeff" else str(b)
                        for b in range(0, n_blocks, step)], rotation=90, fontsize=FONT - 8)
    ax.set_xlim(float(x.min()) - block * 0.02, float(x.max()) + block * 0.02)

    ax.set_xlabel(f"{'Coefficient' if block_name == 'coeff' else 'Bit'}"
                  f"  (each block = {block} {'bits' if block_name == 'coeff' else 'coefficients'})",
                  fontsize=FONT)
    ax.set_ylabel(args.metric, fontsize=FONT)
    ax.tick_params(axis="y", labelsize=FONT - 4)
    ax.grid(True, axis="y", ls="--", alpha=0.3)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    if ax.get_legend_handles_labels()[1]:
        ax.legend(fontsize=FONT - 6, frameon=False, ncol=3,
                  loc="lower left", bbox_to_anchor=(0, 1.005))


def _linthresh(values):
    pos = values[values > 0]
    return float(10 ** np.floor(np.log10(pos.min()))) if len(pos) else 1e-12


def make_figure(d, cfg, gap, args, name):
    width = 20 if len(d) > 2000 else 14
    fig, ax = plt.subplots(figsize=(width, 5.5))
    plot_flat(ax, d, cfg, gap, args)
    fig.suptitle(f"{cfg['stage']}  [{cfg['pipeline']}]  logQ={cfg['logQ']}  "
                 f"log$\\Delta$={cfg['logDelta']}", fontsize=FONT - 2, y=1.10)

    IMG_DIR.mkdir(exist_ok=True)
    out = IMG_DIR / name
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=120)
    print(f"-> {out}.png  ({len(d)} points)")
    if args.show:
        plt.show()
    plt.close(fig)


def main():
    args = parse_args()
    filters = {k: parse_value(v) for k, v in (w.split("=", 1) for w in args.where)}
    camps = select(load_campaigns(args.results), **filters)
    if camps.empty:
        sys.exit(f"No finished campaigns match {filters}")

    per_values = sorted(camps[args.per].unique()) if args.per else [None]
    for pv in per_values:
        sub = camps if pv is None else camps[camps[args.per] == pv]
        try:
            d, cfg, gap = load_flat(sub, args.results, args.drop_coeffs, args.metric)
        except ValueError as e:
            sys.exit(f"ERROR: {e}\n  -> add a --where filter, or use --per on that column")
        name = args.title if pv is None else f"{args.title}_{args.per}_{pv}"
        make_figure(d, cfg, gap, args, name)


if __name__ == "__main__":
    main()
