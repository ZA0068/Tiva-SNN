#!/usr/bin/env python3
"""Record a labelled accelerometer session from the Tiva into a text file.

  python3 scripts/record_dataset.py --label smooth     --seconds 60
  python3 scripts/record_dataset.py --label turbulence --seconds 60

Writes data/<label>_<n>.txt by default. Record several takes of each class
rather than one long one — the training script globs them, and varied takes
generalise far better than a single continuous recording.

What "smooth" and "turbulence" should mean in practice:
  smooth      — the board carried, tilted, rotated slowly, set down gently.
                Orientation should vary; if every smooth sample is the board
                lying flat, the network learns "Z == 1g" and nothing else.
  turbulence  — shaken, tapped, vibrated, jostled. High-frequency content.

Vary orientation in BOTH classes. Otherwise the easiest separating feature
is which way is down, and that is not what you're trying to detect.
"""

import argparse
import math
import os
import re
import statistics
import sys
import time

from tiva_serial import iter_lines, open_port

SAMPLE_RE = re.compile(r"^\d+,")


def parse_row(line):
    """Return (t_ms, x, y, z, rx, ry, rz) or None if not a sample row."""
    if not SAMPLE_RE.match(line):
        return None
    parts = line.split(",")
    if len(parts) < 7:
        return None
    try:
        return (
            int(parts[0]),
            float(parts[1]), float(parts[2]), float(parts[3]),
            int(parts[4]), int(parts[5]), int(parts[6]),
        )
    except ValueError:
        return None


def next_free_path(directory, label):
    os.makedirs(directory, exist_ok=True)
    n = 1
    while True:
        path = os.path.join(directory, f"{label}_{n:02d}.txt")
        if not os.path.exists(path):
            return path
        n += 1


def summarise(rows):
    """Per-axis stats plus the vibration proxy that separates the classes."""
    ts = [r[0] for r in rows]
    intervals = [b - a for a, b in zip(ts, ts[1:]) if 0 < b - a < 1000]
    axes = [[r[1 + i] for r in rows] for i in range(3)]
    mags = [math.sqrt(r[1] ** 2 + r[2] ** 2 + r[3] ** 2) for r in rows]
    # Mean absolute sample-to-sample jerk: low for smooth motion, high for
    # shaking. This is roughly what the network has to key on, so if it does
    # not separate your two classes, no amount of training will.
    jerk = [abs(b - a) for a, b in zip(mags, mags[1:])]
    return {
        "n": len(rows),
        "period_ms": statistics.median(intervals) if intervals else float("nan"),
        "axis_mean": [statistics.fmean(a) for a in axes],
        "axis_std": [statistics.pstdev(a) for a in axes],
        "mag_mean": statistics.fmean(mags),
        "jerk_mean": statistics.fmean(jerk) if jerk else float("nan"),
    }


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--label", required=True, choices=["smooth", "turbulence"])
    ap.add_argument("--seconds", type=float, default=60.0, help="recording length")
    ap.add_argument("--countdown", type=int, default=5, help="seconds before capture")
    ap.add_argument("--settle", type=float, default=1.0,
                    help="seconds of samples to discard at the start")
    ap.add_argument("--dir", default="data", help="output directory")
    ap.add_argument("--out", help="explicit output path (overrides --dir/--label)")
    ap.add_argument("--baud", type=int, default=115200)
    args = ap.parse_args()

    path = args.out or next_free_path(args.dir, args.label)

    print(f"Recording '{args.label}' for {args.seconds:g}s -> {path}")
    if args.label == "smooth":
        print("  Move the board slowly and deliberately. Vary its orientation.")
    else:
        print("  Shake, tap and jostle the board. Vary its orientation too.")

    rows = []
    try:
        with open_port(args.baud) as dev:
            for i in range(args.countdown, 0, -1):
                print(f"  starting in {i}...", end="\r", flush=True)
                time.sleep(1)
            print(" " * 30, end="\r")

            # The board free-runs, so the port holds whatever it emitted while
            # we were counting down. Drain it, then discard --settle seconds so
            # the take starts from motion we actually asked for.
            t0 = time.monotonic()
            discard_until = t0 + args.settle
            last_report = 0.0

            for line in iter_lines(dev, args.seconds + args.settle):
                row = parse_row(line)
                if row is None:
                    if line.startswith("#") or "WARNING" in line or "ERROR" in line:
                        print(f"  board: {line}")
                    continue
                now = time.monotonic()
                if now < discard_until:
                    continue
                rows.append(row)
                if now - last_report >= 0.5:
                    last_report = now
                    mag = math.sqrt(row[1] ** 2 + row[2] ** 2 + row[3] ** 2)
                    elapsed = now - discard_until
                    print(f"  {elapsed:5.1f}s  {len(rows):6d} samples  "
                          f"|a|={mag:5.2f} g", end="\r", flush=True)
    except KeyboardInterrupt:
        print("\n  interrupted — keeping what was captured")
    except RuntimeError as exc:
        sys.exit(str(exc))

    print(" " * 60, end="\r")
    if len(rows) < 50:
        sys.exit(f"Only {len(rows)} samples captured — is the board running?")

    st = summarise(rows)
    with open(path, "w") as f:
        f.write(f"# label={args.label}\n")
        f.write(f"# recorded={time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
        f.write(f"# samples={st['n']} median_period_ms={st['period_ms']:.1f}\n")
        f.write("time_ms,accel_x_g,accel_y_g,accel_z_g,raw_x,raw_y,raw_z\n")
        for r in rows:
            f.write(f"{r[0]},{r[1]:.3f},{r[2]:.3f},{r[3]:.3f},{r[4]},{r[5]},{r[6]}\n")

    print(f"Wrote {st['n']} samples to {path}")
    print(f"  median period : {st['period_ms']:.1f} ms "
          f"({1000 / st['period_ms']:.0f} Hz)")
    print("  per-axis mean : " + "  ".join(f"{v:+.3f}" for v in st["axis_mean"]))
    print("  per-axis std  : " + "  ".join(f"{v:.3f}" for v in st["axis_std"]))
    print(f"  |a| mean      : {st['mag_mean']:.3f} g")
    print(f"  jerk mean     : {st['jerk_mean']:.4f} g/sample   <-- compare classes")

    if args.label == "smooth" and st["jerk_mean"] > 0.05:
        print("  NOTE: that jerk figure is high for 'smooth'. Move more gently.")
    if args.label == "turbulence" and st["jerk_mean"] < 0.02:
        print("  NOTE: that jerk figure is low for 'turbulence'. Shake harder.")


if __name__ == "__main__":
    main()
