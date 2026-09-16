"""Tabla de features para ML: una fila por (config_id, limb, coeff, bit), target = err_bits_mean.

    python3 build_ml_dataset.py ../results  -> ../results/agg/ml_dataset.parquet
"""
import sys
from pathlib import Path
import pandas as pd

OPS = ["add", "pmul", "mul", "scalar", "rot", "boot"]
MULTS = {"pmul", "mul", "scalar"}
CLIENT_PRE = {"encode", "encrypt_c0", "encrypt_c1"}
CLIENT_POST = {"decrypt_c0", "decrypt_c1", "decode"}


def expand(pipeline):
    """'add; mul x2; rot 4' -> ['add', 'mul', 'mul', 'rot']  (misma gramatica que el C++)."""
    ops = []
    for chunk in str(pipeline).split(";"):
        w = chunk.split()
        if not w or w[0] == "nan":
            continue
        reps = next((int(t[1:]) for t in w[1:] if t.startswith("x") and t[1:].isdigit()), 1)
        ops += [w[0]] * reps
    return ops


def injection_index(ops, stage, op_depth):
    """Posicion del op inyectado dentro del pipeline expandido."""
    if stage in CLIENT_PRE:
        return -1                      # antes de todo el pipeline
    if stage in CLIENT_POST:
        return len(ops)                # despues de todo el pipeline
    if stage == "rescale":             # el k-esimo rescale = la k-esima mult
        idx = [i for i, o in enumerate(ops) if o in MULTS]
    else:
        base = stage.replace("_asplos", "").split("_")[0]   # mul_asplos->mul, boot_eval->boot
        idx = [i for i, o in enumerate(ops) if o == base]
    return idx[op_depth]


def pipeline_features(row):
    ops = expand(row["pipeline"])
    pos = injection_index(ops, row["stage"], int(row["op_depth"]))
    after = ops[pos + 1:] if pos >= 0 else ops
    before = ops[:max(pos, 0)]
    f = {f"n_{o}": ops.count(o) for o in OPS}
    f["n_ops"] = len(ops)
    f["mults_before"] = sum(o in MULTS for o in before)
    f["mults_after"] = sum(o in MULTS for o in after)
    f["ops_after"] = len(after)
    f["boot_after"] = int("boot" in after)
    return pd.Series(f)


def main(results_dir):
    agg = pd.read_parquet(Path(results_dir) / "agg" / "per_coeff_bit.parquet")
    cfg = agg.drop_duplicates("config_id").set_index("config_id")
    df = agg.merge(cfg.apply(pipeline_features, axis=1), left_on="config_id", right_index=True)

    # Posicion del bit relativa a los parametros
    df["bit_minus_delta"] = df["bit"] - df["logDelta"]
    df["bit_minus_q"] = df["bit"] - df["logQ"]
    df["bit_over_q"] = df["bit"] / df["logQ"]
    if "coeff" in df:
        gap = 2 ** (df["logN"] - 1 - df["logSlots"])   # separacion entre slots en los coeficientes
        df["coeff_aligned"] = (df["coeff"] % gap == 0).astype(int)

    df = pd.get_dummies(df, columns=["library", "stage", "scaleTech"], dtype=int)
    df = df.drop(columns=["pipeline"])
    df.to_parquet(Path(results_dir) / "agg" / "ml_dataset.parquet", index=False)
    print(df.shape, "->", Path(results_dir) / "agg" / "ml_dataset.parquet")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../results")
