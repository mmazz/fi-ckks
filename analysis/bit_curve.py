#!/usr/bin/env python3
"""Error per bit: x = flipped bit, y = l2_rel combined over coefficients.

Seeds of the same config are first averaged in each (limb, coeff, bit); then the
coefficients of each bit are combined with --stat.
  --split gap   two files, <title>_aligned (coefficients with coeff % gap == 0) and
                <title>_other (the rest), with gap = (N/2) / slots = 2^(logN - 1 - logSlots).
                Same y axis in both, so they can go side by side as two subfigures
  --vary COL    one curve per value of COL (logN, logQ, stage, library, gap_aligned, limb...)
  --per COL     one figure per value of COL (typically op_step)
  --labels ...  legend labels, one per curve, overriding the automatic ones

Examples:
  python3 bit_curve.py --title decode --where library=heaan stage=decode pipeline=add logQ=60
  python3 bit_curve.py --title logQ   --where stage=decode pipeline=add --vary logQ --xnorm over_q
  python3 bit_curve.py --title add_gap --where stage=add pipeline=add --per op_step --split gap
  python3 bit_curve.py --title logN --where library=heaan stage=encrypt_c0 pipeline= --vary logN \\
      --labels 'logN=6 - Mean $L_2$' 'logN=16 - Mean $L_2$'
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
from utils.results import (load_campaigns, load_data, load_reps, select,  
                           require_single_config, parse_value)
from build_ml_dataset import MULTS, expand, injection_index  
SIZE_STEP = 20   # each earlier curve is this much bigger, so identical curves stay visible
SCATER_SIZE = 24
FONT = 24
TICK_FONT = 18
IMG_DIR = Path(__file__).resolve().parent / "img"
FIGSIZE = (12, 5)
# --split gap: one panel of the old side-by-side figure (16x5 / 2), so the fonts keep
# their size when each file goes into a 0.49\textwidth subfigure.
SPLIT_FIGSIZE = (8, 5)
COLORS = ["#4382B4", "#E31A1C", "#EE7733", "#31A354", "#AA3377", "#663333", "#66CCEE", "#CCBB44"]
STATS = {"mean": "mean", "median": "median",
         "geomean": lambda x: float(np.exp(np.log(np.maximum(x, 1e-300)).mean()))}
# Metrics that live in [0, 1]: with --stat mean they are probabilities, so they get a
# linear y axis instead of symlog. See load_data() in utils/results.py.
RATE_METRICS = {"is_sdc", "is_masked", "frac_bad", "frac_failed", "detected",
                "misclassified", "sdc_undetected", "false_alarm"}
# --detect_onset: a (limb, coeff) counts as detected from the lowest bit where OpenFHE's
# SDC detector fired in at least this fraction of the repetitions (seed x seed_input).
DETECT_RATE = 0.5
# ------------------------------------------------------------------ #
# CLI
# ------------------------------------------------------------------ #

def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default="../results")
    p.add_argument("--where", nargs="+", default=[], metavar="COL=VAL")
    p.add_argument("--vary", nargs="*", default=[], help="columns: one curve per combination of values")
    p.add_argument("--per", default=None, help="one figure per value of this column (e.g. op_step)")
    p.add_argument("--split", choices=["none", "gap"], default="none",
                   help="gap: save <title>_aligned and <title>_other as two separate files")
    p.add_argument("--metric", default="l2_rel", help="column of data to be plotted")
    p.add_argument("--stat", choices=list(STATS), default="mean",
                   help="how to combine the coefficients of each bit")
    p.add_argument("--xnorm", choices=["none", "minus_delta", "over_q", "minus_level", "top_bit"],
                   default="none",
                   help="x axis: bit | bit - logDelta | bit / logQ | bit - logq of the injection "
                        "level | top bit of the burst (bit + amountBits - 1)")
    p.add_argument("--drop_coeffs", nargs="*", default=[], help="coefficients to be excluded: 0 N/2 ...")
    p.add_argument("--band", nargs="?", const="p10_90", default=None, choices=["p10_90", "std"],
                   help="shaded band across coefficients: p10_90 (default if no value) or std (mean +- 1 std)")
    p.add_argument("--minmax", action="store_true",
                   help="also mark the min and max across coefficients of each bit")
    p.add_argument("--linthresh", type=float, default=None,
                   help="symlog: linear region is [0, linthresh] (default: below the smallest non-zero error)")
    p.add_argument("--title", default="bit_curve")
    p.add_argument("--yscale", choices=["auto", "linear", "log", "symlog"], default="auto",
                   help="auto: linear for the rate metrics (is_sdc, frac_bad, detected, "
                        "misclassified), symlog for the error magnitudes")
    p.add_argument("--labels", nargs="+", default=None,
                   help="legend labels, one per curve, in the order of the sorted --vary values; "
                        "overrides the automatic 'col=value' labels")
    p.add_argument("--ylabel", default=None,
                   help="y axis label (default: '<stat> <metric> (<scale>)')")
    p.add_argument("--query", default=None,
                   help="extra pandas filter over the campaigns, for conditions --where cannot "
                        "express, e.g. 'logSlots == logN - 1', 'logDelta == 0.75 * logQ', "
                        "'stage in [\"encode\", \"encrypt_c0\"]'")
    p.add_argument("--no_refs", action="store_true",
                   help="do not draw the logDelta / logQ reference lines")
    p.add_argument("--suptitle", default="",
                   help="text above the figure (default: none). --title is only the file name")
    p.add_argument("--rep_spread", action="store_true",
                   help="shaded band = min..max over the repetitions (seed x seed_input) of the "
                        "per-bit curve, i.e. how much a single repetition can deviate")
    p.add_argument("--raw_spread",action="store_true",
                    help="shaded band = min..max per bit over all raw "
                         "(seed, seed_input, limb, coeff) values" )
    p.add_argument("--xlim", nargs=2, type=float, default=None, metavar=("LO", "HI"),
                   help="x axis range, in plotted units; reference lines outside it are dropped")
    p.add_argument("--ymax", type=float, default=None,
                   help="top of the y axis: values above it are drawn as open triangles on "
                        "the top edge instead of stretching the axis")
    p.add_argument("--lines", action="store_true",
                   help="join the points of each curve with a thin line")
    p.add_argument("--order", nargs="+", default=None,
                   help="values of the (single) --vary column in the order the curves are "
                        "drawn, colored and listed; --labels follows this order")
    p.add_argument("--boot_cutoff", action="store_true",
                   help="HEAAN only: dotted line per curve at the bit from which the boot "
                        "removes the fault, logq_boot + k*logDelta (k = mults before the boot)")
    p.add_argument("--detect_onset", action="store_true",
                   help="OpenFHE only: dash-dot line per curve at the mean bit from which the "
                        "SDC detector fires (per coefficient: lowest bit with detected >= "
                        "DETECT_RATE), shaded p10..p90 over the coefficients")
    p.add_argument("--show", action="store_true")
    return p.parse_args()


# ------------------------------------------------------------------ #
# Data
# ------------------------------------------------------------------ #
def level_logq(cfg):
    """logq of the ciphertext at the injection point: logQ minus logDelta per mult that
    ran before it (HEAAN). Stages that cannot be placed in the pipeline keep logQ."""
    ops = expand(cfg["pipeline"])
    pos = injection_index(ops, cfg["stage"], int(cfg["op_depth"]))
    if pos is None:
        return int(cfg["logQ"])
    n_mults = sum(o in MULTS for o in ops[:max(pos, 0)])
    return int(cfg["logQ"]) - int(cfg["logDelta"]) * n_mults

# backends/heaan.cpp: the boot starts with a modDown to logq_boot = logDelta + 10.
HEAAN_BOOT_EXTRA_BITS = 10


def boot_cutoff_bit(cfg):
    """First bit whose fault the HEAAN boot removes: after k mults (one rescale by
    logDelta each) the fault is a multiple of 2^(b - k*logDelta), and the modDown to
    q_boot = 2^(logDelta + 10) drops it once that exponent reaches logq_boot.
    NaN when there is no boot after the injection point."""
    ops = expand(cfg["pipeline"])
    pos = injection_index(ops, cfg["stage"], int(cfg["op_depth"]))
    after = ops[pos + 1:] if pos is not None and pos >= 0 else ops
    if pos is None or cfg["library"] != "heaan" or "boot" not in after:
        return np.nan
    k = sum(o in MULTS for o in after[:after.index("boot")])
    delta = int(cfg["logDelta"])
    return delta + HEAAN_BOOT_EXTRA_BITS + k * delta

def detector_onset(d):
    """Bit from which OpenFHE's SDC detector fires, one value per (limb, coeff) of `d`:
    the lowest bit whose detection rate over the repetitions is >= DETECT_RATE.
    Returns (onset bits, list of (limb, coeff) where it never fires)."""
    onset = d[d["detected"] >= DETECT_RATE].groupby(["limb", "coeff"])["bit"].min()
    never = sorted(set(d.groupby(["limb", "coeff"]).groups) - set(onset.index))
    return onset.to_numpy(dtype=float), never

def detector_bound(d, metric, never):
    """Largest `metric` a fault reached WITHOUT being detected, leaving out the cells
    where the detector never fires: above it the detector always fired. Uses <metric>_hi
    (max over the repetitions of each cell) when the collapse has it, so the bound holds
    for every single injection, not only for the per-cell means.
    Returns (bound or None if every fault was detected, column used)."""
    col = f"{metric}_hi" if f"{metric}_hi" in d.columns else metric
    blind = d.set_index(["limb", "coeff"]).index.isin(never)
    missed = d.loc[(d["detected"] < 1) & ~blind, col]
    return (float(missed.max()) if len(missed) else None), col

def load_curve_data(camps, results, vary, drop_coeffs, metric, stat="mean", rep_spread=False, raw_spread=False, detect_onset=False):
    """One row per (curve, limb, coeff, bit), seeds already averaged. Adds gap_aligned."""
    keys = [c for c in vary if c in camps.columns] # 'limb' comes from the data, not from the registry     
    groups = camps.groupby(keys) if keys else [((), camps)]
    parts = []


    for _, g in groups:
        cfg = require_single_config(g).iloc[0]           # within one curve only the seeds vary  
        N = 1 << int(cfg["logN"])
        gap = (N // 2) // (1 << int(cfg["logSlots"]))
        d = load_data(g, results)
        drop = {N // 2 if c == "N/2" else int(c) for c in drop_coeffs}
        d = d[~d["coeff"].isin(drop)]
        agg = {metric: "mean"}                              # mean over seeds
        if detect_onset:
            agg["detected"] = "mean"     # kept per cell: plot_curves() needs it for the onset
            if f"{metric}_hi" in d.columns:
                agg[f"{metric}_hi"] = "max"  # max over repetitions: detector_bound() needs it
        if raw_spread:
            lo, hi = f"{metric}_lo", f"{metric}_hi"
            if lo not in d.columns:
                sys.exit(f"--raw_spread needs {lo} / {hi} in the collapsed data: available for "
                         f"l2_rel and err_bits, after 'python3 collapse.py <dir> --force'")
            agg.update({lo: "min", hi: "max"})
        d = d.groupby(["limb", "coeff", "bit"], as_index=False).agg(agg)       
        if rep_spread:
            # One curve per repetition (mean over its coefficients), then min..max per bit.
            # Precomputed by the collapse, so --drop_coeffs and --stat do not apply to it.
            rep = (load_reps(g, results).groupby("bit")[metric]
                   .agg(rep_lo="min", rep_hi="max").reset_index())
            d = d.merge(rep, on="bit", how="left")
        for c in ["library", "logN", "logSlots", "logQ", "logDelta", "amountBits", "stage", "pipeline", *keys]:
            d[c] = cfg[c]
        d["gap"] = gap
        d["level"] = level_logq(cfg)
        d["boot_cut"] = boot_cutoff_bit(cfg)
        d["gap_aligned"] = (d["coeff"] % gap == 0)
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def x_values(bits, df, xnorm):
    if xnorm == "minus_delta":
        return bits - df["logDelta"].iloc[0]
    if xnorm == "over_q":
        return bits / df["logQ"].iloc[0]
    if xnorm == "minus_level":
        return bits - df["level"].iloc[0]
    if xnorm == "top_bit":
        return bits + int(df["amountBits"].iloc[0]) - 1
    return bits


# ------------------------------------------------------------------ #
# Plot
# ------------------------------------------------------------------ #
def plot_curves(ax, data, vary, args, subset_label="", yref=None, legend=True):
    """yref: frame the y scale and limits come from. With --split the panels share the y
    axis, so it has to be the FULL data: otherwise the last panel drawn resets the limits."""
    yref = data if yref is None else yref
    groups = list(data.groupby(vary)) if vary else [(None, data)]
    keys = getattr(args, "curve_keys", [k for k, _ in groups])
    # Draw in the order of keys (--order), so the legend lists the curves in that order.
    groups.sort(key=lambda kv: keys.index(kv[0]))
    if args.labels and len(args.labels) != len(keys):
        sys.exit(f"--labels has {len(args.labels)} entries but there are {len(keys)} curves: "
                 f"{vary} = {keys}")
    for val, d in groups:
        i = keys.index(val)          # position among ALL curves, not among this panel's
        # A non-finite value (a flip in a high bit can overflow the decode) makes the mean
        # of that bit inf, and matplotlib drops the point SILENTLY: the curve just stops
        # early and nothing says why. Average over the finite rows and mark those bits.
        finite = np.isfinite(d[args.metric].to_numpy(dtype=float))
        overflow_bits = np.unique(d.loc[~finite, "bit"].to_numpy())
        per_bit = d[finite].groupby("bit")[args.metric]
        y = per_bit.agg(STATS[args.stat])
        x = x_values(y.index.to_numpy(), d, args.xnorm)
        yv = y.to_numpy(dtype=float)
        color = COLORS[i % len(COLORS)]
        label = None
        if vary:
            vals = val if isinstance(val, tuple) else (val,)
            label = ", ".join(f"{k}={v}" for k, v in zip(vary, vals))
        if args.labels:
            label = args.labels[i]

        # First curve biggest and at the back, last one at SCATER_SIZE on top: when two
        # curves coincide, the bigger dot behind still shows as a ring.
        size = SCATER_SIZE + (len(keys) - 1 - i) * SIZE_STEP
        over = yv > args.ymax if args.ymax is not None else np.zeros(yv.size, dtype=bool)
        yv = np.where(over, np.nan, yv)            # off-scale points: triangles, below
        if args.lines:
            # NaN cuts the line, so it never runs up to an off-scale point.
            ax.plot(x, yv, color=color, lw=1.2, alpha=0.6, zorder=1 + i)
        ax.scatter(x, yv, s=size, color=color, label=label, zorder=2 + i)
        if over.any():
            ax.scatter(x[over], np.full(over.sum(), 0.985), s=size, marker="^",
                       facecolors="none", edgecolors=color, linewidths=1.2, clip_on=False,
                       transform=ax.get_xaxis_transform(), zorder=2 + i)
            print(f"  {label or 'curve'}: {over.sum()} bit(s) above --ymax {args.ymax:g}, "
                  f"max {np.nanmax(y.to_numpy(dtype=float)):.3g}")
        if args.boot_cutoff and np.isfinite(d["boot_cut"].iloc[0]):
            cut = float(x_values(np.array([d["boot_cut"].iloc[0]]), d, args.xnorm)[0])
            ax.axvline(cut, color=color, ls=":", lw=1.5, zorder=1)
        if args.detect_onset:
            onset, never = detector_onset(d)
            name = label or "curve"
            if onset.size == 0:
                print(f"  {name}: the SDC detector never fires, no onset line")
            else:
                if never:
                    print(f"  {name}: the detector never fires on {len(never)} (limb, coeff) "
                          f"cell(s), left out of the onset: {never[:6]}")
                xo = x_values(onset, d, args.xnorm)
                # Median, not mean: it is an actual bit position, and one coefficient the
                # detector misses until the top bits does not move it.
                bit = int(np.median(onset))
                # p10..p90, not +- std: one coefficient the detector misses until the top
                # bits would stretch a std band over the whole region.
                lo, hi = np.percentile(xo, [10, 90])

                ax.axvline(x_values(np.array([bit]), d, args.xnorm)[0], color=color, ls="-.",
                           lw=2, zorder=1, label=f"detector onset: bit {bit}")
                ax.axvspan(lo, hi, color=color, alpha=0.1, lw=0, zorder=0)
                print(f"  {name}: detector onset bit mean {onset.mean():.2f}, median "
                      f"{np.median(onset):g}, range {onset.min():g}..{onset.max():g}, "
                      f"over {onset.size} cell(s)")
                bound, col = detector_bound(d, args.metric, never)
                if bound is None:
                    print(f"  {name}: the detector fired on every fault")
                else:
                    print(f"  {name}: every undetected fault has {col} <= {bound:.3g} "
                          f"(never-detected cells left out): above it the detector always fires")
        if overflow_bits.size:
            ax.plot(x_values(overflow_bits, d, args.xnorm),
                    np.full(overflow_bits.size, 0.97), ls="none", marker="|", ms=9,
                    color=color, alpha=0.8, transform=ax.get_xaxis_transform(), zorder=4,
                    label=None if i else f"bits with non-finite {args.metric}")
            print(f"  {(~finite).sum()} non-finite {args.metric} rows on "
                  f"{overflow_bits.size} bit(s) {list(overflow_bits[:6])}: averaged over the "
                  f"rest, marked at the top (use --metric err_bits to keep them, clipped)")
        if args.band == "p10_90":
            lo, hi = per_bit.quantile(0.1).to_numpy(), per_bit.quantile(0.9).to_numpy()
            ax.fill_between(x, lo, hi, color=color, alpha=0.15, lw=0)
        elif args.band == "std":
            # std across coefficients; clipped at 0 because an error is never negative
            sd = per_bit.std().fillna(0).to_numpy()
            ax.fill_between(x, np.maximum(yv - sd, 0), yv + sd, color=color, alpha=0.2, lw=0,
                            label=None if i else r"$\pm 1$ std")
        if args.minmax:
            ax.plot(x, per_bit.min().to_numpy(), ls="none", marker="_", ms=8, color="red",
                    alpha=0.8, label=None if i else "min over coeffs")
            ax.plot(x, per_bit.max().to_numpy(), ls="none", marker="+", ms=8, color="green",
                    alpha=0.8, label=None if i else "max over coeffs")
        if args.rep_spread:
            band = d.groupby("bit")[["rep_lo", "rep_hi"]].first().reindex(y.index)
            ax.fill_between(x, band["rep_lo"], band["rep_hi"], color=color, alpha=0.2, lw=0,
                            label=None if i else "min-max over repetitions")
        if args.raw_spread:
            # min / max per bit over the coefficients of THIS curve and panel, and over
            # every repetition: each cell already carries its own min / max over seeds.
            band = (d.groupby("bit").agg(lo=(f"{args.metric}_lo", "min"),
                                         hi=(f"{args.metric}_hi", "max")).reindex(y.index))
            ax.fill_between(x, band["lo"], band["hi"], color=color, alpha=0.2, lw=0,
                            label=None if i else "min-max over coeffs and repetitions")
        # A reference line is drawn when it falls at the same x for every curve, in the plotted
    # units: with --xnorm over_q and logDelta = 0.75 logQ, logDelta sits at 0.75 and logQ at 1.
    for col, name in [("logDelta", r"$\log\Delta$"), ("logQ", r"$\log Q$")]:
        if args.no_refs:
            break
        if args.xnorm == "over_q":
            refs = data[col] / data["logQ"]
        elif args.xnorm == "minus_delta":
            refs = data[col] - data["logDelta"]
        elif args.xnorm == "minus_level":
            refs = data[col] - data["level"]
        else:
            refs = data[col]
        if refs.nunique() == 1:
            ref = float(refs.iloc[0])
            if args.xlim and not args.xlim[0] <= ref <= args.xlim[1]:
                continue          # out of range: the label would be drawn outside the axes
            ax.axvline(ref, color="black", ls="--", lw=1)
            ax.text(ref, 1.0, f" {name}", transform=ax.get_xaxis_transform(),
                    va="bottom", ha="center", fontsize=FONT - 4)
    # The top has to be set from the finite values: autoscaling with an inf in the frame
    # leaves the limit at inf and the whole figure collapses into one line.
    finite_vals = yref[args.metric].to_numpy(dtype=float)
    finite_vals = finite_vals[np.isfinite(finite_vals)]
    scale = args.yscale
    if scale == "auto":
        scale = "linear" if args.metric in RATE_METRICS else "symlog"
    if scale == "symlog":
        # symlog so a 0 (fully masked fault) is still visible.
        ax.set_yscale("symlog", linthresh=args.linthresh or _linthresh(finite_vals))
    else:
        ax.set_yscale(scale)
    if scale == "log":
        pos = finite_vals[finite_vals > 0]
        if pos.size:
            ax.set_ylim(float(pos.min()) / 3.0, float(pos.max()) * 3.0)
    elif args.metric in RATE_METRICS and scale == "linear":
        ax.set_ylim(-0.02, 1.02)
    elif args.ymax is not None:
        ax.set_ylim(0, args.ymax)
    else:
        top = float(finite_vals.max()) if finite_vals.size else 0.0
        if top > 0:            # all zeros: leave matplotlib's default instead of an empty range
            ax.set_ylim(0, top * 3.0 if np.isfinite(top * 3.0) else top)
    if args.xlim:
        ax.set_xlim(*args.xlim)
    xlabel = {"none": "Bit index", "minus_delta": r"Bit index $-\ \log\Delta$",
              "over_q": r"Bit index relative to $\log Q$","minus_level": r"Bit index $-\ \log q_\ell$", "top_bit": r"Top bit of the burst ($b + k - 1$)"}[args.xnorm]
    ax.set_xlabel(xlabel, fontsize=FONT)
    ax.tick_params(labelsize=TICK_FONT)
    ax.set_ylabel(args.ylabel or f"{args.stat} {args.metric} ({scale})", fontsize=FONT)
    ax.grid(True, ls="--", alpha=0.3)
    if subset_label:
        ax.set_title(subset_label, fontsize=FONT, pad=26)
    if legend and (vary or args.labels or args.band == "std" or args.minmax or args.rep_spread or args.raw_spread or args.detect_onset):
        ax.legend(fontsize=FONT - 6, frameon=False)

def _linthresh(values):
    """symlog is linear only near 0: below the smallest non-zero error."""
    pos = values[values > 0]
    return float(10 ** np.floor(np.log10(pos.min()))) if len(pos) else 1e-12

def save_figure(fig, name, args):
    if args.suptitle:
        fig.suptitle(args.suptitle, fontsize=FONT - 2, y=1.02)
    IMG_DIR.mkdir(exist_ok=True)
    # f-string, not with_suffix(): a name with a dot (e.g. '..._logDelta_0.5_aligned')
    # would lose everything after the dot and the two --split files would overwrite each other.
    out = IMG_DIR / name
    fig.savefig(f"{out}.pdf", bbox_inches="tight")
    fig.savefig(f"{out}.png", bbox_inches="tight", dpi=120)
    print(f"-> {out}.png")
    if args.show:
        plt.show()
    plt.close(fig)


def make_figure(data, vary, args, name):
    """--split none: one file <name>. --split gap: <name>_aligned (coefficients the decode
    reads, coeff % gap == 0) and <name>_other (the rest), each in its own file."""
    # Curve identity comes from the FULL data, so a curve missing from one file (e.g. no
    # non-aligned coefficients when gap=1) keeps its color, size and label in the other.
    args.curve_keys = [k for k, _ in data.groupby(vary)] if vary else [None]
    if args.order:
        # --order gives the values as text; map them onto the groupby keys (with one
        # --vary column these can be scalars or 1-tuples, depending on pandas).
        by_name = {str(k[0] if isinstance(k, tuple) else k): k for k in args.curve_keys}
        missing = [v for v in args.order if v not in by_name]
        if len(vary) != 1 or missing or len(args.order) != len(by_name):
            sys.exit(f"--order needs exactly one --vary column and all its values once: "
                     f"got {args.order}, the curves are {list(by_name)}")
        args.curve_keys = [by_name[v] for v in args.order]
    if args.split == "none":
        fig, ax = plt.subplots(figsize=FIGSIZE)
        plot_curves(ax, data, vary, args)
        save_figure(fig, name, args)
        return
    parts = {"aligned": data[data["gap_aligned"]], "other": data[~data["gap_aligned"]]}
    for suffix, part in parts.items():
        if part.empty:
            print(f"  {name}_{suffix}: no coefficients in this subset (gap = 1), not saved")
            continue
        fig, ax = plt.subplots(figsize=SPLIT_FIGSIZE)
        # yref=data: both files get the same y scale and limits, computed from ALL the data
        plot_curves(ax, part, vary, args, yref=data, legend=(suffix == "aligned"))
        if suffix == "other":
            # Same y axis and colors as _aligned: the y label, the tick labels and the
            # legend are drawn only there. The ticks and the grid stay.
            ax.set_ylabel("")
            ax.tick_params(axis="y", labelleft=False)
        save_figure(fig, f"{name}_{suffix}", args)


def select_campaigns(args):
    """Finished campaigns matching --where (fixed values) and --query (any pandas expression)."""
    filters = {k: parse_value(v) for k, v in (w.split("=", 1) for w in args.where)}
    camps = select(load_campaigns(args.results), **filters)
    if args.query:
        camps = camps.query(args.query)
    if camps.empty:
        sys.exit(f"No finished campaigns match --where {args.where} --query {args.query!r}")
    return camps

def main():
    args = parse_args()
    camps = select_campaigns(args)
    per_values = sorted(camps[args.per].unique()) if args.per else [None]
    for pv in per_values:
        sub = camps if pv is None else camps[camps[args.per] == pv]
        try:
            data = load_curve_data(sub, args.results, args.vary, args.drop_coeffs,
                args.metric, stat=args.stat, rep_spread=args.rep_spread, raw_spread=args.raw_spread, detect_onset=args.detect_onset)
        except ValueError as e:
            sys.exit(f"ERROR: {e}\n  -> add a filter with --where, or use --vary/--per for that columns")
        name = args.title if pv is None else f"{args.title}_{args.per}_{pv}"
        make_figure(data, args.vary, args, name)


if __name__ == "__main__":
    main()
