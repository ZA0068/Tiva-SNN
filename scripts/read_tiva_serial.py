#!/usr/bin/env python3
"""Print the Tiva LaunchPad's UART0 stream to stdout.

Transport details live in tiva_serial.py — see that module for why this
doesn't just open /dev/ttyACM0.

  python3 scripts/read_tiva_serial.py --seconds 10 --out capture.csv
"""

import argparse
import sys

from tiva_serial import iter_lines, open_port


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--seconds", type=float, default=10.0,
                    help="capture duration; 0 = run until interrupted")
    ap.add_argument("--out", help="also tee raw output to this file")
    args = ap.parse_args()

    sink = open(args.out, "wb") if args.out else None
    total = 0
    try:
        with open_port(args.baud) as dev:
            for line in iter_lines(dev, args.seconds, sink=sink):
                total += len(line) + 1
                sys.stdout.write(line + "\n")
                sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    except RuntimeError as exc:
        sys.exit(str(exc))
    finally:
        if sink:
            sink.close()
    print(f"# {total} bytes read", file=sys.stderr)


if __name__ == "__main__":
    main()
