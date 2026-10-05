"""Shared CDC-ACM transport for the Tiva LaunchPad's UART0 stream.

The ICDI chip (VID:PID 1cbe:00fd) exposes UART0 as a standard CDC-ACM
virtual COM port, which the host kernel binds as /dev/ttyACM0. This
container gets usbfs (/dev/bus/usb) passed through but has no CAP_MKNOD,
so that tty node can't be recreated here — hence talking CDC-ACM directly
over usbfs via libusb.

The kernel's cdc_acm driver is detached for the duration (it owns the
interface and libusb can't claim it otherwise) and reattached on exit, so
/dev/ttyACM0 comes back on the host afterwards.
"""

import contextlib
import sys
import time

import usb.core
import usb.util

VID, PID = 0x1CBE, 0x00FD
COMM_IFACE, DATA_IFACE = 0, 1
EP_IN, EP_OUT = 0x82, 0x01

CDC_SET_LINE_CODING = 0x20
CDC_SET_CONTROL_LINE_STATE = 0x22


def _set_line_coding(dev, baud, stop_bits=0, parity=0, data_bits=8):
    """CDC SET_LINE_CODING: dwDTERate | bCharFormat | bParityType | bDataBits."""
    payload = bytes(
        [
            baud & 0xFF,
            (baud >> 8) & 0xFF,
            (baud >> 16) & 0xFF,
            (baud >> 24) & 0xFF,
            stop_bits,
            parity,
            data_bits,
        ]
    )
    dev.ctrl_transfer(0x21, CDC_SET_LINE_CODING, 0, COMM_IFACE, payload)


def _set_control_line_state(dev, dtr=True, rts=True):
    value = (0x01 if dtr else 0) | (0x02 if rts else 0)
    dev.ctrl_transfer(0x21, CDC_SET_CONTROL_LINE_STATE, value, COMM_IFACE, None)


@contextlib.contextmanager
def open_port(baud=115200, quiet=False):
    """Yield a claimed CDC-ACM device configured at `baud`, 8N1.

    Always reattaches the kernel driver on the way out, including on error,
    so a crash here doesn't leave the host without /dev/ttyACM0.
    """
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        raise RuntimeError(
            f"Tiva ICDI {VID:04x}:{PID:04x} not found on usbfs. "
            "Is the board plugged in and /dev/bus/usb passed through?"
        )

    def log(msg):
        if not quiet:
            print(msg, file=sys.stderr)

    log(f"# ICDI on bus {dev.bus} device {dev.address}")

    detached = []
    for iface in (COMM_IFACE, DATA_IFACE):
        if dev.is_kernel_driver_active(iface):
            dev.detach_kernel_driver(iface)
            detached.append(iface)
    if detached:
        log(f"# detached cdc_acm from interface(s) {detached} (reattached on exit)")

    try:
        usb.util.claim_interface(dev, DATA_IFACE)
        _set_line_coding(dev, baud)
        _set_control_line_state(dev, dtr=True, rts=True)
        log(f"# reading {baud} 8N1 from endpoint 0x{EP_IN:02x}")
        yield dev
    finally:
        with contextlib.suppress(usb.core.USBError):
            usb.util.release_interface(dev, DATA_IFACE)
        usb.util.dispose_resources(dev)
        for iface in detached:
            try:
                dev.attach_kernel_driver(iface)
            except usb.core.USBError as exc:
                print(
                    f"# warning: could not reattach cdc_acm to {iface}: {exc}",
                    file=sys.stderr,
                )


def iter_lines(dev, seconds=0.0, sink=None):
    """Yield decoded text lines from `dev` until `seconds` elapses (0 = forever).

    Partial reads are buffered, so a line split across two USB packets comes
    out whole. `sink`, if given, receives every raw byte as it arrives.
    """
    deadline = time.monotonic() + seconds if seconds else None
    pending = b""
    while deadline is None or time.monotonic() < deadline:
        try:
            chunk = bytes(dev.read(EP_IN, 64, timeout=500))
        except usb.core.USBTimeoutError:
            continue
        if not chunk:
            continue
        if sink is not None:
            sink.write(chunk)
            sink.flush()
        pending += chunk
        *lines, pending = pending.split(b"\n")
        for line in lines:
            yield line.decode("utf-8", "replace").rstrip("\r")
    if pending:
        yield pending.decode("utf-8", "replace")
