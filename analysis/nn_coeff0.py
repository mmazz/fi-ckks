#!/usr/bin/env python3
"""Coefficient-0 NN campaigns (random mode with numSamples=0: coefficient 0 of every limb,
the random subset of bits) next to the random campaigns of the same config.

    cd analysis
    python3 nn_coeff0.py --coeff0 ../results_NN_coeff0 --random ../results_NN

For every config (library, stage, ...) found in --coeff0:

  1. Detection rate and P(mis) at coefficient 0, and P(mis & undetected): misclassifications
     the OpenFHE check did not flag. Printed with a one-line verdict.
  2. The same numbers for the random coefficients of the same config (--random, numSamples
     is the only column allowed to differ), split into aligned (coeff % gap == 0, coeff != 0,
     gap = (N/2) / slots) and other.
  3. P(mis) per bit (table + figure). HEAAN: a model line next to the data.
       decrypt_c0: coefficient 0 of c0 is uniform mod q, so a flip moves every slot by
                   +-2^(bit - logDelta) with a random sign: P(mis) = 0.5 once that exceeds
                   the margin (correct logit - best other), 0 for bit >= logq.
       decode:     coefficient 0 of the plaintext is round(Delta * logit) mod 2^logq (every
                   slot holds the logit), so the flip is deterministic. The model flips that
                   integer and checks the class; the data is also split by the sign of the
                   correct logit.
     OpenFHE RNS: one row per limb, coefficient 0 should look the same in every limb.
  4. Per image: label, correct logit, margin and the onset bit logDelta + log2(margin).
  5. Counts k/n with 95% Wilson intervals for coefficient 0, including logit corruption and
     SDC (output altered, i.e. misclassified or some logit beyond 0.1%, and not detected).
     The logit corruption column is --corrupt_col, or the first of CORRUPT_CANDIDATES found.

The random campaigns are matched on every config column except numSamples and the seeds, and
then restricted to the images and key seeds of the coefficient-0 campaigns, so both sides
average over the same inputs. With withNTT=1 the random coefficients form one group, since
an NTT index has no parity. HEAAN encode: if the bits run past logQ they are shown as
bit - logP, as in the paper.

Golden logits: plain forward of the network (weights + mnist_test.csv from $FI_NN_DATA or
workloads/nn/data), the reference the C++ checks the CKKS baseline against. Without
mnist_test.csv the model lines and the sign split are skipped.

Expected for OpenFHE with withNTT=0: detection 0 at decrypt_c0. The check (fork,
CKKSPackedEncoding::Decode) estimates the noise from m(X) - m(1/X) on the COEFFICIENTS,
before the FFT. Coefficient 0 maps to itself under X -> 1/X, so it cancels exactly and the
real part at index 0 is left out of the estimate: a change confined to coefficient 0 cannot
move it. With withNTT=1 index 0 is an evaluation point, not coefficient 0.
"""
import argparse
import math
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
from utils.results import config_columns, is_collapsed, load_campaigns, load_data  # noqa: E402

IMG_DIR = Path(__file__).resolve().parent / "img"
NN_DATA = Path(os.environ.get("FI_NN_DATA",
                              Path(__file__).resolve().parent.parent / "workloads/nn/data"))
NN_LEVELS = 5          # levels the network spends (W1, x^2, x^3, -0.23*x^3, W2), heaan_nn.cpp
# Only numSamples may differ between a coefficient-0 campaign and its random counterpart.
# Seed columns are not matched one to one, the random side is restricted to the seeds of the
# coefficient-0 group instead (random_match).
NOT_MATCHED = {"numSamples"}
SEED_PREFIX = "seed"
# Labels of the first ten MNIST test images, to check that seed_input is the image index.
MNIST_FIRST = [7, 2, 1, 0, 4, 1, 4, 9, 5, 9]
# Possible names of the per-injection flag "some logit moved beyond 0.1%".
CORRUPT_CANDIDATES = ["logit_corrupted", "corrupted", "logit_changed", "logits_changed",
                      "logit_moved"]
# Fixed order: coefficient 0 is always the first color. Validated (light surface).
COLORS = {"coeff 0": "#AA3377", "coeff 0, logit > 0": "#AA3377",
          "coeff 0, logit < 0": "#EE7733", "coeff 0, limb 0": "#AA3377",
          "coeff 0, limb 1": "#EE7733", "coeff 0, limb 2": "#CCBB44",
          "random aligned": "#2B7BBA", "random other": "#31A354", "random": "#2B7BBA",
          "model": "#555555"}
STYLES = {"coeff 0": ("-", "o"), "coeff 0, logit > 0": ("-", "o"),
          "coeff 0, logit < 0": ("-", "s"), "coeff 0, limb 0": ("-", "o"),
          "coeff 0, limb 1": ("-", "s"), "coeff 0, limb 2": ("-", "D"),
          "random aligned": ("--", "^"), "random other": (":", "v"), "random": ("--", "^"),
          "model": ("-", None)}
METRICS = ["detected", "misclassified", "mis_undetected", "corrupted", "sdc"]
LABELS = {"detected": "detected", "misclassified": "P(mis)", "mis_undetected": "mis & undet",
          "corrupted": "logit corr.", "sdc": "SDC"}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--coeff0", required=True, help="results dir of the coefficient-0 campaigns")
    p.add_argument("--random", default=None, help="results dir of the random campaigns")
    p.add_argument("--title", default="nn_coeff0", help="prefix of the figures")
    p.add_argument("--corrupt_col", default=None,
                   help="column flagging 'some logit moved beyond 0.1%%' (default: first of "
                        + ", ".join(CORRUPT_CANDIDATES) + " found)")
    p.add_argument("--no_show", action="store_true")
    return p.parse_args()


# ------------------------------------------------------------------------------ data

def load(results_dir):
    """Campaigns and rows. Raw dirs keep one row per injection (needed for the per-image
    split and P(mis & undetected)); a collapsed dir gives per-cell means, weighted by n_seeds."""
    camps = load_campaigns(results_dir, raw=True)
    return camps, results_dir


_warned_corrupt = False


def corrupt_column(data, wanted):
    """Name of the logit corruption column, or None (warns once)."""
    global _warned_corrupt
    if wanted:
        if wanted in data.columns:
            return wanted
        msg = f"--corrupt_col {wanted} not in the data"
    else:
        found = [k for k in CORRUPT_CANDIDATES if k in data.columns]
        if found:
            return found[0]
        msg = "no logit corruption column found"
    if not _warned_corrupt:
        print(f"WARNING: {msg}; logit corruption and SDC are left empty. "
              f"Columns: {', '.join(map(str, data.columns))}")
        _warned_corrupt = True
    return None


def rows(camps, results_dir, corrupt_col=None):
    data = load_data(camps, results_dir)
    # HEAAN has no check: an empty 'detected' means not detected.
    det = data["detected"].astype(float).fillna(0.0)
    mis = data["misclassified"].astype(float)
    col = corrupt_column(data, corrupt_col)
    cor = data[col].astype(float) if col else pd.Series(np.nan, index=data.index)
    data["corrupted"] = cor
    if is_collapsed(camps):
        # needs the injections, not their means
        data["mis_undetected"] = np.nan
        data["sdc"] = np.nan
    else:
        data["mis_undetected"] = mis * (1.0 - det)
        # altered output: misclassified or some logit beyond the threshold
        data["sdc"] = np.maximum(mis, cor) * (1.0 - det) if col else np.nan
    return data


def wmean(d, by=None):
    """Mean of METRICS (weighted by n_seeds on collapsed data), and n injections."""
    w = d["n_seeds"].astype(float) if "n_seeds" in d.columns else pd.Series(1.0, index=d.index)
    x = d[METRICS].astype(float).mul(w, axis=0)
    x["n"] = w
    if by is None:
        s = x.sum(min_count=1)
        out = s[METRICS] / s["n"]
        out["n"] = s["n"]
        return out
    g = x.groupby(d[by]).sum(min_count=1)
    out = g[METRICS].div(g["n"], axis=0)
    out["n"] = g["n"]
    return out


def random_match(group, rnd_camps):
    """Random campaigns with the config of the coefficient-0 group (numSamples aside),
    restricted to the images and key seeds of the group.

    Matching every config column against group.iloc[0] would keep only the seeds of its
    first row, so seed columns are matched as sets instead."""
    if rnd_camps is None:
        return None
    c = group.iloc[0]
    cols = [k for k in config_columns(rnd_camps)
            if k not in NOT_MATCHED and not k.startswith(SEED_PREFIX) and k in c.index]
    mask = np.ones(len(rnd_camps), dtype=bool)
    for k in cols:
        mask &= (rnd_camps[k].astype(str) == str(c[k])).to_numpy()
    if not mask.any():
        return None
    seeds = [k for k in group.columns if k.startswith(SEED_PREFIX) and k in rnd_camps.columns]
    smask = mask.copy()
    for k in seeds:
        smask &= rnd_camps[k].astype(str).isin(set(group[k].astype(str))).to_numpy()
    if smask.any():
        return rnd_camps[smask]
    print(f"WARNING: no random campaign shares the seeds ({', '.join(seeds)}) of "
          f"{c['library']} {c['stage']}: comparing against all of its seeds")
    return rnd_camps[mask]


# ----------------------------------------------------------------------- golden logits

def golden_logits(images):
    """{image index: 10 plain logits}, the same forward as workloads/nn/mnist.cpp."""
    csv = NN_DATA / "mnist_test.csv"
    if not csv.exists():
        print(f"WARNING: {csv} not found: no golden logits, no model lines and no sign split")
        return {}, {}
    w = NN_DATA / "weights"
    W1 = np.loadtxt(w / "W1.csv", delimiter=",")
    b1 = np.loadtxt(w / "b1.csv", delimiter=",").ravel()
    W2 = np.loadtxt(w / "W2.csv", delimiter=",")
    b2 = np.loadtxt(w / "b2.csv", delimiter=",").ravel()
    raw = pd.read_csv(csv, header=None, nrows=max(images) + 2)
    if not str(raw.iloc[0, 0]).strip().isdigit():          # header line: not an image
        raw = raw.iloc[1:]
    raw = raw.reset_index(drop=True).astype(float)
    logits, labels = {}, {}
    for i in images:
        x = 2.0 * (np.clip(raw.iloc[i, 1:].to_numpy(), 0, 255) / 255.0) - 1.0
        s = W1 @ x + b1
        h = 0.98 * s - 0.23 * s ** 3
        logits[i] = W2 @ h + b2
        labels[i] = int(raw.iloc[i, 0])
        if i < len(MNIST_FIRST) and labels[i] != MNIST_FIRST[i]:
            print(f"WARNING: image {i} has label {labels[i]}, the MNIST test set has "
                  f"{MNIST_FIRST[i]} there: is seed_input the image index?")
        if int(np.argmax(logits[i])) != labels[i]:
            print(f"WARNING: image {i} is misclassified in plaintext: the margin is negative")
    return logits, labels


def margin(lg, label):
    return lg[label] - max(v for k, v in enumerate(lg) if k != label)


def model_decode(lg, label, bit, log_delta, logq):
    """HEAAN decode: flip `bit` of round(Delta * logit) mod 2^logq, decode centered.
    Bits >= logq are removed by the reduction mod q in decode: masked."""
    bit = int(bit)                     # a numpy int overflows in 1 << bit
    if bit >= logq:
        return 0.0
    q = 1 << logq
    v = (int(round(lg[label] * 2.0 ** log_delta)) % q) ^ (1 << bit)
    if v >= q // 2:
        v -= q
    new = v / 2.0 ** log_delta
    return float(new <= max(x for k, x in enumerate(lg) if k != label))


def model_c0(lg, label, bit, log_delta, logq):
    """HEAAN decrypt_c0: coefficient 0 of c0 is uniform, the flip is +-2^bit with a random
    sign; only the minus sign can lower the correct logit."""
    if bit >= logq:
        return 0.0
    return 0.5 if 2.0 ** (bit - log_delta) > margin(lg, label) else 0.0


# ---------------------------------------------------------------------------- report

def fmt(v, w=8):
    return f"{'.':>{w}s}" if pd.isna(v) else f"{v:{w}.3f}"


def wilson(k, n, z=1.96):
    if n <= 0:
        return np.nan, np.nan
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def print_counts(s, collapsed):
    """k/n and Wilson interval of every metric of one group."""
    n = int(round(s["n"]))
    note = " (k from means, approximate)" if collapsed else ""
    print(f"  coefficient 0, counts with 95% Wilson intervals{note}:")
    for m in METRICS:
        if pd.isna(s[m]):
            continue
        k = int(round(s[m] * n))
        lo, hi = wilson(k, n)
        print(f"    {LABELS[m]:12s} {k:6d}/{n:<6d} = {s[m]:.3f}  [{lo:.3f}, {hi:.3f}]")


def seeds_line(d):
    parts = []
    for k in d.columns:
        if k.startswith(SEED_PREFIX):
            parts.append(f"{d[k].nunique()} {k}")
    return ", ".join(parts)


def report(c, d0, drnd, logits, labels, args):
    lib, stage = c["library"], c["stage"]
    openfhe = lib.startswith("openfhe")
    logN, slots, log_delta = int(c["logN"]), int(c["logSlots"]), int(c["logDelta"])
    gap = max(1, (1 << (logN - 1)) >> slots)
    ntt = openfhe and int(c.get("withNTT", 0)) == 1
    name = f"{lib} {stage}" + (" NTT" if ntt else "")
    print(f"\n=== {name}  (logN={logN} logSlots={slots} logQ={c['logQ']} "
          f"logDelta={log_delta} gap={gap}, {d0['seed_input'].nunique()} images) ===")
    if ntt:
        print("NOTE: withNTT=1: index 0 is an evaluation point, not coefficient 0")

    groups = {"coeff 0": d0}
    if drnd is not None:
        drnd = drnd[drnd["coeff"] != 0]
        if ntt or gap == 1:
            groups["random"] = drnd           # an NTT index has no parity
        else:
            al = drnd["coeff"] % gap == 0
            groups["random aligned"] = drnd[al]
            groups["random other"] = drnd[~al]

    # 1 + 2: rates per group
    print(f"  {'group':16s} {'n':>8s}" + "".join(f" {LABELS[m]:>11s}" for m in METRICS)
          + "  seeds")
    summ = {}
    for g, d in groups.items():
        if d.empty:
            continue
        s = summ[g] = wmean(d)
        print(f"  {g:16s} {int(s['n']):8d}" + "".join(f" {fmt(s[m], 11)}" for m in METRICS)
              + f"  {seeds_line(d)}")
    print_counts(summ["coeff 0"], is_collapsed_rows(d0))
    if openfhe:
        verdict(summ)

    # RNS: coefficient 0 limb by limb
    multi_limb = d0["limb"].nunique() > 1
    if multi_limb:
        print("  coefficient 0 per limb:")
        t = wmean(d0, by="limb")
        for limb, r in t.iterrows():
            print(f"    limb {int(limb):2d}  n {int(r['n']):6d}  detected {fmt(r['detected'])}  "
                  f"P(mis) {fmt(r['misclassified'])}  mis & undet {fmt(r['mis_undetected'])}")

    # 4: images (HEAAN onset bit; the sign matters for decode)
    imgs = sorted(int(i) for i in d0["seed_input"].unique())
    if logits:
        print(f"  {'image':>5s} {'label':>5s} {'logit':>9s} {'margin':>8s} {'onset bit':>9s}")
        for i in imgs:
            lg, lb = logits[i], labels[i]
            m = margin(lg, lb)
            onset = log_delta + math.log2(m) if m > 0 else float("nan")
            print(f"  {i:5d} {lb:5d} {lg[lb]:9.3f} {m:8.3f} {onset:9.1f}")

    # 3: per bit
    curves = {}
    if stage == "decode" and logits and not is_collapsed_rows(d0):
        sign = d0["seed_input"].map(lambda i: logits[int(i)][labels[int(i)]] > 0)
        for g, mask in (("coeff 0, logit > 0", sign), ("coeff 0, logit < 0", ~sign)):
            if mask.any():
                curves[g] = wmean(d0[mask], by="bit")
    elif multi_limb:
        # RNS: the check reacts limb by limb (residues above the prime), so one curve each
        for limb, dl in d0.groupby("limb"):
            curves[f"coeff 0, limb {int(limb)}"] = wmean(dl, by="bit")
    else:
        curves["coeff 0"] = wmean(d0, by="bit")
    for g in ("random aligned", "random other", "random"):
        if g in summ:
            curves[g] = wmean(groups[g], by="bit")

    # HEAAN encode: bits of the 2*logQ wide plaintext, shown as bit - logP like the paper.
    offset = 0
    if lib.startswith("heaan") and stage == "encode" and d0["bit"].max() >= int(c["logQ"]):
        logp = c.get("logP", np.nan)
        offset = int(c["logQ"]) if pd.isna(logp) else int(logp)
        curves = {g: cv.set_axis(cv.index - offset) for g, cv in curves.items()}
        print(f"  encode: bits shown as bit - logP, logP = {offset}")

    model = None
    if lib.startswith("heaan") and logits and stage in ("decode", "decrypt_c0"):
        # logq of the output, expected logQ - NN_LEVELS * logDelta. The data bounds it: a bit
        # >= logq never changes the output, so logq is in (highest bit that moved, lowest
        # sampled bit above it]. If the expected value falls outside, trust the data.
        logq = int(c["logQ"]) - NN_LEVELS * log_delta
        moved = d0.loc[d0["l2_abs"] > 0, "bit"]
        if len(moved):
            lo = int(moved.max())
            above = d0.loc[d0["bit"] > lo, "bit"]
            hi = int(above.min()) if len(above) else lo + 1
            if not lo < logq <= hi:
                print(f"  WARNING: logQ - {NN_LEVELS}*logDelta = {logq}, but the data puts logq "
                      f"in ({lo}, {hi}]: using {lo + 1}")
                logq = lo + 1
        fn = model_decode if stage == "decode" else model_c0
        bits = sorted(d0["bit"].unique())
        model = pd.Series([np.mean([fn(logits[i], labels[i], b, log_delta, logq) for i in imgs])
                           for b in bits], index=bits)
        print(f"  model: logq = {logq}")
        if stage == "decode" and not is_collapsed_rows(d0):
            pred = d0.apply(lambda r: model_decode(logits[int(r["seed_input"])],
                                                   labels[int(r["seed_input"])],
                                                   int(r["bit"]), log_delta, logq), axis=1)
            agree = (pred == d0["misclassified"]).mean()
            print(f"  model vs data, per injection: {agree:.1%} agree")

    show_sdc = bool(args.corrupt_col)
    print_bits(curves, model, openfhe, offset, show_sdc)
    plot(curves, model, openfhe, name, log_delta, args, f"{lib}_{stage}" + ("_ntt" if ntt else ""),
         offset, show_sdc)


def is_collapsed_rows(d):
    return "n_seeds" in d.columns


def verdict(summ):
    s0 = summ["coeff 0"]
    det0, mis0, mu0, sdc0 = (s0["detected"], s0["misclassified"], s0["mis_undetected"],
                             s0["sdc"])
    ref_name = "random aligned" if "random aligned" in summ else "random"
    al = summ.get(ref_name)
    if det0 == 0 and mis0 > 0:
        print(f"  => UNDETECTED SDC at coefficient 0: P(mis) = {mis0:.3f}, detection 0. "
              "'Every fault that altered the output tripped the check' does not hold here.")
    elif mis0 == 0:
        print("  => no misclassification at coefficient 0")
    elif al is not None and abs(det0 - al["detected"]) < 0.02:
        print(f"  => coefficient 0 detected like the {ref_name} ones ({det0:.3f} vs "
              f"{al['detected']:.3f}): no blind spot in practice")
    else:
        print(f"  => coefficient 0 detected at {det0:.3f}"
              + (f", {ref_name} at {al['detected']:.3f}" if al is not None else "")
              + (f"; undetected misclassifications {mu0:.3f}" if not pd.isna(mu0) else ""))
    if not pd.isna(sdc0):
        print(f"  => SDC at coefficient 0 (misclassified or logit beyond 0.1%, undetected): "
              f"{sdc0:.3f}")
    if al is not None and al["mis_undetected"] > 0:
        print(f"  => {ref_name} also has undetected misclassifications: "
              f"{al['mis_undetected']:.3f}")
    if al is not None and not pd.isna(al["sdc"]) and al["sdc"] > 0:
        print(f"  => {ref_name} also has SDCs: {al['sdc']:.3f}")


def print_bits(curves, model, openfhe, offset=0, show_sdc=False):
    names = list(curves)
    c0 = [g for g in names if g.startswith("coeff 0")]
    short = {g: g.replace("coeff 0, ", "").replace("coeff 0", "c0") for g in c0}
    head = f"  {'bit' if not offset else 'b-logP':>6s}" \
        + "".join(f" {'P(mis) ' + g:>26s}" for g in names)
    if openfhe:
        head += "".join(f" {'det ' + short[g]:>11s}" for g in c0)
        if show_sdc:
            head += "".join(f" {'SDC ' + short[g]:>11s}" for g in c0)
    if model is not None:
        head += f" {'model':>8s}"
    print(head)
    bits = sorted(set().union(*(c.index for c in curves.values())))
    for b in bits:
        line = f"  {int(b):6d}" + "".join(
            f" {fmt(curves[g]['misclassified'].get(b, np.nan), 26)}" for g in names)
        if openfhe:
            line += "".join(f" {fmt(curves[g]['detected'].get(b, np.nan), 11)}" for g in c0)
            if show_sdc:
                line += "".join(f" {fmt(curves[g]['sdc'].get(b, np.nan), 11)}" for g in c0)
        if model is not None:
            line += f" {fmt(model.get(b, np.nan))}"
        print(line)


def plot(curves, model, openfhe, name, log_delta, args, tag, offset=0, show_sdc=False):
    panels = (["detected", "misclassified"] if openfhe else ["misclassified"])
    # SDC only with an explicit --corrupt_col: a guessed column may not be the 0.1% criterion
    if openfhe and show_sdc and any(cv["sdc"].notna().any() for cv in curves.values()):
        panels.append("sdc")
    fig, axes = plt.subplots(1, len(panels), figsize=(7 * len(panels), 4.5), squeeze=False)
    for ax, metric in zip(axes[0], panels):
        for g, cv in curves.items():
            ls, mk = STYLES[g]
            ax.plot(cv.index, cv[metric], ls, marker=mk, ms=5, lw=2, color=COLORS[g], label=g)
        if model is not None and metric == "misclassified":
            ax.plot(model.index, model.values, color=COLORS["model"], lw=1, label="model")
        ax.axvline(log_delta, color="#999999", lw=1, ls="--")
        ax.text(log_delta, 1.02, r" $\log\Delta$", fontsize=10, color="#555555",
                transform=ax.get_xaxis_transform())
        ax.set_ylim(-0.03, 1.03)
        ax.set_xlabel(r"bit $-\log P$" if offset else "bit")
        ax.set_ylabel({"detected": "detection rate", "misclassified": "P(mis)",
                       "sdc": "P(SDC)"}[metric])
        ax.grid(alpha=0.25)
    axes[0][-1].legend(fontsize=9, loc="best")
    fig.suptitle(name, fontsize=12)
    fig.tight_layout()
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    out = IMG_DIR / f"{args.title}_{tag}"
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=150)
    print(f"  -> {out}.png / .pdf")
    if not args.no_show:
        plt.show()
    plt.close(fig)


def main():
    args = parse_args()
    c0_camps, c0_dir = load(args.coeff0)
    rnd_camps, rnd_dir = load(args.random) if args.random else (None, None)
    c0_camps = c0_camps[c0_camps["numSamples"].astype(int) == 0]
    if c0_camps.empty:
        sys.exit(f"{args.coeff0}: no campaign with numSamples=0 (coefficient 0)")

    images = sorted(int(i) for i in c0_camps["seed_input"].unique()) \
        if "seed_input" in c0_camps.columns else []
    logits, labels = golden_logits(images) if images else ({}, {})

    for _, group in c0_camps.groupby("config_id", sort=False):
        c = group.iloc[0]
        d0 = rows(group, c0_dir, args.corrupt_col)
        match = random_match(group, rnd_camps)
        drnd = rows(match, rnd_dir, args.corrupt_col) if match is not None else None
        if args.random and drnd is None:
            print(f"\nWARNING: no random campaigns with the config of {c['library']} "
                  f"{c['stage']} in {args.random}")
        report(c, d0, drnd, logits, labels, args)


if __name__ == "__main__":
    main()
