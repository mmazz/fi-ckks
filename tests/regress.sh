#!/usr/bin/env bash
# tests/regress.sh — red de seguridad para el refactor.
#
#   tests/regress.sh create   # genera/actualiza las referencias (tests/reference/*.csv.gz)
#   tests/regress.sh check    # corre todo y compara contra las referencias
set -uo pipefail

MODE="${1:-check}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/build/bin"
REF="$ROOT/tests/reference"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$REF"

PASS=0; FAIL=0; SKIP=0
pass() { echo "  PASS  $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL  $1  ($2)"; FAIL=$((FAIL+1)); }
skip() { echo "  SKIP  $1  ($2)"; SKIP=$((SKIP+1)); }

HEAAN_S="--logN 4 --logQ 60  --logDelta 30 --logSlots 3 --bitsPerCoeff 64  --seed 1 --seed_input 1"
HEAAN_L="--logN 4 --logQ 120 --logDelta 30 --logSlots 3 --bitsPerCoeff 128 --seed 1 --seed_input 1"
OFHE_S="--logN 4 --logQ 60 --logDelta 40 --logSlots 3 --bitsPerCoeff 64 --mult_depth 1 --seed 1 --seed_input 1"

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
)
# Configs invalidas: tienen que fallar, POR EL MOTIVO ESPERADO, y sin registrar la campania.
# nombre | binario | argumentos | pedazo del mensaje de error esperado
MUST_FAIL=(
  "heaan_depth_fuera   | fi_heaan   | --isExhaustive 1 --stage mul --op_depth 5 --pipeline 'mul x2' $HEAAN_L   | never reach"
  "heaan_step_fuera    | fi_heaan   | --isExhaustive 1 --stage mul --op_step 999 --pipeline 'mul x2' $HEAAN_L | never reach"
  "heaan_stage_mal     | fi_heaan   | --isExhaustive 1 --stage rot --pipeline 'mul' $HEAAN_L                  | never reach"
  "heaan_pipeline_mal  | fi_heaan   | --isExhaustive 1 --stage encode --pipeline 'mul x2; rot' $HEAAN_L      | necesita un valor"
  "openfhe_mul_inside  | fi_openfhe | --isExhaustive 1 --stage mul --pipeline 'mul' $OFHE_S                   | never reach"
  "openfhe_boot        | fi_openfhe | --isExhaustive 1 --stage encode --pipeline 'boot' $OFHE_S               | no esta implementado"
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

echo "== casos de regresion ($MODE) =="
for entry in "${CASES[@]}"; do
  IFS='|' read -r name bin args <<<"$entry"
  name=$(trim "$name"); bin=$(trim "$bin"); args=$(trim "$args")
  [[ -x "$BIN/$bin" ]] || { skip "$name" "no existe $bin"; continue; }

  run_case "$name" "$bin" "$args" "$TMP/$name"
  out=$(data_of "$TMP/$name")
  if [[ $RC -ne 0 || ! -f "$out" ]]; then
    fail "$name" "rc=$RC, ver log abajo"; tail -5 "$TMP/$name.log" | sed 's/^/        /'; continue
  fi

  if [[ "$name" == *random* ]]; then   # las random tienen que ser deterministas
    run_case "$name" "$bin" "$args" "$TMP/${name}_bis"
    if ! cmp -s <(zcat "$out") <(zcat "$(data_of "$TMP/${name}_bis")"); then
      fail "$name" "no determinista: dos corridas iguales dan distinto"; continue
    fi
  fi

  if [[ "$MODE" == "create" ]]; then
    cp "$out" "$REF/$name.csv.gz"
    pass "$name (referencia creada, $(zcat "$out" | wc -l) filas)"
  else
    [[ -f "$REF/$name.csv.gz" ]] || { skip "$name" "sin referencia, corre 'create'"; continue; }
    if cmp -s <(zcat "$REF/$name.csv.gz") <(zcat "$out"); then
      pass "$name"
    else
      nd=$(diff <(zcat "$REF/$name.csv.gz") <(zcat "$out") | grep -c '^>')
      fail "$name" "$nd filas distintas; primera diferencia:"
      diff <(zcat "$REF/$name.csv.gz") <(zcat "$out") | head -4 | sed 's/^/        /'
    fi
  fi
done

if [[ "$MODE" == "check" ]]; then
  echo "== configs invalidas (tienen que fallar sin registrarse) =="
  for entry in "${MUST_FAIL[@]}"; do
    IFS='|' read -r name bin args expect <<<"$entry"
    name=$(trim "$name"); bin=$(trim "$bin"); args=$(trim "$args"); expect=$(trim "$expect")
    [[ -x "$BIN/$bin" ]] || { skip "$name" "no existe $bin"; continue; }

    run_case "$name" "$bin" "$args" "$TMP/$name"
    rows=0
    [[ -f "$TMP/$name/campaigns_start.csv" ]] && rows=$(( $(wc -l <"$TMP/$name/campaigns_start.csv") - 1 ))
    if [[ $RC -eq 0 ]]; then
      fail "$name" "termino OK y tenia que fallar"
    elif [[ $rows -gt 0 ]]; then
      fail "$name" "fallo, pero registro $rows campania(s)"
    elif ! grep -q -- "$expect" "$TMP/$name.log"; then
      fail "$name" "fallo por otro motivo (se esperaba '$expect'):"
      grep -m2 -iE 'error|unrecognized|invalid' "$TMP/$name.log" | sed 's/^/        /'
    else
      pass "$name ($expect)"
    fi
  done
fi

echo "== PASS=$PASS FAIL=$FAIL SKIP=$SKIP =="
[[ $FAIL -eq 0 ]]
