#!/bin/bash
# Clones both forks at the pinned commits and builds them.
set -e
cd "$(dirname "$0")"

HEAAN_SHA="c24295a1577e3c9248278cf4eeb7d786c041bbaa"
OPENFHE_SHA="b989e4768c65bc5de5400554546809b5217c98e4"   # first commit with fault-hook.h

[ -d HEAAN-PRNG-Control ]   || git clone https://github.com/mmazz/HEAAN-PRNG-Control.git
[ -d openfhe-PRNG-Control ] || git clone https://github.com/mmazz/openfhe-PRNG-Control.git

git -C HEAAN-PRNG-Control fetch -q
git -C HEAAN-PRNG-Control checkout -q "$HEAAN_SHA"
make -C HEAAN-PRNG-Control lib

git -C openfhe-PRNG-Control fetch -q
git -C openfhe-PRNG-Control checkout -q "$OPENFHE_SHA"
make -C openfhe-PRNG-Control          # target 'all': cmake + make + make install into ./install

echo "=== Setup completed successfully ==="
