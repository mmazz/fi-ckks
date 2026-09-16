"""Carga de resultados de fi-ckks: registry + datos por campania."""
from pathlib import Path
import hashlib
import numpy as np
import pandas as pd

# Todo lo que NO define el experimento. El resto de las columnas del start CSV es la config.
NOT_CONFIG = {"campaign_id", "seed", "seed_input", "config_id"}
# Columnas de campaigns_end.csv: son RESULTADOS, nunca features ni parte de la config.
END_COLS = {"total_bitFlips", "sdc_count", "duration_seconds", "l2_P95", "l2_P99", "duration", "git_commit"}
ERR_FLOOR = 2.0 ** -60   # piso para log2 cuando el error es exactamente 0


def load_campaigns(results_dir):
    """Una fila por campania TERMINADA (start JOIN end), con config_id."""
    results_dir = Path(results_dir)
    start = pd.read_csv(results_dir / "campaigns_start.csv", keep_default_na=False)   # pipeline vacio = ""
    end = pd.read_csv(results_dir / "campaigns_end.csv")
    camps = start.merge(end, on="campaign_id", how="inner")   # las interrumpidas quedan afuera

    key = camps[config_columns(start)].astype(str).agg("|".join, axis=1)
    camps["config_id"] = key.map(lambda s: hashlib.sha1(s.encode()).hexdigest()[:10])
    return camps


def config_columns(df):
    return [c for c in df.columns if c not in NOT_CONFIG and c not in END_COLS]


def select(camps, **filters):
    """Filtro exacto: select(camps, library="heaan", stage="encrypt_c0", pipeline="add")."""
    mask = np.ones(len(camps), dtype=bool)
    for col, val in filters.items():
        if col not in camps.columns:
            raise KeyError(f"columna inexistente: {col}")
        mask &= (camps[col] == val).to_numpy()
    return camps[mask]


def require_single_config(camps):
    """Falla si el filtro dejo mas de una config, y dice en que columnas difieren."""
    if camps["config_id"].nunique() != 1:
        cols = [c for c in config_columns(camps) if camps[c].nunique() > 1]
        raise ValueError(f"{camps['config_id'].nunique()} configs distintas; difieren en: {cols}")
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
    data["err_bits"] = np.log2(np.maximum(data["l2_rel"].to_numpy(dtype=float), ERR_FLOOR))
    return data.merge(camps[["campaign_id", "config_id", "seed", "seed_input"]], on="campaign_id")
