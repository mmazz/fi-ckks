#!/usr/bin/env python3
"""NN workloads: vulnerable bits per coefficient at every injection site, in the order the
sites run in the network.

Vulnerable bits of a site = expected number of bits of one coefficient whose flip changes
the predicted class = sum over the bits b of [0, bitsPerCoeff) of P(mis | b), with P(mis | b)
interpolated between the sampled bits (random campaigns do not sample every bit). It is
the width of the vulnerable band times its plateau, so it shrinks when the network spends
a level (the register gets logDelta bits narrower) and grows in the key-switching
registers (mod qQ, up to 2 logQ bits). Computed separately for the coefficients aligned
to the gap and the other ones (nn_sdc_curve.py --split gap).

The order is the one of the HEAAN workload (workloads/nn/heaan_nn.cpp). Sites without
campaigns are skipped, so a partial results dir still plots.

Example:
  python3 nn_profile.py --results ../results_NN --title nn_profile --where library=heaanNN
"""
import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
import nn_sdc_curve as nsc                                             # noqa: E402

# (stage, op_steps, block) in execution order. The rotations of reduceSum run between
# hidden_layer 4/5 (the copy to rotate) and 6/7 (the rotated one); the mul z^2 * z and its
# rescale between cheby_tanh3 2/3 (operands) and 4/5 (z^3).
EXECUTION_ORDER = [
    ("encode", [0], "client"), ("encrypt_c0", [0], "client"), ("encrypt_c1", [0], "client"),
    ("hidden_layer", range(0, 6), "hidden layer"),
    ("rot", range(12), "rotation"),
    ("hidden_layer", range(6, 14), "hidden layer"),
    ("cheby_tanh3", range(0, 4), "activation"),
    ("mul", range(26), r"mul $z^2 \cdot z$"),
    ("rescale", range(4), "rescale"),
    ("cheby_tanh3", range(4, 10), "activation"),
    ("add", range(6), "add"),
    ("decrypt_c0", [0], "output"), ("decrypt_c1", [0], "output"), ("decode", [0], "output"),
]
SHADE = "#f1f0ec"
FONT = nsc.FONT


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default="../results_NN")
    p.add_argument("--where", nargs="+", default=[], metavar="COL=VAL")
    p.add_argument("--title", default="nn_profile")
    p.add_argument("--show", action="store_true")
    args = p.parse_args()
    # load_steps reads the stages to load from args.stages
    args.stages = list(dict.fromkeys(stage for stage, _, _ in EXECUTION_ORDER))
    return args


def vulnerable_bits(curve, width):
    """Sum over [0, width) of P(mis | bit), interpolated between the sampled bits."""
    return float(np.interp(np.arange(width), curve["bit"], curve["rate"]).sum())


def profile(steps):
    """One row per site present in the data, in EXECUTION_ORDER."""
    by_key = {key: (cfg, data) for key, cfg, data in steps}
    rows = []
    for stage, op_steps, block in EXECUTION_ORDER:
        for step in op_steps:
            if (stage, step) not in by_key:
                continue
            cfg, data = by_key[(stage, step)]
            width = int(cfg["bitsPerCoeff"])
            row = {"stage": stage, "op_step": step, "block": block, "width": width}
            for group, sub in nsc.split_gap(data, cfg).items():
                row[group] = vulnerable_bits(nsc.per_bit(sub), width)
            rows.append(row)
    return pd.DataFrame(rows)


def plot(prof):
    fig, ax = plt.subplots(figsize=(14, 4.6))
    x = np.arange(len(prof))
    # one shaded / plain span per run of consecutive sites of the same block, labeled on top
    run = (prof["block"] != prof["block"].shift()).cumsum()
    for k, (_, g) in enumerate(prof.groupby(run, sort=False)):
        lo, hi = g.index.min() - 0.5, g.index.max() + 0.5
        if k % 2 == 0:
            ax.axvspan(lo, hi, color=SHADE, lw=0, zorder=0)
        ax.text((lo + hi) / 2, 1.01, g["block"].iloc[0], transform=ax.get_xaxis_transform(),
                ha="left", va="bottom", rotation=30, rotation_mode="anchor", fontsize=FONT - 5)
    ax.vlines(x, prof[["aligned", "other"]].min(axis=1), prof[["aligned", "other"]].max(axis=1),
              color="#c9c8c2", lw=1, zorder=1)
    for group in ("aligned", "other"):
        ax.scatter(x, prof[group], s=34, color=nsc.GROUP_COLOR[group],
                   marker=nsc.GROUP_MARKER[group], edgecolor="white", lw=0.6, zorder=3,
                   label=nsc.GROUP_LABEL[group])
    ax.set_xticks([])
    ax.set_xlim(-0.8, len(prof) - 0.2)
    ax.set_ylim(0, None)
    ax.set_ylabel("Vulnerable bits\nper coefficient", fontsize=FONT - 2)
    ax.set_xlabel("Injection site, in execution order", fontsize=FONT - 2)
    ax.tick_params(labelsize=FONT - 5)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(loc="upper right", frameon=False, fontsize=FONT - 4)
    fig.tight_layout()
    return fig


def main():
    args = parse_args()
    prof = profile(nsc.load_steps(args))
    fig = plot(prof)

    pd.set_option("display.width", 200)
    print(prof.round(1).to_string(index=False))
    print("\n  per block (min - max):")
    print(prof.groupby("block", sort=False)[["aligned", "other"]].agg(["min", "max"]).round(0)
              .to_string())

    nsc.rm.IMG_DIR.mkdir(parents=True, exist_ok=True)
    out = nsc.rm.IMG_DIR / args.title
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=150)
    print(f"-> {out}.png / .pdf")
    if args.show:
        plt.show()
    plt.close(fig)


if __name__ == "__main__":
    main()
