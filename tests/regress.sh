#!/usr/bin/env bash
# tests/regress.sh — regression safety net.
#
#   tests/regress.sh create          # generate/update the references (tests/reference/*.csv.gz)
#   tests/regress.sh check           # run everything and compare against the references
#   tests/regress.sh check --slow    # also the network with real injections (~5 min per case)
#
set -uo pipefail

MODE="${1:-check}"
SLOW="${2:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/build/bin"
REF="$ROOT/tests/reference"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$REF"
# Synthetic data for the NN workload (no MNIST download or training needed)
export FI_NN_DATA="$TMP/nndata"
python3 "$ROOT/tests/nn_testdata.py" "$FI_NN_DATA" || exit 1

PASS=0; FAIL=0; SKIP=0
pass() { echo "  PASS  $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL  $1  ($2)"; FAIL=$((FAIL+1)); }
skip() { echo "  SKIP  $1  ($2)"; SKIP=$((SKIP+1)); }

HEAAN_S="--logN 4 --logQ 60  --logDelta 30 --logSlots 3 --bitsPerCoeff 64  --seed 1 --seed_input 1"
HEAAN_L="--logN 4 --logQ 120 --logDelta 30 --logSlots 3 --bitsPerCoeff 128 --seed 1 --seed_input 1"
OFHE_S="--logN 4 --logQ 60 --logDelta 40 --logSlots 3 --bitsPerCoeff 64 --mult_depth 1 --seed 1 --seed_input 1"
# NN with numSamples 0: runs baseline + probe + transient check, no injections (one run is slow),
# so the reference CSV only has the header. Real network injections are in --slow.
NN_H="--isExhaustive 0 --numSamples 0 --logN 11 --logQ 220 --logDelta 30 --logSlots 10 --bitsPerCoeff 250 --seed 1 --seed_input 0"
NN_O="--isExhaustive 0 --numSamples 0 --logN 12 --logQ 60 --logDelta 50 --logSlots 10 --bitsPerCoeff 64 --mult_depth 5 --withNTT 1 --seed 1 --seed_input 0"

# name | binary | arguments
CASES=(
  "heaan_encode        | fi_heaan      | --isExhaustive 1 --stage encode     $HEAAN_S"
  "heaan_encrypt_c1    | fi_heaan      | --isExhaustive 1 --stage encrypt_c1 $HEAAN_S"
  "heaan_decode        | fi_heaan      | --isExhaustive 1 --stage decode     $HEAAN_S"
  "heaan_ops_enc_c0    | fi_heaan      | --isExhaustive 1 --stage encrypt_c0 --pipeline 'add; mul x2; rot 2' $HEAAN_L"
  "heaan_ops_dec_c1    | fi_heaan      | --isExhaustive 1 --stage decrypt_c1 --pipeline 'add; mul x2; rot 2' $HEAAN_L"
  "heaan_mul_inside    | fi_heaan      | --isExhaustive 1 --stage mul --op_depth 1 --op_step 5 --pipeline 'mul x2' $HEAAN_L"
  "heaan_random        | fi_heaan      | --isExhaustive 0 --numSamples 5 --stage encrypt_c0 --pipeline 'mul' $HEAAN_L"
  "openfhe_encode      | fi_openfhe    | --isExhaustive 1 --stage encode     $OFHE_S"
  "openfhe_encrypt_c0  | fi_openfhe    | --isExhaustive 1 --stage encrypt_c0 $OFHE_S"
  "openfhe_add_dec_c0  | fi_openfhe    | --isExhaustive 1 --stage decrypt_c0 --pipeline 'add' $OFHE_S"
  "openfhe_random      | fi_openfhe    | --isExhaustive 0 --numSamples 5 --stage encrypt_c1 $OFHE_S"
  "openfhe_add_inside  | fi_openfhe    | --isExhaustive 1 --stage add --op_step 1 --pipeline 'add' $OFHE_S"
  "openfhe_mul_inside  | fi_openfhe    | --isExhaustive 1 --stage mul --op_step 6 --pipeline 'mul' $OFHE_S"
  "heaannn_hidden      | fi_heaan_nn   | --stage hidden_layer --op_step 4 $NN_H"
  "heaannn_mul         | fi_heaan_nn   | --stage mul --op_step 25 $NN_H"
  "openfhenn_cheby     | fi_openfhe_nn | --stage cheby_tanh3 --op_step 9 $NN_O"
)
if [[ "$SLOW" == "--slow" ]]; then
  CASES+=(
    "nnslow_heaan_hidden | fi_heaan_nn   | --stage hidden_layer --op_step 12 $NN_H --numSamples 1"
    "nnslow_heaan_mul    | fi_heaan_nn   | --stage mul --op_step 5 $NN_H --numSamples 1"
    "nnslow_openfhe_cheb | fi_openfhe_nn | --stage cheby_tanh3 --op_step 2 $NN_O --numSamples 1"
  )
fi

# Invalid configs: they must fail, FOR THE EXPECTED REASON, and without registering the campaign.
# The expected message is matched as a fixed string (grep -F), not as a regex.
# name | binary | arguments | expected piece of the error message
MUST_FAIL=(
  # probe: the injection point exists in the backend but not in this pipeline
  "heaan_depth_out     | fi_heaan      | --isExhaustive 1 --stage mul --op_depth 5 --pipeline 'mul x2' $HEAAN_L   | never reached"
  "heaan_step_out      | fi_heaan      | --isExhaustive 1 --stage mul --op_step 999 --pipeline 'mul x2' $HEAAN_L | never reached"
  "heaan_stage_missing | fi_heaan      | --isExhaustive 1 --stage rot --pipeline 'mul' $HEAAN_L                  | never reached"
  # argument validation (before setup + baseline)
  "heaan_bad_pipeline  | fi_heaan      | --isExhaustive 1 --stage encode --pipeline 'mul x2; rot' $HEAAN_L      | needs a value"
  "heaan_client_step   | fi_heaan      | --isExhaustive 1 --stage encode --op_step 3 $HEAAN_S                   | take no --op_step"
  "heaan_no_levels     | fi_heaan      | --isExhaustive 1 --stage encode --pipeline 'mul x3' $HEAAN_S           | needs more than logQ"
  "heaan_boot_short    | fi_heaan      | --isExhaustive 0 --numSamples 1 --stage encrypt_c0 --pipeline 'mul; boot' --logN 4 --logQ 600 --logDelta 30 --logSlots 3 --bitsPerCoeff 610 --seed 1 --seed_input 1 | needs logQ >"
  "openfhe_decode      | fi_openfhe    | --isExhaustive 1 --stage decode $OFHE_S                                | is not implemented"
  "openfhe_step_out    | fi_openfhe    | --isExhaustive 1 --stage mul --op_step 11 --pipeline 'mul' $OFHE_S     | op_step 0..10"
  "openfhe_boot        | fi_openfhe    | --isExhaustive 1 --stage encode --pipeline 'boot' $OFHE_S              | hasn't been implemented yet"
  "heaannn_step_out    | fi_heaan_nn   | --stage mul --op_step 26 $NN_H                                         | has op_step 0..25"
  "heaannn_no_levels   | fi_heaan_nn   | --stage encode $NN_H --logQ 140                                        | needs logQ > 5*logDelta"
  "heaannn_pipeline    | fi_heaan_nn   | --stage encode --pipeline 'mul' $NN_H                                  | --pipeline must be left empty"
  "heaannn_misclass    | fi_heaan_nn   | --stage encode $NN_H --seed_input 3                                    | The plain network misclassifies the image"
  "openfhenn_mul       | fi_openfhe_nn | --stage mul $NN_O                                                      | is not implemented"
)


trim() { local s="$1"; s="${s#"${s%%[![:space:]]*}"}"; echo "${s%"${s##*[![:space:]]}"}"; }

run_case() {   # run_case <name> <binary> <args> <dir>  -> leaves the exit code in $RC
  local name="$1" bin="$2" args="$3" dir="$4"
  rm -rf "$dir"
  # eval so the quotes of --pipeline '...' are respected
  eval "\"\$BIN/\$bin\" $args --results_dir \"\$dir\"" >"$dir.log" 2>&1
  RC=$?
}
data_of() { echo "$1/data/campaign_000001.csv.gz"; }

echo "== regression cases ($MODE) =="
for entry in "${CASES[@]}"; do
  IFS='|' read -r name bin args <<<"$entry"
  name=$(trim "$name"); bin=$(trim "$bin"); args=$(trim "$args")
  [[ -x "$BIN/$bin" ]] || { skip "$name" "missing $bin"; continue; }

  run_case "$name" "$bin" "$args" "$TMP/$name"
  out=$(data_of "$TMP/$name")
  if [[ $RC -ne 0 || ! -f "$out" ]]; then
    fail "$name" "rc=$RC, see log below"; tail -5 "$TMP/$name.log" | sed 's/^/        /'; continue
  fi

  if [[ "$name" == *random* ]]; then   # random campaigns must be deterministic
    run_case "$name" "$bin" "$args" "$TMP/${name}_bis"
    if ! cmp -s <(zcat "$out") <(zcat "$(data_of "$TMP/${name}_bis")"); then
      fail "$name" "non-deterministic: two identical runs give different results"; continue
    fi
  fi

  if [[ "$MODE" == "create" ]]; then
    cp "$out" "$REF/$name.csv.gz"
    pass "$name (reference created, $(( $(zcat "$out" | wc -l) - 1 )) injections)"
  else
    [[ -f "$REF/$name.csv.gz" ]] || { skip "$name" "no reference, run 'create'"; continue; }
    if cmp -s <(zcat "$REF/$name.csv.gz") <(zcat "$out"); then
      pass "$name"
    else
      nd=$(diff <(zcat "$REF/$name.csv.gz") <(zcat "$out") | grep -c '^>')
      fail "$name" "$nd different rows; first difference:"
      diff <(zcat "$REF/$name.csv.gz") <(zcat "$out") | head -4 | sed 's/^/        /'
    fi
  fi
done

if [[ "$MODE" == "check" ]]; then
  echo "== invalid configs (must fail without registering) =="
  for entry in "${MUST_FAIL[@]}"; do
    IFS='|' read -r name bin args expect <<<"$entry"
    name=$(trim "$name"); bin=$(trim "$bin"); args=$(trim "$args"); expect=$(trim "$expect")
    [[ -x "$BIN/$bin" ]] || { skip "$name" "missing $bin"; continue; }

    run_case "$name" "$bin" "$args" "$TMP/$name"
    rows=0
    [[ -f "$TMP/$name/campaigns_start.csv" ]] && rows=$(( $(wc -l <"$TMP/$name/campaigns_start.csv") - 1 ))
    if [[ $RC -eq 0 ]]; then
      fail "$name" "it finished OK but should have failed"
    elif [[ $rows -gt 0 ]]; then
      fail "$name" "it failed, but registered $rows campaign(s)"
    elif ! grep -qF -- "$expect" "$TMP/$name.log"; then
      fail "$name" "failed for another reason (expected '$expect'):"
      grep -m2 -iE 'error|unrecognized|invalid' "$TMP/$name.log" | sed 's/^/        /'
    else
      pass "$name ($expect)"
    fi
  done
fi

echo "== PASS=$PASS FAIL=$FAIL SKIP=$SKIP =="
[[ $FAIL -eq 0 ]]
