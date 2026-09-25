#!/usr/bin/env python3
"""NN workloads: probability that a bit flip changes the predicted class, per bit.

`misclassified` is 0/1 per injection (class of the faulty run != class of the fault-free
CKKS run), so its mean over every sample of a bit is a probability. All samples of a bit
are pooled: every coefficient, limb, seed and image of the same config.

One panel per stage, in the --stages order. Default: the client-side registers, top row
before sending to the server, bottom row after receiving from it.

  --mode rate    P(SDC) per bit with its 95% Wilson interval (default)
  --mode stack   stacked fractions per bit: masked / tolerable SDC / critical SDC

Each panel title carries P(SDC | random bit of the register): the per-bit curve
interpolated over every bit in [0, logQ) and averaged. The sampled bits of a random
campaign are not uniform (dense near logDelta and logQ), so the plain mean of the
samples would be biased; the interpolated mean is not.

Examples:
  python3 nn_sdc_curve.py --title nn_client --where library=heaanNN
  python3 nn_sdc_curve.py --title nn_client_stack --where library=heaanNN --mode stack
  python3 nn_sdc_curve.py --title nn_enc --where library=heaanNN --stages encrypt_c0 encrypt_c1 --ncols 2
"""
import argparse
import sys
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
import register_map as rm                                              # noqa: E402
from utils.results import (load_campaigns, load_data, select, require_single_config,  # noqa: E402
                           assign_config_id, parse_value)

CLIENT_STAGES = ["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"]
RATE_CMAP = mcolors.LinearSegmentedColormap.from_list("rate", [rm.GREEN, rm.YELLOW, rm.RED])
# gamma < 1 so that a small but non-zero rate is already visibly yellow, not green.
RATE_NORM = mcolors.PowerNorm(gamma=0.5, vmin=0.0, vmax=1.0)
BAND_COLOR = "#6BAED6"
Z95 = 1.959964
FONT = 16


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default="../results_NN")
    p.add_argument("--where", nargs="+", default=[], metavar="COL=VAL")
    p.add_argument("--stages", nargs="+", default=CLIENT_STAGES,
                   help="one panel per stage, in this order (missing stages are skipped)")
    p.add_argument("--ncols", type=int, default=3)
    p.add_argument("--mode", choices=["rate", "stack"], default="rate")
    p.add_argument("--title", default="nn_sdc")
    p.add_argument("--show", action="store_true")
    return p.parse_args()


# ------------------------------------------------------------------ #
# Data
# ------------------------------------------------------------------ #
def load_stages(args):
    """{stage: (cfg, data)} for the stages that have finished campaigns."""
    filters = {k: parse_value(v) for k, v in (w.split("=", 1) for w in args.where)}
    if "stage" in filters:
        sys.exit("ERROR: remove stage from --where; use --stages")
    camps = select(load_campaigns(args.results), **filters)
    camps = camps[camps["stage"].isin(args.stages)]
    if camps.empty:
        sys.exit(f"ERROR: no finished campaigns for stages {args.stages} and {filters}")

    # Every panel must be the same config except for the stage.
    together = camps.copy()
    together["stage"] = "*"
    try:
        require_single_config(assign_config_id(together))
    except ValueError as exc:
        sys.exit(f"ERROR: the stages differ in more than the stage: {exc}. Add them to --where.")

    missing = [s for s in args.stages if s not in set(camps["stage"])]
    if missing:
        print(f"  no campaigns for {missing}: skipped")
    out = {}
    for stage in [s for s in args.stages if s not in missing]:
        group = camps[camps["stage"] == stage]
        out[stage] = (group.iloc[0], load_data(group, args.results))
    return out


def wilson(k, n, z=Z95):
    """95% Wilson interval of a proportion. Unlike p +- std it stays inside [0, 1] and
    does not collapse to zero width when every sample is 0 or 1."""
    p = k / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return center - half, center + half

def per_bit(data):
    """One row per bit: n, P(SDC), its interval, and the three-way split.

    Each row of a collapsed dir is one (limb, coeff, bit) cell with n_seeds injections, and
    misclassified / tolerable_sdc are the fraction of them that hit, so rate x n_seeds
    gives back the exact counts.
    """
    w = data["n_seeds"] if "n_seeds" in data.columns else pd.Series(1.0, index=data.index)
    d = pd.DataFrame({"bit": data["bit"], "n": w,
                      "k": data["misclassified"] * w, "k_tol": data["tolerable_sdc"] * w})
    out = d.groupby("bit")[["n", "k", "k_tol"]].sum()
    out["rate"] = out["k"] / out["n"]
    out["lo"], out["hi"] = wilson(out["k"].to_numpy(float), out["n"].to_numpy(float))
    out["tolerable"] = out["k_tol"] / out["n"]
    out["masked"] = 1.0 - out["rate"] - out["tolerable"]
    return out.reset_index()

def register_width(cfg):
    """Bits the fault can land in. HEAAN's encode register is logDelta bits wider than a
    ciphertext: it is scaled by 2^(logDelta + logQ) before encryptMsg shifts it by logQ."""
    heaan_encode = str(cfg["library"]).startswith("heaan") and cfg["stage"] == "encode"
    return int(cfg["logQ"]) + (int(cfg["logDelta"]) if heaan_encode else 0)

def register_rate(curve, log_q):
    """P(SDC) for a bit drawn uniformly from [0, logQ): interpolate the sampled bits."""
    bits = np.arange(int(log_q))
    return float(np.interp(bits, curve["bit"], curve["rate"]).mean())


# ------------------------------------------------------------------ #
# Plot
# ------------------------------------------------------------------ #
def mark_params(ax, cfg):
    for val, name in [(cfg["logDelta"], r"$\log\Delta$"), (cfg["logQ"], r"$\log Q$")]:
        ax.axvline(val, color="black", lw=0.8, ls="--", alpha=0.7, zorder=4)
        ax.text(val, 1.02, name, transform=ax.get_xaxis_transform(),
                ha="center", va="bottom", fontsize=FONT - 5)


def draw_rate(ax, curve):
    x = curve["bit"].to_numpy()
    ax.fill_between(x, curve["lo"], curve["hi"], color=BAND_COLOR, alpha=0.45, lw=0, zorder=2)
    ax.scatter(x, curve["rate"], c=curve["rate"].to_numpy(), cmap=RATE_CMAP, norm=RATE_NORM,
               s=28, edgecolors="black", linewidths=0.3, zorder=3)
    ax.set_ylim(-0.05, 1.05)
    ax.set_yticks([0, 0.5, 1])
    ax.set_yticklabels(["Mask", "0.5", "SDC"])


def draw_stack(ax, curve):
    x = curve["bit"].to_numpy()
    ax.stackplot(x, curve["masked"], curve["tolerable"], curve["rate"],
                 colors=[rm.GREEN, rm.YELLOW, rm.RED], alpha=0.9, zorder=2,
                 labels=["Masked", "Tolerable SDC", "Critical SDC"])
    ax.set_ylim(0, 1)
    ax.set_yticks([0, 0.5, 1])


def plot(stages, args):
    n = len(stages)
    ncols = min(args.ncols, n)
    nrows = -(-n // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 3.4 * nrows),
                             sharex=True, sharey=True, squeeze=False)
    n_min = {}      # fewest injections behind any bit of each panel
    for ax, (stage, (cfg, data)) in zip(axes.flat, stages.items()):
        curve = per_bit(data)
        n_min[stage] = int(curve["n"].min())
        (draw_rate if args.mode == "rate" else draw_stack)(ax, curve)
        mark_params(ax, cfg)
        ax.set_title(stage, fontsize=FONT - 3, pad=20)
        ax.grid(alpha=0.3)
        ax.tick_params(labelsize=FONT - 5)
    for ax in axes.flat[n:]:
        ax.set_visible(False)
    for ax in axes[-1]:
        ax.set_xlabel("Bit index", fontsize=FONT - 2)
    for ax in axes[:, 0]:
        ax.set_ylabel("SDC rate" if args.mode == "rate" else "Fraction", fontsize=FONT - 2)
    if args.mode == "rate":
        # Proxies: the scatter is colored point by point, its own handle would be green.
        handles = [Line2D([], [], ls="none", marker="o", mfc=rm.RED, mec="black", mew=0.3,
                          label="P(SDC) per bit"),
                   Patch(facecolor=BAND_COLOR, alpha=0.45, label="95% Wilson CI")]
    else:
        handles, _ = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles=handles, loc="upper center", ncol=len(handles), frameon=False,
               fontsize=FONT - 4, bbox_to_anchor=(0.5, 1.05))
    fig.tight_layout()
    return fig, n_min


def main():
    args = parse_args()
    stages = load_stages(args)
    fig, n_min = plot(stages, args)

    print(f"  {'stage':12s} {'min n/bit':>10s}")
    for stage, n in n_min.items():
        print(f"  {stage:12s} {n:10d}")

    rm.IMG_DIR.mkdir(parents=True, exist_ok=True)
    out = rm.IMG_DIR / args.title
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=150)
    print(f"-> {out}.png / .pdf")
    if args.show:
        plt.show()
    plt.close(fig)


if __name__ == "__main__":
    main()
