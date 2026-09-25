#!/bin/bash


L="--logN 4 --logQ 120 --logDelta 30 --logSlots 3 --bitsPerCoeff 128 --seed 1 --seed_input 1 --isExhaustive 0 --numSamples 1"
for d in 0 1; do
  rm -rf /tmp/t$d
  build/bin/fi_heaan --stage add --op_depth $d --op_step 1 --pipeline 'add x2' $L --results_dir /tmp/t$d >/dev/null || exit 1
done
if cmp -s <(zcat /tmp/t0/data/*.gz) <(zcat /tmp/t1/data/*.gz); then
  echo "PASS add transitional"
else
  echo "FAIL add transitional"; exit 1
fi
for s in $(seq 0 25); do
  rm -rf /tmp/s
  build/bin/fi_heaan --stage mul --op_step $s --pipeline 'mul x2' $L --results_dir /tmp/s >/dev/null 2>&1 || echo "FAIL step $s"
done
