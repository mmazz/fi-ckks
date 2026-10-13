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

You need CMake, a C++17 compiler, NTL and GMP (`libntl-dev libgmp-dev` on Debian/Ubuntu),
and Python 3 for the campaign and analysis scripts.

```sh
./third_party/setup_thirdParty.sh    # clones both forks at the pinned commits and builds them
cmake -S . -B build                  # -DWITH_OPENFHE=OFF or -DWITH_HEAAN=OFF to skip one
cmake --build build -j               # or: make build
pip install -r analysis/requirements.txt
```

The OpenFHE build takes a while. Binaries end up in `build/bin`:

| binary                                         | what                                   |
|------------------------------------------------|----------------------------------------|
| `fi_heaan`                                     | HEAAN, pipeline given as a string      |
| `fi_openfhe`                                   | OpenFHE, pipeline given as a string    |
| `fi_heaan_nn`                                  | HEAAN, neural network workload         |
| `fi_openfhe_nn`                                | OpenFHE, neural network workload       |
| `fi_nn_metrics_heaan`, `fi_nn_metrics_openfhe` | accuracy of the network, no faults     |

The four `fi_*` campaign binaries are the same `apps/fi_main.cpp` linked against a
different backend, so they take the same flags, for exhaustive and random campaigns
alike. `--help` lists them.

## Running a campaign

```sh
./build/bin/fi_heaan --logN 6 --logQ 100 --logDelta 30 --logSlots 3 --bitsPerCoeff 104 \
    --pipeline "add; mul" --stage mul --op_step 3 \
    --isExhaustive 1 --seed 1 --seed_input 1 --results_dir /tmp/fi_example
```

- `--isExhaustive 1` sweeps every limb, coefficient and bit up to `bitsPerCoeff`.
- `--isExhaustive 0 --numSamples K` picks K distinct random (limb, coeff) pairs and, for
  each, a fixed list of bits: a few below logDelta, up to 30 evenly spaced between logDelta
  and the top of the register (as measured by the probe in HEAAN, logQ in OpenFHE), a few
  above. With a `boot` in the pipeline (HEAAN) it also
  sweeps every bit near the point where the boot starts to mask the fault.
- HEAAN `encode`: the plaintext sits logQ bits above a ciphertext (encryption adds it mod
  qQ and shifts right by logQ), so every bit below logQ is rounded away. Exhaustive
  campaigns start at bit logQ, and bit logQ + k acts as bit k of `encrypt_c0`.
- `--seed` controls keys and encryption noise, `--seed_input` the input vector. In random
  campaigns the sampled coefficients also depend on both.
- `--amountBits N` flips N consecutive bits starting at `bit` (both backends; in OpenFHE
  the burst has to fit in the 64-bit word).

Before injecting anything the binary checks that the fault-free CKKS output matches the
same pipeline computed in plaintext. If it doesn't, the parameters are wrong and the
campaign doesn't start. Invalid arguments (a stage the backend doesn't have, an OpenFHE or
NN `op_step` out of range, not enough modulus for the pipeline) are rejected before setup.
An injection point the pipeline never reaches (e.g. `--stage rot` without a `rot`, or a
HEAAN `op_step` that does not exist) is caught by the probe run. In both cases nothing is
written to `campaigns_start.csv`.

### Pipeline

The server-side workload is a string, run left to right:

```
"add x2; mul x3; boot; mul x2"
"add; pmul; scalar 0.5; rot 4"
```

| op         | what it does                                |
|------------|---------------------------------------------|
| `add`      | ct + ct (a fresh encryption of the input)   |
| `mul`      | ct * ct, then rescale                       |
| `pmul`     | ct * plaintext, then rescale                |
| `scalar k` | ct * k, then rescale                        |
| `rot k`    | left rotation by k slots, 1 <= k < slots    |
| `boot`     | bootstrapping (HEAAN only)                  |

`x N` repeats an op. The string is stored in canonical form (`"mul; mul"` becomes
`"mul x2"`), so two spellings of the same pipeline are the same campaign. `--op_depth`
picks which occurrence of the target op gets the fault (0 = the first). For `rescale` it
counts rescales, and there is one after every `mul`, `pmul` and `scalar`.

### Stages

`--stage` says where the fault goes and `--op_step` which register inside that
operation. Client stages have no steps.

| stage                                   | HEAAN op_step | OpenFHE op_step |
|-----------------------------------------|---------------|-----------------|
| `encode`                                | -             | -               |
| `encrypt_c0`, `encrypt_c1`              | -             | -               |
| `decrypt_c0`, `decrypt_c1`              | -             | -               |
| `decode`                                | -             | not implemented |
| `add`                                   | 0..5          | 0..5            |
| `pmul`, `pmul_non_transient`            | 0..5          | not implemented |
| `mul`, `mul_non_transient`              | 0..25         | 0..10 (`mul`)   |
| `rescale`                               | 0..3          | not implemented |
| `rot`, `rot_non_transient`              | 0..11         | not implemented |
| `boot`                                  | 0..7          | not implemented |
| `boot_coeff`, `boot_slot`               | 0..1          | not implemented |
| `boot_eval`                             | 0..15         | not implemented |

`c0` is the part that carries the message (`bx` in HEAAN), `c1` the other one (`ax`).
The HEAAN steps are the `flipIfStep` indices of `src/Scheme.cpp` in its fork, and the
OpenFHE ones are listed in `src/pke/include/fault-hook.h` of its fork. They don't match
one to one, because OpenFHE multiplies and key-switches differently.

In HEAAN, `pmul`, `mul` and `rot` put a flipped input register back right after the read
that uses it (a fault on the bus). The `_non_transient` versions leave it flipped until
the end of the operation, so every later read inside the operation sees it (a fault in
the register). In both cases the fault does not outlive the operation: the inputs are
restored, or the operand is a private copy.

The registers that live mod qQ during key switching (some `mul` and `rot` steps) are up
to logq + logQ bits wide. For those, use `bitsPerCoeff` around `2*logQ + 4` or you only
sweep half of them. The binary prints a warning when `bitsPerCoeff` is smaller than the
register it probed.

### What "transient" means here

Every injection runs the whole workload again from the same clean state, with the same
keys and seeds. The injector checks, on every run, that the fault fired exactly once,
that it changed exactly `amountBits` bits and that only one coefficient changed. A HEAAN
restore only counts as such if it gives back the exact original value; anything else
counts as a second flip. If any of that fails the campaign aborts. Every 1000
injections, and at the start and end, it reruns the fault-free workload and checks that
the output is still bit-for-bit the golden one. That catches a flip that leaked into keys
or other shared state.

In OpenFHE a flip can leave a residue >= q of its limb. It is injected anyway and the row
is marked with `out_of_range`.

## Neural network

MLP 784 -> 64 -> 10 on MNIST, activation `0.98 z - 0.23 z^3`, run fully encrypted. It
uses the same main and injector as everything else. `--pipeline` must be empty, and
`--seed_input` is the index of the test image.

```sh
make nn_data      # downloads MNIST into workloads/nn/data (the weights are committed)
./build/bin/fi_heaan_nn --logN 12 --logQ 220 --logDelta 30 --logSlots 10 --bitsPerCoeff 250 \
    --stage hidden_layer --op_step 4 --isExhaustive 0 --numSamples 20 --seed 1 --seed_input 0
```

Weights and `mnist_test.csv` are read from `workloads/nn/data`, or from `$FI_NN_DATA`.
`workloads/nn/train.py` retrains the network, but that gives other weights and other
results. If the plaintext network gets the image wrong, the campaign doesn't start.
Faults in `decrypt_*` and `decode` hit the logit of the correct class.

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
HEAAN `encode`, `mul` and `rot` need `bitsPerCoeff = 2*logQ + 4` (444).

## Output

```
results_dir/
├── campaigns_start.csv    one row per campaign: id + every parameter
├── campaigns_end.csv      one row per finished campaign
├── data/campaign_000042.csv.gz     one row per injection
└── vectors/campaign_000042.csv.gz  full output vectors, only with --saveVectors 1
```

`campaigns_end.csv` has the number of injections, how many the OpenFHE detector flagged,
the duration, the p95/p99 of `l2_rel`, and what the probe measured at the injection
point: the register width in bits (`reg_bits`) and the number of limbs (`limbs`). Dirs
created before those two columns existed keep their old header, and new rows follow it.

Each row of `data/` has the fault position (`limb, coeff, bit`), the error (`l2_abs`,
`l2_rel`, `linf_abs`, `linf_rel`) and how many slots stayed correct or became degraded,
corrupted or failed (relative error above 1%, 10% and 10x). The error is measured against
the fault-free CKKS output, not the plaintext one, so a masked fault gives exactly 0. The
norm of that golden output is `l2_abs / l2_rel` of any row with a non-zero error. Some
columns only mean something in one case: `detected` and `out_of_range` are OpenFHE only,
while `misclassified`, `hidden_layer` and `reduceSum_layer` are NN only.

A campaign with exactly the same parameters already in `campaigns_end.csv` is skipped,
so relaunching a group only runs what's missing. One that started but never finished is
rerun with the same id. Several processes can share a `results_dir`; a second process
with a config that is already running skips it.

The registry matches whole lines of `campaigns_start.csv`. Never add, remove or reorder
its columns (`CampaignRegistry::makeCampaignKey`): every existing campaign would stop
matching and run again.

## Campaigns

Campaign groups are defined in Python and run in parallel. Never produce data by running a
binary by hand: every campaign belongs to a group, so it is versioned and reproducible.

```sh
python3 scripts/clientCampaigns.py                    # list the groups
python3 scripts/clientCampaigns.py "sweep_*" --dry-run  # print the commands
python3 scripts/serverCampaigns.py all --jobs 16
```

| script                         | writes to         | what                                                |
|--------------------------------|-------------------|-----------------------------------------------------|
| `scripts/clientCampaigns.py`   | `results_client/` | faults on the client side (chapter 6)               |
| `scripts/serverCampaigns.py`   | `results_server/` | faults inside the operations (chapter 7)            |
| `scripts/NNCampaigns.py`       | `results_NN/`     | the neural network (chapter 8)                      |
| `burst_*` groups of the first two | `results_burst/` | multi-bit faults (`amountBits` 1, 2, 4, 8)       |

`scripts/campaigns.py` is the runner: `grid()` builds the cartesian product of a base
config and the swept parameters, and `main()` runs a list of groups with `--jobs`
processes, dropping configs repeated across groups.

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
repetitions (`n_seeds` says how many), and a small `_reps.csv.gz` with the
per-repetition curves. Coefficients are not averaged there, since the plots need them.

The plotting scripts accept either the raw dir or the collapsed one. Given a raw dir,
they refresh the cache first. The cache only notices a change in the set of finished
campaigns: after changing `analysis/utils/collapse.py` or `add_derived()`, or after
rerunning a campaign with the same id, run `collapse.py --force`. The collapsed dir is
also what goes to the thesis repo. It is self-contained.

The figures of the thesis are targets in `analysis/Makefile`: `make ch1`, `make ch2`,
or a single one like `make c1_fig07`. Output goes to `analysis/img/`. The main scripts:

- `bit_curve.py`: error per bit, averaged over coefficients (`--vary`, `--per`, `--split gap`)
- `step_heatmap.py`: op_step x bit, and groups steps that behave the same
- `register_map.py`, `register_map_compare.py`: coefficient x bit maps
- `flat_curve.py`: every (coeff, bit) in a row, no averaging
- `slot_share.py`, `slot_stats.py`: how many slots a fault breaks
- `nn_sdc_curve.py`, `nn_table.py`: probability of misclassification per bit (NN)
- `master_curve.py`, `analytic_baseline.py`, `theory_check.py`: the analytical model
  (one-bit law, predictor without fitted parameters, numerical check on a toy CKKS)
- `build_ml_dataset.py`: see below

### ML dataset

```sh
python3 analysis/build_ml_dataset.py results_client/collapsed
```

It writes `ml_dataset.parquet`, one row per (experiment, limb, coeff, bit): the fault
position, every config parameter, features of the pipeline relative to the injection
point (`mults_before`, `mults_after`, `mults_until_boot`, `boot_after`, ...), the bit
relative to the parameters (`bit_minus_delta`, `bit_minus_reg`, ...) and every measured
column. Next to it, `ml_columns.json` says which columns are features, targets, ids and
the weight, so nothing measured ends up in X by accident:

```python
cols = json.load(open("ml_columns.json"))
X, y, w = df[cols["features"]], df["err_bits"], df[cols["weight"]]
groups = df["config_id"]          # split by experiment, never by row
```

## Tests

```sh
ctest --test-dir build --output-on-failure   # parser, backend contract, ciphertext-level flips
tests/regress.sh check                       # compare against tests/reference/
tests/regress.sh check --slow                # also a few real NN injections (slow)
```

`ctest` checks that every (stage, op_step) of the list is reachable and that a fault
there leaves no trace in the next fault-free run. `regress.sh` reruns small campaigns and
compares them byte for byte with `tests/reference/`, and checks that invalid configs fail
for the right reason without registering anything. The NN cases use a small synthetic
network (`tests/nn_testdata.py`), so no download is needed.

If a change of the numbers is intended, look at the diff first, then freeze the new
references:

```sh
tests/regress.sh create
git add -f tests/reference/*.csv.gz          # *.csv.gz is gitignored
```

## Layout

```
apps/         fi_main.cpp (the only main) and small tools
core/         args, pipeline parser, injector, metrics, logger, registry
backends/     heaan.cpp, openfhe.cpp and the injector <-> library glue
workloads/nn/ the neural network (mnist.* is the plaintext part, train.py the training)
scripts/      campaign definitions; campaigns.py is the runner
analysis/     collapse, checks, plots and the ML dataset
tests/        unit tests, regression script and references
third_party/  setup script; the forks get cloned here
```

A new backend has to implement the five functions in `core/backend_interface.h`.

### Adding an OpenFHE fault site

The OpenFHE backend only arms sites that exist in its fork. To add one (e.g. inside
`EvalRotate`):

1. In the fork, add the op to `fi::Op` and its steps to an enum in
   `src/pke/include/fault-hook.h`, and call `fi::FlipIfStep(fi::Op::<op>, <step>, poly)`
   at each site. Pin the new commit in `third_party/setup_thirdParty.sh`.
2. In `backends/openfhe.cpp`: add the stage to `require_stage`, add its op_step range
   check next to the `add` / `mul` ones, and wrap the call in `run_iteration` with
   `armed(Stage::<stage>, fi::Op::<op>, d, [&] { return ...; })`.
3. Add its steps to `stages_to_probe` in `tests/backend_tests.cpp`.

The flip itself is `inject()`, so the checks above (one coefficient, `amountBits` bits,
`out_of_range`, probe) come for free.

## Known gaps

- OpenFHE has no `boot`, no faults inside `pmul`, `scalar`, `rescale` or `rot`, and none
  at `decode`. Its flips are limited to 64-bit words (`bitsPerCoeff <= 64`).
- In HEAAN, `encode` coefficients can be negative and NTL stores them as sign and
  magnitude, so a flip there changes the magnitude.
- Random campaigns sample different coefficients for each seed. That's fine for
  per-bit curves, but most cells of a coefficient map have a single repetition.
- NN data from before the refactor (September 2026) is not comparable with the new data.

## Workflow

End to end: build → run campaigns → check → plot locally → publish a data release → plot
in the thesis.

### Where things live

| Path | Contents |
|------|----------|
| `results_client/` | raw data of `scripts/clientCampaigns.py` (chapter 6 and the `ev_` figures) |
| `results_server/` | raw data of `scripts/serverCampaigns.py` (chapter 7) |
| `results_NN/` | raw data of `scripts/NNCampaigns.py` (chapter 8) |
| `results_burst/` | raw data of the `burst_*` groups |
| `<raw>/collapsed/` | local cache, written by the plotting scripts on their own |
| `export/` | staging area of the last data release (gitignored) |
| `<thesis>/figures/` | the part of `analysis/` the thesis uses, plus `data.mk` (written by `export_thesis.sh`) |
| `<thesis>/data/` | the downloaded data release (never committed) |

A campaign that is in `campaigns_start.csv` but not in `campaigns_end.csv` is ignored by
every script.

### 1. Build and test (once, and after touching the C++ or a fork)

```sh
./third_party/setup_thirdParty.sh
make build
ctest --test-dir build --output-on-failure
tests/regress.sh check
```

### 2. Add or change campaigns

- **Repetitions** are `SEEDS × INPUTS`: campaigns that differ only in `seed` / `seed_input`.
  They are averaged together. Groups that are compared in one figure should have the
  same number of repetitions.
- **`bitsPerCoeff`** has to be above `logQ`, typically `logQ + 4`. Key-switching steps
  (`mul`, `rot`) work mod q·Q and need `2·logQ + 4`. HEAAN `encode` is `logQ + logDelta`
  bits wide.
- **HEAAN levels**: after the last rescale, at least `logDelta` bits have to remain. The
  binary checks this before the baseline.
- **Exhaustive or random**: exhaustive is `limbs · 2^logN · bitsPerCoeff` injections, so
  use it with `logN` 4 or 6 for register maps. Random is `numSamples · ~35-45 bits` (more
  with a boot), and is the choice for large `logN`, the boot and the NN.

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
- `fault applied 2 times` or `contaminated state`: a bug (in the fork or here). Stop.

### 3. Run

```sh
make campaigns JOBS=10          # client + server + NN, appends to campaigns.log
make client                     # or one script only: client / server / nn
```

- Every campaign is its own process. Finished campaigns are skipped (`Campaign already
  done`), so a run can be killed and relaunched at any time.
- **Never run `make` in the root while campaigns are running.** It rebuilds the binaries
  that the running pool keeps launching.
- Progress: `wc -l results_*/campaigns_{start,end}.csv`

### 4. Check

```sh
make check                      # check_results.py on every results dir + refresh the caches
```

This lists unfinished campaigns, duplicated ids, configs with fewer repetitions than the
rest, and the share of non-finite / `out_of_range` rows per stage. It is safe to run while
campaigns are running, because the raw dirs are only read.

### 5. Plot locally

```sh
cd analysis
make ch1 burst ch2 nn           # thesis figures -> img/
make c1_fig07 SHOW=--show       # one figure, on screen
make explore OP=mul             # every op_step of one operation (choose representatives)
```

Every figure needs one config (seeds aside). If a script says `different configs; they
differ in [...]`, add that column to `--where`, or move it to `--vary` (one curve per
value) or `--per` (one figure per value).

### 6. Publish a data release

The data never goes into the thesis repo. It is published as a release asset of fi-ckks,
and the thesis Makefile downloads it.

```sh
git add -A && git commit -m "..." && git push    # the release tag points at HEAD
gh auth status
./scripts/export_thesis.sh ../licar/tesis/2026_Mazzanti <tag>
```

The script copies the scripts the thesis uses into `<thesis>/figures/`, collapses every
raw dir that has finished campaigns into `export/data/{client,server,nn,burst}` (forced
when the collapse code changed), packs it, creates the release `<tag>` on fi-ckks and
writes `<thesis>/figures/data.mk` pinned to that release.

- **A tag is never overwritten.** Running the script with an existing tag only re-pins
  it. New data needs a new tag.
- **Partial exports are fine**, even while campaigns are running: only finished
  campaigns go in, and their data file is closed before the end line is written.
- Without `<tag>`, only the scripts are copied (data pin unchanged).

### 7. Plot in the thesis

```sh
cd ../licar/tesis/2026_Mazzanti/figures
make -k all
```

The first run (and every run after `DATA_TAG` changes) downloads the release into
`../data` and replots everything. After that, only figures whose script, Makefile or
data changed are replotted. `-k` keeps going when one figure has no data yet.

### Checklist

```sh
make campaigns JOBS=10                                    # run (resumable)
make check                                                # health check
cd analysis && make ch1 burst ch2 nn && cd ..             # look at the figures
git commit -am "..." && git push                          # tag points at HEAD
./scripts/export_thesis.sh ../licar/tesis/2026_Mazzanti <new tag>
cd ../licar/tesis/2026_Mazzanti/figures && make -k all    # thesis figures
```
