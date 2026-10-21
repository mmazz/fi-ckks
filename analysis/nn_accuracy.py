#!/usr/bin/env python3
"""NN workloads without faults: accuracy and macro-F1, in plain and under CKKS.

Reads the per-image CSVs written by fi_nn_metrics_heaan / fi_nn_metrics_openfhe
(groups heaan_metrics / openfhe_metrics of scripts/NNCampaigns.py) and prints one row
per configuration. Seeds are pooled: each (image, seed) pair counts once.

  python3 analysis/nn_accuracy.py
  python3 analysis/nn_accuracy.py --results results_NN
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

CONFIG = ["library", "logN", "logQ", "logDelta", "logSlots", "mult_depth"]


def macro_f1(labels, preds):
    """Unweighted mean of the one-vs-rest F1 over the classes present in labels
    (same definition as apps/tools/nn_metrics.cpp)."""
    f1 = []
    for c in np.unique(labels):
        tp = np.sum((preds == c) & (labels == c))
        fp = np.sum((preds == c) & (labels != c))
        fn = np.sum((preds != c) & (labels == c))
        f1.append(2 * tp / (2 * tp + fp + fn))
    return float(np.mean(f1))


def summarize(df):
    rows = []
    for cfg, g in df.groupby(CONFIG):
        y = g["label"].to_numpy()
        plain = g["plain_pred"].to_numpy()
        ckks = g["ckks_pred"].to_numpy()
        rows.append({**dict(zip(CONFIG, cfg)),
                     "seeds": g["seed"].nunique(), "images": g["image"].nunique(),
                     "acc_plain": np.mean(plain == y), "f1_plain": macro_f1(y, plain),
                     "acc_ckks": np.mean(ckks == y), "f1_ckks": macro_f1(y, ckks),
                     "agreement": np.mean(ckks == plain),
                     "logit_err_mean": g["logit_rel_err"].mean(),
                     "logit_err_max": g["logit_rel_err"].max()})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", default=str(Path(__file__).resolve().parent.parent / "results_NN"))
    args = ap.parse_args()

    files = sorted(Path(args.results, "nn_metrics").glob("*.csv"))
    if not files:
        raise SystemExit(f"no files in {args.results}/nn_metrics: "
                         "run python3 scripts/NNCampaigns.py '*_metrics' first")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)

    pd.set_option("display.width", 250)
    print(summarize(df).to_string(index=False, float_format=lambda x: f"{x:.4g}"))


if __name__ == "__main__":
    main()
