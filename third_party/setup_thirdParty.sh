#!/bin/bash

# setup_project.sh - Script to set up the project structure
cd "$(dirname "$0")"
set -e


echo "=== Setting up project structure ==="

HEAAN_SHA="c24295a1577e3c9248278cf4eeb7d786c041bbaa"
[ -d HEAAN-PRNG-Control ] || git clone git@github.com:mmazz/HEAAN-PRNG-Control.git
git -C HEAAN-PRNG-Control fetch -q
git -C HEAAN-PRNG-Control checkout -q "$HEAAN_SHA"
make -C HEAAN-PRNG-Control lib

OPENFHE_SHA="6826c05ce64198018c3c08cee9709fd9f9888853"
[ -d openfhe-PRNG-Control ] || git clone git@github.com:mmazz/openfhe-PRNG-Control.git
git -C openfhe-PRNG-Control fetch -q
git -C openfhe-PRNG-Control checkout -q "$OPENFHE_SHA"
make -C openfhe-PRNG-Control lib
echo ""
echo "=== Building libraries ==="

# Build HEAAN if library doesn't exist
if [ ! -f "HEAAN-PRNG-Control/lib/libHEAAN.a" ]; then
    echo "Building HEAAN library..."
    cd HEAAN-PRNG-Control
    make
    cd ..
else
    echo "HEAAN library already built (libHEAAN.a found)"
fi

# Build OpenFHE if library doesn't exist
if [ ! -f "openfhe-PRNG-Control/install/lib/libOPENFHEpke.so.1" ]; then
    echo "Building OpenFHE library..."
    cd openfhe-PRNG-Control
    make
    cd ..
else
    echo "OpenFHE library already built (libOPENFHEpke.so.1 found)"
fi

echo ""
echo "=== Setup completed successfully ==="
