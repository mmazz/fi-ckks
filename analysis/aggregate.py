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
                     frac_failed=("failed", lambda x: (x > 0).mean()),
                     # Rate targets: err_bits says HOW BIG the error is, these say HOW
                     # OFTEN it is visible. Useful as a second ML target (classification).
                     sdc_rate=("is_sdc", "mean"),
                     masked_rate=("is_masked", "mean"),
                     detected_rate=("detected", "mean"),
                     frac_bad_mean=("frac_bad", "mean"),
                     misclassified_rate=("misclassified", "mean"),
                     # err_bits viene clipeado: esto dice cuanto de la celda toco el techo
                     # (o era inf/NaN) y por lo tanto no es un valor de error confiable.
                     frac_saturated=("err_saturated", "mean"))
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
        part = aggregate(load_data(sel, results_dir), keys)
        # Las random no tienen un coeficiente fijo: -1 en vez de NaN, y una columna
        # que dice a que granularidad corresponde cada fila.
        part["grain"] = "coeff_bit" if exhaustive else "bit"
        for col in ("limb", "coeff"):
            if col not in part.columns:
                part[col] = -1
        parts.append(part)
    agg = pd.concat(parts, ignore_index=True)
    agg[["limb", "coeff"]] = agg[["limb", "coeff"]].astype(int)

    parts = []

    cfg = camps.drop_duplicates("config_id")[["config_id", *config_columns(camps)]]
    agg.merge(cfg, on="config_id").to_parquet(out / "per_coeff_bit.parquet", index=False)
    print(f"{len(agg)} filas, {agg['config_id'].nunique()} configs -> {out / 'per_coeff_bit.parquet'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../results")
