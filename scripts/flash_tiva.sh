#!/usr/bin/env bash
# Flash hello_tiva.bin onto the TM4C123G LaunchPad using lm4flash.
# Run this script inside the container: bash scripts/flash_tiva.sh
set -euo pipefail

BIN="/workspace/tiva/hello_tiva.bin"

echo "NOTE: Make sure the TM4C123G LaunchPad is connected and the container"
echo "      was started with USB device access (see compose.yaml)."
echo ""

# Verify lm4flash is available.
if ! command -v lm4flash &> /dev/null; then
    echo "✘  lm4flash not found in PATH. Is the container image built correctly?" >&2
    exit 1
fi

# Verify the binary exists.
if [[ ! -f "${BIN}" ]]; then
    echo "✘  Binary not found: ${BIN}" >&2
    echo "   Run scripts/build_tiva.sh first." >&2
    exit 1
fi

echo "==> Flashing ${BIN} ..."
if lm4flash "${BIN}"; then
    echo ""
    echo "✔  Flash succeeded. The board should now be running the firmware."
else
    echo ""
    echo "✘  Flash FAILED. Check USB connection and udev/plugdev permissions." >&2
    echo "   See: https://github.com/utzig/lm4tools" >&2
    exit 1
fi
