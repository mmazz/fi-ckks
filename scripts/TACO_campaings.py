#!/usr/bin/env python3
"""Campanias de operaciones del servidor (fi_heaan).

    python3 scripts/serverCampaigns.py                        # lista los grupos
    python3 scripts/serverCampaigns.py op_add --dry-run       # muestra los comandos
    python3 scripts/serverCampaigns.py op_add op_mul --jobs 8
    python3 scripts/serverCampaigns.py all --jobs 16

Equivalencias con la version vieja (doAdd/doMul/... -> --pipeline):
    doAdd 2              -> "add x2"
    doMul 3              -> "mul x3"
    doRot 2              -> "rot 2"     (una rotacion de 2 slots)
    doBoot 1             -> "boot"      (al final del pipeline)
    exhaustiveSingleBitFlip -> isExhaustive=1
    randomSingleBitFlip     -> isExhaustive=0
"""
from campaigns import ROOT, grid, main

RESULTS = str(ROOT / "results")
RESULTS_TACO = str(ROOT / "results_taco")

SEEDS_ANALYSIS = range(25)
SEEDS = [1, 2, 3]           # --seed
INPUTS = [1, 2, 3]          # --seed_input
SEEDS_MUL = [3, 4, 5]    # las campanias de mul usaban otra lista de seeds; se conserva
SEEDS_BOOT = [1]         # boot es caro: una sola seed
NUM_SAMPLES = 50

# Cantidad de op_step de cada stage del fork (0 .. n-1)
ADD_STEPS = 6
MUL_STEPS = 26
RESCALE_STEPS = 4
ROT_STEPS = 12
BOOT_STEPS = 8           # boot (bootstrapAndEqualBitFlip)
BOOT_EVAL_STEPS = 16     # boot_eval (evalExpAndEqualBitFlip)


BASE_TACO = dict(binary="fi_heaan", results_dir=RESULTS_TACO, isExhaustive=1,
              logN=6, logSlots=5, logQ=60, logDelta=25, bitsPerCoeff=64)

BASE_OpenFHE_TACO = dict(binary="fi_openfhe", results_dir=RESULTS_TACO, isExhaustive=1,
              logN=4, logSlots=2, logQ=60, logDelta=50, bitsPerCoeff=64, withNTT=0, mult_depth=3)

BOOT_TACO = dict(binary="fi_heaan", results_dir=RESULTS_TACO, isExhaustive=0, numSamples=NUM_SAMPLES,
            logN=6, logSlots=4, logQ=840, logDelta=40, bitsPerCoeff=860)

GROUPS_TACO = {
        "mul_taco":           grid(dict(BASE_TACO, pipeline="mul"), stage=["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"],  seed=SEEDS, seed_input=INPUTS),
        "logQ_taco":          grid(dict(BASE_TACO, logQ=45, logDelta=15), stage=["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"],  seed=SEEDS, seed_input=INPUTS),
        "gap_add_taco":       grid(dict(BASE_TACO, logSlots=3, pipeline="add"), stage=["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"],  seed=SEEDS, seed_input=INPUTS),
        "gap_mul_taco":       grid(dict(BASE_TACO, logSlots=3, pipeline="mul"), stage=["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"],  seed=SEEDS, seed_input=INPUTS),
        "Open_RNS_add_taco":  grid(dict(BASE_OpenFHE_TACO,  pipeline="add"), stage=["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1"],  seed=SEEDS, seed_input=INPUTS),
        "Open_RNS_mul1_taco": grid(dict(BASE_OpenFHE_TACO,  pipeline="mul"), stage=["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1"],  seed=SEEDS, seed_input=INPUTS),
        "Open_RNS_mul3_taco": grid(dict(BASE_OpenFHE_TACO,  pipeline="mul x3"), stage=["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1"],  seed=SEEDS, seed_input=INPUTS),
        "Open_NTT_add_taco":  grid(dict(BASE_OpenFHE_TACO,  pipeline="add", withNTT=1, mult_depth=0), stage=["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1"],  seed=SEEDS, seed_input=INPUTS),
        "boot_taco":          grid(dict(BOOT_TACO), pipeline=["mul x3", "mul x3; boot", "pmul x3; boot", "mul x5; boot", "mul; boot", "boot"],stage=["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"], seed=SEEDS, seed_input=INPUTS),
        "mul_multiBit_taco":           grid(dict(BASE_TACO, pipeline="mul"), amountBits=[3,6], stage=["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"],  seed=SEEDS, seed_input=INPUTS),
                # Client registers with and without the final boot (BOOT_TACO with logSlots=3).
        # HEAAN encode is swept from bit logQ up (below it encryptMsg rounds the flip away),
        # and bit logQ + k acts as bit k of a ciphertext: bitsPerCoeff = logQ + 860 gives
        # encode exactly the bit list of the other stages, shifted by logQ.
        "boot_client_taco": (
            grid(dict(BOOT_TACO, logSlots=3), pipeline=["mul x4", "mul x4; boot"],
                 stage=["encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"],
                 seed=SEEDS, seed_input=INPUTS)
            + grid(dict(BOOT_TACO, logSlots=3, bitsPerCoeff=840 + 860),
                   pipeline=["mul x4", "mul x4; boot"], stage=["encode"],
                   seed=SEEDS, seed_input=INPUTS)),
        }
ALL_GROUPS = {**GROUPS_TACO}
assert len(ALL_GROUPS) == len(GROUPS_TACO), "a group name is defined twice"

if __name__ == "__main__":
    main(ALL_GROUPS, __doc__)

