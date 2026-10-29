#!/usr/bin/env python3
"""One-bit law per input vector: measured E_L2 against the law, one row per seed_input.

For every seed_input of the selected config, the injections are averaged over the crypto
seeds and over the coefficients the law covers, and compared bit by bit with

    E_L2 = 2^b / Delta_c * kappa / (sqrt(2) * rms(z))

kappa = sqrt(2) for coefficient 0, 0 for N/2 and for coefficients off the gap, 1 otherwise.
For a fault in c1 (stage *_c1), kappa = sqrt(h/g) in every coefficient (see c1_factor).
z is the fault-free output (the reference E_L2 is measured against), so rms(z) is read
from the data itself: ||z|| = l2_abs / l2_rel of any injection of that campaign.

Needs the RAW results dir: the collapsed one has already averaged the seed_inputs.

Scope: faults that reach the decrypted polynomial as +-2^b in one coefficient: c0, the
decrypted polynomial (decode), HEAAN's encode shifted by logQ, with add / rot on the way,
and decrypt_* / decode after any pipeline without bootstrapping (the modulus is then the
level the pipeline ends at). The same in c1, with the average factor sqrt(h/g). Not a
fault that goes through a product (its Delta_c is the product's: pass --log_delta_c).
OpenFHE with attackModeSKA != 0 adds noise when decoding: expect a ratio above 1 there.

  python3 law_by_input.py --results ../results_client \\
      --where library=heaan stage=encrypt_c0 logN=6 logQ=60 logDelta=40 logSlots=5 pipeline=
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
from build_ml_dataset import MULTS, expand, injection_index
from utils.results import (is_collapsed, load_campaigns, load_data, parse_value,
                           require_single_config, select)

# Below this the predicted error is at the level of double precision noise.
MIN_ERR = 1e-12


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", required=True, help="raw results dir (what the C++ writes)")
    p.add_argument("--where", nargs="+", default=[], metavar="COL=VAL")
    p.add_argument("--query", default=None, help="extra pandas filter on the campaigns")
    p.add_argument("--log_delta_c", type=float, default=None,
                   help="log2 of the scale at which the fault reaches the decrypted "
                        "polynomial (default: logDelta)")
    p.add_argument("--min_err", type=float, default=MIN_ERR,
                   help="skip cells whose predicted E_L2 is below this")
    p.add_argument("--per_bit", action="store_true",
                   help="also print the bit-by-bit table of each seed_input")
    return p.parse_args()


def select_config(args):
    """Finished raw campaigns of exactly one config."""
    camps = load_campaigns(args.results, raw=True)
    if is_collapsed(camps):
        sys.exit("ERROR: --results is a collapsed dir: the seed_inputs are already averaged "
                 "there. Pass the raw dir the C++ writes.")
    filters = {k: parse_value(v) for k, v in (w.split("=", 1) for w in args.where)}
    camps = select(camps, **filters)
    if args.query:
        camps = camps.query(args.query)
    if camps.empty:
        sys.exit(f"No finished campaigns match --where {args.where} --query {args.query!r}")
    try:
        return require_single_config(camps)
    except ValueError as e:
        sys.exit(f"ERROR: {e}\n  -> pin those columns with --where")


def warn_scope(cfg, args):
    """Cases where a ratio far from 1 is expected, not a failure of the law."""
    stage, pipeline = str(cfg["stage"]), str(cfg["pipeline"])
    if is_c1(cfg):
        gap = 2 ** (int(cfg["logN"]) - 1 - int(cfg["logSlots"]))
        print(f"NOTE: fault in c1: kappa = sqrt(h/g) with h = {key_weight(cfg):g}, "
              f"g = {gap} (see c1_factor).")
        if gap > 1:
            print("NOTE: with g > 1 the copies read depend on the key: the mean of their "
                  "sqrt is below sqrt(h/g), so expect a negative diff.")
    # decrypt_* and decode come after the whole pipeline: the fault never meets a product.
    after_pipeline = stage in ("decrypt_c0", "decrypt_c1", "decode")
    if "mul" in pipeline and not after_pipeline and args.log_delta_c is None:
        print("NOTE: the fault goes through a product: the law needs that product's "
              "Delta_c (--log_delta_c), and may not hold at all.")
    if "boot" in pipeline:
        print("NOTE: bootstrapping in the pipeline: the modulus width used here is wrong.")
    if str(cfg["library"]).startswith("openfhe") and int(cfg["attackModeSKA"]) != 0:
        print("NOTE: OpenFHE with attackModeSKA != 0 adds noise when decoding: expect a "
              "ratio above 1.")
    if int(cfg["isComplex"]) != 0:
        print("NOTE: the law here is the one for real inputs (isComplex = 0).")


def module_bits(cfg):
    """Bits of the modulus at the injection point: logQ minus logDelta for every product
    that ran before it, so decrypt_* and decode see the level the pipeline ends at.
    Not valid after a bootstrapping (it raises the modulus again)."""
    ops = expand(cfg["pipeline"])
    pos = injection_index(ops, cfg["stage"], int(cfg["op_depth"]))
    if pos is None:
        return int(cfg["logQ"])
    n_mults = sum(o in MULTS for o in ops[:max(pos, 0)])
    return int(cfg["logQ"]) - int(cfg["logDelta"]) * n_mults


def law_bit(data, cfg):
    """Bit of the decrypted polynomial the fault lands on. HEAAN encodes with scale
    Delta * P, P = 2^logQ, so bit b of its encoded plaintext reaches the ciphertext as
    bit b - logQ (the bits below logQ are rounded away by the encryption)."""
    if str(cfg["library"]).startswith("heaan") and cfg["stage"] == "encode":
        return data["bit"] - int(cfg["logQ"])
    return data["bit"]


def is_c1(cfg):
    return "c1" in str(cfg["stage"])


def key_weight(cfg):
    """Nonzero coefficients of the secret key (h). HEAAN (backends/heaan.cpp): 64 if
    logN > 10, else max(4, N/64). OpenFHE: uniform ternary key by default, so each
    coefficient is nonzero with probability 2/3 and h = 2N/3 on average."""
    N = 2 ** int(cfg["logN"])
    if str(cfg["library"]).startswith("heaan"):
        return 64 if int(cfg["logN"]) > 10 else max(4, N // 64)
    return 2 * N / 3


def c1_factor(cfg):
    """A fault 2^b X^j in c1 reaches the decrypted polynomial times s: h copies of 2^b,
    one per nonzero coefficient of the key, in different positions. The decoding reads
    only the multiples of the gap g, so h/g copies are read on average, and their slot
    patterns are orthogonal, so they add in quadrature: sqrt(h/g) times the c0 law.
    It ignores the exceptions (a copy on 0 weighs sqrt(2), one on N/2 is not read, copies
    on j and N - j are not orthogonal), and with g > 1 h/g is an average over keys."""
    gap = 2 ** (int(cfg["logN"]) - 1 - int(cfg["logSlots"]))
    return np.sqrt(key_weight(cfg) / gap)


def kappa(coeff, cfg):
    """Factor of the one-bit law for a fault in coefficient `coeff`. For c1 it does not
    depend on the coefficient: the key moves the copies to other positions."""
    if is_c1(cfg):
        return np.full(len(coeff), c1_factor(cfg))
    N = 2 ** int(cfg["logN"])
    gap = 2 ** (int(cfg["logN"]) - 1 - int(cfg["logSlots"]))
    k = np.where(coeff % gap == 0, 1.0, 0.0)
    k = np.where(coeff == 0, np.sqrt(2.0), k)
    return np.where(coeff == N // 2, 0.0, k)


def add_law(data, cfg, log_delta_c):
    """Columns rms_z, law_bit, kappa and law (the predicted E_L2) for every injection."""
    n = 2 ** int(cfg["logSlots"])
    ok = (data["l2_rel"] > 0) & np.isfinite(data["l2_rel"]) & np.isfinite(data["l2_abs"])
    # The reference is the same for every injection of a campaign: ||z|| = l2_abs / l2_rel.
    norm = ((data.loc[ok, "l2_abs"] / data.loc[ok, "l2_rel"])
            .groupby(data.loc[ok, "campaign_id"]).median())
    data["rms_z"] = data["campaign_id"].map(norm) / np.sqrt(n)
    data["law_bit"] = law_bit(data, cfg)
    data["kappa"] = kappa(data["coeff"].to_numpy(), cfg)
    # The law with kappa = 1: used to pick the bits, so that every coefficient of a bit
    # goes in or out together (otherwise coefficient 0, kappa = sqrt(2), enters alone).
    data["law_unit"] = 2.0 ** (data["law_bit"] - log_delta_c) / (np.sqrt(2.0) * data["rms_z"])
    data["law"] = data["law_unit"] * data["kappa"]
    return data


def signed(v):
    """+0.0123 / -0.0123, with -0.0000 printed as +0.0000."""
    return f"{round(v, 4) + 0.0:+.4f}"


def main():
    args = parse_args()
    camps = select_config(args)
    cfg = camps.iloc[0]
    log_delta_c = args.log_delta_c if args.log_delta_c is not None else float(cfg["logDelta"])
    data = load_data(camps, args.results)
    if data["limb"].nunique() > 1:
        sys.exit("ERROR: more than one limb: the law is for a single modulus (Plain).")

    print(f"config: {cfg['library']} stage={cfg['stage']} logN={cfg['logN']} "
          f"logQ={cfg['logQ']} logDelta={cfg['logDelta']} logSlots={cfg['logSlots']} "
          f"pipeline='{cfg['pipeline']}' ({len(camps)} campaigns)")
    print(f"law: E_L2 = 2^(b - {log_delta_c:g}) * kappa / (sqrt(2) * rms(z))")
    warn_scope(cfg, args)

    data = add_law(data, cfg, log_delta_c)
    # Only the bits of the modulus: below 0 (HEAAN's encode) and above it the law says 0.
    width = module_bits(cfg)
    print(f"bits of the modulus at the injection point: 0-{width - 1}")
    data = data[(data["law_bit"] >= 0) & (data["law_bit"] < width)]

    masked = data[data["kappa"] == 0]
    print(f"cells where the law predicts 0 (N/2, off the gap): {len(masked)} injections, "
          f"{int((masked['l2_rel'] > args.min_err).sum())} with E_L2 > {args.min_err:g}")

    cells = data[(data["kappa"] > 0) & (data["law_unit"] >= args.min_err)]
    per_bit = (cells.groupby(["seed_input", "law_bit"])
                    .agg(measured=("l2_rel", "mean"), law=("law", "mean"))
                    .reset_index())
    zero = per_bit["measured"] == 0
    if zero.any():
        print(f"WARNING: {int(zero.sum())} (seed_input, bit) cells measure exactly 0 where "
              f"the law predicts an error: left out of the table.")
        per_bit = per_bit[~zero]
    per_bit["diff_bits"] = np.log2(per_bit["measured"] / per_bit["law"])

    rows = []
    for si, g in per_bit.groupby("seed_input"):
        sub = cells[cells["seed_input"] == si]
        rows.append({"seed_input": si,
                     "seeds": sub["seed"].nunique(),
                     "rms_z": sub["rms_z"].mean(),
                     "bits": f"{int(g['law_bit'].min())}-{int(g['law_bit'].max())}",
                     "diff_median": g["diff_bits"].median(),
                     "diff_min": g["diff_bits"].min(),
                     "diff_max": g["diff_bits"].max()})
    summary = pd.DataFrame(rows)
    print("\ndiff = log2(measured / law), over the bits of each seed_input "
          "(0 = exact, 1 = a factor of 2)")
    print(summary.to_string(index=False, formatters={"rms_z": "{:.4f}".format,
                                                      "diff_median": signed,
                                                      "diff_min": signed,
                                                      "diff_max": signed}))

    if args.per_bit:
        for si, g in per_bit.groupby("seed_input"):
            print(f"\nseed_input {si}")
            print(g.drop(columns="seed_input").to_string(
                index=False, formatters={"measured": "{:.4g}".format,
                                         "law": "{:.4g}".format,
                                         "diff_bits": signed}))


if __name__ == "__main__":
    main()
