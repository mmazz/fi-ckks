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
RESULTS_BOOT = str(ROOT / "results_boot")

SEEDS = [1, 2]           # --seed
INPUTS = [1, 2]          # --seed_input
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

SEEDS = dict(binary="fi_heaan", results_dir=RESULTS, isExhaustive=1,
              logN=6, logSlots=5, logQ=60, logDelta=40, bitsPerCoeff=64, )
# Operaciones del servidor, anillo chico
SERVER = dict(binary="fi_heaan", results_dir=RESULTS, isExhaustive=1,
              logN=6, logSlots=4, logQ=120, logDelta=40, bitsPerCoeff=144)

# Bootstrapping: aleatorio, logQ grande
BOOT = dict(binary="fi_heaan", results_dir=RESULTS_BOOT, isExhaustive=0, numSamples=NUM_SAMPLES,
            logN=4, logSlots=3, logQ=840, logDelta=40, bitsPerCoeff=860)

# ASPLOS: exhaustivo, parametros chicos
ASPLOS = dict(binary="fi_heaan", results_dir=RESULTS, isExhaustive=1,
              logN=6, logSlots=3, logQ=60, logDelta=25, bitsPerCoeff=64, pipeline="add; mul")


def steps(base, n, seeds=SEEDS, inputs=INPUTS, **sweep):
    """Barrido de op_step 0..n-1 (y lo que se pase en sweep) sobre seeds x inputs."""
    return grid(base, op_step=range(n), seed=seeds, seed_input=inputs, **sweep)


GROUPS = {
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

if __name__ == "__main__":
    main(GROUPS, __doc__)
