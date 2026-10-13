#!/usr/bin/env python3
"""Every number the thesis quotes from the data, computed in one place.

    python3 thesis_numbers.py --client RES1 --server RES2 --burst RES_BURST --nn RES_NN \\
        [--out numbers.txt] [--only 6 7]

Writes one text file with a section per thesis chapter (4 to 8). Every number has an ID
(7.8.3 = third number of section 7.8), its value with a decimal comma as in the text, and
every section says which configuration and which statistic the numbers come from; tables
are printed as tables. The numbers that already have their own script (master_curve.py,
analytic_baseline.py, theory_check.py, nn_table.py) are included as that script prints
them. Also run by `make numbers`.

Definitions shared by every section (Chapter 4 of the thesis):
  E_L2 curve   per (limb, coeff, bit) cell the median over the repetitions (l2_rel_median),
               then the median over the coefficients of the subset: aligned (coeff % gap
               == 0, the ones the decode reads), other (the rest) or all.
               The figures (bit_curve.py) draw mean and mean instead: where a number of the
               text depends on that choice, the section prints both.
  visible      E_L2 > 1e-2. "a-b" = first and last bit where the curve is visible.
  MREP         same curve with linf_rel_median (worst slot), visible above 1 %.
  P(SDC)       is_sdc (some slot > 10 %) averaged over repetitions and coefficients per
               bit, then over every bit of the module [0, W), interpolating the sampled bits
               of random campaigns. W = log q_l of the value at the injection point, plus
               log Q for the values of a key switching, plus log Q for the HEAAN encode.
  bits         "bit" is always the bit of the coefficient where the flip starts.

A configuration missing from the release prints MISSING instead of a number, so the script
runs on any release (older ones lack some campaigns). The script only computes: it holds no
expected value, so comparing with the text is done by reading the output.
"""
import argparse
import datetime
import math
import subprocess
import sys
import textwrap
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.append(str(HERE))
from utils.results import load_campaigns            # noqa: E402
from analytic_baseline import predict, rms_x         # noqa: E402
from bit_curve import boot_cutoff_bit, level_logq    # noqa: E402

TAU = 1e-2          # visible: E_L2 above this
MREP_PCT = 1.0      # MREP visible above this (%), the Correct / Degraded border
H = 4               # Hamming weight of s for logN = 6 (HEAAN)
H_NN = 64           # Hamming weight of s in the network (logN = 12)
SIGMA_E = 1.6       # std of the fresh noise per coefficient (HEAAN, encryption shifted by logQ)
SQRT2 = math.sqrt(2)

# ======================================================================================
# Configurations: the same ones as the Makefile, one per campaign group
# ======================================================================================
BASE = dict(library="heaan", logN=6, logSlots=5, logQ=60, logDelta=40)
NULL40 = BASE | dict(pipeline="", bitsPerCoeff=64, logMin=0, logMax=0)
CLIENT_MUL = dict(library="heaan", logN=6, logSlots=3, logQ=150, logDelta=30, bitsPerCoeff=170)
OFHE = dict(library="openfhe", logN=6, logQ=60, logDelta=30, bitsPerCoeff=64)
BOOTP = dict(library="heaan", logN=6, logSlots=3, logQ=840, logDelta=40, bitsPerCoeff=860)
SERVER = dict(library="heaan", logN=6, logSlots=3, logQ=60, logDelta=30)

OP_ADD = SERVER | dict(bitsPerCoeff=64, stage="add", pipeline="add x2", op_depth=1)
OP_PMUL = SERVER | dict(logQ=120, bitsPerCoeff=124, stage="pmul", pipeline="pmul x2", op_depth=1)
OP_MUL = SERVER | dict(bitsPerCoeff=124, stage="mul", pipeline="mul")
OP_RESCALE = SERVER | dict(logQ=100, bitsPerCoeff=110, stage="rescale", pipeline="mul x2")
OP_ROT = SERVER | dict(bitsPerCoeff=124, stage="rot", pipeline="rot 2")
OP_MUL_DEPTH = SERVER | dict(logQ=160, bitsPerCoeff=324, stage="mul", pipeline="mul x3")
OP_PMUL_NT = OP_PMUL | dict(stage="pmul_non_transient")
OP_MUL_NT = OP_MUL | dict(stage="mul_non_transient")
OP_ROT_NT = OP_ROT | dict(stage="rot_non_transient")
MIX = "add; mul; rot 2; mul; add"
OP_MIX = BOOTP | dict(numSamples=50, stage="mul", pipeline=MIX)
OP_MIX_BOOT = BOOTP | dict(numSamples=50, stage="mul", pipeline=MIX + "; boot")
OP_BOOT = BOOTP | dict(stage="boot", pipeline="mul x4; boot")
OP_BOOT_EVAL = BOOTP | dict(logSlots=2, stage="boot_eval", pipeline="mul x4; boot")

# Values of a key switching live mod q_l * Q: W = log q_l + log Q (read in Scheme.cpp of
# the HEAAN fork; the numbering is the same in the read and the persistent fault models).
KS_STEPS = {"mul": range(10, 16), "mul_non_transient": range(10, 16),
            "rot": range(2, 8), "rot_non_transient": range(2, 8)}
# Steps after the shift of a rescale: one logDelta less than before it.
AFTER_SHIFT = {"rescale": (2, 3)}
# What each op_step flips (read in Scheme.cpp of the HEAAN fork). The mul has its own
# algorithm in the thesis; its steps are not labelled here.
STEP_LABELS = {
    "add": ["c1 of operand 1", "c1 of operand 2", "c0 of operand 1", "c0 of operand 2",
            "output c1", "output c0"],
    "pmul": ["c1", "p read with c1", "c0", "p read with c0", "output c1", "output c0"],
    "rescale": ["c1 before shift", "c0 before shift", "c1 after shift", "c0 after shift"],
    "rot": ["c0 before phi_r", "c1 before phi_r", "rotated c1 read for k1", "k1",
            "rotated c1 read for k0", "k0", "u1 before shift", "u0 before shift",
            "u0 after shift", "rotated c0", "output c0", "output c1"],
    "boot": ["c1 after SubSum", "c0 after SubSum", "c1 after /(N/2)", "c0 after /(N/2)",
             "c1 after CoeffToSlot", "c0 after CoeffToSlot", "c1 after EvalExp",
             "c0 after EvalExp"],
}
STEP_LABELS["pmul_non_transient"] = STEP_LABELS["pmul"]
STEP_LABELS["rot_non_transient"] = STEP_LABELS["rot"]


# ======================================================================================
# Formatting
# ======================================================================================
def isnum(x):
    return x is not None and not (isinstance(x, (float, np.floating)) and np.isnan(x))


def fnum(x, nd=2):
    """Decimal comma, as in the text: 0.734 -> '0,73'. None / NaN -> '-'."""
    if not isnum(x):
        return "-"
    if np.isinf(x):
        return "inf" if x > 0 else "-inf"
    return f"{x:.{nd}f}".replace(".", ",")


def fsci(x, nd=1):
    """2.26e18 -> '2,3e18', 0 -> '0'."""
    if not isnum(x):
        return "-"
    if np.isinf(x):
        return "inf"
    if x == 0:
        return "0"
    mant, exp = f"{x:.{nd}e}".split("e")
    return f"{mant.replace('.', ',')}e{int(exp)}"


def fint(n):
    """27459816 -> '27.459.816'."""
    return f"{int(n):,}".replace(",", ".")


def frange(r):
    return "none" if r is None else f"{r[0]}-{r[1]}"


def fbit(b):
    """A bit or '-' when there is none (bit 0 is a bit, not a missing value)."""
    return "-" if b is None else str(b)


def describe(e, extra=()):
    """One line with the configuration of an experiment."""
    keys = ["library", "stage", "pipeline", "logN", "logQ", "logDelta", "logSlots",
            "bitsPerCoeff", *extra]
    parts = [f"{k}={e[k]!r}" if k == "pipeline" else f"{k}={e[k]}" for k in keys]
    if int(e["logMin"]) or int(e["logMax"]):
        parts.append(f"inputs=[2^{e['logMin']},2^{e['logMax']}]")
    sampling = "exhaustive" if int(e["isExhaustive"]) else f"random {e['numSamples']} coeffs"
    return " ".join(parts) + f"  [{e['n_campaigns']} reps, {sampling}]"


def fdict(f):
    return " ".join(f"{k}={v!r}" if isinstance(v, str) else f"{k}={v}" for k, v in f.items())


# ======================================================================================
# Report
# ======================================================================================
class Report:
    """Numbers are numbered within their section (7.8.3 = third number of 7.8), so every
    line of the file has its own ID."""

    def __init__(self):
        self.out = []
        self.sid, self.count = "", 0

    def chapter(self, title):
        self.out += ["", "", "=" * 100, title, "=" * 100]

    def section(self, sid, title):
        self.sid, self.count = sid, 0
        self.out += ["", f"--- {sid}  {title} " + "-" * max(3, 92 - len(sid) - len(title))]

    def how(self, text):
        """How the numbers below are computed."""
        for line in textwrap.wrap(text, 92):
            self.out.append(f"    | {line}")

    def note(self, text):
        for i, line in enumerate(textwrap.wrap(text, 90)):
            self.out.append(("    note: " if i == 0 else "          ") + line)

    def num(self, value, what):
        self.count += 1
        self.out.append(f"  {f'{self.sid}.{self.count}':<8s} {value:>16s}   {what}")

    def missing(self, what):
        self.out.append(f"  MISSING  {what}")

    def table(self, header, rows):
        rows = [[str(c) for c in r] for r in rows]
        if not rows:
            self.out.append("    (no rows)")
            return
        width = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(header)]
        line = lambda cells: "    " + "  ".join(c.ljust(w) for c, w in zip(cells, width))
        self.out.append(line(header))
        self.out.append("    " + "  ".join("-" * w for w in width))
        self.out += [line(r) for r in rows]

    def raw(self, text):
        self.out += ["    " + line for line in text.splitlines()]

    def text(self):
        return "\n".join(self.out) + "\n"


# ======================================================================================
# Data
# ======================================================================================
class Release:
    """The four parts of a release (or raw results dirs), one experiment per row."""

    def __init__(self, dirs):
        self.dirs, self.camps, self._cells = {}, {}, {}
        for part, d in dirs.items():
            if d is None:
                continue
            d = Path(d).resolve()
            if not (d / "campaigns_start.csv").exists():
                print(f"WARNING: {d} has no campaigns_start.csv: part '{part}' skipped",
                      file=sys.stderr)
                continue
            self.dirs[part] = d
            self.camps[part] = load_campaigns(d)

    def find(self, part, query=None, **eq):
        """Experiments of `part` with column == value for every keyword, and the query."""
        if part not in self.camps:
            return pd.DataFrame()
        c = self.camps[part]
        mask = np.ones(len(c), dtype=bool)
        for k, v in eq.items():
            mask &= (c[k] == v).to_numpy()
        c = c[mask]
        return c.query(query) if query and len(c) else c

    def one(self, rep, part, query=None, **eq):
        """The single experiment that matches, or None (and a MISSING line in the report)."""
        c = self.find(part, query, **eq)
        what = f"{part}: {fdict(eq)}" + (f" and {query}" if query else "")
        if c.empty:
            rep.missing(what)
            return None
        if len(c) > 1:
            cols = [k for k in c.columns if k not in ("experiment_id", "data_file",
                    "campaign_ids", "seeds", "seed_inputs", "total_bitFlips", "duration_minutes",
                    "l2_P95", "l2_P99", "sdc_rate", "detected_rate", "config_id", "n_campaigns")
                    and c[k].astype(str).nunique() > 1]
            rep.missing(f"{what}: {len(c)} experiments, they differ in {cols}")
            return None
        return c.iloc[0]

    def cells(self, part, e):
        """One row per (limb, coeff, bit), repetitions already combined, plus `aligned`."""
        key = (part, e["experiment_id"])
        if key not in self._cells:
            d = pd.read_csv(self.dirs[part] / e["data_file"])
            N = 1 << int(e["logN"])
            gap = (N // 2) >> int(e["logSlots"])
            d["aligned"] = d["coeff"] % gap == 0
            self._cells[key] = d
        return self._cells[key]


def gap_of(e):
    return ((1 << int(e["logN"])) // 2) >> int(e["logSlots"])


def subset(d, which):
    if which == "al":
        return d[d["aligned"]]
    if which == "other":
        return d[~d["aligned"]]
    return d


def curve(d, which="al", col="l2_rel_median", stat="median"):
    """Per bit: `col` combined over the coefficients of the subset with `stat`."""
    x = subset(d, which)
    return x.groupby("bit")[col].agg(stat)


def first_last(c, thr=TAU):
    """First and last bit of a per-bit curve above thr, or None."""
    vals = c.to_numpy(dtype=float)
    hit = c.index[np.nan_to_num(vals, nan=-1.0, posinf=np.inf) > thr]
    return (int(hit.min()), int(hit.max())) if len(hit) else None


def first(c, thr=TAU):
    r = first_last(c, thr)
    return None if r is None else r[0]


def rate_per_bit(d, col="is_sdc"):
    """Per bit, the mean of a 0/1 column over every injection (cells weighted by n_seeds)."""
    w = d["n_seeds"]
    return ((d[col] * w).groupby(d["bit"]).sum() / w.groupby(d["bit"]).sum()).sort_index()


def interp_mean(series, lo, hi):
    """Mean over the integer bits [lo, hi) of a per-bit series, interpolating missing bits."""
    if series.empty or hi <= lo:
        return np.nan
    bits = np.arange(int(lo), int(hi))
    return float(np.interp(bits, series.index.to_numpy(dtype=float),
                           series.to_numpy(dtype=float)).mean())


def p_module(d, width, which="all", col="is_sdc", lo=0):
    """P(col) for a bit drawn uniformly from [lo, width) (interpolated over sampled bits)."""
    x = subset(d, which)
    if x.empty:
        return np.nan
    return interp_mean(rate_per_bit(x, col), lo, width)


def module_width(e):
    """(W, capped): bits of the module at the injection point of a server step. capped is
    True when W exceeds the bits that were injected (bitsPerCoeff) and was cut there."""
    W = level_logq(e)
    st, s = e["stage"], int(e["op_step"])
    if s in AFTER_SHIFT.get(st, ()):
        W -= int(e["logDelta"])
    if s in KS_STEPS.get(st, ()):
        W += int(e["logQ"])
    if W > int(e["bitsPerCoeff"]):
        return int(e["bitsPerCoeff"]), True
    return int(W), False


def bvis_raw(logd, rms):
    """Unrounded first visible bit of a fault added to a value at scale 2^logd (eq:bvis)."""
    return logd + math.log2(SQRT2 * TAU * rms)


def ceil_bit(x):
    return int(math.ceil(x - 1e-9))


def run_script(rep, args):
    """Run one of the analysis scripts and paste what it prints."""
    cmd = [sys.executable, str(HERE / args[0]), *args[1:]]
    rep.how("$ python3 " + " ".join(args))
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
    rep.raw(p.stdout.rstrip())
    if p.returncode:
        rep.raw(f"ERROR: exit {p.returncode}\n{p.stderr[-3000:]}")


# ======================================================================================
# Sections. Each one: f(rel, rep, args). @section(n) puts it in chapter n.
# ======================================================================================
SECTIONS = []
CHAPTERS = {4: "Chapter 4 - Methodology: volume of the campaigns and sample sizes",
            5: "Chapter 5 - Analytical model: rules vs. data",
            6: "Chapter 6 - Client: representations, pipelines, bootstrapping, bursts",
            7: "Chapter 7 - Server: faults inside the operations",
            8: "Chapter 8 - Application: encrypted neural network"}


def section(chapter):
    def deco(f):
        SECTIONS.append((chapter, f))
        return f
    return deco


# --------------------------------------------------------------------------------------
# Chapter 4
# --------------------------------------------------------------------------------------
@section(4)
def ch4_volume(rel, rep, args):
    rep.section("4.1", "Volume of the release (tab:campanias)")
    rep.how("Per part and library: experiments = configurations (one row of the collapsed "
            "index), campaigns = repetitions (seed x seed_input) behind them, injections = "
            "total_bitFlips, hours = duration_minutes / 60 (compute time of the campaigns).")
    rows, tot = [], np.zeros(4)
    for part, c in rel.camps.items():
        for lib, g in c.groupby("library"):
            v = np.array([len(g), g["n_campaigns"].sum(), g["total_bitFlips"].sum(),
                          g["duration_minutes"].sum() / 60])
            tot += v
            rows.append([part, lib, fint(v[0]), fint(v[1]), fint(v[2]), fint(v[3])])
    rows.append(["total", "", fint(tot[0]), fint(tot[1]), fint(tot[2]), fint(tot[3])])
    rep.table(["part", "library", "experiments", "campaigns", "injections", "hours"], rows)

    rep.section("4.2", "Repetitions per experiment")
    rep.how("n_campaigns = repetitions (seed x seed_input) of one configuration: how many "
            "experiments have each value, per part.")
    rows = []
    for part, c in rel.camps.items():
        counts = c["n_campaigns"].value_counts().sort_index()
        rows.append([part, ", ".join(f"{n} reps: {k}" for n, k in counts.items())])
    rep.table(["part", "experiments per number of repetitions"], rows)
    for part, c in rel.camps.items():
        seeds = sorted({s for v in c["seeds"].astype(str) for s in v.split(";")})
        inputs = sorted({s for v in c["seed_inputs"].astype(str) for s in v.split(";")})
        rep.num(f"{len(seeds)} / {len(inputs)}",
                f"{part}: distinct key seeds / input seeds over the whole part")

    rep.section("4.3", "Injections behind one point of a curve, and the 95 % half-width")
    rep.how("n = injections per bit (every repetition and coefficient of the subset; the "
            "minimum over the bits). For a proportion estimated from n injections the 95 % "
            "half-width is at most 1.96 * sqrt(1/4 / n) = 0.98 / sqrt(n).")
    cases = [("client, no ops, 625 reps (c0)", "client", NULL40 | dict(stage="encrypt_c0")),
             ("client, no ops, 8 reps (c0, logDelta 25)", "client",
              NULL40 | dict(stage="encrypt_c0", logDelta=25)),
             ("client, mul (c0)", "client", CLIENT_MUL | dict(stage="encrypt_c0", pipeline="mul")),
             ("client, mul x4; boot (c0)", "client",
              BOOTP | dict(stage="encrypt_c0", pipeline="mul x4; boot")),
             ("server, mul step 0", "server", OP_MUL | dict(op_step=0)),
             ("server, boot step 0", "server", OP_BOOT | dict(op_step=0)),
             ("burst, k = 1 (c0)", "burst", NULL40 | dict(stage="encrypt_c0", amountBits=1)),
             ("network, encrypt_c0", "nn", dict(library="heaanNN", stage="encrypt_c0"))]
    rows = []
    for label, part, f in cases:
        e = rel.one(rep, part, **f)
        if e is None:
            continue
        d = rel.cells(part, e)
        n_all = d.groupby("bit")["n_seeds"].sum().min()
        n_al = d[d["aligned"]].groupby("bit")["n_seeds"].sum().min()
        rows.append([label, int(e["n_campaigns"]), fint(n_all), fint(n_al),
                     fnum(0.98 / math.sqrt(n_all), 3), fnum(0.98 / math.sqrt(n_al), 3)])
    rep.table(["configuration", "reps", "n/bit all", "n/bit aligned", "half-width all",
               "half-width aligned"], rows)


# --------------------------------------------------------------------------------------
# Chapter 5
# --------------------------------------------------------------------------------------
@section(5)
def ch5_master(rel, rep, args):
    rep.section("5.1", "Master curve of the one-bit law (fig:teo-curva)")
    if not {"client", "server"} <= set(rel.dirs):
        rep.missing("needs --client and --server")
        return
    run_script(rep, ["master_curve.py", "--client", str(rel.dirs["client"]),
                     "--server", str(rel.dirs["server"])])


@section(5)
def ch5_one_bit(rel, rep, args):
    rep.section("5.2", "One-bit law, c0, exact (reg:ley)")
    rep.how("Every HEAAN encrypt_c0 experiment without pipeline. Per cell (coeff, bit < logQ): "
            "ratio = l2_abs / (2^(b - logDelta) * sqrt(n/2)), n = slots (l2_abs of c0 does not "
            "depend on the key nor the input, so its mean over repetitions is exact). Main = "
            "aligned coefficients other than 0 and N/2, cells with E_L2 >= 1e-12 (below, double "
            "precision noise).")
    exps = rel.find("client", library="heaan", stage="encrypt_c0", pipeline="")
    if exps.empty:
        rep.missing("client: heaan encrypt_c0 without pipeline")
        return
    rows, main_all, c0_all, zero_cnt, zero_max, tiny_cnt, tiny_max = [], [], [], 0, 0.0, 0, 0.0
    for _, e in exps.sort_values(["logN", "logQ", "logDelta", "logSlots", "logMin"]).iterrows():
        d = rel.cells("client", e)
        d = d[d["bit"] < int(e["logQ"])]
        n, half = 1 << int(e["logSlots"]), (1 << int(e["logN"])) // 2
        ratio = d["l2_abs"] / (2.0 ** (d["bit"] - int(e["logDelta"])) * math.sqrt(n / 2))
        big = d["l2_rel"] >= 1e-12
        main = d["aligned"] & (d["coeff"] != 0) & (d["coeff"] != half) & big
        zero = (~d["aligned"]) | (d["coeff"] == half)
        tiny = d["aligned"] & (d["coeff"] != half) & ~big
        main_all.append(ratio[main])
        c0_all.append(ratio[(d["coeff"] == 0) & big])
        zero_cnt += int(zero.sum())
        zero_max = max(zero_max, float(d.loc[zero, "l2_abs"].max()) if zero.any() else 0.0)
        tiny_cnt += int(tiny.sum())
        tiny_max = max(tiny_max, float(d.loc[tiny, "l2_rel"].max()) if tiny.any() else 0.0)
        r = ratio[main]
        inputs = ("[-1,1]" if int(e["logMin"]) == int(e["logMax"]) == 0
                  else f"[2^{e['logMin']},2^{e['logMax']}]")
        rows.append([e["logN"], e["logQ"], e["logDelta"], n, inputs, e["bitsPerCoeff"],
                     e["n_campaigns"], int(main.sum()), fnum(r.median(), 4), fnum(r.min(), 5),
                     fnum(r.max(), 5)])
    rep.table(["logN", "logQ", "logD", "slots", "inputs", "bpc", "reps", "cells", "median",
               "min", "max"], rows)
    m, c0 = pd.concat(main_all), pd.concat(c0_all)
    rep.num(str(len(exps)), "configurations")
    rep.num(fint(len(m)), "cells, aligned, coefficient not 0 nor N/2, E_L2 >= 1e-12")
    rep.num(f"{fnum(m.median(), 4)}", "ratio, median over those cells")
    rep.num(f"{fnum(m.min(), 5)}-{fnum(m.max(), 5)}", "ratio, min-max")
    rep.num(fnum(c0.median(), 6), f"coefficient 0: ratio, median over {fint(len(c0))} "
            f"cells (sqrt 2 = {fnum(SQRT2, 6)})")
    rep.num(fint(zero_cnt), "cells of N/2 and non-aligned coefficients (bits < logQ)")
    rep.num(fsci(zero_max), "max l2_abs over them (0 = masked in every one)")
    rep.num(fint(tiny_cnt), "aligned cells with E_L2 < 1e-12 (double precision)")
    rep.num(fsci(tiny_max), "max E_L2 over them")

    rep.section("5.3", "One-bit law, c1: factor over c0 (reg:c1)")
    rep.how("Same ratio for encrypt_c1 (cells with E_L2 >= 1e-12, bits < logQ). Each cell is "
            "the mean over the repetitions, i.e. over the keys of the experiment. With gap "
            "(8 and 16 slots) only the aligned coefficients. sqrt(h) = 2.")
    groups = [("32 slots, 8 reps (2 keys)", "logSlots == 5 and n_campaigns == 8", "all"),
              ("32 slots, 625 reps (25 keys)", "logSlots == 5 and n_campaigns == 625", "all"),
              ("8 and 16 slots, aligned", "logSlots in [3, 4]", "al")]
    rows = []
    for label, q, which in groups:
        exps = rel.find("client", q, library="heaan", stage="encrypt_c1", pipeline="", logN=6)
        if exps.empty:
            rep.missing(f"client: encrypt_c1 without pipeline, {q}")
            continue
        rs = []
        for _, e in exps.iterrows():
            d = subset(rel.cells("client", e), which)
            d = d[(d["bit"] < int(e["logQ"])) & (d["l2_rel"] >= 1e-12)]
            n = 1 << int(e["logSlots"])
            rs.append(d["l2_abs"] / (2.0 ** (d["bit"] - int(e["logDelta"])) * math.sqrt(n / 2)))
        r = pd.concat(rs)
        p10, p50, p90 = np.percentile(r, [10, 50, 90])
        rows.append([label, len(exps), fint(len(r)), fnum(p10, 3), fnum(p50, 3), fnum(p90, 3)])
    rep.table(["c1 cells", "configs", "cells", "p10", "median", "p90"], rows)
    rep.num(fnum((SQRT2 + 2) / 2, 3), "(sqrt2 + 2) / 2: mean of the two values a key gives")


@section(5)
def ch5_bvis(rel, rep, args):
    rep.section("5.4", "First visible bit and first bit with E_L2 >= 1, relative to logDelta")
    rep.how("HEAAN encrypt without pipeline, inputs in [-1,1], every logDelta and logQ of the "
            "sweeps. E_L2 curve of the aligned coefficients (median over reps, median over "
            "coefficients). Columns: first visible bit - logDelta, first bit with E_L2 >= 1 - "
            "logDelta.")
    rows = []
    exps = rel.find("client", "logMin == 0 and logMax == 0", library="heaan", pipeline="",
                    logN=6)
    exps = exps[exps["stage"].isin(["encrypt_c0", "encrypt_c1"])]
    for _, e in exps.sort_values(["logQ", "logDelta", "logSlots", "stage"]).iterrows():
        c = curve(rel.cells("client", e), "al")
        fv, f1 = first(c), first(c, 1.0 - 1e-12)
        D = int(e["logDelta"])
        rows.append([e["stage"], e["logQ"], D, 1 << int(e["logSlots"]), e["bitsPerCoeff"],
                     e["n_campaigns"], "-" if fv is None else fv - D,
                     "-" if f1 is None else f1 - D])
    rep.table(["stage", "logQ", "logD", "slots", "bpc", "reps", "visible - logD",
               "E>=1 - logD"], rows)

    rep.section("5.5", "First visible bit: prediction (eq:bvis) vs. data")
    rep.how("Prediction b_vis = ceil(logDelta_r + log2(sqrt2 * 1e-2 * rms(z))), z = output; "
            "c1 one bit less. Measured, aligned coefficients, three ways of combining: "
            "median over reps then median over coeffs (text), mean over reps then median, "
            "mean and mean (what the figures draw).")
    r1 = rms_x(-1, 1, 1)
    cases = [("no ops, [-1,1], 32 slots", NULL40, ("encrypt_c0", "encrypt_c1"), 40, r1)]
    for a in (0, 9, 19, 29):
        cases.append((f"no ops, [2^{a},2^{a + 1}]",
                      BASE | dict(pipeline="", bitsPerCoeff=64, logDelta=20, logMin=a, logMax=a + 1),
                      ("encrypt_c0", "encrypt_c1"), 20, rms_x(2.0 ** a, 2.0 ** (a + 1), 1)))
    for ls in (3, 4, 5):
        cases.append((f"add; rot 3, {1 << ls} slots",
                      dict(library="heaan", logN=6, logQ=60, logDelta=30, bitsPerCoeff=64,
                           pipeline="add; rot 3", logSlots=ls),
                      ("encrypt_c0", "encrypt_c1"), 30, 2 * r1))
    cases.append(("decrypt after mul x3 (z = x^4)", CLIENT_MUL | dict(pipeline="mul x3"),
                  ("decrypt_c0", "decrypt_c1"), 30, rms_x(-1, 1, 4)))
    rows = []
    for label, f, stages, logd, rms in cases:
        pred = ceil_bit(bvis_raw(logd, rms))
        meas = []
        for st in stages:
            e = rel.one(rep, "client", **(f | dict(stage=st)))
            if e is None:
                meas.append(("-", "-", "-"))
                continue
            d = rel.cells("client", e)
            meas.append(tuple(fbit(first(curve(d, "al", col, stat))) for col, stat in
                              (("l2_rel_median", "median"), ("l2_rel", "median"),
                               ("l2_rel", "mean"))))
        rows.append([label, f"{pred}/{pred - 1}", fnum(bvis_raw(logd, rms)),
                     f"{meas[0][0]}/{meas[1][0]}", f"{meas[0][1]}/{meas[1][1]}",
                     f"{meas[0][2]}/{meas[1][2]}"])
    rep.table(["configuration", "pred c0/c1", "unrounded", "med-med c0/c1", "mean-med",
               "mean-mean"], rows)


@section(5)
def ch5_leak_key(rel, rep, args):
    rep.section("5.6", "Leak of the gap through a ciphertext product (eq:fuga)")
    rep.how("Client, fault in c0 before K ct x ct mults (logQ 150, logDelta 30, 8 slots). "
            "Prediction for the non-aligned coefficients: 2 logDelta + log2(1e-2 rms(x^(K+1)) / "
            "(sigma_e sqrt(n) rms(x^(K-1)))), sigma_e = 1.6. Measured: first visible bit "
            "(median-median) of the non-aligned and of the aligned coefficients.")
    rows = []
    for K, pipe in ((1, "mul"), (2, "mul x2"), (3, "mul x3")):
        e = rel.one(rep, "client", **(CLIENT_MUL | dict(stage="encrypt_c0", pipeline=pipe)))
        if e is None:
            continue
        d = rel.cells("client", e)
        n, D = 1 << int(e["logSlots"]), int(e["logDelta"])
        pred = 2 * D + math.log2(TAU * rms_x(-1, 1, K + 1) /
                                 (SIGMA_E * math.sqrt(n) * rms_x(-1, 1, K - 1)))
        rows.append([pipe, fnum(pred), ceil_bit(pred), fbit(first(curve(d, "other"))),
                     fbit(first(curve(d, "al")))])
    rep.table(["pipeline", "pred other", "ceil", "measured other", "measured aligned"], rows)

    rep.section("5.7", "Faults in the key and before the shift of a key switching (eq:clave)")
    rep.how("Server. b_vis_u = logDelta_r + log2(sqrt2 1e-2 rms(z)) unrounded, logDelta_r = "
            "scale of the value the key switching is added to (2 logDelta in a mul, logDelta "
            "in a rot). Key: b_vis_u + log Q - log q_l - log2 sqrt(2 n h / 3) (k1) or log2 "
            "sqrt(2 n / 3) (k0). Before the shift: log Q + b_vis_u. Measured: first visible "
            "bit, aligned / non-aligned.")
    rows = []
    cases = []
    for s, kind in ((11, "k1"), (13, "k0"), (14, "shift"), (15, "shift")):
        cases.append((f"mul, step {s}", OP_MUL | dict(op_step=s), kind, 60, rms_x(-1, 1, 2)))
    for dep in (0, 1, 2):
        for s, kind in ((11, "k1"), (13, "k0"), (14, "shift"), (15, "shift")):
            cases.append((f"mul x3 depth {dep}, step {s}",
                          OP_MUL_DEPTH | dict(op_step=s, op_depth=dep), kind, 60,
                          rms_x(-1, 1, dep + 2)))
    for s, kind in ((3, "k1"), (5, "k0")):
        cases.append((f"rot 2, step {s}", OP_ROT | dict(op_step=s), kind, 30, rms_x(-1, 1, 1)))
    for label, f, kind, logd, rms in cases:
        e = rel.one(rep, "server", **f)
        if e is None:
            continue
        d = rel.cells("server", e)
        n, logQ, logq = 1 << int(e["logSlots"]), int(e["logQ"]), level_logq(e)
        b = bvis_raw(logd, rms)
        if kind == "shift":
            pred = logQ + b
        else:
            spread = 2 * n * H / 3 if kind == "k1" else 2 * n / 3
            pred = b + logQ - logq - math.log2(math.sqrt(spread))
        rows.append([label, kind, logq, fnum(pred), ceil_bit(pred),
                     fbit(first(curve(d, "al"))), fbit(first(curve(d, "other")))])
    rep.table(["step", "kind", "log q_l", "pred", "ceil", "measured al", "measured other"], rows)


@section(5)
def ch5_saturation(rel, rep, args):
    rep.section("5.8", "Saturation (reg:saturacion)")
    rep.how("Prediction E_sat = (q_out / Delta_r) sqrt(n/12) / rms(z) at the output level. "
            "Client (c0 before K mults, logQ 150): measured plateau = median of the curve over "
            "the bits within a factor 4 of its maximum, aligned coefficients; both the "
            "median-median curve and the mean-mean curve of the figures.")
    rows = []
    for K, pipe in ((1, "mul"), (2, "mul x2"), (3, "mul x3")):
        e = rel.one(rep, "client", **(CLIENT_MUL | dict(stage="encrypt_c0", pipeline=pipe)))
        if e is None:
            continue
        d = rel.cells("client", e)
        n, D, Q = 1 << int(e["logSlots"]), int(e["logDelta"]), int(e["logQ"])
        pred = 2.0 ** (Q - K * D - D) * math.sqrt(n / 12) / rms_x(-1, 1, K + 1)
        out, plateau = [pipe, fsci(pred)], []
        for col, stat in (("l2_rel_median", "median"), ("l2_rel", "mean")):
            c = curve(d, "al", col, stat)
            c = c[np.isfinite(c)]
            top = c[c >= c.max() / 4]
            plateau.append(float(top.median()))
            out += [fsci(top.median()), f"{top.index.min()}-{top.index.max()}"]
        rows.append(out + [fnum(plateau[0] / pred)])
    rep.table(["pipeline", "pred", "plateau med-med", "bits", "plateau mean-mean", "bits",
               "med-med / pred"], rows)

    rep.how("Server steps that destroy the output from bit 0: measured = median over the "
            "bits of the module of the curve over all coefficients (median-median); "
            "prediction at the output of the operation (mul: level 30, z = x^2; rot: level 60, "
            "z = x; pmul x2: level 60, z = x^3; Delta_r = 2^30).")
    rows, ratios = [], []
    for name, f, out_level, k in (("mul", OP_MUL, lambda e: level_logq(e) - 30, 2),
                                  ("rot", OP_ROT, lambda e: level_logq(e), 1),
                                  ("pmul", OP_PMUL, lambda e: level_logq(e) - 30, 3)):
        for _, e in rel.find("server", **f).sort_values("op_step").iterrows():
            d = rel.cells("server", e)
            c = curve(d, "all")
            if first(c) != 0:
                continue
            W, _ = module_width(e)
            meas = float(c[c.index < W].median())
            n = 1 << int(e["logSlots"])
            pred = 2.0 ** (out_level(e) - 30) * math.sqrt(n / 12) / rms_x(-1, 1, k)
            ratios.append(meas / pred)
            rows.append([name, int(e["op_step"]), W, fsci(meas, 2), fsci(pred, 2),
                         fnum(meas / pred)])
    rep.table(["op", "step", "W", "measured", "pred", "ratio"], rows)
    if ratios:
        rep.num(f"{fnum(min(ratios))}-{fnum(max(ratios))}",
                "measured / predicted over the destroyed server steps")


@section(5)
def ch5_floor(rel, rep, args):
    rep.section("5.9", "Rounding floor at bit 0 (reg:division)")
    rep.how("Client HEAAN, fault before ct x ct or ct x pt mults, no boot. Measured: log2 of "
            "the E_L2 curve (median-median, aligned) at bit 0. Predicted: analytic_baseline."
            "predict at bit 0 (median over the aligned coefficients), where the rounding floor "
            "dominates. Difference = measured - predicted, in bits.")
    rows = []
    exps = rel.find("client", library="heaan", logN=6)
    exps = exps[exps["stage"].isin(["encrypt_c0", "encrypt_c1"])
                & exps["pipeline"].isin(["mul", "mul x2", "mul x3", "mul x4", "pmul", "pmul x3"])]
    for _, e in exps.sort_values(["pipeline", "stage"]).iterrows():
        d = rel.cells("client", e)
        c = curve(d, "al")
        if 0 not in c.index or c.loc[0] <= 0:
            continue
        cells0 = d[(d["bit"] == 0) & d["aligned"]]
        pred = np.median(predict(e, cells0))
        meas = math.log2(c.loc[0])
        rows.append([e["stage"], e["pipeline"], e["logQ"], fnum(meas), fnum(pred),
                     fnum(meas - pred)])
    rep.table(["stage", "pipeline", "logQ", "log2 E meas", "log2 E pred", "meas - pred"], rows)


@section(5)
def ch5_exposure(rel, rep, args):
    rep.section("5.10", "Exposure (reg:exposicion): P(SDC) of the aligned coefficients")
    rep.how("HEAAN client encrypt, logN 6, every configuration. Predicted: fraction of the "
            "(aligned coefficient other than 0 and N/2, bit in [0, logQ)) cells where "
            "analytic_baseline.predict gives E_L2 > 1e-2 (visible between b_vis and logQ or "
            "the boot cut). Measured: P(SDC) over [0, logQ) of the same coefficients. Note: "
            "predicted is 'visible', measured is 'some slot > 10 %'.")
    rows, diffs = [], []
    exps = rel.find("client", library="heaan", logN=6)
    exps = exps[exps["stage"].isin(["encrypt_c0", "encrypt_c1"])]
    for _, e in exps.sort_values(["pipeline", "logQ", "logDelta", "logSlots", "logMin",
                                  "stage"]).iterrows():
        d = rel.cells("client", e)
        half = (1 << int(e["logN"])) // 2
        x = d[d["aligned"] & (d["coeff"] != 0) & (d["coeff"] != half)].copy()
        x["vis_pred"] = (predict(e, x) > math.log2(TAU)).astype(float)
        W = int(e["logQ"])
        pred = interp_mean(x.groupby("bit")["vis_pred"].mean(), 0, W)
        meas = interp_mean(rate_per_bit(x), 0, W)
        diffs.append((abs(pred - meas), e))
        inputs = "" if int(e["logMin"]) == int(e["logMax"]) == 0 else f"2^{e['logMin']}"
        rows.append([e["stage"], e["pipeline"] or "(none)", e["logQ"], e["logDelta"],
                     1 << int(e["logSlots"]), inputs, e["bitsPerCoeff"], fnum(pred, 3),
                     fnum(meas, 3), fnum(meas - pred, 3)])
    rep.table(["stage", "pipeline", "logQ", "logD", "slots", "inputs", "bpc", "pred", "meas",
               "meas - pred"], rows)
    if diffs:
        err = np.array([x for x, _ in diffs])
        worst = max(diffs, key=lambda t: t[0])[1]
        rep.num(str(len(err)), "configurations")
        rep.num(fnum(err.mean(), 3), "mean |meas - pred|")
        rep.num(fnum(err.max(), 3),
                f"max |meas - pred| ({worst['stage']}, {worst['pipeline'] or '(none)'})")
        rest = err[[("x5" not in e["pipeline"]) for _, e in diffs]]
        rep.num(fnum(rest.max(), 3), "max |meas - pred| without 'mul x5; boot'")


@section(5)
def ch5_scripts(rel, rep, args):
    rep.section("5.11", "Analytical predictor without fitting (tab:teo-predictor)")
    if "client" not in rel.dirs:
        rep.missing("needs --client")
    else:
        run_script(rep, ["analytic_baseline.py", str(rel.dirs["client"])])
    rep.section("5.12", "Toy CKKS with exact integers (numbers of the proofs and the cancellation)")
    run_script(rep, ["theory_check.py"])


# --------------------------------------------------------------------------------------
# Chapter 6
# --------------------------------------------------------------------------------------
@section(6)
def ch6_stages(rel, rep, args):
    rep.section("6.1", "Encode, c0, c1, decrypt and decode coincide (c1_fig03)")
    rep.how("Config of c1_fig03: HEAAN logN 6, 32 slots, logQ 60, logDelta 40, no pipeline. "
            "HEAAN encode is shifted by logQ (its bit logQ + b acts as bit b). Cell by cell: "
            "l2_abs / l2_abs of encrypt_c0 at the same (coeff, bit), bits [0, 60), cells where "
            "encrypt_c0 is not 0. Curves: ratio of the E_L2 curves over all coefficients, "
            "median over bits 34-59 and value at bit 59.")
    st_f = {"encrypt_c0": NULL40 | dict(stage="encrypt_c0"),
            "encrypt_c1": NULL40 | dict(stage="encrypt_c1"),
            "decrypt_c0": NULL40 | dict(stage="decrypt_c0"),
            "decrypt_c1": NULL40 | dict(stage="decrypt_c1"),
            "decode": NULL40 | dict(stage="decode"),
            "encode": NULL40 | dict(stage="encode", bitsPerCoeff=128)}
    d = {}
    for st, f in st_f.items():
        e = rel.one(rep, "client", **f)
        if e is not None:
            x = rel.cells("client", e).copy()
            if st == "encode":
                x["bit"] -= int(e["logQ"])
            d[st] = x
    if "encrypt_c0" not in d:
        return
    ref = d["encrypt_c0"][["coeff", "bit", "l2_abs"]]
    for st in ("decode", "decrypt_c0", "encode"):
        if st not in d:
            continue
        m = d[st].merge(ref, on=["coeff", "bit"], suffixes=("", "_ref"))
        m = m[(m["bit"] >= 0) & (m["bit"] < 60) & (m["l2_abs_ref"] > 0)]
        r = m["l2_abs"] / m["l2_abs_ref"]
        rep.num(f"{fnum(r.min(), 4)}-{fnum(r.max(), 4)}",
                f"{st} / encrypt_c0, l2_abs cell by cell over {fint(len(r))} cells")
    half = 32
    for st in ("encrypt_c0", "decode"):
        if st in d:
            x = d[st]
            rep.num(fsci(x[(x["coeff"] == half) & (x["bit"] >= 0) & (x["bit"] < 60)]
                                  ["l2_abs"].max()), f"{st}: max l2_abs at N/2, bits < logQ")
    pairs = [("decrypt_c1", "encrypt_c1"), ("encrypt_c1", "encrypt_c0"), ("decode", "encrypt_c0"),
             ("decrypt_c0", "encrypt_c0")]
    rows = []
    for a, b in pairs:
        if a in d and b in d:
            out = [f"{a} / {b}"]
            for col, stat in (("l2_rel_median", "median"), ("l2_rel", "mean")):
                q = curve(d[a], "all", col, stat) / curve(d[b], "all", col, stat)
                out += [fnum(q.loc[34:59].median(), 3), fnum(q.get(59, np.nan), 3)]
            rows.append(out)
    rep.table(["curves", "med-med: median 34-59", "bit 59", "mean-mean: median 34-59",
               "bit 59"], rows)
    rows = [[st, fbit(first(curve(x, "all")))] for st, x in d.items()]
    rep.table(["stage", "first visible bit (encode: minus logQ)"], rows)
    if "encode" in d:
        x = d["encode"]
        top = x[x["bit"] >= 60]          # bits >= 2 logQ of the encode register
        rep.num(fsci(top["l2_abs"].max()), "HEAAN encode, bits >= 2 logQ: max l2_abs")
        rep.num(fsci(curve(top, "all").max()),
                "HEAAN encode, bits >= 2 logQ: max of the E_L2 curve")
    e = rel.one(rep, "client", **(dict(library="openfhe", logN=6, logSlots=5, logQ=60,
                                       logDelta=40, stage="encode", pipeline="",
                                       attackModeSKA=1)))
    if e is not None:
        for col, stat, name in (("l2_rel_median", "median", "med-med"), ("l2_rel", "mean", "mean-mean")):
            c = curve(rel.cells("client", e), "all", col, stat)
            rep.num(" / ".join(fsci(c.get(b, np.nan)) for b in (62, 63)),
                    f"OpenFHE encode, E_L2 curve ({name}) at bits 62 / 63 (above the 60-bit prime)")


@section(6)
def ch6_openfhe_factor(rel, rep, args):
    rep.section("6.2", "OpenFHE / HEAAN encode: the factor of the decoding noise (c1_fig01)")
    rep.how("l2_abs of OpenFHE encode (bit b) / HEAAN encode (bit b + logQ), same coefficient, "
            "logDelta 40, 32 slots. 'rest' = coefficients other than 0 and N/2. attackModeSKA "
            "= 1 adds OpenFHE's decoding noise (default), 0 does not.")
    h = rel.one(rep, "client", **(NULL40 | dict(stage="encode", bitsPerCoeff=128)))
    if h is None:
        return
    dh = rel.cells("client", h).copy()
    dh["bit"] -= int(h["logQ"])
    half = 32
    for ska in (1, 0):
        o = rel.one(rep, "client", library="openfhe", logN=6, logSlots=5, logQ=60, logDelta=40,
                    stage="encode", pipeline="", attackModeSKA=ska)
        if o is None:
            continue
        do = rel.cells("client", o)
        m = do.merge(dh, on=["coeff", "bit"], suffixes=("_o", "_h"))
        m = m[(m["bit"] >= 0) & (m["bit"] < 60) & (m["l2_abs_h"] > 0)]
        m["r"] = m["l2_abs_o"] / m["l2_abs_h"]
        rest = m[(m["coeff"] != 0) & (m["coeff"] != half)]
        by_bit = rest.groupby("bit")["r"].median()
        by_coeff = rest[rest["bit"] >= 14].groupby("coeff")["r"].median()
        tag = f"SKA={ska}"
        rep.num(fnum(m[m["coeff"] == 0]["r"].median(), 3), f"{tag}: coefficient 0, median")
        rep.num(fnum(rest["r"].median(), 3), f"{tag}: rest, median over every bit")
        rep.num(f"{fnum(by_coeff.min())}-{fnum(by_coeff.max())}",
                f"{tag}: rest, per-coefficient median (bits >= 14), min-max")
        rep.num(f"{fnum(by_bit.loc[0:6].min())}-{fnum(by_bit.loc[0:6].max())}",
                f"{tag}: rest, per-bit median, bits 0-6")
        rep.num(" ".join(fnum(by_bit.get(b, np.nan)) for b in range(7, 14)),
                f"{tag}: rest, per-bit median, bits 7..13")
        rep.num(f"{fnum(by_bit.loc[14:].min())}-{fnum(by_bit.loc[14:].max())}",
                f"{tag}: rest, per-bit median, bits >= 14")
        cells = m[(m["coeff"] != half) & (m["bit"] >= 34)]
        rep.num(f"{fnum(cells['r'].min(), 4)}-{fnum(cells['r'].max(), 4)}",
                f"{tag}: every coefficient but N/2, bits 34-59 ({fint(len(cells))} cells), min-max")
        n2 = do[(do["coeff"] == half) & (do["bit"] < 60)].set_index("bit")["l2_abs"]
        c1 = do[do["coeff"] == 1].set_index("bit")["l2_abs"]
        rep.num(fsci(n2.max()), f"{tag}: N/2, max l2_abs over bits < 60 (0 = masked)")
        if n2.max() > 0:
            q = (n2 / c1).loc[12:59]
            rep.num(f"{fnum(q.min())}-{fnum(q.max())}",
                    f"{tag}: N/2 / coefficient 1, bits 12-59")
    e = rel.one(rep, "client", library="openfhe", logN=6, logSlots=5, logQ=60, logDelta=40,
                bitsPerCoeff=64, mult_depth=0, withNTT=0, attackModeSKA=1, stage="encode",
                pipeline="")
    if e is not None:
        d = rel.cells("client", e)
        win = d[(d["bit"] >= 40) & (d["bit"] <= 58)]
        rep.num(fnum(rate_per_bit(win[win["coeff"] == 0], "detected").mean()),
                "detector, coefficient 0, bits 40-58: detection rate")
        rep.num(fnum(rate_per_bit(win[win["coeff"] != 0], "detected").mean()),
                "detector, other coefficients, bits 40-58: detection rate")
        rep.num(fnum(p_module(d, 64, col="sdc_undetected")),
                "encode: SDC undetected, fraction of the injections (bits 0-63)")
        rep.num(fnum(p_module(d, 64, col="false_alarm")),
                "encode: false alarms, fraction of the injections (bits 0-63)")


@section(6)
def ch6_reps(rel, rep, args):
    rep.section("6.3", "Repetitions: how much one key and one input move the curve")
    rep.how("Per repetition, the curve = mean over its coefficients (the _reps file of the "
            "collapse). Spread = max over the bits of (max / min over the repetitions). Onset "
            "= first bit where a repetition's curve exceeds 1e-2.")
    for st in ("encrypt_c0", "encrypt_c1"):
        e = rel.one(rep, "client", **(NULL40 | dict(stage=st)))
        if e is None:
            continue
        r = pd.read_csv(rel.dirs["client"] / str(e["data_file"]).replace(".csv.gz", "_reps.csv.gz"))
        g = r[(r["bit"] >= 34) & (r["bit"] < 60)].groupby("bit")["l2_rel"].agg(["min", "max"])
        on = r[r["l2_rel"] > TAU].groupby("campaign_id")["bit"].min()
        rep.num(fnum((g["max"] / g["min"]).max()),
                f"{st}, {e['n_campaigns']} reps: max over bits 34-59 of max/min")
        rep.num(f"{on.min()}-{on.max()}",
                f"{st}: onset per repetition ({', '.join(f'{b}: {n}' for b, n in on.value_counts().sort_index().items())})")
    rows = []
    for st in ("encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"):
        e = rel.one(rep, "client", **(CLIENT_MUL | dict(stage=st, pipeline="mul x3")))
        if e is None:
            continue
        r = pd.read_csv(rel.dirs["client"] / str(e["data_file"]).replace(".csv.gz", "_reps.csv.gz"))
        g = r[r["l2_rel"] > 0].groupby("bit")["l2_rel"].agg(["min", "max"])
        q = g["max"] / g["min"]
        rows.append([st, e["n_campaigns"], fnum(q.max(), 1), int(q.idxmax())])
    rep.table(["stage (pipeline mul x3, output x^4)", "reps", "max over bits of max/min",
               "at bit"], rows)


@section(6)
def ch6_logn(rel, rep, args):
    rep.section("6.4", "logN = 16 vs logN = 6 (c1_fig05)")
    rep.how("encrypt_c0, logQ 60, logDelta 40, slots = N/2. Ratio of the curves logN16 / logN6 "
            "per bit (all coefficients), over bits 34-59: median and min-max.")
    a = rel.one(rep, "client", library="heaan", stage="encrypt_c0", pipeline="", logN=16,
                logQ=60, logDelta=40)
    b = rel.one(rep, "client", **(NULL40 | dict(stage="encrypt_c0")))
    if a is None or b is None:
        return
    for col, stat, name in (("l2_rel_median", "median", "med-med"), ("l2_rel", "mean", "mean-mean")):
        q = (curve(rel.cells("client", a), "all", col, stat) /
             curve(rel.cells("client", b), "all", col, stat)).loc[34:59]
        rep.num(f"{fnum(q.median())} ({fnum(q.min())}-{fnum(q.max())})",
                f"{name}: logN16 / logN6, median (min-max) over bits 34-59")


@section(6)
def ch6_slots(rel, rep, args):
    rep.section("6.5", "Does a fault break every slot or only some? (c1_fig04)")
    rep.how("Per injection: 'every slot' = all slots > 1 % (all_over1), 'some' = some but not "
            "all (some_over1), 'not correct' = some slot > 1 % (1 - is_masked). Every slot = "
            "sum(all_over1) / sum(1 - is_masked) over the cells with bit < logQ. Band of "
            "'some' = sum over the bits of the mean of some_over1 (expected number of bits). "
            "Crest = linf_abs sqrt(n) / l2_abs, median over the cells with E_L2 > 1e-2. "
            "frac_bad (slots > 1 %) at the bit whose E_L2 curve is closest to 0.1 and 1, over "
            "the coefficients where the error is not 0.")
    cases = [("[-1,1], 32 slots, logDelta 40", NULL40),
             ("[-1,1], 8 slots, logDelta 40", NULL40 | dict(logSlots=3)),
             ("[1,2], 32 slots, logDelta 20", BASE | dict(pipeline="", bitsPerCoeff=64,
                                                          logDelta=20, logMin=0, logMax=1))]
    rows = []
    for label, f in cases:
        for st in ("encrypt_c0", "encrypt_c1"):
            e = rel.one(rep, "client", **(f | dict(stage=st)))
            if e is None:
                continue
            d = rel.cells("client", e)
            d = d[d["bit"] < int(e["logQ"])]
            every = d["all_over1"].sum() / (1 - d["is_masked"]).sum()
            band = d.groupby("bit")["some_over1"].mean().sum()
            crest = d.loc[d["l2_rel_median"] > TAU, "crest"].median()
            c = curve(d, "al")
            fb = []
            for t in (0.1, 1.0):
                b = (np.log10(c[c > 0]) - math.log10(t)).abs().idxmin()
                x = d[(d["bit"] == b) & d["aligned"] & (d["l2_rel_median"] > 0)]
                fb.append(f"{fnum(x['frac_bad'].mean())} (bit {b})")
            rows.append([label, st, e["n_campaigns"], fnum(every), fnum(band, 1), fnum(crest),
                         fb[0], fb[1]])
    rep.table(["inputs, slots", "stage", "reps", "every slot", "band 'some' (bits)", "crest",
               "frac_bad at E~0.1", "frac_bad at E~1"], rows)

    rep.how("MREP vs E_L2: first bit where the MREP curve (linf_rel_median, median over the "
            "aligned coefficients) exceeds 1 %, and first bit where E_L2 exceeds 1e-2. Lead = "
            "how many bits earlier the MREP crosses.")
    cases = [("[1,2], 32 slots", BASE | dict(pipeline="", bitsPerCoeff=64, logDelta=20, logMin=0,
                                            logMax=1, stage="encrypt_c0")),
             ("[-1,1], 8 slots", NULL40 | dict(logSlots=3, stage="encrypt_c0")),
             ("[-1,1], 32 slots", NULL40 | dict(stage="encrypt_c0")),
             ("x^4 (decrypt_c0 after mul x3)", CLIENT_MUL | dict(pipeline="mul x3",
                                                                stage="decrypt_c0"))]
    rows = []
    for label, f in cases:
        e = rel.one(rep, "client", **f)
        if e is None:
            continue
        d = rel.cells("client", e)
        m, v = first(curve(d, "al", "linf_rel_median") * 100, MREP_PCT), first(curve(d, "al"))
        rows.append([label, m, v, "-" if None in (m, v) else v - m])
    rep.table(["configuration (c0)", "MREP > 1 %", "E_L2 > 1e-2", "lead"], rows)

    rep.how("c1, non-aligned coefficients, 8 and 16 slots: fraction of damaged slots "
            "(frac_bad) in the cells with E_L2 > 10.")
    for ls in (3, 4):
        e = rel.one(rep, "client", **(NULL40 | dict(stage="encrypt_c1", logSlots=ls)))
        if e is None:
            continue
        d = rel.cells("client", e)
        x = d[(~d["aligned"]) & (d["l2_rel_median"] > 10)]
        rep.num(f"{fnum(x['frac_bad'].median())} ({fnum((x['frac_bad'] == 0.5).mean())})",
                f"{1 << ls} slots: median frac_bad (fraction of cells exactly 0,5), {len(x)} cells")


@section(6)
def ch6_pipelines(rel, rep, args):
    rep.section("6.6", "HEAAN: a fault before a pipeline (c1_fig10, c1_fig12, c1_fig13, ev_)")
    rep.how("Every HEAAN client configuration with a pipeline and no boot. Visible range of the "
            "aligned and of the non-aligned coefficients (median-median); max E_L2 over the "
            "non-aligned cells (0 = the gap masks them exactly); maximum of the aligned curve "
            "(median-median and mean-mean).")
    exps = rel.find("client", library="heaan", logN=6)
    exps = exps[(exps["pipeline"] != "") & ~exps["pipeline"].str.contains("boot")]
    rows = []
    for _, e in exps.sort_values(["pipeline", "logQ", "logSlots", "stage"]).iterrows():
        d = rel.cells("client", e)
        oth = subset(d, "other")
        rows.append([e["stage"], e["pipeline"], e["logQ"], e["logDelta"], 1 << int(e["logSlots"]),
                     frange(first_last(curve(d, "al"))),
                     frange(first_last(curve(d, "other"))) if len(oth) else "-",
                     fsci(oth["l2_rel_median"].max()) if len(oth) else "-",
                     fsci(curve(d, "al").max()), fsci(curve(d, "al", "l2_rel", "mean").max())])
    rep.table(["stage", "pipeline", "logQ", "logD", "slots", "visible al", "visible other",
               "max E other", "max al med", "max al mean"], rows)


def limb_widths(e, d):
    """OpenFHE: {limb: bits of its prime} for the limbs present in the data (a ciphertext
    decrypted after k rescales has k limbs less than mult_depth + 1). Limb 0 is the first
    prime (logQ bits), the rest are scaling primes (logDelta bits)."""
    return {int(l): int(e["logQ"]) if l == 0 else int(e["logDelta"])
            for l in sorted(d["limb"].unique())}


def p_limbs(d, widths, which="all", col="is_sdc", above=False):
    """P over the bits of the module of every limb (or the bits above it, up to 64),
    weighted by the number of bits."""
    num_, den = 0.0, 0
    for limb, W in widths.items():
        x = d[d["limb"] == limb]
        lo, hi = (W, 64) if above else (0, W)
        p = p_module(x, hi, which, col, lo=lo)
        if isnum(p):
            num_ += p * (hi - lo)
            den += hi - lo
    return num_ / den if den else np.nan


@section(6)
def ch6_openfhe(rel, rep, args):
    rep.section("6.7", "OpenFHE: plain, RNS and NTT (c1_fig11, c1_fig16-18, ev_rns_*, ev_mul_rns)")
    rep.how("Every OpenFHE client experiment. limbs = the limbs present at the injection "
            "point (mult_depth + 1 less the rescales before it); module of limb 0 = logQ "
            "bits, of the others logDelta bits. P = P(SDC) over the bits of the module of every "
            "limb (weighted by bits); P above = over the bits above it (up to bit 63). OOR = "
            "fraction of injections that left the residue >= q (out_of_range). log10 E = median "
            "of log10 E_L2 over the aligned cells inside the module.")
    exps = rel.find("client", library="openfhe")
    rows = []
    for _, e in exps.sort_values(["pipeline", "mult_depth", "withNTT", "logSlots", "stage",
                                  "attackModeSKA"]).iterrows():
        d = rel.cells("client", e)
        ws = limb_widths(e, d)
        inside = d[d["bit"] < d["limb"].map(ws)]
        al = inside[inside["aligned"] & (inside["l2_rel_median"] > 0)]
        rows.append([e["stage"], e["pipeline"] or "(none)", len(ws), int(e["withNTT"]),
                     1 << int(e["logSlots"]), int(e["attackModeSKA"]),
                     fnum(p_limbs(d, ws)), fnum(p_limbs(d, ws, "al")),
                     fnum(p_limbs(d, ws, "other")), fnum(p_limbs(d, ws, above=True)),
                     fnum(d["out_of_range"].mean()),
                     fnum(np.log10(al["l2_rel_median"]).median(), 1) if len(al) else "-",
                     frange(first_last(curve(d[d["limb"] == 0], "al")))])
    rep.table(["stage", "pipeline", "limbs", "NTT", "slots", "SKA", "P", "P al", "P other",
               "P above", "OOR", "log10 E al", "visible al (limb 0)"], rows)

    rep.how("RNS prediction (reg:rns): a flip of a residue moves the value by m * M_a with "
            "median M / 4, so log10 E_L2 = log10(2^(log M - 2 - logDelta) / (sqrt2 rms(z))), "
            "log M = logQ + (limbs - 1) logDelta (nominal prime sizes). Config of c1_fig16 "
            "(add; rot 3, z = 2x, 4 limbs, 8 slots): median log10 E_L2 per limb, aligned cells "
            "inside the module.")
    for st in ("encrypt_c0", "encrypt_c1"):
        e = rel.one(rep, "client", **(OFHE | dict(stage=st, pipeline="add; rot 3", mult_depth=3,
                                                  withNTT=0, logSlots=3)))
        if e is None:
            continue
        d = rel.cells("client", e)
        ws = limb_widths(e, d)
        logM = sum(ws.values())
        pred = (logM - 2 - int(e["logDelta"])) * math.log10(2) - math.log10(SQRT2 * 2 * rms_x(-1, 1, 1))
        per = []
        for limb, W in ws.items():
            x = d[(d["limb"] == limb) & (d["bit"] < W) & d["aligned"] & (d["l2_rel_median"] > 0)]
            per.append(fnum(np.log10(x["l2_rel_median"]).median(), 2))
        rep.num(" / ".join(per), f"{st}: median log10 E_L2 per limb (pred {fnum(pred, 2)})")
        x = d[d["aligned"] & (d["l2_rel_median"] > 0)]
        span = np.log10(curve(x, "all")).agg(["min", "max"])
        rep.num(fnum(span["max"] - span["min"], 1),
                f"{st}: decades spanned by the aligned curve over bits 0-63, every limb")

    rep.how("Exposure with one limb (add; rot 3, plain, no NTT): (W - b_vis) / W with b_vis = "
            "first visible bit of the aligned coefficients, vs. measured P(SDC) of those "
            "coefficients over the 60 bits.")
    for ls in (3, 4, 5):
        for st in ("encrypt_c0", "encrypt_c1"):
            e = rel.one(rep, "client", **(OFHE | dict(stage=st, pipeline="add; rot 3",
                                                      mult_depth=0, withNTT=0, logSlots=ls)))
            if e is None:
                continue
            d = rel.cells("client", e)
            bv = first(curve(d, "al"))
            W = int(e["logQ"])
            rep.num(f"{fnum((W - bv) / W)} / {fnum(p_module(d, W, 'al'))}",
                    f"{1 << ls} slots, {st}: exposure (W - b_vis)/W (b_vis = {bv}) / measured P al")


@section(6)
def ch6_detector(rel, rep, args):
    rep.section("6.8", "OpenFHE SDC detector, one limb, add; rot 3 (c1_fig11)")
    rep.how("Onset = per coefficient, the lowest bit of the module where the detector fires in "
            ">= half of the repetitions; median over the coefficients where it fires. Undetected "
            "= among the injections whose cell has E_L2 > 1e-2 (bits of the module), the "
            "fraction not detected, without coefficient 0. Bound = max E_L2 of a cell (max over "
            "its repetitions) with some undetected injection, without the coefficients where "
            "the detector never fires; cells > 0.4 = how many such cells have E_L2 above 0.4. "
            "Coefficient 0 of c0 is reported apart.")
    rows = []
    for ls in (3, 4, 5):
        for st in ("encrypt_c0", "encrypt_c1"):
            e = rel.one(rep, "client", **(OFHE | dict(stage=st, pipeline="add; rot 3",
                                                      mult_depth=0, withNTT=0, logSlots=ls)))
            if e is None:
                continue
            d = rel.cells("client", e)
            d = d[d["bit"] < int(e["logQ"])]
            on = d[d["detected"] >= 0.5].groupby(["limb", "coeff"])["bit"].min()
            never = set(d.groupby(["limb", "coeff"]).groups) - set(on.index)
            vis = d[(d["l2_rel_median"] > TAU) & (d["coeff"] != 0)]
            und = ((1 - vis["detected"]) * vis["n_seeds"]).sum() / vis["n_seeds"].sum()
            idx = d.set_index(["limb", "coeff"]).index
            blind = idx.isin(list(never)) | (d["coeff"] == 0).to_numpy()
            missed = d.loc[(d["detected"] < 1).to_numpy() & ~blind, "l2_rel_hi"]
            c0 = d[d["coeff"] == 0]
            rows.append([st, 1 << ls, fnum(np.median(on), 0) if len(on) else "-", len(never),
                         fnum(und), fsci(missed.max()) if len(missed) else "-",
                         int((missed > 0.4).sum()),
                         fnum(rate_per_bit(c0, "detected").max()), fsci(c0["l2_rel_median"].max()),
                         fnum(p_module(d, int(e["logQ"]), col="false_alarm"), 3)])
    rep.table(["stage", "slots", "onset median", "cells never", "undetected | visible",
               "bound", "cells > 0.4", "coef 0: max det. rate", "coef 0: max E",
               "false alarms"], rows)


@section(6)
def ch6_boot(rel, rep, args):
    rep.section("6.9", "Client fault through the bootstrapping (c1_fig14, c1_fig15)")
    rep.how("HEAAN logQ 840, logDelta 40, 8 slots, random 50 coefficients. Cut = log q_boot + "
            "R logDelta (bit_curve.boot_cutoff_bit). Last visible = last bit of the aligned "
            "curve (median-median) above 1e-2. Plateau = max of the aligned curve below the cut. "
            "Above = min-max of the aligned curve over the bits >= cut, and max over every "
            "cell. P = P(SDC) over [0, 840).")
    rows = []
    for pipe in ("mul x4", "mul; boot", "mul x2; boot", "mul x3; boot", "mul x4; boot",
                 "mul x5; boot"):
        for st in ("encrypt_c0", "encrypt_c1"):
            e = rel.one(rep, "client", **(BOOTP | dict(stage=st, pipeline=pipe)))
            if e is None:
                continue
            d = rel.cells("client", e)
            c, cm = curve(d, "al"), curve(d, "al", "l2_rel", "mean")
            cut = boot_cutoff_bit(e)
            vis = first_last(c)
            if np.isfinite(cut):
                cut = int(cut)
                ab, cab = c[c.index >= cut], d[d["bit"] >= cut]
                rows.append([st, pipe, cut, frange(vis), fsci(c.get(cut - 1, np.nan)),
                             fsci(c[c.index < cut].max()), fsci(cm[cm.index < cut].max()),
                             f"{fsci(ab.min())}..{fsci(ab.max())}", fsci(cab["l2_rel"].max()),
                             fnum(p_module(d, 840), 3), fnum(p_module(d, 840, "al"), 3)])
            else:
                rows.append([st, pipe, "-", frange(vis), "-", fsci(c.max()), fsci(cm.max()), "-",
                             "-", fnum(p_module(d, 840), 3), fnum(p_module(d, 840, "al"), 3)])
    rep.table(["stage", "pipeline", "cut", "visible al", "E at cut-1", "plateau med",
               "plateau mean", "above (curve)", "above (cells)", "P", "P al"], rows)

    rep.how("mul x5; boot, bits from the cut to 839: P(SDC) per sampled bit (range and "
            "median), P over [cut, 840) interpolated, worst slot (max over the cells of "
            "linf_rel_max) and max E_L2 (mean over repetitions).")
    for st in ("encrypt_c0", "encrypt_c1"):
        e = rel.one(rep, "client", **(BOOTP | dict(stage=st, pipeline="mul x5; boot")))
        if e is None:
            continue
        d = rel.cells("client", e)
        cut = int(boot_cutoff_bit(e))
        x = d[d["bit"] >= cut]
        r = rate_per_bit(x)
        rep.num(f"{fnum(r.min())}-{fnum(r.max())} (med {fnum(r.median())})",
                f"{st}: P(SDC) per bit above the cut")
        rep.num(fnum(p_module(x, 840, lo=cut), 3), f"{st}: P(SDC) over [{cut}, 840)")
        rep.num(fnum(x["linf_rel_max"].max()), f"{st}: worst slot, max relative error")
        rep.num(fsci(x["l2_rel"].max()), f"{st}: max E_L2 above the cut")


@section(6)
def ch6_bursts(rel, rep, args):
    rep.section("6.10", "Bursts of k bits (mb_fig01, mb_fig02, ev_mb_*)")
    rep.how("burst_enc: HEAAN, no pipeline, logDelta 40, 32 slots. top = b + k - 1. First top "
            "visible: aligned curve (median-median) per top bit. P(top = t): P(SDC) of the "
            "injections with that top bit. P inside: over the start bits [0, 60 - k] (bursts "
            "entirely inside the module). Offsets vs. k = 1 at the same top bit, over tops "
            "36-58, coefficient N/2 left out: arithmetic = log2 of the ratio of the mean E_L2 "
            "(mean over coefficients of the mean over reps), median and max |.|; log = mean "
            "over the tops of (mean log2 E_L2 at k) - (same at k = 1). Prediction of the log "
            "offset: mean of log2(m) over odd m < 2^k, minus k - 1.")
    for st in ("encrypt_c0", "encrypt_c1"):
        ref = None
        rows = []
        for k in (1, 2, 4, 8):
            e = rel.one(rep, "burst", **(NULL40 | dict(stage=st, amountBits=k)))
            if e is None:
                continue
            d = rel.cells("burst", e).copy()
            d["top"] = d["bit"] + k - 1
            p_inside = rate_per_bit(d).loc[: 60 - k].mean()
            ptop = [fnum(rate_per_bit(d.assign(bit=d["top"])).get(t, np.nan)) for t in (34, 35, 36)]
            d = d[d["coeff"] != 32]           # N/2 of c0 is always 0: out of the offsets
            c_top = d[d["aligned"]].groupby("top")["l2_rel_median"].median()
            vis_start = first_last(curve(d, "al"))
            arith = d.groupby("top")["l2_rel"].mean()
            logm = d.groupby("top")["err_bits"].mean()
            pred = float(np.mean(np.log2(np.arange(1, 2 ** k, 2)))) - (k - 1)
            if k == 1:
                ref = (arith, logm)
                offs = ["-", "-", "-", "-", fnum(pred)]
            else:
                da = np.log2(arith / ref[0]).loc[36:58]
                dl = (logm - ref[1]).loc[36:58]
                msb = np.log2(arith / ref[0]).get(59, np.nan)
                offs = [fnum(da.abs().median()), fnum(da.abs().max()), fnum(dl.mean()),
                        fnum(msb), fnum(pred)]
            rows.append([k, fbit(first(c_top)), vis_start[1] if vis_start else "-", *ptop,
                         fnum(p_inside, 3), *offs])
        rep.table([f"{st} k", "first top vis", "last start vis", "P(top=34)", "P(35)",
                   "P(36)", "P inside", "arith med", "arith max", "log offset", "top 59",
                   "pred log"], rows)

    rep.how("burst_boot: mul x4; boot, logQ 840. Last start bit visible (aligned, median-"
            "median), its top bit, max E_L2 over the cells starting at or above the cut, P(SDC) "
            "over the start bits [0, 840 - k].")
    rows = []
    for st in ("encrypt_c0", "encrypt_c1"):
        for k in (1, 2, 4, 8):
            e = rel.one(rep, "burst", **(BOOTP | dict(stage=st, pipeline="mul x4; boot",
                                                      amountBits=k)))
            if e is None:
                continue
            d = rel.cells("burst", e)
            vis = first_last(curve(d, "al"))
            cut = int(boot_cutoff_bit(e))
            rows.append([st, k, cut, vis[1] if vis else "-", vis[1] + k - 1 if vis else "-",
                         fsci(d.loc[d["bit"] >= cut, "l2_rel"].max()),
                         fnum(p_module(d, 840 - k + 1), 3), fnum(p_module(d, 840 - k + 1, "al"), 3)])
    rep.table(["stage", "k", "cut", "last start vis", "its top", "max E above", "P", "P al"], rows)

    rep.how("burst_rns: OpenFHE, 4 limbs, add; rot 3, 8 slots. P(SDC) over the start bits "
            "inside the module of each limb (weighted), OOR, min over bits of the aligned curve.")
    rows = []
    for st in ("encrypt_c0", "encrypt_c1"):
        for k in (1, 2, 4, 8):
            e = rel.one(rep, "burst", **(OFHE | dict(stage=st, pipeline="add; rot 3",
                                                     mult_depth=3, logSlots=3, amountBits=k)))
            if e is None:
                continue
            d = rel.cells("burst", e)
            ws = {l: w - k + 1 for l, w in limb_widths(e, d).items()}
            rows.append([st, k, fnum(p_limbs(d, ws)), fnum(p_limbs(d, ws, "al")),
                         fnum(p_limbs(d, ws, "other")), fnum(d["out_of_range"].mean()),
                         fsci(curve(d, "al").min())])
    rep.table(["stage", "k", "P", "P al", "P other", "OOR", "min E al"], rows)

    rep.how("burst_op_mul: server mul (config of c2_fig03), representative steps. First top "
            "bit visible (aligned, median-median), P(SDC) over the start bits [0, W - k], W = 60 "
            "or 120 (key switching steps).")
    rows = []
    for _, e in rel.find("burst", **OP_MUL).sort_values(["op_step", "amountBits"]).iterrows():
        d = rel.cells("burst", e)
        k = int(e["amountBits"])
        W, _ = module_width(e)
        f = first(curve(d, "al"))
        rows.append([int(e["op_step"]), k, W, "-" if f is None else f + k - 1,
                     fnum(p_module(d, W - k + 1))])
    rep.table(["step", "k", "W", "first top vis", "P"], rows)


# --------------------------------------------------------------------------------------
# Chapter 7
# --------------------------------------------------------------------------------------
def step_row(rel, part, e):
    """Columns shared by every per-step table of Chapter 7."""
    d = rel.cells(part, e)
    W, capped = module_width(e)
    al, ot = curve(d, "al"), curve(d, "other")
    v_al, v_ot = first_last(al), first_last(ot)
    m = first(curve(d, "al", "linf_rel_median") * 100, MREP_PCT)
    above = d[d["bit"] >= W]
    labels = STEP_LABELS.get(e["stage"])
    s = int(e["op_step"])
    return [int(e["op_depth"]), s, labels[s] if labels and s < len(labels) else "",
            f"{W}{'*' if capped else ''}", frange(v_al), frange(v_ot),
            "-" if m is None else m, "-" if (m is None or v_al is None) else v_al[0] - m,
            fnum(p_module(d, W)), fnum(p_module(d, W, "al")), fnum(p_module(d, W, "other")),
            fsci(above["l2_rel_median"].max()) if len(above) else "-"]


STEP_HEADER = ["depth", "step", "flips", "W", "visible al", "visible other", "MREP al",
               "lead", "P", "P al", "P other", "max E above W"]
STEP_HOW = ("One row per op_step (and op_depth). W = bits of the module at the injection "
            "point (* = cut at bitsPerCoeff). Visible = E_L2 curve (median-median) > 1e-2, "
            "aligned / non-aligned. MREP al = first bit where the worst slot exceeds 1 %; lead "
            "= first visible E_L2 bit - that bit. P = P(SDC) over [0, W): all, aligned, "
            "non-aligned. Max E above W = max E_L2 (median over reps) of the cells at bits >= W.")


def op_section(rel, rep, sid, title, f, part="server"):
    rep.section(sid, title)
    exps = rel.find(part, **f)
    if exps.empty:
        rep.missing(f"{part}: {fdict(f)}")
        return
    rep.how(STEP_HOW)
    one_depth = exps["op_depth"].nunique() == 1
    rep.how("Config: " + describe(exps.iloc[0], ("op_depth",) if one_depth else ()))
    rep.table(STEP_HEADER, [step_row(rel, part, e) for _, e in
                            exps.sort_values(["op_depth", "op_step"]).iterrows()])


@section(7)
def ch7_ops(rel, rep, args):
    op_section(rel, rep, "7.1", "add (second add of 'add x2', level 60) - c2_fig01", OP_ADD)
    op_section(rel, rep, "7.2", "pmul (second pmul of 'pmul x2', level 90) - c2_fig02", OP_PMUL)
    op_section(rel, rep, "7.3", "mul (one mul, level 60, key switching mod 2^120) - c2_fig03", OP_MUL)
    op_section(rel, rep, "7.4", "chain of three muls 'mul x3', logQ 160 - ev_mul_depth", OP_MUL_DEPTH)
    op_section(rel, rep, "7.5", "rescale ('mul x2', logQ 100) - c2_fig04", OP_RESCALE)
    op_section(rel, rep, "7.6", "rot 2 (level 60) - c2_fig05", OP_ROT)


@section(7)
def ch7_lead(rel, rep, args):
    rep.section("7.7", "How many bits earlier the worst slot crosses 1 % (MREP vs E_L2)")
    rep.how("Per operation: min-max over its steps of (first visible E_L2 bit - first MREP > 1 % "
            "bit), aligned coefficients, steps where both exist and the output is not destroyed "
            "from bit 0.")
    rows = []
    for name, f in (("add", OP_ADD), ("pmul", OP_PMUL), ("mul", OP_MUL), ("rescale", OP_RESCALE),
                    ("rot", OP_ROT)):
        leads = []
        for _, e in rel.find("server", **f).iterrows():
            d = rel.cells("server", e)
            v = first(curve(d, "al"))
            m = first(curve(d, "al", "linf_rel_median") * 100, MREP_PCT)
            if v is not None and v > 0 and m is not None:     # v = 0: destroyed from bit 0
                leads.append(v - m)
        rows.append([name, f"{min(leads)}-{max(leads)}" if leads else "-", len(leads)])
    rep.table(["operation", "lead (bits)", "steps"], rows)


@section(7)
def ch7_persistent(rel, rep, args):
    rep.section("7.8", "Persistent fault vs. fault in the read (c2_fig05b)")
    rep.how("For every step with a persistent-fault campaign (*_non_transient), the same step "
            "with the read fault (restore after the marked read). Columns as in 7.1.")
    rows = []
    for f_read, f_nt in ((OP_MUL, OP_MUL_NT), (OP_PMUL, OP_PMUL_NT), (OP_ROT, OP_ROT_NT)):
        nt = rel.find("server", **f_nt)
        if nt.empty:
            rep.missing(f"server: {fdict(f_nt)}")
            continue
        for _, e in nt.sort_values("op_step").iterrows():
            r = rel.one(rep, "server", **(f_read | dict(op_step=int(e["op_step"]))))
            for model, x in (("read", r), ("persistent", e)):
                if x is not None:
                    rows.append([f_read["stage"], model] + step_row(rel, "server", x)[1:])
    rep.table(["op", "model"] + STEP_HEADER[1:], rows)

    e = rel.one(rep, "server", **(OP_MUL_NT | dict(op_step=10)))
    if e is not None:
        c = curve(rel.cells("server", e), "al")
        lc = np.log2(c[c > 0])
        rep.num(fnum(lc.loc[60:87].median(), 1),
                "mul step 10, persistent: log2 E_L2 (aligned), median over bits 60-87 (floor)")
        x = lc.loc[90:113]
        rep.num(fnum(np.polyfit(x.index, x.values, 1)[0], 3),
                "mul step 10, persistent: slope of log2 E_L2 over bits 90-113")
        rep.num(frange(first_last(c[c.index >= 60])),
                "mul step 10, persistent: visible range above bit 60")
    r1 = rel.one(rep, "server", **(OP_ROT | dict(op_step=1)))
    n2 = rel.one(rep, "server", **(OP_ROT_NT | dict(op_step=2)))
    if r1 is not None and n2 is not None:
        c1, c2 = curve(rel.cells("server", r1), "al"), curve(rel.cells("server", n2), "al")
        both = (c1 > 0) & (c2 > 0)
        q = np.log2(c2[both] / c1[both]).loc[:119]
        vis = q[c1.reindex(q.index) > TAU]
        rep.num(fnum(vis.abs().max(), 3),
                "rot: max |log2(persistent step 2 / read step 1)|, aligned, visible bits < 120")
        worst = q.abs().idxmax()
        rep.num(fnum(q.abs().max(), 3),
                f"same over every bit < 120 (largest at bit {worst}, where E_L2 = {fsci(c1[worst])})")
        d2 = rel.cells("server", n2)
        rep.num(f"{fnum(p_module(d2, 60))} / {fnum(p_module(d2, 120, lo=60))}",
                "rot step 2, persistent: P(SDC) over [0,60) / [60,120)")
        x = np.log2(c1[c1 > 0]).loc[60:116]
        rep.num(fnum(np.polyfit(x.index, x.values, 1)[0], 3),
                "rot step 1, read: slope of log2 E_L2 over bits 60-116 (above the module)")
        rep.num(frange(first_last(c1[c1.index >= 60])),
                "rot step 1, read: visible range above the module (bits >= 60)")


@section(7)
def ch7_mix(rel, rep, args):
    rep.section("7.9", "Mixed pipeline 'add; mul; rot 2; mul; add' with and without boot (c2_fig06)")
    rep.how("logQ 840, logDelta 40, random 50 coefficients. Fault inside the first (depth 0) "
            "or the second (depth 1) mul. Without boot: visible range (aligned), P(SDC) over "
            "[0, W) and max E_L2 over the cells. With boot: cut (counting the rescale of the "
            "mul hit), visible range, max of the aligned curve and of the cells at bits >= cut, "
            "and whether every cell above the cut is exactly 0.")
    rows = []
    for _, e in rel.find("server", **OP_MIX).sort_values(["op_depth", "op_step"]).iterrows():
        b = rel.one(rep, "server", **(OP_MIX_BOOT | dict(op_depth=int(e["op_depth"]),
                                                         op_step=int(e["op_step"]))))
        d = rel.cells("server", e)
        W, capped = module_width(e)
        row = [int(e["op_depth"]), int(e["op_step"]), f"{W}{'*' if capped else ''}",
               frange(first_last(curve(d, "al"))), fnum(p_module(d, W)),
               fsci(d["l2_rel"].replace(np.inf, np.nan).max())]
        if b is not None:
            db = rel.cells("server", b)
            cut = int(boot_cutoff_bit(b))
            cb = curve(db, "al")
            above = db[db["bit"] >= cut]
            row += [cut, frange(first_last(cb)), fsci(cb[cb.index >= cut].max()),
                    fsci(above["l2_rel"].max()), "yes" if (above["l2_rel"] == 0).all() else "no",
                    fnum(p_module(db, W))]
        rows.append(row)
    rep.table(["depth", "step", "W", "no boot: visible al", "P", "max E", "cut",
               "boot: visible al", "max curve above", "max cell above", "exact 0 above", "P"],
              rows)


@section(7)
def ch7_boot_inside(rel, rep, args):
    rep.section("7.10", "Faults inside the bootstrapping (c2_fig07)")
    rep.how("One repetition, random 50 coefficients. The module at each step is not logged: W "
            "is estimated as (last visible bit of the aligned or the non-aligned curve) + 1. "
            "P(SDC) over [0, W). boot: even step = c1, odd = c0.")
    for f, name in ((OP_BOOT, "boot (between stages, 8 slots)"),
                    (OP_BOOT_EVAL, "boot_eval (inside EvalExp, 4 slots)")):
        exps = rel.find("server", **f)
        if exps.empty:
            rep.missing(f"server: {fdict(f)}")
            continue
        rows = []
        for _, e in exps.sort_values("op_step").iterrows():
            d = rel.cells("server", e)
            v_al, v_ot = first_last(curve(d, "al")), first_last(curve(d, "other"))
            tops = [v[1] for v in (v_al, v_ot) if v]
            W = max(tops) + 1 if tops else int(e["logQ"])
            s = int(e["op_step"])
            lab = STEP_LABELS["boot"][s] if e["stage"] == "boot" else ("c1" if s % 2 == 0 else "c0")
            rows.append([s, lab, W, frange(v_al), frange(v_ot), fnum(p_module(d, W)),
                         fnum(p_module(d, W, "al")), fnum(p_module(d, W, "other"))])
        rep.how(name + ": " + describe(exps.iloc[0]))
        rep.table(["step", "flips", "W est.", "visible al", "visible other", "P", "P al",
                   "P other"], rows)


@section(7)
def ch7_boot_rule(rel, rep, args):
    rep.section("7.11", "Boot cut rule over every configuration with a boot after the fault (reg:boot)")
    rep.how("Every experiment (client, server, bursts) with a HEAAN boot after the injection "
            "point. cut = logDelta + 10 + R logDelta (bit_curve.boot_cutoff_bit, R counts the "
            "rescale of a mul hit inside); measured = last visible bit of the aligned curve "
            "(median-median) + 1; diff = measured - cut. One row per (part, pipeline, stage, "
            "logDelta): how many experiments (slots, k, op_step, numSamples differ) and the "
            "range of diff; then every experiment with diff != 0.")
    found = []
    for part in ("client", "server", "burst"):
        for _, e in rel.find(part).iterrows():
            if e["library"] != "heaan" or "boot" not in str(e["pipeline"]):
                continue
            cut = boot_cutoff_bit(e)
            if not np.isfinite(cut):
                continue
            v = first_last(curve(rel.cells(part, e), "al"))
            if v is not None:
                found.append(dict(part=part, stage=e["stage"], pipeline=e["pipeline"],
                                  logD=int(e["logDelta"]), depth=int(e["op_depth"]),
                                  e=e, cut=int(cut), diff=v[1] + 1 - int(cut)))
    if not found:
        rep.missing("no experiment with a boot after the fault")
        return
    df = pd.DataFrame(found)
    rows = []
    for key, g in df.groupby(["part", "pipeline", "stage", "logD", "depth"]):
        rows.append([*key, len(g), "/".join(map(str, sorted(g["cut"].unique()))),
                     f"{g['diff'].min()}..{g['diff'].max()}"])
    rep.table(["part", "pipeline", "stage", "logD", "depth", "experiments", "cut", "diff"], rows)
    odd = df[df["diff"] != 0]
    if len(odd):
        rep.table(["diff != 0: part", "stage", "pipeline", "logD", "slots", "k", "depth", "step",
                   "cut", "diff"],
                  [[r.part, r.stage, r.pipeline, r.logD, 1 << int(r.e["logSlots"]),
                    int(r.e["amountBits"]), r.depth, int(r.e["op_step"]), r.cut, r.diff]
                   for r in odd.itertuples()])
    rep.num(str(len(df)), "experiments")
    rep.num(str(int((df["diff"].abs() <= 1).sum())), "with |diff| <= 1")
    rep.num(str(int((df["diff"] == 0).sum())), "with diff = 0")


# --------------------------------------------------------------------------------------
# Chapter 8
# --------------------------------------------------------------------------------------
NN_CLIENT = ["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"]


def nn_rate(d, parity=None, col="misclassified"):
    if parity is not None:
        d = d[d["coeff"] % 2 == parity]
    return rate_per_bit(d, col)


@section(8)
def ch8_table(rel, rep, args):
    rep.section("8.1", "Client stages of the network (tab:nn-cliente)")
    if "nn" not in rel.dirs:
        rep.missing("needs --nn")
        return
    run_script(rep, ["nn_table.py", "--results", str(rel.dirs["nn"]), "--where", "library=heaanNN"])

    rep.section("8.2", "Sample of the network campaigns")
    c = rel.find("nn", library="heaanNN")
    e = c.iloc[0]
    rep.num(str(len(set(";".join(c["seed_inputs"].astype(str)).split(";")))), "images")
    rep.num(str(len(set(";".join(c["seeds"].astype(str)).split(";")))), "key seeds")
    rep.num(str(e["numSamples"]), "coefficients sampled per image")
    rep.num(f"{e['logN']} / {e['logSlots']} / {e['logQ']} / {e['logDelta']}",
            "logN / logSlots / logQ / logDelta")
    rep.num(fint(c["total_bitFlips"].sum()), "injections, every stage")
    rep.num(fnum(math.log2(math.sqrt(H_NN / 2)), 1),
            "log2 sqrt(h / g), h = 64, g = 2: expected shift of c1 vs c0 (bits)")


@section(8)
def ch8_parity(rel, rep, args):
    rep.section("8.3", "Client stages by parity of the coefficient (gap 2: even = aligned)")
    rep.how("P(misclassification) per sampled bit, injections pooled over images and "
            "coefficients of each parity. Window = first-last bit with P > 0. Moved = the "
            "logits change by more than 0.1 % (misclassified + tolerable_sdc): first bit where "
            "that fraction is > 0 and >= 0.5.")
    rows = []
    for st in NN_CLIENT:
        e = rel.one(rep, "nn", library="heaanNN", stage=st)
        if e is None:
            continue
        d = rel.cells("nn", e)
        out = [st]
        for par in (0, 1):
            r = nn_rate(d, par)
            hit = r[r > 0].index
            out.append(f"{hit.min()}-{hit.max()}" if len(hit) else "none")
        moved = nn_rate(d, None, "misclassified") + nn_rate(d, None, "tolerable_sdc")
        out += [fbit(first(moved, 0.0)), fbit(first(moved, 0.5 - 1e-12))]
        rows.append(out)
    rep.table(["stage", "window even", "window odd", "moved > 0", "moved >= 0.5"], rows)

    rep.how("encrypt_c0 / encrypt_c1: P per parity at the first and last sampled bits of the "
            "window (where the parities differ).")
    for st in ("encrypt_c0", "encrypt_c1"):
        e = rel.one(rep, "nn", library="heaanNN", stage=st)
        if e is None:
            continue
        d = rel.cells("nn", e)
        ev, od = nn_rate(d, 0), nn_rate(d, 1)
        both = pd.DataFrame({"even": ev, "odd": od}).fillna(0)
        hit = both.index[(both > 0).any(axis=1)]
        if not len(hit):
            continue
        bits = both.index[(both.index >= hit.min()) & (both.index <= hit.max())]
        edge = sorted(set(bits[:5]) | set(bits[-5:]) | set(both.index[both.index > hit.max()][:2]))
        rep.table([f"{st} bit"] + [str(b) for b in edge],
                  [["P even"] + [fnum(both.loc[b, "even"]) for b in edge],
                   ["P odd"] + [fnum(both.loc[b, "odd"]) for b in edge]])


@section(8)
def ch8_internal(rel, rep, args):
    rep.section("8.4", "Steps inside the network, by parity")
    rep.how("Per stage and op_step: window (first-last sampled bit with P(mis) > 0) and median "
            "P(mis) over the sampled bits 60-180, even / odd coefficients.")
    exps = rel.find("nn", library="heaanNN")
    exps = exps[~exps["stage"].isin(NN_CLIENT)]
    rows = []
    for _, e in exps.sort_values(["stage", "op_step"]).iterrows():
        d = rel.cells("nn", e)
        out = [e["stage"], int(e["op_step"])]
        for par in (0, 1):
            r = nn_rate(d, par)
            hit = r[r > 0].index
            out += [f"{hit.min()}-{hit.max()}" if len(hit) else "none",
                    fnum(r.loc[60:180].median())]
        rows.append(out)
    rep.table(["stage", "step", "window even", "med 60-180 even", "window odd",
               "med 60-180 odd"], rows)


# ======================================================================================
# Main
# ======================================================================================
def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--client", help="client results (RES1)")
    p.add_argument("--server", help="server results (RES2)")
    p.add_argument("--burst", help="burst results (RES_BURST)")
    p.add_argument("--nn", help="network results (RES_NN)")
    p.add_argument("--out", default="numbers.txt")
    p.add_argument("--only", nargs="+", type=int, default=None, metavar="CHAPTER",
                   help="only these chapters (4 to 8)")
    return p.parse_args()


def header(rel):
    lines = ["Numbers of the thesis computed from the data (thesis_numbers.py)",
             f"Generated: {datetime.datetime.now():%Y-%m-%d %H:%M}"]
    for part, d in rel.dirs.items():
        version = d.parent / "VERSION"
        tag = f"  (release built from fi-ckks {version.read_text().strip()[:7]})" if version.exists() else ""
        lines.append(f"{part:7s} {d}{tag}")
    # The definitions of the module docstring, so the file can be read on its own.
    defs = __doc__.split("Definitions shared", 1)[1].split("A configuration missing", 1)[0]
    lines += ["", "Definitions shared" + defs.rstrip()]
    return "\n".join(lines)


def main():
    args = parse_args()
    rel = Release({"client": args.client, "server": args.server, "burst": args.burst,
                   "nn": args.nn})
    rep = Report()
    rep.out.append(header(rel))
    done = set()
    for chapter, f in SECTIONS:
        if args.only and chapter not in args.only:
            continue
        if chapter not in done:
            rep.chapter(CHAPTERS[chapter])
            done.add(chapter)
        print(f"  {f.__name__}", file=sys.stderr)
        try:
            f(rel, rep, args)
        except Exception:                                  # one broken section, not the file
            rep.out.append(f"  ERROR in {f.__name__}:")
            rep.raw(traceback.format_exc())
    Path(args.out).write_text(rep.text())
    print(f"-> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
