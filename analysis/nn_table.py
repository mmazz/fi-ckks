#!/usr/bin/env python3
"""NN workloads: per-stage summary table of misclassification (client stages).

One row per stage, computed from the same per-bit curves as nn_sdc_curve.py:

  w           width of the register at the injection point (nn_sdc_curve.register_width)
  window      first and last sampled bit with P(misclassification) > 0
  plateau     the window minus its transitions. Rule: starting from each end of the
              window, drop a sampled bit while the upper bound of its 95% Wilson interval
              is below the median P of the window; stop at the first bit that is not.
  plateau P   mean and range of P over the plateau bits. The range is rounded outwards
              (min down, max up), so it contains every value.
  P_mis       P(misclassification) for a bit drawn uniformly from [0, w), interpolating
              the per-bit curve (nn_sdc_curve.register_rate). HEAAN encode also gets it
              over the upper logQ bits, the ones that survive the division by Q.

Prints a readable table and the LaTeX rows of the paper table (\\stg{} macro).

Examples:
  python3 nn_table.py --results ../results_NN --where library=heaanNN
  python3 nn_table.py --results ../data_v6/nn --where library=heaanNN
"""
import argparse
import math
import sys
from pathlib import Path

import numpy as np

sys.path.append(str(Path(__file__).resolve().parent))
import nn_sdc_curve as nsc                                             # noqa: E402

# Stage number of the client pipeline (Fig. 4 of the DSN paper) and register name.
STAGE_ROW = {"encode": (1, "encoded image"), "encrypt_c0": (3, r"$c_0$, fresh"),
             "encrypt_c1": (4, r"$c_1$, fresh"), "decrypt_c0": (7, r"$c_0$, logit"),
             "decrypt_c1": (8, r"$c_1$, logit"), "decode": (9, "decrypted logit")}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default="../results_NN")
    p.add_argument("--where", nargs="+", default=["library=heaanNN"], metavar="COL=VAL")
    p.add_argument("--stages", nargs="+", default=nsc.CLIENT_STAGES)
    return p.parse_args()


def window(curve):
    """Sampled bits from the first to the last one with P > 0 (inclusive)."""
    hit = curve.index[curve["rate"] > 0]
    if len(hit) == 0:
        return curve.iloc[0:0]
    return curve.loc[hit[0]:hit[-1]]


def plateau(win):
    """Drop transition bits at both ends: a bit is a transition while its Wilson upper
    bound is below the median P of the window."""
    med = win["rate"].median()
    lo, hi = 0, len(win)
    while lo < hi and win["hi"].iloc[lo] < med:
        lo += 1
    while hi > lo and win["hi"].iloc[hi - 1] < med:
        hi -= 1
    return win.iloc[lo:hi]


def floor2(x):
    return math.floor(x * 100) / 100


def ceil2(x):
    return math.ceil(x * 100) / 100


def summarize(stage, cfg, data):
    curve = nsc.per_bit(data).set_index("bit").sort_index()
    w = nsc.register_width(cfg)
    win = window(curve)
    pla = plateau(win)
    row = {"stage": stage, "w": w, "n_min": int(curve["n"].min()),
           "p_mis": nsc.register_rate(curve.reset_index(), w)}
    if len(win):
        row["window"] = (int(win.index[0]), int(win.index[-1]))
    if len(pla):
        row["plateau"] = (int(pla.index[0]), int(pla.index[-1]))
        row["plateau_mean"] = float(pla["rate"].mean())
        row["plateau_min"] = float(pla["rate"].min())
        row["plateau_max"] = float(pla["rate"].max())
    shift = nsc.encode_shift(cfg)
    if shift:
        # HEAAN encode: P over the upper logQ bits only, [logQ, 2*logQ).
        bits = np.arange(shift, w)
        row["p_mis_upper"] = float(np.interp(bits, curve.index.to_numpy(),
                                             curve["rate"].to_numpy()).mean())
    return row


def span(pair):
    return f"{pair[0]}--{pair[1]}" if pair else "--"


def main():
    args = parse_args()
    if not hasattr(nsc, "OUTPUT_STAGES"):
        sys.exit("ERROR: nn_sdc_curve.py still uses logQ as the width of the output "
                 "registers. Apply the register_width change first (OUTPUT_STAGES, NN_LEVELS).")
    stages = nsc.load_stages(args)
    rows = [summarize(stage, cfg, data) for stage, (cfg, data) in stages.items()]

    print(f"\n  {'stage':11s} {'w':>4s} {'n/bit':>6s} {'window':>10s} {'plateau':>10s} "
          f"{'mean':>6s} {'min':>6s} {'max':>6s} {'P_mis':>6s}")
    for r in rows:
        mean = f"{r['plateau_mean']:.3f}" if "plateau_mean" in r else "-"
        pmin = f"{r['plateau_min']:.3f}" if "plateau_min" in r else "-"
        pmax = f"{r['plateau_max']:.3f}" if "plateau_max" in r else "-"
        extra = f"  (upper half: {r['p_mis_upper']:.3f})" if "p_mis_upper" in r else ""
        print(f"  {r['stage']:11s} {r['w']:4d} {r['n_min']:6d} "
              f"{span(r.get('window')):>10s} {span(r.get('plateau')):>10s} "
              f"{mean:>6s} {pmin:>6s} {pmax:>6s} {r['p_mis']:6.3f}{extra}")

    print("\n  LaTeX rows (Table nn):")
    for r in rows:
        num, name = STAGE_ROW.get(r["stage"], ("?", r["stage"]))
        if "plateau_mean" in r:
            pla_p = (f"{r['plateau_mean']:.2f} "
                     f"({floor2(r['plateau_min']):.2f}--{ceil2(r['plateau_max']):.2f})")
        else:
            pla_p = "--"
        print(f"\\stg{{{num}}} & {name} & {r['w']} & {span(r.get('window'))} & "
              f"{span(r.get('plateau'))} & {pla_p} & {r['p_mis']:.2f} \\\\")
    for r in rows:
        if "p_mis_upper" in r:
            print(f"  {r['stage']}: P_mis over the upper half of the register = "
                  f"{r['p_mis_upper']:.2f} (table caption)")


if __name__ == "__main__":
    main()
