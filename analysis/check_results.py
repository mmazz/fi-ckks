#!/usr/bin/env python3
"""Sanity check of a results directory. Run it AFTER the campaigns and BEFORE plotting.

    python3 check_results.py ../results           # full check (reads every data file)
    python3 check_results.py ../results --quick   # registry only, skips the data files

Exit code 1 if something is wrong, 0 otherwise. Checks:
  1. campaigns that started but never finished (load_campaigns drops them silently)
  2. duplicated campaign_id in campaigns_end.csv (same config launched twice in parallel)
  3. finished campaigns whose data file is missing or has fewer rows than total_bitFlips
  4. configurations with a different number of repetitions (seed x seed_input), or
     repetitions of the same config with a different number of injections
  5. (not --quick) non-finite l2_rel and out_of_range rows, in percent, per stage
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from utils.results import load_campaigns

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)


def data_path(results_dir, cid):
    return Path(results_dir) / "data" / f"campaign_{int(cid):06d}.csv.gz"


def check_unfinished(results_dir):
    start = pd.read_csv(results_dir / "campaigns_start.csv", keep_default_na=False)
    end = pd.read_csv(results_dir / "campaigns_end.csv")
    print(f"campaigns started : {len(start)}")
    print(f"campaigns finished: {len(end)}")
    problems = 0

    missing = start[~start["campaign_id"].isin(end["campaign_id"])]
    if len(missing):
        problems += 1
        print(f"\n!! {len(missing)} campaign(s) started but never finished. They are NOT in the "
              "plots. Re-run their group (finished ones are skipped):")
        print(missing[["campaign_id", "library", "stage", "logN", "pipeline", "op_step",
                       "seed", "seed_input"]].to_string(index=False))

    dup = end[end["campaign_id"].duplicated(keep=False)]
    if len(dup):
        problems += 1
        ids = sorted(int(x) for x in dup["campaign_id"].unique())
        print(f"\n!! campaign_id duplicated in campaigns_end.csv: {ids}")
        print("   The same config was launched twice in parallel; both wrote the same data file. "
              "Delete those rows and data files and re-run them.")
    return problems


def check_data_files(camps, results_dir, quick):
    """Missing / truncated data files. Returns (problems, rows of the full check or None)."""
    problems = 0
    absent = [cid for cid in camps["campaign_id"] if not data_path(results_dir, cid).exists()]
    if absent:
        problems += 1
        print(f"\n!! {len(absent)} finished campaign(s) without data file: {absent[:20]}")
    if quick:
        return problems, None

    rows, short = [], []
    for _, c in camps.iterrows():
        path = data_path(results_dir, c["campaign_id"])
        if not path.exists():
            continue
        try:
            d = pd.read_csv(path, usecols=["l2_rel", "out_of_range"])
        except Exception as e:                       # truncated gzip, empty file, ...
            short.append((c["campaign_id"], f"unreadable: {e}"))
            continue
        if len(d) < c["total_bitFlips"]:
            short.append((c["campaign_id"], f"{len(d)} rows < total_bitFlips={c['total_bitFlips']}"))
        l2 = pd.to_numeric(d["l2_rel"], errors="coerce").to_numpy(dtype=float)
        rows.append(dict(library=c["library"], stage=c["stage"], n=len(d),
                         nonfinite=int((~np.isfinite(l2)).sum()),
                         out_of_range=int(d["out_of_range"].sum())))
    if short:
        problems += 1
        print(f"\n!! {len(short)} data file(s) truncated or unreadable:")
        for cid, why in short[:20]:
            print(f"   campaign {cid}: {why}")
    return problems, rows


def check_repetitions(camps):
    problems = 0
    reps = (camps.groupby("config_id")
                 .agg(library=("library", "first"), stage=("stage", "first"),
                      logN=("logN", "first"), op_step=("op_step", "first"),
                      pipeline=("pipeline", "first"), n=("campaign_id", "size"),
                      seeds=("seed", "nunique"), inputs=("seed_input", "nunique"),
                      inj_min=("total_bitFlips", "min"), inj_max=("total_bitFlips", "max")))
    lo, hi = reps["n"].min(), reps["n"].max()
    print(f"\nconfigurations: {len(reps)}, repetitions per configuration: "
          f"{lo if lo == hi else f'{lo}..{hi}'}")

    if lo != hi:
        problems += 1
        print("!! not every configuration has the same number of repetitions; the ones with "
              "fewer\n   seeds carry less weight when you average (only matters for configs "
              "you compare):")
        print(reps[reps["n"] < hi].drop(columns=["inj_min", "inj_max"]).to_string())

    uneven = reps[reps["inj_min"] != reps["inj_max"]]
    if len(uneven):
        problems += 1
        print("\n!! repetitions of the same config with a different number of injections "
              "(they do not align cell by cell):")
        print(uneven.to_string())
    return problems


def print_row_stats(rows):
    if not rows:
        return
    t = pd.DataFrame(rows).groupby(["library", "stage"]).sum()
    t["pct_nonfinite"] = (100 * t["nonfinite"] / t["n"]).round(2)
    t["pct_out_of_range"] = (100 * t["out_of_range"] / t["n"]).round(2)
    print("\nrows per stage:")
    print(t[["n", "pct_nonfinite", "pct_out_of_range"]].to_string())
    print("(non-finite l2_rel: use --metric err_bits in bit_curve.py, it is clipped)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", help="results directory (has campaigns_start.csv)")
    ap.add_argument("--quick", action="store_true", help="registry only, do not read data files")
    args = ap.parse_args()
    results_dir = Path(args.results)

    problems = check_unfinished(results_dir)
    camps = load_campaigns(results_dir, raw=True)
    if camps.empty:
        print("\nno finished campaigns")
        sys.exit(1)
    camps = camps.drop_duplicates("campaign_id")    # already reported by check_unfinished

    p, rows = check_data_files(camps, results_dir, args.quick)
    problems += p
    problems += check_repetitions(camps)
    print_row_stats(rows)

    print(f"\n{problems} problem(s) found" if problems else "\nOK")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
