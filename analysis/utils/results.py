"""Carga de resultados de fi-ckks: registry + datos por campania."""
from pathlib import Path
import hashlib
import numpy as np
import pandas as pd

# Todo lo que NO define el experimento. El resto de las columnas del start CSV es la config.
NOT_CONFIG = {"campaign_id", "seed", "seed_input", "config_id", "saveVectors"}
# Columns of campaigns_end.csv: RESULTS, never features nor part of the config.
# sdc_count is the old name of detected_count (results dirs created before the rename).
END_COLS = {"total_bitFlips", "detected_count", "sdc_count", "duration_minutes", "l2_P95", "l2_P99"}
ERR_FLOOR = 2.0 ** -60    # piso para log2 cuando el error es exactamente 0
# Techo: solo para que un inf/NaN no arruine la celda entera. Tiene que quedar MUY por
# encima de cualquier error real (con logQ=840 y logDelta=40 el l2_rel llega a ~2^800),
# asi que no se clipea nada medible: 2^1000 es practicamente el maximo de un double.
ERR_CEIL = 2.0 ** 1000


def finite_max(arrays, floor=0.0):
    """Maximo ignorando inf/NaN sobre una o varias secuencias (de largos distintos).

    `floor` es lo que se devuelve si no queda ningun valor finito. Un solo inf
    (un flip en un bit alto que desborda) basta para romper LogNorm en los mapas de
    registro, asi que la escala de color nunca se calcula sobre no-finitos.
    """
    if isinstance(arrays, (pd.Series, np.ndarray)) or not hasattr(arrays, "__iter__"):
        arrays = [arrays]
    out = floor
    for a in arrays:
        v = np.asarray(a, dtype=float).ravel()
        v = v[np.isfinite(v)]
        if v.size:
            out = max(out, float(v.max()))
    return out

def load_campaigns(results_dir):
    """Una fila por campania TERMINADA (start JOIN end), con config_id."""
    results_dir = Path(results_dir)
    start = pd.read_csv(results_dir / "campaigns_start.csv", keep_default_na=False)   # pipeline vacio = ""
    end = pd.read_csv(results_dir / "campaigns_end.csv")
    camps = start.merge(end, on="campaign_id", how="inner")   # las interrumpidas quedan afuera

    return assign_config_id(camps)


def assign_config_id(camps):
    """(Re)compute config_id from the CURRENT column values.

    load_campaigns() calls it once. Any caller that overwrites a config column (so that
    campaigns which differ only in that column count as one) has to call it again:
    config_id is a stored hash, not a view, so overwriting the column alone leaves the
    old hash in place and require_single_config() still sees two configs.
    """
    camps = camps.copy()
    key = camps[config_columns(camps)].astype(str).agg("|".join, axis=1)
    camps["config_id"] = key.map(lambda s: hashlib.sha1(s.encode()).hexdigest()[:10])
    return camps


def config_columns(df):
    return [c for c in df.columns if c not in NOT_CONFIG and c not in END_COLS]


def select(camps, **filters):
    """Filtro exacto: select(camps, library="heaan", stage="encrypt_c0", pipeline="add")."""
    mask = np.ones(len(camps), dtype=bool)
    for col, val in filters.items():
        if col not in camps.columns:
            raise KeyError(f"unknown column: {col}")
        mask &= (camps[col] == val).to_numpy()
    return camps[mask]


def require_single_config(camps):
    """Falla si el filtro dejo mas de una config, y dice en que columnas difieren."""
    if camps["config_id"].nunique() != 1:
        cols = [c for c in config_columns(camps) if camps[c].nunique() > 1]
        raise ValueError(f"{camps['config_id'].nunique()} different configs; they differ in: {cols}")
    return camps


def load_data(camps, results_dir):
    """Concatena los .csv.gz de las campanias pedidas y agrega err_bits."""
    data_dir = Path(results_dir) / "data"
    dfs = []
    for cid in camps["campaign_id"]:
        df = pd.read_csv(data_dir / f"campaign_{int(cid):06d}.csv.gz")
        df["campaign_id"] = int(cid)
        dfs.append(df)
    data = pd.concat(dfs, ignore_index=True)
    # Piso Y techo: sin el techo, un solo inf deja err_bits_mean = inf y err_bits_std = NaN
    # en esa celda para siempre. `err_saturated` dice cuantas filas tocaron el techo.
    l2 = data["l2_rel"].to_numpy(dtype=float)
    data["err_saturated"] = (~np.isfinite(l2)) | (l2 > ERR_CEIL)
    data["err_bits"] = np.log2(np.clip(np.nan_to_num(l2, nan=ERR_CEIL, posinf=ERR_CEIL),
                                       ERR_FLOOR, ERR_CEIL))
        # Rate metrics, from the slot counters the injector already logs. They are all plain
    # columns, so they work as --metric in bit_curve.py / flat_curve.py: with --stat mean
    # an indicator column becomes a PROBABILITY per bit, which is the other half of the
    # story (how often a flip is visible at all, next to how big the error is).
    slots = data[["correct", "degraded", "corrupted", "failed"]].sum(axis=1)
    data["n_slots"] = slots
    data["frac_bad"] = (data["degraded"] + data["corrupted"] + data["failed"]) / slots
    data["frac_failed"] = data["failed"] / slots
    data["is_sdc"] = ((data["corrupted"] + data["failed"]) > 0).astype(float)
    data["is_masked"] = (data["correct"] == slots).astype(float)
    data["detected"] = data["detected"].astype(float)            # OpenFHE SDC detector
    data["misclassified"] = data["misclassified"].astype(float)  # NN workloads only
    # Detector outcome vs ground truth, for coverage / false-alarm tables (OpenFHE).
    data["sdc_undetected"] = ((data["is_sdc"] > 0) & (data["detected"] == 0)).astype(float)
    data["false_alarm"] = ((data["is_sdc"] == 0) & (data["detected"] > 0)).astype(float)
    return data.merge(camps[["campaign_id", "config_id", "seed", "seed_input"]], on="campaign_id")

def parse_value(v):
    """CLI value -> int, float or str. Shared by the plotting scripts."""
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    return v
