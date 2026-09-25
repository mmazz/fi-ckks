#!/usr/bin/env python3
"""Results chapter 1: faults on the CLIENT side (fi_heaan / fi_openfhe).

Stages: encode, encrypt_c0, encrypt_c1, decrypt_c0, decrypt_c1, decode.

    python3 scripts/clientCampaigns.py                        # list the groups
    python3 scripts/clientCampaigns.py enc_seeds --dry-run    # print the commands
    python3 scripts/clientCampaigns.py sweep_* --jobs 8
    python3 scripts/clientCampaigns.py all --jobs 16

Each group is tagged with the figure it feeds (FIG n) or with the claim it backs up
without being plotted (EVIDENCE). Re-running a group is safe: the registry skips the
campaigns that already finished.
"""
from campaigns import ROOT, grid, main

RESULTS = str(ROOT / "results_client")

SEEDS_ANALYSIS = range(25)  # only for the seed-variability figure
SEEDS = [1, 2]           # --seed       (keys and encryption noise)
INPUTS = [1, 2, 3, 4]          # --seed_input (input vector)
NUM_SAMPLES = 50

# ---------------------------------------------------------------------------
# Base configurations
# ---------------------------------------------------------------------------
BASE = dict(binary="fi_heaan", results_dir=RESULTS, isExhaustive=1,
            logN=6, logSlots=5, logQ=60, logDelta=40, bitsPerCoeff=64)

# withNTT defaults to 0; it is written explicitly so the encode comparison with HEAAN
# is visibly done in the coefficient domain.
BASE_OPENFHE = dict(binary="fi_openfhe", results_dir=RESULTS, isExhaustive=1,
                    logN=6, logSlots=5, logQ=60, logDelta=40, bitsPerCoeff=64, withNTT=0)

# logN comparison: random on both sides so both have the same number of sampled coefficients
LOGN_CMP = dict(binary="fi_heaan", results_dir=RESULTS,
                logQ=60, logDelta=40, bitsPerCoeff=64, stage="encrypt_c0")

# logQ sweep at a fixed ratio: logDelta = 3/4 logQ, bitsPerCoeff = 5/4 logQ
LOGQ_SWEEP = [40, 60, 80, 100]
SWEEP_Q = dict(binary="fi_heaan", results_dir=RESULTS, isExhaustive=1, logN=6, logSlots=5)

LOGDELTA_SWEEP = [25, 35, 45, 55]
SWEEP_DELTA = dict(BASE)             # logDelta is swept

LOGSLOTS_SWEEP = [3, 4, 5]
SWEEP_SLOTS = dict(BASE)             # logSlots is swept

INPUT_SWEEP = [0, 9, 19, 29]         # logMin = x, logMax = x + 1

# Pipeline figures. logSlots=3 -> gap = 4, so the coefficient gaps are clearly visible.
CLIENT = dict(binary="fi_heaan", results_dir=RESULTS, isExhaustive=1,
              logN=6, logSlots=3, logQ=60, logDelta=30, bitsPerCoeff=64)
# mul x3 consumes 3*logDelta = 90 bits: logQ=150 leaves 60 bits at decryption
# (logDelta + 30 of headroom), bitsPerCoeff = logQ + 20 keeps the out-of-modulus tail.
CLIENT_MUL = dict(CLIENT, logQ=150, bitsPerCoeff=170)

CLIENT_OPENFHE = dict(binary="fi_openfhe", results_dir=RESULTS, isExhaustive=1,
                      logN=6, logSlots=4, logQ=60, logDelta=30, bitsPerCoeff=64, withNTT=0)

BOOT = dict(binary="fi_heaan", results_dir=RESULTS, isExhaustive=0, numSamples=NUM_SAMPLES,
            logN=6, logSlots=3, logQ=840, logDelta=40, bitsPerCoeff=860)

ENC = ["encrypt_c0", "encrypt_c1"]
DEC = ["decrypt_c0", "decrypt_c1"]


def sweep_q(stage, seeds=SEEDS, inputs=INPUTS):
    """One campaign per logQ in LOGQ_SWEEP (x seeds x inputs), with logDelta and
    bitsPerCoeff scaled with logQ so every run sits at the same relative position."""
    return [run for q in LOGQ_SWEEP
            for run in grid(dict(SWEEP_Q, stage=stage, logQ=q,
                                 logDelta=3 * q // 4, bitsPerCoeff=5 * q // 4),
                            seed=seeds, seed_input=inputs)]


GROUPS = {
    # ---- Null pipeline -------------------------------------------------------------
    # FIG 1 (seed variability). 25x25 repetitions; the figure compares the 2x4 average
    # (what every other group uses) against the 25x25 one. c1 is the non-trivial case:
    # its error is 2^b X^i * s, so it depends on the key (--seed). c0 does not.
    "enc_seeds": grid(dict(BASE), stage=ENC, seed=SEEDS_ANALYSIS, seed_input=SEEDS_ANALYSIS),

    # FIG 2 (logN does not change the pattern). x axis = bit, averaged over coefficients.
    "logN_cmp": grid(dict(LOGN_CMP, logN=6, logSlots=5, isExhaustive=1),
                     seed=SEEDS, seed_input=INPUTS)
              + grid(dict(LOGN_CMP, logN=16, logSlots=15, isExhaustive=0, numSamples=NUM_SAMPLES),
                     seed=SEEDS, seed_input=INPUTS),

    # FIG 3 (encode OpenFHE vs HEAAN, panel a) and FIG 4 (HEAAN encode / c0 / c1, panel b;
    # c0 and c1 come from enc_seeds filtered to seeds 1-3). HEAAN's encoded plaintext is
    # wider, hence bitsPerCoeff=128.
    "plain_cmp": grid(dict(BASE, stage="encode", bitsPerCoeff=128), seed=SEEDS, seed_input=INPUTS)
               + grid(dict(BASE_OPENFHE, stage="encode"), seed=SEEDS, seed_input=INPUTS),

    # FIG 5 (logDelta). Plot also with x = bit - logDelta: the curves should collapse.
    "sweep_delta": grid(dict(SWEEP_DELTA, stage="encrypt_c0"),
                        logDelta=LOGDELTA_SWEEP, seed=SEEDS, seed_input=INPUTS),

    # FIG 6 (logQ, x normalised by logQ). Scale invariance: logDelta moves with logQ.
    "sweep_q": sweep_q("encrypt_c0"),

    # FIG 7 (logSlots, panel c0 = gaps visible / panel c1 = no gaps).
    "sweep_slots": grid(dict(SWEEP_SLOTS), stage=ENC, logSlots=LOGSLOTS_SWEEP,
                        seed=SEEDS, seed_input=INPUTS),

    # FIG 8 (input magnitude). With l2_rel the c0 curve shifts by log2 of the magnitude
    # ratio. Paired sweep (logMax = logMin + 1), not a cartesian product.
    "sweep_input": [run for x in INPUT_SWEEP
                    for run in grid(dict(BASE, logDelta=20, logMin=x, logMax=x + 1),
                                    stage=ENC, seed=SEEDS, seed_input=INPUTS)],

    # EVIDENCE: with a null pipeline decrypt_c0 == encrypt_c0, decrypt_c1 == encrypt_c1
    # and decode == encode (same config as enc_seeds / plain_cmp).
    "dec_stages": grid(dict(BASE), stage=DEC, seed=SEEDS, seed_input=INPUTS)
                + grid(dict(BASE, stage="decode", bitsPerCoeff=128), seed=SEEDS, seed_input=INPUTS),

    # ---- With pipeline -------------------------------------------------------------
    # FIG 9 (add + rot preserves the coefficient gaps: the automorphism maps multiples
    # of the gap to multiples of the gap).
    "add_rot": grid(dict(CLIENT, pipeline="add; rot 3"),
                    stage=ENC, logSlots=LOGSLOTS_SWEEP, seed=SEEDS, seed_input=INPUTS),

    # FIG 10 (1, 2 and 3 muls, and what happens to the gaps).
    "mul": grid(dict(CLIENT_MUL), stage=ENC, pipeline=["mul", "mul x2", "mul x3"],
                seed=SEEDS, seed_input=INPUTS),

    # EVIDENCE: a fault at decryption does not see the pipeline, only the modulus level
    # it ends at. Same config as "mul", so it compares directly with it.
    "dec_after_mul": grid(dict(CLIENT_MUL, pipeline="mul x3"), stage=DEC + ["decode"],
                          seed=SEEDS, seed_input=INPUTS),

    # FIG 11 (the same muls followed by bootstrapping). Only compared within itself.
    "boot": grid(BOOT, pipeline=["mul x4", "mul x4; boot"], stage=ENC,
                 seed=SEEDS, seed_input=INPUTS),

    # ---- RNS / NTT (OpenFHE) ---------------------------------------------------------
    # FIG 12 (RNS: add + rot keeps the gaps). mult_depth=3 -> 4 limbs; use --vary limb.
    "add_rotRNS": grid(dict(CLIENT_OPENFHE, pipeline="add; rot 3", mult_depth=3),
                       stage=ENC, logSlots=[3, 5], seed=SEEDS, seed_input=INPUTS),
    # EVIDENCE: with a mul in RNS every bit breaks the output. Not plotted; quote the
    # SDC rate in the text.
    "mulRNS": grid(dict(CLIENT_OPENFHE, pipeline="mul", mult_depth=3),
                   stage=ENC, logSlots=[3, 5], seed=SEEDS, seed_input=INPUTS),

    # FIG 13 (NTT domain: a single flip spreads over every coefficient).
    "addNTT": grid(dict(CLIENT_OPENFHE, pipeline="add; rot 3", withNTT=1),
                   stage=ENC, logSlots=[3, 5], seed=SEEDS, seed_input=INPUTS),
}

if __name__ == "__main__":
    main(GROUPS, __doc__)
