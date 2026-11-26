#!/usr/bin/env python3
"""
Dump OpenFHE detector counts, one row per (campaign, limb, coefficient class, bit).

Coefficient classes: zero (coeff 0), half (coeff N/2), aligned (other multiples of the gap),
unaligned. Every row carries the campaign parameters, so any table can be built from the file.
All bits are kept; restricting to the module bits [0, logQ) is done at analysis time.

Usage:
  python3 detector_dump.py results_client results_server results_nn_openfhe -o detector_cells.csv.gz
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

KEEP = ["campaign_id", "library", "stage", "logN", "logQ", "logDelta", "logSlots", "withNTT",
        "mult_depth", "pipeline", "op_step", "op_depth", "seed", "seed_input", "isExhaustive",
        "scaleTech", "attackModeSKA", "thresholdSKA"]
COLS = ["limb", "coeff", "bit", "l2_rel", "detected", "corrupted", "failed",
        "misclassified", "out_of_range"]
VISIBLE = 1e-2   # E_L2 threshold for "visible" (thesis criterion)


def to_bool(s):
    """Accept 0/1, True/False or 'true'/'false'."""
    if s.dtype == bool:
        return s
    if s.dtype.kind in "iuf":
        return s.fillna(0) != 0
    return s.astype(str).str.strip().str.lower().isin(["1", "true", "yes"])


def coeff_class(coeff, n_half, gap):
    cls = np.where(coeff % gap == 0, "aligned", "unaligned").astype(object)
    cls[coeff == n_half] = "half"
    cls[coeff == 0] = "zero"
    return cls


def summarize(d, row):
    n_half = 2 ** (int(row["logN"]) - 1)
    gap = 2 ** (int(row["logN"]) - 1 - int(row["logSlots"]))
    l2 = d["l2_rel"].astype(float)
    det = to_bool(d["detected"])
    sdc = (d["corrupted"].fillna(0) + d["failed"].fillna(0)) > 0   # some slot > 10 %
    mis = to_bool(d["misclassified"]) if "misclassified" in d else pd.Series(False, index=d.index)
    oor = to_bool(d["out_of_range"]) if "out_of_range" in d else pd.Series(False, index=d.index)
    vis = l2 > VISIBLE
    zero = l2 == 0
    d = d.assign(
        cls=coeff_class(d["coeff"].to_numpy(), n_half, gap),
        det=det, sdc=sdc, sdc_det=sdc & det, vis=vis, vis_det=vis & det,
        zero=zero, zero_det=zero & det, mis=mis, mis_det=mis & det, oor=oor,
        l2_undet=l2.where(~det), l2_det=l2.where(det & (l2 > 0)), l2=l2,
    )
    g = d.groupby(["limb", "cls", "bit"])
    return g.agg(
        n=("det", "size"), n_det=("det", "sum"),
        n_sdc=("sdc", "sum"), n_sdc_det=("sdc_det", "sum"),
        n_vis=("vis", "sum"), n_vis_det=("vis_det", "sum"),
        n_zero=("zero", "sum"), n_zero_det=("zero_det", "sum"),
        n_mis=("mis", "sum"), n_mis_det=("mis_det", "sum"),
        n_oor=("oor", "sum"),
        l2_median=("l2", "median"),
        l2_undet_max=("l2_undet", "max"),
        l2_det_min=("l2_det", "min"),
    ).reset_index()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="+", help="results directories")
    ap.add_argument("-o", "--out", default="detector_cells.csv.gz")
    args = ap.parse_args()

    parts = []
    for res in args.results:
        start_path = os.path.join(res, "campaigns_start.csv")
        if not os.path.exists(start_path):
            print(f"[skip] {start_path} not found")
            continue
        start = pd.read_csv(start_path)
        # HEAAN files also have a 'detected' column (always 0): filter by library.
        start = start[start["library"].astype(str).str.lower().str.contains("openfhe")]
        print(f"[info] {res}: {len(start)} OpenFHE campaigns")
        for _, row in start.iterrows():
            path = os.path.join(res, "data", f"campaign_{int(row['campaign_id']):06d}.csv.gz")
            if not os.path.exists(path):
                print(f"[skip] {path} not found")
                continue
            head = pd.read_csv(path, nrows=0).columns
            d = pd.read_csv(path, usecols=[c for c in COLS if c in head])
            cells = summarize(d, row)
            for k in KEEP:
                if k in row.index:
                    cells[k] = row[k]
            cells["results"] = os.path.basename(os.path.normpath(res))
            parts.append(cells)

    if not parts:
        sys.exit("No OpenFHE campaigns found.")
    out = pd.concat(parts, ignore_index=True)
    out.to_csv(args.out, index=False)
    size_mb = os.path.getsize(args.out) / 2**20
    print(f"[ok] {len(out)} rows, {out['campaign_id'].nunique()} campaigns -> {args.out} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
