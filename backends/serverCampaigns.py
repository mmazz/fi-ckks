from utilsGen import cartesian_product_rows, write_csv, SEEDS_PRNG, SEEDS_INP, EXTRA_SEEDS, SEEDS_PRNG_NN, SEEDS_INP_NN
ADD_STEPS = 5
MUL_STEPS = 25
RESCALE_STEPS = 3
ROT_STEPS = 11
BOOTOUT_STEPS = 7
BOOTEVAL_STEPS = 15

seed_init = 3
seed_list = list(range(seed_init, seed_init+SEEDS_PRNG+1))




def gen_opServerAdd_analysis():
    fixed = {
        "binary": "exhaustiveSingleBitFlip",
        "library": "heaan",  # ajustar si corresponde a $(LIBRARY)
        "logN": 6,
        "logQ": 120,
        "bitsPerCoeff": 144,
        "logDelta": 40,
        "stage": "add_inside",
        "doAdd": 2,
        "op_depth": 0,
        "logSlots": 4,
    }
    sweep = {
        "seed": list(range(1, SEEDS_PRNG+1)),
        "seed_input": list(range(1, SEEDS_INP+1)),
        "op_step": list(range(0,ADD_STEPS+1)),
    }
    write_csv("opServerAdd_analysis", cartesian_product_rows(fixed, sweep))


def gen_opServerMul_analysis():
    fixed = {
        "binary": "exhaustiveSingleBitFlip",
        "library": "heaan",  # ajustar si corresponde a $(LIBRARY)
        "logN": 6,
        "logQ": 120,
        "bitsPerCoeff": 144,
        "logDelta": 40,
        "stage": "mul_inside_asplos",
        "doMul": 1,
        "op_depth": 0,
        "mult_depth": 0,
        "logSlots": 4,
    }
    sweep = {
        "seed": seed_list,
        "seed_input": seed_list,
        "op_step": list(range(0,MUL_STEPS+1)),
    }
    write_csv("opServerMul_analysis", cartesian_product_rows(fixed, sweep))

def gen_opServerMulDepth_analysis():
    fixed = {
        "results": "/home/mmazz/ckks-singleBitFlip/results",
        "binary": "exhaustiveSingleBitFlip",
        "library": "heaan",  # ajustar si corresponde a $(LIBRARY)
        "logN": 6,
        "logQ": 160,
        "bitsPerCoeff": 174,
        "logDelta": 40,
        "stage": "mul_inside_asplos",
        "doMul": 3,
        "mult_depth": 0,
        "logSlots": 4,
    }
    sweep = {
        "seed": seed_list,
        "seed_input": seed_list,
        "op_depth": [0,1,2],
        "op_step": list(range(0,MUL_STEPS+1)),
    }
    write_csv("opServerMulDepth_analysis", cartesian_product_rows(fixed, sweep))


def gen_opServerRescaleDepth_analysis():
    fixed = {
        "binary": "exhaustiveSingleBitFlip",
        "library": "heaan",  # ajustar si corresponde a $(LIBRARY)
        "logN": 6,
        "logQ": 120,
        "bitsPerCoeff": 144,
        "logDelta": 40,
        "stage": "rescale_inside",
        "doMul": 2,
        "mult_depth": 0,
        "logSlots": 4,
    }
    sweep = {
        "seed": list(range(1, SEEDS_PRNG+1)),
        "seed_input": list(range(1, SEEDS_INP+1)),
        "op_step": list(range(0,RESCALE_STEPS+1)),
        "op_depth": [0,1],
    }
    write_csv("opServerRescaleDepth_analysis", cartesian_product_rows(fixed, sweep))

def gen_opServerRot_analysis():
    fixed = {
        "binary": "exhaustiveSingleBitFlip",
        "library": "heaan",  # ajustar si corresponde a $(LIBRARY)
        "logN": 6,
        "logQ": 120,
        "bitsPerCoeff": 144,
        "logDelta": 40,
        "stage": "rot_inside_asplos",
        "doRot": 2,
        "logSlots": 4,
    }
    sweep = {
        "seed": list(range(1, SEEDS_PRNG+1)),
        "seed_input": list(range(1, SEEDS_INP+1)),
        "op_step": list(range(0,ROT_STEPS+1)),
    }
    write_csv("opServerRot_analysis", cartesian_product_rows(fixed, sweep))


def gen_opServerBootOutside_analysis():
    sweep = {
        "seed": list(range(1, SEEDS_PRNG_NN+1)),
        "seed_input": list(range(1, SEEDS_INP_NN+1)),
        "op_step": list(range(0,BOOTOUT_STEPS+1)),
    }
    fixed = {
        "binary": "randomSingleBitFlip",
        "library": "heaan",
        "stage": "boot_outside",
        "logN": 4,
        "logDelta": 40,
        "bitsPerCoeff": 860,
        "logSlots": 3,
        "logQ": 840,
        "doMul": 4,
        "doBoot": 1,
        "withNTT": 0,
    }

    write_csv("bootOutside_analysis", cartesian_product_rows(fixed, sweep))

def gen_opServerBootEval_analysis():
    sweep = {
        "seed": list(range(1, SEEDS_PRNG_NN+1)),
        "seed_input": list(range(1, SEEDS_INP_NN+1)),
        "op_step": list(range(0,BOOTEVAL_STEPS+1)),
    }
    fixed = {
        "binary": "randomSingleBitFlip",
        "library": "heaan",
        "stage": "boot_eval",
        "logN": 4,
        "logDelta": 40,
        "bitsPerCoeff": 860,
        "logSlots": 3,
        "logQ": 840,
        "doMul": 4,
        "doBoot": 1,
        "withNTT": 0,
    }

    write_csv("bootEval_analysis", cartesian_product_rows(fixed, sweep))

def gen_opServerBootOps_analysis():
    variants = [
            {"doAdd":1, "doMul":3 , "doRot": 1},
            {"doAdd":1, "doMul":3 , "doRot": 1, "op_depth": 1},
            {"doAdd":1, "doMul":3 , "doRot": 2, "op_depth": 1},
            {"doAdd":1, "doMul":3 , "doRot": 1, "op_depth": 2},
            {"doAdd":1, "doMul":1 },
            {"doAdd":1, "doMul":2 },
            {"doAdd":1, "doMul":2 , "doRot": 1},
    ]
    sweep = {
        "seed": list(range(1, 2)),
        "seed_input": list(range(1, 2)),
        "stage" : ["encrypt_c0", "encrypt_c1"]
    }
    rows = []
    for v in variants:
        fixed = {
            "results": "/home/mmazz/ckks-singleBitFlip/results_boot",
            "binary": "randomSingleBitFlip",
            "library": "heaan",
            "logN": 6,
            "logSlots": 4,
            "logDelta": 34,
            "logQ": 660,
            "bitsPerCoeff": 680,
            "doBoot": 1,
            "withNTT": 0,
            **v,
        }
        rows += cartesian_product_rows(fixed, sweep)

    write_csv("bootOps_analysis", rows)

def gen_opServerBootOpsSlots_analysis():
    variants = [
            {"doAdd":1, "doMul":3 , "doRot": 1},
            {"doAdd":1, "doMul":3 , "doRot": 1, "op_depth": 1},
            {"doAdd":1, "doMul":3 , "doRot": 2, "op_depth": 1},
            {"doAdd":1, "doMul":3 , "doRot": 1, "op_depth": 2},
            {"doAdd":1, "doMul":1 },
            {"doAdd":1, "doMul":2 },
            {"doAdd":1, "doMul":2 , "doRot": 1},
    ]
    sweep = {
        "seed": list(range(1, 2)),
        "seed_input": list(range(1, 2)),
        "stage" : ["encrypt_c0", "encrypt_c1"],
        "logSlots": [1,2,3]
    }
    rows = []
    for v in variants:
        fixed = {
            "results": "/home/mmazz/ckks-singleBitFlip/results_boot",
            "binary": "randomSingleBitFlip",
            "library": "heaan",
            "logN": 4,
            "logDelta": 40,
            "logQ": 840,
            "bitsPerCoeff": 860,
            "doBoot": 1,
            "withNTT": 0,
            **v,
        }
        rows += cartesian_product_rows(fixed, sweep)

    write_csv("bootOpsSlots_analysis", rows)





def gen_ASPLOS_mul_analysis():
    variants = [
            {"logN": 6,  "logSlots": 3, "logQ": 60, "logDelta": 25, "bitsPerCoeff": 64, "doAdd":1, "doMul":1 },
    ]
    sweep = {
        "seed": list(range(1, 2)),
        "seed_input": list(range(1, 2)),
        "op_step": list(range(0,MUL_STEPS+1)),
    }
    rows = []
    for v in variants:
        fixed = {
            "library": "heaan",
            "stage": "mul_inside",
            "withNTT": 0,
            "binary": "exhaustiveSingleBitFlip",
            **v,
        }
        rows += cartesian_product_rows(fixed, sweep)

    write_csv("mul_inside_asplos_analysis", rows)

def gen_ASPLOS_add_analysis():
    variants = [
            {"logN": 6,  "logSlots": 3, "logQ": 60, "logDelta": 25, "bitsPerCoeff": 64, "doAdd":1, "doMul":1 },
    ]
    sweep = {
        "seed": list(range(1, 2)),
        "seed_input": list(range(1, 2)),
        "op_step": list(range(0,ADD_STEPS+1)),
    }
    rows = []
    for v in variants:
        fixed = {
            "library": "heaan",
            "stage": "add_inside",
            "withNTT": 0,
            "binary": "exhaustiveSingleBitFlip",
            **v,
        }
        rows += cartesian_product_rows(fixed, sweep)

    write_csv("add_inside_asplos_analysis", rows)
