# fi-ckks

Fault injection for CKKS, at the level of single polynomial coefficients.

The idea is simple: run a CKKS workload (encode, encrypt, a few server-side
operations, decrypt, decode), flip one or a few bits of **one** coefficient
somewhere along the way, and measure how much the decrypted result moves away
from the fault-free output. Repeat that for every coefficient/bit (or a random
subset) and you get a map of which positions actually matter.

It currently supports two libraries, both forked so we control the PRNG and
every run is reproducible:

- **HEAAN** ([HEAAN-PRNG-Control](https://github.com/mmazz/HEAAN-PRNG-Control)):
  the original, non-RNS CKKS. Coefficients are big integers mod Q, so there is
  only one "limb".
- **OpenFHE** ([openfhe-PRNG-Control](https://github.com/mmazz/openfhe-PRNG-Control)):
  RNS + NTT. Faults are injected in one RNS limb, either in coefficient or
  NTT representation. This fork also has an SDC detector, which we log.

This is research code for my PhD. It's meant to be correct and reproducible,
not fast or pretty.

## Fault model

A fault is described by:

| field        | meaning                                                  |
|--------------|----------------------------------------------------------|
| `stage`      | where in the pipeline the fault happens (see below)      |
| `op_depth`   | which occurrence of that op (0 = first `mul`, 1 = second, ...) |
| `op_step`    | which internal step of the op (only for `*_inside` stages) |
| `limb`       | RNS limb (always 0 for HEAAN)                            |
| `coeff`      | coefficient index, `0 .. N-1`                            |
| `bit`        | first bit to flip                                        |
| `amountBits` | how many consecutive bits to flip (1 = single bit flip)  |

Faults are **transient**: every injection re-runs the whole pipeline from a
clean state (same keys, same PRNG seed), the flip is applied exactly once and
nothing else is touched. The injector checks this on every run: if the fault
fired zero times, more than once, or changed a different number of bits than
`amountBits`, the campaign aborts instead of silently writing garbage.

### Stages

Client side: `encode`, `encrypt_c0`, `encrypt_c1`, `decrypt_c0`, `decrypt_c1`,
`decode`.

Server side, inside the operations (HEAAN only for now):

| stage            | `op_step` range |
|------------------|-----------------|
| `add_inside`     | 0..5            |
| `mul_inside`     | 0..25           |
| `rescale_inside` | 0..3            |
| `rot_inside`     | 0..11           |
| `boot_outside`   | 0..11           |
| `boot_coeff`     | 0..1            |
| `boot_eval`      | 0..15           |
| `boot_slot`      | 0..1            |

Neural network workload (HEAAN): `hidden_layer` (0..11), `cheby_tanh3` (0..9).

## Pipeline

The server-side workload is a string, executed left to right:

```
"add; mul x2; pmul; scalar 0.5; rot 4; boot"
```

| op         | what it does                                  |
|------------|-----------------------------------------------|
| `add`      | ct + ct (fresh encryption of the input)       |
| `mul`      | ct * ct, followed by rescale                  |
| `pmul`     | ct * plaintext                                |
| `scalar k` | ct * k                                        |
| `rot k`    | left rotation by k slots                      |
| `boot`     | bootstrapping                                 |

`x N` repeats an op N times, so `mul x3` is the same as `mul; mul; mul`.
`op_depth` counts occurrences of the op targeted by the stage, e.g. with
`add; mul x3` and `--stage mul_inside --op_depth 2` the fault lands in the
third multiplication.

The same pipeline is applied to the plaintext input to get the reference
output, so there is a sanity check before any fault is injected: if plain and
CKKS outputs don't agree, the parameters are wrong and the campaign doesn't
start.

## Build

```sh
./third_party/setup_thirdParty.sh     # clones and builds both forks
cmake -S . -B build                   # -DWITH_OPENFHE=OFF or -DWITH_HEAAN=OFF to skip one
cmake --build build -j
```

You'll need NTL and GMP for HEAAN. OpenFHE by default s built without external dependencies. Binaries end up
in `build/bin/`: `fi_heaan` and `fi_openfhe`. Both come from the same
`apps/fi_main.cpp`, the only difference is which backend is linked.

## Running

Exhaustive campaign (every limb, coefficient and bit):

```sh
./build/bin/fi_heaan --logN 6 --logQ 60 --logDelta 30 --logSlots 4 \
    --pipeline "add; mul x2" \
    --stage mul_inside --op_depth 1 --op_step 3 \
    --isExhaustive 1 --seed 1 --seed_input 1
```

Random campaign: picks `numSamples` random (limb, coeff) pairs and for each one
sweeps a fixed set of bit positions spread over `[0, Δ)`, `[Δ, Q]` and
`(Q, bitsPerCoeff)`:

```sh
./build/bin/fi_openfhe --logN 12 --logQ 60 --logDelta 40 --mult_depth 2 \
    --pipeline "mul x2" --stage encrypt_c0 --withNTT 1 \
    --isExhaustive 0 --numSamples 200 --seed 3 --seed_input 7
```

`--help` lists everything. The ones you'll use most:

| flag              | meaning                                          |
|-------------------|--------------------------------------------------|
| `--logN`          | ring dimension                                   |
| `--logQ`          | first modulus size                               |
| `--logDelta`      | scaling factor                                   |
| `--logSlots`      | input size (default `logN - 1`)                  |
| `--bitsPerCoeff`  | how many bits of each coefficient to sweep       |
| `--mult_depth`    | OpenFHE only                                     |
| `--withNTT`       | inject in NTT form (OpenFHE only)                |
| `--seed`          | seed for keys / encryption noise                 |
| `--seed_input`    | seed for the input vector                        |
| `--logMin/logMax` | input range `[2^logMin, 2^logMax]`, `0 0` means `[-1, 1]` |
| `--isComplex`     | complex input (HEAAN only)                       |
| `--amountBits`    | burst size                                       |
| `--saveVectors 1` | also dump the full output vector of every run    |
| `--results_dir`   | where to write everything (default `results/`)   |

Campaigns are single-threaded on purpose. To use more cores, launch several
processes. They can share the same `results_dir`: the registry takes a file lock
when assigning campaign ids.

## Output

```
results/
├── campaigns_start.csv     one row per campaign: id + every parameter
├── campaigns_end.csv       one row per finished campaign: counts, p95/p99, time
├── data/
│   └── campaign_000042.csv.gz    one row per injection
└── vectors/                      only with --saveVectors
    └── campaign_000042.csv.gz
```

Each row in `data/` has the fault position (`limb, coeff, bit`), the error
(`l2_abs`, `l2_rel`, `linf_abs`, `linf_rel`), whether OpenFHE's detector
flagged it, and how many slots ended up correct / degraded / corrupted /
failed (relative error thresholds of 1%, 10% and 10x).

If a campaign with exactly the same parameters is already in
`campaigns_end.csv` it's skipped. If it's in `campaigns_start.csv` but never
finished, it's re-run with the same id and its data file is overwritten.

### Typical analysis

Campaigns that only differ in `seed` / `seed_input` are repetitions of the same
experiment. To average them:

```python
import pandas as pd

start = pd.read_csv("results/campaigns_start.csv")
params = [c for c in start.columns if c not in ("campaign_id", "seed", "seed_input")]

frames = []
for _, row in start.iterrows():
    df = pd.read_csv(f"results/data/campaign_{row.campaign_id:06d}.csv.gz")
    frames.append(df.assign(**row[params].to_dict()))

data = pd.concat(frames)
heatmap = data.groupby(params + ["coeff", "bit"])["l2_rel"].mean()
```

That gives one coefficient × bit grid per configuration, which is what the
plots in `analysis/` use. The same joined table (parameters + pipeline +
fault position → error) is what goes into the ML models in `ML_tree/`.

## Repo layout

```
apps/        fi_main.cpp, the single entry point
core/        args, pipeline parser, injector, metrics, logger, registry
backends/    heaan.cpp, openfhe.cpp (+ the NN workloads)
analysis/    plotting scripts
ML_tree/     error prediction models
mathTest/    small sanity scripts (conjugation, roots of unity)
third_party/ setup script; the library forks get cloned here
```

Adding a backend means implementing the functions in
`core/backend_interface.h`: set up the context, run one iteration (with or
without a fault), return the reference output and the number of limbs.

## Status / known gaps

- OpenFHE: only client-side stages are implemented. `*_inside` and `boot_*`
  stages are HEAAN only for now.
- OpenFHE: `amountBits > 1` is not wired yet.
- The NN workloads still live in `backends/*NN/` with their own build and
  haven't been moved to the single main.
- `--scaleTech` other than `FIXEDMANUAL` may drop limbs during the pipeline;
  the number of limbs to sweep is still computed as `mult_depth + 1`.
