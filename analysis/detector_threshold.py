#!/usr/bin/env python3
"""
Does OpenFHE's detector always fire above some E_L2? Reads the output of detector_dump.py.

X = largest E_L2 of an undetected injection. Everything with E_L2 > X was detected.
Coefficient 0 of c0 is reported apart (its fault is a real constant, the detector looks at
the imaginary part). Only module bits [0, logQ) are used.

Usage:
  python3 detector_threshold.py detector_cells.csv.gz
"""
import sys

import numpy as np
import pandas as pd

VISIBLE = 1e-2
# Stages / server steps whose fault lands on c0 (fault-hook numbering of the thesis).
C0_STAGES = {"encode", "encrypt_c0", "decrypt_c0"}
C0_STEPS = {"add": {2, 3, 5}, "mul": {4, 7, 9}}


def on_c0(d):
    by_step = pd.Series(False, index=d.index)
    for stage, steps in C0_STEPS.items():
        by_step |= (d["stage"] == stage) & d["op_step"].isin(steps)
    return d["stage"].isin(C0_STAGES) | by_step


def where_max(x):
    """X and the bit where it happens, with and without the top bit of the module.
    The top bit (logQ - 1) holds an isolated undetected cell (c1, 8 slots, one key)."""
    out = {}
    for name, part in [("", x), ("_no_top", x[x["bit"] < x["logQ"] - 1])]:
        if part["l2_undet_max"].notna().sum() == 0:
            out["X" + name], out["bit_X" + name] = np.nan, np.nan
            continue
        i = part["l2_undet_max"].idxmax()
        out["X" + name], out["bit_X" + name] = part.loc[i, "l2_undet_max"], part.loc[i, "bit"]
    return pd.Series(out)


def table(d, by):
    g = d.groupby(by)
    t = pd.DataFrame({"vis": g["n_vis"].sum(),
                      "vis_undet": g["n_vis"].sum() - g["n_vis_det"].sum()})
    t["P_undet|vis"] = t["vis_undet"] / t["vis"]
    return t.join(g.apply(where_max, include_groups=False))


def main():
    d = pd.read_csv(sys.argv[1], low_memory=False)
    d["pipeline"] = d["pipeline"].fillna("").astype(str)
    d["nlimbs"] = d.groupby(["results", "campaign_id"])["limb"].transform("max") + 1
    d = d[d["bit"] < d["logQ"]]
    # NTT goes before RNS: a fault in NTT form is spread over all coefficients, whatever the limbs.
    d["regime"] = np.select([d["pipeline"].str.contains("boot"), d["withNTT"] == 1, d["nlimbs"] > 1],
                            ["boot", "NTT", "RNS"], "1 limb")
    zero_c0 = (d["cls"] == "zero") & on_c0(d)
    rest, z = d[~zero_c0], d[zero_c0]
    pd.set_option("display.width", 200)

    print("== Everything except coefficient 0 of c0 ==")
    print(table(rest, ["results", "regime"]).to_string())
    print("\n== 1 limb, by stage and pipeline ==")
    one = rest[rest["regime"] == "1 limb"]
    print(table(one, ["results", "stage", "pipeline", "op_step", "logSlots"]).to_string())

    print("\n== Coefficient 0 of c0: P(detected) by decade of E_L2 (visible only) ==")
    zv = z[(z["l2_median"] > VISIBLE) & (z["results"] != "results_NN")].copy()
    zv["decade"] = np.floor(np.log10(zv["l2_median"])).astype(int)
    g = zv.groupby(["regime", "decade"])
    t = pd.DataFrame({"n": g["n"].sum(), "det": g["n_det"].sum()})
    t["P_det"] = t["det"] / t["n"]
    print(t.to_string())

    print("\n== Coefficient 0 of c0: totals per regime (visible only) ==")
    g = zv.groupby("regime")
    t = pd.DataFrame({"n": g["n"].sum(), "det": g["n_det"].sum(),
                      "max_E_undet": g["l2_undet_max"].max()})
    t["P_det"] = t["det"] / t["n"]
    print(t.to_string())

    nn = d[d["results"].str.contains("NN")]
    if len(nn):
        print("\n== Network: class changed vs detected ==")
        g = nn.groupby("stage")
        t = pd.DataFrame({"n": g["n"].sum(), "mis": g["n_mis"].sum(),
                          "mis_undet": g["n_mis"].sum() - g["n_mis_det"].sum(),
                          "det_class_kept": g["n_det"].sum() - g["n_mis_det"].sum()})
        print(t.to_string())
        print(f"coefficient-0 cells sampled in the network: {(nn['cls'] == 'zero').sum()}")


if __name__ == "__main__":
    main()
