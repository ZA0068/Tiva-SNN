#!/usr/bin/env bash
# Locate the Tiva LaunchPad (ICDI, VID:PID 1cbe:00fd) via sysfs and point a
# human-readable symlink at it. Bus/device numbers change on every USB
# replug, so this re-resolves them fresh on every container start instead
# of relying on a hardcoded path.
set -uo pipefail

VID="1cbe"
PID="00fd"
LINK="/dev/Tiva/LaunchPad"

mkdir -p "$(dirname "$LINK")"

for dev_path in /sys/bus/usb/devices/*/; do
    [[ -f "${dev_path}idVendor" && -f "${dev_path}idProduct" ]] || continue
    if [[ "$(cat "${dev_path}idVendor")" == "$VID" && "$(cat "${dev_path}idProduct")" == "$PID" ]]; then
        bus=$(cat "${dev_path}busnum")
        devnum=$(cat "${dev_path}devnum")
        target=$(printf '/dev/bus/usb/%03d/%03d' "$bus" "$devnum")

        if [[ -e "$target" ]]; then
            ln -sf "$target" "$LINK"
            echo "==> Tiva LaunchPad found at ${target} -> ${LINK}"
        else
            echo "==> Tiva LaunchPad detected in sysfs (bus ${bus}, dev ${devnum}) but ${target}" >&2
            echo "    isn't passed through to this container. Check the 'devices:' entry in compose.yaml" >&2
            echo "    — it must mount the whole bus directory (e.g. /dev/bus/usb/${bus})." >&2
        fi
        exit 0
    fi
done

echo "==> Tiva LaunchPad (${VID}:${PID}) not found. Is it plugged in and passed through?" >&2
