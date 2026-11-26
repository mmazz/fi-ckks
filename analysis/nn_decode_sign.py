#!/usr/bin/env python3
"""Sign model for HEAAN decode faults in the NN (thesis, Sec. nn-cliente, "Salida").

    cd analysis
    python3 nn_decode_sign.py                      # default dirs, see below
    python3 nn_decode_sign.py --plot 1 0           # also plot m_j for key seed 1, image 0

Inputs
  --dumps    clean decrypted plaintext of the correct-class logit, one file per key seed and
             image (default ../results_NN_plain/ckks_only_plain/heaan*_seed*_in*.csv), one
             row per coefficient:
             library logN logQ logDelta logSlots pipeline seed seed_input logq coeff value
  --results  raw results dir with the HEAAN decode random campaigns (default ../results_NN).

Model. Slot 0 is Re m(zeta) / Delta with zeta = exp(i*pi/N), so a change d in coefficient j
moves the logit by d * cos(pi*j/N) / Delta. The fault flips bit b of m_j mod 2^logq (HEAAN
keeps it in [0, q)) and decode centers the result. Prediction: misclassified iff the new
correct logit falls to or below the best other logit (golden plain logits).

Prints
  1. Per dump: m_0 / Delta against the golden logit, and how many bits the other
     coefficients take.
  2. Per key seed, aligned coefficients, plateau bits: measured P(mis), predicted P(mis)
     and the fraction of injections where model and data agree.
  3. Per key seed: fraction of ALL aligned coefficients whose flip lowers the logit (at
     --bref), the quantity that should set P(mis) on the plateau.
"""
import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
from utils.results import load_campaigns, load_data   # noqa: E402
from nn_coeff0 import golden_logits                    # noqa: E402

IMG_DIR = Path(__file__).resolve().parent / "img"
REPO = Path(__file__).resolve().parent.parent
# Written by the ckks_only_plain mode: one file per (key seed, image),
# heaanNN_logN12_logQ220_logDelta30_logSlots10_none_seed<S>_in<I>.csv
DUMP_DIR = REPO / "results_NN_plain" / "ckks_only_plain"
DUMP_GLOB = "heaan*_seed*_in*.csv"
RESULTS_DIR = REPO / "results_NN"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dumps", nargs="+", default=[str(DUMP_DIR)],
                   help="clean plaintext dumps: csv files or directories "
                        f"(default {DUMP_DIR}, every {DUMP_GLOB} inside)")
    p.add_argument("--results", default=str(RESULTS_DIR),
                   help=f"raw results dir with the HEAAN NN campaigns (default {RESULTS_DIR})")
    p.add_argument("--stage", default="decode")
    p.add_argument("--bmin", type=int, default=34, help="first plateau bit")
    p.add_argument("--bmax", type=int, default=None, help="last plateau bit (default logq-2)")
    p.add_argument("--bref", type=int, default=50, help="bit used for the coefficient census")
    p.add_argument("--plot", nargs=2, type=int, metavar=("SEED", "IMAGE"),
                   help="plot m_j against j for one dump")
    return p.parse_args()


# ------------------------------------------------------------------------------ model

def center(v, logq):
    """Representative of v mod 2^logq in [-q/2, q/2)."""
    q = 1 << logq
    v %= q
    return v - q if v >= q // 2 else v


def flip_delta(mj, bit, logq):
    """Change of the centered coefficient when bit `bit` of its stored value flips."""
    if bit >= logq:                       # removed by the reduction mod q in decode
        return 0
    r = (mj % (1 << logq)) ^ (1 << bit)
    return center(r, logq) - mj


def logit_shift(d, j, N, log_delta):
    return d * math.cos(math.pi * j / N) / 2.0 ** log_delta


# ------------------------------------------------------------------------------- data

def dump_files(paths):
    """Expand directories into their dump files (one per key seed and image)."""
    files = []
    for p in map(Path, paths):
        files += sorted(p.glob(DUMP_GLOB)) if p.is_dir() else [p]
    if not files:
        sys.exit(f"no dump files in {', '.join(paths)}")
    print(f"{len(files)} dump files")
    return files


def load_dumps(paths):
    """{(seed, image): dict(m, N, logq, logd, gap)}. Values are read as text: they do not
    fit in int64."""
    df = pd.concat([pd.read_csv(p, sep=None, engine="python", keep_default_na=False,
                                dtype={"value": str}) for p in paths], ignore_index=True)
    out = {}
    for (seed, img), g in df.groupby(["seed", "seed_input"]):
        logN, logq = int(g["logN"].iloc[0]), int(g["logq"].iloc[0])
        N = 1 << logN
        m = [0] * N
        for j, v in zip(g["coeff"], g["value"]):
            m[int(j)] = center(int(v), logq)
        if len(g) != N:
            print(f"WARNING: dump seed {seed} image {img} has {len(g)} coefficients, N = {N}")
        out[(int(seed), int(img))] = dict(
            m=m, N=N, logq=logq, logd=int(g["logDelta"].iloc[0]),
            gap=(N // 2) >> int(g["logSlots"].iloc[0]))
    return out


def injections(results_dir, stage, dumps):
    """HEAAN injections of `stage` at aligned coefficients != 0, N/2, restricted to the
    (seed, image) pairs that have a dump."""
    camps = load_campaigns(results_dir, raw=True)
    camps = camps[camps["library"].astype(str).str.contains("heaan", case=False)
                  & (camps["stage"] == stage)]
    if camps.empty:
        sys.exit(f"no HEAAN campaign with stage {stage} in {results_dir}")
    data = load_data(camps, results_dir)
    data = data[data["coeff"] != 0]
    keep = [(int(s), int(i)) in dumps for s, i in zip(data["seed"], data["seed_input"])]
    data = data[keep]
    any_dump = next(iter(dumps.values()))
    gap, N = any_dump["gap"], any_dump["N"]
    data = data[(data["coeff"] % gap == 0) & (data["coeff"] != N // 2)]
    missing = sorted({k[0] for k in dumps} - set(data["seed"].astype(int)))
    if missing:
        print(f"WARNING: no injections for the dumped seeds {missing}")
    return data.reset_index(drop=True)


# ----------------------------------------------------------------------------- report

def report_dumps(dumps, logits, labels):
    print("\n=== 1. Clean plaintext of the correct logit ===")
    print(" seed  img   m_0/Delta   golden   max|m_j| (bits, j != 0)   m_j > 0 (aligned)")
    for (seed, img), d in sorted(dumps.items()):
        m, N, gap = d["m"], d["N"], d["gap"]
        other = [abs(v) for j, v in enumerate(m) if j != 0]
        al = [m[j] for j in range(gap, N, gap) if j != N // 2]
        gold = f"{logits[img][labels[img]]:8.4f}" if logits else "     n/a"
        print(f" {seed:4d} {img:4d} {m[0] / 2.0 ** d['logd']:11.4f} {gold}"
              f"   {math.log2(max(other) + 1):6.1f}"
              f"                    {np.mean([v > 0 for v in al]):.2f}")


def predict(data, dumps, logits, labels):
    pred, shift = [], []
    for s, i, j, b in zip(data["seed"], data["seed_input"], data["coeff"], data["bit"]):
        d = dumps[(int(s), int(i))]
        j, b = int(j), int(b)
        dl = logit_shift(flip_delta(d["m"][j], b, d["logq"]), j, d["N"], d["logd"])
        shift.append(dl)
        if logits:
            lg, lab = logits[int(i)], labels[int(i)]
            best_other = max(v for k, v in enumerate(lg) if k != lab)
            pred.append(float(lg[lab] + dl <= best_other))
        else:
            pred.append(float(dl < 0))        # without logits: only the direction
    data = data.copy()
    data["pred"] = pred
    data["shift"] = shift
    return data


def report_agreement(data, bmin, bmax):
    plateau = data[(data["bit"] >= bmin) & (data["bit"] <= bmax)]
    print(f"\n=== 2. Aligned coefficients, bits {bmin}-{bmax} ===")
    print(" seed      n   P(mis) data   P(mis) model   agreement")
    for seed, g in plateau.groupby("seed"):
        mis = g["misclassified"].astype(float)
        print(f" {int(seed):4d} {len(g):6d}        {mis.mean():.3f}          "
              f"{g['pred'].mean():.3f}       {(mis == g['pred']).mean():.3f}")
    mis = plateau["misclassified"].astype(float)
    print(f"  all {len(plateau):6d}        {mis.mean():.3f}          "
          f"{plateau['pred'].mean():.3f}       {(mis == plateau['pred']).mean():.3f}")
    mis_all = data["misclassified"].astype(float)
    print(f"All bits: agreement {(mis_all == data['pred']).mean():.3f} over {len(data)}")


def report_census(dumps, bref):
    print(f"\n=== 3. Aligned coefficients whose flip at bit {bref} lowers the logit ===")
    per_seed = {}
    for (seed, img), d in sorted(dumps.items()):
        N, gap = d["N"], d["gap"]
        js = [j for j in range(gap, N, gap) if j != N // 2]
        down = [logit_shift(flip_delta(d["m"][j], bref, d["logq"]), j, N, d["logd"]) < 0
                for j in js]
        per_seed.setdefault(seed, []).append(np.mean(down))
    for seed, v in per_seed.items():
        print(f" seed {seed}: {np.mean(v):.3f} (images: {min(v):.2f}-{max(v):.2f})")


def plot_dump(dumps, seed, img):
    import matplotlib.pyplot as plt
    d = dumps[(seed, img)]
    N, gap = d["N"], d["gap"]
    js = np.arange(gap, N, gap)
    m = np.array([d["m"][j] for j in js], dtype=float)
    # Top: every aligned coefficient but 0. Bottom: zoom on the bulk, colored by whether a
    # flip of a high bit there lowers (red) or raises (blue) the correct logit.
    down = np.sign(m) * np.cos(np.pi * js / N) < 0
    lim = np.percentile(np.abs(m), 95) * 1.5
    fig, (ax, az) = plt.subplots(2, 1, figsize=(7, 5), sharex=True)
    ax.plot(js, m, ".", ms=2)
    az.plot(js[~down], m[~down], ".", ms=2, color="#0077BB", label="flip raises the logit")
    az.plot(js[down], m[down], ".", ms=2, color="#CC3311", label="flip lowers the logit")
    az.set_ylim(-lim, lim)
    az.legend(fontsize=7, loc="upper right", markerscale=4)
    for a in (ax, az):
        a.axhline(0, color="k", lw=0.5)
        a.axvline(N // 2, color="k", lw=0.5, ls="--")
        a.set_ylabel("$m_j$ (centered)")
    az.set_xlabel("coefficient j (aligned, j > 0)")
    ax.set_title(f"Clean plaintext of the correct logit, seed {seed}, image {img} "
                 f"({down.mean():.0%} of the flips lower it)")
    IMG_DIR.mkdir(exist_ok=True)
    out = IMG_DIR / f"nn_decode_noise_s{seed}_i{img}.pdf"
    fig.tight_layout()
    fig.savefig(out)
    print(f"\nSaved {out}")


def main():
    args = parse_args()
    dumps = load_dumps(dump_files(args.dumps))
    images = sorted({k[1] for k in dumps})
    logits, labels = golden_logits(images)
    report_dumps(dumps, logits, labels)
    if args.plot:
        plot_dump(dumps, *args.plot)
    report_census(dumps, args.bref)
    data = predict(injections(args.results, args.stage, dumps), dumps, logits, labels)
    bmax = args.bmax if args.bmax is not None else next(iter(dumps.values()))["logq"] - 2
    report_agreement(data, args.bmin, bmax)


if __name__ == "__main__":
    main()
