#!/usr/bin/env python3
"""NN campaigns (fi_heaan_nn / fi_openfhe_nn).

    python3 scripts/NNCampaigns.py                          # lista los grupos
    python3 scripts/NNCampaigns.py heaan_client --dry-run   # muestra los comandos
    python3 scripts/NNCampaigns.py heaan_hidden_layer heaan_cheby_tanh3 --jobs 8
    python3 scripts/NNCampaigns.py all --jobs 16
The network data (weights + mnist_test.csv) is read from workloads/nn/data, or from $FI_NN_DATA if set.
"""
from campaigns import ROOT, grid, main
RESULTS = str(ROOT / "results_NN")
IMAGES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]     # --seed_input: index of the image in mnist_test.csv
NUM_SAMPLES = 20             
SEEDS = [2]             

HEAAN = dict(binary="fi_heaan_nn", results_dir=RESULTS, isExhaustive=0, numSamples=NUM_SAMPLES,
             logN=12, logQ=220, logDelta=30, logSlots=10, bitsPerCoeff=250)
OPENFHE = dict(binary="fi_openfhe_nn", results_dir=RESULTS, isExhaustive=0, numSamples=NUM_SAMPLES,
               logN=12, logQ=60, logDelta=30, logSlots=10, bitsPerCoeff=64, mult_depth=5, withNTT=1)
OPENFHE_NON_NTT = dict(binary="fi_openfhe_nn", results_dir=RESULTS, isExhaustive=0, numSamples=NUM_SAMPLES,
               logN=12, logQ=60, logDelta=50, logSlots=10, bitsPerCoeff=64, mult_depth=5, withNTT=0)


OPENFHE_TEST = dict(binary="fi_openfhe_nn", results_dir=RESULTS, isExhaustive=0, numSamples=NUM_SAMPLES,
               logN=12, logQ=60, logDelta=50, logSlots=10, bitsPerCoeff=64, mult_depth=3, withNTT=1)
# Registers mod q*Q, up to 2*logQ bits: key switching (mul, rot) and encode, which is added
# to the encryption mod q*Q before the shift by logQ.
HEAAN_KS = dict(HEAAN, bitsPerCoeff=2 * 220 + 4)

# stage -> number of op_steps (see the header of workloads/nn/heaan_nn.cpp and openfhe_nn.cpp)
HEAAN_INTERNAL = {"hidden_layer": 14, "cheby_tanh3": 10, "mul": 26, "rescale": 4, "add": 6, "rot": 12}
OPENFHE_INTERNAL = {"hidden_layer": 14, "cheby_tanh3": 10}

HEAAN_CLIENT = ["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"]
OPENFHE_CLIENT = ["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1"]
OPENFHE_CLIENT_TEST = ["encrypt_c0"]


# Accuracy and F1 without faults, with the same parameters as the campaigns (fi_nn_metrics_*).
# Images [0, METRIC_IMAGES) are split in chunks of METRIC_CHUNK, one run per chunk, so --jobs
# runs them in parallel. Keep METRIC_IMAGES a multiple of METRIC_CHUNK.
# Each run writes results_NN/nn_metrics/<config>_img<a>-<b>.csv and is skipped if that file
# already exists. Summary: python3 analysis/nn_accuracy.py
METRIC_IMAGES = 1000
METRIC_CHUNK = 50

def client(base, stages):
    return grid(base, stage=stages, seed=SEEDS, seed_input=IMAGES)


def internal(base, stage, steps):
    return grid(dict(base, stage=stage), op_step=range(steps), seed=SEEDS, seed_input=IMAGES)

def metrics(base, binary):
    return grid(dict(base, binary=binary, images=METRIC_CHUNK), seed=SEEDS,
                first_image=range(0, METRIC_IMAGES, METRIC_CHUNK))

GROUPS = {
    "heaan_client": client(HEAAN, [s for s in HEAAN_CLIENT if s != "encode"])
                    + client(HEAAN_KS, ["encode"]),
    **{f"heaan_{st}": internal(HEAAN, st, n) for st, n in HEAAN_INTERNAL.items()},
    **{f"heaan_{st}": internal(HEAAN_KS if st in ("mul", "rot") else HEAAN, st, n)
       for st, n in HEAAN_INTERNAL.items()},
    "openfhe_client": client(OPENFHE, OPENFHE_CLIENT),
    "openfhe_client_nonNTT": client(OPENFHE_NON_NTT, OPENFHE_CLIENT),
    **{f"openfhe_{st}": internal(OPENFHE, st, n) for st, n in OPENFHE_INTERNAL.items()},
    **{f"openfhe_{st}_nonNTT": internal(OPENFHE_NON_NTT, st, n) for st, n in OPENFHE_INTERNAL.items()},
    "openfhe_client_test": client(OPENFHE_TEST, OPENFHE_CLIENT_TEST),
    "heaan_metrics":   metrics(HEAAN, "fi_nn_metrics_heaan"),
    "openfhe_metrics": metrics(OPENFHE, "fi_nn_metrics_openfhe"),
}

if __name__ == "__main__":
    main(GROUPS, __doc__)
