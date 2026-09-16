"""Promedia entre seeds: una fila por (config_id, limb, coeff, bit).

    python3 aggregate.py ../results        -> ../results/agg/per_coeff_bit.parquet
"""
import sys
from pathlib import Path
import pandas as pd
from utils.results import load_campaigns, load_data, config_columns


def aggregate(data, keys):
    return (data.groupby(["config_id", *keys])
                .agg(n_seeds=("err_bits", "size"),
                     err_bits_mean=("err_bits", "mean"),
                     err_bits_median=("err_bits", "median"),
                     err_bits_std=("err_bits", "std"),
                     err_bits_max=("err_bits", "max"),
                     frac_zero=("l2_rel", lambda x: (x == 0).mean()),
                     frac_failed=("failed", lambda x: (x > 0).mean()))
                .reset_index())


def main(results_dir):
    results_dir = Path(results_dir)
    camps = load_campaigns(results_dir)
    out = results_dir / "agg"
    out.mkdir(exist_ok=True)

    parts = []
    for exhaustive, keys in [(1, ["limb", "coeff", "bit"]), (0, ["bit"])]:
        sel = camps[camps["isExhaustive"] == exhaustive]
        if sel.empty:
            continue
        parts.append(aggregate(load_data(sel, results_dir), keys))
    agg = pd.concat(parts, ignore_index=True)

    cfg = camps.drop_duplicates("config_id")[["config_id", *config_columns(camps)]]
    agg.merge(cfg, on="config_id").to_parquet(out / "per_coeff_bit.parquet", index=False)
    print(f"{len(agg)} filas, {agg['config_id'].nunique()} configs -> {out / 'per_coeff_bit.parquet'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../results")
