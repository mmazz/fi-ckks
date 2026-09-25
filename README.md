# fi-ckks

Transient fault injection for CKKS, at the level of single polynomial coefficients.

A campaign runs a small CKKS workload (encode, encrypt, some server-side operations,
decrypt, decode), flips one bit (or a few consecutive bits) of one coefficient at some
point, and measures how far the decrypted output ends up from the fault-free one. Doing
that for every coefficient and bit, or for a random subset, tells you which positions
actually matter.

Two libraries are supported, both through forks where the PRNG is seeded so that every
run is reproducible:

- HEAAN ([HEAAN-PRNG-Control](https://github.com/mmazz/HEAAN-PRNG-Control)): non-RNS
  CKKS, one big integer per coefficient, so there is only one limb.
- OpenFHE ([openfhe-PRNG-Control](https://github.com/mmazz/openfhe-PRNG-Control)): RNS +
  NTT. A fault hits one limb, in coefficient or NTT form. The fork also has an SDC
  detector, whose output is logged.

This is research code for my PhD.

## Build

You need CMake, a C++17 compiler, NTL and GMP (`libntl-dev libgmp-dev` on Debian/Ubuntu).

```sh
./third_party/setup_thirdParty.sh    # clones both forks at the pinned commits and builds them
cmake -S . -B build                  # -DWITH_OPENFHE=OFF or -DWITH_HEAAN=OFF to skip one
cmake --build build -j
```

The OpenFHE build takes a while. Binaries end up in `build/bin`:

| binary                  | what                                   |
|-------------------------|----------------------------------------|
| `fi_heaan`              | HEAAN, pipeline given as a string      |
| `fi_openfhe`            | OpenFHE, pipeline given as a string    |
| `fi_heaan_nn`           | HEAAN, neural network workload         |
| `fi_openfhe_nn`         | OpenFHE, neural network workload       |
| `fi_nn_metrics_heaan`, `fi_nn_metrics_openfhe` | accuracy of the network, no faults |

All four `fi_*` binaries are the same `apps/fi_main.cpp` linked against a different
backend, so they take the same flags. `--help` lists them.

## Running a campaign

```sh
./build/bin/fi_heaan --logN 6 --logQ 60 --logDelta 30 --logSlots 3 --bitsPerCoeff 64 \
    --pipeline "add; mul" --stage mul --op_step 3 \
    --isExhaustive 1 --seed 1 --seed_input 1 --results_dir results
```

- `--isExhaustive 1` sweeps every limb, coefficient and bit up to `bitsPerCoeff`.
- `--isExhaustive 0 --numSamples K` picks K random (limb, coeff) pairs and, for each,
  a fixed list of bits: a few below logDelta, denser between logDelta and logQ, a few
  above. With a `boot` in the pipeline it also sweeps every bit near the point where the
  boot starts to mask the fault. For HEAAN `encode` it samples every bit above logQ,
  because the plaintext sits logQ bits higher than a ciphertext.
- `--seed` controls keys and encryption noise, `--seed_input` the input vector. In random
  campaigns the sampled coefficients also depend on both.
- `--amountBits N` flips N consecutive bits starting at `bit`.

Before injecting anything the binary checks that the fault-free CKKS output matches the
same pipeline computed in plaintext. If it doesn't, the parameters are wrong and the
campaign doesn't start. Invalid configs (a stage the backend doesn't have, an `op_step`
out of range, not enough modulus for the pipeline) are rejected before setup.

### Pipeline

The server-side workload is a string, run left to right:

```
"add; mul x2; pmul; scalar 0.5; rot 4; boot"
```

| op         | what it does                                |
|------------|---------------------------------------------|
| `add`      | ct + ct (a fresh encryption of the input)   |
| `mul`      | ct * ct, then rescale                       |
| `pmul`     | ct * plaintext, then rescale                |
| `scalar k` | ct * k, then rescale                        |
| `rot k`    | left rotation by k slots, 1 <= k < slots    |
| `boot`     | bootstrapping (HEAAN only)                  |

`x N` repeats an op. `--op_depth` picks which occurrence of the target op gets the fault
(0 = the first). For `rescale`, it counts rescales, and there is one after every
`mul`, `pmul` and `scalar`.

### Stages

`--stage` says where the fault goes and `--op_step` which register inside that
operation. Client stages have no steps.

| stage                         | HEAAN op_step | OpenFHE op_step |
|-------------------------------|---------------|-----------------|
| `encode`                      | -             | -               |
| `encrypt_c0`, `encrypt_c1`    | -             | -               |
| `decrypt_c0`, `decrypt_c1`    | -             | -               |
| `decode`                      | -             | not implemented |
| `add`                         | 0..5          | 0..5            |
| `mul`, `mul_asplos`           | 0..25         | 0..10 (`mul`)   |
| `rescale`                     | 0..3          | not implemented |
| `rot`, `rot_asplos`           | 0..11         | not implemented |
| `boot`                        | 0..7          | not implemented |
| `boot_coeff`, `boot_slot`     | 0..1          | not implemented |
| `boot_eval`                   | 0..15         | not implemented |

`c0` is the part that carries the message (`bx` in HEAAN), `c1` the other one (`ax`).
In HEAAN, `mul` and `rot` put the flipped register back right after its first read.
The `_asplos` versions leave it flipped until the end of the operation. The steps are
the `flipIfStep` indices in the HEAAN fork. The OpenFHE ones are listed in
`src/pke/include/fault-hook.h` of its fork. They don't match HEAAN's one to one,
because OpenFHE multiplies and key-switches differently.

The registers that live mod qQ during key switching (some `mul` and `rot` steps) are up
to logq + logQ bits wide. For those, use `bitsPerCoeff` around `2*logQ + 4` or you only
sweep half of them. The binary prints a warning when `bitsPerCoeff` is smaller than the
register it probed.

### What "transient" means here

Every injection runs the whole workload again from the same clean state, with the same
keys and seeds. The injector checks, on every run, that the fault fired exactly once,
that it changed exactly `amountBits` bits and that only one coefficient changed. If any
of that fails the campaign aborts. Every 1000 injections, and at the start and end, it
reruns the fault-free workload and checks that the output is still bit-for-bit the
golden one. That catches a flip that leaked into keys or other shared state.

In OpenFHE a flip can leave a residue >= q of its limb. It is injected anyway and
the row is marked with `out_of_range`.

## Neural network

MLP 784 -> 64 -> 10 on MNIST, activation `0.98 z - 0.23 z^3`, run fully encrypted. It
uses the same main and injector as everything else. `--pipeline` must be empty, and
`--seed_input` is the index of the test image.

```sh
cd workloads/nn && ./mnist_download.sh && python3 ../../scripts/nn/trainingNeuralNetwork.py && cd ../..
./build/bin/fi_heaan_nn --logN 12 --logQ 220 --logDelta 30 --logSlots 10 --bitsPerCoeff 250 \
    --stage hidden_layer --op_step 4 --isExhaustive 0 --numSamples 20 --seed 1 --seed_input 0
```

Weights and `mnist_test.csv` are read from `workloads/nn/data`, or from `$FI_NN_DATA`.
If the plaintext network gets that image wrong, the campaign doesn't start. Faults in
`decrypt_*` and `decode` hit the logit of the correct class.

| stage          | op_step | HEAAN | OpenFHE | where                                   |
|----------------|---------|:-----:|:-------:|-----------------------------------------|
| client stages  | -       | yes   | yes (no `decode`) | network input / correct logit  |
| `hidden_layer` | 0..13   | yes   | yes     | registers of one neuron                 |
| `cheby_tanh3`  | 0..9    | yes   | yes     | registers of the activation             |
| `mul`          | 0..25   | yes   |         | inside x^2 * x of the activation        |
| `rescale`      | 0..3    | yes   |         | rescale after x^3                       |
| `add`          | 0..5    | yes   |         | final add of the activation             |
| `rot`          | 0..11   | yes   |         | one rotation of reduceSum               |

For the internal stages each injection picks one neuron, and for rotations one
reduceSum step. The pick is a function of seed, image and coefficient, so every bit of
a coefficient lands on the same neuron. Both are logged (`hidden_layer`,
`reduceSum_layer`). Even steps flip c0, odd steps c1. The exact registers are listed
at the top of `workloads/nn/heaan_nn.cpp`. OpenFHE always uses `FLEXIBLEAUTO` here.

## Output

```
results_dir/
├── campaigns_start.csv    one row per campaign: id + every parameter
├── campaigns_end.csv      one row per finished campaign: injections, detections, time, p95/p99
├── data/campaign_000042.csv.gz     one row per injection
└── vectors/campaign_000042.csv.gz  full output vectors, only with --saveVectors 1
```

Each row of `data/` has the fault position (`limb, coeff, bit`), the error (`l2_abs`,
`l2_rel`, `linf_abs`, `linf_rel`) and how many slots stayed correct or became degraded,
corrupted or failed (relative error above 1%, 10% and 10x). Some columns only mean
something in one case: `detected` and `out_of_range` are OpenFHE only, while
`misclassified`, `hidden_layer` and `reduceSum_layer` are NN only.

A campaign with exactly the same parameters already in `campaigns_end.csv` is skipped,
so relaunching a group only runs what's missing. One that started but never finished is
rerun with the same id. Several processes can share a `results_dir`. Just don't launch
the same config twice at the same time, because both would write the same file.

## Campaigns

Campaign groups are defined in Python and run in parallel:

```sh
python3 scripts/clientCampaigns.py                    # list the groups
python3 scripts/clientCampaigns.py sweep_* --dry-run  # print the commands
python3 scripts/serverCampaigns.py all --jobs 16
```

- `clientCampaigns.py` writes to `results_client/` (faults on the client side).
- `serverCampaigns.py` writes to `results_server/` (faults inside the operations).
- `NNCampaigns.py` writes to `results_NN/`.

## Analysis

Campaigns that only differ in `seed` / `seed_input` are repetitions of the same
experiment. `analysis/collapse.py` averages them:

```sh
python3 analysis/check_results.py results_client   # unfinished, missing or uneven campaigns
python3 analysis/collapse.py results_client        # -> results_client/collapsed/
```

The collapsed dir has one row per experiment in `campaigns_start.csv`, which also
records which campaigns and seeds went in. Each experiment has a
`data/experiment_<id>.csv.gz` with one row per (limb, coeff, bit), averaged over the
repetitions, and a small `_reps.csv.gz` with the per-repetition curves. Coefficients
are not averaged there, since the plots need them.

The plotting scripts accept either the raw dir or the collapsed one. Given a raw dir,
they refresh the cache first. After changing `add_derived` or `MEAN_COLS` in
`analysis/utils`, run `collapse.py --force`, because the cache only notices new
campaigns. The collapsed dir is also what goes to the thesis repo. It is self-contained.

The figures of the thesis are targets in `analysis/Makefile`: `make ch1`, `make ch2`,
or a single one like `make c1_fig07`. Output goes to `analysis/img/`. The main scripts:

- `bit_curve.py`: error per bit, averaged over coefficients (`--vary`, `--per`, `--split gap`)
- `step_heatmap.py`: op_step x bit, and groups steps that behave the same
- `register_map.py`, `register_map_compare.py`: coefficient x bit maps
- `flat_curve.py`: every (coeff, bit) in a row, no averaging
- `nn_sdc_curve.py`: probability of misclassification per bit (NN)
- `build_ml_dataset.py`: parameters, pipeline features and fault position -> error, as
  parquet. It includes every error column; keep only your target when training.

## Tests

```sh
cd build && ctest                # parser, backend contract, ciphertext-level flips
tests/regress.sh check           # compare against the references in tests/reference/
tests/regress.sh check --slow    # also a few real NN injections (slow)
```

`tests/regress.sh create` regenerates the references. They are ignored by `.gitignore`
(`*.csv.gz`), so add them with `git add -f`. The NN cases use a small synthetic
network (`tests/nn_testdata.py`), so no download is needed.

## Layout

```
apps/         fi_main.cpp (the only main) and small tools
core/         args, pipeline parser, injector, metrics, logger, registry
backends/     heaan.cpp, openfhe.cpp and the injector <-> library glue
workloads/nn/ the neural network (mnist.* is the plaintext part)
scripts/      campaign definitions; campaigns.py is the runner
analysis/     collapse, checks and plots
tests/        unit tests, regression script and references
mathTest/     small sanity scripts (conjugation, roots of unity)
third_party/  setup script; the forks get cloned here
```

A new backend has to implement the five functions in `core/backend_interface.h`.

## Known gaps

- OpenFHE has no `boot`, and no faults inside `rescale` or `rot`, nor at `decode`.
- OpenFHE flips are limited to 64-bit registers (`bitsPerCoeff <= 64`).
- In HEAAN, `encode` coefficients can be negative and NTL stores them as sign and
  magnitude, so a flip there changes the magnitude.
- Random campaigns sample different coefficients for each seed. That's fine for
  per-bit curves, but not for coefficient maps.
- NN data from before the refactor (Sept 2026) is not comparable with the new data.
