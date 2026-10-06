#!/usr/bin/env python3
"""Does a fault break every output slot, or a few slots while the rest stay fine?

Every injection is classified on its own (before the seeds are averaged) against a
threshold on the per-slot relative error (--threshold 1 or 10 %):

  none   no slot above the threshold
  some   at least one slot above it, but not all of them
  all    every slot above it

One panel per group (--vary), x = flipped bit, y = stacked fraction of the injections
in each class. A thin "some" band means the slots break together. The table gives, per
panel, how the VISIBLE faults (some + all) split, and the crest factor of the absolute
error: max / rms over the slots, ~1.4 when every slot gets the same error, sqrt(n_slots)
when it all sits in one slot.

Examples:
  python3 slot_share.py --results ../results_client --title share_enc \\
      --where library=heaan logN=6 logSlots=5 logQ=60 logDelta=40 bitsPerCoeff=64 pipeline= \\
      --query 'stage in ["encrypt_c0", "encrypt_c1"]' --vary stage
  python3 slot_share.py --results ../results_client --title share_mul --threshold 10 \\
      --where library=heaan logN=6 logSlots=3 logQ=150 logDelta=30 bitsPerCoeff=170 \\
      --query 'pipeline in ["mul", "mul x3"]' --vary stage pipeline --gap aligned
"""
import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

sys.path.append(str(Path(__file__).resolve().parent))
import bit_curve as bc                                     # noqa: E402
import register_map as rm                                  # noqa: E402
from utils.results import load_data                        # noqa: E402

FONT = 16


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default="../results")
    p.add_argument("--where", nargs="+", default=[], metavar="COL=VAL")
    p.add_argument("--query", default=None, help="extra pandas filter over the campaigns")
    p.add_argument("--vary", nargs="*", default=[], help="one panel per value of these columns")
    p.add_argument("--threshold", type=int, choices=[1, 10], default=1,
                   help="per-slot relative error, in %%")
    p.add_argument("--gap", choices=["all", "aligned", "other"], default="all",
                   help="only the coefficients with coeff %% gap == 0 (aligned) or the rest")
    p.add_argument("--ncols", type=int, default=2)
    p.add_argument("--title", default="slot_share")
    p.add_argument("--show", action="store_true")
    return p.parse_args()


def load(args):
    """Cells of the selected experiments with 'panel', 'w' (injections per cell) and the
    three class probabilities none / some / all."""
    camps = bc.select_campaigns(args)
    data = load_data(camps, args.results)
    some, every = f"some_over{args.threshold}", f"all_over{args.threshold}"
    if some not in data.columns:
        sys.exit(f"ERROR: no {some} column. Rebuild the collapsed data: "
                 "python3 collapse.py <raw results dir> --force")
    cols = list(dict.fromkeys(["logN", "logSlots", "logQ", "logDelta"] + args.vary))
    data = data.merge(camps[["config_id"] + cols].drop_duplicates("config_id"), on="config_id")
    gap = 2 ** (data["logN"].astype(int) - 1 - data["logSlots"].astype(int))   # (N/2) / slots
    if args.gap != "all":
        data = data[(data["coeff"] % gap == 0) == (args.gap == "aligned")]
    if data.empty:
        sys.exit(f"ERROR: nothing left after --gap {args.gap}")
    data["w"] = data["n_seeds"] if "n_seeds" in data.columns else 1.0
    data["some"] = data[some]
    data["all"] = data[every]
    data["none"] = 1.0 - data["some"] - data["all"]
    data["panel"] = "all"
    for i, k in enumerate(args.vary):
        part = f"{k}=" + data[k].astype(str)
        data["panel"] = part if i == 0 else data["panel"] + ", " + part
    return data


def per_bit(d):
    """Mean of each class over coefficients and seeds, weighted by injections."""
    cls = ["none", "some", "all"]
    w = d[cls].mul(d["w"], axis=0).assign(bit=d["bit"], w=d["w"]).groupby("bit").sum()
    return w[cls].div(w["w"], axis=0)


def summary(data):
    rows = []
    for panel, d in data.groupby("panel"):
        n = d["w"].sum()
        n_some, n_all = (d["some"] * d["w"]).sum(), (d["all"] * d["w"]).sum()
        visible = n_some + n_all
        crest = d["crest"].dropna()
        rows.append({"panel": panel,
                     "pct_visible": 100 * visible / n,
                     "pct_all_of_visible": 100 * n_all / visible if visible else np.nan,
                     "pct_some_of_visible": 100 * n_some / visible if visible else np.nan,
                     "crest_median": crest.median() if len(crest) else np.nan,
                     "sqrt_n_slots": float((2.0 ** (d["logSlots"].astype(int) / 2)).median()),
                     "n_inj": int(n)})
    return pd.DataFrame(rows).set_index("panel")


def plot(data, args):
    panels = sorted(data["panel"].unique())
    ncols = min(args.ncols, len(panels))
    nrows = -(-len(panels) // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(5.5 * ncols, 3.4 * nrows),
                             sharey=True, squeeze=False)
    colors = [rm.GREEN, rm.YELLOW, rm.RED]
    t = args.threshold
    labels = [f"No slot > {t}%", f"Some slots > {t}%", f"Every slot > {t}%"]
    for ax, panel in zip(axes.flat, panels):
        d = data[data["panel"] == panel]
        f = per_bit(d)
        ax.stackplot(f.index, f["none"], f["some"], f["all"], colors=colors, alpha=0.9,
                     edgecolor="white", linewidth=0.5)
        for col, name in [("logDelta", r"$\log\Delta$"), ("logQ", r"$\log Q$")]:
            if d[col].nunique() == 1:
                v = float(d[col].iloc[0])
                ax.axvline(v, color="black", ls="--", lw=0.8)
                ax.text(v, 1.02, name, transform=ax.get_xaxis_transform(), ha="center",
                        va="bottom", fontsize=FONT - 5)
        ax.set_title(panel, fontsize=FONT - 4, pad=18)
        ax.set_xlim(f.index.min(), f.index.max())
        ax.set_ylim(0, 1)
        ax.tick_params(labelsize=FONT - 5)
    for ax in axes.flat[len(panels):]:
        ax.set_visible(False)
    for ax in axes[-1]:
        ax.set_xlabel("Bit index", fontsize=FONT - 2)
    for ax in axes[:, 0]:
        ax.set_ylabel("Fraction of injections", fontsize=FONT - 2)
    handles = [Patch(facecolor=c, label=lab) for c, lab in zip(colors, labels)]
    fig.legend(handles=handles, loc="upper center", ncol=3, frameon=False,
               fontsize=FONT - 4, bbox_to_anchor=(0.5, 1.07))
    fig.tight_layout()
    return fig


def main():
    args = parse_args()
    data = load(args)
    table = summary(data)
    with pd.option_context("display.width", 200, "display.float_format", "{:.2f}".format):
        print(table.to_string())
    fig = plot(data, args)
    bc.IMG_DIR.mkdir(exist_ok=True)
    out = bc.IMG_DIR / args.title
    table.to_csv(out.with_name(f"{args.title}_summary.csv"), float_format="%.3g")
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=130)
    print(f"-> {out}.png")
    if args.show:
        plt.show()
    plt.close(fig)


if __name__ == "__main__":
    main()
