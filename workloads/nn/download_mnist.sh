#!/bin/bash
# Downloads MNIST as CSV into $FI_NN_DATA, or into data/ next to this script.
set -euo pipefail
DATA="${FI_NN_DATA:-$(dirname "$(readlink -f "$0")")/data}"
if [[ -f "$DATA/mnist_test.csv" && -f "$DATA/mnist_train.csv" ]]; then
    echo "MNIST data already in $DATA"
    exit 0
fi
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
git clone -q --depth 1 https://github.com/phoebetronic/mnist.git "$TMP/mnist"
mkdir -p "$DATA"
unzip -o -q "$TMP/mnist/mnist_test.csv.zip"  -x '__MACOSX/*' -d "$DATA"
unzip -o -q "$TMP/mnist/mnist_train.csv.zip" -x '__MACOSX/*' -d "$DATA"
echo "MNIST data in $DATA"

