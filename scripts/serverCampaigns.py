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
RESULTS_BOOT = str(ROOT / "results_boot")

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


## RES 1
BASE = dict(binary="fi_heaan", results_dir=RESULTS, isExhaustive=1,
              logN=6, logSlots=5, logQ=60, logDelta=40, bitsPerCoeff=64)

BASE_OPENFHE = dict(binary="fi_openfhe", results_dir=RESULTS, isExhaustive=1,
              logN=6, logSlots=5, logQ=60, logDelta=40, bitsPerCoeff=64)
# logN comparison: random on both sides so both have the same number of sampled coefficients
LOGN_CMP = dict(binary="fi_heaan", results_dir=RESULTS,
                logQ=60, logDelta=40, bitsPerCoeff=64, stage="encrypt_c0")
# logQ sweep at a fixed ratio: logDelta = 3/4 logQ, bitsPerCoeff = 5/4 logQ
LOGQ_SWEEP = [40, 60, 80, 100]
SWEEP_Q = dict(binary="fi_heaan", results_dir=RESULTS, isExhaustive=1,
               logN=6, logSlots=5)

LOGDELTA_SWEEP = [25,35,45,55]
SWEEP_DELTA = dict(binary="fi_heaan", results_dir=RESULTS, isExhaustive=1,
               logN=6, logSlots=5, logQ=60, bitsPerCoeff=64)

LOGSLOTS_SWEEP = [3,4,5]
SWEEP_SLOTS = dict(binary="fi_heaan", results_dir=RESULTS, isExhaustive=1,
               logN=6, logQ=60, logDelta=40, bitsPerCoeff=64)



INPUT_SWEEP = [0,9,19,29]

# RES 2
# Operaciones del servidor, anillo chico
SERVER = dict(binary="fi_heaan", results_dir=RESULTS, isExhaustive=1,
              logN=6, logSlots=4, logQ=60, logDelta=30, bitsPerCoeff=64)

# Bootstrapping: aleatorio, logQ grande
BOOT = dict(binary="fi_heaan", results_dir=RESULTS_BOOT, isExhaustive=0, numSamples=NUM_SAMPLES,
            logN=6, logSlots=3, logQ=840, logDelta=40, bitsPerCoeff=860)

# ASPLOS: exhaustivo, parametros chicos
ASPLOS = dict(binary="fi_heaan", results_dir=RESULTS, isExhaustive=1,
              logN=6, logSlots=3, logQ=60, logDelta=25, bitsPerCoeff=64, pipeline="add; mul")




def steps(base, n, seeds=SEEDS, inputs=INPUTS, **sweep):
    """Barrido de op_step 0..n-1 (y lo que se pase en sweep) sobre seeds x inputs."""
    return grid(base, op_step=range(n), seed=seeds, seed_input=inputs, **sweep)

def sweep_q(stage, seeds=SEEDS, inputs=INPUTS):
    """One campaign per logQ in LOGQ_SWEEP (x seeds x inputs), with logDelta and
    bitsPerCoeff scaled with logQ so every run sits at the same relative position."""
    return [run for q in LOGQ_SWEEP
            for run in grid(dict(SWEEP_Q, stage=stage, logQ=q,
                                 logDelta=3 * q // 4, bitsPerCoeff=5 * q // 4),
                            seed=seeds, seed_input=inputs)]

GROUPS = {
        # RES 1
    "enc_seeds": grid(dict(BASE), stage=["encrypt_c0", "encrypt_c1"], seed= SEEDS_ANALYSIS, seed_input=SEEDS_ANALYSIS),
    "logN_cmp": grid(dict(LOGN_CMP, logN=6, logSlots=5,  isExhaustive=1),  seed=SEEDS, seed_input=INPUTS)
              + grid(dict(LOGN_CMP, logN=16, logSlots=15,  isExhaustive=0, numSamples=50 ), seed=SEEDS, seed_input=INPUTS),
    "plain_cmp": grid(dict(BASE, stage="encode", bitsPerCoeff=128),  seed=SEEDS, seed_input=INPUTS) # Also to compare plain wint c0 and c1 all in heaan
              + grid(dict(BASE_OPENFHE, stage="encode"),  seed=SEEDS, seed_input=INPUTS),
    "sweep_q": sweep_q("encrypt_c0"),

    "sweep_delta": grid(dict(SWEEP_DELTA, stage="encrypt_c0"),
                        logDelta=LOGDELTA_SWEEP, seed=SEEDS, seed_input=INPUTS),
    "sweep_slots": grid(dict(SWEEP_SLOTS), stage=["encrypt_c0", "encrypt_c1"], logSlots=LOGSLOTS_SWEEP,
                         seed=SEEDS, seed_input=INPUTS),
    # Input magnitude sweep: logMin = x, logMax = x + 1 (paired, not a cartesian product).
    "sweep_input": [run for x in INPUT_SWEEP
                    for run in grid(dict(BASE, logDelta=20, logMin=x, logMax=x + 1),
                                    stage=["encrypt_c0", "encrypt_c1"],
                                    seed=SEEDS, seed_input=INPUTS)],
    "add_rot": grid(dict(SERVER, pipeline="add; rot 3"),
                    stage=["encrypt_c0", "encrypt_c1"], logSlots=[3, 4, 5],
                    seed=SEEDS, seed_input=INPUTS),
    "mul": grid(dict(SERVER, logQ=120, bitsPerCoeff=150),
                stage=["encrypt_c0", "encrypt_c1"], pipeline=["mul", "mul x2", "mul x3"],
                seed=SEEDS, seed_input=INPUTS),

    "boot": grid(BOOT, pipeline=["mul x4", "mul x4; boot"],
                 stage=["encrypt_c0", "encrypt_c1"], seed=SEEDS, seed_input=INPUTS),
    # RES 2

    "op_add": steps(dict(SERVER, stage="add", pipeline="add x2"), ADD_STEPS),

    "op_mul": steps(dict(SERVER, stage="mul_asplos", pipeline="mul"), MUL_STEPS,
                    seeds=SEEDS_MUL, inputs=SEEDS_MUL),

    "op_mul_depth": steps(dict(SERVER, stage="mul_asplos", pipeline="mul x3", logQ=160, bitsPerCoeff=174),
                          MUL_STEPS, seeds=SEEDS_MUL, inputs=SEEDS_MUL, op_depth=[0, 1, 2]),

    "op_rescale_depth": steps(dict(SERVER, stage="rescale", pipeline="mul x2"), RESCALE_STEPS,
                              op_depth=[0, 1]),

    "op_rot": steps(dict(SERVER, stage="rot_asplos", pipeline="rot 2"), ROT_STEPS),

    "boot_outside": steps(dict(BOOT, stage="boot", pipeline="mul x4; boot"), BOOT_STEPS,
                          seeds=SEEDS_BOOT, inputs=SEEDS_BOOT),

    # boot_eval necesita slots < N/2: con logSlots = logN-1 el fork no inyecta (imprime "Error en boot").
    "boot_eval": steps(dict(BOOT, stage="boot_eval", pipeline="mul x4; boot", logSlots=2), BOOT_EVAL_STEPS,
                       seeds=SEEDS_BOOT, inputs=SEEDS_BOOT),

    # Fault en el cliente, pipeline con bootstrapping al final.
    # Las variantes viejas con op_depth 1/2 eran la misma campania (op_depth no aplica al
    # cliente, y ahora el probe las rechaza), asi que quedan solo las pipelines distintas.
    # logQ=660 no alcanza para el boot con logDelta=34 (HEAAN hace segfault): se usa 840.
    "boot_ops": grid(dict(BOOT, logN=6, logSlots=4, logDelta=34),
                     pipeline=["add; mul x3; rot 1; boot", "add; mul x3; rot 2; boot",
                               "add; mul; boot", "add; mul x2; boot", "add; mul x2; rot 1; boot"],
                     stage=["encrypt_c0", "encrypt_c1"], seed=SEEDS_BOOT, seed_input=SEEDS_BOOT),

    "boot_ops_slots": grid(BOOT,
                           pipeline=["add; mul x3; rot 1; boot", "add; mul x3; rot 2; boot",
                                     "add; mul; boot", "add; mul x2; boot", "add; mul x2; rot 1; boot"],
                           stage=["encrypt_c0", "encrypt_c1"], logSlots=[1, 2, 3],
                           seed=SEEDS_BOOT, seed_input=SEEDS_BOOT),

    "asplos_mul": steps(dict(ASPLOS, stage="mul"), MUL_STEPS, seeds=[1], inputs=[1]),
    "asplos_add": steps(dict(ASPLOS, stage="add"), ADD_STEPS, seeds=[1], inputs=[1]),
}

BASE_TACO = dict(binary="fi_heaan", results_dir=RESULTS_TACO, isExhaustive=1,
              logN=6, logSlots=5, logQ=60, logDelta=25, bitsPerCoeff=64)
BASE_OpenFHE_TACO = dict(binary="fi_openfhe", results_dir=RESULTS_TACO, isExhaustive=1,
              logN=4, logSlots=2, logQ=60, logDelta=50, bitsPerCoeff=64, withNTT=0, mult_depth=3)
BOOT_TACO = dict(binary="fi_heaan", results_dir=RESULTS_TACO, isExhaustive=0, numSamples=NUM_SAMPLES,
            logN=6, logSlots=4, logQ=800, logDelta=40, bitsPerCoeff=820)

GROUPS_TACO = {
        "mul_taco": grid(dict(BASE_TACO, pipeline="mul"), stage=["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"],  seed=SEEDS, seed_input=INPUTS),
        "logQ_taco": grid(dict(BASE_TACO, logQ=45, logDelta=15), stage=["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"],  seed=SEEDS, seed_input=INPUTS),
        "gap_add_taco": grid(dict(BASE_TACO, logSlots=3, pipeline="add"), stage=["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"],  seed=SEEDS, seed_input=INPUTS),
        "gap_mul_taco": grid(dict(BASE_TACO, logSlots=3, pipeline="mul"), stage=["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"],  seed=SEEDS, seed_input=INPUTS),
        "Open_RNS_add_taco": grid(dict(BASE_OpenFHE_TACO,  pipeline="add"), stage=["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"],  seed=SEEDS, seed_input=INPUTS),
        "Open_RNS_mul1_taco": grid(dict(BASE_OpenFHE_TACO,  pipeline="mul"), stage=["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"],  seed=SEEDS, seed_input=INPUTS),
        "Open_RNS_mul3_taco": grid(dict(BASE_OpenFHE_TACO,  pipeline="mul x3"), stage=["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"],  seed=SEEDS, seed_input=INPUTS),
        "Open_NTT_add_taco": grid(dict(BASE_OpenFHE_TACO,  pipeline="mul", withNTT=1, mult_depth=0), stage=["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"],  seed=SEEDS, seed_input=INPUTS),
        "boot_taco": grid(BOOT_TACO, pipeline=["mul x3", "mul x3; boot"],
                 stage=["encrypt_c0", "encrypt_c1"], seed=SEEDS, seed_input=INPUTS),
        }
ALL_GROUPS = {**GROUPS, **GROUPS_TACO}
assert len(ALL_GROUPS) == len(GROUPS) + len(GROUPS_TACO), "a group name is defined twice"

if __name__ == "__main__":
    main(ALL_GROUPS, __doc__)

