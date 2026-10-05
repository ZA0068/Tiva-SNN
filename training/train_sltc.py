#!/usr/bin/env python3
"""
Train a tiny 4-neuron spiking Liquid-Time-Constant (sLTC) network to tell
"Smooth Motion" from "Turbulence" using the BMI160 accelerometer logs
recorded from the Tiva board (see tiva/main.cpp — CSV lines of
"time_ms,accel_x_g,accel_y_g,accel_z_g").

Runs entirely outside the container, on the host, with plain PyTorch (no
snnTorch — it has no built-in LTC neuron, so the sLTC cell below is a
direct, transparent implementation instead of one warped to fit a
library's existing neuron zoo).

Model
-----
Each of the 4 hidden neurons is a "liquid time-constant" leaky integrator
(Hasani et al., 2021) with a spiking (LIF-style) output on top:

    gate  = sigmoid(W_in @ x_t + W_rec @ s_{t-1} + b)   # input/state-dependent gate
    dh/dt = -h / tau + gate * (A - h)                    # liquid time constant: 1/tau_eff = 1/tau + gate
    h     = h + dt * dh/dt
    s_t   = spike(h - v_th)                              # surrogate-gradient Heaviside
    h     = h - s_t * v_th                                # soft reset

Trained end-to-end with BPTT (full backprop through the unrolled time
loop) using a surrogate gradient for the non-differentiable spike
function, which is what makes SNN-via-BPTT possible at all.

Usage
-----
    python train_sltc.py --smooth data/smooth_motion.txt --turbulence data/turbulence.txt

If the given files don't exist, small synthetic stand-ins are generated
in their place (clearly logged as such) so the script is runnable and
testable before real recordings exist.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F

torch.manual_seed(0)

HIDDEN = 4     # the network: exactly 4 sLTC neurons, as requested
INPUT = 3      # accel_x_g, accel_y_g, accel_z_g
CLASSES = 2    # 0 = smooth motion, 1 = turbulence


# ── Data loading ──────────────────────────────────────────────────────────
def load_recording(path: Path) -> list[tuple[float, float, float, float]]:
    """Parses a UART capture: skips boot-banner text, keeps CSV data rows."""
    rows = []
    with open(path, "r", errors="replace") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) != 4:
                continue
            try:
                t, x, y, z = (float(p) for p in parts)
            except ValueError:
                continue  # header row ("time_ms,accel_x_g,...") or boot text
            rows.append((t, x, y, z))
    return rows


def make_synthetic(path: Path, kind: str, n_samples: int = 1200, dt_ms: float = 50.0) -> None:
    """Writes a small synthetic stand-in in the same CSV format the firmware
    emits, so the script has something to run against before real hardware
    recordings exist. NOT real sensor data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    g = torch.Generator().manual_seed(42 if kind == "smooth" else 43)
    with open(path, "w") as f:
        f.write("time_ms,accel_x_g,accel_y_g,accel_z_g\n")
        t = 0.0
        for i in range(n_samples):
            if kind == "smooth":
                # slow sinusoidal drift + small noise, like a hand-held board panning gently
                x = 0.05 * math.sin(i * 0.02) + 0.01 * torch.randn(1, generator=g).item()
                y = 0.05 * math.cos(i * 0.017) + 0.01 * torch.randn(1, generator=g).item()
                z = 1.0 + 0.02 * torch.randn(1, generator=g).item()
            else:
                # high-frequency, high-amplitude jitter, like shaking the board
                x = 0.6 * math.sin(i * 0.9) + 0.3 * torch.randn(1, generator=g).item()
                y = 0.6 * math.cos(i * 1.3) + 0.3 * torch.randn(1, generator=g).item()
                z = 1.0 + 0.5 * torch.randn(1, generator=g).item()
            f.write(f"{t:.0f},{x:.3f},{y:.3f},{z:.3f}\n")
            t += dt_ms


def windows_from_recording(
    rows: list[tuple[float, float, float, float]], label: int, window: int, stride: int
) -> tuple[list[torch.Tensor], list[int], float]:
    if len(rows) < window:
        raise ValueError(f"recording has only {len(rows)} samples, need at least {window}")

    times = torch.tensor([r[0] for r in rows], dtype=torch.float32)
    feats = torch.tensor([r[1:] for r in rows], dtype=torch.float32)  # (N, 3)

    diffs = (times[1:] - times[:-1]).clamp(min=1.0)
    dt_s = float(diffs.median()) / 1000.0  # representative sample period, in seconds

    xs, ys = [], []
    for start in range(0, len(rows) - window + 1, stride):
        xs.append(feats[start : start + window])  # (window, 3)
        ys.append(label)
    return xs, ys, dt_s


# ── sLTC cell ────────────────────────────────────────────────────────────
class SpikeFn(torch.autograd.Function):
    """Heaviside spike with a fast-sigmoid surrogate gradient (Zenke & Ganguli)."""

    slope = 10.0

    @staticmethod
    def forward(ctx, v):
        ctx.save_for_backward(v)
        return (v > 0).float()

    @staticmethod
    def backward(ctx, grad_output):
        (v,) = ctx.saved_tensors
        sg = 1.0 / (1.0 + SpikeFn.slope * v.abs()) ** 2
        return grad_output * sg


spike = SpikeFn.apply


class SLTCCell(nn.Module):
    """A tiny fully-recurrent layer of `hidden` spiking liquid-time-constant neurons."""

    def __init__(self, input_size: int, hidden: int, v_th: float = 1.0):
        super().__init__()
        self.hidden = hidden
        self.v_th = v_th

        self.W_in = nn.Parameter(torch.randn(hidden, input_size) * 0.5)
        self.W_rec = nn.Parameter(torch.randn(hidden, hidden) * 0.3)
        self.bias = nn.Parameter(torch.zeros(hidden))
        self.log_tau = nn.Parameter(torch.full((hidden,), math.log(0.1)))  # base tau ~100ms
        self.A = nn.Parameter(torch.ones(hidden))  # target/resting potential

    def forward(self, x_seq: torch.Tensor, dt: float) -> torch.Tensor:
        # x_seq: (batch, time, input_size) -> returns spikes (batch, time, hidden)
        batch, T, _ = x_seq.shape
        h = torch.zeros(batch, self.hidden, device=x_seq.device)
        s = torch.zeros(batch, self.hidden, device=x_seq.device)
        tau = F.softplus(self.log_tau) + 1e-3

        spikes = []
        for t in range(T):
            drive = x_seq[:, t, :] @ self.W_in.T + s @ self.W_rec.T + self.bias
            gate = torch.sigmoid(drive)
            dh = -h / tau + gate * (self.A - h)
            h = h + dt * dh
            s = spike(h - self.v_th)
            h = h - s * self.v_th  # soft reset
            spikes.append(s)
        return torch.stack(spikes, dim=1)  # (batch, time, hidden)


class SLTCClassifier(nn.Module):
    def __init__(self, input_size: int, hidden: int, classes: int):
        super().__init__()
        self.cell = SLTCCell(input_size, hidden)
        self.readout = nn.Linear(hidden, classes)

    def forward(self, x_seq: torch.Tensor, dt: float) -> torch.Tensor:
        spikes = self.cell(x_seq, dt)          # (batch, time, hidden)
        rates = spikes.mean(dim=1)             # firing rate per neuron over the window
        return self.readout(rates)             # (batch, classes)


# ── C++ export ───────────────────────────────────────────────────────────
def _cpp_array1d(name: str, vals) -> str:
    body = ", ".join(f"{v:.8f}f" for v in vals)
    return f"constexpr float {name}[{len(vals)}] = {{{body}}};"


def _cpp_array2d(name: str, rows) -> str:
    lines = [f"constexpr float {name}[{len(rows)}][{len(rows[0])}] = {{"]
    for row in rows:
        body = ", ".join(f"{v:.8f}f" for v in row)
        lines.append(f"    {{{body}}},")
    lines.append("};")
    return "\n".join(lines)


def export_cpp_header(
    model: "SLTCClassifier", mean: torch.Tensor, std: torch.Tensor, dt: float,
    smooth_path: Path, turb_path: Path, path: Path,
) -> None:
    tau = F.softplus(model.cell.log_tau).detach().tolist()
    w_in = model.cell.W_in.detach().tolist()
    w_rec = model.cell.W_rec.detach().tolist()
    bias = model.cell.bias.detach().tolist()
    A = model.cell.A.detach().tolist()
    readout_w = model.readout.weight.detach().tolist()
    readout_b = model.readout.bias.detach().tolist()

    lines = [
        "#pragma once",
        "// AUTO-GENERATED by training/train_sltc.py --export-cpp — do not hand-edit.",
        f"// Trained on: {smooth_path.name} / {turb_path.name}",
        "// If either of those was a SYNTHETIC stand-in (not real sensor data), these",
        "// weights are a placeholder only — retrain on real recordings before trusting",
        "// the classifier's output.",
        "",
        "namespace sltc_weights {",
        "",
        "constexpr int HIDDEN = 4;",
        "constexpr int INPUT = 3;",
        "constexpr int CLASSES = 2;",
        f"constexpr float DT = {dt:.6f}f; // seconds, from the recording's sample period",
        "",
        "// Per-channel normalization applied to raw accel_x/y/z (in g) before the network:",
        "// x_norm = (x_raw - NORM_MEAN) / NORM_STD",
        _cpp_array1d("NORM_MEAN", mean.tolist()),
        _cpp_array1d("NORM_STD", std.tolist()),
        "",
        _cpp_array2d("W_IN", w_in),
        _cpp_array2d("W_REC", w_rec),
        _cpp_array1d("BIAS", bias),
        _cpp_array1d("TAU", tau),
        _cpp_array1d("A", A),
        "",
        _cpp_array2d("READOUT_W", readout_w),
        _cpp_array1d("READOUT_B", readout_b),
        "",
        "} // namespace sltc_weights",
        "",
    ]
    path.write_text("\n".join(lines))
    print(f"\nWrote C++ weights header: {path}")


# ── Training ─────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--smooth", type=Path, default=Path(__file__).parent / "data" / "smooth_motion.txt")
    ap.add_argument("--turbulence", type=Path, default=Path(__file__).parent / "data" / "turbulence.txt")
    ap.add_argument("--window", type=int, default=50, help="timesteps per training example")
    ap.add_argument("--stride", type=int, default=10)
    ap.add_argument("--epochs", type=int, default=300)
    ap.add_argument("--lr", type=float, default=0.02)
    ap.add_argument("--val-fraction", type=float, default=0.2)
    ap.add_argument("--export-cpp", type=Path, default=None,
                     help="write the trained weights as a C++ header to this path")
    args = ap.parse_args()

    for path, kind in ((args.smooth, "smooth"), (args.turbulence, "turbulence")):
        if not path.exists():
            print(f"[!] {path} not found — writing a SYNTHETIC stand-in (not real sensor data).")
            make_synthetic(path, kind)

    smooth_rows = load_recording(args.smooth)
    turb_rows = load_recording(args.turbulence)
    print(f"Loaded {len(smooth_rows)} smooth-motion samples from {args.smooth}")
    print(f"Loaded {len(turb_rows)} turbulence samples from {args.turbulence}")

    xs_s, ys_s, dt_s1 = windows_from_recording(smooth_rows, 0, args.window, args.stride)
    xs_t, ys_t, dt_s2 = windows_from_recording(turb_rows, 1, args.window, args.stride)
    dt = (dt_s1 + dt_s2) / 2.0
    print(f"Windowed into {len(xs_s)} smooth + {len(xs_t)} turbulence examples "
          f"(window={args.window} steps, stride={args.stride}, dt≈{dt*1000:.1f} ms)")

    X = torch.stack(xs_s + xs_t)                      # (N, window, 3)
    y = torch.tensor(ys_s + ys_t, dtype=torch.long)    # (N,)

    # Normalize using dataset statistics (zero mean, unit variance per channel).
    mean = X.reshape(-1, INPUT).mean(dim=0)
    std = X.reshape(-1, INPUT).std(dim=0).clamp(min=1e-4)
    X = (X - mean) / std

    # Shuffle + split.
    n = X.shape[0]
    perm = torch.randperm(n)
    X, y = X[perm], y[perm]
    n_val = max(1, int(n * args.val_fraction))
    X_train, y_train = X[n_val:], y[n_val:]
    X_val, y_val = X[:n_val], y[:n_val]
    print(f"Train/val split: {X_train.shape[0]} / {X_val.shape[0]} examples\n")

    model = SLTCClassifier(INPUT, HIDDEN, CLASSES)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)

    for epoch in range(1, args.epochs + 1):
        model.train()
        opt.zero_grad()
        logits = model(X_train, dt)
        loss = F.cross_entropy(logits, y_train)
        loss.backward()
        opt.step()

        if epoch % max(1, args.epochs // 10) == 0 or epoch == 1:
            model.eval()
            with torch.no_grad():
                train_acc = (logits.argmax(dim=1) == y_train).float().mean().item()
                val_logits = model(X_val, dt)
                val_loss = F.cross_entropy(val_logits, y_val).item()
                val_acc = (val_logits.argmax(dim=1) == y_val).float().mean().item()
            print(f"epoch {epoch:4d}/{args.epochs}  "
                  f"loss={loss.item():.4f}  train_acc={train_acc:.2%}  "
                  f"val_loss={val_loss:.4f}  val_acc={val_acc:.2%}")

    torch.set_printoptions(precision=4, sci_mode=False)
    print("\n" + "=" * 60)
    print("Final 4x4 recurrent weight matrix (W_rec) of the sLTC network:")
    print("(row i = incoming weights TO neuron i, from each of the 4 neurons)")
    print(model.cell.W_rec.detach())

    print("\nInput weight matrix W_in (4 neurons x [accel_x, accel_y, accel_z]):")
    print(model.cell.W_in.detach())

    print("\nLearned per-neuron time constants tau (seconds):")
    print(F.softplus(model.cell.log_tau).detach())

    print("\nReadout weights (firing rate -> [smooth, turbulence] logits):")
    print(model.readout.weight.detach())
    print("=" * 60)

    if args.export_cpp is not None:
        export_cpp_header(model, mean, std, dt, args.smooth, args.turbulence, args.export_cpp)


if __name__ == "__main__":
    main()
