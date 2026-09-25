"""Collapse the repetitions of every experiment into ONE csv (a cache of the raw dir).

An experiment is a configuration. Its repetitions are the finished campaigns that only
differ in seed / seed_input (or saveVectors). Each experiment gets one file with one row
per (limb, coeff, bit), averaged over its repetitions, and an index that points to it:

    <out>/campaigns_start.csv            one row per experiment: its config, data_file and
                                         which campaigns went in (campaign_ids, seeds, ...)
    <out>/data/experiment_<id>.csv.gz    one row per (limb, coeff, bit)

Coefficients are NOT averaged here (gap vs no-gap, register maps and flat curves need
them): that happens when plotting. The raw dir is never modified: the C++ registry matches
whole lines of its campaigns_start.csv, so an extra column there would rerun everything.
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .results import add_derived, config_columns, is_collapsed, load_campaigns

COLLAPSED_DIR = "collapsed"
CELL = ["limb", "coeff", "bit"]
# Averaged over the repetitions of each cell. The names are the raw ones, so --metric
# means the same thing on a raw and on a collapsed dir.
MEAN_COLS = ["l2_abs", "l2_rel", "linf_abs", "linf_rel", "err_bits", "err_saturated",
             "frac_bad", "frac_failed", "is_sdc", "is_masked", "detected", "misclassified",
             "out_of_range", "sdc_undetected", "false_alarm"]


def collapse_cells(data):
    """One row per (limb, coeff, bit). A single inf repetition makes the mean inf, the same
    as averaging the seeds on the fly did; err_bits is clipped, so it stays finite."""
    g = data.groupby(CELL, sort=True)
    out = g[MEAN_COLS].mean()
    out.insert(0, "n_seeds", g.size())
    out["err_bits_std"] = g["err_bits"].std(ddof=0)
    out["l2_rel_median"] = g["l2_rel"].median()      # register_map.py --stat median / max
    out["linf_rel_median"] = g["linf_rel"].median()
    out["linf_rel_max"] = g["linf_rel"].max()
    return out.reset_index()


def index_row(exp_id, camps, data, data_file):
    """The experiment's row in <out>/campaigns_start.csv."""
    row = camps.iloc[0][config_columns(camps)].to_dict()
    l2 = data["l2_rel"].to_numpy(dtype=float)
    l2 = l2[np.isfinite(l2)]
    row.update(
        experiment_id=exp_id,
        data_file=data_file,
        n_campaigns=len(camps),
        campaign_ids=campaign_ids(camps),
        seeds=";".join(map(str, sorted(camps["seed"].unique()))),
        seed_inputs=";".join(map(str, sorted(camps["seed_input"].unique()))),
        total_bitFlips=len(data),
        duration_minutes=int(camps["duration_minutes"].sum()),
        # Over every injection of every repetition, finite values only (like the C++).
        l2_P95=float(np.percentile(l2, 95)) if l2.size else 0.0,
        l2_P99=float(np.percentile(l2, 99)) if l2.size else 0.0,
        sdc_rate=float(data["is_sdc"].mean()),
        detected_rate=float(data["detected"].mean()),
    )
    return row


def campaign_ids(camps):
    return ";".join(map(str, sorted(int(c) for c in camps["campaign_id"])))


def read_campaign(raw_dir, cid):
    df = pd.read_csv(Path(raw_dir) / "data" / f"campaign_{int(cid):06d}.csv.gz")
    df["campaign_id"] = int(cid)
    return df

def write_atomic(df, path, **to_csv_kw):
    """Two plotting processes may refresh the cache at the same time (make -j): each one
    writes a private temp file and renames it, so a reader never sees half a file."""
    tmp = path.with_name(f".{os.getpid()}.{path.name}")    # same suffix: to_csv still gzips
    df.to_csv(tmp, index=False, **to_csv_kw)
    os.replace(tmp, path)



def collapse_dir(raw, out=None, force=False, verbose=True):
    """Bring <out> (default <raw>/collapsed) up to date with the finished campaigns of <raw>.

    Only experiments whose set of finished campaigns changed are re-read and rewritten, so
    when nothing changed this only reads the two registry CSVs. Returns the <out> path.
    """
    raw = Path(raw)
    out = Path(out) if out else raw / COLLAPSED_DIR
    (out / "data").mkdir(parents=True, exist_ok=True)
    log = print if verbose else (lambda *a, **k: None)

    camps = load_campaigns(raw, raw=True)
    if is_collapsed(camps):
        raise ValueError(f"{raw} is already a collapsed dir")
    # The same (seed, seed_input) twice in one experiment (e.g. rerun with --saveVectors 1)
    # is the same repetition: keep one, or it would weigh double in the mean.
    camps = (camps.sort_values("campaign_id")
                  .drop_duplicates(["config_id", "seed", "seed_input"], keep="last"))

    index_path = out / "campaigns_start.csv"
    old = {}
    if index_path.exists() and not force:
        prev = pd.read_csv(index_path, keep_default_na=False)
        old = {r["experiment_id"]: r for r in prev.to_dict("records")}

    rows, written = [], 0
    for exp_id, group in camps.groupby("config_id", sort=False):
        data_file = f"data/experiment_{exp_id}.csv.gz"
        prev = old.get(exp_id)
        if (prev is not None and str(prev["campaign_ids"]) == campaign_ids(group)
                and (out / data_file).exists()):
            rows.append(prev)
            continue
        data = add_derived(pd.concat([read_campaign(raw, c) for c in group["campaign_id"]],
                                     ignore_index=True))
        cells = collapse_cells(data)
        if cells["n_seeds"].nunique() > 1:     # random campaigns sampled different coeffs
            log(f"  {exp_id}: cells have {cells['n_seeds'].min()}..{cells['n_seeds'].max()} "
                f"repetitions (random campaign: the sampled coefficients depend on the seed)")
        # Seed averages: 8 significant digits are far below the seed-to-seed spread and
        # halve the file (full-precision means barely compress).
        write_atomic(cells, out / data_file, float_format="%.8g")
        rows.append(index_row(exp_id, group, data, data_file))
        written += 1

    if written == 0 and len(rows) == len(old):
        return out                              # cache already up to date: touch nothing

    index = pd.DataFrame(rows)
    first = ["experiment_id", "data_file", "n_campaigns"]
    index = index[first + [c for c in index.columns if c not in first]]
    write_atomic(index.sort_values(["library", "stage", "experiment_id"]), index_path)

    keep = set(index["data_file"])
    for p in (out / "data").glob("experiment_*.csv.gz"):
        if f"data/{p.name}" not in keep:
            p.unlink()
    log(f"[collapse] {written} experiment(s) updated, {len(index)} in total -> {out}")
    return out
