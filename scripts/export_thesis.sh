#!/bin/bash
# Exports the collapsed results and the plotting scripts to the thesis repo.
#   scripts/export_thesis.sh ../thesis
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$(cd "$1" && pwd)"

for pair in client:results_client server:results_server nn:results_NN; do
    name="${pair%%:*}"; raw="$ROOT/${pair#*:}"
    [ -d "$raw" ] || { echo "skip $raw (missing)"; continue; }
    python3 "$ROOT/analysis/collapse.py" "$raw" --out "$DEST/data/$name"
done

rsync -a --delete --exclude img/ --exclude __pycache__/ "$ROOT/analysis/" "$DEST/figures/"
git -C "$ROOT" rev-parse HEAD > "$DEST/data/VERSION"
echo "exported fi-ckks $(cat "$DEST/data/VERSION") -> $DEST"
