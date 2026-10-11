#!/usr/bin/env python3
"""Analytical predictor of err_bits = log2(E_L2), as a baseline for the ML chapter.

No parameter is fitted to the data: every rule comes from the analytical chapter.
For each (configuration, coefficient, bit) of the client HEAAN encryption campaigns:

  masked     b >= logQ (reduction mod q); c0 outside Z[X^g] or at N/2 with no ct x ct
             product after it (Cor. cor:gap, Prop. prop:ley);
             b >= log q_boot + k logDelta before a bootstrapping (Prop. prop:boot)
  additive   log2(E_L2) = b - logDelta + log2(kappa * F * rms(x^K) / (sqrt2 * rms(z)))
             K = mults after the fault, F = sqrt(h) (c1, no gap), sqrt(h/g) (c1, gap), 1 (c0)
  leak       c0 (any coefficient) through a ct x ct product (Eq. eq:fuga), sigma_e = 1.6
  floor      rounding of every rescale (and rotation key switch) that sees a perturbed
             component (Prop. prop:piso), added in power to the terms above
  capped     at the saturation value of Lemma lem:saturacion at the final level

Bootstrapping plateaus are not modeled: those configurations only count for the
visible / not visible classification.

    python3 analytic_baseline.py <client results (RES1)>
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
from utils.results import load_campaigns  # noqa: E402  (raw or collapsed results dir)

H, SIGMA_E, TAU = 4, 1.6, 1e-2      # Hamming weight of s, fresh noise std, visibility threshold
FLOOR = -60.0                       # log2 of the smallest error kept from the data
VAR_ROUND = 1 / 6                   # variance of the difference of two independent roundings


def expand(pipeline):
    """'add; mul x2' -> ['add', 'mul', 'mul']"""
    ops = []
    for chunk in str(pipeline).split(";"):
        w = chunk.split()
        if not w:
            continue
        reps = next((int(t[1:]) for t in w[1:] if t.startswith("x") and t[1:].isdigit()), 1)
        ops += [w[0]] * reps
    return ops


def rms_x(lo, hi, k):
    """rms of x^k for x uniform in [lo, hi]."""
    if k == 0:
        return 1.0
    return math.sqrt((hi ** (2 * k + 1) - lo ** (2 * k + 1)) / ((2 * k + 1) * (hi - lo)))


def rounding_floor(ops, K, stage, n, logD, lo, hi, b):
    """Squared relative error left by the roundings after the fault (Prop. prop:piso),
    without the 1 / rms(z)^2 factor, per cell (b is the array of bits).
    Each rescale or rotation key switch that sees a perturbed component adds VAR_ROUND (c0)
    or VAR_ROUND * h (c1) per coefficient; the later products multiply it by x.
    The k-th rescale after the fault is exact when b >= k logDelta (Lemma lem:rescale):
    the perturbation is then a multiple of Delta."""
    diff = {"c0"} if stage == "encrypt_c0" else {"c1"}
    acc, done = np.zeros_like(b), 0
    for o in ops:
        if o == "boot":
            break
        if o in ("mul", "pmul"):
            if o == "mul":
                diff = {"c0", "c1"}
            done += 1
            var = VAR_ROUND * (("c0" in diff) + H * ("c1" in diff))
            active = b < done * logD
        elif o == "rot" and "c1" in diff:
            var = VAR_ROUND * (1 + H)
            active = np.ones_like(b, dtype=bool)
        else:
            continue
        acc = acc + np.where(active, var * rms_x(lo, hi, K - done) ** 2, 0.0)
    return n * acc / 2.0 ** (2 * logD)


def predict(cfg, cells):
    """Predicted log2(E_L2) per cell (array), -inf = masked."""
    ops = expand(cfg.pipeline)
    logN, logS, logQ, logD = int(cfg.logN), int(cfg.logSlots), int(cfg.logQ), int(cfg.logDelta)
    lo, hi = (-1.0, 1.0) if cfg.logMin == cfg.logMax == 0 else (2.0 ** cfg.logMin, 2.0 ** cfg.logMax)
    N, n = 2 ** logN, 2 ** logS
    g = N // (2 * n)
    boot = "boot" in ops
    mults = [o for o in (ops[: ops.index("boot")] if boot else ops) if o in ("mul", "pmul")]
    K = len(mults)
    adds_before = 0
    for o in ops:
        if o in ("mul", "pmul", "boot"):
            break
        adds_before += o == "add"
    rms_z = (1 + adds_before) * rms_x(lo, hi, K + 1)
    b = cells["bit"].to_numpy(dtype=float)
    i = cells["coeff"].to_numpy()
    aligned = i % g == 0
    c1 = cfg.stage == "encrypt_c1"
    F = (math.sqrt(H) if g == 1 else math.sqrt(H / g)) if c1 else 1.0
    kappa = np.where(i == 0, math.sqrt(2), 1.0)
    if not c1:
        kappa = np.where(i == N // 2, 0.0, kappa)
        kappa = np.where(aligned, kappa, 0.0)          # c0 outside Z[X^g] is projected out
    # independent contributions add in power; work with log2 of the amplitudes
    with np.errstate(divide="ignore"):
        pred = b - logD + np.log2(kappa * F * rms_x(lo, hi, K) / (math.sqrt(2) * rms_z))
    if not c1 and mults and mults[0] == "mul":
        # the other operand's noise brings every coefficient (also N/2) into Z[X^g]
        leak = b - 2 * logD + math.log2(SIGMA_E * math.sqrt(n) * rms_x(lo, hi, K - 1) / rms_z)
        pred = 0.5 * np.logaddexp2(2 * pred, 2 * leak)
    if K and not boot:
        with np.errstate(divide="ignore"):
            floor = 0.5 * np.log2(rounding_floor(ops, K, cfg.stage, n, logD, lo, hi, b) / rms_z ** 2)
        if not c1 and "mul" not in mults:
            # pmul and rescale keep the class mod g (Prop. prop:clases): a non-aligned
            # c0 fault leaves its rounding residue outside Z[X^g] too
            floor = np.where(aligned, floor, -np.inf)
        pred = 0.5 * np.logaddexp2(2 * pred, 2 * floor)
        sat = math.log2(2.0 ** (logQ - logD * K - logD) * math.sqrt(n / 12) / rms_z)
        pred = np.minimum(pred, sat)
    pred = np.where(b >= logQ, -np.inf, pred)
    if boot:
        cut = logD + 10 + K * logD
        pred = np.where(b >= cut, -np.inf, pred)
    return pred


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = Path(sys.argv[1])
    # one row per experiment; data_file is relative (collapsed dir) or absolute (raw dir)
    camps = load_campaigns(root)
    camps = camps.query("library=='heaan' and stage in ['encrypt_c0', 'encrypt_c1'] and logN==6")
    reg, cls = [], []
    for _, cfg in camps.iterrows():
        y = pd.read_csv(root / cfg.data_file)
        meas = np.log2(np.clip(y["l2_rel_median"].to_numpy(dtype=float), 2.0 ** FLOOR, None))
        pred = predict(cfg, y)
        boot = "boot" in cfg.pipeline
        n, g = 2 ** int(cfg.logSlots), 2 ** (int(cfg.logN) - 1 - int(cfg.logSlots))
        vis_m = meas > math.log2(TAU)
        vis_p = pred > math.log2(TAU)
        cls.append(pd.DataFrame(dict(boot=boot, stage=cfg.stage, vm=vis_m, vp=vis_p)))
        if not boot:
            both = np.isfinite(pred) & (meas > FLOOR + 1)
            reg.append(pd.DataFrame(dict(stage=cfg.stage, pipe=cfg.pipeline or "(none)", gap=g,
                                         inputs="[-1,1]" if cfg.logMin == cfg.logMax == 0 else "[2^a,2^(a+1)]",
                                         err=np.abs(pred[both] - meas[both]))))
    reg = pd.concat(reg)
    cls = pd.concat(cls)
    print(f"Regression (non-boot configurations, cells not masked in data nor prediction): {len(reg)} cells")
    print(f"  |pred - meas| in bits: median {reg.err.median():.2f}, mean {reg.err.mean():.2f}, "
          f"p90 {reg.err.quantile(0.9):.2f}, p99 {reg.err.quantile(0.99):.2f}")
    print(f"  cells within 1 bit: {(reg.err <= 1).mean():.3f}, within 2 bits: {(reg.err <= 2).mean():.3f}")
    print(reg.groupby(["stage", "gap"]).err.agg(["median", "mean", "count"]).round(2).to_string())
    print(reg.groupby("pipe").err.agg(["median", "mean", "count"]).round(2).to_string())
    print(reg.groupby("inputs").err.agg(["median", "mean", "count"]).round(2).to_string())
    key_free = reg[~((reg.stage == "encrypt_c1") & (reg.gap > 1))]
    print(f"  without c1 under gap (key-dependent, Prop. prop:c1): {len(key_free)} cells, median "
          f"{key_free.err.median():.2f}, mean {key_free.err.mean():.2f}, p90 {key_free.err.quantile(0.9):.2f}, "
          f"within 1 bit {(key_free.err <= 1).mean():.3f}")
    print(f"\nVisible (E_L2 > {TAU}) classification, {len(cls)} cells:")
    for name, d in [("all", cls), ("no boot", cls[~cls.boot]), ("boot", cls[cls.boot]),
                    ("c0", cls[cls.stage == "encrypt_c0"]), ("c1", cls[cls.stage == "encrypt_c1"])]:
        acc = (d.vm == d.vp).mean()
        tp = (d.vm & d.vp).sum(); fp = (~d.vm & d.vp).sum(); fn = (d.vm & ~d.vp).sum()
        print(f"  {name:8s}: accuracy {acc:.4f}  precision {tp / max(tp + fp, 1):.4f}  "
              f"recall {tp / max(tp + fn, 1):.4f}  (n = {len(d)})")


if __name__ == "__main__":
    main()
