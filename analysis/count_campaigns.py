#!/usr/bin/env python3
"""Count configurations and bit flips per backend (heaan, heaanNN, openfhe, openfheNN).

Reads <dir>/campaigns_start.csv (one row per campaign) and, for every campaign id,
looks up its row in <dir>/campaigns_end.csv to add up the injections.

Usage:
    python3 count_campaigns.py                       # results_server results_client results_NN
    python3 count_campaigns.py results_server results_NN
    python3 count_campaigns.py --id-col campaign_id --lib-col library --inj-col injections
"""
import argparse
import csv
import os
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

        for row in reader:
            cid = row[id_col].strip()
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
    print(f"[info] {d}: read")


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
    args = p.parse_args()

    totals = defaultdict(lambda: {"campaigns": 0, "configs": set(), "unfinished": 0,
                                  "injections": 0, "bits": 0})
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
if __name__ == "__main__":
    main()
