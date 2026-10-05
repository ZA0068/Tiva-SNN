#!/usr/bin/env bash
# build_image.sh — Builds the tiva-snn container image.
#
# WHY THIS SCRIPT EXISTS:
#   The Linux overlay filesystem driver cannot handle spaces in mount option
#   paths (lowerdir=, upperdir=, etc.).  Because this project lives under
#   "Tiva SNN" (with a space), `podman build` / `podman-compose up --build`
#   fails with "no such device" when buildah tries to set up the overlay for
#   the build context.
#
#   This script works around the problem by creating a temporary symlink in
#   /tmp (no spaces) that points to the real project root, then calling
#   `podman build` against that symlink.  The symlink is removed on exit.
#
# USAGE (run from anywhere):
#   bash scripts/build_image.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TMP_LINK="/tmp/tiva-snn-build"

cleanup() {
    rm -f "$TMP_LINK"
}
trap cleanup EXIT

echo "→ Creating symlink: $TMP_LINK -> $PROJECT_DIR"
ln -sfn "$PROJECT_DIR" "$TMP_LINK"

echo "→ Building image tiva-snn:latest ..."
podman build \
    --tag tiva-snn:latest \
    --file "$TMP_LINK/Containerfile" \
    "$TMP_LINK"

echo ""
echo "✔ Image built successfully: tiva-snn:latest"
echo "  Start the container with:  podman-compose up -d"
