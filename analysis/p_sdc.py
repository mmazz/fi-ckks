#!/usr/bin/env python3
"""P(SDC) of one experiment, and nothing else.

P(SDC) is the probability that a fault produces an SDC when the coefficient is drawn
uniformly among all of them and the bit uniformly among the W bits of the module at the
injection point (thesis, section "Bits del modulo y probabilidad de SDC"):

  1. Per bit: the fraction of the injections at that bit that are an SDC, pooling every
     coefficient, limb and repetition (cells of a collapsed dir weighted by n_seeds).
  2. That curve is interpolated linearly at every integer bit of [0, W) and averaged.
     In an exhaustive campaign this is the plain mean over the bits; in a random one it
     keeps the densely sampled bits from weighing more.

Criterion: is_sdc (some slot > 10 %), or misclassified (change of class) for the NN
workloads. --metric picks another 0/1 column.

W, the width of the module at the injection point:
  OpenFHE           log q_0 (logQ) for every limb: with several limbs any change in a
                    residue destroys the output, so the width does not change P
  HEAAN encode      log Q_l + log P = 2 logQ
  HEAAN NN client   nn_sdc_curve.register_width (logits: logQ - 5 logDelta)
  HEAAN otherwise   thesis_numbers.module_width: log Q_l of the level, minus logDelta after
                    the shift of a rescale, plus log P in the key-switching steps
  NN internal stages and steps inside the boot do not carry W in their config: pass --width.

Every experiment that matches --where / --exp gets one block of output.

Examples:
  python3 p_sdc.py --results ../results_client --where library=heaan stage=encrypt_c0 \\
      "pipeline=add; rot 3" logSlots=3
  python3 p_sdc.py --results ../results_server --exp 365f3144
  python3 p_sdc.py --results ../results_NN --where library=heaanNN stage=decrypt_c0
  python3 p_sdc.py --results ../results_NN --where library=heaanNN stage=mul op_step=13 \\
      --width 444
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
import nn_sdc_curve as nsc                                             # noqa: E402
import thesis_numbers as tn                                            # noqa: E402
from utils.results import load_campaigns, load_data, select, parse_value  # noqa: E402

NN_CLIENT = set(nsc.CLIENT_STAGES)
BOOT_STAGES = {"boot", "boot_eval"}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", required=True, help="results dir (raw or collapsed)")
    p.add_argument("--where", nargs="+", default=[], metavar="COL=VAL")
    p.add_argument("--exp", help="experiment_id, or its first characters")
    p.add_argument("--metric", help="0/1 column (default: is_sdc; misclassified for the NN)")
    p.add_argument("--width", type=int, help="W, instead of the one read from the config")
    args = p.parse_args()
    if not args.where and not args.exp:
        p.error("choose the experiment with --where and/or --exp")
    return args


def find_experiments(args):
    """Rows of the campaign index that match --exp and --where."""
    camps = load_campaigns(args.results)
    if args.exp:
        camps = camps[camps["experiment_id"].astype(str).str.startswith(args.exp)]
    filters = {k: parse_value(v) for k, v in (w.split("=", 1) for w in args.where)}
    camps = select(camps, **filters)
    if camps.empty:
        sys.exit(f"ERROR: no experiment matches --exp {args.exp} --where {args.where}")
    return camps.sort_values(["library", "stage", "op_depth", "op_step"])


def module_width(e, override):
    """(W, where it comes from). W is None when the config does not say it."""
    if override:
        return override, "--width"
    lib, stage = str(e["library"]), e["stage"]
    if lib.startswith("openfhe"):
        return int(e["logQ"]), "log q_0, the same for every limb"
    if lib == "heaanNN":
        if stage in NN_CLIENT:
            return nsc.register_width(e), "nn_sdc_curve.register_width"
        return None, "NN internal stage: its level depends on the op_step"
    if stage in BOOT_STAGES:
        return None, "inside the boot: the module of each step is not logged"
    if stage == "encode":
        return 2 * int(e["logQ"]), "log Q_l + log P (HEAAN encode)"
    width, capped = tn.module_width(e)
    return width, "thesis_numbers.module_width" + (", capped at bitsPerCoeff" if capped else "")


def default_metric(e):
    return "misclassified" if str(e["library"]).endswith("NN") else "is_sdc"


def per_bit(d, metric):
    """(P per sampled bit as a Series indexed by bit, number of injections)."""
    w = d["n_seeds"] if "n_seeds" in d.columns else pd.Series(1.0, index=d.index)
    k = (d[metric] * w).groupby(d["bit"]).sum()
    n = w.groupby(d["bit"]).sum()
    return (k / n).sort_index(), int(n.sum())


def fill_encode(curve, e):
    """HEAAN encode: the encryption rounds away every bit below logQ, so a campaign that
    did not inject them (the exhaustive ones start at logQ) gets P = 0 there. Without
    this the interpolation would copy P(logQ) down to bit 0."""
    log_q = int(e["logQ"])
    heaan_encode = str(e["library"]).startswith("heaan") and e["stage"] == "encode"
    if not heaan_encode or curve.index.min() < log_q:
        return curve, False
    low = pd.Series(0.0, index=[0, log_q - 1])
    return pd.concat([low, curve]).sort_index(), True


def module_p(curve, width):
    """Interpolate the per-bit curve at every bit of [0, width) and average."""
    bits = np.arange(width)
    return float(np.interp(bits, curve.index.to_numpy(float), curve.to_numpy(float)).mean())


def groups(d, e):
    """{"all": every row}, plus aligned / other when the config has a gap."""
    gap = ((1 << int(e["logN"])) // 2) >> int(e["logSlots"])
    out = {"all": d}
    if gap > 1:
        aligned = d["coeff"] % gap == 0
        out["aligned"], out["other"] = d[aligned], d[~aligned]
    return out


def describe(e):
    keys = ["library", "stage", "op_step", "op_depth", "pipeline", "logN", "logSlots",
            "logQ", "logDelta"]
    return "  ".join(f"{k}={e[k]}" for k in keys if k in e.index and str(e[k]) != "")


def report(e, d, args):
    """Print the block of one experiment."""
    print(f"{e['experiment_id']}  {describe(e)}")
    width, source = module_width(e, args.width)
    if width is None:
        print(f"  no W: {source}. Pass --width.")
        return
    metric = args.metric or default_metric(e)
    if metric not in d.columns:
        print(f"  no column {metric} in the data")
        return
    parts = []
    for name, sub in groups(d, e).items():
        if sub.empty:
            continue
        curve, n = per_bit(sub, metric)
        curve, filled = fill_encode(curve, e)
        if name == "all":
            print(f"  metric {metric}, W = {width} ({source}), {n} injections, "
                  f"{len(curve)} sampled bits")
            if filled:
                print(f"  bits below logQ = {e['logQ']} not injected: P = 0 there "
                      f"(rounded away by the encryption)")
            elif curve.index.min() > 0:
                print(f"  warning: no bit below {curve.index.min()} was injected, "
                      f"its P is copied down to bit 0")
            if curve.index.max() < width - 1:
                print(f"  warning: no bit above {curve.index.max()} was injected, "
                      f"its P is copied up to bit {width - 1}")
        parts.append(f"{name} {module_p(curve, width):.3f}")
    print("  P = " + "   ".join(parts))


def main():
    args = parse_args()
    camps = find_experiments(args)
    for i in range(len(camps)):
        e = camps.iloc[i]
        report(e, load_data(camps.iloc[[i]], args.results), args)
        print()


if __name__ == "__main__":
    main()
