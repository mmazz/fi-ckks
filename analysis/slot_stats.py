#!/usr/bin/env python3
"""How many slots does a visible fault damage? Numbers for the slot-spread section.

Reads the RAW data (one row per injection), because "exactly one slot" cannot be recovered
from the collapsed cache, where the seeds are already averaged. Each campaign file is read
on its own and only counted, so it works on the full results dirs.

Per injection, with n slots and a threshold on the per-slot relative error (--threshold):
  visible   at least one slot above the threshold
  all       every slot above it
  some      at least one, but not all
  one       exactly one slot above it
The pct_all / pct_some / pct_one columns are percentages of the VISIBLE faults, so they also
depend on how many bits above the threshold the campaign sweeps (logQ, bitsPerCoeff). The
sweep-independent number is band_bits: per coefficient, how many flipped bits leave only
SOME slots above the threshold (median over coefficients; exhaustive campaigns only).
crest = median of linf_abs * sqrt(n) / l2_abs over the visible faults: ~1.41 when every slot
gets the same error (a cosine), sqrt(n) when it all sits in one slot.

--l2 adds a second table: the injections whose l2_rel is close to 10^-2, 10^-1, 1 and 10
(within +-L2_HALF_WIDTH decades), and for them the mean fraction of slots above 1 % and
above 10 %, and how often EVERY slot is above them. It backs up "once l2_rel is ten times a
threshold, more than 90 % of the slots are above it".

Examples (from analysis/):
  python3 slot_stats.py ../results_client ../results_server       # one total per dir + per stage
  python3 slot_stats.py ../results_client --by stage logMin logMax # input range control
  python3 slot_stats.py ../results_server --by stage op_step       # per internal step
  python3 slot_stats.py ../results_client --threshold 10 --where library=heaan
  python3 slot_stats.py ../results_client ../results_server --l2   # slots vs l2_rel
"""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
from utils.results import load_campaigns, parse_value  # noqa: E402

COUNTS = ["correct", "degraded", "corrupted", "failed"]
L2_DECADES = [-2, -1, 0, 1]     # log10 of the l2_rel values of the --l2 table
L2_HALF_WIDTH = 0.1             # decades on each side: 10^-1 means [10^-1.1, 10^-0.9)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("results", nargs="+", help="raw results dirs (the ones the C++ writes)")
    p.add_argument("--by", nargs="*", default=["library", "stage"],
                   help="campaign columns to group by (default: library stage)")
    p.add_argument("--threshold", type=int, choices=[1, 10], default=1,
                   help="per-slot relative error, in %%")
    p.add_argument("--where", nargs="*", default=[], metavar="COL=VAL",
                   help="keep only the campaigns with these exact values")
    p.add_argument("--exhaustive_only", action="store_true",
                   help="skip the random campaigns")
    p.add_argument("--l2", action="store_true",
                   help="also print the fraction of slots above 1 %% / 10 %% per l2_rel value")
    return p.parse_args()


def select(camps, args):
    for w in args.where:
        col, val = w.split("=", 1)
        camps = camps[camps[col] == parse_value(val)]
    if args.exhaustive_only:
        camps = camps[camps["isExhaustive"] == 1]
    # The same (config, seed, seed_input) twice (e.g. a rerun with --saveVectors) is the
    # same repetition: count it once, as the collapse does.
    return (camps.sort_values("campaign_id")
                 .drop_duplicates(["config_id", "seed", "seed_input"], keep="last"))


class Acc:
    """Counters of one group, plus the crest values of its visible faults."""
    def __init__(self):
        self.n = self.visible = self.all = self.some = self.one = 0
        self.crest = []
        self.band = []
        self.n_slots = set()

    def add(self, df, threshold, exhaustive):
        slots = df[COUNTS].sum(axis=1).to_numpy()
        over = (slots - df["correct"].to_numpy()) if threshold == 1 \
            else (df["corrupted"] + df["failed"]).to_numpy()
        vis = over > 0
        self.n += len(df)
        self.visible += int(vis.sum())
        self.all += int((vis & (over == slots)).sum())
        self.some += int((vis & (over < slots)).sum())
        self.one += int((vis & (over == 1) & (slots > 1)).sum())
        with np.errstate(divide="ignore", invalid="ignore"):
            crest = df["linf_abs"].to_numpy() * np.sqrt(slots) / df["l2_abs"].to_numpy()
        crest = crest[vis & np.isfinite(crest)]
        self.crest.append(crest.astype(np.float32))
        self.n_slots.update(np.unique(slots).tolist())
        if exhaustive:      # random campaigns sample a few bits: a band width means nothing
            some = pd.Series(vis & (over < slots), index=df.index)
            per_coeff = some.groupby([df["limb"], df["coeff"]]).sum()
            seen = pd.Series(vis, index=df.index).groupby([df["limb"], df["coeff"]]).any()
            self.band.append(per_coeff[seen].to_numpy())

    def row(self):
        v = max(self.visible, 1)
        crest = np.concatenate(self.crest) if self.crest else np.array([])
        return {"n_inj": self.n,
                "pct_visible": 100 * self.visible / max(self.n, 1),
                "pct_all": 100 * self.all / v,
                "pct_some": 100 * self.some / v,
                "pct_one": 100 * self.one / v,
                "crest": float(np.median(crest)) if crest.size else np.nan,
                "band_bits": float(np.median(np.concatenate(self.band))) if self.band else np.nan,
                "n_slots": ",".join(str(s) for s in sorted(self.n_slots))}


class L2Acc:
    """Slot fractions of the injections whose l2_rel falls in one L2_DECADES window."""
    def __init__(self):
        self.n = 0
        self.f1 = self.f10 = 0.0
        self.all1 = self.all10 = 0

    def add(self, df):
        slots = df[COUNTS].sum(axis=1).to_numpy()
        over1 = slots - df["correct"].to_numpy()
        over10 = (df["corrupted"] + df["failed"]).to_numpy()
        self.n += len(df)
        self.f1 += float((over1 / slots).sum())
        self.f10 += float((over10 / slots).sum())
        self.all1 += int((over1 == slots).sum())
        self.all10 += int((over10 == slots).sum())

    def row(self):
        n = max(self.n, 1)
        return {"n_inj": self.n,
                "pct_slots_over1": 100 * self.f1 / n,
                "pct_slots_over10": 100 * self.f10 / n,
                "pct_inj_all_over1": 100 * self.all1 / n,
                "pct_inj_all_over10": 100 * self.all10 / n}


def add_l2(l2groups, key, df):
    with np.errstate(divide="ignore", invalid="ignore"):
        lg = np.log10(df["l2_rel"].to_numpy(dtype=float))
    for k in L2_DECADES:
        sel = np.abs(lg - k) < L2_HALF_WIDTH         # NaN / inf / 0 never match
        if sel.any():
            l2groups[key + (f"1e{k}",)].add(df[sel])


def main():
    args = parse_args()
    for res in args.results:
        camps = select(load_campaigns(res, raw=True), args)
        missing = [c for c in args.by if c not in camps.columns]
        if missing:
            sys.exit(f"ERROR: unknown columns {missing}")
        total, groups, l2groups = Acc(), defaultdict(Acc), defaultdict(L2Acc)
        for i, (_, c) in enumerate(camps.iterrows(), 1):
            df = pd.read_csv(Path(res) / "data" / f"campaign_{int(c['campaign_id']):06d}.csv.gz",
                             usecols=["limb", "coeff"] + COUNTS + ["l2_abs", "linf_abs", "l2_rel"])
            exhaustive = int(c["isExhaustive"]) == 1
            total.add(df, args.threshold, exhaustive)
            key = tuple(c[k] for k in args.by)
            groups[key].add(df, args.threshold, exhaustive)
            if args.l2:
                add_l2(l2groups, key, df)
                add_l2(l2groups, ("TOTAL",) * len(args.by), df)
            if i % 200 == 0:
                print(f"  {res}: {i}/{len(camps)} campaigns", file=sys.stderr)

        table = pd.DataFrame([{**dict(zip(args.by, k)), **acc.row()}
                              for k, acc in sorted(groups.items(), key=lambda kv: str(kv[0]))])
        print(f"\n=== {res}  ({len(camps)} campaigns, threshold {args.threshold} %)")
        with pd.option_context("display.width", 220, "display.max_rows", 1000,
                               "display.float_format", "{:.2f}".format):
            print(table.to_string(index=False))
        t = total.row()
        print(f"TOTAL  visible faults: {total.visible} of {total.n} injections "
              f"({t['pct_visible']:.1f} %)\n"
              f"       damage every slot: {t['pct_all']:.1f} %   only some: {t['pct_some']:.1f} %"
              f"   exactly one: {t['pct_one']:.1f} %   median crest: {t['crest']:.2f}\n"
              f"       bits per coefficient with only some slots above it (median): "
              f"{t['band_bits']:.0f}")
        if args.l2:
            rank = {f"1e{k}": i for i, k in enumerate(L2_DECADES)}
            rows = [{**dict(zip(args.by + ["l2_rel"], k)), **acc.row()}
                    for k, acc in sorted(l2groups.items(),
                                         key=lambda kv: (str(kv[0][:-1]), rank[kv[0][-1]]))]
            print(f"\n--- slots above 1 % / 10 % for injections with l2_rel within "
                  f"+-{L2_HALF_WIDTH} decades of each value")
            with pd.option_context("display.width", 220, "display.max_rows", 1000,
                                   "display.float_format", "{:.1f}".format):
                print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
