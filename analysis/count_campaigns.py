#!/usr/bin/env python3
"""Count configurations and bit flips per backend (heaan, heaanNN, openfhe, openfheNN).

Reads <dir>/campaigns_start.csv (one row per campaign) and, for every campaign id,
looks up its row in <dir>/campaigns_end.csv to add up the injections.

Usage:
    python3 count_campaigns.py                       # results_server results_client results_NN
    python3 count_campaigns.py results_server results_NN
    python3 count_campaigns.py --id-col campaign_id --lib-col library --inj-col injections
    python3 count_campaigns.py ../results_NN --where "stage=encode|encrypt_c0|encrypt_c1|decrypt_c0|decrypt_c1|decode"
    python3 count_campaigns.py ../results_NN --where "stage=decrypt_c0" --where "withNTT=0" --detected  --err-thr 1e-1
"""
import argparse
import csv
import os
import gzip
import math
import sys
from collections import defaultdict

DEFAULT_DIRS = ["results_server", "results_client", "results_NN"]

# Candidate column names, tried in order (case-insensitive).
ID_CANDIDATES = ["campaign_id", "id", "campaign"]
LIB_CANDIDATES = ["library", "lib", "backend", "binary"]
INJ_CANDIDATES = ["total_bitflips", "injections", "num_injections", "n_injections",
                  "total_injections"]
BITS_CANDIDATES = ["amountbits", "amount_bits", "nbits"]

# Columns that only change between repetitions of the same configuration.
DEFAULT_IGNORE = ["seed", "seed_input"]

GROUPS = ["heaan", "heaanNN", "openfhe", "openfheNN"]
def parse_filters(exprs):
    """Parse --where expressions 'col=v1,v2' or 'col!=v1,v2' into (col, negate, values)."""
    filters = []
    for e in exprs:
        if "!=" in e:
            col, vals = e.split("!=", 1)
            negate = True
        elif "=" in e:
            col, vals = e.split("=", 1)
            negate = False
        else:
            sys.exit(f"[error] bad --where '{e}', expected col=value or col!=value")
        # '|' separates alternative values, so values may contain commas.
        values = {v.strip().lower() for v in vals.split("|")}
        filters.append((col.strip(), negate, values))
    return filters

def find_col(header, candidates, override, what, path, required=True):
    """Return the real column name in header for the given candidates (or the override)."""
    lower = {h.lower(): h for h in header}
    if override:
        if override.lower() in lower:
            return lower[override.lower()]
        sys.exit(f"[error] {path}: column '{override}' not found. Columns: {header}")
    for c in candidates:
        if c in lower:
            return lower[c]
    if required:
        sys.exit(f"[error] {path}: no {what} column (tried {candidates}). "
                 f"Columns: {header}\nPass it with the matching --*-col option.")
    return None


def classify(lib_value, dirname):
    """Map a library value (and the results directory) to one of GROUPS."""
    v = lib_value.lower()
    if "openfhe" in v or "ofhe" in v:
        base = "openfhe"
    elif "heaan" in v:
        base = "heaan"
    else:
        return None
    is_nn = "nn" in v.replace("openfhe", "").replace("heaan", "") or "nn" in dirname.lower()
    return base + ("NN" if is_nn else "")


def read_end(path, args):
    """Return {campaign_id: injections} from campaigns_end.csv (last row wins)."""
    end = {}
    dup = 0
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        id_col = find_col(reader.fieldnames, ID_CANDIDATES, args.id_col, "id", path)
        inj_col = find_col(reader.fieldnames, INJ_CANDIDATES, args.inj_col, "injections", path)
        for row in reader:
            cid = row[id_col].strip()
            try:
                n = int(float(row[inj_col]))
            except (ValueError, TypeError):
                print(f"[warn] {path}: campaign {cid} has a non-numeric injection count "
                      f"'{row[inj_col]}', skipped")
                continue
            if cid in end:
                dup += 1
            end[cid] = n
    if dup:
        print(f"[warn] {path}: {dup} repeated ids, kept the last row of each")
    return end
TRUE_VALUES = {"1", "1.0", "true", "yes", "y", "t"}

def count_detected(path, det_col, err_col=None, thr=None):
    """Return per-file counts (rows, detected, and detected/undetected split by an
    error threshold), or None if the file is unusable."""
    if not os.path.isfile(path):
        return None
    c = {"rows": 0, "det": 0, "det_lo": 0, "det_hi": 0, "und_lo": 0, "und_hi": 0}
    try:
        with gzip.open(path, "rt", newline="") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
            col = find_col(fields, [det_col.lower()], None, "detected", path, required=False)
            if col is None:
                print(f"[warn] {path}: no '{det_col}' column, skipped")
                return None
            ecol = None
            if thr is not None:
                ecol = find_col(fields, [err_col.lower()], None, "error", path, required=False)
                if ecol is None:
                    print(f"[warn] {path}: no '{err_col}' column, skipped")
                    return None
            for row in reader:
                c["rows"] += 1
                is_det = row[col].strip().lower() in TRUE_VALUES
                if is_det:
                    c["det"] += 1
                if ecol is None:
                    continue
                try:
                    err = float(row[ecol])
                except (ValueError, TypeError):
                    err = math.nan
                # NaN/inf count as above the threshold (the output is broken anyway).
                hi = math.isnan(err) or err >= thr
                c[("det_" if is_det else "und_") + ("hi" if hi else "lo")] += 1
    except (OSError, EOFError) as e:
        print(f"[warn] {path}: unreadable ({e}), skipped")
        return None
    return c


def process_dir(d, args, totals):
    start_path = os.path.join(d, "campaigns_start.csv")
    end_path = os.path.join(d, "campaigns_end.csv")
    if not os.path.isfile(start_path):
        print(f"[warn] {start_path} not found, directory skipped")
        return
    end = read_end(end_path, args) if os.path.isfile(end_path) else {}
    if not end:
        print(f"[warn] {end_path} missing or empty: no bit flips counted for {d}")

    ignore = {c.lower() for c in args.ignore_cols.split(",") if c}
    with open(start_path, newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        id_col = find_col(header, ID_CANDIDATES, args.id_col, "id", start_path)
        lib_col = find_col(header, LIB_CANDIDATES, args.lib_col, "library", start_path)
        bits_col = find_col(header, BITS_CANDIDATES, args.bits_col, "amountBits",
                            start_path, required=False)
        cfg_cols = [h for h in header if h != id_col and h.lower() not in ignore]
        # Resolve filter columns against this file's header (case-insensitive).
        filters = [(find_col(header, [], col, "filter", start_path), neg, vals)
                   for col, neg, vals in args.filters]
        filtered_out = 0
        for row in reader:
            cid = row[id_col].strip()
            # Keep the row only if every --where condition holds.
            if not all((row[c].strip().lower() in vals) != neg for c, neg, vals in filters):
                filtered_out += 1
                continue
            group = classify(row[lib_col], os.path.basename(os.path.normpath(d)))
            if group is None:
                print(f"[warn] {start_path}: campaign {cid} has unknown library "
                      f"'{row[lib_col]}', skipped")
                continue
            t = totals[group]
            t["campaigns"] += 1
            # Configuration key: dir + every parameter except id and repetition seeds.
            t["configs"].add((d,) + tuple(row[c] for c in cfg_cols))
            if cid not in end:
                t["unfinished"] += 1
                continue
            n = end[cid]
            t["injections"] += n
            k = 1
            if bits_col:
                try:
                    k = max(1, int(float(row[bits_col])))
                except (ValueError, TypeError):
                    k = 1
            t["bits"] += n * k
            if args.detected:
                # Per-campaign data file: <dir>/data/<6-digit id>.csv.gz
                data_path = os.path.join(d, "data", f"campaign_{cid.zfill(6)}.csv.gz")
                res = count_detected(data_path, args.det_col, args.err_col, args.err_thr)
                if res is None:
                    t["det_missing"] += 1
                else:
                    t["det_rows"] += res["rows"]
                    t["det_hits"] += res["det"]
                    if res["det"] > 0:
                        t["det_campaigns"] += 1
                    for k in ("det_lo", "det_hi", "und_lo", "und_hi"):
                        t[k] += res[k]

    print(f"[info] {d}: read ({filtered_out:,} campaigns filtered out by --where)")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("dirs", nargs="*", default=DEFAULT_DIRS)
    p.add_argument("--id-col", default=None)
    p.add_argument("--lib-col", default=None)
    p.add_argument("--inj-col", default=None)
    p.add_argument("--bits-col", default=None, help="bits flipped per injection (multibit)")
    p.add_argument("--ignore-cols", default=",".join(DEFAULT_IGNORE),
                   help="comma-separated columns ignored when grouping configurations")
    p.add_argument("--where", action="append", default=[],
                   help="filter campaigns: 'col=v1,v2' or 'col!=v' (repeatable, all must hold)")
    p.add_argument("--detected", action="store_true",
                   help="also count detected rows from <dir>/data/<id>.csv.gz")
    p.add_argument("--det-col", default="detected",
                   help="name of the detection column in the data files")
    p.add_argument("--err-thr", type=float, default=None,
                   help="error threshold: split rows into below/above (implies --detected)")
    p.add_argument("--err-col", default="l2_rel",
                   help="error column compared against --err-thr")
    args = p.parse_args()
    args.filters = parse_filters(args.where)
    if args.err_thr is not None:
        args.detected = True
    totals = defaultdict(lambda: {"campaigns": 0, "configs": set(), "unfinished": 0,
                                  "injections": 0, "bits": 0,
                                  "det_rows": 0, "det_hits": 0,
                                  "det_lo": 0, "det_hi": 0, "und_lo": 0, "und_hi": 0,
                                  "det_campaigns": 0, "det_missing": 0})
    for d in args.dirs:
        process_dir(d, args, totals)

    print()
    print(f"{'group':<11}{'campaigns':>11}{'configs':>10}{'unfinished':>12}"
          f"{'injections':>15}{'bits flipped':>15}")
    grand = {"campaigns": 0, "configs": 0, "unfinished": 0, "injections": 0, "bits": 0}
    for g in GROUPS:
        t = totals[g]
        nconf = len(t["configs"])
        print(f"{g:<11}{t['campaigns']:>11,}{nconf:>10,}{t['unfinished']:>12,}"
              f"{t['injections']:>15,}{t['bits']:>15,}")
        grand["campaigns"] += t["campaigns"]
        grand["configs"] += nconf
        grand["unfinished"] += t["unfinished"]
        grand["injections"] += t["injections"]
        grand["bits"] += t["bits"]
    print("-" * 74)
    print(f"{'total':<11}{grand['campaigns']:>11,}{grand['configs']:>10,}"
          f"{grand['unfinished']:>12,}{grand['injections']:>15,}{grand['bits']:>15,}")

    for base in ("heaan", "openfhe"):
        a, b = totals[base], totals[base + "NN"]
        print(f"\n{base} + {base}NN: {a['campaigns'] + b['campaigns']:,} campaigns, "
              f"{len(a['configs']) + len(b['configs']):,} configurations, "
              f"{a['injections'] + b['injections']:,} injections, "
              f"{a['bits'] + b['bits']:,} bits flipped")

    print(f"\nheaan + openfhe (NN included): {grand['campaigns']:,} campaigns, "
          f"{grand['configs']:,} configurations, {grand['injections']:,} injections, "
          f"{grand['bits']:,} bits flipped")
    if args.detected:
        print()
        print(f"{'group':<11}{'rows':>12}{'detected':>12}{'det %':>8}"
              f"{'campaigns w/ det':>18}{'no data file':>14}")
        for g in GROUPS:
            t = totals[g]
            pct = 100 * t["det_hits"] / t["det_rows"] if t["det_rows"] else 0.0
            print(f"{g:<11}{t['det_rows']:>12,}{t['det_hits']:>12,}{pct:>7.1f}%"
                  f"{t['det_campaigns']:>18,}{t['det_missing']:>14,}")
        if args.err_thr is not None:
            print(f"\n{args.err_col} threshold = {args.err_thr:g}  "
                  f"(below: < thr, above: >= thr or NaN)")
            print(f"{'group':<11}{'det below':>12}{'det above':>12}"
                  f"{'undet below':>13}{'undet above':>13}")
            for g in GROUPS:
                t = totals[g]
                print(f"{g:<11}{t['det_lo']:>12,}{t['det_hi']:>12,}"
                      f"{t['und_lo']:>13,}{t['und_hi']:>13,}")


if __name__ == "__main__":
    main()
