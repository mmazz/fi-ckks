#!/usr/bin/env python3
"""P(mis) of the HEAAN decode campaigns of the NN, per key seed.

    cd analysis
    python3 nn_decode_per_seed.py                    # results in ../results_NN
    python3 nn_decode_per_seed.py --by_image         # also one row per (seed, image)

Goes over every HEAAN campaign with stage `decode` and reports, for each key seed:
  - P(mis) at the aligned coefficients (coeff % gap == 0, coeff != 0, coeff != N/2) on the
    plateau bits (--bmin to --bmax), with a 95% Wilson interval that counts coefficients,
    not injections (all the bits of one coefficient move the logit the same way);
  - the same over every bit, for reference;
  - whether a clean plaintext dump exists for that seed (needed by nn_decode_sign.py).

The plateau ends two bits below the modulus of the logits, logQ - 5*logDelta (the network
spends five levels, see heaan_nn.cpp).
"""
import argparse
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
from utils.results import load_campaigns, load_data   # noqa: E402

REPO = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO / "results_NN"
DUMP_DIR = REPO / "results_NN_plain" / "ckks_only_plain"
NN_LEVELS = 5          # W1, x^2, x^3, -0.23*x^3, W2


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default=str(RESULTS_DIR),
                   help=f"raw results dir (default {RESULTS_DIR})")
    p.add_argument("--dumps", default=str(DUMP_DIR),
                   help=f"dir of the clean plaintext dumps (default {DUMP_DIR})")
    p.add_argument("--stage", default="decode")
    p.add_argument("--bmin", type=int, default=34, help="first plateau bit")
    p.add_argument("--bmax", type=int, default=None,
                   help="last plateau bit (default: logits modulus - 2)")
    p.add_argument("--by_image", action="store_true", help="also one row per (seed, image)")
    return p.parse_args()


def wilson(p, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan")
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return c - h, c + h


def dumped_seeds(dump_dir):
    """Key seeds with at least one dump file (..._seed<S>_in<I>.csv)."""
    seeds = set()
    for f in Path(dump_dir).glob("heaan*_seed*_in*.csv"):
        try:
            seeds.add(int(f.stem.split("_seed")[-1].split("_in")[0]))
        except ValueError:
            pass
    return seeds


def summary(g):
    """n injections, n coefficients, P(mis) and its interval over coefficients."""
    p = g["misclassified"].astype(float).mean()
    n_coef = g.groupby(["seed_input", "coeff"]).ngroups
    lo, hi = wilson(p, n_coef)
    return len(g), n_coef, p, lo, hi


def main():
    args = parse_args()
    camps = load_campaigns(args.results, raw=True)
    camps = camps[camps["library"].astype(str).str.contains("heaan", case=False)
                  & (camps["stage"] == args.stage)]
    if camps.empty:
        sys.exit(f"no HEAAN campaign with stage {args.stage} in {args.results}")
    for col in ("logN", "logSlots", "logQ", "logDelta"):
        if camps[col].nunique() != 1:
            sys.exit(f"the {args.stage} campaigns mix values of {col}: "
                     f"{sorted(camps[col].unique())}")
    c = camps.iloc[0]
    N = 1 << int(c["logN"])
    gap = (N // 2) >> int(c["logSlots"])
    logq = int(c["logQ"]) - NN_LEVELS * int(c["logDelta"])
    bmax = args.bmax if args.bmax is not None else logq - 2

    data = load_data(camps, args.results)
    data = data[(data["coeff"] % gap == 0) & (data["coeff"] != 0) & (data["coeff"] != N // 2)]
    plateau = data[(data["bit"] >= args.bmin) & (data["bit"] <= bmax)]
    have_dump = dumped_seeds(args.dumps)

    print(f"{len(camps)} campaigns, N = {N}, gap = {gap}, logits modulus {logq} bits")
    print(f"Aligned coefficients, plateau bits {args.bmin}-{bmax}\n")
    print(" seed  images     n  coeffs   P(mis)   95% (coeffs)    all bits   dump")
    for seed, g in plateau.groupby("seed"):
        n, nc, p, lo, hi = summary(g)
        p_all = data[data["seed"] == seed]["misclassified"].astype(float).mean()
        dump = "yes" if int(seed) in have_dump else "NO"
        print(f" {int(seed):4d}  {g['seed_input'].nunique():6d} {n:5d}  {nc:6d}"
              f"   {p:.3f}   [{lo:.3f}, {hi:.3f}]      {p_all:.3f}   {dump}")
    n, nc, p, lo, hi = summary(plateau)
    print(f"  all  {plateau['seed_input'].nunique():6d} {n:5d}  {nc:6d}"
          f"   {p:.3f}   [{lo:.3f}, {hi:.3f}]      "
          f"{data['misclassified'].astype(float).mean():.3f}")
    means = plateau.groupby("seed")["misclassified"].apply(lambda s: s.astype(float).mean())
    print(f"\nMean of the per-seed P(mis): {means.mean():.3f}, "
          f"range {means.min():.3f} - {means.max():.3f}")

    if args.by_image:
        print("\n seed  image     n  coeffs   P(mis)")
        for (seed, img), g in plateau.groupby(["seed", "seed_input"]):
            n, nc, p, _, _ = summary(g)
            print(f" {int(seed):4d}  {int(img):5d} {n:5d}  {nc:6d}   {p:.3f}")


if __name__ == "__main__":
    main()
