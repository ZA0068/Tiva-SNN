#!/usr/bin/env bash
# Build the TIVA bare-metal firmware.
# Run this script inside the container: bash scripts/build_tiva.sh
set -euo pipefail

TIVA_DIR="/workspace/tiva"

echo "==> Cleaning previous build artefacts..."
cd "${TIVA_DIR}"
make clean

echo "==> Building TIVA firmware..."
if make all; then
    echo ""
    echo "✔  Build succeeded."
    echo "   Output: ${TIVA_DIR}/hello_tiva.elf  (ELF debug binary)"
    echo "           ${TIVA_DIR}/hello_tiva.bin  (raw binary for flashing)"
else
    echo ""
    echo "✘  Build FAILED. Check the compiler output above for errors." >&2
    exit 1
fi
