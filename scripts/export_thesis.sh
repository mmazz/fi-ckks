#!/bin/bash
# Exports the thesis figures to the lab repo. The data never goes into that repo: it is
# published as a GitHub release asset of fi-ckks, and the Makefile downloads it.
#
#   scripts/export_thesis.sh <thesis dir>          scripts only (Makefile, *.py, utils/)
#   scripts/export_thesis.sh <thesis dir> <tag>    also collapse the results, publish them
#                                                  as release <tag> and pin the thesis to it
#
#   <thesis>/figures/          mirror of analysis/: anything added there by hand is deleted
#                              on the next export (except img/ and data.mk)
#   <thesis>/figures/data.mk   pinned data release + where the Makefile finds it
#   <thesis>/data/             downloaded by make on first use, never committed
set -euo pipefail
[ $# -ge 1 ] && [ $# -le 2 ] || { echo "usage: $0 <thesis dir> [data tag]" >&2; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$1"
DEST="$(cd "$1" && pwd)"
TAG="${2:-}"

rsync -a --delete --exclude img/ --exclude __pycache__/ --exclude data.mk \
      "$ROOT/analysis/" "$DEST/figures/"

if [ -n "$TAG" ]; then
    # The release tag points at HEAD: uncommitted code would not be reproducible from it.
    git -C "$ROOT" diff --quiet HEAD || { echo "commit fi-ckks first" >&2; exit 1; }
    STAGE="$ROOT/export"                               # gitignored in fi-ckks

    # The collapse only rewrites an experiment when its SET of campaigns changes, not when
    # the code that computes its columns changes. Rebuild everything if that code changed.
    CODE_HASH="$(cat "$ROOT/analysis/utils/collapse.py" "$ROOT/analysis/utils/results.py" \
                 | sha1sum | cut -d' ' -f1)"
    for pair in client:results_client server:results_server nn:results_NN; do
        name="${pair%%:*}"; raw="$ROOT/${pair#*:}"; out="$STAGE/data/$name"
        [ -d "$raw" ] || { echo "skip $raw (missing)"; continue; }
        # Only a header line: nothing finished yet (e.g. the NN campaigns are still running).
        [ "$(wc -l < "$raw/campaigns_end.csv" 2>/dev/null || echo 0)" -gt 1 ] \
            || { echo "skip $raw (no finished campaigns)"; continue; }
        force=""
        [ "$(cat "$out/COLLAPSE_CODE" 2>/dev/null || true)" = "$CODE_HASH" ] || force="--force"
        python3 "$ROOT/analysis/collapse.py" "$raw" --out "$out" $force
        echo "$CODE_HASH" > "$out/COLLAPSE_CODE"
    done
    git -C "$ROOT" rev-parse HEAD > "$STAGE/data/VERSION"

    TARBALL="$STAGE/thesis-data.tar.gz"
    rm -f "$TARBALL"
    tar -czf "$TARBALL" --exclude=COLLAPSE_CODE -C "$STAGE/data" .
    (cd "$ROOT" && gh release create "$TAG" "$TARBALL" --target "$(git rev-parse HEAD)" \
        --title "Thesis data $TAG" --notes "Collapsed results for the thesis figures.")
    REPO="$(cd "$ROOT" && gh repo view --json nameWithOwner -q .nameWithOwner)"

    cat > "$DEST/figures/data.mk" <<MK
# Written by fi-ckks/scripts/export_thesis.sh. The Makefile downloads this release into
# ../data the first time it plots, and again whenever DATA_TAG changes.
DATA_TAG = $TAG
DATA_URL = https://github.com/$REPO/releases/download/$TAG/thesis-data.tar.gz
RES1     = ../data/client
RES2     = ../data/server
RES_NN   = ../data/nn
MK
fi

[ -f "$DEST/figures/data.mk" ] || echo "WARNING: no data.mk yet: run once with a tag"
echo "exported fi-ckks $(git -C "$ROOT" rev-parse --short HEAD) -> $DEST/figures" \
     "(data: $(sed -n 's/^DATA_TAG = //p' "$DEST/figures/data.mk" 2>/dev/null || echo none))"
