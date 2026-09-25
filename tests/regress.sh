#!/usr/bin/env bash
# tests/regress.sh — red de seguridad para el refactor.
#
#   tests/regress.sh create   # genera/actualiza las referencias (tests/reference/*.csv.gz)
#   tests/regress.sh check    # corre todo y compara contra las referencias
#   tests/regress.sh check --slow    # ademas, la red con inyecciones reales (~5 min por caso)
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
# Datos sinteticos para el workload NN (no hace falta MNIST ni entrenar)
export FI_NN_DATA="$TMP/nndata"
python3 "$ROOT/tests/nn_testdata.py" "$FI_NN_DATA" || exit 1

PASS=0; FAIL=0; SKIP=0
pass() { echo "  PASS  $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL  $1  ($2)"; FAIL=$((FAIL+1)); }
skip() { echo "  SKIP  $1  ($2)"; SKIP=$((SKIP+1)); }

HEAAN_S="--logN 4 --logQ 60  --logDelta 30 --logSlots 3 --bitsPerCoeff 64  --seed 1 --seed_input 1"
HEAAN_L="--logN 4 --logQ 120 --logDelta 30 --logSlots 3 --bitsPerCoeff 128 --seed 1 --seed_input 1"
OFHE_S="--logN 4 --logQ 60 --logDelta 40 --logSlots 3 --bitsPerCoeff 64 --mult_depth 1 --seed 1 --seed_input 1"
# NN con numSamples 0: corre baseline + probe + chequeo de transitoriedad, sin inyectar (una corrida es lenta)
# el CSV de referencia tiene solo el header. Las inyecciones reales de la red estan en --slow.
NN_H="--isExhaustive 0 --numSamples 0 --logN 11 --logQ 220 --logDelta 30 --logSlots 10 --bitsPerCoeff 250 --seed 1 --seed_input 0"
NN_O="--isExhaustive 0 --numSamples 0 --logN 12 --logQ 60 --logDelta 50 --logSlots 10 --bitsPerCoeff 64 --mult_depth 5 --withNTT 1 --seed 1 --seed_input 0"
# nombre | binario | argumentos
CASES=(
  "heaan_encode        | fi_heaan   | --isExhaustive 1 --stage encode     $HEAAN_S"
  "heaan_encrypt_c1    | fi_heaan   | --isExhaustive 1 --stage encrypt_c1 $HEAAN_S"
  "heaan_decode        | fi_heaan   | --isExhaustive 1 --stage decode     $HEAAN_S"
  "heaan_ops_enc_c0    | fi_heaan   | --isExhaustive 1 --stage encrypt_c0 --pipeline 'add; mul x2; rot 2' $HEAAN_L"
  "heaan_ops_dec_c1    | fi_heaan   | --isExhaustive 1 --stage decrypt_c1 --pipeline 'add; mul x2; rot 2' $HEAAN_L"
  "heaan_mul_inside    | fi_heaan   | --isExhaustive 1 --stage mul --op_depth 1 --op_step 5 --pipeline 'mul x2' $HEAAN_L"
  "heaan_random        | fi_heaan   | --isExhaustive 0 --numSamples 5 --stage encrypt_c0 --pipeline 'mul' $HEAAN_L"
  "openfhe_encode      | fi_openfhe | --isExhaustive 1 --stage encode     $OFHE_S"
  "openfhe_encrypt_c0  | fi_openfhe | --isExhaustive 1 --stage encrypt_c0 $OFHE_S"
  "openfhe_add_dec_c0  | fi_openfhe | --isExhaustive 1 --stage decrypt_c0 --pipeline 'add' $OFHE_S"
  "openfhe_random      | fi_openfhe | --isExhaustive 0 --numSamples 5 --stage encrypt_c1 $OFHE_S"
  "heaannn_hidden      | fi_heaan_nn   | --stage hidden_layer --op_step 4 $NN_H"
  "heaannn_mul         | fi_heaan_nn   | --stage mul --op_step 25 $NN_H"
  "openfhenn_cheby     | fi_openfhe_nn | --stage cheby_tanh3 --op_step 9 $NN_O"
  "openfhe_add_inside  | fi_openfhe | --isExhaustive 1 --stage add --op_step 1 --pipeline 'add' $OFHE_S"
  "openfhe_mul_inside  | fi_openfhe | --isExhaustive 1 --stage mul --op_step 6 --pipeline 'mul' $OFHE_S"
)
if [[ "$SLOW" == "--slow" ]]; then
  CASES+=(
    "nnslow_heaan_hidden | fi_heaan_nn   | --stage hidden_layer --op_step 12 $NN_H --numSamples 1"
    "nnslow_heaan_mul    | fi_heaan_nn   | --stage mul --op_step 5 $NN_H --numSamples 1"
    "nnslow_openfhe_cheb | fi_openfhe_nn | --stage cheby_tanh3 --op_step 2 $NN_O --numSamples 1"
  )
fi
# Configs invalidas: tienen que fallar, POR EL MOTIVO ESPERADO, y sin registrar la campania.
# nombre | binario | argumentos | pedazo del mensaje de error esperado
MUST_FAIL=(
  "heaan_depth_fuera   | fi_heaan   | --isExhaustive 1 --stage mul --op_depth 5 --pipeline 'mul x2' $HEAAN_L   | never reach"
  "heaan_step_fuera    | fi_heaan   | --isExhaustive 1 --stage mul --op_step 999 --pipeline 'mul x2' $HEAAN_L | never reach"
  "heaan_stage_mal     | fi_heaan   | --isExhaustive 1 --stage rot --pipeline 'mul' $HEAAN_L                  | never reach"
  "heaan_pipeline_mal  | fi_heaan   | --isExhaustive 1 --stage encode --pipeline 'mul x2; rot' $HEAAN_L      | needs a value"
  "openfhe_mul_inside  | fi_openfhe | --isExhaustive 1 --stage mul --pipeline 'mul' $OFHE_S                   | never reach"
  "openfhe_boot        | fi_openfhe | --isExhaustive 1 --stage encode --pipeline 'boot' $OFHE_S               | hasn't been implemented yet"
  "heaannn_step_fuera  | fi_heaan_nn   | --stage mul --op_step 26 $NN_H                 | never reach"
  "heaannn_mal_clasif  | fi_heaan_nn   | --stage encode $NN_H --seed_input 3            | The plain network misclassifies the image"
  "heaannn_pipeline    | fi_heaan_nn   | --stage encode --pipeline 'mul' $NN_H          | --pipeline must be left empty"
  "openfhenn_mul       | fi_openfhe_nn | --stage mul $NN_O                              | never reach"
  "heaan_no_levels   | fi_heaan   | --isExhaustive 1 --stage encode --pipeline 'mul x3' $HEAAN_S | needs more than logQ"
  "openfhe_step_fuera  | fi_openfhe | --isExhaustive 1 --stage mul --op_step 11 --pipeline 'mul' $OFHE_S      | op_step 0..10"
  "heaan_boot_short    | fi_heaan   | --isExhaustive 0 --numSamples 1 --stage encrypt_c0 --pipeline 'mul; boot' --logN 4 --logQ 600 --logDelta 30 --logSlots 3 --bitsPerCoeff 610 --seed 1 --seed_input 1 | needs logQ >"
)


trim() { local s="$1"; s="${s#"${s%%[![:space:]]*}"}"; echo "${s%"${s##*[![:space:]]}"}"; }

run_case() {   # run_case <nombre> <binario> <args> <dir>  -> deja el rc en $RC
  local name="$1" bin="$2" args="$3" dir="$4"
  rm -rf "$dir"
  # eval para respetar las comillas de --pipeline '...'
  eval "\"\$BIN/\$bin\" $args --results_dir \"\$dir\"" >"$dir.log" 2>&1
  RC=$?
}
data_of() { echo "$1/data/campaign_000001.csv.gz"; }

echo "== regression cases ($MODE) =="
for entry in "${CASES[@]}"; do
  IFS='|' read -r name bin args <<<"$entry"
  name=$(trim "$name"); bin=$(trim "$bin"); args=$(trim "$args")
  [[ -x "$BIN/$bin" ]] || { skip "$name" "dosen't exist $bin"; continue; }

  run_case "$name" "$bin" "$args" "$TMP/$name"
  out=$(data_of "$TMP/$name")
  if [[ $RC -ne 0 || ! -f "$out" ]]; then
    fail "$name" "rc=$RC, see log below "; tail -5 "$TMP/$name.log" | sed 's/^/        /'; continue
  fi

  if [[ "$name" == *random* ]]; then   # las random tienen que ser deterministas
    run_case "$name" "$bin" "$args" "$TMP/${name}_bis"
    if ! cmp -s <(zcat "$out") <(zcat "$(data_of "$TMP/${name}_bis")"); then
      fail "$name" "non-deterministic: two identical runs yield different results"; continue
    fi
  fi

  if [[ "$MODE" == "create" ]]; then
    cp "$out" "$REF/$name.csv.gz"
    pass "$name (reference created, $(( $(zcat "$out" | wc -l) - 1 )) injections)"
  else
    [[ -f "$REF/$name.csv.gz" ]] || { skip "$name" "without reference, it runs 'create'"; continue; }
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
    [[ -x "$BIN/$bin" ]] || { skip "$name" "no existe $bin"; continue; }

    run_case "$name" "$bin" "$args" "$TMP/$name"
    rows=0
    [[ -f "$TMP/$name/campaigns_start.csv" ]] && rows=$(( $(wc -l <"$TMP/$name/campaigns_start.csv") - 1 ))
    if [[ $RC -eq 0 ]]; then
      fail "$name" "It finished OK, but it was bound to FAIL."
    elif [[ $rows -gt 0 ]]; then
      fail "$name" "failure, but recorded $rows campanign(s)"
    elif ! grep -q -- "$expect" "$TMP/$name.log"; then
      fail "$name" "failed for another reason (it was expected '$expect'):"
      grep -m2 -iE 'error|unrecognized|invalid' "$TMP/$name.log" | sed 's/^/        /'
    else
      pass "$name ($expect)"
    fi
  done
fi

echo "== PASS=$PASS FAIL=$FAIL SKIP=$SKIP =="
[[ $FAIL -eq 0 ]]
