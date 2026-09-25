#!/usr/bin/env python3
"""Results chapter 2: faults on the SERVER side, inside the operations (fi_heaan).

    python3 scripts/serverCampaigns.py                        # list the groups
    python3 scripts/serverCampaigns.py op_mul --dry-run       # print the commands
    python3 scripts/serverCampaigns.py op_* --jobs 8
    python3 scripts/serverCampaigns.py all --jobs 16

--op_step picks the internal step of the operation (the first steps are the input
ciphertexts, before the operation touches them). --op_depth picks WHICH occurrence of
that operation is hit when the pipeline has several (0 = the first one).

Fault model: the * stages do not restore the flipped register inside the
operation (a corrupted register that is read again later in the same op). The plain
"mul"/"rot" stages restore it right after the first read. All the groups here use the
* variants.

Old flags -> pipeline:  doAdd 2 -> "add x2", doMul 3 -> "mul x3", doRot 2 -> "rot 2",
doBoot 1 -> "boot" (at the end), exhaustiveSingleBitFlip -> isExhaustive=1,
randomSingleBitFlip -> isExhaustive=0.
"""
from campaigns import ROOT, grid, main

RESULTS = str(ROOT / "results_server")

SEEDS = [1, 2]          # --seed
INPUTS = [1, 2, 3, 4]         # --seed_input
SEEDS_MUL = [3, 4, 5]      # kept from the old mul campaigns so their data can be reused
SEEDS_BOOT = [1]           # boot is expensive: a single seed
NUM_SAMPLES = 50

# Number of op_step of each stage in the HEAAN fork (0 .. n-1)
ADD_STEPS = 6
MUL_STEPS = 26
RESCALE_STEPS = 4
ROT_STEPS = 12
BOOT_STEPS = 8             # boot      (bootstrapAndEqualBitFlip)
BOOT_EVAL_STEPS = 16       # boot_eval (evalExpAndEqualBitFlip)

# One representative op_step per pattern of mul. FIRST GUESS from reading
# multBitFlipAsplos; replace it with one step per band of the op_mul heatmap:
#   0, 1   input ciphertext (ax, bx)
#   4      (a1+b1): only the cross term d1
#   8      b1 in b1*b2: goes straight to the output c0
#   10     a1*a2 before the relinearisation key          (mod qQ)
#   11     relinearisation key                            (mod qQ)
#   14     key-switch product before the shift by logQ    (mod qQ)
#   24, 25 output (ax, bx)
MUL_REPR = [0, 1, 4, 8, 10, 11, 14, 24, 25]
# Same list without the steps that live mod qQ (only for the boot configs, whose logQ=840
# would need bitsPerCoeff ~1700 to cover them; the key-switch steps are covered by op_mul).
MUL_REPR_Q = [s for s in MUL_REPR if s not in (10, 11, 14)]


def keyswitch_bits(logQ):
    """Register width of the key-switching steps: HEAAN computes them mod q*Q with
    Q = 2^logQ, so they are up to 2*logQ bits wide. With bitsPerCoeff = logQ + 4 the
    upper half is never flipped, and the lower half is exactly the part the shift by
    logQ throws away: those steps would look harmless."""
    return 2 * logQ + 4


# Server operations, exhaustive. logSlots=3 (gap = 4) as in chapter 1.
SERVER = dict(binary="fi_heaan", results_dir=RESULTS, isExhaustive=1,
              logN=6, logSlots=3, logQ=60, logDelta=30, bitsPerCoeff=64)
# mul and rot have key-switching steps (mod qQ).
SERVER_KS = dict(SERVER, bitsPerCoeff=keyswitch_bits(60))
# mul x3: 3*30 = 90 bits consumed, 70 left at decryption.
SERVER_DEPTH = dict(SERVER, logQ=160, bitsPerCoeff=keyswitch_bits(160))
# mul x2: 2*30 = 60 bits consumed; logQ=100 leaves 40 >= logDelta at decryption.
SERVER_RESCALE = dict(SERVER, logQ=100, bitsPerCoeff=110)

# Bootstrapping: random, large logQ.
BOOT = dict(binary="fi_heaan", results_dir=RESULTS, isExhaustive=0, numSamples=NUM_SAMPLES,
            logN=6, logSlots=3, logQ=840, logDelta=40, bitsPerCoeff=860)

# Mixed pipeline: ops before and after each mul. Run with and without the final boot on
# the SAME config, so the only difference between the two groups is the boot.
MIX_PIPELINE = "add; mul; rot 2; mul; add"
# mul steps that live mod q*Q (key switching). Their registers are ~2*logQ bits wide,
# so with the boot configs (logQ=840, bitsPerCoeff=860) they would only be half swept.
MUL_KS_STEPS = range(10, 16)
MUL_STEPS_Q = [s for s in range(MUL_STEPS) if s not in MUL_KS_STEPS]

def steps(base, op_steps, seeds=SEEDS, inputs=INPUTS, **sweep):
    """Sweep of op_step (an int n means 0..n-1, or an explicit list) over seeds x inputs."""
    op_steps = range(op_steps) if isinstance(op_steps, int) else op_steps
    return grid(base, op_step=op_steps, seed=seeds, seed_input=inputs, **sweep)


GROUPS = {
    # ---- Single operations: heatmap op_step x bit, then one curve per pattern ----------
    # FIG 1 (add). Expected 2 patterns: steps {0, 1, 4} behave as c1, {2, 3, 5} as c0.
    "op_add": steps(dict(SERVER, stage="add", pipeline="add x2"), ADD_STEPS),

    # FIG 2 (mul, the 26 steps). Run this first: its heatmap fixes MUL_REPR.
    "op_mul": steps(dict(SERVER_KS, stage="mul", pipeline="mul"), MUL_STEPS,
                    seeds=SEEDS_MUL, inputs=SEEDS_MUL),

    # FIG 2b / EVIDENCE (which mul of the chain is hit). Only the representative steps,
    # and 1 seed x 3 inputs (chapter 1 shows the seed does not matter): 26 steps x 9
    # repetitions would be ~15M injections. Each mul multiplies by a fresh encryption, so
    # the relative error should stay roughly constant with depth; what changes is the
    # modulus (logQ - 30*op_depth), so plot with x = bit - logq.
    "op_mul_depth": steps(dict(SERVER_DEPTH, stage="mul", pipeline="mul x3"), MUL_REPR,
                          seeds=SEEDS_MUL[:1], inputs=SEEDS_MUL, op_depth=[0, 1, 2]),

    # FIG 3 (rescale). Steps 0/1 = ax/bx before the shift, 2/3 = after. Expected: the
    # "before" curves are the "after" ones shifted by logDelta (the flip is divided by Delta).
    "op_rescale_depth": steps(dict(SERVER_RESCALE, stage="rescale", pipeline="mul x2"), RESCALE_STEPS,
                              op_depth=[0, 1]),

    # FIG 4 (rot). 0, 9 = c0 path; 1, 2, 4 = c1 path before key switching; 3, 5 = key;
    # 6, 7 = before the shift by logQ (mod qQ); 8, 10, 11 = output.
    "op_rot": steps(dict(SERVER_KS, stage="rot", pipeline="rot 2"), ROT_STEPS),

    # ---- Mixed pipeline, hitting mul --------------------------------------------------
    # FIG 5 (mixed pipeline, fault in the 1st or 2nd mul). 1 seed x 3 inputs: every
    # injection of the boot variant runs a full bootstrapping.
    "mix_mul": steps(dict(BOOT, stage="mul", pipeline=MIX_PIPELINE), MUL_REPR_Q,
                     seeds=SEEDS_BOOT, inputs=INPUTS, op_depth=[0, 1]),

    # FIG 6 (same + boot). Expected: small errors go through the boot, large ones break
    # the sine approximation and the whole output.
    "mix_mul_boot": steps(dict(BOOT, stage="mul", pipeline=MIX_PIPELINE + "; boot"),
                          MUL_REPR_Q, seeds=SEEDS_BOOT, inputs=INPUTS, op_depth=[0, 1]),

    # ---- Inside the bootstrapping -----------------------------------------------------
    # FIG 7a (boot, the 8 checkpoints between its sub-steps).
    "boot_outside": steps(dict(BOOT, stage="boot", pipeline="mul x4; boot"), BOOT_STEPS,
                          seeds=SEEDS_BOOT, inputs=SEEDS_BOOT),

    # FIG 7b (inside evalExp). Needs slots < N/2: with logSlots = logN-1 the fork does not
    # inject (it prints "Error en boot").
    "boot_eval": steps(dict(BOOT, stage="boot_eval", pipeline="mul x4; boot", logSlots=2),
                       BOOT_EVAL_STEPS, seeds=SEEDS_BOOT, inputs=SEEDS_BOOT),

    # ---- Not plotted in this chapter --------------------------------------------------
    # ML dataset: client fault, several pipelines ending in boot.
    # logQ=660 is not enough for the boot with logDelta=34 (HEAAN segfaults): 840.
    "boot_ops": grid(dict(BOOT, logSlots=4, logDelta=34),
                     pipeline=["add; mul x3; rot 1; boot", "add; mul x3; rot 2; boot",
                               "add; mul; boot", "add; mul x2; boot", "add; mul x2; rot 1; boot"],
                     stage=["encrypt_c0", "encrypt_c1"], seed=SEEDS_BOOT, seed_input=SEEDS_BOOT),

    "boot_ops_slots": grid(BOOT,
                           pipeline=["add; mul x3; rot 1; boot", "add; mul x3; rot 2; boot",
                                     "add; mul; boot", "add; mul x2; boot", "add; mul x2; rot 1; boot"],
                           stage=["encrypt_c0", "encrypt_c1"], logSlots=[1, 2, 3],
                           seed=SEEDS_BOOT, seed_input=SEEDS_BOOT),
    # ---- Exploration: every op_step, one repetition --------------------------------------
    # To look at every step before choosing MUL_REPR. The seeds are a subset of the full
    # groups, so the campaigns shared with them are not run twice.
    "explore_mul_depth": steps(dict(SERVER_DEPTH, stage="mul", pipeline="mul x3"),
                               MUL_STEPS, seeds=SEEDS_MUL[:1], inputs=SEEDS_MUL[:1],
                               op_depth=[0, 1, 2]),
    "explore_mix_mul": steps(dict(BOOT, stage="mul", pipeline=MIX_PIPELINE, numSamples=10),
                             MUL_STEPS_Q, seeds=SEEDS_BOOT, inputs=INPUTS[:1], op_depth=[0, 1]),
    "explore_mix_mul_boot": steps(dict(BOOT, stage="mul", pipeline=MIX_PIPELINE + "; boot",
                                       numSamples=10),
                                  MUL_STEPS_Q, seeds=SEEDS_BOOT, inputs=INPUTS[:1], op_depth=[0, 1]),
}

if __name__ == "__main__":
    main(GROUPS, __doc__)
