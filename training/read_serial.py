#!/usr/bin/env python3
"""
Reads the accelerometer CSV stream from the Tiva board's UART (bridged
through the LaunchPad's ICDI to a virtual COM port, e.g. /dev/ttyACM0)
and prints it live. Optionally saves it straight to a file in the format
train_sltc.py expects — point --out at training/data/smooth_motion.txt
or training/data/turbulence.txt to record a training example directly.

Runs on the host, not in the container (this is just serial I/O against
a /dev node, nothing container-specific about it).

Usage
-----
    python read_serial.py                                   # just watch the stream
    python read_serial.py --out data/smooth_motion.txt --duration 15
    python read_serial.py --port /dev/ttyACM1               # if it enumerates differently

Press Ctrl+C to stop early (also stops automatically at --duration, if given).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import serial


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="/dev/ttyACM0", help="serial device (default: /dev/ttyACM0)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--out", type=Path, default=None, help="also write raw lines to this file")
    ap.add_argument("--duration", type=float, default=None, help="stop automatically after N seconds")
    args = ap.parse_args()

    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
    except serial.SerialException as e:
        print(f"Couldn't open {args.port}: {e}", file=sys.stderr)
        print("Is the board plugged in, and do you have permission to read the port?", file=sys.stderr)
        sys.exit(1)

    out_f = None
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        out_f = open(args.out, "w")
        print(f"Recording to {args.out}" + (f" for {args.duration}s" if args.duration else " (Ctrl+C to stop)"))

    start = time.monotonic()
    line_count = 0
    try:
        while True:
            if args.duration is not None and (time.monotonic() - start) >= args.duration:
                print(f"\nReached --duration {args.duration}s, stopping.")
                break

            raw = ser.readline()
            if not raw:
                continue  # read timeout, no data this tick

            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            print(line)

            if out_f is not None:
                out_f.write(line + "\n")
                out_f.flush()
            line_count += 1
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        ser.close()
        if out_f is not None:
            out_f.close()
            print(f"Wrote {line_count} lines to {args.out}")


if __name__ == "__main__":
    main()
