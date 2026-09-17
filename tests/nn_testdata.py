#!/usr/bin/env python3
"""Datos sinteticos para testear el workload NN sin MNIST ni entrenamiento.

    python3 tests/nn_testdata.py /tmp/nndata      ->  /tmp/nndata/weights/*.csv + mnist_test.csv

Pesos chicos (la pre-activacion queda en |z| < 1.2) y el label de cada imagen es lo
que predice la red en claro, salvo la imagen 3, que tiene el label mal a proposito.
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1] if len(sys.argv) > 1 else "nndata")
(out / "weights").mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(0)
W1, b1 = rng.normal(0, 0.02, (64, 784)), rng.normal(0, 0.1, 64)
W2, b2 = rng.normal(0, 0.5, (10, 64)), rng.normal(0, 0.1, 10)
for name, m in {"W1": W1, "b1": b1, "W2": W2, "b2": b2}.items():
    np.savetxt(out / "weights" / f"{name}.csv", np.atleast_2d(m), delimiter=",", fmt="%.10g")

rows = []
for k in range(5):
    img = rng.integers(0, 256, 784)
    x = 2 * img / 255 - 1
    z = W1 @ x + b1
    label = int(np.argmax(W2 @ (0.98 * z - 0.23 * z**3) + b2))
    if k == 3:
        label = (label + 1) % 10   # mal clasificada a proposito
    rows.append([label, *img])

with open(out / "mnist_test.csv", "w") as f:
    f.write("label," + ",".join(f"px{i}" for i in range(784)) + "\n")
    for r in rows:
        f.write(",".join(map(str, r)) + "\n")
