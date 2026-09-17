#!/usr/bin/env python3
"""Campanias de la red neuronal (fi_heaan_nn / fi_openfhe_nn).

    python3 scripts/NNCampaigns.py                          # lista los grupos
    python3 scripts/NNCampaigns.py heaan_client --dry-run   # muestra los comandos
    python3 scripts/NNCampaigns.py heaan_hidden_layer heaan_cheby_tanh3 --jobs 8
    python3 scripts/NNCampaigns.py all --jobs 16

Los datos de la red (pesos + mnist_test.csv) se buscan en workloads/nn/data,
o en $FI_NN_DATA si esta definida.
"""
from campaigns import ROOT, grid, main
RESULTS = str(ROOT / "results_NN")
RESULTS = "results_NN"   # en el server conviene un path absoluto
SEEDS = [1]              # --seed: claves y ruido
IMAGES = [0]             # --seed_input: indice de la imagen en mnist_test.csv
NUM_SAMPLES = 50         # coeficientes al azar por campania, cada uno con todos los bits

HEAAN = dict(binary="fi_heaan_nn", results_dir=RESULTS, isExhaustive=0, numSamples=NUM_SAMPLES,
             logN=12, logQ=220, logDelta=30, logSlots=10, bitsPerCoeff=250)
OPENFHE = dict(binary="fi_openfhe_nn", results_dir=RESULTS, isExhaustive=0, numSamples=NUM_SAMPLES,
               logN=12, logQ=60, logDelta=50, logSlots=10, bitsPerCoeff=64, mult_depth=5, withNTT=1)

# stage -> cantidad de op_step (ver la cabecera de workloads/nn/heaan_nn.cpp y openfhe_nn.cpp)
HEAAN_INTERNAL = {"hidden_layer": 14, "cheby_tanh3": 10, "mul": 26, "rescale": 4, "add": 6, "rot": 12}
OPENFHE_INTERNAL = {"hidden_layer": 14, "cheby_tanh3": 10}

HEAAN_CLIENT = ["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"]
OPENFHE_CLIENT = ["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1"]


def client(base, stages):
    return grid(base, stage=stages, seed=SEEDS, seed_input=IMAGES)


def internal(base, stage, steps):
    return grid(dict(base, stage=stage), op_step=range(steps), seed=SEEDS, seed_input=IMAGES)


GROUPS = {
    "heaan_client": client(HEAAN, HEAAN_CLIENT),
    **{f"heaan_{st}": internal(HEAAN, st, n) for st, n in HEAAN_INTERNAL.items()},
    "openfhe_client": client(OPENFHE, OPENFHE_CLIENT),
    **{f"openfhe_{st}": internal(OPENFHE, st, n) for st, n in OPENFHE_INTERNAL.items()},
}

if __name__ == "__main__":
    main(GROUPS, __doc__)
