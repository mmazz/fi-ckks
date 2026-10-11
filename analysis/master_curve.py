#!/usr/bin/env python3
"""Master curve of the one-bit law (analytical chapter, Prop. prop:ley).

For every configuration where the fault reaches the output additively, the normalized
error  y = log2(E_L2) + log2(sqrt(2) rms(z) / kappa)  should equal  x = b - log2(Delta_r):
slope 1, intercept 0. Uses aligned coefficients only (coefficient 0 and N/2 excluded) and
c1 only without gap (factor sqrt(h), Prop. prop:c1).

    python3 master_curve.py --client <client results> --server <server results> [--plot out.pdf]
"""
import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
from utils.results import load_campaigns  # noqa: E402  (raw or collapsed results dir)

H = 4                                    # Hamming weight of s for logN = 6 (HEAAN)


def rms_pow(k):
    """rms of x^k for x uniform in [-1, 1]."""
    return 1 / math.sqrt(2 * k + 1)


def rms_interval(a):
    """rms of x uniform in [2^a, 2^(a+1)]."""
    return 2 ** a * math.sqrt(7 / 3)


# (family, release part, pandas query, log2 Delta_r, rms(z), c1 factor, first bit of the fit,
#  top bit of the register)
def configs():
    out = []
    base = "library=='heaan' and isExhaustive==1 and logN==6"
    for D in (25, 35, 40, 45, 55):
        q = f"{base} and pipeline=='' and stage=='{{st}}' and logSlots==5 and logQ==60 and logDelta=={D} and bitsPerCoeff==64 and logMin==0"
        for st, c1 in (("encrypt_c0", 0), ("encrypt_c1", 1)):
            out.append(("client, no operations", "client", q.format(st=st), D, rms_pow(1), c1, 0, 60))
    for Q, D in ((40, 30), (80, 60), (100, 75)):
        q = f"{base} and pipeline=='' and stage=='encrypt_c0' and logQ=={Q} and logDelta=={D}"
        out.append(("client, no operations", "client", q, D, rms_pow(1), 0, 0, Q))
    for a in (0, 9, 19, 29):
        q = f"{base} and pipeline=='' and stage=='encrypt_c0' and logDelta==20 and logMin=={a}"
        out.append(("client, no operations", "client", q, 20, rms_interval(a), 0, 0, 60))
    for ls in (3, 4):
        q = f"{base} and pipeline=='' and stage=='encrypt_c0' and logSlots=={ls} and logQ==60 and logDelta==40 and bitsPerCoeff==64"
        out.append(("client, no operations", "client", q, 40, rms_pow(1), 0, 0, 60))
    for ls in (3, 4, 5):
        q = f"library=='heaan' and pipeline=='add; rot 3' and stage=='encrypt_c0' and logSlots=={ls}"
        out.append(("client, with operations", "client", q, 30, 2 * rms_pow(1), 0, 0, 60))
    q = "library=='heaan' and pipeline=='add; rot 3' and stage=='encrypt_c1' and logSlots==5"
    out.append(("client, with operations", "client", q, 30, 2 * rms_pow(1), 1, 0, 60))
    for st in ("decrypt_c0", "decode"):
        q = f"library=='heaan' and pipeline=='mul x3' and stage=='{st}'"
        out.append(("client, with operations", "client", q, 30, rms_pow(4), 0, 0, 60))
    for s in (2, 3, 5):
        out.append(("server, add and rot", "server", f"stage=='add' and op_depth==1 and op_step=={s}",
                    30, 3 * rms_pow(1), 0, 0, 60))
    for s in (0, 8, 9, 10):
        out.append(("server, add and rot", "server", f"stage=='rot' and op_step=={s}", 30, rms_pow(1), 0, 0, 60))
    # registers followed by a rescale: below log Delta the change rounds to 0 or 1 (Lemma lem:rescale)
    for s in (22, 23, 25):
        out.append(("server, mul and rescale", "server", f"stage=='mul' and pipeline=='mul' and op_step=={s}",
                    60, rms_pow(2), 0, 31, 60))
    out.append(("server, mul and rescale", "server", "stage=='rescale' and op_depth==1 and op_step==1",
                60, rms_pow(3), 0, 31, 70))
    out.append(("server, mul and rescale", "server", "stage=='rescale' and op_depth==1 and op_step==3",
                30, rms_pow(3), 0, 0, 40))
    out.append(("server, mul and rescale", "server", "stage=='pmul' and pipeline=='pmul x2' and op_step==5",
                60, rms_pow(3), 0, 31, 90))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client", required=True, help="collapsed client results (RES1)")
    ap.add_argument("--server", required=True, help="collapsed server results (RES2)")
    ap.add_argument("--plot", default=None)
    args = ap.parse_args()
    dirs = {"client": Path(args.client), "server": Path(args.server)}
    # one row per experiment; data_file is relative (collapsed dir) or absolute (raw dir,
    # whose collapsed cache load_campaigns brings up to date), so dir / data_file works in both
    camps = {p: load_campaigns(d) for p, d in dirs.items()}

    rows, points, missing = [], [], []
    for fam, part, q, logD, rms, c1, lo, top in configs():
        sel = camps[part].query(q)
        if len(sel) > 1:
            sys.exit(f"ERROR: {len(sel)} experiments for {q} (the query must pick exactly one)")
        if len(sel) == 0:
            # older releases do not have every campaign (e.g. TAG_V6 has no pmul)
            missing.append(f"{part}: {q}")
            continue
        r = sel.iloc[0]
        y = pd.read_csv(dirs[part] / r.data_file)
        gap = 2 ** (int(r.logN) - 1 - int(r.logSlots))
        nh = 2 ** (int(r.logN) - 1)
        y = y[(y.coeff % gap == 0) & (y.coeff != 0) & (y.coeff != nh) & (y.bit >= lo) & (y.bit <= top - 2)]
        g = y.groupby("bit").l2_rel_median.median()
        g = g[g > 0]
        x = g.index.values - logD
        yn = np.log2(g.values) + math.log2(math.sqrt(2) * rms) - (math.log2(math.sqrt(H)) if c1 else 0)
        slope, icpt = np.polyfit(x, yn, 1)
        resid = yn - x
        rows.append(dict(family=fam, config=f"{part}: {q.split('and', 3)[-1][:60]}", n_bits=len(x),
                         slope=slope, intercept=icpt, rms_resid=float(np.sqrt(np.mean(resid ** 2)))))
        points.append((fam, x, yn))

    for m in missing:
        print(f"WARNING: not in this release, skipped: {m}")
    if not rows:
        sys.exit("ERROR: none of the configurations is in this release")
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    print(df.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    allx = np.concatenate([p[1] for p in points])
    ally = np.concatenate([p[2] for p in points])
    s, i = np.polyfit(allx, ally, 1)
    print(f"\n{len(df)} configurations, {len(allx)} points (bit, configuration)")
    print(f"per-configuration slope: mean {df.slope.mean():.4f}, min {df.slope.min():.4f}, max {df.slope.max():.4f}")
    print(f"per-configuration intercept: mean {df.intercept.mean():+.3f}, min {df.intercept.min():+.3f}, max {df.intercept.max():+.3f} bits")
    print(f"global fit: slope {s:.4f}, intercept {i:+.3f} bits; rms of y - x = {np.sqrt(np.mean((ally - allx) ** 2)):.3f} bits")

    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        colors = {"client, no operations": "#2a78d6", "client, with operations": "#eb6834",
                  "server, add and rot": "#1baf7a", "server, mul and rescale": "#eda100"}
        markers = {"client, no operations": "o", "client, with operations": "s",
                   "server, add and rot": "^", "server, mul and rescale": "D"}
        fig, ax = plt.subplots(figsize=(7.5, 4.6))
        lim = (min(allx) - 2, max(allx) + 2)
        ax.plot(lim, lim, color="#52514e", lw=1.2, ls="--", zorder=1, label="prediction $y = x$")
        seen = set()
        for fam, x, yn in points:
            ax.scatter(x, yn, s=14, marker=markers[fam], facecolors="none", edgecolors=colors[fam],
                       linewidths=0.9, zorder=2, label=None if fam in seen else fam)
            seen.add(fam)
        ax.set_xlim(*lim)
        ax.set_xlabel(r"$b - \log_2\Delta_r$", fontsize=13)
        ax.set_ylabel(r"$\log_2 E_{L_2} + \log_2(\sqrt{2}\,\mathrm{rms}(\mathbf{z})/\kappa)$", fontsize=13)
        ax.grid(color="#e4e3df", lw=0.6)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.legend(frameon=False, fontsize=10, loc="upper left")
        fig.tight_layout()
        fig.savefig(args.plot, bbox_inches="tight")
        fig.savefig(str(Path(args.plot).with_suffix(".png")), bbox_inches="tight", dpi=130)
        print(f"-> {args.plot}")


if __name__ == "__main__":
    main()
