"""Load fi-ckks results. Works on two layouts, told apart by campaigns_start.csv:

  raw        what the C++ writes: one row per campaign (config + seed + seed_input) in
             campaigns_start.csv / campaigns_end.csv, one data/campaign_XXXXXX.csv.gz each.
  collapsed  what collapse.py writes: one row per experiment in campaigns_start.csv, with
             a data_file column pointing to ONE csv where the seeds are already averaged.

load_campaigns() and load_data() return the same columns in both cases, so the plotting
scripts take either directory with --results.
"""
from pathlib import Path
import hashlib
import numpy as np
import pandas as pd

# Columns that the collapsed index adds: they say where the data is and which campaigns
# went into it, not how the experiment was configured.
INDEX_COLS = {"experiment_id", "data_file", "n_campaigns", "campaign_ids", "seeds",
              "seed_inputs", "sdc_rate", "detected_rate"}
# Everything that does NOT define the experiment. The rest of campaigns_start is the config.
NOT_CONFIG = {"campaign_id", "seed", "seed_input", "config_id", "saveVectors"} | INDEX_COLS
# Columns of campaigns_end.csv: RESULTS, never features nor part of the config.
END_COLS = {"total_bitFlips", "detected_count", "duration_minutes", "l2_P95", "l2_P99"}
# Max logit change (linf_rel, in %) that still counts as masked. Same value as
# register_map.MASKED_PCT.
MOVED_PCT = 0.1
ERR_FLOOR = 2.0 ** -60    # floor for log2 when the error is exactly 0
# Ceiling: only so that one inf/NaN does not ruin a whole cell. It has to sit far above any
# real error (with logQ=840 and logDelta=40 l2_rel reaches ~2^800), so nothing measurable
# is clipped: 2^1000 is close to the largest double.
ERR_CEIL = 2.0 ** 1000


def finite_max(arrays, floor=0.0):
    """Max over one or more sequences (of different lengths), ignoring inf/NaN.

    `floor` is returned when no finite value is left. A single inf (a flip in a high bit
    that overflows) is enough to break LogNorm in the register maps, so the color scale
    is never computed over non-finite values.
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


def is_collapsed(camps):
    return "data_file" in camps.columns


def load_campaigns(results_dir, raw=False):
    """One row per experiment, read from the collapsed cache, with config_id.

    Given a raw dir (the one the C++ writes), the cache <results_dir>/collapsed is brought
    up to date first: only experiments with new finished campaigns are rewritten, so when
    nothing changed this costs two small CSV reads. Given a collapsed dir (e.g. the copy in
    the thesis repo, without the raw data), it is used as is.

    raw=True: one row per FINISHED campaign, straight from the raw registry, no cache.
    Only check_results.py and the collapse itself need that.
    """
    results_dir = Path(results_dir)
    # keep_default_na=False: an empty pipeline has to stay "", not NaN
    start = pd.read_csv(results_dir / "campaigns_start.csv", keep_default_na=False)
    if is_collapsed(start):
        return assign_config_id(start)
    if not raw:
        from .collapse import collapse_dir            # here, to avoid a circular import
        out = collapse_dir(results_dir, verbose=True)
        camps = load_campaigns(out)
        # Absolute paths: callers keep passing the raw dir to load_data().
        camps["data_file"] = [str((out / f).resolve()) for f in camps["data_file"]]
        return camps
    end = pd.read_csv(results_dir / "campaigns_end.csv")
    camps = start.merge(end, on="campaign_id", how="inner")   # unfinished ones are dropped
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
    """Exact filter: select(camps, library="heaan", stage="encrypt_c0", pipeline="add")."""
    mask = np.ones(len(camps), dtype=bool)
    for col, val in filters.items():
        if col not in camps.columns:
            raise KeyError(f"unknown column: {col}")
        mask &= (camps[col] == val).to_numpy()
    return camps[mask]


def require_single_config(camps):
    """Fail if the filter left more than one config, and say which columns differ."""
    if camps["config_id"].nunique() != 1:
        cols = [c for c in config_columns(camps) if camps[c].nunique() > 1]
        raise ValueError(f"{camps['config_id'].nunique()} different configs; they differ in: {cols}")
    return camps


def add_derived(data):
    """err_bits and the rate metrics, computed from the columns the C++ logs."""
    # Floor AND ceiling: without the ceiling one inf leaves err_bits_mean = inf and
    # err_bits_std = NaN in that cell forever. `err_saturated` says which rows hit it.
    l2 = data["l2_rel"].to_numpy(dtype=float)
    data["err_saturated"] = ((~np.isfinite(l2)) | (l2 > ERR_CEIL)).astype(float)
    data["err_bits"] = np.log2(np.clip(np.nan_to_num(l2, nan=ERR_CEIL, posinf=ERR_CEIL),
                                       ERR_FLOOR, ERR_CEIL))
    # Rate metrics. With --stat mean an indicator column becomes a PROBABILITY per bit:
    # how often a flip is visible at all, next to how big the error is.
    slots = data[["correct", "degraded", "corrupted", "failed"]].sum(axis=1)
    data["frac_bad"] = (data["degraded"] + data["corrupted"] + data["failed"]) / slots
    data["frac_failed"] = data["failed"] / slots
    data["is_sdc"] = ((data["corrupted"] + data["failed"]) > 0).astype(float)
    data["is_masked"] = (data["correct"] == slots).astype(float)
    data["detected"] = data["detected"].astype(float)            # OpenFHE SDC detector
    data["misclassified"] = data["misclassified"].astype(float)  # NN workloads only
    data["out_of_range"] = data["out_of_range"].astype(float)    # OpenFHE only
    # Detector outcome vs ground truth, for coverage / false-alarm tables (OpenFHE).
    data["sdc_undetected"] = ((data["is_sdc"] > 0) & (data["detected"] == 0)).astype(float)
    data["false_alarm"] = ((data["is_sdc"] == 0) & (data["detected"] > 0)).astype(float)
    # NN: the class did not change but the logits moved by more than MOVED_PCT (the
    # "tolerable SDC" of nn_sdc_curve.py). Per injection, so it survives the collapse.
    moved = ~(data["linf_rel"].astype(float) * 100.0 <= MOVED_PCT)    # NaN counts as moved
    data["tolerable_sdc"] = (moved & (data["misclassified"] == 0)).astype(float)
    return data


def load_data(camps, results_dir):
    """Rows of the selected campaigns / experiments, with config_id.

    raw: one row per injection (all seeds), plus seed / seed_input.
    collapsed: one row per (limb, coeff, bit), seeds already averaged (n_seeds says how many).
    """
    results_dir = Path(results_dir)
    if is_collapsed(camps):
        dfs = []
        for _, c in camps.iterrows():
            df = pd.read_csv(results_dir / c["data_file"])
            df["experiment_id"] = c["experiment_id"]
            df["config_id"] = c["config_id"]
            dfs.append(df)
        return pd.concat(dfs, ignore_index=True)

    dfs = []
    for cid in camps["campaign_id"]:
        df = pd.read_csv(results_dir / "data" / f"campaign_{int(cid):06d}.csv.gz")
        df["campaign_id"] = int(cid)
        dfs.append(df)
    data = add_derived(pd.concat(dfs, ignore_index=True))
    return data.merge(camps[["campaign_id", "config_id", "seed", "seed_input"]], on="campaign_id")

def load_reps(camps, results_dir):
    """Per-repetition curves of collapsed experiments: one row per (campaign_id, bit), each
    metric averaged over the coefficients of that single campaign (bit_curve --rep_spread)."""
    return pd.concat([pd.read_csv(Path(results_dir) / reps_file(c["data_file"]))
                      for _, c in camps.iterrows()], ignore_index=True)


def reps_file(data_file):
    """data/experiment_<id>.csv.gz -> data/experiment_<id>_reps.csv.gz"""
    return str(data_file).replace(".csv.gz", "_reps.csv.gz")

def n_repetitions(camps):
    """How many campaigns (seed x seed_input) are behind these rows, in either layout."""
    return int(camps["n_campaigns"].sum()) if is_collapsed(camps) else len(camps)


def parse_value(v):
    """CLI value -> int, float or str. Shared by the plotting scripts."""
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    return v
