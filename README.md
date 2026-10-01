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


## Workflow

End to end: build → run campaigns → check → plot locally → publish a data release → plot in the thesis.

### Where things live

| Path | Contents |
|------|----------|
| `results_client/` | raw data of `scripts/clientCampaigns.py` (chapter 1 and the `ev_` figures) |
| `results_server/` | raw data of `scripts/serverCampaigns.py` (chapter 2) |
| `results_NN/` | raw data of `scripts/NNCampaigns.py` |
| `results_taco/`, `results/` | raw data of `scripts/TACO_campaings.py` (papers, not the thesis) |
| `<raw>/collapsed/` | local cache, written by the plotting scripts on their own |
| `export/` | staging area of the last data release (gitignored) |
| `<thesis>/figures/` | the part of `analysis/` the thesis uses, plus `data.mk` (written by `export_thesis.sh`) |
| `<thesis>/data/` | the downloaded data release (never committed) |

A raw dir has three things. `campaigns_start.csv` has one row per launched campaign, with all of its parameters. `campaigns_end.csv` has one row per finished campaign. `data/campaign_XXXXXX.csv.gz` has one row per injection. A campaign that is in `start` but not in `end` is ignored by every script.

### 1. Build and test (once, and after touching the C++)

```sh
./third_party/setup_thirdParty.sh            # clones and builds both forks (once)
make build
ctest --test-dir build --output-on-failure
tests/regress.sh check                       # reference campaigns, byte for byte
```

If a change of the numbers is intended, look at the diff first. Then freeze the new references:

```sh
tests/regress.sh create
git add -f tests/reference/*.csv.gz          # *.csv.gz is gitignored
```

### 2. Add or change campaigns

Never produce data by running a binary by hand. Every campaign belongs to a group in `scripts/*Campaigns.py`, so it is versioned and reproducible.

- **Repetitions** are `SEEDS × INPUTS`: campaigns that differ only in `seed` / `seed_input`. They are averaged together. Groups that are compared in one figure should have the same number of repetitions.
- **`bitsPerCoeff`** has to be above `logQ`, typically `logQ + 4`. Key-switching steps (`mul`, `rot`) work mod q·Q and need `2·logQ + 4`. HEAAN `encode` is `logQ + logDelta` bits wide.
- **HEAAN levels**: after the last rescale, at least `logDelta` bits have to remain. The binary checks this before the baseline.
- **Exhaustive or random**: exhaustive is `limbs · 2^logN · bitsPerCoeff` injections, so use it with `logN` 4 or 6 for register maps. Random is `numSamples · ~30 bits`, and is the choice for large `logN` and for the NN.

Before launching, size the group and run a smoke test:

```sh
python3 scripts/serverCampaigns.py op_mul --dry-run | wc -l          # number of runs
python3 scripts/serverCampaigns.py op_mul --dry-run | head -1        # copy one command
./build/bin/fi_heaan <that command> --isExhaustive 0 --numSamples 1 --results_dir /tmp/smoke
```

Read its output:
- `WARNING ... sweep is incomplete`: `bitsPerCoeff` is too small.
- `never reached` / `is not implemented`: the stage or op_step does not exist in that backend.
- `Error with golden norm`: the parameters cannot run the pipeline.
- `contaminated state`: a bug. Stop.

### 3. Run

```sh
make campaigns JOBS=10          # client + server + NN, appends to campaigns.log
make client                     # or one script only: client / server / nn
```

- Every campaign is its own process. Finished campaigns are skipped (`Campaign already done`), so a run can be killed and relaunched at any time.
- **Never launch the same group twice at the same time.** Both copies get the same `campaign_id` and write the same data file.
- **Never run `make` in the root while campaigns are running.** It rebuilds the binaries that the running pool keeps launching, and it relaunches every group, which breaks the previous rule.
- Progress: `wc -l results_*/campaigns_{start,end}.csv`

### 4. Check

```sh
make check                      # check_results.py on the three dirs + refresh the caches
```

This lists unfinished campaigns, duplicated ids, configs with fewer repetitions than the rest, and the share of non-finite / `out_of_range` rows per stage. These are safe to run while campaigns are running, because the raw dirs are only read.

### 5. Plot locally

```sh
cd analysis
make ch1 ch2 ev                 # thesis figures -> img/
make c1_fig07 SHOW=--show       # one figure, on screen
make explore OP=mul             # every op_step of one operation (choose representatives)
make nn                         # NN P(SDC) curves
make client_panels              # client registers side by side (results_taco)
```

The scripts accept a raw dir or a collapsed one, and refresh `<raw>/collapsed/` on their own. That cache is rebuilt only when the set of finished campaigns changes, not when the code changes. Force it after touching `analysis/utils/collapse.py` or `add_derived()`:

```sh
python3 analysis/collapse.py results_client --force
```

`export_thesis.sh` does its own collapse and forces it when that code changed, so this is only needed for local plots.

Every figure needs one config (seeds aside). If a script says `different configs; they differ in [...]`, add that column to `--where`, or move it to `--vary` (one curve per value) or `--per` (one figure per value).

### 6. Publish a data release

The data never goes into the thesis repo. It is published as a release asset of fi-ckks, and the thesis Makefile downloads it.

```sh
git add -A && git commit -m "..." && git push    # the release tag points at HEAD
gh auth status
./scripts/export_thesis.sh ../licar/tesis/2026_Mazzanti <tag>
```

The script does five things:
1. It copies the scripts the thesis uses into `<thesis>/figures/`.
2. It collapses every raw dir that has finished campaigns into `export/data/{client,server,nn}`.
3. It packs that into `thesis-data.tar.gz`.
4. It creates the release `<tag>` on fi-ckks.
5. It writes `<thesis>/figures/data.mk` pinned to that release.

The data is collapsed: one file per experiment, with one row per `(limb, coeff, bit)` averaged over the repetitions.

- **A tag is never overwritten.** Running the script with an existing tag only re-pins it, and nothing is collapsed or published. New data needs a new tag (`thesis-data-1`, `TAG_V2`, ...).
- **Partial exports are fine**, even while campaigns are running, for example the NN client stages before the rest of the NN group finishes. Only finished campaigns go in. Every campaign in `campaigns_end.csv` has a complete data file, because the data file is closed before the end line is written. The release is a snapshot; when the rest finishes, publish a new tag.
- Without `<tag>`, only the scripts are copied (data pin unchanged).

### 7. Plot in the thesis

```sh
cd ../licar/tesis/2026_Mazzanti/figures
make -k all
```

The first run (and every run after `DATA_TAG` changes) downloads the release into `../data` and replots everything. After that, only figures whose script, Makefile or data changed are replotted. `-k` keeps going when one figure has no data yet. Commit `figures/` and `data.mk`, and keep `/data/` and `/data.tmp/` in the thesis `.gitignore`.

### Checklist

```sh
make campaigns JOBS=10                                    # run (resumable)
make check                                                # health check
cd analysis && make ch1 ch2 ev && cd ..                   # look at the figures
git commit -am "..." && git push                          # tag points at HEAD
./scripts/export_thesis.sh ../licar/tesis/2026_Mazzanti <new tag>
cd ../licar/tesis/2026_Mazzanti/figures && make -k all    # thesis figures
```
